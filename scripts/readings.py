#!/usr/bin/env python3
"""ジャンル・メーカー・シリーズ・作家の「読みがな」を集める道具（Python標準ライブラリだけ。Gemini は使わない）。

運営者の希望「APIで使えるものは全部。SEO対策も徹底」（2026-10-10）。FANZA公式のAPIの GenreSearch・MakerSearch・SeriesSearch・AuthorSearch は、
名前と読みがな（ruby）を返す（2026-10-10 に本物で確かめた。動画のメーカー 4,739件・シリーズ 44,350件・同人のメーカー 29,616件など）。
読みがなは、一覧のページの「50音で探す」と、作品検索で、ひらがなで打っても見つかるようにするのに使う。

  python3 scripts/readings.py --update [--force]

・7日に1回（前に集めてから7日たった日だけ。--force で、いつでも）。一覧を500件ずつ読む（1回 MAX_CALLS 回まで。読みきれなかった一覧は、次の日に続きから）
・保存するのは、このサイトに載っている名前（作品データにあるメーカー・シリーズ・ジャンル・作家）の読みがなだけ
・読めなかった一覧は、前の読みがなのまま（消さない）
・ファイル: site/src/data/readings.json
  {"updated": 一回り読み終えた日, "next": {"<売り場>.<種類>": 次に読む位置（途中の一覧だけ）},
   "<売り場>": {"genre": {名前: 読み}, "maker": {キー: 読み}, "series": {シリーズの id: 読み}, "author": {名前: 読み}}}
  メーカーのキーは、動画は名前（作品データにメーカーの id が無いため）、同人・ゲームは id。1つの読みを1行に
"""
import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import get_new_releases as G  # noqa: E402
import floor_data as F  # noqa: E402

DATA = os.path.join(ROOT, "site", "src", "data")
PATH = os.environ.get("READINGS_PATH", os.path.join(DATA, "readings.json"))
EVERY_DAYS = 7
HITS = 500
MAX_CALLS = 400  # 1回の上限（念のため）
KINDS = ("genre", "maker", "series", "author")
# 売り場: FloorList の id（2026-10-10 に本物で確かめた。動画は 43、同人・ゲームなどは floor_data.FLOORS の floor_id）と、集める一覧
# （作家の一覧 AuthorSearch は、ゲームなどでは使えるが、動画・同人では0件だった＝floor_data.FLOORS の author_search）
FLOOR_IDS = {"video": 43, **{k: c["floor_id"] for k, c in F.FLOORS.items()}}
LISTS = {"video": ("genre", "maker", "series"),
         **{k: ("genre", "maker", "series", "author") if c.get("author_search") else ("genre", "maker", "series") for k, c in F.FLOORS.items()}}
API = {"genre": ("GenreSearch", "genre", "genre_id"), "maker": ("MakerSearch", "maker", "maker_id"),
       "series": ("SeriesSearch", "series", "series_id"), "author": ("AuthorSearch", "author", "author_id")}


def clean_ruby(text):
    """読みがな（ひらがな・カタカナ・英数字・記号）。空白はつめる。60文字まで"""
    return "".join(str(text or "").split())[:60]


def wanted(data_dir=DATA):
    """このサイトに載っている名前・id → {売り場: {種類: set(キー)}}"""
    out = {k: {kind: set() for kind in KINDS} for k in LISTS}
    video = []
    try:
        video += json.load(open(os.path.join(data_dir, "new_releases.json"), encoding="utf-8"))
    except (OSError, ValueError):
        pass
    for path in glob.glob(os.path.join(data_dir, "catalog", "*.json")):
        try:
            video += json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            continue
    for it in video:
        if not isinstance(it, dict):
            continue
        if it.get("maker") and it["maker"] != "不明":
            out["video"]["maker"].add(str(it["maker"]))
        if it.get("series_id"):
            out["video"]["series"].add(str(it["series_id"]))
        for g in it.get("genres") or []:
            out["video"]["genre"].add(str(g))
    for key in F.FLOORS:
        try:
            data = F.load_floor(F.floor_path(key)) or {"items": {}}
        except ValueError:
            continue
        for it in data["items"].values():
            if it["maker_id"]:
                out[key]["maker"].add(str(it["maker_id"]))
            if it["series_id"]:
                out[key]["series"].add(str(it["series_id"]))
            for g in it["genres"] + it["formats"]:
                out[key]["genre"].add(g)
            for a in it["authors"]:
                out[key]["author"].add(a)
    return out


def fetch_list(floor_id, kind, call, budget, start=1):
    """一覧を start 件目から読む → ({キー: 読み}（キーは名前と "#id" の両方）, 次に読む位置（最後まで読めたら 0）, 呼んだ回数)"""
    endpoint, field, id_key = API[kind]
    out, off, calls, total, hits = {}, start, 0, 0, HITS
    while calls < budget:
        try:
            res = call(endpoint, {"floor_id": floor_id, "hits": hits, "offset": off})
        except RuntimeError as e:
            if hits > 100 and calls == 0:
                hits = 100  # 500件ずつが使えなければ100件ずつ
                continue
            print(f"  ⚠️ {endpoint}（floor_id={floor_id}・{off}件目から）を読めませんでした: {e}")
            # 少しでも進んでいれば、次の日に続きから。はじめから読めなければ、次の一回り（7日後）にまた
            return out, (off if off > start else 0), calls
        calls += 1
        rows = res.get(field) or []
        try:
            total = int(res.get("total_count"))
        except (TypeError, ValueError):
            pass
        for r in rows:
            if not isinstance(r, dict):
                continue
            ruby = clean_ruby(r.get("ruby"))
            name = " ".join(str(r.get("name") or "").split())
            if not ruby or not name:
                continue
            out.setdefault(name, ruby)
            if r.get(id_key) not in (None, ""):
                out.setdefault(f"#{r[id_key]}", ruby)
        time.sleep(G.DMM_INTERVAL_SEC)
        off += len(rows)
        if not rows or off > total:
            return out, 0, calls
    return out, off, calls


