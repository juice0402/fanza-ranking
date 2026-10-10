#!/usr/bin/env python3
"""FANZA同人・FANZAゲーム（PCゲーム・DL版）などの売り場の人気作品を、毎日集め直す道具（Python標準ライブラリだけ。Gemini は使わない）。

運営者の希望「『FANZA セール』で上に来る、同人・ゲームのセール情報のページも作りたい」→「同人 1,000本・ゲーム 500本」（2026-10-09）。
運営者の希望「アニメ動画・素人・成人映画・FANZAブックス（コミック・写真集）・VR見放題も。各100、素人は500」（2026-10-10）。売り場は scripts/floor_data.py の FLOORS。

  python3 scripts/doujin_game.py --update [--only doujin|game|anime|amateur|cinema|comic|photo|vr]

・FANZA(DMM) アフィリエイトAPI の ItemList（site=FANZA、同人は service=doujin・floor=digital_doujin、
  ゲームは service=pcgame・floor=digital_pcgame）を、人気順（sort=rank・発売済み）に100本ずつ上から読み、
  決めた本数（scripts/floor_data.py の FLOORS の target）がそろうまで集める（1日 max_calls 回まで）。ゲームは予約の人気順も少し（upcoming 本）
・未成年を連想させる作品は入れない（タイトル・ジャンル・シリーズ・サークル/ブランド・メーカー・レーベル・出版社・作家・出演者・監督の名前のどれかに、
  claude_comments.py の title_block_reason が "minor" と見る言葉があるもの）。同人の約半分・ゲームの約7割が当たる（2026-10-09 に本物のAPIで確認）
・前の日にあって今日の上位に無い作品は外す（Claude がコメントを書いた作品は残す）。途中で取れなくなった日は、前の作品を外さない
・ファイルの形は scripts/floor_data.py。失敗しても、ほかの毎日の更新は止めない（ワークフローは continue-on-error）
・集めたあと、人気の動き（毎日の順位）とセールの記録を足していく（scripts/floor_history.py。2026-10-09 から）
"""
import argparse
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
import floor_data as F  # noqa: E402
import floor_history as H  # noqa: E402

PAGE = 100  # 1回の本数（APIの上限）
SHRINK_GUARD = 0.5  # 今日そろった本数が、前の日の半分より少なければ、念のため前の作品を外さない（APIの答えがおかしいとき）

# ジャンルの札の分け方（中身のジャンル・形式・セールの札）
SALE_TAG = re.compile(r"セール|OFF|ＯＦＦ|クーポン|キャンペーン|還元|対象|特価|半額|割引|ポイント")
FORMAT_TAG = re.compile(r"^(男性向け|女性向け|成人向け|専売|単話|単行本|新作|準新作|旧作|日本語作品|英語作品|中国語作品|韓国語作品|翻訳作品|"
                        r"ハイビジョン|4K|8KVR|VR専用|ハイクオリティVR|単体作品|4時間以上作品|複数話|ベスト・総集編|サンプル動画|配信専用|期間限定配信|"
                        r"デジタルモザイク|カラー|モノクロ|オールカラー|分冊版|フルカラー版)$|"
                        r"^コミケ|^コミティア|^C\d|即売会|イベント|Windows|Mac|Android|iOS|対応|体験版|独占|セット|DL版|ダウンロード|パッケージ版")
EVAL_TAG = re.compile(r"がいい$|に定評|おすすめ|オススメ|人気|ランキング")  # 「CGがいい」「エロに定評」のような評価の札は持たない


def blocked_reason(raw):
    """入れない理由（"" なら入れる）。タイトル・ジャンル・シリーズ・サークル/ブランド/メーカー・レーベル・出版社・作家・出演者・監督の名前を、
    未成年を連想させる言葉で調べる"""
    info = raw.get("iteminfo") or {}
    texts = [("タイトル", raw.get("title"))]
    for key, label in (("genre", "ジャンル"), ("series", "シリーズ"), ("maker", "サークル・ブランド"), ("label", "レーベル"), ("manufacture", "出版社"),
                       ("author", "作家"), ("actress", "出演者"), ("director", "監督")):
        for e in info.get(key) or []:
            if isinstance(e, dict):
                texts.append((label, e.get("name")))
    for label, text in texts:
        if text and title_block_reason({"title": str(text)}) == "minor":
            return label
    return ""


