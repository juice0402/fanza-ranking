#!/usr/bin/env python3
"""売り場のセール（キャンペーン）ごとの本数と、このサイトに無い対象作品を集める道具（Python標準ライブラリだけ。Gemini は使わない）。

運営者の「素人のセールもセールとしてまとめられてるけど、○○セールとか、動画みたいに色んなセールが何種類かあると思う」（2026-10-12）。
動画の「特集ごとのページ」（get_new_releases.py の refresh_sales・sale.json の extra）と同じ考え方を、名前のあるキャンペーンが付く売り場
（FANZA素人・FANZAアニメ・FANZA成人映画。scripts/floor_data.py の FLOORS の campaign_calls）にも。

  python3 scripts/floor_sales.py --update [--only amateur|anime|cinema]

・人気順（発売済み）を上から読み（素人は5万本＝APIの上限まで。アニメ・成人映画は全部で約4千・約6千本）、いま期間中のキャンペーン
  （名前・始まり・終わり。get_new_releases.py の sale_of と同じ見分け方で、時刻まで見る）ごとに、対象の本数を数える
  （2026-10-12 に本物で確かめた: 素人は「素人ホイホイZ他30％OFF」1,404本・アニメは「○○他50％OFF」3件。人気の上位1,000本に入るのは一部だけ＝probe_api.py の 18）
・このサイトの売り場のデータ（amateur.json など）に無い作品も、キャンペーンごとに人気の高い順に EXTRA_PER_CAMPAIGN 本まで保存する
  （キャンペーンのページに並べる。作品ページは無いので、FANZAへ直接）。未成年を連想させる作品は入れない（doujin_game.py の blocked_reason）
・数えた本数は、セールの記録（floor_sale_history.json の tags）にも足す（「セールはいつ？」の対象の本数）
・最後まで読めなかった売り場は、前のデータのうち、まだ期間中のキャンペーンだけ残す（本数・作品）
・ファイルは site/src/data/floor_sale.json（1作品1行）:
  {"checked": "YYYY-MM-DD HH:MM",
   "<売り場>": {"date": 読んだ日, "scanned": 読んだ本数,
               "campaigns": [{"title", "begin": "YYYY-MM-DD HH:MM", "end": "YYYY-MM-DD HH:MM", "n": 対象の本数}],
               "extra": [{cid, title, url, image_url, date, maker, maker_id, actress, genres, price, list_price, campaign: {title, begin}, rank}]}}
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import get_new_releases as G  # noqa: E402
import doujin_game as D  # noqa: E402
import floor_data as F  # noqa: E402
import floor_history as H  # noqa: E402

PAGE = 100  # 1回の本数（APIの上限）
EXTRA_PER_CAMPAIGN = 60  # このサイトに無い作品を、キャンペーンごとにこの本数まで（キャンペーンのページに並べる本数＝lib/floors.js の FLOOR_SALE_PAGE_LIST）
TITLE_MAX = 40  # キャンペーンの名前の長さ（売り場のデータの campaign と同じ。scripts/doujin_game.py の parse_floor_item）
ROW_KEYS = ("cid", "title", "url", "image_url", "date", "maker", "maker_id", "actress", "genres")
PATH = os.environ.get("FLOOR_SALE_PATH", os.path.join(F.DATA_DIR, "floor_sale.json"))
KEYS = [k for k, conf in F.FLOORS.items() if conf.get("campaign_calls")]


def scan(key, now, site, call=None):
    """人気順を上から campaign_calls×100本まで読んで、キャンペーンごとの本数と、このサイトに無い作品を集める。
    → ({"campaigns": [...], "extra": [...], "scanned"}, 最後まで読めたか, 一覧を取った回数)"""
    conf = F.FLOORS[key]
    call = call or G.call_api
    today_str, now_str = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M")
    base = {"site": "FANZA", "service": conf["service"], "floor": conf["floor"], "sort": "rank", "hits": PAGE,
            "lte_date": G.iso(now.replace(hour=23, minute=59, second=59, microsecond=0))}
    camps, counts, extra = {}, {}, {}
    seen, calls, fails, off, scanned = set(), 0, 0, 1, 0
    while calls < conf["campaign_calls"] and off <= G.CATALOG_MAX_OFFSET:
        if fails >= G.MAX_API_FAILS_IN_ROW:
            break
        calls += 1
        try:
            got = call("ItemList", dict(base, offset=off))
            fails = 0
        except RuntimeError as e:
            fails += 1
            print(f"  ⚠️ {conf['label']}の人気順（{off}本目から）を取れませんでした: {e}")
            continue
        time.sleep(G.DMM_INTERVAL_SEC)
        rows = got.get("items") or []
        for pos, raw in enumerate(rows):
            if not isinstance(raw, dict):
                continue
            cid = str(raw.get("content_id") or raw.get("product_id") or "")
            if not F.CID.match(cid) or cid in seen:
                continue
            seen.add(cid)
            scanned += 1
            sale = G.sale_of(raw, today_str, now_str)
            if not sale:
                continue
            camp, price, list_price = sale
            camp = dict(camp, title=camp["title"][:TITLE_MAX])
            ck = G.camp_key(camp)
            camps.setdefault(ck, camp)
            counts[ck] = counts.get(ck, 0) + 1
            if cid in site or len(extra.get(ck, [])) >= EXTRA_PER_CAMPAIGN or D.blocked_reason(raw):
                continue
            item = D.parse_floor_item(raw, key)
            if not item or not item["image_url"] or item["date"][:10] > today_str:
                continue
            row = {k: item[k] for k in ROW_KEYS}
            row["actress"] = row["actress"][:4]
            row["genres"] = row["genres"][:12]
            row.update(price=price, list_price=list_price, campaign={"title": camp["title"], "begin": camp["begin"][:10]}, rank=off + pos)
            extra.setdefault(ck, []).append(row)
        if len(rows) < PAGE:
            break
        off += PAGE
    complete = fails < G.MAX_API_FAILS_IN_ROW
    order = sorted(camps, key=lambda ck: (ck[2], -counts[ck], ck[0]))  # 終わりが近い順・同じなら本数の多い順
    data = {
        "date": today_str,
        "scanned": scanned,
        "campaigns": [dict(camps[ck], n=counts[ck]) for ck in order],
        "extra": sorted((r for ck in order for r in extra.get(ck, [])), key=lambda r: (r["rank"], r["cid"])),
    }
    return data, complete, calls


def still_active(old, now_str):
    """前のデータのうち、まだ期間中のキャンペーンと、その作品だけ（読めなかった日に残す）"""
    camps = [c for c in old.get("campaigns") or [] if G.sale_active(c.get("end"), now_str)]
    titles = {c["title"] for c in camps}
    return dict(old, campaigns=camps, extra=[r for r in old.get("extra") or [] if (r.get("campaign") or {}).get("title") in titles])


def clean_campaign(c):
    if not isinstance(c, dict):
        return None
    title = str(c.get("title") or "").strip()[:TITLE_MAX]
    begin, end, n = str(c.get("begin") or "")[:16], str(c.get("end") or "")[:16], c.get("n")
    if not title or not re.match(r"^\d{4}-\d{2}-\d{2}", end) or not isinstance(n, int) or isinstance(n, bool) or n < 1:
        return None
    return {"title": title, "begin": begin, "end": end, "n": n}


def clean_extra(r):
    if not isinstance(r, dict):
        return None
    item = F.clean_item(r)
    camp = r.get("campaign") if isinstance(r.get("campaign"), dict) else {}
    rank = r.get("rank")
    if not item or not F.FANZA_URL.match(item["url"]) or not F.FANZA_URL.match(item["image_url"]) or not str(camp.get("title") or "").strip() or not isinstance(rank, int) or isinstance(rank, bool) or not 1 <= rank <= 100000:
        return None
    row = {k: item[k] for k in ROW_KEYS}
    row.update(price=item["price"], list_price=item["list_price"], campaign=item["campaign"], rank=rank)
    return row


def load(path=PATH):
    """ファイルを読む → {"checked", 売り場: {date, scanned, campaigns, extra}}。無ければ空。壊れていれば ValueError（上書きしない）"""
    if not os.path.exists(path):
        return {"checked": ""}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(f"{os.path.basename(path)} を読めませんでした（{e}）") from e
    if not isinstance(raw, dict):
        raise ValueError(f"{os.path.basename(path)} の形が違います")
    out = {"checked": str(raw.get("checked") or "")}
    for key in KEYS:
        fl = raw.get(key)
        if not isinstance(fl, dict):
            continue
        out[key] = {
            "date": str(fl.get("date") or ""),
            "scanned": fl.get("scanned") if isinstance(fl.get("scanned"), int) else 0,
            "campaigns": [c for c in (clean_campaign(x) for x in fl.get("campaigns") or []) if c],
            "extra": [r for r in (clean_extra(x) for x in fl.get("extra") or []) if r],
        }
    return out


def dump(data):
    """書き出す文字（キャンペーン・作品を1行ずつ。差分が読みやすいように）"""
    line = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
    parts = []
    for key in KEYS:
        fl = data.get(key)
        if not fl:
            continue
        camps = ",\n".join(line(c) for c in fl["campaigns"])
        extra = ",\n".join(line(r) for r in fl["extra"])
        parts.append(f'"{key}":{{"date":{json.dumps(fl["date"])},"scanned":{int(fl["scanned"])},\n"campaigns":[' + (f"\n{camps}\n" if camps else "")
                     + '],\n"extra":[' + (f"\n{extra}\n" if extra else "") + "]}")
    return "{" + f'"checked":{json.dumps(data.get("checked", ""))}' + "".join(",\n" + p for p in parts) + "}\n"


def site_cids(key):
    """このサイトの売り場のデータにある作品（読めなければ空。そのときは、どの作品も「このサイトに無い」として集める）"""
    try:
        floor = F.load_floor(F.floor_path(key))
    except ValueError:
        return set()
    return set((floor or {}).get("items") or {})


def update(now, keys=None, call=None, path=PATH):
    """集めて保存する → (保存したか, 結果の要約の行)。前のファイルが壊れていたら保存しない"""
    now_str = now.strftime("%Y-%m-%d %H:%M")
    try:
        old = load(path)
    except ValueError as e:
        print(f"::warning title=売り場のセールのデータを読めませんでした::{e}。上書きを防ぐため、今回は集めません")
        return False, [f"- 売り場のセール: データを読めなかったので、集めませんでした（{e}）"]
    new = {"checked": now_str}
    lines = []
    for key in KEYS:
        conf = F.FLOORS[key]
        if keys and key not in keys:
            if old.get(key):
                new[key] = still_active(old[key], now_str)
            continue
        t0 = time.time()
        data, complete, calls = scan(key, now, site_cids(key), call)
        if not complete:
            if old.get(key):
                new[key] = still_active(old[key], now_str)
            print(f"::warning title={conf['label']}のセールを最後まで読めませんでした::前のデータのうち、まだ期間中のキャンペーンだけ残します")
            lines.append(f"- {conf['label']}: 最後まで読めなかったので、前のデータのまま（期間中のキャンペーンだけ）")
            continue
        new[key] = data
        note = ""
        try:
            tags = [{"title": c["title"], "begin": c["begin"][:10], "count": c["n"], "off": H.off_in_title(c["title"])} for c in data["campaigns"]]
            note = "・" + H.record_campaigns(key, now.strftime("%Y-%m-%d"), tags)
        except Exception as e:  # noqa: BLE001
            print(f"::warning title={conf['label']}のセールの名前を記録できませんでした::{type(e).__name__}: {e}")
        names = "・".join(f"{c['title']}（{c['n']}本）" for c in data["campaigns"][:6]) or "なし"
        lines.append(f"- {conf['label']}: 人気順の上位{data['scanned']}本を見て、キャンペーン {len(data['campaigns'])}件（{names}）・"
                     f"このサイトに無い作品 {len(data['extra'])}本（一覧を{calls}回・{int(time.time() - t0)}秒）{note}")
    text = dump(new)
    try:
        with open(path, encoding="utf-8") as f:
            before = f.read()
    except OSError:
        before = ""
    if before and before.split("\n", 1)[-1] == text.split("\n", 1)[-1]:  # 確かめた時刻（1行目）のほかが同じなら、保存しない
        return False, lines + ["- 変わりなし（保存しません）"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(path + ".tmp", path)
    return True, lines + ["- 保存しました"]


def main():
    parser = argparse.ArgumentParser(description="売り場のセール（キャンペーン）ごとの本数と対象作品を集める")
    parser.add_argument("--update", action="store_true", help="集めて保存する")
    parser.add_argument("--only", choices=KEYS, help="1つの売り場だけ")
    args = parser.parse_args()
    if not args.update:
        parser.print_help()
        return
    if not G.API_ID:
        sys.exit("❌ API_ID が設定されていません")
    now = datetime.now(G.JST).replace(second=0, microsecond=0)
    saved, lines = update(now, [args.only] if args.only else None)
    for line in lines:
        print(line)
    G.write_step_summary(["### 🏷️ 売り場のセール（キャンペーンごと）", ""] + lines)


if __name__ == "__main__":
    main()
