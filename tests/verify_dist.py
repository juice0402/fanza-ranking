"""ビルド結果（site/dist）の点検

`npm run build` のあとに実行します。ページが揃っているか、サイトに必ず必要な表記
（18歳確認・広告表記・FANZAクレジット・RTA）が全ページに残っているかを確かめます。
実行: python3 tests/verify_dist.py [distのパス]   （省略時は site/dist）
"""
import datetime
import glob
import html as htmllib
import json
import os
import re
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "site", "dist")
DATA = os.path.join(ROOT, "site", "src", "data", "new_releases.json")
ROUNDUPS = os.path.join(ROOT, "site", "src", "data", "roundups.json")
ACTRESSES = os.path.join(ROOT, "site", "src", "data", "actresses.json")
RANKING = os.path.join(ROOT, "site", "src", "data", "ranking.json")

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


def tags(text, name):
    """<name ...> タグを、属性の辞書（値はHTMLの記号を元に戻したもの）にして、出てきた順に返す"""
    out = []
    for m in re.finditer(r"<%s\b((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>" % name, text):
        attrs = {}
        for a in re.finditer(r"""([A-Za-z_:][-A-Za-z0-9_:.]*)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?""", m.group(1)):
            val = next((g for g in a.groups()[1:] if g is not None), "")
            attrs[a.group(1)] = htmllib.unescape(val)
        out.append(attrs)
    return out


def has_class(attrs, name):
    return name in attrs.get("class", "").split()


def fanza_https(url, hosts):
    """https で、ホストが hosts のどれか（またはそのサブドメイン）のURLか"""
    text = str(url or "")
    # ホストのあとは、ポート番号（数字）か、パス・?・#・終わりだけ。ユーザー名の欄に FANZA のホストを入れて見せかける形（https://dmm.co.jp:@別のサイト/）や、空白・バックスラッシュを含む形は通さない
    m = re.match(r"^https://([A-Za-z0-9.\-]+)(?::\d{1,5})?(?:[/?#]|$)", text)
    host = m.group(1).lower() if m else ""
    return bool(m) and not re.search(r"[\\\s\x00-\x1f\x7f]", text) and any(host == h or host.endswith("." + h) for h in hosts)


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

print("\n■ 作品ページの表示（サンプル画像の拡大・カード）")
check("拡大表示のスクリプト（lightbox.js）が公開されている", os.path.isfile(os.path.join(DIST, "lightbox.js")))
bad_samples = []
for cid, x in valid.items():
    page = os.path.join(DIST, "item", cid, "index.html")
    if not os.path.isfile(page):
        continue
    html = read(page)
    shown = min(len([u for u in (x.get("sample_images") or []) if u]), 8)  # 画面に出すのは最大8枚
    if fanza_https(x.get("sample_movie"), ["dmm.co.jp"]) and str(x.get("image_url") or "").strip():
        shown += 1  # サンプル動画がある作品は、サンプル画像の下に、パッケージ写真の欄が別にある（拡大表示のリンクはその1つぶん増える）
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

# ---------- サンプル動画・出演者プロフィール・出演者検索・売れ筋 ----------
JST_TODAY = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d")
DMM = ["dmm.co.jp"]
FANZA_LINK = ["fanza.co.jp", "dmm.co.jp"]
SPONSORED = {"sponsored", "nofollow", "noopener", "noreferrer"}


def load_json(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def age_on(birthday, today):
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(birthday or ""))
    if not m:
        return None
    y, mo, d = map(int, m.groups())
    ty, tmo, td = map(int, today.split("-"))
    age = ty - y - ((tmo, td) < (mo, d))
    return age if 18 <= age <= 80 else None


all_html = sorted(glob.glob(os.path.join(DIST, "**", "*.html"), recursive=True))  # 404 を含む、すべてのHTML

