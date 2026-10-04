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
    "広告表記（フッターのくわしい文）": "アフィリエイト広告",
    "広告ラベル（ヘッダー。最初に見える画面に出す）": 'class="pr-chip"',
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


def read_raw(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def unphrase(text):
    """日本語の文章に足した、文節の区切り（<wbr>）と包み（<span class="ph">）を取り除く（site/src/lib/phrase.js の逆。文字を探す検査が、区切りで途切れないように）"""
    return re.sub(r'<span class="ph">([\s\S]*?)</span>', r"\1", re.sub(r"<wbr\s*/?>", "", text))


def read(path):
    """ファイルの中身。HTMLは、文節の区切りを取り除いた形で返す（区切りそのものの検査だけが read_raw を使う）"""
    text = read_raw(path)
    return unphrase(text) if path.endswith(".html") else text


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
# 拡大表示を開いた直後のフォーカスは、枠そのもの（前へボタンに黄色い輪が付いて見えないように）。枠に tabindex="-1"、輪を消す CSS、lightbox.js の dialog.focus が揃っている
bad_lb_focus = []
for cid, x in valid.items():
    page = os.path.join(DIST, "item", cid, "index.html")
    if os.path.isfile(page) and 'id="lightbox"' in read(page):
        dlg = next((t for t in tags(read(page), "dialog") if t.get("id") == "lightbox"), None)
        if not dlg or dlg.get("tabindex") != "-1":
            bad_lb_focus.append(cid)
lb_js = read(os.path.join(DIST, "lightbox.js")) if os.path.isfile(os.path.join(DIST, "lightbox.js")) else ""
check("拡大表示: 枠に tabindex=-1・開いた直後は枠にフォーカス（lightbox.js の dialog.focus）で、前へボタンに輪が付かない", not bad_lb_focus and "dialog.focus(" in lb_js, bad_lb_focus[:3])
# 拡大表示の矢印（前・次）と×は、文字（‹ › ×）ではなく図形（SVG）。文字だと、丸の中心より下にずれて見える（本物のフォントで4〜5px）
bad_lb_icon = []
for cid, x in valid.items():
    page = os.path.join(DIST, "item", cid, "index.html")
    if os.path.isfile(page) and 'id="lightbox"' in read(page):
        btns = re.findall(r'<button\b[^>]*class="[^"]*lightbox-btn[^"]*"[^>]*>(.*?)</button>', read(page), re.S)
        if len(btns) != 3 or any('<svg' not in b or re.search(r'[‹›×]', re.sub(r'<svg.*?</svg>', '', b, flags=re.S)) for b in btns):
            bad_lb_icon.append(cid)
check("拡大表示: 前・次・閉じるのボタンは、図形（SVG）の矢印・×で、文字ではない（丸の真ん中にそろえるため）", not bad_lb_icon, bad_lb_icon[:3])
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
    rk_items = rk_items[:6]  # 売れ筋は、VR作品を隠したときの差し替え用に、6本まで持つ（画面に出すのは先頭の3本）
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
    check("1〜3位のカードに、順位ごとの大きさの目印（rank-1〜rank-3。4位以降は rank-0）が、順番どおりに付いている（表示の順位は、抜けがあっても1,2,3…とそろえる）", [m.group(1) if m else None for m in cell_places] == [str(i) if i <= 3 else "0" for i in range(1, len(rk_items) + 1)], [t.get("class") for t in rank_cards])
    check("売れ筋の並びに rank-podium の目印がある（スマホで1位を大きく・広い画面で3本を横いっぱいにする見た目の足がかり）", any(has_class(t, "rank-podium") for t in tags(home_html, "ul")))
    # 「VR作品を隠す」で本数が減っても空白ができないよう、並べ方の印（data-visible・先頭の .is-hero）を付けている（隠す前は、全部が見えている状態）
    podium = next((t for t in tags(home_html, "ul") if has_class(t, "rank-podium")), None)
    podium_cells = [t for t in tags(home_html, "li") if has_class(t, "rank-cell")]
    shown_n = min(len(podium_cells), 3)
    hero_expected = [i == 0 and (shown_n == 1 or shown_n >= 3) for i in range(len(podium_cells))]
    check("売れ筋の並びに、出す本数（data-show=3）・見えている本数（data-visible）・大きく出す1本（先頭の is-hero。3本以上か1本のとき）の印がある", bool(podium) and podium.get("data-show") == "3" and podium.get("data-visible") == str(shown_n) and [has_class(t, "is-hero") for t in podium_cells] == hero_expected, (podium.get("data-show") if podium else None, podium.get("data-visible") if podium else None, [t.get("class") for t in podium_cells]))
    check("売れ筋: 先頭の3本だけが見えていて、4位以降は rank-off（VR作品を隠したとき、差し替えに使う）。各マスに元の順位（data-rank）が入っている", [has_class(t, "rank-off") for t in podium_cells] == [i >= 3 for i in range(len(podium_cells))] and [t.get("data-rank") for t in podium_cells] == [str(i) for i in range(1, len(podium_cells) + 1)], [(t.get("class"), t.get("data-rank")) for t in podium_cells])
    check("売れ筋の見出しの横に、「VRを除く」の注記（最初は隠れている。VR作品を隠したとき、JavaScriptが出す）がある", re.search(r'<span class="rank-vr-note" hidden>｜VRを除く</span>', home_html) is not None)
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
# 運営者の希望で、画面に「AI」という表示・言葉は出さない（コメントの横のチップ・「AIのひとこと」・「AIが…」の文）。
# ただし、コメントが自動で作られていること・正確さを保証できないことの注記は、フッターに必ず残す（読者への正直さのため。消さない）。
# 作品のタイトルや出演者名に「AI」が入ることはあるので、画面に出る文の言い回しだけを調べる
AI_PHRASES = ("ai-chip", "AIのひとこと", "AIがひとこと", "AIが出演者", "AIが作品情報", "AIが自動", "AIが書", "AIによる")
ai_shown = [(os.path.relpath(p, DIST), ph) for p in pages for ph in AI_PHRASES if ph in read(p)]
check("画面に「AI」の表示・言い回しが出ていない（チップ・「AIのひとこと」・「AIが…」）", not ai_shown, ai_shown[:3])
no_auto_note = [os.path.relpath(p, DIST) for p in pages if "ひとことコメントは、" not in read(p) or "自動で作成しており、内容の正確さは保証できません" not in read(p)[read(p).find("<footer") :]]
check("フッターに、コメントが自動で作成されていて正確さは保証できない、という注記が残っている（全ページ）", not no_auto_note, no_auto_note[:3])

# 運営者の希望で、ボタンの下の「広告｜リンク先はFANZAの公式ページです…」の行は出さない（文字が多くなって見づらいため）。
# 広告であることは、ヘッダーの「広告」ラベルとフッターの文で示す（下の検査）
per_link_ad = [os.path.relpath(p, DIST) for p in pages if "広告｜リンク先は" in read(p)]
check("ボタンの下に「広告｜リンク先は…」の行が出ていない（広告の表記は、ヘッダーのラベルとフッターに）", not per_link_ad, per_link_ad[:3])

print("\n■ 全ページの共通の部品（広告表記・年齢確認・リンクの属性・画像・アイコン・ヘッダー）")
bad_label, bad_foot_ad, bad_gate, bad_credit, bad_head, bad_alt, bad_lang, bad_ext = [], [], [], [], [], [], [], []
for p in pages:
    html, name = read(p), os.path.relpath(p, DIST)
    # 広告表記: 最初に見える画面（ヘッダー。本文より前、メニューより前）に、小さな「広告」ラベルがある。くわしい文はフッターにある
    head_part = html[html.find("<header") : html.find("<main")] if "<header" in html and "<main" in html else ""
    chip = re.search(r'<span class="pr-chip">広告</span>', head_part)
    if not chip or head_part.find("pr-chip") > head_part.find("<nav") or 'class="pr-strip"' in html:
        bad_label.append(name)
    foot_part = html[html.find("<footer") :] if "<footer" in html else ""
    if "広告｜当サイトはアフィリエイト広告（FANZA）を利用しており" not in foot_part:
        bad_foot_ad.append(name)
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
check("全ページの最初に見える画面（ヘッダー）に、小さな「広告」ラベルがある（上の細い帯はやめた）", not bad_label, bad_label[:3])
check("全ページのフッターに、広告のくわしい文がある", not bad_foot_ad, bad_foot_ad[:3])
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
chip_rules = [body for sels, body in css_rules if ".pr-chip" in sels]
chip_hidden = [b for b in chip_rules if re.search(r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?![.\d])|clip\s*:|height\s*:\s*0", b)]
chip_small = [b for b in chip_rules for m in [re.search(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", b)] if m and float(m.group(1)) < 11]
check("CSS: 広告ラベル（.pr-chip）が、隠されていない・小さすぎない（11px以上）", bool(chip_rules) and not chip_hidden and not chip_small, (len(chip_rules), chip_hidden[:1], chip_small[:1]))
check("CSS: 動画の枠（.movie-box）に contain: paint と isolation: isolate がある（枠の外に出ない）", movie_clip)
# 18歳確認の背景: 真っ黒ではなく濃い曇りガラス（ぼかし）。ぼかしが弱すぎると後ろが読める・強すぎると画面のふちが逆にぼけない（Chromiumで確認済み）ので、10〜30pxに収める
gate_rules = [body for sels, body in css_rules if ".gate" in sels]
gate_blur = [float(m.group(1)) for b in gate_rules for m in [re.search(r"(?<![-\w])backdrop-filter\s*:\s*blur\(\s*(\d+(?:\.\d+)?)px", b)] if m]


def css_alpha(body):
    """background: の色の透明度（0〜1）。ビルドで rgba(…) が #rrggbbaa に縮められても読めるようにしてある。読めなければ None"""
    m = re.search(r"(?<![-\w])background\s*:\s*(rgba?\([^)]*\)|#[0-9a-fA-F]{3,8})", body)
    if not m:
        return None
    v = m.group(1)
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 8:
            return int(h[6:8], 16) / 255
        if len(h) == 4:
            return int(h[3] * 2, 16) / 255
        return 1.0
    parts = [x.strip() for x in re.split(r"[,/\s]+", v[v.index("(") + 1:-1]) if x.strip()]
    return float(parts[3]) if len(parts) >= 4 else 1.0


gate_tint = [a for a in (css_alpha(b) for b in gate_rules) if a is not None]
gate_fixed = any(re.search(r"position\s*:\s*fixed", b) and re.search(r"touch-action\s*:\s*none", b) for b in gate_rules)
gate_lock = any(("html.gate-open" in sels or "html.gate-open body" in sels) and re.search(r"overflow\s*:\s*hidden", body) for sels, body in css_rules)
gate_vignette = any(sels in ([".gate::before"], [".gate:before"]) and "gradient" in body for sels, body in css_rules)  # ビルドで ::before が :before に縮められることがある
check("CSS: 18歳確認の背景は、ぼかし（backdrop-filter: blur 10〜30px）で、色の重ねは真っ黒でない（透明度0.5〜0.75）。-webkit- は、ビルドの道具が消すことがあるので問わない（その代わり、ぼかしの条件は @supports の無印だけ）", bool(gate_blur) and 10 <= gate_blur[0] <= 30 and any(0.5 <= a <= 0.75 for a in gate_tint), (gate_blur, gate_tint))
check("CSS: 18歳確認は画面に固定（position: fixed）・指でなぞっても動かない（touch-action: none）・開いている間は後ろのページをスクロールさせない（html.gate-open の overflow: hidden）", gate_fixed and gate_lock, (gate_fixed, gate_lock))
check("CSS: 18歳確認の画面のふちを暗くする覆い（.gate::before）がある（ふちでぼかしが弱くなるブラウザ向け）", gate_vignette)
check("CSS: ふだん（ぼかしが使えない古いブラウザ）と「透明さを減らす」設定のときは、ほぼ真っ黒（透明度0.9以上）にする（ぼかしだけが効かず、薄い色だけが残るのを防ぐ）", sum(1 for a in gate_tint if a >= 0.9) >= 2 and any(sels == [".gate"] and "position" in body and (css_alpha(body) or 0) >= 0.9 for sels, body in css_rules), gate_tint)
hdr = os.path.join(DIST, "_headers")
htext = read(hdr) if os.path.isfile(hdr) else ""
check("応答ヘッダーの設定（_headers）がある: nosniff・フレームへの埋め込み禁止（frame-ancestors）", "X-Content-Type-Options: nosniff" in htext and "frame-ancestors 'self'" in htext and re.search(r"^/\*\s*$", htext, re.M) is not None)


print("\n■ サムネの切り取り・作品検索・「VR作品を隠す」")


def is_vr_raw(x):
    """保存データの1件がVR作品か（site/src/lib/items.js の isVrWork と同じ決まり。突き合わせるため、別に書いてある）"""
    title = str(x.get("title", ""))
    tags_ = [t for t in (x.get("tags") or []) if isinstance(t, str) and re.fullmatch(r"[0-9A-Za-z]{1,6}", t)]
    genres_ = [g for g in (x.get("genres") or []) if g]
    return bool(re.search(r"【[^】]*VR[^】]*】", title, re.I)) or any("VR" in t.upper() for t in tags_) or any("VR" in str(g).upper() for g in genres_)


# サムネ: パッケージ画像（800×538）の右端の表紙だけを、すべて同じ比率で切り出す（背表紙を入れない・表紙を欠かさない）
def rule_bodies(selector):
    return [body for sels, body in css_rules if selector in sels]


root_vars = " ".join(rule_bodies(":root"))
ratio_m = re.search(r"--cover-ratio\s*:\s*(\d+)\s*/\s*(\d+)", root_vars)
cover_ratio = int(ratio_m.group(1)) / int(ratio_m.group(2)) if ratio_m else 0
check("CSS: サムネの比率（--cover-ratio）が、表紙（379:538 ≒ 0.7045）より少し細い 0.69〜0.704（背表紙を入れず、表紙もほとんど欠けない）", 0.69 <= cover_ratio <= 0.704, cover_ratio)
cover_boxes = [b for b in rule_bodies(".item-cover") if "aspect-ratio" in b]
check("CSS: 作品カードのサムネの枠（.item-cover）が --cover-ratio の比率", len(cover_boxes) == 1 and re.search(r"aspect-ratio\s*:\s*var\(--cover-ratio\)", cover_boxes[0]) is not None, cover_boxes[:2])
other_ratios = [sels for sels, body in css_rules if "aspect-ratio" in body and any(x.endswith("item-cover") and x != ".item-cover" for x in sels)]
check("CSS: ランキング（.rank-item など）が、サムネの比率を別の値に変えていない（3:4だと背表紙が入る）", not other_ratios, other_ratios[:2])
img_rules = rule_bodies(".item-img")
check("CSS: サムネの画像（.item-img）は、枠いっぱいに、右端にそろえて切り出す（object-fit: cover・object-position: 100% 50%）", any(re.search(r"object-fit\s*:\s*cover", b) and re.search(r"object-position\s*:\s*100%\s*50%", b) for b in img_rules), img_rules[:1])
thumb = " ".join(rule_bodies(".fav-thumb"))
tw, th = re.search(r"width\s*:\s*(\d+)px", thumb), re.search(r"height\s*:\s*(\d+)px", thumb)
check("CSS: お気に入りのサムネ（.fav-thumb）も、表紙の比率に近い（0.68〜0.72）・右端にそろえる", bool(tw and th) and 0.68 <= int(tw.group(1)) / int(th.group(1)) <= 0.72 and re.search(r"object-position\s*:\s*100%\s*50%", thumb) is not None, thumb[:120])

# 「VR作品を隠す」の見た目の決まり
hide_rule = [b for sels, b in css_rules if ".hide-vr [data-vr]" in sels]
rank_sels = [x for sels, b in css_rules for x in sels]
check("CSS: 売れ筋は、VRを隠して2本・1本になったときの並べ方（data-visible=2/1）と、全部がVRのとき売れ筋ごと隠す（#ranking.vr-empty）がある", '.rank-podium[data-visible="2"]' in rank_sels and '.rank-podium[data-visible="1"]' in rank_sels and any("#ranking.vr-empty" in sels and re.search(r"display\s*:\s*none", b) for sels, b in css_rules), [x for x in rank_sels if "data-visible" in x or "vr-empty" in x])
check("CSS: html.hide-vr のとき、VR作品の目印（data-vr）のマスと、全部がVRの日付（.day.vr-empty）を隠す", bool(hide_rule) and all(re.search(r"display\s*:\s*none", b) for b in hide_rule) and any(".day.vr-empty" in sels for sels, b in css_rules if ".hide-vr [data-vr]" in sels), hide_rule[:1])
hidden_ok = [sels for sels, b in css_rules if ".vr-toggle[hidden]" in sels and re.search(r"display\s*:\s*none", b)]
check("CSS: 隠れているスイッチ・検索（hidden）が、display の指定に負けずに隠れる", bool(hidden_ok) and any(".work-search[hidden]" in sels for sels in hidden_ok), hidden_ok[:1])

# 全ページ: 先に印を付ける小さなスクリプト・スイッチのスクリプト・検索へのリンク
no_head_vr, no_vr_js, no_nav_search, no_foot_search = [], [], [], []
for p in pages:
    html_ = read(p)
    head_ = html_[: html_.find("</head>")] if "</head>" in html_ else ""
    if "localStorage.getItem('hide-vr') === '1'" not in head_ or "classList.add('hide-vr')" not in head_:
        no_head_vr.append(os.path.relpath(p, DIST))
    if 'src="/vr-filter.js"' not in html_:
        no_vr_js.append(os.path.relpath(p, DIST))
    nav_ = html_[html_.find('<nav class="site-nav"') : html_.find("</nav>", html_.find('<nav class="site-nav"'))] if '<nav class="site-nav"' in html_ else ""
    if 'href="/search/"' not in nav_:
        no_nav_search.append(os.path.relpath(p, DIST))
    foot_ = html_[html_.find("<footer") :] if "<footer" in html_ else ""
    if 'href="/search/"' not in foot_:
        no_foot_search.append(os.path.relpath(p, DIST))
check(f"全ページの <head> に、「VR作品を隠す」の印を先に付ける小さなスクリプトがある（開いた瞬間にチラつかない。{len(pages)}ページ）", not no_head_vr, no_head_vr[:3])
check("全ページに vr-filter.js が読み込まれている", not no_vr_js, no_vr_js[:3])
check("全ページの上のメニュー・フッターに、検索（/search/）へのリンクがある", not no_nav_search and not no_foot_search, (no_nav_search[:2], no_foot_search[:2]))
check("スクリプト（search.js・vr-filter.js）が公開されている", os.path.isfile(os.path.join(DIST, "search.js")) and os.path.isfile(os.path.join(DIST, "vr-filter.js")))
check("出演者検索の「FANZAで全作品を見る」に（広告）が付いていない（広告表記は、全ページのヘッダー・フッター）", os.path.isfile(os.path.join(DIST, "actress-search.js")) and "（広告）" not in read(os.path.join(DIST, "actress-search.js")) and "FANZAで全作品を見る" in read(os.path.join(DIST, "actress-search.js")))

# 一覧の1マス（li）の目印: VR作品にだけ data-vr が付く
def shelf_cells(html_):
    for m in re.finditer(r'<li class="shelf-cell([^"]*)"([^>]*)>(.*?)</li>', html_, re.S):
        link = re.search(r'href="/item/([^/"]+)/"', m.group(3))
        yield m.group(1), m.group(2), (link.group(1) if link else None), m.group(3)


wrong_mark, marked_total, vr_total = [], 0, 0
list_pages = [index_path] + sorted(glob.glob(os.path.join(DIST, "archive", "*", "index.html"))) + sorted(glob.glob(os.path.join(DIST, "actress", "*", "index.html"))) + sorted(glob.glob(os.path.join(DIST, "maker", "*", "index.html"))) + sorted(glob.glob(os.path.join(DIST, "item", "*", "index.html")))
for lp in list_pages:
    for cls, attrs, cid, inner in shelf_cells(read(lp)):
        if cid is None or cid not in valid or "rank-cell" in cls:
            continue
        marked = 'data-vr="true"' in attrs
        marked_total += 1
        vr_total += int(marked)
        if marked != is_vr_raw(valid[cid]):
            wrong_mark.append((os.path.relpath(lp, DIST), cid, marked))
check(f"作品の一覧のマス（{marked_total}個）: VR作品（データのタイトル・形式・ジャンルから判定）にだけ data-vr が付いている", not wrong_mark, wrong_mark[:3])
warn("VR作品のマスが、一覧のどこかにある（目印のテストが空振りしていない）", vr_total > 0)
rank_wrong = []
for cls, attrs, cid, inner in shelf_cells(home_html):
    if "rank-cell" not in cls:
        continue
    rank_title = (re.search(r'class="item-title-link"[^>]*>([^<]*)<', inner) or [None, ""])[1]
    rk = next((r for r in rk_items if htmllib.unescape(rank_title) == str(r.get("title", "")).strip()), None)
    if rk is None:
        continue
    expect = rk.get("vr") is True or bool(re.search(r"【[^】]*VR[^】]*】", str(rk["title"]), re.I)) or (str(rk["cid"]) in valid and is_vr_raw(valid[str(rk["cid"])]))
    if ('data-vr="true"' in attrs) != expect:
        rank_wrong.append((rk["cid"], 'data-vr="true"' in attrs, expect))
check("売れ筋: VR作品（データの vr・題名の【VR】・当サイトの作品のジャンル）にだけ data-vr が付いている", not rank_wrong, rank_wrong[:3])

# スイッチ（VR作品を隠す）の置き場所: 最初は隠れていて、JavaScriptが出す
toggle_pages = [index_path, os.path.join(DIST, "search", "index.html")] + sorted(glob.glob(os.path.join(DIST, "archive", "*", "index.html")))[:1] + sorted(glob.glob(os.path.join(DIST, "actress", "*", "index.html")))[:1] + sorted(glob.glob(os.path.join(DIST, "maker", "*", "index.html")))[:1]
bad_toggle = []
for tp in toggle_pages:
    if not os.path.isfile(tp):
        bad_toggle.append((os.path.relpath(tp, DIST), "ページが無い"))
        continue
    btns = [t for t in tags(read(tp), "button") if "data-vr-toggle" in t]
    if len(btns) != 1 or "hidden" not in btns[0] or btns[0].get("aria-pressed") != "false" or not btns[0].get("data-on") or not btns[0].get("data-off") or btns[0].get("type") != "button":
        bad_toggle.append((os.path.relpath(tp, DIST), btns[:1]))
check("「VR作品を隠す」スイッチが、トップ・検索・過去の作品・出演者・メーカーのページに1つずつある（最初は隠れている・押された状態ではない・文言つき）", not bad_toggle, bad_toggle[:3])

# 作品ページ: ジャンルは、そのジャンルで絞り込んだ検索へのリンク
import urllib.parse as _up
bad_chip, chip_pages = [], 0
for cid, x in valid.items():
    fp = os.path.join(DIST, "item", cid, "index.html")
    genres_ = [g for g in (x.get("genres") or []) if g]
    if not genres_ or not os.path.isfile(fp):
        continue
    chip_pages += 1
    links_ = [t.get("href") for t in tags(read(fp), "a") if has_class(t, "chip-tag")]
    if links_ != ["/search/?tag=" + _up.quote(g, safe="") for g in genres_]:
        bad_chip.append((cid, links_[:2]))
check(f"作品ページのジャンル（{chip_pages}ページ）が、そのジャンルで絞り込んだ検索（/search/?tag=…）へのリンクになっている", not bad_chip, bad_chip[:2])
warn("ジャンルのある作品が1本以上ある", chip_pages > 0)

# 検索ページ
sp = os.path.join(DIST, "search", "index.html")
check("検索ページ（/search/）がある", os.path.isfile(sp))
if os.path.isfile(sp):
    stext_ = read(sp)
    check("検索ページは noindex で、sitemap に入っていない（条件ごとに内容が変わる画面のため）", 'name="robots" content="noindex' in stext_ and "/search/" not in sm_paths)
    section_ = next((t for t in tags(stext_, "section") if t.get("id") == "work-search"), None)
    check("検索の部品（#work-search）: 最初は隠れている・索引は /data/items-index.json・search.js を読む", section_ is not None and "hidden" in section_ and section_.get("data-index") == "/data/items-index.json" and 'src="/search.js"' in stext_, section_)
    names_ = {t.get("name") for tag in ("input", "select") for t in tags(stext_, tag)}
    ids_ = {t.get("id") for tag in ("ul", "p", "button", "section") for t in tags(stext_, tag)}
    check("検索のフォーム（q・status・sort）と、結果の表示先（#ws-tag-list・#ws-tag-more・#ws-count・#ws-list・#ws-more）がある", {"q", "status", "sort"} <= names_ and {"ws-tag-list", "ws-tag-more", "ws-count", "ws-list", "ws-more"} <= ids_, (sorted({"q", "status", "sort"} - names_), sorted({"ws-tag-list", "ws-tag-more", "ws-count", "ws-list", "ws-more"} - ids_)))
    sel_values = [re.findall(r'<option value="([^"]*)"', blk) for blk in re.findall(r'<select name="(?:status|sort)".*?</select>', stext_, re.S)]
    check("選択肢の値が、スクリプトの読める形（''・released・upcoming / new・old）だけ", sel_values == [["", "released", "upcoming"], ["new", "old"]], sel_values)
    fb = next((t for t in tags(stext_, "section") if t.get("id") == "ws-fallback"), None)
    check("JavaScriptが使えないとき用の案内（#ws-fallback）に、過去の作品・出演者・メーカーへのリンクがある", fb is not None and all(f'href="{h}"' in stext_ for h in ("/archive/1/", "/actress/", "/maker/")))
    check("ジャンルが載っていない予約作品がある旨の注意書きが、検索ページにある", "予約中の作品は、ジャンルがまだ載っていないことがあります" in stext_)

# 索引（/data/items-index.json）
ii = os.path.join(DIST, "data", "items-index.json")
check("検索の索引（/data/items-index.json）がある", os.path.isfile(ii))
if os.path.isfile(ii):
    try:
        iidx = json.loads(read(ii))
    except ValueError:
        iidx = None
    ok_shape = isinstance(iidx, dict) and DAY.match(str(iidx.get("generated", ""))) and isinstance(iidx.get("newDays"), int) and isinstance(iidx.get("genres"), list) and isinstance(iidx.get("items"), list)
    check("索引が正しいJSONで、generated・newDays・genres・items がある", bool(ok_shape), str(iidx)[:80])
    if ok_shape:
        irows, igenres = iidx["items"], iidx["genres"]
        check("索引の項目が、短い名前（c,t,d,a,m,g,i,v）だけで、データにある作品・長い文やURLは入っていない", all(isinstance(r, dict) and set(r) <= set("ctdamgiv") and {"c", "t", "d", "a", "m", "g", "i"} <= set(r) and r["c"] in valid and DAY.match(str(r["d"])) and isinstance(r["a"], list) and isinstance(r["g"], list) for r in irows) and "al.fanza.co.jp" not in read(ii), [r for r in irows if not (isinstance(r, dict) and set(r) <= set("ctdamgiv"))][:1])
        check(f"索引の作品の数（{len(irows)}）= min(データの件数 {len(valid)}, 3000)", len(irows) == min(len(valid), 3000), (len(irows), len(valid)))
        check("索引は発売日の新しい順", [r["d"] for r in irows] == sorted((r["d"] for r in irows), reverse=True))
        check("ジャンルの番号（g）が、すべて genres の範囲内で、作品のジャンルの名前に戻る", all(all(isinstance(n, int) and 0 <= n < len(igenres) for n in r["g"]) and sorted(igenres[n] for n in r["g"]) == sorted(set(g for g in (valid[r["c"]].get("genres") or []) if g)) for r in irows), [r["c"] for r in irows if sorted(igenres[n] for n in r["g"] if isinstance(n, int) and 0 <= n < len(igenres)) != sorted(set(g for g in (valid[r["c"]].get("genres") or []) if g))][:2])
        check("ジャンルの一覧は、重複なし・作品の多い順", len(set(igenres)) == len(igenres) and [sum(1 for r in irows if i in r["g"]) for i in range(len(igenres))] == sorted((sum(1 for r in irows if i in r["g"]) for i in range(len(igenres))), reverse=True))
        check("VRの印（v:1）が、データから判定したVR作品と一致する（VR作品にだけ付く）", all((r.get("v") == 1) == is_vr_raw(valid[r["c"]]) and r.get("v") in (None, 1) for r in irows), [r["c"] for r in irows if (r.get("v") == 1) != is_vr_raw(valid[r["c"]])][:3])
        warn("索引にVR作品が1本以上ある（VRの除外のテストが空振りしていない）", any(r.get("v") == 1 for r in irows))
        bad_img = [r["c"] for r in irows if r["i"] and not fanza_https(r["i"] if r["i"].startswith("https://") else "https://pics.dmm.co.jp/" + r["i"], ["dmm.co.jp"])]
        check("索引の画像が、FANZA(DMM)の画像に戻せる形（先頭を省いた形）", not bad_img, bad_img[:3])
        check("索引の大きさが 1.5MB 以内（検索ページを開くたびにダウンロードされるため）", os.path.getsize(ii) <= 1500 * 1024, os.path.getsize(ii))

print("\n■ 日本語の文章の改行（文節の区切り）")
# 日本語の文章は、ビルドの最後に、文節の区切り（<wbr>）と包み（<span class="ph">）が足される（site/src/lib/phrase.js・Astro の拡張 phrase-breaks）。
# iPhone/iPadのSafari系には、CSSで文節ごとに改行する機能が無いため、「あ／り」のような語の途中の改行を、これで防いでいる
html_files = glob.glob(os.path.join(DIST, "**", "*.html"), recursive=True)
PH_BLOCK = re.compile(r'<span class="ph">[\s\S]*?</span>')
SKIP_EL = re.compile(r"<(script|style|title|textarea|button|option|select|pre|code|noscript|svg|template)\b[^>]*>[\s\S]*?</\1\s*>", re.I)
stray_wbr, tag_in_ph, ph_in_skip, with_ph = [], [], [], 0
for p in html_files:
    raw = read_raw(p)
    if PH_BLOCK.search(raw):
        with_ph += 1
    if "<wbr" in PH_BLOCK.sub("", raw):
        stray_wbr.append(rel(p))
    if any("<" in re.sub(r"<wbr>", "", m.group(0)[len('<span class="ph">'):-len("</span>")]) for m in PH_BLOCK.finditer(raw)):
        tag_in_ph.append(rel(p))
    if any('class="ph"' in m.group(0) or "<wbr" in m.group(0) for m in SKIP_EL.finditer(raw)):
        ph_in_skip.append(rel(p))
check("全ページで、文節の区切り（<wbr>）が、すべて <span class=\"ph\"> の中にある", not stray_wbr, stray_wbr[:3])
check("<span class=\"ph\"> の中には、<wbr> のほか、タグが入っていない（文章だけ）", not tag_in_ph, tag_in_ph[:3])
check("script・style・title・ボタン・コードなどの中には、区切りを入れていない", not ph_in_skip, ph_in_skip[:3])
check(f"ほとんどのページ（9割以上）の日本語の文章に、文節の区切りが入っている（Astro の拡張が動いた証拠。{with_ph}/{len(html_files)}）", html_files and with_ph >= len(html_files) * 0.9, (with_ph, len(html_files)))
for path_, label in [("index.html", "トップ"), ("actress/index.html", "出演者一覧（運営者が見つけた説明文）"), ("calendar/index.html", "カレンダーの使い方")]:
    f = os.path.join(DIST, path_)
    check(f"{label}の説明文に、文節の区切り（<wbr>）が入っている", os.path.isfile(f) and bool(re.search(r'<span class="ph">[^<]*<wbr>', read_raw(f))), path_)
ph_rules = [body for sels, body in css_rules if ".ph" in sels]
check("CSS: .ph は word-break: keep-all（<wbr> の所以外では改行しない）・overflow-wrap（長すぎるときだけ、どこででも）・line-break: strict（禁則を厳しめに）", any(re.search(r"word-break\s*:\s*keep-all", b) and re.search(r"overflow-wrap\s*:\s*(anywhere|break-word)", b) and re.search(r"line-break\s*:\s*strict", b) for b in ph_rules), ph_rules[:1])

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
