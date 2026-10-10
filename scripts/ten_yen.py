#!/usr/bin/env python3
"""FANZAの「10円セール」（動画・同人・ゲーム）の対象作品を集める道具（Python標準ライブラリだけ。Gemini は使わない）。

運営者の希望「動画・同人・ゲームのどれも、10円セールの時は大イベント。開催中はものすごく訴求したいし、SEOもかなり上位に来るように」（2026-10-09）。

  python3 scripts/ten_yen.py --update               毎日の更新から（変わらなくても、確かめた時刻を書く）
  python3 scripts/ten_yen.py --update --if-changed  1日に数回の確認から（10円の作品が変わったときだけ保存する。変わらなければファイルを書かない＝公開もしない）

・10円の作品は、安い順（sort=-price）の一覧から、すべて読む（運営者の希望「10円セールの作品は、期間中だけ、いつもの枠をこえて全部載せたい」。2026-10-10）。
  安い順の先頭には、0円・5円（95%OFF）の作品が何千本も並ぶ（同人は約2,700本。2026-10-10 に本物のAPIで確かめた）ので、
  「価格が10円以上になる位置」を二分探索で見つけ（1本ずつ・17回ほど）、その少し前から100本ずつ、10円以下の作品が出てこなくなるまで読む
  （安い順は、ところどころ順番が前後する（ゲーム）ので、少し前から読み、10円以下が1本も無い100本が出たらやめる）
・同人・ゲームは、人気順（sort=rank・発売済み）も上から読む（同人3,000本・ゲーム1,500本）。人気順の順位（rank）を付けるため。
  人気順の外の10円の作品は、順位なし（ページでは人気順の作品のあと）
・10円の作品＝価格がちょうど10円で、値引きされているもの
  （動画は、定価が10円より高いか分からないもの。同人・ゲームは、定価が300円以上か、キャンペーン・セールの札の名前に「10円」があるもの。
   同人には、ふだんから110円の作品の95%OFF＝5円のような安売りがあるので、それとは分ける）
・未成年を連想させる作品は入れない（doujin_game.blocked_reason。タイトル・ジャンル・シリーズ・サークル/メーカー・作家の名前）
・売り場ごとに、最後まで読めなかったときは、その売り場は前のまま（10円の作品を消さない・開催の記録も足さない）
・終わりの日時は、動画のキャンペーンの「2026-10-12 09:59」の形のときだけ使う（ほかの形は、日本時間かどうかが分からないので使わない）
・開催の記録（runs）: 売り場ごとに、10円の作品を見かけた日が続くあいだを1回とする（このサイトが見かけた日。400日分）

ファイル: site/src/data/ten_yen.json
  {"checked": "YYYY-MM-DD HH:MM"（確かめた日時・日本時間）, "video": [作品], "doujin": [作品], "game": [作品],
   "runs": [{"floor", "first", "last", "count"（いちばん多かった本数）, "end", "titles"}]}
  作品は1行に1本。動画は new_releases.json と同じ項目（の一部）、同人・ゲームは doujin.json と同じ項目（の一部）に、
  price・list_price・sale_title（キャンペーンの名前）・sale_end（終わりの日時）・rank（人気順。同人・ゲーム）を足したもの
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import get_new_releases as G  # noqa: E402
import doujin_game as D  # noqa: E402
import floor_data as F  # noqa: E402

PATH = os.environ.get("TEN_YEN_PATH", os.path.join(ROOT, "site", "src", "data", "ten_yen.json"))
PRICE = 10
FLOOR_MIN_LIST = 300  # 同人・ゲーム: 定価がこれ以上の作品が10円なら、10円セールの対象とみる（ふだんの「110円の95%OFF」と分ける）
FLOOR_KEYS = ("video", "doujin", "game")
PAGE = 100
RANK_PAGES = {"doujin": 30, "game": 15}  # 同人・ゲーム: 人気順の上から（同人3,000本・ゲーム1,500本。順位を付けるため）
CHEAP_BACK = 100  # 安い順: 二分探索で見つけた位置の、この本数だけ前から読む（順番が前後する所があるので）
CHEAP_MAX_PAGES = 30  # 安い順: 10円のあたりを読む最大（100本ずつ・3,000本まで。2026-10-10 の同人は161本）
OFFSET_MAX = 50000  # APIの offset の上限（total_count も 50000 で止まる）
RUN_KEEP_DAYS = 400
RUN_GAP_DAYS = 1  # 見かけた日が1日より空いたら、別の回
TITLE_LIMIT = 3
END = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VIDEO_KEYS = ("cid", "title", "url", "image_url", "date", "maker", "actress", "genres", "series_id", "series", "label_id", "label", "tags")
FLOOR_ITEM_KEYS = ("cid", "title", "url", "image_url", "date", "maker", "maker_id", "authors", "series", "series_id", "genres", "formats", "sales")


def price_pair(raw):
    """APIの1件の (価格, 定価)。読めなければ None"""
    prices = raw.get("prices") if isinstance(raw.get("prices"), dict) else {}
    return G.parse_yen(prices.get("price")), G.parse_yen(prices.get("list_price"))


def campaigns(raw):
    """APIの campaign の [(名前, 終わり)]。終わりは「YYYY-MM-DD HH:MM」の形のときだけ（ほかは ''）"""
    out = []
    for c in raw.get("campaign") or []:
        if not isinstance(c, dict):
            continue
        title = " ".join(str(c.get("title") or "").split())[:60]
        m = END.match(str(c.get("date_end") or ""))
        if title:
            out.append((title, f"{m.group(1)} {m.group(2)}:{m.group(3)}" if m else ""))
    return out


TEN_NAME = re.compile(r"(?<![0-9,])10円")


def has_ten_yen(name):
    """名前に「10円」があるか（全角の数字も。「110円」「1,010円」は入れない。サイトの lib/sale.js の isTenYenCampaign と同じ）"""
    return bool(TEN_NAME.search(unicodedata.normalize("NFKC", str(name or ""))))


def is_ten_yen(key, price, list_price, names):
    """10円セールの対象か（価格がちょうど10円で、値引きされているもの）"""
    if price != PRICE:
        return False
    if any(has_ten_yen(n) for n in names):
        return True
    if key == "video":
        return list_price is None or list_price > PRICE
    return list_price is not None and list_price >= FLOOR_MIN_LIST


def sale_info(camps, names):
    """(セールの名前, 終わりの日時)。名前に「10円」のあるキャンペーン（無ければ札）を先に、無ければ早く終わるキャンペーン"""
    ten = [c for c in camps if has_ten_yen(c[0])]
    if ten:
        return ten[0]
    tag = next((n for n in names if has_ten_yen(n)), "")
    if tag:
        return tag[:60], ""
    timed = sorted((c for c in camps if c[1]), key=lambda c: c[1])
    return timed[0] if timed else (camps[0] if camps else ("", ""))


def video_row(raw):
    """動画の1件 → 保存する形（10円の作品でなければ None）"""
    if not isinstance(raw, dict) or D.blocked_reason(raw):
        return None
    price, list_price = price_pair(raw)
    camps = campaigns(raw)
    if not is_ten_yen("video", price, list_price, [c[0] for c in camps]):
        return None
    item = G.parse_api_item(raw)
    if not item or not DAY.match(str(item["date"])[:10]):
        return None
    row = {k: item[k] for k in VIDEO_KEYS}
    row["url"] = G.safe_https_url(row["url"], G.LIST_HOSTS)
    row["image_url"] = G.safe_https_url(row["image_url"], G.IMAGE_HOSTS)
    if not row["url"]:
        return None
    title, end = sale_info(camps, [])
    row.update(price=price, list_price=list_price if list_price and list_price > PRICE else None, sale_title=title, sale_end=end)
    return row


def floor_row(raw, key, rank=None):
    """同人・ゲームの1件 → 保存する形（10円の作品でなければ None）"""
    if not isinstance(raw, dict) or D.blocked_reason(raw):
        return None
    price, list_price = price_pair(raw)
    if price != PRICE:
        return None
    item = D.parse_floor_item(raw, key)
    if not item:
        return None
    camps = campaigns(raw)
    names = [c[0] for c in camps] + list(item.get("sales") or [])
    if not is_ten_yen(key, item["price"], item["list_price"], names):
        return None
    row = {k: item[k] for k in FLOOR_ITEM_KEYS}
    title, end = sale_info(camps, list(item.get("sales") or []))
    row.update(price=PRICE, list_price=item["list_price"], sale_title=title, sale_end=end, rank=rank)
    return row


def ten_yen_start(base, call):
    """安い順（sort=-price）の一覧で、価格が10円以上の作品がはじまる位置（1から。二分探索）。読めなければ RuntimeError"""
    def price_at(off):
        got = call("ItemList", dict(base, sort="-price", offset=off, hits=1))
        time.sleep(G.DMM_INTERVAL_SEC)
        items = got.get("items") or []
        return got, (price_pair(items[0])[0] if items and isinstance(items[0], dict) else None)

    first, p1 = price_at(1)
    if p1 is None or p1 >= PRICE:
        return 1
    try:
        total = int(str(first.get("total_count") or "0").replace(",", ""))
    except ValueError:
        total = 0
    lo, hi = 2, min(max(total, 1), OFFSET_MAX) + 1
    while lo < hi:
        mid = (lo + hi) // 2
        _, pr = price_at(mid)
        if pr is None or pr >= PRICE:  # 価格の読めない作品は、10円以上とみる（前を探す）
            hi = mid
        else:
            lo = mid + 1
    return lo


def scan_cheap(base, call, make_row, rows, seen, today_str):
    """安い順の、10円のあたりを読んで、10円の作品を rows に足す → 最後まで読めたか"""
    try:
        start = max(1, ten_yen_start(base, call) - CHEAP_BACK)
    except RuntimeError as e:
        print(f"  ⚠️ 安い順の10円の位置を探せませんでした: {e}")
        return False
    off = start
    for _ in range(CHEAP_MAX_PAGES):
        try:
            got = call("ItemList", dict(base, sort="-price", offset=off, hits=PAGE)).get("items") or []
        except RuntimeError as e:
            print(f"  ⚠️ 安い順（{off}本目から）を取れませんでした: {e}")
            return False
        time.sleep(G.DMM_INTERVAL_SEC)
        low = False
        for raw in got:
            if not isinstance(raw, dict):
                continue
            price, _ = price_pair(raw)
            if price is not None and price <= PRICE:
                low = True
            row = make_row(raw)
            if row and row["cid"] not in seen and row["date"][:10] <= today_str:
                seen.add(row["cid"])
                rows.append(row)
        if not low or len(got) < PAGE or off + PAGE > OFFSET_MAX:
            break
        off += PAGE
    return True


def fetch_video(call, now):
    """動画の10円の作品（安い順の10円のあたりを、すべて） → (作品のリスト, 最後まで読めたか)"""
    rows, seen = [], set()
    base = {"site": "FANZA", "service": "digital", "floor": "videoa"}
    ok = scan_cheap(base, call, video_row, rows, seen, now.strftime("%Y-%m-%d"))
    return rows, ok


def fetch_floor(key, call, now):
    """同人・ゲームの10円の作品（人気順の上から＝順位付き → 安い順の10円のあたりを、すべて） → (作品のリスト, 最後まで読めたか)"""
    conf = F.FLOORS[key]
    today_str = now.strftime("%Y-%m-%d")
    lte = G.iso(now.replace(hour=23, minute=59, second=59, microsecond=0))
    base = {"site": "FANZA", "service": conf["service"], "floor": conf["floor"], "hits": PAGE}
    rows, seen = [], set()
    fails = read = 0
    off = 1
    while read < RANK_PAGES[key] and fails < G.MAX_API_FAILS_IN_ROW:
        try:
            got = call("ItemList", dict(base, sort="rank", offset=off, lte_date=lte)).get("items") or []
            fails = 0
        except RuntimeError as e:
            fails += 1
            print(f"  ⚠️ {conf['label']}の人気順（{off}本目から）を取れませんでした: {e}")
            continue
        read += 1
        time.sleep(G.DMM_INTERVAL_SEC)
        for pos, raw in enumerate(got):
            row = floor_row(raw, key, off + pos)
            if row and row["cid"] not in seen and row["date"][:10] <= today_str:
                seen.add(row["cid"])
                rows.append(row)
        if len(got) < PAGE:
            break
        off += PAGE
    if fails >= G.MAX_API_FAILS_IN_ROW:
        return rows, False
    cheap = {k: v for k, v in base.items() if k != "hits"}
    ok = scan_cheap(cheap, call, lambda raw: floor_row(raw, key), rows, seen, today_str)
    return rows, ok


def clean_run(r):
    """開催の記録の1行（決まった項目だけ）。使えなければ None"""
    if not isinstance(r, dict) or r.get("floor") not in FLOOR_KEYS or not DAY.match(str(r.get("first") or "")) or not DAY.match(str(r.get("last") or "")):
        return None
    if r["first"] > r["last"]:
        return None
    end = str(r.get("end") or "")
    titles = [" ".join(str(t).split())[:60] for t in (r.get("titles") or []) if str(t or "").strip()][:TITLE_LIMIT]
    return {"floor": r["floor"], "first": r["first"], "last": r["last"],
            "count": r["count"] if isinstance(r.get("count"), int) and r["count"] > 0 else 1,
            "end": end if END.match(end) and len(end) == 16 else "", "titles": titles}


def merge_runs(runs, found, today_str):
    """前の開催の記録と、きょう見かけた10円の作品 {floor: [作品]}（最後まで読めた売り場だけ） → 新しい記録（新しい順）"""
    rows = [r for r in (clean_run(x) for x in runs or []) if r]
    day = datetime.strptime(today_str, "%Y-%m-%d")
    for key, items in found.items():
        if not items:
            continue
        ends = sorted(i["sale_end"] for i in items if i.get("sale_end"))
        names = []
        for i in items:
            if i.get("sale_title") and i["sale_title"] not in names:
                names.append(i["sale_title"])
        mine = [r for r in rows if r["floor"] == key]
        last = max(mine, key=lambda r: r["last"]) if mine else None
        if last and (day - datetime.strptime(last["last"], "%Y-%m-%d")).days <= RUN_GAP_DAYS:
            last["last"] = max(last["last"], today_str)
            last["count"] = max(last["count"], len(items))
            if ends and ends[-1] > last["end"]:
                last["end"] = ends[-1]
            last["titles"] = (last["titles"] + [n for n in names if n not in last["titles"]])[:TITLE_LIMIT]
        else:
            rows.append({"floor": key, "first": today_str, "last": today_str, "count": len(items), "end": ends[-1] if ends else "", "titles": names[:TITLE_LIMIT]})
    since = (day - timedelta(days=RUN_KEEP_DAYS)).strftime("%Y-%m-%d")
    rows = [r for r in rows if r["last"] >= since]
    rows.sort(key=lambda r: (r["first"], r["floor"]), reverse=True)
    return rows


def load(path=PATH):
    """前のデータ（無ければ空）。壊れていたら ValueError（上書きしない）"""
    if not os.path.exists(path):
        return {"checked": "", **{k: [] for k in FLOOR_KEYS}, "runs": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(f"{os.path.basename(path)} を読めません: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"{os.path.basename(path)} の形が違います")
    out = {"checked": str(data.get("checked") or ""), "runs": [r for r in (clean_run(x) for x in data.get("runs") or []) if r]}
    for k in FLOOR_KEYS:
        out[k] = [x for x in data.get(k) or [] if isinstance(x, dict) and x.get("cid")]
    return out


def dump(data):
    """1作品・1回を1行にした JSON の文字（差分が読みやすいように）"""
    line = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
    parts = ["{", f'"checked":{json.dumps(data["checked"])},']
    for k in FLOOR_KEYS:
        rows = data[k]
        parts.append(f'"{k}":[' + ("\n" + ",\n".join(line(x) for x in rows) + "\n" if rows else "") + "],")
    parts.append('"runs":[' + ("\n" + ",\n".join(line(r) for r in data["runs"]) + "\n" if data["runs"] else "") + "]")
    parts.append("}")
    return "\n".join(parts) + "\n"


def signature(data):
    """変わったかを比べる中身（確かめた時刻は除く）"""
    return json.dumps({k: data[k] for k in (*FLOOR_KEYS, "runs")}, ensure_ascii=False, sort_keys=True)


def update(now, call=None, path=PATH, if_changed=False):
    """集めて保存する。→ (保存したか, 結果の要約の行)"""
    call = call or G.call_api
    old = load(path)
    new = {"checked": now.strftime("%Y-%m-%d %H:%M"), "runs": old["runs"]}
    found, lines = {}, []
    for key in FLOOR_KEYS:
        label = "動画" if key == "video" else F.FLOORS[key]["label"]
        try:
            rows, ok = fetch_video(call, now) if key == "video" else fetch_floor(key, call, now)
        except Exception as e:  # noqa: BLE001
            rows, ok = [], False
            print(f"::warning title={label}の10円セールを確かめられませんでした::{type(e).__name__}: {e}")
        if ok:
            new[key] = rows
            found[key] = rows
            lines.append(f"- {label}: 10円の作品 {len(rows)}本")
        else:
            new[key] = old[key]
            lines.append(f"- {label}: 最後まで確かめられなかったので、前のまま（{len(old[key])}本）")
    new["runs"] = merge_runs(old["runs"], found, now.strftime("%Y-%m-%d"))
    changed = signature(new) != signature(old)
    if if_changed and not changed:
        return False, lines + ["- 変わりなし（保存しません）"]
    with open(path, "w", encoding="utf-8") as f:
        f.write(dump(new))
    return True, lines + [f"- 保存しました（{'10円の作品が変わりました' if changed else '確かめた時刻だけ'}）"]


def main():
    parser = argparse.ArgumentParser(description="FANZAの10円セールの対象作品を集める")
    parser.add_argument("--update", action="store_true", help="集めて保存する")
    parser.add_argument("--if-changed", action="store_true", help="10円の作品が変わったときだけ保存する")
    args = parser.parse_args()
    if not args.update:
        parser.print_help()
        return
    if not G.API_ID:
        sys.exit("❌ API_ID が設定されていません")
    now = datetime.now(G.JST).replace(second=0, microsecond=0)
    try:
        saved, lines = update(now, if_changed=args.if_changed)
    except ValueError as e:
        print(f"::warning title=10円セールのデータを読めませんでした::{e}。上書きを防ぐため、今回は保存しません")
        saved, lines = False, [f"- データを読めなかったので、保存しませんでした: {e}"]
    for line in lines:
        print(line)
    G.write_step_summary(["### 💴 10円セール", "", *lines])
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"saved={1 if saved else 0}\n")


if __name__ == "__main__":
    main()