print("\n■ サンプル動画（作品ページ）")
check("動画の枠の縮小スクリプト（movie.js）が公開されている", os.path.isfile(os.path.join(DIST, "movie.js")))
bad_movie = []
movie_count = 0
for cid, x in valid.items():
    page = os.path.join(DIST, "item", cid, "index.html")
    if not os.path.isfile(page):
        continue
    text = read(page)
    iframes = tags(text, "iframe")
    movie = str(x.get("sample_movie") or "").strip()
    cover = str(x.get("image_url") or "").strip()
    sample_links = [t for t in tags(text, "a") if has_class(t, "sample-link")]
    cover_links = [t for t in sample_links if t.get("data-label") == "パッケージ画像"]
    if fanza_https(movie, DMM):
        movie_count += 1
        frame = iframes[0] if iframes else {}
        problems_here = []
        if len(iframes) != 1 or frame.get("src") != movie:
            problems_here.append("動画の枠(iframe)が1つで、動画のURLと同じではない")
        if frame.get("width") != "476" or frame.get("height") != "306":
            problems_here.append("枠のサイズが 476x306 ではない")
        if 'src="/movie.js"' not in text:
            problems_here.append("movie.js を読み込んでいない")
        if any(has_class(t, "detail-cover") for t in tags(text, "img")):
            problems_here.append("動画があるのに、表紙が上に出ている")
        # パッケージ写真は、サンプル画像の並びには混ぜず、その下の別の欄に、大きく出す（拡大表示では最後に送られる）
        has_pkg_section = 'id="package-title"' in text and ">パッケージ写真</h2>" in text
        after_samples = 'id="samples-title"' not in text or text.find('id="samples-title"') < text.find('id="package-title"')
        pkg_link_ok = len(cover_links) == 1 and sample_links[-1] is cover_links[0] and cover_links[0].get("href") == cover
        if cover and not (has_pkg_section and after_samples and pkg_link_ok and any(has_class(t, "package-img") for t in tags(text, "img"))):
            problems_here.append("パッケージ写真の欄（サンプル画像の下・大きな画像）がない")
        if cover and len(sample_links) - len(cover_links) != min(len([u for u in (x.get("sample_images") or []) if u]), 8):
            problems_here.append("サンプル画像の並びに、パッケージ画像が混ざっている（サンプル画像の枚数と合わない）")
        if not cover and "パッケージ写真" in text:
            problems_here.append("パッケージ画像が無いのに、パッケージ写真の欄がある")
        if x.get("url") and not any(has_class(t, "movie-link") and fanza_https(t.get("href"), FANZA_LINK) for t in tags(text, "a")):
            problems_here.append("「FANZAで見る」の代わりのリンクがない")
        if problems_here:
            bad_movie.append((cid, problems_here))
    else:
        problems_here = []
        if iframes:
            problems_here.append("動画が無いのに iframe がある")
        if cover and not any(has_class(t, "detail-cover") for t in tags(text, "img")):
            problems_here.append("動画が無いのに、表紙が上に出ていない")
        if cover_links or "パッケージ写真" in text:
            problems_here.append("動画が無いのに、パッケージ写真の欄がある（表紙が上にあるので、欄は作らない）")
        if 'src="/movie.js"' in text:
            problems_here.append("動画が無いのに movie.js を読み込んでいる")
        if problems_here:
            bad_movie.append((cid, problems_here))
check(f"動画がある作品（{movie_count}件）は動画を表紙の場所に出し、パッケージ写真をサンプル画像の下の別の欄に大きく出している／動画が無い作品は、これまでどおり表紙", not bad_movie, bad_movie[:3])
foreign_frames = []
for pth in all_html:
    for t in tags(read(pth), "iframe"):
        if not fanza_https(t.get("src"), DMM):
            foreign_frames.append((os.path.relpath(pth, DIST), t.get("src")))
check("どのページの iframe も、FANZA(DMM)の https のURLだけ", not foreign_frames, foreign_frames[:3])

