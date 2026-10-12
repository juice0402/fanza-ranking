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

素人の「女の子のタイプ」ごとの「FANZA素人で人気の○○ TOP20」も、同じしくみで集める（運営者の希望「公式サイトの『女の子のタイプから探す』のように」。2026-10-12）:
・タイプ（floor_data.py の GIRL_TYPES。人妻・主婦・巨乳 など）の id を、素人のジャンルの一覧（GenreSearch・floor_id=44）から引き、素人（service=digital・floor=videoc）で同じように20本
・ファイル: site/src/data/floor_genre_tops.json
  {"updated": 集めた日, "amateur": {タイプ: {"id", "date", "items": [{c, t, d, m, i, u}, …]}}}（c 作品ID / t タイトル（女の子の名前）/ d 発売日 / m メーカー / i 画像 / u FANZAのリンク）。1作品1行
・どちらか片方が失敗しても、もう片方は集める
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
import doujin_game as D  # noqa: E402
import floor_data as F  # noqa: E402

PATH = os.environ.get("GENRE_TOPS_PATH", os.path.join(ROOT, "site", "src", "data", "genre_tops.json"))
FLOOR_PATH = os.environ.get("FLOOR_GENRE_TOPS_PATH", os.path.join(ROOT, "site", "src", "data", "floor_genre_tops.json"))
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


def genre_ids(call, floor_id=VIDEO_FLOOR_ID):
    """ジャンルの一覧（動画は floor_id=43・素人は 44）→ {名前: id}（読めなければ RuntimeError）"""
    out, off = {}, 1
    for _ in range(5):
        res = call("GenreSearch", {"floor_id": floor_id, "hits": 500, "offset": off})
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


# ---- 素人の「女の子のタイプ」ごとの人気TOP20（2026-10-12） ----

def girl_type_names():
    """女の子のタイプのジャンルの名前（floor_data.py の GIRL_TYPES の順）"""
    return [g for _, names in F.GIRL_TYPES for g in names]


def fetch_floor_top(call, key, gid, now):
    """売り場（素人）のそのジャンルの、発売済みの作品を人気順に → 保存する形の作品（TOP 本まで。表紙とFANZAのリンクのある作品だけ）"""
    conf = F.FLOORS[key]
    items = call("ItemList", {"site": "FANZA", "service": conf["service"], "floor": conf["floor"], "article": "genre", "article_id": gid,
                              "sort": "rank", "hits": FETCH, "offset": 1,
                              "lte_date": G.iso(now.replace(hour=23, minute=59, second=59))}).get("items") or []
    out, seen = [], set()
    for raw in items:
        if not isinstance(raw, dict) or D.blocked_reason(raw):
            continue
        p = D.parse_floor_item(raw, key)
        if not p or p["cid"] in seen or not p["url"] or not p["image_url"]:
            continue
        seen.add(p["cid"])
        out.append({"c": p["cid"], "t": p["title"], "d": p["date"][:10], "m": p["maker"], "i": p["image_url"], "u": p["url"]})
        if len(out) >= TOP:
            break
    return out


def load_floor_tops(path=FLOOR_PATH):
    """前の売り場のデータ（無ければ・壊れていれば空）→ {"updated", 売り場: {タイプ: {id, date, items}}}"""
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    out = {"updated": str(raw.get("updated") or "") if isinstance(raw, dict) else ""}
    for key in F.GIRL_TYPE_FLOORS:
        part = raw.get(key) if isinstance(raw, dict) and isinstance(raw.get(key), dict) else {}
        out[key] = {}
        for name, g in part.items():
            if isinstance(g, dict) and isinstance(g.get("items"), list) and isinstance(g.get("id"), int) and re.match(r"^\d{4}-\d{2}-\d{2}$", str(g.get("date") or "")):
                out[key][name] = {"id": g["id"], "date": g["date"], "items": [r for r in g["items"] if isinstance(r, dict) and r.get("c")][:TOP]}
    return out


def dump_floor_tops(data):
    """1作品1行（売り場・タイプは名前の順）"""
    floors = []
    for key in F.GIRL_TYPE_FLOORS:
        parts = []
        for name in sorted(data.get(key) or {}):
            g = data[key][name]
            rows = ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in g["items"])
            parts.append(f'{json.dumps(name, ensure_ascii=False)}:{{"id":{g["id"]},"date":{json.dumps(g["date"])},"items":[\n{rows}\n]}}')
        floors.append(f'{json.dumps(key)}:{{\n' + ",\n".join(parts) + "\n}")
    return f'{{"updated":{json.dumps(data["updated"])},\n' + ",\n".join(floors) + "}\n"


def update_floor_types(now, call=None, path=FLOOR_PATH):
    """素人の女の子のタイプごとの人気TOP20を集めて保存する → 結果の要約の行"""
    call = call or G.call_api
    today_str = now.strftime("%Y-%m-%d")
    old = load_floor_tops(path)
    new = {"updated": today_str}
    lines = []
    for key in F.GIRL_TYPE_FLOORS:
        try:
            ids = genre_ids(call, F.FLOORS[key]["floor_id"])
        except RuntimeError as e:
            ids = {n: g["id"] for n, g in old[key].items()}
            print(f"  ⚠️ {F.FLOORS[key]['label']}のジャンルの一覧を読めませんでした（前の id を使います）: {e}")
        new[key], fails = {}, 0
        for name in girl_type_names():
            gid, prev, got = ids.get(name), old[key].get(name), None
            if gid and fails < 3:
                try:
                    got = fetch_floor_top(call, key, gid, now)
                    fails = 0
                except RuntimeError as e:
                    fails += 1
                    print(f"  ⚠️ {F.FLOORS[key]['label']}の{name} を読めませんでした: {e}")
                time.sleep(G.DMM_INTERVAL_SEC)
            if got:
                new[key][name] = {"id": gid, "date": today_str, "items": got}
                lines.append(f"- {F.FLOORS[key]['label']}の{name}: {len(got)}本")
            elif prev and 0 <= (G.days_between(prev["date"], today_str) or 0) <= KEEP_DAYS:
                new[key][name] = prev
                lines.append(f"- {F.FLOORS[key]['label']}の{name}: 取れなかったので前のまま（{prev['date']}）")
            else:
                lines.append(f"- {F.FLOORS[key]['label']}の{name}: なし")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(dump_floor_tops(new))
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
    now = datetime.now(G.JST)
    lines, failed = [], False
    # 動画のジャンルと、素人の女の子のタイプ。片方が失敗しても、もう片方は集める
    for label, run in (("動画のジャンル", lambda: update(now)), ("素人の女の子のタイプ", lambda: update_floor_types(now))):
        try:
            lines += run()
        except Exception as e:  # noqa: BLE001
            failed = True
            lines.append(f"- {label}: 集められませんでした（{type(e).__name__}: {str(e)[:120]}）")
    for line in lines:
        print(line)
    G.write_step_summary(["### 🏷 ジャンルの「FANZA全体で人気の作品」・素人の女の子のタイプ", "", *lines])
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