def load(path=PATH):
    """前のデータ（無ければ空・壊れていても空から。読みがなは、また集まる）"""
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    nxt = raw.get("next") if isinstance(raw.get("next"), dict) else {}
    out = {"updated": str(raw.get("updated") or ""),
           "next": {str(a): b for a, b in nxt.items() if isinstance(b, int) and not isinstance(b, bool) and b >= 1}}
    for k in LISTS:
        src = raw.get(k) if isinstance(raw.get(k), dict) else {}
        out[k] = {kind: {str(a): clean_ruby(b) for a, b in src[kind].items() if clean_ruby(b)} if isinstance(src.get(kind), dict) else {} for kind in KINDS}
    return out


def dump(data):
    """1つの読みを1行に（キーの順）"""
    parts = [f'{{"updated":{json.dumps(data["updated"])}', f'"next":{json.dumps(data["next"], sort_keys=True)}']
    for k in LISTS:
        kinds = []
        for kind in KINDS:
            rows = data[k][kind]
            body = ",\n".join(f"{json.dumps(a, ensure_ascii=False)}:{json.dumps(b, ensure_ascii=False)}" for a, b in sorted(rows.items()))
            kinds.append(f'"{kind}":{{' + (f"\n{body}\n" if rows else "") + "}")
        parts.append(f'"{k}":{{' + ",\n".join(kinds) + "}")
    return ",\n".join(parts) + "}\n"


def update(today_str, call=None, path=PATH, force=False, want=None, max_calls=MAX_CALLS):
    """集めて保存する → 結果の要約の行。
    集めるのは、前に集めてから7日たった日か、途中まで読んだ一覧（next）がある日だけ（--force なら、いつでも）。
    1回に読むのは max_calls 回まで。読みきれなかった一覧は、次の日に続きから（next）。
    want: このサイトに載っている名前（テスト用。ふだんは wanted()）"""
    call = call or G.call_api
    old = load(path)
    if not force and old["updated"] and not old["next"]:
        try:
            if datetime.strptime(today_str, "%Y-%m-%d") - datetime.strptime(old["updated"], "%Y-%m-%d") < timedelta(days=EVERY_DAYS):
                return [f"- 前に集めてから{EVERY_DAYS}日たっていないので、お休み（前回 {old['updated']}）"]
        except ValueError:
            pass
    want = want if want is not None else wanted()
    new = {"updated": old["updated"], "next": {}}  # 一回り読み終えた日（読み終えたら、きょうにする）
    lines, calls = [], 0
    for k, kinds in LISTS.items():
        new[k] = {}
        for kind in KINDS:
            # メーカーのキー: 動画は名前、同人・ゲームなどは id（作品データの持ち方に合わせる）。シリーズは id、ジャンル・作家は名前
            by_id = kind == "series" or (kind == "maker" and k != "video")
            keys = want[k][kind]
            # 前の読みがなは、いまも載っている名前の分だけ残す
            new[k][kind] = {a: b for a, b in old[k][kind].items() if a in keys}
            if kind not in kinds:
                continue
            slot = f"{k}.{kind}"
            if old["next"] and slot not in old["next"]:
                continue  # 続きの日は、途中の一覧だけ読む
            start = old["next"].get(slot, 1)
            if calls >= max_calls:
                new["next"][slot] = start
                continue
            got, nxt, n = fetch_list(FLOOR_IDS[k], kind, call, max_calls - calls, start)
            calls += n
            for key in keys:
                ruby = got.get(f"#{key}" if by_id else key)
                if ruby:
                    new[k][kind][key] = ruby
            if nxt:
                new["next"][slot] = nxt
            lines.append(f"- {k} {kind}: {len(new[k][kind])}件（一覧 {start}件目から{len(got)}件・{'最後まで' if not nxt else f'{nxt}件目から次の日に'}）")
    if not new["next"]:
        new["updated"] = today_str
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(dump(new))
    os.replace(path + ".tmp", path)
    return lines + [f"- 一覧を{calls}回取得"]


def main():
    parser = argparse.ArgumentParser(description="ジャンル・メーカー・シリーズ・作家の読みがなを集める")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--force", action="store_true", help="7日たっていなくても集める")
    args = parser.parse_args()
    if not args.update:
        parser.print_help()
        return
    if not G.API_ID:
        sys.exit("❌ API_ID が設定されていません")
    today = datetime.now(G.JST).strftime("%Y-%m-%d")
    lines = update(today, force=args.force)
    for line in lines:
        print(line)
    G.write_step_summary(["### 🔤 読みがな（ジャンル・メーカー・シリーズ・作家）", "", *lines])


if __name__ == "__main__":
    main()