print("\n■ 出演者の顔写真・プロフィール")
act_raw = load_json(ACTRESSES) if os.path.isfile(ACTRESSES) else None
profiles = {}
if isinstance(act_raw, dict):
    for r in act_raw.get("actresses", []):
        if isinstance(r, dict) and str(r.get("name", "")).strip() and r.get("fetched") and str(r["name"]).strip() not in profiles:
            profiles[str(r["name"]).strip()] = r
bad_faces = []
for pth in all_html:
    for t in tags(read(pth), "img"):
        if has_class(t, "face-img") and not fanza_https(t.get("src"), DMM):
            bad_faces.append((os.path.relpath(pth, DIST), t.get("src")))
check("顔写真（face-img）は、すべて FANZA(DMM) の https の画像", not bad_faces, bad_faces[:3])

actress_pages = glob.glob(os.path.join(DIST, "actress", "*", "index.html"))
page_name_slug = {}  # 出演者ページの「名前 → ページの識別子」（出演者検索の索引と突き合わせる）
bad_profile_pages = []
for pth in actress_pages:
    text = read(pth)
    m = re.search(r'<h1 class="hero-title">(.*?)</h1>', text, re.S)
    h1_text = htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""  # 見出しが <span> で分かれていても読む
    name = h1_text[: -len("の新作・出演作品")] if h1_text.endswith("の新作・出演作品") else ""
    if name:
        page_name_slug[name] = os.path.basename(os.path.dirname(pth))
    prof = profiles.get(name)
    btn_text = f"FANZAで{name}の全作品を見る"
    btns = [t for t in tags(text, "a") if has_class(t, "btn") and has_class(t, "btn-hot")]
    list_url = str((prof or {}).get("list_url") or "")
    here = []
    if not name:
        here.append("見出しから名前を読めない")
    elif prof and fanza_https(list_url, FANZA_LINK):
        link = [t for t in btns if t.get("href") == list_url]
        if not link or not SPONSORED <= set(link[0].get("rel", "").split()) or link[0].get("target") != "_blank" or btn_text not in text:
            here.append("「FANZAで全作品を見る」のリンクが無い・属性が足りない")
    elif btn_text in text:
        here.append("リンク先が無い人なのに「FANZAで全作品を見る」が出ている")
    faces = [t for t in tags(text, "img") if has_class(t, "face-img")]
    if prof and (prof.get("image_large") or prof.get("image_small")) and not faces:
        here.append("顔写真があるはずなのに出ていない")
    if not prof and faces:
        here.append("プロフィールが無い人に顔写真が出ている")
    age = age_on(str((prof or {}).get("birthday") or ""), JST_TODAY)
    has_age_row = '<dt class="spec-term">年齢</dt>' in text
    if has_age_row != (age is not None):
        here.append(f"年齢の行の有無が、データと合わない（行={has_age_row}・年齢={age}）")
    for label, key in (("身長", "height"), ("バスト", "bust"), ("ウエスト", "waist"), ("ヒップ", "hip")):
        has_row = f'<dt class="spec-term">{label}</dt>' in text
        have = isinstance((prof or {}).get(key), int)
        if has_row != have:
            here.append(f"{label}の行の有無が、データと合わない")
    if here:
        bad_profile_pages.append((name or os.path.relpath(pth, DIST), here))
check(f"出演者ページ（{len(actress_pages)}ページ）: 顔写真・年齢/身長/サイズの行・FANZAの全作品ボタンが、データのとおりに出ている", not bad_profile_pages, bad_profile_pages[:3])

# 個人情報: 生年月日そのものを、公開するファイルに出さない（出すのは、計算した年齢だけ）
births = {str(r.get("birthday")) for r in profiles.values() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("birthday") or ""))}
leaks = []
json_leaks = []
if births:
    pattern = re.compile("|".join(re.escape(b) for b in sorted(births)))
    for pth in glob.glob(os.path.join(DIST, "**", "*"), recursive=True):
        if os.path.isfile(pth) and pth.endswith((".html", ".json", ".xml", ".ics", ".js", ".txt")):
            if pattern.search(read(pth)):
                leaks.append(os.path.relpath(pth, DIST))
