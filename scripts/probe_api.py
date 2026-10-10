#!/usr/bin/env python3
"""FANZA(DMM) アフィリエイトAPI の「本物の応答の形」を調べる道具（読むだけ。Pythonの標準ライブラリだけ）

新しい機能（サンプル動画・出演者のプロフィール・売れ筋ランキング）を作る前に、本物のAPIが返す項目を確かめるために、
GitHub Actions の「Probe FANZA API」から手動で動かします。保存はしません。Geminiは使いません。
実行結果は Actions のログと「結果の要約」に出ます（リポジトリは公開なので、ログも公開されます）。
・API_ID などの秘密の値と、それを含むURLは、出力しません
・出演者の誕生日・血液型・趣味・出身地は、値を出さず「あるかどうか」だけ出します
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
API_ID = os.environ.get("API_ID", "")
AFFILIATE_ID = os.environ.get("AFFILIATE_ID", "juice0402-990")
DATA_PATH = os.path.join("site", "src", "data", "new_releases.json")
BASE = "https://api.dmm.com/affiliate/v3/"
PERSONAL = {"birthday", "blood_type", "hobby", "prefectures"}  # 値は出さない
lines = []


def say(text=""):
    print(text)
    lines.append(text)


def call(endpoint, params):
    """APIを呼ぶ。失敗しても止まらず (結果, エラー文) を返す。URL（API_IDを含む）は出さない"""
    q = {"api_id": API_ID, "affiliate_id": AFFILIATE_ID, "output": "json"}
    q.update(params)
    url = BASE + endpoint + "?" + urllib.parse.urlencode(q)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as res:
            data = json.loads(res.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e).replace(API_ID, '***')}"[:200]
    result = data.get("result") or {}
    status = result.get("status")
    if status is not None and str(status) != "200":
        return None, f"status={status} message={result.get('message')}"
    return result, None


def shape(value, depth=0):
    """値の「形」だけを文字にする（値そのものは出さない）"""
    if isinstance(value, dict):
        if depth >= 3:
            return "{…}"
        return "{" + ", ".join(f"{k}: {shape(v, depth + 1)}" for k, v in list(value.items())[:20]) + "}"
    if isinstance(value, list):
        return f"[{shape(value[0], depth + 1)} ×{len(value)}]" if value else "[]"
    if isinstance(value, str):
        return f"str({len(value)})"
    return type(value).__name__ + (f"={value}" if isinstance(value, (int, float, bool)) else "")


def mask_url(url):
    """URLの形だけ（ホスト + パスの数字を # に）。af_id は出さない"""
    p = urllib.parse.urlparse(str(url))
    text = f"{p.scheme}://{p.netloc}{re.sub(r'[0-9]+', '#', p.path)}"
    inner = urllib.parse.parse_qs(p.query).get("lurl", [""])[0]  # アフィリエイトの飛び先（本来のURL）の形も見る
    if inner:
        q = urllib.parse.urlparse(inner)
        text += f" → lurl={q.scheme}://{q.netloc}{re.sub(r'[0-9]+', '#', q.path)}" + ("?…" if q.query else "")
    elif p.query:
        text += "?…"
    return text



