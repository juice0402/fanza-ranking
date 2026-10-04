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


def main():
    if not API_ID:
        sys.exit("❌ API_ID が設定されていません")
    today = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    fmt = "%Y-%m-%dT%H:%M:%S"
    try:
        archive = json.load(open(DATA_PATH, encoding="utf-8"))
    except (OSError, ValueError):
        archive = []
    base = {"site": "FANZA", "service": "digital", "floor": "videoa"}

    say("## 1) ItemList（新しい作品）の項目")
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

    say("\n## 7) ActressSearch: 一覧で何人取れるか（女優検索を大きくするための下調べ。名前や体型の値は出さない）")
    for label, extra in (("絞り込みなし", {}), ("バストあり gte_bust=1", {"gte_bust": 1}), ("身長あり gte_height=1", {"gte_height": 1}),
                         ("生年月日あり gte_birthday=1900-01-01", {"gte_birthday": "1900-01-01"}), ("バスト・身長あり", {"gte_bust": 1, "gte_height": 1})):
        res, err = call("ActressSearch", dict({"hits": 1}, **extra))
        say(f"- {label}: " + (f"❌ {err}" if err else f"total_count {res.get('total_count')}"))
    for label, extra in (("sort=-id hits=100 offset=1", {"sort": "-id", "hits": 100, "offset": 1}), ("sort=id hits=100 offset=1", {"sort": "id", "hits": 100, "offset": 1}),
                         ("gte_bust=1 sort=-id hits=100 offset=101", {"gte_bust": 1, "sort": "-id", "hits": 100, "offset": 101})):
        res, err = call("ActressSearch", extra)
        if err:
            say(f"- {label}: ❌ {err}")
            continue
        rows = res.get("actress") or []
        ids = [int(a.get("id")) for a in rows if str(a.get("id") or "").isdigit()]
        has = lambda k: sum(1 for a in rows if a.get(k))
        say(f"- {label}: {len(rows)}件（result_count {res.get('result_count')} / first_position {res.get('first_position')}）/ id {ids[:1]}…{ids[-1:]} / "
            f"バストあり {has('bust')}・身長あり {has('height')}・生年月日あり {has('birthday')}・顔写真あり {sum(1 for a in rows if (a.get('imageURL') or {}).get('small'))}・読みあり {has('ruby')}")
    for off in (10001, 30001, 50001):
        res, err = call("ActressSearch", {"sort": "id", "hits": 1, "offset": off})
        say(f"- offset={off}: " + (f"❌ {err}" if err else f"{len(res.get('actress') or [])}件"))

    say("\n## 8) ItemList: 作品の説明文があるか・シリーズ・レーベル（ひとことを詳しくするための下調べ）")
    res, err = call("ItemList", dict(base, sort="date", hits=50, lte_date=today.replace(hour=23, minute=59, second=59).strftime(fmt)))
    if err:
        say(f"❌ {err}")
    else:
        rows = res.get("items") or []
        top = sorted({k for x in rows for k in x})
        info = sorted({k for x in rows for k in (x.get("iteminfo") or {})})
        say(f"- 作品{len(rows)}件の項目（すべて）: {', '.join(top)}")
        say(f"- iteminfo の項目（すべて）: {', '.join(info)}")
        texty = [k for k in top if any(isinstance(x.get(k), str) and len(x.get(k)) > 80 for x in rows) and k not in ("title", "affiliateURL", "affiliateURLsp", "URL", "URLsp")]
        say(f"- 長い文の項目（説明文の候補）: {texty or 'なし'}")
        for k in ("series", "label", "director"):
            vals = [v.get("name") for x in rows for v in ((x.get("iteminfo") or {}).get(k) or []) if isinstance(v, dict)]
            say(f"- iteminfo.{k}: {sum(1 for x in rows if (x.get('iteminfo') or {}).get(k))}件にあり / 例 {vals[:5]}")
        say(f"- maker_product あり: {sum(1 for x in rows if x.get('maker_product'))}件 / 例 {[x.get('maker_product') for x in rows if x.get('maker_product')][:5]}")
        say(f"- review あり: {sum(1 for x in rows if x.get('review'))}件")

    # ログの取得が制限される環境でも読めるように、見出しごとに「注釈（notice）」としても出す（GitHub の check-run の注釈として読める）
    if os.environ.get("GITHUB_ACTIONS"):
        sections = []
        for text in lines:
            if text.lstrip("\n").startswith("## ") or not sections:
                sections.append([text])
            else:
                sections[-1].append(text)
        for block in sections[:10]:
            title = block[0].strip().lstrip("# ").strip()[:100]
            body = "\n".join(block[1:]).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::notice title={title}::{body}")

    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("### FANZA API の応答の形\n\n" + "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