check(f"生年月日（{len(births)}件）が、公開ファイルのどこにも出ていない", not leaks, leaks[:3])
for pth in glob.glob(os.path.join(DIST, "data", "*.json")):
    if re.search(r"birthday|blood|hobby|prefecture", read(pth)):
        json_leaks.append(os.path.relpath(pth, DIST))
check("公開するJSONに、生年月日・血液型・趣味・出身地の項目が無い", not json_leaks, json_leaks[:3])

print("\n■ 出演者検索（/actress/）")
search_page = os.path.join(DIST, "actress", "index.html")
idx_path = os.path.join(DIST, "data", "actresses-index.json")
act_index = load_json(idx_path) if os.path.isfile(idx_path) else None
check("出演者検索の索引（/data/actresses-index.json）がある・形が正しい", isinstance(act_index, dict) and isinstance(act_index.get("actresses"), list) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(act_index.get("generated", ""))), str(act_index)[:80])
rows = act_index["actresses"] if isinstance(act_index, dict) and isinstance(act_index.get("actresses"), list) else []
ALLOWED_KEYS = {"n", "r", "s", "k", "i", "a", "h", "b", "c", "wa", "hi", "l"}
page_slugs = {os.path.basename(os.path.dirname(pth)) for pth in actress_pages}
row_names = [str(r.get("n")) for r in rows if isinstance(r, dict)]
row_by_name = {str(r.get("n")): r for r in rows if isinstance(r, dict)}
# 索引に載るのは「プロフィールを取得済みの人」＋「専用ページのある人（プロフィールが無くても、名前・作品数で探せるように）」。
# 同じ名前で別人のプロフィールが2つあるとき（同名の別人）は、取り違えを避けて、プロフィールの側を載せない
check("索引に、名前の重複が無い", len(row_names) == len(set(row_names)), len(row_names) - len(set(row_names)))
check(f"索引の人数が、「プロフィール取得済み（{len(profiles)}人）＋専用ページのある出演者（{len(page_name_slug)}人）」の範囲に収まる", len(page_name_slug) <= len(rows) <= len(set(profiles) | set(page_name_slug)), (len(rows), len(profiles), len(page_name_slug)))
missing_page_rows = [n for n, slug in page_name_slug.items() if n not in row_by_name or row_by_name[n].get("s") != slug]
check("専用ページのある出演者は、全員が索引にいて、s（ページの識別子）が実際のページと合っている", not missing_page_rows, missing_page_rows[:3])
stray_rows = [n for n in row_names if n not in profiles and n not in page_name_slug]
check("索引の全員が、プロフィールがあるか、専用ページがある（出どころの無い行が無い）", not stray_rows, stray_rows[:3])


def int_in(v, lo, hi):
    return v is None or (isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi)


bad_rows = []
for r in rows:
    here = []
    if not isinstance(r, dict) or set(r) != ALLOWED_KEYS:
        bad_rows.append((str(r)[:60], ["項目が決まった形ではない"]))
        continue
    if not str(r["n"]).strip():
        here.append("名前が空")
    if not (isinstance(r["k"], int) and r["k"] >= 0):
        here.append("作品数が整数でない")
    elif (r["s"] != "") != (r["k"] >= 2):
        here.append("出演者ページの有無（s）が、作品数（2本以上）と合わない")
    if r["s"] and (not re.fullmatch(r"[0-9a-f]{10}", str(r["s"])) or r["s"] not in page_slugs):
        here.append("s のページが存在しない")
    if r["i"] and not fanza_https(r["i"], DMM):
        here.append("顔写真のURLが FANZA(DMM) の https ではない")
    if r["l"] and not fanza_https(r["l"], FANZA_LINK):
        here.append("全作品リンクが FANZA の https ではない")
    if not (int_in(r["a"], 18, 80) and int_in(r["h"], 120, 210) and int_in(r["b"], 50, 160) and int_in(r["wa"], 40, 130) and int_in(r["hi"], 50, 160)):
        here.append("年齢・身長・サイズが範囲外")
    if not (isinstance(r["c"], str) and re.fullmatch(r"[A-Z]?", r["c"])):
        here.append("カップが英字1文字でない")
    if here:
        bad_rows.append((r.get("n"), here))
