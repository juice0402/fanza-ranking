#!/usr/bin/env python3
"""ジャンルのページの「FANZA全体で人気の作品 TOP20」を、毎日集め直す道具（Python標準ライブラリだけ。Gemini は使わない）。

運営者の希望「APIで使えるものは全部。コレクションの中身を濃く。SEO対策も徹底」（2026-10-10）。
ジャンルのページ（/tag/<印>/）は、このサイトに載っている作品だけを並べていた。FANZA公式のAPIの ItemList は、ジャンルを指定して
（article=genre・article_id）人気順（sort=rank）に並べられるので、そのジャンルの「いまFANZA全体で人気の作品」を毎日20本ずつ保存する。

  python3 scripts/genre_tops.py --update

・ページを作るジャンル（site/src/config.js の TAG_PAGE_GENRES）の id を、ジャンルの一覧（GenreSearch・動画は floor_id=43）から引く
・ジャンルごとに、発売済みの作品を人気順に40本取り、未成年を連想させる作品（タイトル・ジャンル・シリーズ・メーカー・レーベル・出演者の名前）を除いて20本
・取れなかったジャンルは、前の日の作品のまま（7日たったら消す）
・ファイル: site/src/data/genre_tops.json
  {"updated": 集めた日, "genres": {ジャンルの名前: {"id": FANZAのジャンルの id, "date": 集めた日, "items": [{c, t, d, a, m, i, u, v}, …]}}}
  作品の形は today.json の予約の人気順と同じ（c 作品ID / t タイトル / d 発売日 / a 出演者（4人まで） / m メーカー / i 画像 / u FANZAのリンク / v VRなら1）。1作品1行
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import get_new_releases as G  # noqa: E402
from claude_comments import title_block_reason  # noqa: E402

PATH = os.environ.get("GENRE_TOPS_PATH", os.path.join(ROOT, "site", "src", "data", "genre_tops.json"))
CONFIG = os.path.join(ROOT, "site", "src", "config.js")
TOP = 20  # 1ジャンルに保存する本数
FETCH = 40  # 1ジャンルに取る本数（未成年を連想させる作品を除いても TOP 本残るように）
KEEP_DAYS = 7  # 取れなかったジャンルの、前の日の作品を残す日数
SKIP = {"ベスト・総集編"}  # 人気順に並べても、ジャンルの顔にならないもの
VIDEO_FLOOR_ID = 43


def page_genres(config_path=CONFIG):
    """ページを作るジャンル（config.js の TAG_PAGE_GENRES。ベスト・総集編は除く）"""
    text = open(config_path, encoding="utf-8").read()
    m = re.search(r"export const TAG_PAGE_GENRES = \[(.*?)\];", text, re.S)
    return [g for g in re.findall(r"'([^']+)'", m.group(1)) if g not in SKIP] if m else []


def genre_ids(call):
    """動画のジャンルの一覧 → {名前: id}（読めなければ RuntimeError）"""
    out, off = {}, 1
    for _ in range(5):
        res = call("GenreSearch", {"floor_id": VIDEO_FLOOR_ID, "hits": 500, "offset": off})
        rows = res.get("genre") or []
        for r in rows:
            if isinstance(r, dict) and r.get("name") and str(r.get("genre_id") or "").isdigit():
                out.setdefault(" ".join(str(r["name"]).split()), int(r["genre_id"]))
        off += len(rows)
        try:
            total = int(res.get("total_count"))
        except (TypeError, ValueError):
            total = 0
        if not rows or off > total:
            break
        time.sleep(G.DMM_INTERVAL_SEC)
    return out


def blocked(raw):
    """入れない理由（"" なら入れる）。タイトル・ジャンル・シリーズ・メーカー・レーベル・出演者の名前を、未成年を連想させる言葉で調べる"""
    info = raw.get("iteminfo") or {}
    texts = [raw.get("title")]
    for key in ("genre", "series", "maker", "label", "actress"):
        texts += [e.get("name") for e in info.get(key) or [] if isinstance(e, dict)]
    return next((str(t) for t in texts if t and title_block_reason({"title": str(t)}) == "minor"), "")


def fetch_top(call, gid, now):
    """そのジャンルの、発売済みの作品を人気順に → 保存する形の作品（TOP 本まで）"""
    items = call("ItemList", {"site": "FANZA", "service": "digital", "floor": "videoa", "article": "genre", "article_id": gid,
                              "sort": "rank", "hits": FETCH, "offset": 1,
                              "lte_date": G.iso(now.replace(hour=23, minute=59, second=59))}).get("items") or []
    out, seen = [], set()
    for raw in items:
        if not isinstance(raw, dict) or blocked(raw):
            continue
        p = G.parse_api_item(raw)
        if not p or p["cid"] in seen:
            continue
        row = G.compact_item(p, len(out) + 1)
        if not row["u"] or not row["i"]:
            continue
        row.pop("r", None)  # 順位は並びの順
        seen.add(p["cid"])
        out.append(row)
        if len(out) >= TOP:
            break
    return out


def load(path=PATH):
    """前のデータ（無ければ・壊れていれば空）"""
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {"updated": "", "genres": {}}
    genres = raw.get("genres") if isinstance(raw, dict) and isinstance(raw.get("genres"), dict) else {}
    out = {}
    for name, g in genres.items():
        if isinstance(g, dict) and isinstance(g.get("items"), list) and isinstance(g.get("id"), int) and re.match(r"^\d{4}-\d{2}-\d{2}$", str(g.get("date") or "")):
            out[name] = {"id": g["id"], "date": g["date"], "items": [r for r in g["items"] if isinstance(r, dict) and r.get("c")][:TOP]}
    return {"updated": str(raw.get("updated") or "") if isinstance(raw, dict) else "", "genres": out}


def dump(data):
    """1作品1行（ジャンルは config.js の順ではなく名前の順）"""
    parts = []
    for name in sorted(data["genres"]):
        g = data["genres"][name]
        rows = ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in g["items"])
        parts.append(f'{json.dumps(name, ensure_ascii=False)}:{{"id":{g["id"]},"date":{json.dumps(g["date"])},"items":[\n{rows}\n]}}')
    return f'{{"updated":{json.dumps(data["updated"])},"genres":{{\n' + ",\n".join(parts) + "\n}}\n"


def update(now, call=None, path=PATH, genres=None):
    """集めて保存する → 結果の要約の行"""
    call = call or G.call_api
    today_str = now.strftime("%Y-%m-%d")
    names = genres if genres is not None else page_genres()
    old = load(path)
    try:
        ids = genre_ids(call)
    except RuntimeError as e:
        ids = {n: g["id"] for n, g in old["genres"].items()}  # 一覧を読めなければ、前に使った id で
        print(f"  ⚠️ ジャンルの一覧を読めませんでした（前の id を使います）: {e}")
    new = {"updated": today_str, "genres": {}}
    lines, fails = [], 0
    for name in names:
        gid = ids.get(name)
        prev = old["genres"].get(name)
        got = None
        if gid and fails < 3:
            try:
                got = fetch_top(call, gid, now)
                fails = 0
            except RuntimeError as e:
                fails += 1
                print(f"  ⚠️ {name} を読めませんでした: {e}")
            time.sleep(G.DMM_INTERVAL_SEC)
        if got:
            new["genres"][name] = {"id": gid, "date": today_str, "items": got}
            lines.append(f"- {name}: {len(got)}本")
        elif prev and 0 <= (G.days_between(prev["date"], today_str) or 0) <= KEEP_DAYS:
            new["genres"][name] = prev
            lines.append(f"- {name}: 取れなかったので前のまま（{prev['date']}）")
        else:
            lines.append(f"- {name}: なし")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(dump(new))
    os.replace(path + ".tmp", path)
    return lines


def main():
    parser = argparse.ArgumentParser(description="ジャンルのページの「FANZA全体で人気の作品」を集める")
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()
    if not args.update:
        parser.print_help()
        return
    if not G.API_ID:
        sys.exit("❌ API_ID が設定されていません")
    lines = update(datetime.now(G.JST))
    for line in lines:
        print(line)
    G.write_step_summary(["### 🏷 ジャンルの「FANZA全体で人気の作品」", "", *lines])


if __name__ == "__main__":
    main()