def probe_ten_yen():
    """13) 10円セール: 安い順（sort=-price）の中で、10円の作品がどこから始まり、何本あるか
    （運営者の「同人の10円セールは71本あるのに、サイトは18本。期間中は全部載せたい」。2026-10-10。
    人気順の上から3,000本しか見ていないので、安い順の中の10円の場所を、二分探索で探せるかを確かめる）"""
    import time
    from collections import Counter
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ten_yen as T
    import doujin_game as D
    try:
        have = json.load(open(T.PATH, encoding="utf-8"))
    except (OSError, ValueError):
        have = {}
    import floor_data as F
    targets = [("video", "動画", "digital", "videoa")] + [(k, c["label"], c["service"], c["floor"]) for k, c in F.FLOORS.items() if k != "vr"]
    for key, label, svc, flr in targets:
        say(f"## 13-{key}) 10円セール: {label}の安い順")
        base = {"site": "FANZA", "service": svc, "floor": flr, "sort": "-price"}
        calls = [0]

        def page(off, hits):
            calls[0] += 1
            time.sleep(0.4)
            res, err = call("ItemList", dict(base, offset=off, hits=hits))
            if err:
                raise RuntimeError(err)
            return res

        try:
            first = page(1, 1)
        except RuntimeError as e:
            say(f"- ❌ {e}")
            continue
        total = int(first.get("total_count") or 0)
        top = min(total, 50000)
        price = lambda raw: T.price_pair(raw)[0]  # noqa: E731
        p1 = price((first.get("items") or [{}])[0])
        say(f"- 全体 {total}本・先頭の価格 {p1}")
        lo, hi, unknown = 1, top + 1, 0  # 価格が10円以上の、いちばん前の位置を探す
        try:
            while lo < hi:
                mid = (lo + hi) // 2
                got = page(mid, 1).get("items") or []
                pr = price(got[0]) if got else None
                if pr is None:
                    unknown += 1
                if pr is None or pr >= T.PRICE:
                    hi = mid
                else:
                    lo = mid + 1
        except RuntimeError as e:
            say(f"- ❌ 二分探索の途中: {e}")
            continue
        say(f"- 10円以上が始まる位置 {lo}（呼んだ回数 {calls[0]}・価格が読めない {unknown}）")
        start = max(1, lo - 5)
        tens, prices, drops, last = [], [], 0, None
        off = start
        try:
            for _ in range(30):
                got = page(off, 100).get("items") or []
                stop = False
                for raw in got:
                    pr = price(raw)
                    prices.append(pr)
                    if pr is not None and last is not None and pr < last:
                        drops += 1
                    if pr is not None:
                        last = pr
                    if pr == T.PRICE:
                        tens.append(raw)
                    elif pr is not None and pr > T.PRICE:
                        stop = True
                if stop or len(got) < 100:
                    break
                off += 100
        except RuntimeError as e:
            say(f"- ❌ 読み進める途中: {e}")
        say(f"- はじめの価格 {prices[:8]}・終わりの価格 {prices[-3:]}・前より安くなった所 {drops}・読んだ位置 {start}〜{off + 99}")
        blocked = Counter()
        rows, list_prices, names = [], Counter(), Counter()
        for raw in tens:
            reason = D.blocked_reason(raw)
            if reason:
                blocked[reason] += 1
            _, lp = T.price_pair(raw)
            list_prices["定価なし" if lp is None else ("300円以上" if lp >= 300 else "300円未満")] += 1
            for c in T.campaigns(raw):
                names[c[0]] += 1
            row = T.video_row(raw) if key == "video" else T.floor_row(raw, key)
            if row:
                rows.append(row)
        cur = {r.get("cid") for r in have.get(key) or []}
        got_c = {r["cid"] for r in rows}
        say(f"- 価格がちょうど10円 {len(tens)}本 / うち未成年を連想させる {sum(blocked.values())}本（{dict(blocked)}） / 定価 {dict(list_prices)}")
        say(f"- 10円セールの対象として載せられる {len(rows)}本 / いまのデータ {len(cur)}本 / いまのデータにもある {len(cur & got_c)}本 / いまのデータにだけある {len(cur - got_c)}本")
        say(f"- キャンペーンの名前: {dict(names.most_common(6))}")
        say(f"- 発売日が未来（予約） {sum(1 for r in rows if str(r.get('date'))[:10] > datetime.now(JST).strftime('%Y-%m-%d'))}本")