check("索引の各項目: 決まった項目だけ・ページの有無が作品数と合う・URLがFANZAのhttps・数字が範囲内", not bad_rows, bad_rows[:3])
check("索引は作品の多い順", all(rows[i]["k"] >= rows[i + 1]["k"] for i in range(len(rows) - 1)) if rows and all(isinstance(r, dict) and isinstance(r.get("k"), int) for r in rows) else True)
if os.path.isfile(search_page):
    stext = read(search_page)
    check("検索のスクリプト（actress-search.js）が公開されている", os.path.isfile(os.path.join(DIST, "actress-search.js")))
    if rows:
        section = [t for t in tags(stext, "section") if t.get("id") == "actress-search"]
        check("検索の部品がある（最初は隠れていて、索引のURLを持つ）", bool(section) and "hidden" in section[0] and section[0].get("data-index") == "/data/actresses-index.json" and 'src="/actress-search.js"' in stext, section[:1])
        names = {t.get("name") for tag in ("input", "select") for t in tags(stext, tag)}
        need = {"text", "age", "height", "bust", "cup", "waist", "hip", "sort"}
        check("検索の入力欄が揃っている（名前・年齢・身長・バスト・カップ・ウエスト・ヒップ・並び順）", need <= names, sorted(need - names))
        values = [t.get("value", "") for t in tags(stext, "option")]
        bad_values = [v for v in values if not re.fullmatch(r"|\d{0,3}-\d{0,3}|[A-Z]\+?|works|name", v)]
        check("選択肢の値が、スクリプトの読める形（20-24 / -19 / 40- / D / K+）だけ", not bad_values, bad_values[:5])
        ids = {t.get("id") for tag in ("ul", "p", "button", "section") for t in tags(stext, tag)}
        check("検索結果の表示先（#as-list・#as-count・#as-more・#as-note）がある", {"as-list", "as-count", "as-more", "as-note"} <= ids, sorted({"as-list", "as-count", "as-more", "as-note"} - ids))
    else:
        check("索引が空のときは、検索の部品を出さない", 'id="actress-search"' not in stext and 'src="/actress-search.js"' not in stext)
    static_rows = len([t for t in tags(stext, "li") if has_class(t, "actress-row")])
    check(f"JavaScriptが使えないとき用の一覧に、専用ページのある出演者が全員いる（{len(actress_pages)}人）", static_rows == len(actress_pages) and any(t.get("id") == "actress-static" for t in tags(stext, "section")), (static_rows, len(actress_pages)))
    check("検索の注意書き（載っていない人は絞り込みで外れる・データのある人数）が、ページにある", (not rows) or ("結果に出ません" in stext and "調べ済み" in stext))

print("\n■ 売れ筋ランキング（トップページ）")
rk_raw = load_json(RANKING) if os.path.isfile(RANKING) else None
rk_items = []
rk_fresh = False
if isinstance(rk_raw, dict) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(rk_raw.get("date", ""))) and isinstance(rk_raw.get("items"), list):
    gap = (datetime.date.fromisoformat(JST_TODAY) - datetime.date.fromisoformat(rk_raw["date"])).days
    rk_fresh = gap <= 7
    for r in rk_raw["items"]:
        if isinstance(r, dict) and re.fullmatch(r"[A-Za-z0-9_\-]+", str(r.get("cid", ""))) and str(r.get("title", "")).strip() and fanza_https(r.get("url"), FANZA_LINK):
            rk_items.append(r)
    rk_items = rk_items[:3]
