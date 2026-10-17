"""公開したページを、検索エンジンに知らせる（IndexNow。運営者の希望「本番に公開するたびに、中身の変わったページを検索エンジンへ自動で知らせて」。2026-10-17）。

知らせる先は api.indexnow.org の1か所（Bing・Yandex・Naver・Seznam・Yep で共有される。Yahoo!（米国）・DuckDuckGo の多くは Bing の結果を使う）。
Google は IndexNow に入っていないので、いまのまま sitemap と Search Console で見つけてもらう。
鍵は公開してよい値で、site/public/<鍵>.txt（中身は鍵だけ）に置いてある。秘密情報は使わない。

本番（main）の公開のときだけ、.github/workflows/deploy.yml が動かす:
  python3 scripts/indexnow.py prepare --out <えらんだページの書き出し先>
      アップロードの前。sitemap.xml のページと「最後に変わった日」（lastmod）を、本番にある前回の記録
      （/indexnow-pages.json）とくらべて、知らせるページをえらぶ。今回の記録を site/dist に置く（サイトといっしょに公開。
      リポジトリにはコミットしない＝main にコミットを足さない）
  python3 scripts/indexnow.py send --list <えらんだページ> --uploaded <アップロード済みの印>
      アップロードが済んだあと（印があるときだけ）。えらんだページを1万件ずつ知らせる

えらび方（運営者の「ランキングの数字が変わっただけのページを、毎日ぜんぶ送らない。送るのは、新しいページと、
コメントやまとめ記事が入ったページが中心」）。sitemap に無いページ（noindex）は送らない:
  - 前回の記録に無いページ（コメントが付いて検索エンジンに出すようになった作品ページ・新しい週のまとめなど）→ すぐ
  - lastmod が変わった作品ページ（lastmod はコメントを書いた日）・週のまとめ・このサイトについて・
    月のまとめ記事が新しく入った月のページ → すぐ
  - lastmod が変わった、そのほかのページ（一覧・ランキング・セールなど。並びや数字が毎日変わる）→ 前に知らせてから
    7日たったら（それまでは前の記録のまま持ち越すので、7日たつと知らせる）
知らせに失敗しても、公開は止めない（いつも 0 で終わる。結果は GitHub の注記に1行）。
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_URL = re.search(r"export const SITE_URL = '([^']+)'", open(os.path.join(ROOT, "site", "src", "config.js"), encoding="utf-8").read()).group(1)
DIST = os.environ.get("DIST_DIR", os.path.join(ROOT, "site", "dist"))
PUBLIC = os.path.join(ROOT, "site", "public")
MONTHLY = os.path.join(ROOT, "site", "src", "data", "monthly.json")
LIVE_URL = os.environ.get("LIVE_URL", SITE_URL)                       # 前回の記録を読む先（テストでは差しかえる）
ENDPOINT = os.environ.get("INDEXNOW_ENDPOINT", "https://api.indexnow.org/indexnow")
RECORD = "indexnow-pages.json"  # 前回の記録（サイトのいちばん上に、サイトといっしょに公開する）
BATCH = 10_000                  # 1回に送れるのは1万件まで（IndexNow の決まり）
HOLD_DAYS = 7                   # 一覧・ランキングなどは、前に知らせてから7日たつまで待つ
RETRY_WAIT = float(os.environ.get("INDEXNOW_RETRY_WAIT", "10"))
JST = datetime.timezone(datetime.timedelta(hours=9))
# lastmod が変わったら、すぐ知らせるページ（中身＝コメント・記事が変わったときに lastmod が変わるもの）
NOW_PATTERN = re.compile(r"^/(?:[a-z]+/)?item/[^/]+/$|^/weekly/|^/about/$")
MONTH_PAGE = re.compile(r"^/month/(\d{4}-\d{2})/$")


def notice(msg, level="notice"):
    """GitHub の注記（1行）と、実行結果の要約"""
    print(f"::{level} title=IndexNow（検索エンジンへのお知らせ）::{msg}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### {'🔔' if level == 'notice' else '⚠️'} IndexNow\n- {msg}\n")


def today_jst():
    return datetime.datetime.now(JST).strftime("%Y-%m-%d")


def days_between(a, b):
    try:
        return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days
    except ValueError:
        return HOLD_DAYS  # 日付が読めない記録は、待たない


def read_sitemap(path):
    """sitemap.xml のページ（サイトの中の道 → lastmod。lastmod の無いページは ''）"""
    xml = open(path, encoding="utf-8").read()
    pages = {}
    for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>\s*([^<\s]+)\s*</loc>", block)
        if not loc or not loc.group(1).startswith(SITE_URL + "/"):
            continue
        mod = re.search(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", block)
        pages[loc.group(1)[len(SITE_URL):]] = mod.group(1)[:10] if mod else ""
    return pages


def monthly_written():
    """月のまとめ記事のある月のページ → 記事を書いた日"""
    try:
        rows = json.load(open(MONTHLY, encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {f"/month/{r['month']}/": str(r.get("written", ""))[:10] for r in rows if isinstance(r, dict) and r.get("month")}


def valid_record(data):
    return (isinstance(data, dict) and isinstance(data.get("pages"), dict)
            and all(isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) for x in v) for v in data["pages"].values()))


def fetch_record(url, tries=3, wait=None):
    """本番にある前回の記録。('ok', 記録) ／ ('none', None)＝まだ無い（はじめて） ／ ('error', 理由)＝読めない"""
    wait = RETRY_WAIT if wait is None else wait
    reason = ""
    for i in range(tries):
        try:
            req = urllib.request.Request(f"{url}/{RECORD}?cb={int(time.time())}", headers={"Cache-Control": "no-cache", "User-Agent": "fanza-ranking-indexnow"})
            with urllib.request.urlopen(req, timeout=30) as res:
                data = json.loads(res.read().decode("utf-8"))
            if valid_record(data):
                return "ok", data["pages"]
            return "error", "前回の記録の形がおかしい"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "none", None
            reason = f"HTTP {e.code}"
        except (urllib.error.URLError, OSError, ValueError) as e:
            reason = str(getattr(e, "reason", e))[:120]
        if i < tries - 1:
            time.sleep(wait)
    return "error", reason


def choose(now, prev, today, written):
    """知らせるページと、今回の記録をえらぶ。
    now: sitemap（道 → lastmod）／ prev: 前回の記録（道 → [lastmod, 知らせた日]。はじめては None）／ written: 月のまとめ記事を書いた日
    返り値: (知らせる道の一覧, 今回の記録, 内訳 {'new': 新しい, 'content': 作品・記事, 'list': 一覧など})"""
    send, record, count = [], {}, {"new": 0, "content": 0, "list": 0}
    for path, mod in sorted(now.items()):
        old = None if prev is None else prev.get(path)
        if old is None:
            kind = "new"
        elif old[0] == mod:
            record[path] = old
            continue
        else:
            m = MONTH_PAGE.match(path)
            if NOW_PATTERN.match(path) or (m and written.get(path, "") > old[1]):
                kind = "content"
            elif days_between(old[1], today) >= HOLD_DAYS:
                kind = "list"
            else:
                record[path] = old  # 7日たつまで持ち越す（前の lastmod のままなので、7日たったら知らせる）
                continue
        send.append(path)
        record[path] = [mod, today]
        count[kind] += 1
    return send, record, count


def breakdown(count, first):
    if first:
        return "はじめてなので sitemap の全部"
    names = {"new": "新しいページ", "content": "作品・まとめ記事", "list": "一覧・ランキングなど"}
    return "・".join(f"{names[k]} {count[k]:,}" for k in names if count[k]) or "なし"


def prepare(out, today=None, live_url=None):
    today = today or today_jst()
    sitemap = os.path.join(DIST, "sitemap.xml")
    if not os.path.exists(sitemap):
        notice("sitemap.xml が無いので、えらびませんでした", "warning")
        return 0
    now = read_sitemap(sitemap)
    status, prev = fetch_record(live_url or LIVE_URL)
    if status == "error":
        # 前回が分からないときは、全部を送り直さない（同じページを何千件も送らないように）。今回の状態を記録して、次から続ける
        send, record, count = [], {p: [m, today] for p, m in now.items()}, {}
        note = f"前回の記録を読めなかったので、今回は知らせません（{prev}）"
    else:
        send, record, count = choose(now, prev if status == "ok" else None, today, monthly_written())
        note = breakdown(count, status == "none")
    with open(os.path.join(DIST, RECORD), "w", encoding="utf-8") as f:
        json.dump({"v": 1, "updated": today, "pages": record}, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"urls": [SITE_URL + p for p in send], "note": note, "total": len(now)}, f, ensure_ascii=False)
    print(f"知らせるページ {len(send):,}件（{note}）／ sitemap の全 {len(now):,}件")
    return 0


def find_key():
    """site/public/<鍵>.txt（名前が英数字32文字で、中身が鍵だけのファイル）"""
    keys = []
    for p in glob.glob(os.path.join(PUBLIC, "*.txt")):
        name = os.path.basename(p)[:-4]
        if re.fullmatch(r"[A-Za-z0-9]{32}", name) and open(p, encoding="utf-8").read().strip() == name:
            keys.append(name)
    if len(keys) != 1:
        raise RuntimeError(f"鍵のファイルが {len(keys)} 個あります（1個だけにしてください）")
    return keys[0]


def post(urls, key, endpoint=None):
    """1回ぶんを送る。返り値: (返事の番号, 本文の頭)。つながらなければ (0, 理由)"""
    body = json.dumps({"host": SITE_URL.split("://", 1)[1], "key": key, "keyLocation": f"{SITE_URL}/{key}.txt", "urlList": urls}).encode("utf-8")
    req = urllib.request.Request(endpoint or ENDPOINT, data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "fanza-ranking-indexnow"})
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return res.status, res.read(200).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(200).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        return 0, str(getattr(e, "reason", e))[:120]


def send(list_path, uploaded):
    if not uploaded or not os.path.exists(uploaded):
        print("本番に公開されていないので、知らせません")
        return 0
    try:
        data = json.load(open(list_path, encoding="utf-8"))
        urls = [u for u in data["urls"] if u.startswith(SITE_URL + "/")]
    except (OSError, ValueError, KeyError, TypeError):
        notice("知らせるページをえらべていなかったので、知らせませんでした", "warning")
        return 0
    note = str(data.get("note", ""))
    if not urls:
        if "読めなかった" in note:
            notice(note, "warning")
        else:
            notice("変わったページが無いので、知らせませんでした")
        return 0
    try:
        key = find_key()
    except RuntimeError as e:
        notice(f"知らせられませんでした: {e}", "warning")
        return 0
    batches = [urls[i:i + BATCH] for i in range(0, len(urls), BATCH)]
    codes, sent, why = [], 0, ""
    for b in batches:
        code, text = post(b, key)
        if code == 0 or code == 429 or code >= 500:  # つながらない・混んでいる → 少し待って1回だけやり直す
            time.sleep(RETRY_WAIT)
            code, text = post(b, key)
        codes.append(code)
        if code in (200, 202):
            sent += len(b)
        else:
            why = text.strip().replace("\n", " ")[:120]
            break
    how = f"1万件ずつ{len(batches)}回・" if len(batches) > 1 else ""
    ret = "・".join(str(c) if c else "つながらない" for c in codes)
    if sent == len(urls):
        notice(f"{sent:,}件を知らせました（{note}。{how}返事 {ret}）")
    else:
        notice(f"{len(urls):,}件のうち {sent:,}件だけ知らせました（{how}返事 {ret}。{why}）", "warning")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="公開したページを IndexNow で検索エンジンに知らせる")
    sub = ap.add_subparsers(dest="cmd")
    p1 = sub.add_parser("prepare")
    p1.add_argument("--out", required=True)
    p2 = sub.add_parser("send")
    p2.add_argument("--list", required=True)
    p2.add_argument("--uploaded", required=True)
    a = ap.parse_args(argv)
    if a.cmd is None:
        ap.print_help()
        return 2
    try:
        return prepare(a.out) if a.cmd == "prepare" else send(a.list, a.uploaded)
    except Exception as e:  # 知らせに失敗しても、公開は止めない
        notice(f"うまく動きませんでした（{type(e).__name__}: {str(e)[:120]}）", "warning")
        return 0


if __name__ == "__main__":
    sys.exit(main())