def main():
    if not API_ID:
        sys.exit("❌ API_ID が設定されていません")
    if os.environ.get("PROBE_ONLY") == "13":
        probe_ten_yen()
        finish()
        return
    today = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    fmt = "%Y-%m-%dT%H:%M:%S"
    try:
        archive = json.load(open(DATA_PATH, encoding="utf-8"))
    except (OSError, ValueError):
        archive = []
    base = {"site": "FANZA", "service": "digital", "floor": "videoa"}

    # 新しい売り場の下調べ（運営者の希望「アニメ動画・素人・成人映画・FANZAブックス（コミック・写真集）・VR見放題も」。2026-10-10）
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    try:
        from claude_comments import title_block_reason as tbr
    except Exception:  # noqa: BLE001
        tbr = lambda x: ""  # noqa: E731
    from collections import Counter

    def masked(u, cid):
        u = str(u or "")
        if cid:
            u = u.replace(cid, "{cid}")
        return re.sub(r"[0-9]", "#", u)[:110]

    for n_, (label, svc, flr) in enumerate((("アニメ動画", "digital", "anime"), ("素人", "digital", "videoc"), ("成人映画", "digital", "nikkatsu"),
                                             ("ブックス・コミック", "ebook", "comic"), ("ブックス・写真集", "ebook", "photo"), ("VR見放題", "monthly", "vr")), start=1):
        say(f"## 11-{n_}) 新しい売り場: {label}（{svc}/{flr}）")
        got, total = [], None
        for off in (1, 101, 201):
            res, err = call("ItemList", {"site": "FANZA", "service": svc, "floor": flr, "sort": "rank", "hits": 100, "offset": off})
            if err:
                say(f"- offset={off}: ❌ {err}")
                break
            total = res.get("total_count")
            got += res.get("items") or []
        if not got:
            continue
        keys, info_keys, img_forms, smp_forms, aff_forms, price_forms = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
        blocked = cid_bad = with_review = with_actress = with_author = with_maker = with_movie = future = 0
        today_s = today.strftime("%Y-%m-%d")
        for x in got:
            cid = str(x.get("content_id") or "")
            keys.update(x.keys())
            info = x.get("iteminfo") or {}
            info_keys.update(info.keys())
            img_forms[masked((x.get("imageURL") or {}).get("large"), cid)] += 1
            smp = x.get("sampleImageURL") or {}
            smp_forms[",".join(sorted(smp.keys())) + " " + masked(((smp.get("sample_l") or smp.get("sample_s") or {}).get("image") or [""])[0], cid)] += 1
            aff_forms[mask_url(x.get("affiliateURL"))] += 1
            pr = x.get("prices") or {}
            price_forms[re.sub(r"[0-9]", "#", f"{pr.get('price')}|{pr.get('list_price')}")] += 1
            texts = [x.get("title")] + [g.get("name") for k in ("genre", "series", "maker", "author", "label") for g in info.get(k) or [] if isinstance(g, dict)]
            if any(t and tbr({"title": str(t)}) == "minor" for t in texts):
                blocked += 1
            if not re.match(r"^[A-Za-z0-9_\-]{1,40}$", cid):
                cid_bad += 1
            with_review += bool(x.get("review"))
            with_actress += bool(info.get("actress"))
            with_author += bool(info.get("author"))
            with_maker += bool(info.get("maker"))
            with_movie += bool(x.get("sampleMovieURL"))
            future += str(x.get("date") or "")[:10] > today_s
        say(f"- 取得 {len(got)}本 / 全体 {total} / 未成年を連想させる {blocked}本 / 品番の形が違う {cid_bad}本 / 予約 {future}本 / レビューあり {with_review} / 出演者あり {with_actress} / 作者あり {with_author} / メーカーあり {with_maker} / サンプル動画あり {with_movie}")
        say(f"- 項目: {', '.join(sorted(keys))} / iteminfo: {dict(info_keys.most_common(12))}")
        say(f"- 表紙の形: {img_forms.most_common(3)}")
        say(f"- サンプル画像の形: {smp_forms.most_common(2)}")
        say(f"- リンクの形: {aff_forms.most_common(2)} / 価格の形: {price_forms.most_common(4)}")
        ex = got[0]
        say(f"- 1本目: 品番 {ex.get('content_id')} / volume {ex.get('volume')} / 発売日 {ex.get('date')} / iteminfo {json.dumps({k: [g.get('name') for g in v][:3] for k, v in (ex.get('iteminfo') or {}).items() if isinstance(v, list)}, ensure_ascii=False)[:300]}")

    # 新しい売り場の画像（表紙の大きさ・ほかのサイトの中で読めるか・pics.dmm.co.jp にも同じ画像があるか）
    def jpeg_size(data):
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            m = data[i + 1]
            if m in (0xC0, 0xC1, 0xC2):
                return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
            i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
        return None

    def fetch_img(url, referer=None):
        try:
            h = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"}
            if referer:
                h["Referer"] = referer
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=20) as r:
                body = r.read()
                return r.status, len(body), jpeg_size(body), body
        except Exception as e:  # noqa: BLE001
            return type(e).__name__ + str(getattr(e, "code", "")), 0, None, b""

    for n_, (label, svc, flr) in enumerate((("素人", "digital", "videoc"), ("ブックス・コミック", "ebook", "comic"), ("ブックス・写真集", "ebook", "photo"), ("成人映画", "digital", "nikkatsu")), start=1):
        say(f"## 12-{n_}) 画像: {label}")
        res, err = call("ItemList", {"site": "FANZA", "service": svc, "floor": flr, "sort": "rank", "hits": 2})
        if err:
            say(f"- ❌ {err}")
            continue
        for x in res.get("items") or []:
            cid = str(x.get("content_id") or "")
            imgs = x.get("imageURL") or {}
            say(f"- {cid}: imageURL {json.dumps({k: masked(v, cid) for k, v in imgs.items()}, ensure_ascii=False)}")
            for k in ("large", "small", "list"):
                u = imgs.get(k)
                if not u:
                    continue
                st, ln, sz, body = fetch_img(u)
                st2, ln2, _, _ = fetch_img(u, "https://fanza-ranking.pages.dev/")
                line = f"  - {k}: 状態 {st} {ln}バイト {sz} / ほかのサイトから {st2} {ln2}バイト"
                if "ebook-assets.dmm.co.jp/" in u:
                    alt = u.replace("https://ebook-assets.dmm.co.jp/", "https://pics.dmm.co.jp/")
                    st3, ln3, sz3, body3 = fetch_img(alt)
                    line += f" / pics.dmm.co.jp: {st3} {ln3}バイト {sz3} 同じ中身={body3 == body and bool(body)}"
                    small = re.sub(r"pl\.jpg$", "ps.jpg", u)
                    if small != u:
                        st4, ln4, sz4, _ = fetch_img(small)
                        line += f" / ps.jpg: {st4} {ln4}バイト {sz4}"
                say(line)
            if not imgs.get("large") and svc == "digital":
                for guess in (f"https://pics.dmm.co.jp/digital/amateur/{cid}/{cid}jp.jpg", f"https://pics.dmm.co.jp/digital/amateur/{cid}/{cid}jm.jpg", f"https://pics.dmm.co.jp/digital/video/{cid}/{cid}pl.jpg"):
                    st, ln, sz, _ = fetch_img(guess)
                    say(f"  - 推測 {masked(guess, cid)}: {st} {ln}バイト {sz}")
            break

    say("\n## 8) まだ使っていないAPI・項目（レビュー・評価順・フロア・ジャンル・メーカー・シリーズ・作者の検索）")
    res, err = call("ItemList", dict(base, sort="rank", hits=5))
    if err:
        say(f"- 人気順の review: ❌ {err}")
    else:
        say("- 人気順の上位5本の review: " + " / ".join(f"{x.get('content_id')}={json.dumps(x.get('review'), ensure_ascii=False)}" for x in res.get("items") or []))
        it = (res.get("items") or [{}])[0]
        say("- iteminfo のキー: " + ", ".join(sorted((it.get("iteminfo") or {}).keys())) + " / 項目のキー: " + ", ".join(sorted(it.keys())))
    res, err = call("ItemList", dict(base, sort="review", hits=5))
    say("- sort=review（評価順）の上位5本: " + (f"❌ {err}" if err else " / ".join(f"{x.get('content_id')}（{str(x.get('date'))[:10]}）={json.dumps(x.get('review'), ensure_ascii=False)}" for x in res.get("items") or [])))
    for label, fl in (("同人", {"site": "FANZA", "service": "doujin", "floor": "digital_doujin"}), ("ゲーム", {"site": "FANZA", "service": "pcgame", "floor": "digital_pcgame"})):
        res, err = call("ItemList", dict(fl, sort="rank", hits=3))
        say(f"- {label}の人気順の review・iteminfo のキー: " + (f"❌ {err}" if err else " / ".join(f"{x.get('content_id')}={json.dumps(x.get('review'), ensure_ascii=False)}" for x in res.get("items") or [])
            + " / " + ", ".join(sorted(((res.get("items") or [{}])[0].get("iteminfo") or {}).keys()))))
    res, err = call("FloorList", {})
    floor_ids = {}
    if err:
        say(f"- FloorList: ❌ {err}")
    else:
        for site_ in res.get("site") or []:
            if site_.get("code") != "FANZA":
                continue
            for sv in site_.get("service") or []:
                fls = [f"{f.get('name')}({f.get('code')}/{f.get('id')})" for f in sv.get("floor") or []]
                for f in sv.get("floor") or []:
                    floor_ids[(sv.get("code"), f.get("code"))] = f.get("id")
                say(f"- FANZA の {sv.get('name')}（{sv.get('code')}）: " + "、".join(fls))
    say("\n## 9) ジャンル・メーカー・シリーズ・作者の検索API（売り場ごと）")
    for label, key in (("動画", ("digital", "videoa")), ("同人", ("doujin", "digital_doujin")), ("ゲーム", ("pcgame", "digital_pcgame"))):
        fid = floor_ids.get(key)
        if not fid:
            say(f"- {label}: フロアの id が分からない")
            continue
        for api, extra in (("GenreSearch", {}), ("MakerSearch", {}), ("SeriesSearch", {}), ("AuthorSearch", {})):
            res, err = call(api, dict(floor_id=fid, hits=3, **extra))
            if err:
                say(f"- {label} {api}: ❌ {err}")
                continue
            rows = next((v for k, v in res.items() if isinstance(v, list)), [])
            say(f"- {label} {api}: 全体 {res.get('total_count')}件 / キー {sorted(rows[0].keys()) if rows else '-'} / 例 {[(r.get('name'), r.get('ruby')) for r in rows[:2]]}")
    say("\n## 10) ジャンルを指定した人気順・評価順")
    res, err = call("GenreSearch", dict(floor_id=floor_ids.get(("digital", "videoa")) or 43, hits=100))
    if not err:
        g = next((r for r in res.get("genre") or [] if r.get("name") in ("巨乳", "人妻・主婦", "単体作品")), None)
        if g:
            r2, e2 = call("ItemList", dict(base, article="genre", article_id=g.get("genre_id"), sort="rank", hits=3))
            say(f"- ItemList article=genre（{g.get('name')}）: " + (f"❌ {e2}" if e2 else f"全体 {r2.get('total_count')}件 / 上位 {[x.get('content_id') for x in r2.get('items') or []]}"))
            r3, e3 = call("ItemList", dict(base, article="genre", article_id=g.get("genre_id"), sort="review", hits=3))
            say(f"- 同じジャンルの評価順: " + (f"❌ {e3}" if e3 else str([(x.get('content_id'), (x.get('review') or {}).get('count'), (x.get('review') or {}).get('average')) for x in r3.get('items') or []])))
    for label, fl in (("同人", {"site": "FANZA", "service": "doujin", "floor": "digital_doujin"}), ("ゲーム", {"site": "FANZA", "service": "pcgame", "floor": "digital_pcgame"})):
        r4, e4 = call("ItemList", dict(fl, sort="review", hits=5))
        say(f"- {label}の評価順: " + (f"❌ {e4}" if e4 else str([(x.get('content_id'), (x.get('review') or {}).get('count'), (x.get('review') or {}).get('average')) for x in r4.get('items') or []])))
    with_review = 0
    total = 0
    for off in (1, 101, 1001):
        r5, e5 = call("ItemList", dict(base, sort="rank", hits=100, offset=off))
        if not e5:
            got = r5.get("items") or []
            total += len(got)
            with_review += sum(1 for x in got if x.get("review"))
    say(f"- 動画の人気順（1〜100・101〜200・1001〜1100本目）で、レビューのある作品: {with_review}/{total}本")

    say("\n## 7) 安い順（sort=-price）で、10円の作品を見つけられるか（動画・同人・ゲーム）")
    floors = (("動画", base), ("同人", {"site": "FANZA", "service": "doujin", "floor": "digital_doujin"}),
              ("ゲーム", {"site": "FANZA", "service": "pcgame", "floor": "digital_pcgame"}))

    def yen(v):
        m = re.match(r"^\s*([0-9][0-9,]*)", str(v or ""))
        return int(m.group(1).replace(",", "")) if m else None

    for label, fl in floors:
        for sort in ("-price", "price"):
            for off in ((1, 101, 501) if sort == "-price" else (1,)):
                res, err = call("ItemList", dict(fl, sort=sort, hits=100, offset=off))
                if err:
                    say(f"- {label} sort={sort} offset={off}: ❌ {err}")
                    continue
                got = res.get("items") or []
                pr = [(yen((x.get("prices") or {}).get("price")), yen((x.get("prices") or {}).get("list_price"))) for x in got]
                now = [p for p, _ in pr if p is not None]
                mono = all(a <= b for a, b in zip(now, now[1:])) if sort == "-price" else all(a >= b for a, b in zip(now, now[1:]))
                disc = sum(1 for p, l in pr if p is not None and l is not None and p < l)
                raw_forms = sorted({re.sub(r"[0-9]", "#", str((x.get("prices") or {}).get("price"))) for x in got})[:5]
                camps = sorted({str(c.get("title"))[:24] for x in got for c in (x.get("campaign") or []) if isinstance(c, dict)})[:8]
                say(f"- {label} sort={sort} offset={off}: {len(got)}件 / 全体 {res.get('total_count')} / 価格 {now[:12]}… 最後 {now[-3:]} / 価格の順に並ぶ={mono} / 値引き中 {disc}件 / 0円 {sum(1 for p in now if p == 0)}件 / 10円 {sum(1 for p in now if p == 10)}件 / 10円以下 {sum(1 for p in now if p <= 10)}件 / 価格の書き方 {raw_forms} / キャンペーン名 {camps}")
                if sort == "-price" and off == 1:
                    ten = [x for x in got if yen((x.get("prices") or {}).get("price")) == 10][:3]
                    for x in ten:
                        say(f"  - 10円の例: {x.get('content_id')} 定価 {(x.get('prices') or {}).get('list_price')} / deliveries {json.dumps((x.get('prices') or {}).get('deliveries'), ensure_ascii=False)[:300]} / campaign {json.dumps(x.get('campaign'), ensure_ascii=False)[:200]} / 発売日 {str(x.get('date'))[:10]}")
                    cheap = [x for x in got if (yen((x.get("prices") or {}).get("price")) or 0) > 0][:2]
                    for x in cheap:
                        say(f"  - 0円より上の最初の例: {x.get('content_id')} 価格 {(x.get('prices') or {}).get('price')} 定価 {(x.get('prices') or {}).get('list_price')} / campaign {json.dumps(x.get('campaign'), ensure_ascii=False)[:160]}")

    say("\n## 0) 過去作品の集め方（人気順・発売済みだけ・offset で続きから）")
    lte = today.replace(hour=23, minute=59, second=59).strftime(fmt)
    for off in (1, 101, 25001, 49901, 50001):
        res, err = call("ItemList", dict(base, sort="rank", hits=100, offset=off, lte_date=lte))
        if err:
            say(f"- offset={off}: ❌ {err}")
            continue
        got = res.get("items") or []
        days = sorted(str(x.get("date", ""))[:10] for x in got if x.get("date"))
        future = sum(1 for d in days if d > today.strftime("%Y-%m-%d"))
        say(f"- offset={off}: 取得 {len(got)}件 / 全体 {res.get('total_count')}件 / first_position {res.get('first_position')} / 発売日 {days[0] if days else '-'}〜{days[-1] if days else '-'} / 未来の発売日 {future}件")
    res1, _ = call("ItemList", dict(base, sort="rank", hits=100, offset=1, lte_date=lte))
    res2, _ = call("ItemList", dict(base, sort="rank", hits=100, offset=101, lte_date=lte))
    if res1 and res2:
        a = {x.get("content_id") for x in res1.get("items") or []}
        b = {x.get("content_id") for x in res2.get("items") or []}
        say(f"- 1〜100本目と101〜200本目の重なり: {len(a & b)}件（0なら、offset で続きを取れている）")

    say("\n## 1) ItemList（新しい作品）の項目")
    res, err = call("ItemList", dict(base, sort="date", hits=20, gte_date=(today - timedelta(days=3)).strftime(fmt), lte_date=today.replace(hour=23, minute=59, second=59).strftime(fmt)))
    if err:
        say(f"❌ {err}")
        items = []
    else:
        items = res.get("items") or []
        say(f"- 取得 {len(items)}件 / 全体 {res.get('total_count')}件")
        if items:
            it = items[0]
            say("- 1件目の項目（形）: " + shape({k: v for k, v in it.items() if k not in ("title", "affiliateURL", "affiliateURLsp", "URL", "URLsp")}))
            say("- sampleMovieURL（値）: " + json.dumps(it.get("sampleMovieURL"), ensure_ascii=False))
            say("- review: " + json.dumps(it.get("review"), ensure_ascii=False))
            say("- iteminfo.actress（id と名前）: " + json.dumps((it.get("iteminfo") or {}).get("actress"), ensure_ascii=False))
        movies = [x.get("sampleMovieURL") for x in items]
        say(f"- サンプル動画あり: {sum(1 for m in movies if m)}件 / 20件中。pc_flag=1: {sum(1 for m in movies if m and m.get('pc_flag') in (1, '1'))}件、sp_flag=1: {sum(1 for m in movies if m and m.get('sp_flag') in (1, '1'))}件")
        say(f"- 出演者あり: {sum(1 for x in items if (x.get('iteminfo') or {}).get('actress'))}件 / 出演者なし: {sum(1 for x in items if not (x.get('iteminfo') or {}).get('actress'))}件")

    say("\n## 2) ItemList sort=rank（人気順 = 売れ筋）の上位")
    for label, extra in (("日付の絞り込みなし", {}), ("発売日が直近30日", {"gte_date": (today - timedelta(days=30)).strftime(fmt), "lte_date": today.replace(hour=23, minute=59, second=59).strftime(fmt)})):
        res, err = call("ItemList", dict(base, sort="rank", hits=5, **extra))
        if err:
            say(f"- {label}: ❌ {err}")
            continue
        rows = [f"{x.get('content_id')}（発売日 {str(x.get('date'))[:10]}）" for x in (res.get("items") or [])]
        say(f"- {label}: " + " / ".join(rows))

    say("\n## 3) ItemList を cid（品番）で指定して取り直せるか")
    for entry in [x for x in archive if isinstance(x, dict) and x.get("cid")][:3]:
        res, err = call("ItemList", dict(base, cid=entry["cid"], hits=5))
        if err:
            say(f"- {entry['cid']}: ❌ {err}")
            continue
        got = res.get("items") or []
        say(f"- {entry['cid']}: {len(got)}件 / 先頭の cid = {got[0].get('content_id') if got else None} / sampleMovieURL あり = {bool(got and got[0].get('sampleMovieURL'))} / 出演者 = {[a.get('name') for a in ((got[0].get('iteminfo') or {}).get('actress') or [])] if got else None}")

    say("\n## 4) ActressSearch（出演者）")
    actress = None
    for it in items:
        for a in (it.get("iteminfo") or {}).get("actress") or []:
            if a.get("id") and a.get("name"):
                actress = a
                break
        if actress:
            break
    if not actress:
        say("- 出演者つきの作品が取れなかったので、スキップ")
    else:
        res, err = call("ActressSearch", {"actress_id": actress["id"], "hits": 3})
        if err:
            say(f"❌ actress_id={actress['id']}: {err}")
        else:
            rows = res.get("actress") or []
            say(f"- actress_id 指定: {len(rows)}件（total_count {res.get('total_count')}）")
            if rows:
                a = rows[0]
                say("- 項目（形）: " + shape(a))
                say("- 個人情報の項目は、あるかどうかだけ: " + ", ".join(f"{k}={'あり' if a.get(k) else 'なし'}" for k in sorted(PERSONAL)))
                say("- 体型・画像（値）: " + json.dumps({k: a.get(k) for k in ("name", "ruby", "bust", "cup", "waist", "hip", "height")}, ensure_ascii=False))
                say("- imageURL（値）: " + json.dumps(a.get("imageURL"), ensure_ascii=False))
                say("- listURL（形）: " + json.dumps({k: mask_url(v) for k, v in (a.get("listURL") or {}).items()}, ensure_ascii=False))
                bd = str(a.get("birthday") or "")
                say(f"- birthday の書き方: {re.sub(r'[0-9]', '#', bd) or '（なし）'}")
        # 名前（keyword）で探したとき、同じ名前が何人出るか
        names = []
        for entry in archive:
            for n in (entry.get("actress") or []) if isinstance(entry, dict) else []:
                if n not in names:
                    names.append(n)
        for name in names[:5]:
            res, err = call("ActressSearch", {"keyword": name, "hits": 5})
            if err:
                say(f"- keyword={name}: ❌ {err}")
                continue
            rows = res.get("actress") or []
            exact = [a for a in rows if a.get("name") == name]
            say(f"- keyword={name}: {len(rows)}件 / 名前が完全に一致 {len(exact)}件 / id = {[a.get('id') for a in exact]}")
        # 出演者の他の作品を、ItemList で取れるか
        res, err = call("ItemList", dict(base, article="actress", article_id=actress["id"], sort="date", hits=3))
        say(f"- ItemList article=actress（{actress.get('name')}）: " + (f"❌ {err}" if err else f"{len(res.get('items') or [])}件 / 全体 {res.get('total_count')}件"))

    say("\n## 5) ActressSearch: 体型などが入っている出演者の値の書き方")
    for aid in ("1017139", "1047611", "1043753", "1092663", "1056220"):
        res, err = call("ActressSearch", {"actress_id": aid, "hits": 1})
        rows = [] if err else (res.get("actress") or [])
        if not rows:
            say(f"- id={aid}: {'❌ ' + err if err else '0件'}")
            continue
        a = rows[0]
        bd = str(a.get("birthday") or "")
        lurl = urllib.parse.parse_qs(urllib.parse.urlparse(str((a.get("listURL") or {}).get("digital") or "")).query).get("lurl", [""])[0]
        lq = urllib.parse.urlparse(lurl)
        say(f"- id={aid} {a.get('name')}: " + json.dumps({k: a.get(k) for k in ("bust", "cup", "waist", "hip", "height")}, ensure_ascii=False)
            + f" / birthday={re.sub(r'[0-9]', '#', bd) or 'なし'} / 型 bust={type(a.get('bust')).__name__} height={type(a.get('height')).__name__}"
            + f" / 画像 {a.get('imageURL')} / digital の飛び先 {lq.scheme}://{lq.netloc}{lq.path}?{urllib.parse.urlencode({k: re.sub(r'[0-9]', '#', v[0]) for k, v in urllib.parse.parse_qs(lq.query).items()})}")

    say("\n## 6) サンプル動画のページ（iframe で埋め込めるか）")
    movie = None
    for it in items:
        m = it.get("sampleMovieURL") or {}
        if m.get("size_720_480"):
            movie = m["size_720_480"]
            break
    if not movie:
        say("- サンプル動画のURLが無いのでスキップ")
    else:
        try:
            req = urllib.request.Request(movie, headers={"User-Agent": "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1", "Referer": "https://fanza-ranking.pages.dev/"})
            with urllib.request.urlopen(req, timeout=30) as res:
                head = {k.lower(): v for k, v in res.headers.items()}
                body = res.read(200000).decode("utf-8", "replace")
                final = urllib.parse.urlparse(res.geturl())
            say(f"- 状態 {res.status} / 最終URL {final.scheme}://{final.netloc}{re.sub(r'[0-9]+', '#', final.path)}")
            say("- x-frame-options: " + str(head.get("x-frame-options")) + " / content-security-policy(frame-ancestors): " + str(re.findall(r"frame-ancestors[^;]*", head.get("content-security-policy", "")) or None))
            say("- content-type: " + str(head.get("content-type")) + f" / 本文 {len(body)}文字 / 年齢確認らしい語: {bool(re.search('age_check|年齢確認|18歳', body))} / video または source タグ: {bool(re.search('<video|<source|mp4|m3u8', body))}")
        except Exception as e:  # noqa: BLE001
            say(f"- 取得できませんでした: {type(e).__name__}: {str(e)[:150]}")

    finish()


def finish():
    """結果を注釈と要約に出す"""
    # ログの取得が制限される環境でも読めるように、見出しごとに「注釈（notice）」としても出す（GitHub の check-run の注釈として読める）
    if os.environ.get("GITHUB_ACTIONS"):
        sections = []
        for text in lines:
            if text.lstrip("\n").startswith("## ") or not sections:
                sections.append([text])
            else:
                sections[-1].append(text)
        for block in sections[:30]:
            title = block[0].strip().lstrip("# ").strip()[:100]
            body = "\n".join(block[1:]).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::notice title={title}::{body}")

    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("### FANZA API の応答の形\n\n" + "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