home_sections = [t for t in tags(home_html, "section") if t.get("id") == "ranking"]
rank_cards = [t for t in tags(home_html, "article") if has_class(t, "rank-item")]
if rk_fresh and rk_items:
    check("ランキングがあるとき: トップに「売れ筋」の欄があり、本数が合う", len(home_sections) == 1 and len(rank_cards) == len(rk_items), (len(home_sections), len(rank_cards), len(rk_items)))
    hrefs = {t.get("href"): t for t in tags(home_html, "a")}
    missing = [r["cid"] for r in rk_items if r["url"] not in hrefs or not SPONSORED <= set(hrefs[r["url"]].get("rel", "").split())]
    check("各作品の「FANZAで見る」は、アフィリエイトのURLで、広告のリンクの属性（sponsored など）が付いている", not missing, missing)
    check("「人気順」と書いてある（FANZAのデイリーランキングと同じとは書かない）", "人気順" in home_html and "デイリーランキング" not in home_html)
    check("ページ内の移動に「売れ筋TOP3」がある", 'href="#ranking"' in home_html)
    cell_places = [re.search(r"\brank-([0-3])\b", t.get("class", "")) for t in rank_cards]
    check("1〜3位のカードに、順位ごとの大きさの目印（rank-1〜rank-3）が、順番どおりに付いている（表示の順位は、抜けがあっても1,2,3とそろえる）", [m.group(1) if m else None for m in cell_places] == ["1", "2", "3"][: len(rk_items)], [t.get("class") for t in rank_cards])
    check("売れ筋の並びに rank-podium の目印がある（スマホで1位を大きく・広い画面で3本を横いっぱいにする見た目の足がかり）", any(has_class(t, "rank-podium") for t in tags(home_html, "ul")))
else:
    check("ランキングが無い・古い（7日より前）・使える行が無いときは、トップに売れ筋の欄を出さない", not home_sections and not rank_cards and 'href="#ranking"' not in home_html)

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

print("\n■ 全ページの共通の部品（広告表記・年齢確認・リンクの属性・画像・アイコン・ヘッダー）")
bad_strip, bad_gate, bad_credit, bad_head, bad_alt, bad_lang, bad_ext = [], [], [], [], [], [], []
for p in pages:
    html, name = read(p), os.path.relpath(p, DIST)
    # 広告表記: ページの先頭（ヘッダーより前）の帯に「広告」と書いてある
    strip = re.search(r'<p class="pr-strip">([^<]*)</p>', html)
    if not strip or not strip.group(1).startswith("広告") or html.find('class="pr-strip"') > html.find("<header"):
        bad_strip.append(name)
    # 18歳確認: 最初は隠れていて（JavaScriptが開く）、ダイアログとして読み上げられ、「はい」「いいえ」がある。JavaScriptが無効のときの注意書きもある
    gate = next((t for t in tags(html, "div") if t.get("id") == "age-gate"), None)
    yes = [t for t in tags(html, "button") if t.get("id") == "gate-yes"]
    if not gate or "hidden" not in gate or gate.get("role") != "dialog" or gate.get("aria-modal") != "true" or not yes or "いいえ" not in html or "<noscript>" not in html or "18歳未満の方はご利用いただけません" not in html.split("<noscript>", 1)[-1]:
        bad_gate.append(name)
    # FANZAクレジット: リンクになっていて、規約の指す先（affiliate.dmm.com）へ行く
    credit = [t for t in tags(html, "a") if str(t.get("href", "")).startswith("https://affiliate.dmm.com/api")]
    if not credit or "Powered by FANZA Webサービス" not in html or not any("noopener" in t.get("rel", "") for t in credit):
        bad_credit.append(name)
    # <head>: 言語・画面幅・OGP・アイコン
    metas = {(t.get("property") or t.get("name")): t.get("content", "") for t in tags(html, "meta")}
    links = [(t.get("rel"), t.get("href")) for t in tags(html, "link")]
    if not all(metas.get(k) for k in ("viewport", "og:title", "og:url", "og:type", "og:site_name", "twitter:card")) or not {("icon", "/favicon.ico"), ("icon", "/favicon.svg"), ("apple-touch-icon", "/apple-touch-icon.png")} <= set(links):
        bad_head.append(name)
    if not re.search(r'<html[^>]*\blang="ja"', html):
        bad_lang.append(name)
    # 画像: alt の属性がある（飾りの画像は alt="" でよい）
    if any("alt" not in t for t in tags(html, "img")):
        bad_alt.append(name)
    # FANZA / DMM への外部リンクは、すべて広告のリンクの属性（sponsored nofollow noopener noreferrer）が付いている
    for t in tags(html, "a"):
        href_url = urlparse(str(t.get("href", "")))
        host = (href_url.hostname or "").lower()
        if re.search(r"\.(jpe?g|png|gif|webp)$", href_url.path, re.I):
            continue  # サンプル画像を拡大して見るための、画像そのものへのリンク（広告のリンクではない）
        if host and any(host == h or host.endswith("." + h) for h in FANZA_LINK) and not SPONSORED <= set(t.get("rel", "").split()):
            bad_ext.append((name, t.get("href")))
