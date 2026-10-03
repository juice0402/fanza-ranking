"""ビルド結果（site/dist）の点検

`npm run build` のあとに実行します。ページが揃っているか、サイトに必ず必要な表記
（18歳確認・広告表記・FANZAクレジット・RTA）が全ページに残っているかを確かめます。
実行: python3 tests/verify_dist.py [distのパス]   （省略時は site/dist）
"""
import datetime
import glob
import json
import os
import re
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "site", "dist")
DATA = os.path.join(ROOT, "site", "src", "data", "new_releases.json")
ROUNDUPS = os.path.join(ROOT, "site", "src", "data", "roundups.json")

# 法令・規約の面で、どのページにも必ず必要な表記
REQUIRED_ON_EVERY_PAGE = {
    "RTAラベル": "RTA-5042-1996-1400-1577-RTA",
    "18歳確認": 'id="age-gate"',
    "広告表記": "アフィリエイト広告",
    "FANZAクレジット": "Powered by FANZA Webサービス",
}

problems = []
LD_BLOCK = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)  # 構造化データ（JSON-LD）


def check(name, cond, detail=""):
    print(("  ✅ " if cond else "  ❌ ") + name + (f"  → {detail}" if (detail and not cond) else ""))
    if not cond:
        problems.append(name)


def warn(name, ok, detail=""):
    """データしだいで起きうる注意点。失敗にはせず、見つけやすいように表示だけする"""
    print(("  ✅ " if ok else "  ⚠️ ") + name + (f"  → {detail}" if (detail and not ok) else ""))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def page_file(url_path):
    """URLのパス（/item/abc/）に対応する、dist内のファイルを返す"""
    rel = url_path.lstrip("/")
    if url_path.endswith("/") or rel == "":
        return os.path.join(DIST, rel, "index.html")
    return os.path.join(DIST, rel)


if not os.path.isdir(DIST):
    print(f"  ❌ {DIST} がありません。先に `npm run build`（site フォルダ）を実行してください")
    sys.exit(1)

raw = json.load(open(DATA, encoding="utf-8"))
valid = {}
for x in raw if isinstance(raw, list) else []:
    cid = str((x or {}).get("cid", "")).strip()
    if cid and str(x.get("title", "")).strip() and re.match(r"^\d{4}-\d{2}-\d{2}", str(x.get("date", ""))):
        valid.setdefault(cid, x)

print("■ ページが揃っている")
index_path = os.path.join(DIST, "index.html")
check("トップページ", os.path.isfile(index_path))
check("404ページ", os.path.isfile(os.path.join(DIST, "404.html")))
check("過去の作品 1ページ目", os.path.isfile(os.path.join(DIST, "archive", "1", "index.html")))
item_pages = glob.glob(os.path.join(DIST, "item", "*", "index.html"))
check("作品ページの数 = データの件数", len(item_pages) == len(valid), f"ページ {len(item_pages)} / データ {len(valid)}")
robots = os.path.join(DIST, "robots.txt")
check("robots.txt に Sitemap の行がある", os.path.isfile(robots) and "Sitemap:" in read(robots))

print("\n■ sitemap.xml")
sitemap_path = os.path.join(DIST, "sitemap.xml")
sm_paths = []  # sitemap に載っているURLのパス
lastmod_of = {}
check("sitemap.xml がある", os.path.isfile(sitemap_path))
if os.path.isfile(sitemap_path):
    sitemap_xml = read(sitemap_path)
    locs = re.findall(r"<loc>([^<]+)</loc>", sitemap_xml)
    rows = re.findall(r"<url><loc>([^<]+)</loc>(?:<lastmod>([^<]*)</lastmod>)?</url>", sitemap_xml)
    check("sitemap のすべてのURLが <url> の形で読める", len(rows) == len(locs) and len(locs) > 0, (len(rows), len(locs)))
    no_lastmod = [u for u, m in rows if not re.match(r"^\d{4}-\d{2}-\d{2}$", m or "")]
    check("sitemap のすべてのURLに lastmod（YYYY-MM-DD）がある", not no_lastmod, no_lastmod[:3])
    lastmod_of = {urlparse(u).path: m for u, m in rows}
    sm_paths = [urlparse(u).path for u in locs]
    wrong = [c for c in valid if lastmod_of.get(f"/item/{c}/") != str(valid[c].get("updated"))]
    check("sitemap の作品ページの lastmod が、データの updated と同じ", not wrong, wrong[:3])
    check("sitemap にトップがある", any(urlparse(u).path == "/" for u in locs))
    check("sitemap に全作品が入っている", all(any(f"/item/{c}/" in u for u in locs) for c in valid))
    missing = [u for u in locs if not os.path.isfile(page_file(urlparse(u).path))]
    check("sitemap のURLがすべて実在するページ", not missing, missing[:3])

