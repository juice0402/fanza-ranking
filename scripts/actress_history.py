#!/usr/bin/env python3
"""女優の歩み（年表）のデータを集める道具（運営者の希望「世界一の女優深掘りサイトにしたい」。2026-10-27）。Pythonの標準ライブラリだけ。

FANZA公式のAPI（ItemList の article=actress）で、出演者ごとの全作品を新しい順に100本ずつ読み、
年ごとの本数・おもなメーカー・FANZAでいちばん古い作品・100本目などの節目・よく共演している人を数えて、
site/src/data/actress_history.json に保存する（作品の一覧そのものは保存しない。数えた結果と、節目の作品の数本だけ）。

・対象: 出演者のプロフィール（actresses.json）がある人のうち、このサイトに HISTORY_MIN_ITEMS 本以上ある人。本数の多い人から
・1人につき、FANZA全体の人気順・評価順の上位 TOP_N 本も1回ずつ読んで残す（popular・rated。女優のページの「人気作ベスト10」「評価の高い作品」）
・いまの対象をぜんぶ集め終わったら、女優検索の名簿（actress_directory.json）にいて、まだ女優のページが無い人も読む（女優名鑑その3。2026-10-27 #173）。
  はじめの1回で FANZA全体の本数（total_count）を見て、DIRECTORY_MIN_TOTAL 本より少ない人は「少ない」（few）と覚えて、FEW_RECHECK_DAYS 日は飛ばす
・1回に呼ぶのは MAX_CALLS 回まで（DMMの待ち時間 DMM_INTERVAL_SEC をあける）。まだ集めていない人 → 古くなった人（REFRESH_DAYS）の順
・FANZAの作品だけを数える。ほかのサイトの情報・私生活・うわさは扱わない（守ること9）。配信より前の作品があるかもしれないので、
  画面では「デビュー作」と言い切らず「FANZAでいちばん古い作品」と書く（APIでは、波多野結衣さんのいちばん古い作品は2009年。probe_api.py の 22）
・Gemini は使わない
・失敗した人は保存しない（前のデータのまま）。続けて失敗したら、そこまでの分を保存して止める

使い方:
  python scripts/actress_history.py --update          # 集めて保存（GitHub Actions の actress-history.yml）
  python scripts/actress_history.py --update --dry    # 保存しない（何人を読むかだけ）
"""
import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import get_new_releases as G  # noqa: E402
from genre_tops import blocked  # noqa: E402  未成年を連想させる作品を外す（ジャンルの人気作品と同じ決まり）

