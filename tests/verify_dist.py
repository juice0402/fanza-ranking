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
        check(f"{week}: 本数は「当サイトで紹介した」数と分かる書き方（FANZA全体の発売本数と誤解されない）", html.count("当サイトで紹介した") >= 2 and "FANZA全体の発売本数ではありません" in html, html.count("当サイトで紹介した"))
        picked = [q["cid"] for q in (r.get("picks") or []) if isinstance(q, dict) and q.get("cid") in valid]
        check(f"{week}: 注目の作品（{len(picked)}件）へのリンクが記事にある", all(f'href="/item/{c}/"' in html for c in picked), [c for c in picked if f'href="/item/{c}/"' not in html][:3])

print("\n■ 作品ページの表示（サンプル画像の拡大・カード）")
check("拡大表示のスクリプト（lightbox.js）が公開されている", os.path.isfile(os.path.join(DIST, "lightbox.js")))
bad_samples = []
for cid, x in valid.items():
    page = os.path.join(DIST, "item", cid, "index.html")
    if not os.path.isfile(page):
        continue
    html = read(page)
    shown = min(len([u for u in (x.get("sample_images") or []) if u]), 8)  # 画面に出すのは最大8枚
    links = len(re.findall(r'class="sample-link"', html))
    has_dialog = 'id="lightbox"' in html
    has_script = 'src="/lightbox.js"' in html
    if shown:
        if not (links == shown and has_dialog and has_script):
            bad_samples.append((cid, shown, links, has_dialog, has_script))
    elif links or has_dialog:
        bad_samples.append((cid, 0, links, has_dialog, has_script))
check("サンプル画像のある作品ページに、拡大表示の部品（リンク・ダイアログ・スクリプト）が揃っている", not bad_samples, bad_samples[:3])
with_spine = [os.path.relpath(p, DIST) for p in glob.glob(os.path.join(DIST, "**", "*.html"), recursive=True) if 'class="spine"' in read(p)]
check("カードに、画像をさえぎるメーカーの縦帯（spine）が出ていない", not with_spine, with_spine[:3])

print("\n■ お気に入り・発売日カレンダー")
all_pages = sorted(glob.glob(os.path.join(DIST, "**", "index.html"), recursive=True))
if os.path.isfile(os.path.join(DIST, "404.html")):
    all_pages.append(os.path.join(DIST, "404.html"))
check("お気に入りのスクリプト（favorites.js）が公開されている", os.path.isfile(os.path.join(DIST, "favorites.js")))
no_fav_parts = [os.path.relpath(p, DIST) for p in all_pages if 'src="/favorites.js"' not in read(p) or 'href="/favorites/"' not in read(p)]
check(f"全ページに、お気に入りへのリンクとスクリプトがある（{len(all_pages)}ページ）", not no_fav_parts, no_fav_parts[:3])
for label, path in (("お気に入り（/favorites/）", "/favorites/"), ("発売日カレンダーの説明（/calendar/）", "/calendar/")):
    f = page_file(path)
    ok = os.path.isfile(f)
    check(f"{label}ページがある", ok)
    if ok:
        check(f"{label}は noindex で、sitemap に入っていない（見る人ごとの内容・使い方だけのページ）", 'name="robots" content="noindex' in read(f) and path not in sm_paths)
fav_page = page_file("/favorites/")
if os.path.isfile(fav_page):
    check("お気に入りページに、表示先（#fav-root）がある", 'id="fav-root"' in read(fav_page))
check("トップに、お気に入りのお知らせ欄（#fav-banner）がある（最初は隠れている）", bool(re.search(r'<a id="fav-banner"[^>]*\bhidden\b', home_html)))

# 索引: お気に入りの出演者・メーカーの新作を、ブラウザ側で探すための小さなJSON
fav_index_path = os.path.join(DIST, "data", "favorites-index.json")
check("お気に入りの索引（/data/favorites-index.json）がある", os.path.isfile(fav_index_path))
if os.path.isfile(fav_index_path):
    try:
        fav_index = json.loads(read(fav_index_path))
    except ValueError:
        fav_index = None
    check("索引が正しいJSONで、generated（日付）と items（配列）がある", isinstance(fav_index, dict) and DAY.match(str(fav_index.get("generated", ""))) and isinstance(fav_index.get("items"), list), str(fav_index)[:80])
    if isinstance(fav_index, dict) and isinstance(fav_index.get("items"), list):
        rows = fav_index["items"]
        check("索引のすべての項目が、短い名前（c,t,d,a,m,i）だけで、データにある作品", all(isinstance(r, dict) and set(r) == {"c", "t", "d", "a", "m", "i"} and r["c"] in valid and DAY.match(str(r["d"])) and isinstance(r["a"], list) for r in rows), [r for r in rows if not (isinstance(r, dict) and set(r) == {"c", "t", "d", "a", "m", "i"})][:1])
        check("索引は発売日の新しい順", [r["d"] for r in rows] == sorted((r["d"] for r in rows), reverse=True))
        warn("索引に作品が1件以上ある", bool(rows))
        check("索引の大きさが 300KB 以内（毎回ダウンロードされるため）", os.path.getsize(fav_index_path) <= 300 * 1024, os.path.getsize(fav_index_path))

# 発売日カレンダー（.ics）
def unfold_ics(text):
    return re.sub(r"\r\n[ \t]", "", text)