print("\n■ 出演者・メーカーのページ")
check("出演者一覧ページ（/actress/）", os.path.isfile(os.path.join(DIST, "actress", "index.html")))
check("メーカー一覧ページ（/maker/）", os.path.isfile(os.path.join(DIST, "maker", "index.html")))
if os.path.isfile(sitemap_path):
    check("sitemap に出演者一覧・メーカー一覧がある", "/actress/" in sm_paths and "/maker/" in sm_paths)
    for kind in ("actress", "maker"):
        entity_pages = glob.glob(os.path.join(DIST, kind, "*", "index.html"))
        in_sitemap = [p for p in sm_paths if p.startswith(f"/{kind}/") and p != f"/{kind}/"]
        check(f"{kind} ページがすべて sitemap に入っている（{len(entity_pages)}ページ）", len(entity_pages) == len(in_sitemap), (len(entity_pages), len(in_sitemap)))

print("\n■ 週のまとめ記事")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_monday(day):
    try:
        return bool(DAY.match(day)) and datetime.date.fromisoformat(day).weekday() == 0
    except ValueError:
        return False


rounds_raw = json.load(open(ROUNDUPS, encoding="utf-8"))
rounds = {}  # 画面に出る記事（週の始まり → 記事）。サイト側の normalizeRoundups と同じ条件
for r in rounds_raw if isinstance(rounds_raw, list) else []:
    if isinstance(r, dict) and is_monday(str(r.get("week_start", ""))) and str(r.get("lead", "")).strip() and DAY.match(str(r.get("written", ""))):
        rounds.setdefault(r["week_start"], r)
weekly_index = os.path.join(DIST, "weekly", "index.html")
weekly_pages = glob.glob(os.path.join(DIST, "weekly", "*", "index.html"))
check("週のまとめの一覧ページ（/weekly/）がある", os.path.isfile(weekly_index))
check(f"記事ページの数 = データの本数（{len(rounds)}本）", len(weekly_pages) == len(rounds), f"ページ {len(weekly_pages)} / データ {len(rounds)}")
home_html = read(index_path) if os.path.isfile(index_path) else ""
if not rounds:
    check("記事が無いあいだは、一覧ページが noindex で、sitemap にもない", os.path.isfile(weekly_index) and 'name="robots" content="noindex' in read(weekly_index) and "/weekly/" not in sm_paths)
    check("記事が無いあいだは、トップ・フッターから /weekly/ へのリンクを出さない", 'href="/weekly/' not in home_html)
else:
    check("記事がある: 一覧ページは noindex でなく、sitemap にある", os.path.isfile(weekly_index) and 'name="robots" content="noindex' not in read(weekly_index) and "/weekly/" in sm_paths)
    newest = max(rounds)
    check("記事がある: トップに、最新の記事・一覧へのリンクがある", f'href="/weekly/{newest}/"' in home_html and 'href="/weekly/"' in home_html)
    for week, r in sorted(rounds.items()):
        page = os.path.join(DIST, "weekly", week, "index.html")
        if not os.path.isfile(page):
            check(f"{week} の記事ページがある", False)
            continue
        html = read(page)
        arts = []
        for b in LD_BLOCK.findall(html):
            try:
                arts.append(json.loads(b))
            except ValueError:
                pass
        art = [a for a in arts if isinstance(a, dict) and a.get("@type") == "Article"]
        check(f"{week}: 記事の構造化データ（Article）の公開日がデータの written と同じ", len(art) == 1 and art[0].get("datePublished") == r["written"], art[:1])
        check(f"{week}: sitemap に入っていて lastmod が公開日", f"/weekly/{week}/" in sm_paths and lastmod_of.get(f"/weekly/{week}/") == r["written"], lastmod_of.get(f"/weekly/{week}/"))
        picked = [q["cid"] for q in (r.get("picks") or []) if isinstance(q, dict) and q.get("cid") in valid]
        check(f"{week}: 注目の作品（{len(picked)}件）へのリンクが記事にある", all(f'href="/item/{c}/"' in html for c in picked), [c for c in picked if f'href="/item/{c}/"' not in html][:3])

