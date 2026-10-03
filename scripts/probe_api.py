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

    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("### FANZA API の応答の形\n\n" + "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