def split_genres(names):
    """ジャンルの札 → (中身のジャンル, 形式, セールの札)。評価の札は捨てる"""
    genres, formats, sales = [], [], []
    for n in names:
        n = " ".join(str(n or "").split())[:60]
        if not n or EVAL_TAG.search(n):
            continue
        if SALE_TAG.search(n):
            sales.append(n)
        elif FORMAT_TAG.search(n):
            formats.append(n)
        else:
            genres.append(n)
    return genres, formats, sales


# 同人の画像は、APIが doujin-assets.dmm.co.jp の URL を返すが、運営者のiPhoneでは、ほかのサイトの中で表示されなかった（画像を直接開くと出る。2026-10-09）。
# 同じ場所の pics.dmm.co.jp（動画・ゲームの画像と同じ置き場所。表示できている）に、まったく同じ画像がある（表紙8枚・サンプル3枚で、中身が1バイトも違わないことを確かめた）ので、そちらを使う
DOUJIN_ASSETS = "https://doujin-assets.dmm.co.jp/"
PICS = "https://pics.dmm.co.jp/"


def pics_url(url):
    """同人の画像の URL を、pics.dmm.co.jp の同じ場所にする（ほかの URL はそのまま）"""
    return PICS + url[len(DOUJIN_ASSETS):] if isinstance(url, str) and url.startswith(DOUJIN_ASSETS) else url


def sample_images(raw, limit):
    """サンプル画像。大きい版（sample_l）を先に。ゲームは小さい版（…js-N.jpg・120×90）しか返らないので、
    同じ場所の大きい版（…jp-N.jpg・640×360。2026-10-09 に本物で確かめた）にする"""
    smp = raw.get("sampleImageURL") or {}
    big = (smp.get("sample_l") or {}).get("image") or []
    if not big:
        big = [re.sub(r"js-(\d+)\.jpg$", r"jp-\1.jpg", u) for u in ((smp.get("sample_s") or {}).get("image") or []) if isinstance(u, str)]
    return [u for u in (G.safe_https_url(pics_url(x), G.IMAGE_HOSTS) for x in big) if u][:limit]


def parse_floor_item(raw, key):
    """APIの1件 → 保存する形（読めなければ None）。入れてよいかは blocked_reason で先に調べる"""
    info = raw.get("iteminfo") or {}
    cid = str(raw.get("content_id") or raw.get("product_id") or "")
    title = " ".join(str(raw.get("title") or "").split())
    date = str(raw.get("date") or "")
    url = G.safe_https_url(raw.get("affiliateURL"), G.LIST_HOSTS)
    if not F.CID.match(cid) or not title or not F.DAY.match(date[:10]) or not url:
        return None
    images = raw.get("imageURL") or {}
    # メーカー（同人はサークル・ゲームはブランド）。ブックスは出版社（manufacture）
    maker_id, maker = G.first_entry(info.get("maker"))
    if not maker:
        maker_id, maker = G.first_entry(info.get("manufacture"))
    series_id, series = G.first_entry(info.get("series"))
    genres, formats, sales = split_genres([g.get("name") for g in info.get("genre") or [] if isinstance(g, dict)])
    prices = raw.get("prices") if isinstance(raw.get("prices"), dict) else {}
    price, list_price = G.parse_yen(prices.get("price")), G.parse_yen(prices.get("list_price"))
    if price is not None and list_price is not None and not 0 < price <= list_price:
        list_price = None  # 定価より高い・0円のような、おかしな組み合わせは、定価を使わない
    campaign = None
    for c in raw.get("campaign") or []:
        if isinstance(c, dict) and str(c.get("title") or "").strip():
            campaign = {"title": str(c["title"]).strip()[:40], "begin": str(c.get("date_begin") or "")[:10]}
            break
    return F.clean_item({
        "cid": cid,
        "title": title,
        "url": url,
        # 表紙: 大きい版。無ければ（素人・成人映画の一部）、小さい版（素人は 1200×1200 の四角）、一覧の版
        "image_url": G.safe_https_url(pics_url(images.get("large") or images.get("small") or images.get("list") or ""), G.IMAGE_HOSTS),
        "sample_images": sample_images(raw, F.FLOORS[key]["samples"]),
        "sample_movie": G.pick_sample_movie(raw),
        "trial_url": G.safe_https_url((raw.get("tachiyomi") or {}).get("affiliateURL") if isinstance(raw.get("tachiyomi"), dict) else "", G.LIST_HOSTS),
        "date": date[:19],
        "maker": maker,
        "maker_id": maker_id,
        "authors": [a.get("name") for a in info.get("author") or [] if isinstance(a, dict)],
        "actress": [a.get("name") for a in info.get("actress") or [] if isinstance(a, dict) and a.get("name") not in (None, "", "----")],
        "series": series,
        "series_id": series_id,
        "genres": genres,
        "formats": formats,
        "sales": sales,
        "price": price,
        "list_price": list_price,
        "campaign": campaign,
        "review": G.parse_review(raw),
        "comment": "",
        "comment_kind": "none",
        "updated": "",
    })