DATA_DIR = os.path.join(ROOT, "site", "src", "data")
PATH = os.environ.get("ACTRESS_HISTORY_PATH", os.path.join(DATA_DIR, "actress_history.json"))
HISTORY_MIN_ITEMS = 10  # このサイトに、この本数以上ある人だけ（約700人。2026-10-27）
MAX_CALLS = int(os.environ.get("ACTRESS_HISTORY_CALLS", "400"))  # 1回に呼ぶ回数の上限（0.5秒ずつで約3〜4分）
MAX_MINUTES = float(os.environ.get("ACTRESS_HISTORY_MINUTES", "12"))  # 1回に使う時間の上限（APIの返事が遅く、1回に約2秒かかる日がある。ワークフローの時間切れより前に止めて保存する。2026-10-27 の1回目が20分で切れたため）
SAVE_EVERY = 10  # この人数ごとに保存する（途中で止まっても、そこまでは残る）
REFRESH_DAYS = 21  # この日数より前に集めた人は、集め直す
PAGE = 100
OFFSET_MAX = 50000  # APIの offset の上限
MILESTONES = (100, 300, 500, 1000, 2000, 3000)  # 節目（何本目）
YEAR_MAKERS = 3  # 年ごとに残すメーカーの数（多い順）
TOP_MAKERS = 8  # メーカーごとの本数・はじめての作品を残す数
TOP_COSTARS = 5  # よく共演している人の数
COSTAR_MAX_CAST = 4  # 共演を数えるのは、出演者が4人までの作品だけ（総集編で数がふくらまないように）
TOP_GENRES = 8
BEST_GENRE = "ベスト・総集編"
TITLE_MAX = 120
FAIL_STOP = 3  # 続けて失敗したら止める
TOP_N = 10  # 人気順・評価順に残す本数（女優のページの「人気作ベスト10」「評価の高い作品」。2026-10-27）
TOP_FETCH = 20  # 人気順・評価順に1回で読む本数（未成年を連想させる作品などを外しても TOP_N 本残るように）
TOP_SORTS = (("popular", "rank"), ("rated", "review"))  # 保存する名前と、APIの並べ方（人気順・評価順）。1人につき1回ずつ
DIRECTORY_PATH = os.environ.get("ACTRESS_DIRECTORY_PATH", os.path.join(DATA_DIR, "actress_directory.json"))
DIRECTORY_MIN_TOTAL = 50  # 名簿の人は、FANZA全体の作品がこの本数以上の人だけ集める（しょーくん 10/27「作品が多い人だけ増やす」。#173）
FEW_RECHECK_DAYS = 180  # 本数が少なかった名簿の人を、もう一度見るまでの日数
PAGE_MIN_ITEMS = 2  # このサイトに、この本数以上ある人は女優のページがある（site/src/config.js の ENTITY_MIN_ITEMS と同じ）
FEW = "few"  # fetch_all の答え: 本数が少ないので読まなかった


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    os.replace(tmp, path)  # 書き込み途中で止まっても壊れないように


def site_counts():
    """このサイトの作品（毎日の更新で載せた作品＋過去作品）の、出演者ごとの本数"""
    counts = Counter()
    paths = [os.path.join(DATA_DIR, "new_releases.json")]
    cat = os.path.join(DATA_DIR, "catalog")
    if os.path.isdir(cat):
        paths += [os.path.join(cat, n) for n in sorted(os.listdir(cat)) if n.endswith(".json")]
    for p in paths:
        raw = load_json(p, [])
        items = raw if isinstance(raw, list) else raw.get("items") or []
        for it in items:
            for name in set(it.get("actress") or []):
                counts[name] += 1
    return counts


def pick_targets(profiles, counts, history, today, min_items=HISTORY_MIN_ITEMS, refresh_days=REFRESH_DAYS):
    """読む人の順番: まだ集めていない人（このサイトの本数が多い順）→ 古くなった人（集めた日が古い順）"""
    stale_before = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=refresh_days)).strftime("%Y-%m-%d")
    fresh, stale = [], []
    for a in profiles:
        aid, name = a.get("id"), a.get("name")
        if not aid or not name or counts.get(name, 0) < min_items:
            continue
        row = history.get(str(aid))
        if not row:
            fresh.append((-counts[name], name, aid))
        elif str(row.get("checked") or "") < stale_before:
            stale.append((str(row.get("checked") or ""), -counts[name], name, aid))
    fresh.sort()
    stale.sort()
    return [(aid, name) for _, name, aid in fresh] + [(aid, name) for _, _, name, aid in stale]


def pick_directory(directory, counts, history, few, today, skip_ids=(), recheck_days=FEW_RECHECK_DAYS):
    """名簿（actress_directory.json の rows）から、新しく読む人: まだ集めていない・女優のページが無い（このサイトに PAGE_MIN_ITEMS 本より少ない）・
    名簿に同じ名前が1人だけ・「少ない」と覚えてから recheck_days 日たった人。名簿の順（id の順）"""
    recheck_before = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=recheck_days)).strftime("%Y-%m-%d")
    rows = [r for r in directory if isinstance(r, dict) and str(r.get("id") or "").strip() and str(r.get("name") or "").strip()]
    names = Counter(str(r["name"]).strip() for r in rows)
    skip, out, seen = {str(i) for i in skip_ids}, [], set()
    for r in rows:
        aid, name = str(r["id"]).strip(), str(r["name"]).strip()
        if aid in seen or aid in skip or aid in history or names[name] > 1 or counts.get(name, 0) >= PAGE_MIN_ITEMS:
            continue
        if str(few.get(aid) or "") >= recheck_before:
            continue
        seen.add(aid)
        out.append((aid, name))
    return out