def ics_problems(path):
    """.ics の形（行の長さ・予定の対応・題名にタイトルが入っていない・予定の日付）の問題を、文章で返す"""
    raw_bytes = open(path, "rb").read()
    text = raw_bytes.decode("utf-8")
    found = []
    if not (text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")):
        found.append("先頭・末尾の形")
    if "\n" in text.replace("\r\n", ""):
        found.append("改行が CRLF でない")
    if [l for l in text.split("\r\n") if len(l.encode("utf-8")) > 75]:
        found.append("75バイトを超える行")
    body = unfold_ics(text).replace("\r\n", "\n")  # 行の終わりの CR を除いて、正規表現で読みやすくする
    if body.count("BEGIN:VEVENT") != body.count("END:VEVENT") or body.count("BEGIN:VALARM") != body.count("END:VALARM"):
        found.append("BEGIN と END の数が合わない")
    uids = re.findall(r"^UID:(.+)$", body, re.M)
    if len(uids) != len(set(uids)):
        found.append("UID の重複")
    summaries = re.findall(r"^SUMMARY:(.*)$", body, re.M)
    if len(summaries) != body.count("BEGIN:VEVENT") or not all(re.match(r"^【発売】.+の新作$", t) for t in summaries):
        found.append("題名が「【発売】○○の新作」の形でない")
    cids = [u.split("@")[0] for u in uids]
    if not all(c in valid for c in cids):
        found.append("データに無い品番の予定")
    titles_in_summary = [t for t in summaries if any(x["title"].strip() and x["title"].strip() in t for x in valid.values())]
    if titles_in_summary:
        found.append("題名に作品タイトルが入っている")
    starts = re.findall(r"^DTSTART;VALUE=DATE:(\d{8})$", body, re.M)
    if len(starts) != len(uids):
        found.append("日付のない予定")
    return found


upcoming_ics = os.path.join(DIST, "calendar", "upcoming.ics")
check("すべての発売予定のカレンダー（/calendar/upcoming.ics）がある", os.path.isfile(upcoming_ics))
if os.path.isfile(upcoming_ics):
    probs = ics_problems(upcoming_ics)
    check("upcoming.ics の形が正しい（行の長さ・題名にタイトルが入らない・予定の数・日付）", not probs, probs)
    warn("upcoming.ics に予定が1件以上ある", "BEGIN:VEVENT" in read(upcoming_ics))
page_host = None
m = re.search(r'<link rel="canonical" href="https?://([^/"]+)', home_html)
if m:
    page_host = m.group(1)
for kind, label in (("actress", "出演者"), ("maker", "メーカー")):
    entity_pages = glob.glob(os.path.join(DIST, kind, "*", "index.html"))
    slugs = {os.path.basename(os.path.dirname(p)) for p in entity_pages}
    ics_files = {os.path.basename(p)[:-4] for p in glob.glob(os.path.join(DIST, "calendar", kind, "*.ics"))}
    check(f"{label}ページ（{len(slugs)}）と、{label}ごとのカレンダー（{len(ics_files)}）が1対1", slugs == ics_files, (sorted(slugs - ics_files)[:2], sorted(ics_files - slugs)[:2]))
    bad_ics = [slug for slug in sorted(ics_files) if ics_problems(os.path.join(DIST, "calendar", kind, slug + ".ics"))]
    check(f"{label}ごとのカレンダーの形が正しい", not bad_ics, bad_ics[:3])
    no_btn = []
    for p in entity_pages:
        html = read(p)
        slug = os.path.basename(os.path.dirname(p))
        link = f'href="webcal://{page_host}/calendar/{kind}/{slug}.ics"'
        if 'data-fav-type="%s"' % kind not in html or link not in html:
            no_btn.append(slug)
    check(f"{label}ページに、☆ボタンと、そのページ専用のカレンダーのリンクがある", not no_btn, no_btn[:3])
no_work_btn = [cid for cid in valid if os.path.isfile(os.path.join(DIST, "item", cid, "index.html")) and 'data-fav-type="work"' not in read(os.path.join(DIST, "item", cid, "index.html"))]
check("すべての作品ページに、作品の☆ボタンがある", not no_work_btn, no_work_btn[:3])
cal_page = page_file("/calendar/")
if os.path.isfile(cal_page):
    check("カレンダーの説明ページに、購読リンク（webcal）と、アドレスがある", f'href="webcal://{page_host}/calendar/upcoming.ics"' in read(cal_page) and f"https://{page_host}/calendar/upcoming.ics" in read(cal_page))

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
# Search Console の所有権の確認コード（config.js の値）が、全ページの <head> に出ている（確認はトップページで行われる）
cfg = read(os.path.join(ROOT, "site", "src", "config.js"))
m = re.search(r"GOOGLE_SITE_VERIFICATION\s*=\s*'([^']*)'", cfg)
if m and m.group(1):
    meta = f'<meta name="google-site-verification" content="{m.group(1)}"'
    lacking = [os.path.relpath(p, DIST) for p in pages if not p.endswith("404.html") and meta not in read(p)]
    check("Search Console の所有権の確認コードが、全ページにある", not lacking, lacking[:3])
else:
    warn("Search Console の所有権の確認コードが設定されている（config.js の GOOGLE_SITE_VERIFICATION）", False)
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