def scan(key, today, call=None):
    """人気順を上から読んで、入れてよい作品を target 本まで集める。
    → (作品のリスト（順位 rank 付き。予約は rank None）, {"calls", "scanned", "skipped", "complete", "fails"})"""
    conf = F.FLOORS[key]
    call = call or G.call_api
    today_str = today.strftime("%Y-%m-%d")
    lte = G.iso(today.replace(hour=23, minute=59, second=59))
    base = {"site": "FANZA", "service": conf["service"], "floor": conf["floor"], "sort": "rank", "hits": PAGE}
    picked, seen = [], set()
    stats = {"calls": 0, "scanned": 0, "skipped": 0, "complete": False, "fails": 0}
    off, fails, ended = 1, 0, False
    while len(picked) < conf["target"] and stats["calls"] < conf["max_calls"] and fails < G.MAX_API_FAILS_IN_ROW:
        stats["calls"] += 1
        try:
            rows = call("ItemList", dict(base, offset=off, lte_date=lte)).get("items") or []
            fails = 0
        except RuntimeError as e:
            fails += 1
            print(f"  ⚠️ {conf['label']}の人気順（{off}本目から）を取れませんでした: {e}")
            continue
        time.sleep(G.DMM_INTERVAL_SEC)
        for pos, raw in enumerate(rows):
            stats["scanned"] = off + pos
            if not isinstance(raw, dict) or len(picked) >= conf["target"]:
                continue
            if blocked_reason(raw):
                stats["skipped"] += 1
                continue
            item = parse_floor_item(raw, key)
            if item and item["cid"] not in seen and item["date"][:10] <= today_str:
                seen.add(item["cid"])
                item["rank"] = off + pos
                picked.append(item)
        if len(rows) < PAGE:
            ended = True
            break
        off += PAGE
    stats["fails"] = fails
    stats["complete"] = fails < G.MAX_API_FAILS_IN_ROW and (len(picked) >= conf["target"] or ended or stats["calls"] >= conf["max_calls"])
    # 予約（ゲーム）: 予約の人気順の上から upcoming 本。入れてよいものだけ
    if conf["upcoming"] > 0 and fails < G.MAX_API_FAILS_IN_ROW:
        stats["calls"] += 1
        try:
            tomorrow = G.iso((today + timedelta(days=1)).replace(hour=0, minute=0, second=0))
            rows = call("ItemList", dict(base, hits=conf["upcoming"], offset=1, gte_date=tomorrow)).get("items") or []
            for raw in rows:
                if not isinstance(raw, dict) or blocked_reason(raw):
                    continue
                item = parse_floor_item(raw, key)
                if item and item["cid"] not in seen and item["date"][:10] > today_str:
                    seen.add(item["cid"])
                    item["rank"] = None
                    picked.append(item)
            time.sleep(G.DMM_INTERVAL_SEC)
        except RuntimeError as e:
            print(f"  ⚠️ {conf['label']}の予約を取れませんでした: {e}")
    return picked, stats