def stale_directory(history, directory, today, skip_ids=(), refresh_days=REFRESH_DAYS):
    """名簿から集めた人（プロフィールの対象でない人）のうち、refresh_days 日より前に集めた人（集めた日が古い順）"""
    stale_before = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=refresh_days)).strftime("%Y-%m-%d")
    dir_ids = {str(r.get("id")) for r in directory if isinstance(r, dict)}
    skip = {str(i) for i in skip_ids}
    rows = [(str(r.get("checked") or ""), aid, r.get("name")) for aid, r in history.items()
            if aid in dir_ids and aid not in skip and isinstance(r, dict) and r.get("name") and str(r.get("checked") or "") < stale_before]
    return [(aid, name) for _, aid, name in sorted(rows)]


def compact(item, n=None):
    """節目などに残す1本: c 作品ID / d 発売日 / m メーカー / t タイトル（/ n 何本目）"""
    row = {"c": item["cid"], "d": G.day_key(item["date"]), "m": "" if item.get("maker") == "不明" else item.get("maker") or "", "t": (item.get("title") or "")[:TITLE_MAX]}
    if n is not None:
        row["n"] = n
    return row


def summarize(name, items, today):
    """1人分の作品（parse_api_item の形）から、年表に使う数字を作る。発売前の作品（予約）は本数を別に数える"""
    seen, works = set(), []
    for it in items:
        if not it or it["cid"] in seen or not G.day_key(it.get("date")):
            continue
        seen.add(it["cid"])
        works.append(it)
    released = sorted((w for w in works if G.day_key(w["date"]) <= today), key=lambda w: (G.day_key(w["date"]), w["cid"]))
    upcoming = len(works) - len(released)
    out = {"name": name, "checked": today, "total": len(released), "upcoming": upcoming}
    if not released:
        return out
    out["first"] = compact(released[0])
    out["latest"] = compact(released[-1])
    years = {}
    for w in released:
        y = G.day_key(w["date"])[:4]
        years.setdefault(y, Counter())[w.get("maker") or "不明"] += 1
    out["years"] = {y: {"n": sum(c.values()), "m": [[m, n] for m, n in sorted(((m, n) for m, n in c.items() if m != "不明"), key=lambda x: (-x[1], x[0]))[:YEAR_MAKERS]]} for y, c in sorted(years.items())}
    makers = {}
    for w in released:
        m = w.get("maker")
        if not m or m == "不明":
            continue
        if m not in makers:
            makers[m] = {"m": m, "n": 0, "f": G.day_key(w["date"]), "c": w["cid"]}
        makers[m]["n"] += 1
    out["makers"] = sorted(makers.values(), key=lambda x: (-x["n"], x["f"]))[:TOP_MAKERS]
    out["milestones"] = [compact(released[n - 1], n) for n in MILESTONES if len(released) >= n]
    vr = [w for w in released if G.is_vr_item(w)]
    if vr:
        out["vr"] = {"n": len(vr), "first": compact(vr[0])}
    out["best"] = sum(1 for w in released if BEST_GENRE in (w.get("genres") or []))
    out["solo"] = sum(1 for w in released if len(w.get("actress") or []) == 1)
    co = Counter()
    for w in released:
        cast = list(dict.fromkeys(w.get("actress") or []))
        if 2 <= len(cast) <= COSTAR_MAX_CAST and name in cast:
            co.update(c for c in cast if c != name)
    out["costars"] = [[c, n] for c, n in sorted(co.items(), key=lambda x: (-x[1], x[0])) if n >= 2][:TOP_COSTARS]
    gen = Counter(g for w in released for g in dict.fromkeys(w.get("genres") or []) if g != BEST_GENRE)
    out["genres"] = [[g, n] for g, n in sorted(gen.items(), key=lambda x: (-x[1], x[0]))[:TOP_GENRES]]
    return out


