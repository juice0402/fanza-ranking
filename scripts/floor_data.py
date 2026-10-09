#!/usr/bin/env python3
"""FANZA同人・FANZAゲームなどの売り場のデータ（site/src/data/doujin.json・game.json・anime.json など）の読み書き（Python標準ライブラリだけ）。

運営者の希望「FANZA同人・FANZAゲームのページも」（2026-10-09）。集めるのは scripts/doujin_game.py（毎日の更新から）、
コメントを書き込むのは scripts/claude_comments.py。どちらもこのファイルの読み書きを使う（書き方がそろって、余計な差分が出ないように）。

ファイルの形（1作品1行・品番の順。毎日書きかわる順位は ranks に分けて、作品の行が毎日変わらないように）:
  {"updated": 集めた日, "scanned": 人気順を何本目まで見たか, "skipped": 入れなかった本数（未成年を連想させる作品）,
   "ranks": {cid: その日の人気順の順位},
   "items": [{cid, title, url, image_url, sample_images, sample_movie, trial_url, date, maker, maker_id, authors, actress, series, series_id,
              genres, formats, sales, price, list_price, campaign, review, comment, comment_kind, updated}, …]}
  ・genres: 中身のジャンル / formats: 形式・配信の区分（男性向け・Windows11対応作品 など） / sales: セール・クーポンの対象を表す札（ゲーム）
  ・price・list_price: 円（分からなければ null）。campaign: {"title": "30%OFF", "begin": "2026-10-01"}（同人。無ければ null）
  ・review: FANZAのレビューの評価 [平均×100, 件数]（無ければ null。2026-10-10 から）
  ・actress: 出演者（VR・成人映画・写真集など。8人まで）・sample_movie: サンプル動画のページ（アニメ・素人・VR など）・trial_url: 立ち読みのページ（ブックス）。
    無ければ空（2026-10-10 から）
  ・comment_kind: "none"（コメントがまだ無い）か "claude"（Claude が書いた）。updated: 入れた日・コメントを変えた日（sitemap の lastmod）
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "site", "src", "data")

# 運営者が決めた本数（2026-10-09）: 同人 1,000本・ゲーム 500本（どちらも、FANZAの人気順の上から。未成年を連想させる作品は入れない）。
# 新しい売り場（運営者の希望「アニメ動画・素人・成人映画・FANZAブックス（コミック・写真集）・VR見放題も。各100、素人は見たい人が多いので500」。2026-10-10）。
# floor_id: FloorList の id（読みがなの一覧に使う）・author_search: 作家の一覧（AuthorSearch）が使える売り場・upcoming: 予約の人気順も入れる本数・
# max_calls: 1日に一覧を取る回数の上限（未成年を連想させる作品が多い売り場は多め。2026-10-10 に本物で確かめた割合: 素人 58%・コミック 65%・アニメ 54%）
FLOORS = {
    "doujin": {
        "label": "FANZA同人", "service": "doujin", "floor": "digital_doujin", "floor_id": 81, "target": 1000, "max_calls": 40, "upcoming": 0,
        "env": "DOUJIN_PATH", "file": "doujin.json", "samples": 6,
    },
    "game": {
        "label": "FANZAゲーム", "service": "pcgame", "floor": "digital_pcgame", "floor_id": 80, "author_search": True, "target": 500, "max_calls": 40, "upcoming": 30,
        "env": "GAME_PATH", "file": "game.json", "samples": 8,
    },
    "anime": {
        "label": "FANZAアニメ", "service": "digital", "floor": "anime", "floor_id": 46, "target": 100, "max_calls": 8, "upcoming": 12,
        "env": "ANIME_PATH", "file": "anime.json", "samples": 8,
    },
    "amateur": {
        "label": "FANZA素人", "service": "digital", "floor": "videoc", "floor_id": 44, "target": 500, "max_calls": 25, "upcoming": 0,
        "env": "AMATEUR_PATH", "file": "amateur.json", "samples": 8,
    },
    "cinema": {
        "label": "FANZA成人映画", "service": "digital", "floor": "nikkatsu", "floor_id": 45, "target": 100, "max_calls": 6, "upcoming": 0,
        "env": "CINEMA_PATH", "file": "cinema.json", "samples": 8,
    },
    "comic": {
        "label": "FANZAコミック", "service": "ebook", "floor": "comic", "floor_id": 82, "author_search": True, "target": 100, "max_calls": 10, "upcoming": 0,
        "env": "COMIC_PATH", "file": "comic.json", "samples": 0,
    },
    "photo": {
        "label": "FANZA写真集", "service": "ebook", "floor": "photo", "floor_id": 84, "author_search": True, "target": 100, "max_calls": 6, "upcoming": 0,
        "env": "PHOTO_PATH", "file": "photo.json", "samples": 0,
    },
    "vr": {
        "label": "FANZA VR見放題", "service": "monthly", "floor": "vr", "floor_id": 91, "target": 100, "max_calls": 6, "upcoming": 0,
        "env": "VR_PATH", "file": "vr.json", "samples": 8,
    },
}

DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CID = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")
KINDS = ("none", "claude")
FANZA_URL = re.compile(r"^https://([a-z0-9-]+\.)*(dmm\.co\.jp|fanza\.co\.jp)/[^\s\\]*$")


def floor_path(key):
    conf = FLOORS[key]
    return os.environ.get(conf["env"], os.path.join(DATA_DIR, conf["file"]))


def _int_or_none(v, low=0, high=10_000_000):
    return v if isinstance(v, int) and not isinstance(v, bool) and low <= v <= high else None


def _names(values, limit):
    out = []
    for v in values if isinstance(values, list) else []:
        text = " ".join(str(v or "").split())[:60]
        if text and text not in out:
            out.append(text)
    return out[:limit]


def _url(v):
    """FANZA(DMM) の https のURLだけ（ちがえば ""）"""
    text = str(v or "").strip()
    return text if FANZA_URL.match(text) else ""


def _review(v):
    """FANZAのレビューの評価 [平均×100, 件数]（無い・形が違えば None。get_new_releases.py の parse_review と同じ形）"""
    return v if isinstance(v, list) and len(v) == 2 and all(isinstance(n, int) and not isinstance(n, bool) for n in v) and 100 <= v[0] <= 500 and v[1] >= 1 else None


def clean_item(row):
    """保存されている1作品を、決まった項目だけの形にそろえる（読めなければ None）"""
    if not isinstance(row, dict):
        return None
    cid = str(row.get("cid") or "")
    title = " ".join(str(row.get("title") or "").split())[:200]
    date = str(row.get("date") or "")
    if not CID.match(cid) or not title or not DAY.match(date[:10]):
        return None
    camp = row.get("campaign")
    campaign = None
    if isinstance(camp, dict) and str(camp.get("title") or "").strip():
        campaign = {"title": str(camp["title"]).strip()[:40], "begin": str(camp.get("begin") or "")[:10] if DAY.match(str(camp.get("begin") or "")[:10]) else ""}
    kind = row.get("comment_kind") if row.get("comment_kind") in KINDS else "none"
    comment = str(row.get("comment") or "").strip() if kind == "claude" else ""
    if not comment:
        kind = "none"
    return {
        "cid": cid,
        "title": title,
        "url": str(row.get("url") or ""),
        "image_url": str(row.get("image_url") or ""),
        "sample_images": [str(u) for u in (row.get("sample_images") or []) if isinstance(u, str) and u][:12],
        "sample_movie": _url(row.get("sample_movie")),
        "trial_url": _url(row.get("trial_url")),
        "date": date[:19],
        "maker": " ".join(str(row.get("maker") or "").split())[:80],
        "maker_id": _int_or_none(row.get("maker_id"), 1) or 0,
        "authors": _names(row.get("authors"), 4),
        "actress": _names(row.get("actress"), 8),
        "series": " ".join(str(row.get("series") or "").split())[:80],
        "series_id": _int_or_none(row.get("series_id"), 1) or 0,
        "genres": _names(row.get("genres"), 30),
        "formats": _names(row.get("formats"), 12),
        "sales": _names(row.get("sales"), 8),
        "price": _int_or_none(row.get("price"), 1),
        "list_price": _int_or_none(row.get("list_price"), 1),
        "campaign": campaign,
        "review": _review(row.get("review")),
        "comment": comment,
        "comment_kind": kind,
        "updated": str(row.get("updated") or "") if DAY.match(str(row.get("updated") or "")) else date[:10],
    }


def load_floor(path):
    """ファイルを読む → {"updated", "scanned", "skipped", "ranks", "items": {cid: 作品}}。無ければ None。壊れていれば ValueError"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"{os.path.basename(path)} を読めませんでした（{e}）") from e
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise ValueError(f"{os.path.basename(path)} の形が違います")
    items = {}
    for row in raw["items"]:
        item = clean_item(row)
        if item:
            items.setdefault(item["cid"], item)
    ranks = {}
    for cid, r in (raw.get("ranks") or {}).items() if isinstance(raw.get("ranks"), dict) else []:
        if cid in items and _int_or_none(r, 1, 50000):
            ranks[cid] = r
    return {
        "updated": str(raw.get("updated") or "") if DAY.match(str(raw.get("updated") or "")) else "",
        "scanned": _int_or_none(raw.get("scanned")) or 0,
        "skipped": _int_or_none(raw.get("skipped")) or 0,
        "ranks": ranks,
        "items": items,
    }


def dump_floor(data):
    """書き出す文字（1作品1行・品番の順。順位も品番の順に1行ずつ）"""
    items = [data["items"][c] for c in sorted(data["items"])]
    ranks = {c: data["ranks"][c] for c in sorted(data["ranks"]) if c in data["items"]}
    rank_lines = ",\n".join(f"{json.dumps(c)}:{r}" for c, r in ranks.items())
    item_lines = ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in items)
    return (f'{{"updated":{json.dumps(data.get("updated", ""))},"scanned":{int(data.get("scanned") or 0)},"skipped":{int(data.get("skipped") or 0)},\n'
            f'"ranks":{{\n{rank_lines}\n}},\n"items":[\n{item_lines}\n]}}\n')


def save_floor(path, data):
    """書き込み途中で止まっても壊れないよう、別のファイルに書いてから置き換える"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(dump_floor(data))
    os.replace(path + ".tmp", path)