def merge(old, picked, stats, today_str):
    """前のデータ（無ければ None）と、今日集めた作品 → 新しいデータ。
    ・前からある作品は、コメントと updated を引き継ぎ、ほかの項目は今日の内容にする
    ・新しい作品は comment_kind "none"・updated は今日
    ・今日の上位に無い前の作品は外す。ただし Claude がコメントを書いた作品は残す（順位は無し）
    ・最後まで読めなかった日・そろった本数が前の半分より少ない日は、前の作品を外さない（順位も前のまま）"""
    old = old or {"items": {}, "ranks": {}}
    items, ranks = {}, {}
    for fresh in picked:
        rank = fresh.pop("rank", None)
        prev = old["items"].get(fresh["cid"])
        if prev:
            fresh["comment"], fresh["comment_kind"], fresh["updated"] = prev["comment"], prev["comment_kind"], prev["updated"]
        else:
            fresh["updated"] = today_str
        items[fresh["cid"]] = fresh
        if rank:
            ranks[fresh["cid"]] = rank
    released_now = sum(1 for c in items if c in ranks)
    released_old = len(old.get("ranks") or {})
    trust = stats["complete"] and not (released_old >= 100 and released_now < released_old * SHRINK_GUARD)
    kept = removed = 0
    for cid, prev in old["items"].items():
        if cid in items:
            continue
        if not trust:
            items[cid] = prev
            if cid in old["ranks"]:
                ranks[cid] = old["ranks"][cid]
            kept += 1
        elif prev["comment_kind"] == "claude" and title_block_reason(prev) != "minor" \
                and not any(title_block_reason({"title": t}) == "minor" for t in [*prev["genres"], prev["series"], prev["maker"], *prev["authors"]] if t):
            items[cid] = prev  # コメントのある作品は、上位から外れても残す（作品ページとコメントがあるので）
            kept += 1
        else:
            removed += 1
    data = {"updated": today_str, "scanned": stats["scanned"], "skipped": stats["skipped"], "ranks": ranks, "items": items}
    return data, {"trusted": trust, "kept": kept, "removed": removed, "added": sum(1 for c in items if c not in old["items"])}


def update_floor(key, today, call=None):
    """1つの売り場を集め直して保存する。結果の要約の1行を返す（読めない・取れないときは、ファイルを変えない）"""
    conf = F.FLOORS[key]
    path = F.floor_path(key)
    today_str = today.strftime("%Y-%m-%d")
    try:
        old = F.load_floor(path)
    except ValueError as e:
        print(f"::warning title={conf['label']}のデータを読めませんでした::{e}。上書きを防ぐため、今回は集めません")
        return f"- {conf['label']}: データを読めなかったので、集めませんでした（ファイルは変更していません）"
    picked, stats = scan(key, today, call)
    if not picked:
        print(f"::warning title={conf['label']}を集められませんでした::1本も取れませんでした（前のデータのまま）")
        return f"- {conf['label']}: 取れなかったので、前のデータのまま"
    data, result = merge(old, picked, stats, today_str)
    F.save_floor(path, data)
    line = (f"- {conf['label']}: {len(data['items'])}本（人気順の上位{stats['scanned']}本目までを見て、未成年を連想させる{stats['skipped']}本は入れない・"
            f"新しく{result['added']}本・外した{result['removed']}本・コメントがあって残した{result['kept'] if result['trusted'] else 0}本。一覧を{stats['calls']}回取得）")
    if not result["trusted"]:
        line += "（最後まで読めなかった・本数が少なすぎたので、前の作品は外していません）"
        print(f"::warning title={conf['label']}を最後まで集められませんでした::前の作品は外していません")
    # 人気の動き・セールの記録（2026-10-09 から。失敗しても、集めたデータはそのまま）
    try:
        line += "。" + H.record(key, data, today_str, result["trusted"])
    except Exception as e:  # noqa: BLE001
        print(f"::warning title={conf['label']}の人気の動き・セールを記録できませんでした::{type(e).__name__}: {e}")
    print(line)
    return line


def main():
    parser = argparse.ArgumentParser(description="FANZA同人・FANZAゲームなどの売り場の人気作品を集め直す")
    parser.add_argument("--update", action="store_true", help="集め直して保存する")
    parser.add_argument("--only", choices=sorted(F.FLOORS), help="1つの売り場だけ")
    args = parser.parse_args()
    if not args.update:
        parser.print_help()
        return
    if not G.API_ID:
        sys.exit("❌ API_ID が設定されていません")
    today = datetime.now(G.JST).replace(hour=0, minute=0, second=0, microsecond=0)
    lines = ["### 🎮 FANZA同人・FANZAゲームなどの売り場", ""]
    for key in ([args.only] if args.only else list(F.FLOORS)):
        lines.append(G.run_stage(f"{F.FLOORS[key]['label']}の取得", lambda k=key: update_floor(k, today)) or f"- {F.FLOORS[key]['label']}: 取得に失敗（前のデータのまま）")
    G.write_step_summary(lines)


if __name__ == "__main__":
    main()