check(f"全ページの先頭に「広告」の帯がある（ヘッダーより前）", not bad_strip, bad_strip[:3])
check(f"全ページの18歳確認: 最初は隠れている・ダイアログ・「はい」「いいえ」・JavaScriptが無効のときの注意書き", not bad_gate, bad_gate[:3])
check(f"全ページの「Powered by FANZA Webサービス」が、規約の指す先へのリンクになっている", not bad_credit, bad_credit[:3])
check(f"全ページの <head>: 画面幅・OGP・Twitterカード・アイコン（ico / svg / apple-touch）", not bad_head, bad_head[:3])
check(f"全ページが lang=ja", not bad_lang, bad_lang[:3])
check(f"全ページの画像に alt がある", not bad_alt, bad_alt[:3])
check("FANZA/DMM への外部リンク（サンプル画像を拡大するリンクを除く）は、すべて広告の属性（sponsored nofollow noopener noreferrer）つき", not bad_ext, bad_ext[:3])
ico = os.path.join(DIST, "favicon.ico")
check("アイコン（favicon.ico・favicon.svg・apple-touch-icon.png）が公開されていて、中身が画像の形式", os.path.isfile(ico) and open(ico, "rb").read(4) == b"\x00\x00\x01\x00" and os.path.isfile(os.path.join(DIST, "favicon.svg")) and open(os.path.join(DIST, "apple-touch-icon.png"), "rb").read(8) == b"\x89PNG\r\n\x1a\n" if os.path.isfile(os.path.join(DIST, "apple-touch-icon.png")) else False)
# スマホで、画面を横に動かせてしまう（グラグラする）のを防ぐ設定が、ビルド後のCSSに残っている
css_rules = []
for css_path in glob.glob(os.path.join(DIST, "**", "*.css"), recursive=True):
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", read(css_path), flags=re.S)):
        css_rules.append(([x.strip() for x in m.group(1).split(",")], m.group(2)))
root_clip = any("html" in sels and re.search(r"overflow-x\s*:\s*(hidden|clip)", body) for sels, body in css_rules)
movie_clip = any(".movie-box" in sels and re.search(r"contain\s*:\s*paint", body) and re.search(r"isolation\s*:\s*isolate", body) for sels, body in css_rules)
check("CSS: html に overflow-x（hidden か clip）がある（スマホで横に動かせない）", root_clip)
check("CSS: 動画の枠（.movie-box）に contain: paint と isolation: isolate がある（枠の外に出ない）", movie_clip)
hdr = os.path.join(DIST, "_headers")
htext = read(hdr) if os.path.isfile(hdr) else ""
check("応答ヘッダーの設定（_headers）がある: nosniff・フレームへの埋め込み禁止（frame-ancestors）", "X-Content-Type-Options: nosniff" in htext and "frame-ancestors 'self'" in htext and re.search(r"^/\*\s*$", htext, re.M) is not None)


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