def fetch_all(aid, budget, sleep=time.sleep, call=None, min_total=0):
    """1人の全作品（新しい順に100本ずつ）。(作品のリスト, 呼んだ回数)。予算が足りなければ (None, 1)（はじめの1回で本数だけ見る）。
    本数が min_total より少なければ (FEW, 1)（名簿の人。読まない）"""
    call = call or G.call_api
    base = {"site": "FANZA", "service": "digital", "floor": "videoa", "article": "actress", "article_id": aid, "sort": "date", "hits": PAGE}
    res = call("ItemList", dict(base, offset=1))
    total = int(res.get("total_count") or 0)
    if total < min_total:
        return FEW, 1
    need = max(1, math.ceil(min(total, OFFSET_MAX) / PAGE))
    if need > budget:
        return None, 1
    items = [G.parse_api_item(r) for r in res.get("items") or []]
    calls = 1
    for off in range(PAGE + 1, min(total, OFFSET_MAX) + 1, PAGE):
        sleep(G.DMM_INTERVAL_SEC)
        page = call("ItemList", dict(base, offset=off))
        calls += 1
        items += [G.parse_api_item(r) for r in page.get("items") or []]
    return [i for i in items if i], calls


def top_row(raw):
    """人気順・評価順の1本（表示に要るものだけ）: c 作品ID / t タイトル / d 発売日 / a 出演者 / m メーカー / i 画像 / u FANZAのリンク / v VRなら1 / rv [★の平均×100, 件数]。
    入れないもの（未成年を連想させる・画像やリンクが無い）は None"""
    if not isinstance(raw, dict) or blocked(raw):
        return None
    p = G.parse_api_item(raw)
    if not p:
        return None
    row = G.compact_item(p, 0)
    row.pop("r", None)  # 順位は並びの順
    row["t"] = row["t"][:TITLE_MAX]
    if not row["u"] or not row["i"]:
        return None
    rv = G.parse_review(raw)
    if rv:
        row["rv"] = rv
    return row


def fetch_tops(aid, today, sleep=time.sleep, call=None):
    """1人の、FANZA全体の人気順（sort=rank）と評価順（sort=review）の上位 TOP_N 本（発売済み）。{"popular": [...], "rated": [...]}。2回呼ぶ。
    評価順は、レビューのある作品だけ"""
    call = call or G.call_api
    out = {}
    for n, (key, sort) in enumerate(TOP_SORTS):
        if n:
            sleep(G.DMM_INTERVAL_SEC)
        res = call("ItemList", {"site": "FANZA", "service": "digital", "floor": "videoa", "article": "actress", "article_id": aid,
                                "sort": sort, "hits": TOP_FETCH, "offset": 1, "lte_date": f"{today}T23:59:59"})
        rows, seen = [], set()
        for raw in res.get("items") or []:
            row = top_row(raw)
            if not row or row["c"] in seen or (key == "rated" and not row.get("rv")):
                continue
            seen.add(row["c"])
            rows.append(row)
            if len(rows) >= TOP_N:
                break
        out[key] = rows
    return out