print("\n■ 必須の表記が全ページにある")
# 404 を含む、すべてのページ（どのページも共通レイアウトを使うので、必須の表記は全部にあるはず）
pages = sorted(glob.glob(os.path.join(DIST, "**", "index.html"), recursive=True))
if os.path.isfile(os.path.join(DIST, "404.html")):
    pages.append(os.path.join(DIST, "404.html"))
for label, needle in REQUIRED_ON_EVERY_PAGE.items():
    lacking = [os.path.relpath(p, DIST) for p in pages if needle not in read(p)]
    check(f"{label}（{len(pages)}ページ）", not lacking, lacking[:3])
no_canonical = [os.path.relpath(p, DIST) for p in pages if 'rel="canonical"' not in read(p)]
check("canonical がある", not no_canonical, no_canonical[:3])


print("\n■ 検索エンジン向けの点検（SEO）")
LD = LD_BLOCK
CANON = re.compile(r'<link rel="canonical" href="([^"]+)"')
indexable = [p for p in pages if not p.endswith("404.html")]
rel = lambda p: os.path.relpath(p, DIST)

bad_ld, no_crumb, wrong_crumb = [], [], []
for p in indexable:
    html = read(p)
    try:
        blocks = [json.loads(b) for b in LD.findall(html)]
    except ValueError:
        bad_ld.append(rel(p))
        continue
    if not all(isinstance(b, dict) and b.get("@context") == "https://schema.org" and b.get("@type") for b in blocks):
        bad_ld.append(rel(p))
        continue
    is_home = os.path.abspath(p) == os.path.abspath(index_path)
    crumbs = [b for b in blocks if b.get("@type") == "BreadcrumbList"]
    if is_home:
        if not any(b.get("@type") == "WebSite" for b in blocks):
            bad_ld.append(rel(p) + "（WebSite がない）")
        continue
    if not crumbs:
        no_crumb.append(rel(p))
        continue
    canon = CANON.search(html)
    items = crumbs[0].get("itemListElement") or []
    if not canon or not items or items[-1].get("item") != canon.group(1) or [i.get("position") for i in items] != list(range(1, len(items) + 1)):
        wrong_crumb.append(rel(p))
check(f"構造化データ（JSON-LD）が正しいJSON（{len(indexable)}ページ）", not bad_ld, bad_ld[:3])
check("トップ以外の全ページにパンくずの構造化データがある", not no_crumb, no_crumb[:3])
check("パンくずの最後のURLが、そのページの canonical と同じ・順番が正しい", not wrong_crumb, wrong_crumb[:3])

no_h1 = [rel(p) for p in pages if len(re.findall(r"<h1[\s>]", read(p))) != 1]
check("すべてのページに h1 がちょうど1つ", not no_h1, no_h1[:3])
url_of = lambda p: "/" + rel(p)[: -len("index.html")]  # dist 内のファイル → URLのパス
noindex = [p for p in indexable if 'name="robots" content="noindex' in read(p)]
check("sitemap に載っているページが noindex になっていない", not [rel(p) for p in noindex if url_of(p) in sm_paths], [rel(p) for p in noindex if url_of(p) in sm_paths][:3])
not_listed = [rel(p) for p in indexable if p not in noindex and url_of(p) not in sm_paths]
check("noindex でないページは、すべて sitemap に載っている", not not_listed, not_listed[:3])

broken = {}
for p in pages:
    for h in set(re.findall(r'href="(/[^"#?]*)', read(p))):
        if h.startswith("//"):
            continue
        if not os.path.isfile(page_file(h)):
            broken.setdefault(h, rel(p))
check("サイト内のリンク先がすべて実在する（リンク切れなし）", not broken, list(broken.items())[:3])

titles, descs = {}, {}
for p in indexable:
    html = read(p)
    t = re.search(r"<title>(.*?)</title>", html, re.S)
    d = re.search(r'<meta name="description" content="([^"]*)"', html)
    titles.setdefault(t.group(1) if t else "", []).append(rel(p))
    descs.setdefault(d.group(1) if d else "", []).append(rel(p))
dup_titles = {t: ps for t, ps in titles.items() if len(ps) > 1}
no_desc = descs.get("", [])
warn("タイトルがページごとに違う（重複があっても失敗にはしない）", not dup_titles, list(dup_titles.items())[:2])
warn("説明文（description）がすべてのページにある", not no_desc, no_desc[:3])

if problems:
    print("\n失敗:", problems)
    sys.exit(1)
print("\n=== ビルド結果 OK ===")