def run(today, max_calls=MAX_CALLS, dry=False, sleep=time.sleep, call=None, max_minutes=MAX_MINUTES, clock=time.monotonic):
    profiles = (load_json(os.path.join(DATA_DIR, "actresses.json"), {}) or {}).get("actresses") or []
    data = load_json(PATH, {"updated": "", "actresses": {}})
    history = data.setdefault("actresses", {})
    counts = site_counts()
    targets = pick_targets(profiles, counts, history, today)
    # 名簿の人（女優名鑑その3。#173）: プロフィールの対象（まだ集めていない人）をぜんぶ集め終わってから。古くなった人の集め直しのあとに読む
    directory = (load_json(DIRECTORY_PATH, {}) or {}).get("rows") or []
    few = data.setdefault("few", {})
    profile_ids = {str(a.get("id")) for a in profiles if a.get("id") and a.get("name") and counts.get(a.get("name"), 0) >= HISTORY_MIN_ITEMS}
    pending = [aid for aid in profile_ids if aid not in history]
    targets += stale_directory(history, directory, today, skip_ids=profile_ids)
    new_dir = [] if pending else pick_directory(directory, counts, history, few, today, skip_ids=profile_ids)
    targets += new_dir
    from_dir = {aid for aid, _ in new_dir}
    print(f"対象 {len(targets)}人（まだ集めていない人・{REFRESH_DAYS}日より前に集めた人・名簿の人 {len(new_dir)}人）。1回に呼ぶのは {max_calls}回まで")
    if dry:
        return 0
    used, done, fails, skipped, few_n = 0, 0, 0, 0, 0
    started = clock()
    for aid, name in targets:
        if used >= max_calls:
            break
        if clock() - started > max_minutes * 60:
            print(f"{max_minutes:g}分たったので、ここまでで止めます（続きは次の回）")
            break
        try:
            items, calls = fetch_all(aid, max_calls - used - 1 - len(TOP_SORTS), sleep=sleep, call=call, min_total=DIRECTORY_MIN_TOTAL if aid in from_dir else 0)
        except RuntimeError as e:
            used += 1
            fails += 1
            print(f"::warning title=女優の歩み::{name}（{aid}）を読めませんでした: {str(e)[:120]}")
            if fails >= FAIL_STOP:
                print("続けて失敗したので、ここまでで止めます")
                break
            continue
        used += calls
        sleep(G.DMM_INTERVAL_SEC)
        if items is None:
            skipped += 1
            continue
        if items == FEW:
            few[str(aid)] = today  # 本数が少ない名簿の人。FEW_RECHECK_DAYS 日は飛ばす
            few_n += 1
            fails = 0
            continue
        row = summarize(name, items, today)
        try:
            tops = fetch_tops(aid, today, sleep=sleep, call=call)
            used += len(TOP_SORTS)
            sleep(G.DMM_INTERVAL_SEC)
        except RuntimeError as e:
            used += 1
            print(f"::warning title=女優の歩み::{name}（{aid}）の人気順・評価順を読めませんでした: {str(e)[:120]}")
            old = history.get(str(aid)) or {}
            tops = {k: old[k] for k, _ in TOP_SORTS if old.get(k)}  # 前に集めた分を残す
        fails = 0
        row.update({k: v for k, v in tops.items() if v})
        history[str(aid)] = row
        done += 1
        if done % SAVE_EVERY == 0:
            data["updated"] = today
            save_json(PATH, data)
    if done or few_n:
        data["updated"] = today
        save_json(PATH, data)
    print(f"{done}人を保存（呼んだ回数 {used}・予算が足りず次に回した人 {skipped}・本数が{DIRECTORY_MIN_TOTAL}本より少ない名簿の人 {few_n}・集めてある人 {len(history)}）")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"saved={1 if done or few_n else 0}\n")
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--update", action="store_true", help="集めて保存する")
    ap.add_argument("--dry", action="store_true", help="保存しない（何人を読むかだけ）")
    args = ap.parse_args()
    if not args.update:
        ap.print_help()
        return
    if not args.dry and not G.API_ID:
        sys.exit("❌ API_ID が設定されていません")
    today = datetime.now(G.JST).strftime("%Y-%m-%d")
    run(today, dry=args.dry)


if __name__ == "__main__":
    main()
