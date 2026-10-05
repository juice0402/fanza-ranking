"""ビルド結果（site/dist）の点検

`npm run build` のあとに実行します。ページが揃っているか、サイトに必ず必要な表記
（18歳確認・広告表記・FANZAクレジット・RTA）が全ページに残っているかを確かめます。
実行: python3 tests/verify_dist.py [distのパス]   （省略時は site/dist）
"""
import datetime
import glob
import hashlib as _hl
import html as htmllib
import json
import os
import re
import sys
import unicodedata as _ud
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "site", "dist")
DATA = os.path.join(ROOT, "site", "src", "data", "new_releases.json")
CATALOG_DIR = os.path.join(ROOT, "site", "src", "data", "catalog")  # 過去作品（発売月ごとのファイル。まだ無いこともある）
CATALOG_RANK = os.path.join(ROOT, "site", "src", "data", "catalog_rank.json")  # 過去作品の人気順の順位 {cid: [順位, 一回りの番号]}
FILE_LIMIT = 20000  # Cloudflare Pages の無料プランの、1つのサイトのファイル数の上限
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
    """日本語の文章に足した、文節の区切り（<wbr>）と包み（<span class="ph">・名前の <span class="nb">）を取り除く
    （site/src/lib/phrase.js の逆。文字を探す検査が、区切りで途切れないように）"""
    text = re.sub(r"<wbr\s*/?>", "", text)
    text = re.sub(r'<span class="nb">([^<]*)</span>', r"\1", text)
    return re.sub(r'<span class="ph">([^<]*)</span>', r"\1", text)


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


strip_tags = lambda h: htmllib.unescape(re.sub(r"<[^>]+>", "", h))  # タグを外した文字だけ


def has_class(attrs, name):
    return name in attrs.get("class", "").split()


def fanza_https(url, hosts):
    """https で、ホストが hosts のどれか（またはそのサブドメイン）のURLか"""
    text = str(url or "")
    # ホストのあとは、ポート番号（数字）か、パス・?・#・終わりだけ。ユーザー名の欄に FANZA のホストを入れて見せかける形（https://dmm.co.jp:@別のサイト/）や、空白・バックスラッシュを含む形は通さない
    m = re.match(r"^https://([A-Za-z0-9.\-]+)(?::\d{1,5})?(?:[/?#]|$)", text)
    host = m.group(1).lower() if m else ""
    return bool(m) and not re.search(r"[\\\s\x00-\x1f\x7f]", text) and any(host == h or host.endswith("." + h) for h in hosts)


def entity_slug(name):
    """site/src/lib/items.js の entitySlug と同じ（名前 → URLの短い英数字）。突き合わせるため、別に書いてある"""
    return _hl.sha1(_ud.normalize("NFC", str(name)).encode("utf-8")).hexdigest()[:10]


def rel(p):
    """dist の中の相対パス（表示用）"""
    return os.path.relpath(p, DIST)


def page_file(url_path):
    """URLのパス（/item/abc/）に対応する、dist内のファイルを返す"""
    url_path = url_path.split("#")[0]  # ページの中の見出しへのリンク（/sale/#sale-0）は、ページのファイルで調べる
    rel = url_path.lstrip("/")
    if url_path.endswith("/") or rel == "":
        return os.path.join(DIST, rel, "index.html")
    return os.path.join(DIST, rel)


if not os.path.isdir(DIST):
    print(f"  ❌ {DIST} がありません。先に `npm run build`（site フォルダ）を実行してください")
    sys.exit(1)

def usable_rows(rows):
    """サイト側の normalizeItems と同じ条件で、使える作品を cid ごとに（同じ cid は先のもの）"""
    out = {}
    for x in rows if isinstance(rows, list) else []:
        if not isinstance(x, dict):
            continue
        cid = str(x.get("cid", "")).strip()
        if cid and str(x.get("title", "")).strip() and re.match(r"^\d{4}-\d{2}-\d{2}", str(x.get("date", ""))):
            out.setdefault(cid, x)
    return out


# 毎日の更新で載せた作品（新作・予約）
curated = usable_rows(json.load(open(DATA, encoding="utf-8")))
# 過去作品（カタログ）: 発売月ごとのファイルを、名前の順につなげて読む（サイト側の data.js と同じ）。
# 毎日の更新で載せた作品と同じ作品・FANZAのURLが無い作品は、サイトに載らない
catalog_rows = []
for shard in sorted(glob.glob(os.path.join(CATALOG_DIR, "*.json"))):
    loaded = json.load(open(shard, encoding="utf-8"))
    catalog_rows.extend(loaded if isinstance(loaded, list) else [])
catalog = {c: x for c, x in usable_rows(catalog_rows).items() if c not in curated and fanza_https(x.get("url"), ["fanza.co.jp", "dmm.co.jp"])}
everything = {**curated, **catalog}
try:
    _ranks = json.load(open(CATALOG_RANK, encoding="utf-8"))
except (OSError, ValueError):
    _ranks = {}
catalog_rank = {c: v[0] for c, v in (_ranks.items() if isinstance(_ranks, dict) else []) if isinstance(v, list) and v and isinstance(v[0], int) and 1 <= v[0] < 50000}  # 50000 は「まだ分からない」
POPULARITY = os.path.join(ROOT, "site", "src", "data", "popularity.json")  # 新着の人気順・毎日の更新の作品の全体の順位
try:
    _pop = json.load(open(POPULARITY, encoding="utf-8"))
except (OSError, ValueError):
    _pop = {}
_pop = _pop if isinstance(_pop, dict) else {}
_rank_map = lambda d: {c: v for c, v in (d.items() if isinstance(d, dict) else []) if isinstance(v, int) and not isinstance(v, bool) and 1 <= v < 50000}
pop_new, pop_all = _rank_map(_pop.get("new")), _rank_map(_pop.get("all"))
all_rank_of = lambda c: catalog_rank.get(c) if c in catalog else pop_all.get(c)  # 全体の人気順（過去作品は catalog_rank、毎日の更新の作品は popularity.json の all）
has_comment = lambda x: bool(str(x.get("comment") or "").strip())


def is_solo_raw(x):
    """保存データの1件が単体作品か（site/src/lib/items.js の isSoloWork と同じ決まり）"""
    genres_ = [g for g in (x.get("genres") or []) if g]
    return "単体作品" in genres_ if genres_ else len([a for a in (x.get("actress") or []) if a]) == 1


def is_vr_raw(x):
    """保存データの1件がVR作品か（site/src/lib/items.js の isVrWork と同じ決まり。突き合わせるため、別に書いてある）"""
    title = str(x.get("title", ""))
    tags_ = [t for t in (x.get("tags") or []) if isinstance(t, str) and re.fullmatch(r"[0-9A-Za-z]{1,6}", t)]
    genres_ = [g for g in (x.get("genres") or []) if g]
    return bool(re.search(r"【[^】]*VR[^】]*】", title, re.I)) or any("VR" in t.upper() for t in tags_) or any("VR" in str(g).upper() for g in genres_)


print("■ ページが揃っている")
index_path = os.path.join(DIST, "index.html")
check("トップページ", os.path.isfile(index_path))
check("404ページ", os.path.isfile(os.path.join(DIST, "404.html")))
check("過去の作品 1ページ目", os.path.isfile(os.path.join(DIST, "archive", "1", "index.html")))
item_pages = glob.glob(os.path.join(DIST, "item", "*", "index.html"))
paged = {os.path.basename(os.path.dirname(p)) for p in item_pages}
check("作品ページは、データにある作品のものだけ", paged <= set(everything), sorted(paged - set(everything))[:3])
check(f"毎日の更新で載せた作品（{len(curated)}本）は、すべて作品ページがある", set(curated) <= paged, sorted(set(curated) - paged)[:3])

print("\n■ ファイル数（Cloudflare Pages の無料プランは2万ファイルまで）")
dist_files = sum(len(fs) for _, _, fs in os.walk(DIST))
print(f"   ファイル {dist_files} ／ 作品ページ {len(paged)} ／ 作品 {len(everything)}本（過去作品 {len(catalog)}本）")
check(f"サイト全体のファイル数（{dist_files}）が {FILE_LIMIT} 以内", dist_files <= FILE_LIMIT, dist_files)


def page_rank(cid):
    """作品ページの優先順（site/src/lib/plan.js と同じ考え方。小さいほど先）: 毎日の更新で載せた作品 → コメントのある過去作品 → そのほか、
    同じ中では、過去作品は人気順の順位が上の作品から（順位が分からない作品はそのあと）、そのあとは発売日の新しい順"""
    x = everything[cid]
    # site/src/lib/data.js の rank と同じ: 全体の人気順と新着の人気順の、上のほう
    rank = min(catalog_rank.get(cid, float("inf")), pop_new.get(cid, float("inf"))) if cid in catalog else float("inf")
    return (0 if cid in curated else 1 if has_comment(x) else 2, rank, -int(str(x["date"])[:10].replace("-", "")))


unpaged = set(everything) - paged
if unpaged:
    worst_paged = max((page_rank(c) for c in paged), default=(-1, 0))
    best_unpaged = min(page_rank(c) for c in unpaged)
    check(f"作品ページの無い作品（{len(unpaged)}本）は、優先順があとのものだけ（毎日の更新で載せた作品→コメントのある過去作品→人気順の順位が上の作品）", worst_paged <= best_unpaged, (worst_paged, best_unpaged))
    budget = int(re.search(r"export const FILE_BUDGET = (\d+);", read(os.path.join(ROOT, "site", "src", "config.js"))).group(1))
    fixed = int(re.search(r"export const FIXED_FILES = (\d+);", read(os.path.join(ROOT, "site", "src", "config.js"))).group(1))
    # 作品ページ以外のファイルは見積もり（FIXED_FILES）より少ないので、そのぶん上限より少し下になる。大きく余らせていないことだけを見る
    check("あふれた作品があるときは、上限近くまで作品ページを作っている（枠を大きく余らせていない）", dist_files >= budget - 2 * fixed, (dist_files, budget - 2 * fixed))
bad_noindex = [c for c in paged if c in everything and (('name="robots" content="noindex' in read_raw(os.path.join(DIST, "item", c, "index.html"))) == has_comment(everything[c]))]
check("作品ページ: コメントの無い作品（過去作品）だけ noindex（コメントのある作品は検索エンジンに出す）", not bad_noindex, bad_noindex[:3])
links_out = []
for lp in sorted(glob.glob(os.path.join(DIST, "archive", "*", "index.html")))[:50]:
    for t in tags(read_raw(lp), "a"):
        m_ = re.match(r"^/item/([^/]+)/$", t.get("href", ""))
        if m_ and m_.group(1) not in paged:
            links_out.append((os.path.relpath(lp, DIST), m_.group(1)))
check("過去の作品の一覧から、作品ページの無い作品へは、サイトの中のリンクを張らない（FANZAへ直接）", not links_out, links_out[:3])
# ここから下の、作品ページごとの点検は、作品ページがある作品を見る
valid = {c: everything[c] for c in sorted(paged) if c in everything}
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
    indexable_items = {c for c, x in valid.items() if has_comment(x)}
    wrong = [c for c in indexable_items if lastmod_of.get(f"/item/{c}/") != str(valid[c].get("updated"))]
    check("sitemap の作品ページの lastmod が、データの updated と同じ", not wrong, wrong[:3])
    check("sitemap にトップがある", any(urlparse(u).path == "/" for u in locs))
    sm_items = {p[len("/item/"):-1] for p in sm_paths if p.startswith("/item/")}
    check(f"sitemap の作品ページ = 作品ページがあり、コメントのある作品（{len(indexable_items)}本）", sm_items == indexable_items, (sorted(indexable_items - sm_items)[:3], sorted(sm_items - indexable_items)[:3]))
    missing = [u for u in locs if not os.path.isfile(page_file(urlparse(u).path))]
    check("sitemap のURLがすべて実在するページ", not missing, missing[:3])

print("\n■ 出演者・メーカーのページ")
check("出演者一覧ページ（/actress/）", os.path.isfile(os.path.join(DIST, "actress", "index.html")))
check("メーカー一覧ページ（/maker/）", os.path.isfile(os.path.join(DIST, "maker", "index.html")))
if os.path.isfile(sitemap_path):
    check("sitemap に出演者一覧・メーカー一覧がある", "/actress/" in sm_paths and "/maker/" in sm_paths)
    for kind in ("actress", "maker"):
        entity_pages = glob.glob(os.path.join(DIST, kind, "*", "index.html"))
        in_sitemap = {p for p in sm_paths if p.startswith(f"/{kind}/") and p != f"/{kind}/"}
        indexable = {f"/{kind}/{os.path.basename(os.path.dirname(p))}/" for p in entity_pages if 'name="robots" content="noindex' not in read_raw(p)}
        check(f"{kind} ページのうち、noindex でないもの（{len(indexable)}/{len(entity_pages)}ページ）が、すべて sitemap に入っている", indexable == in_sitemap, (len(indexable), len(in_sitemap)))

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
# 前・次のボタンは、画像に重ならないよう、画像の下の帯（.lightbox-bar）に置く（運営者の希望。2026-10-05）
bad_lb_bar = []
for cid, x in valid.items():
    page = os.path.join(DIST, "item", cid, "index.html")
    if os.path.isfile(page) and 'id="lightbox"' in read(page):
        bar = re.search(r'<div class="lightbox-bar">(.*?)</div>', read(page), re.S)
        if not bar or 'lightbox-prev' not in bar.group(1) or 'lightbox-next' not in bar.group(1) or 'lightbox-count' not in bar.group(1) or 'class="lightbox-view"' not in read(page):
            bad_lb_bar.append(cid)
check("拡大表示: 前・次のボタンと枚数は、画像の下の帯（.lightbox-bar）にある（画像に重ならない）", not bad_lb_bar, bad_lb_bar[:3])
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
# 表示の速さ: 動画が無い作品の、最初の画面の表紙は、優先して読む（fetchpriority="high"）
slow_lcp = []
for cid, x in valid.items():
    page = os.path.join(DIST, "item", cid, "index.html")
    if not os.path.isfile(page) or not str(x.get("image_url") or "").strip() or fanza_https(str(x.get("sample_movie") or ""), DMM):
        continue
    main_img = next((t for t in tags(read(page), "img") if has_class(t, "detail-cover")), None)
    if not main_img or main_img.get("fetchpriority") != "high" or main_img.get("loading") == "lazy":
        slow_lcp.append(cid)
check("動画が無い作品ページの表紙を、優先して読む（fetchpriority=high・lazy にしない）", not slow_lcp, slow_lcp[:3])
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

# 所属事務所とSNS（data/agencies.json。事務所の公式サイトから週1回。運営者の希望。2026-10-05）。
# 決まった5つの事務所（site/src/lib/agencies.js の AGENCIES）だけ・出どころは事務所の公式サイト・アカウント名の形・同じ名前は1行だけ
_agencies_src = read(os.path.join(ROOT, "site", "src", "lib", "agencies.js"))
AGENCY_SITES = {k: (n, u) for k, n, u in re.findall(r"(\w+): \{ name: '([^']+)', url: '([^']+)' \}", _agencies_src)}
try:
    _agency_data = json.load(open(os.path.join(ROOT, "site", "src", "data", "agencies.json"), encoding="utf-8"))
except (OSError, ValueError):
    _agency_data = {}
_agency_rows = [r for r in (_agency_data.get("rows") if isinstance(_agency_data, dict) and isinstance(_agency_data.get("rows"), list) else []) if isinstance(r, dict)]
_agency_ok = lambda r: (r.get("agency") in AGENCY_SITES and isinstance(r.get("name"), str) and r["name"].strip() and str(r.get("source", "")).startswith(AGENCY_SITES[r["agency"]][1])
                        and not re.search(r"[\s\"'<>\\]", str(r.get("source", ""))) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("seen", ""))))
_agency_name_count = {}
for r in _agency_rows:
    if _agency_ok(r):
        _agency_name_count[r["name"].strip()] = _agency_name_count.get(r["name"].strip(), 0) + 1
agency_by_name = {r["name"].strip(): r for r in _agency_rows if _agency_ok(r) and _agency_name_count[r["name"].strip()] == 1}
check("所属事務所のデータ（agencies.json）: 決まった5つの事務所だけ・出どころが事務所の公式サイト・生年月日などの項目は無い",
      len(AGENCY_SITES) == 5 and all(_agency_ok(r) for r in _agency_rows) and not any(k in r for r in _agency_rows for k in ("birthday", "birth", "blood", "pref", "hobby")),
      [r.get("name") for r in _agency_rows if not _agency_ok(r)][:3])
bad_agency_pages = []
shown_agency = 0
for pth in actress_pages:
    text = read(pth)
    m = re.search(r'<h1 class="hero-title">(.*?)</h1>', text, re.S)
    h1_text = htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""
    name = h1_text[: -len("の新作・出演作品")] if h1_text.endswith("の新作・出演作品") else ""
    row = agency_by_name.get(name)
    has_row = '<dt class="spec-term">所属</dt>' in text
    here = []
    if has_row != bool(row):
        here.append(f"所属の行の有無が、データと合わない（行={has_row}）")
    if row:
        shown_agency += 1
        dd = re.search(r'<dt class="spec-term">所属</dt>\s*<dd class="spec-desc">(.*?)</dd>', text, re.S)
        a_ = tags(dd.group(1), "a") if dd else []
        if not a_ or a_[0].get("href") != row["source"] or a_[0].get("target") != "_blank" or not {"nofollow", "noopener", "noreferrer"} <= set(a_[0].get("rel", "").split()) or strip_tags(dd.group(1)).strip() != AGENCY_SITES[row["agency"]][0]:
            here.append("所属のリンク（出どころ・名前・属性）")
        want_sns = ([f"https://x.com/{row['x']}"] if re.fullmatch(r"[A-Za-z0-9_]{1,15}", str(row.get("x", ""))) else []) + ([f"https://www.instagram.com/{row['instagram']}/"] if re.fullmatch(r"[A-Za-z0-9_.]{1,30}", str(row.get("instagram", ""))) else [])
        sns = re.search(r'<dt class="spec-term">SNS</dt>\s*<dd class="spec-desc sns-links">(.*?)</dd>', text, re.S)
        got_sns = [t for t in tags(sns.group(1), "a")] if sns else []
        if [t.get("href") for t in got_sns] != want_sns or any(t.get("target") != "_blank" or not {"nofollow", "noopener", "noreferrer"} <= set(t.get("rel", "").split()) for t in got_sns):
            here.append(("SNSのリンク", [t.get("href") for t in got_sns], want_sns))
        if f"所属とSNSは、所属事務所（{AGENCY_SITES[row['agency']][0]}）の公式サイトに載っている情報です" not in text or "時点" not in text:
            here.append("出どころの注記")
    elif '<dt class="spec-term">SNS</dt>' in text:
        here.append("所属の無い人に SNS の行がある")
    if here:
        bad_agency_pages.append((name or os.path.relpath(pth, DIST), here))
check(f"出演者ページの所属事務所とSNS（{shown_agency}人）: データのとおり・出どころの事務所のページへのリンク・SNS は x.com / instagram.com のアカウントだけ・出どころの注記",
      not bad_agency_pages, bad_agency_pages[:3])
warn("所属事務所が付いた出演者ページがある（データがあれば出る）", shown_agency > 0 or not agency_by_name)

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
check("女優検索の索引（/data/actresses-index.json）がある・形が正しい（顔写真の置き場所・全作品のURLの形つき）",
      isinstance(act_index, dict) and isinstance(act_index.get("actresses"), list) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(act_index.get("generated", "")))
      and act_index.get("img") == "https://pics.dmm.co.jp/mono/actjpgs/thumbnail/"
      and (act_index.get("list") == "" or (str(act_index.get("list")).count("{ID}") == 1 and fanza_https(str(act_index.get("list")).replace("{ID}", "1"), FANZA_LINK))), str(act_index)[:120])
rows = act_index["actresses"] if isinstance(act_index, dict) and isinstance(act_index.get("actresses"), list) else []
ALLOWED_KEYS = {"n", "r", "id", "s", "k", "i", "a", "h", "b", "c", "wa", "hi", "l", "g"}  # g: 所属事務所のキー（事務所の公式サイトから）
DIRECTORY = os.path.join(ROOT, "site", "src", "data", "actress_directory.json")
dir_raw = load_json(DIRECTORY) if os.path.isfile(DIRECTORY) else None
dir_ids = {str(r.get("id")) for r in (dir_raw.get("rows") if isinstance(dir_raw, dict) and isinstance(dir_raw.get("rows"), list) else []) if isinstance(r, dict)}
profile_ids = {str(r.get("id")) for r in profiles.values()}
page_slugs = {os.path.basename(os.path.dirname(pth)) for pth in actress_pages}
row_by_name = {}
for r in rows:
    if isinstance(r, dict) and r.get("s"):
        row_by_name[str(r.get("n"))] = r
# 索引に載るのは「名簿（FANZA公式の出演者検索の一覧）」＋「プロフィールを取得済みの人」＋「専用ページのある人（プロフィールが無くても、名前・作品数で探せるように）」。
# 同じ名前の別人は id が違う別の行（専用ページは、作品の出演者と同じ人の行にだけ付く）
row_ids = [str(r.get("id")) for r in rows if isinstance(r, dict) and r.get("id")]
check("索引に、同じ id の重複が無い・専用ページ（s）の重複も無い", len(row_ids) == len(set(row_ids)) and len([r for r in rows if isinstance(r, dict) and r.get("s")]) == len({r.get("s") for r in rows if isinstance(r, dict) and r.get("s")}))
missing_page_rows = [n for n, slug in page_name_slug.items() if n not in row_by_name or row_by_name[n].get("s") != slug]
check("専用ページのある出演者は、全員が索引にいて、s（ページの識別子）が実際のページと合っている", not missing_page_rows, missing_page_rows[:3])
stray_rows = [r.get("n") for r in rows if isinstance(r, dict) and not (r.get("s") or str(r.get("id")) in dir_ids or str(r.get("id")) in profile_ids)]
check(f"索引の全員が、名簿（{len(dir_ids)}人）・取得済みのプロフィール・専用ページのどれかにいる（出どころの無い行が無い）", not stray_rows, stray_rows[:3])


def int_in(v, lo, hi):
    return v is None or (isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi)


bad_rows = []
for r in rows:
    here = []
    if not isinstance(r, dict) or not set(r) <= ALLOWED_KEYS or "n" not in r:
        bad_rows.append((str(r)[:60], ["項目が決まった形ではない"]))
        continue
    if not str(r["n"]).strip():
        here.append("名前が空")
    if "id" in r and not re.fullmatch(r"\d{1,12}", str(r["id"])):
        here.append("id が数字でない")
    if "k" in r and not (isinstance(r["k"], int) and r["k"] >= 1):
        here.append("作品数が1以上の整数でない")
    if r.get("s") and (not re.fullmatch(r"[0-9a-f]{10}", str(r["s"])) or r["s"] not in page_slugs or r.get("k", 0) < 2):
        here.append("s のページが存在しない・作品数が2本未満")
    if r.get("i") and not (re.fullmatch(r"[a-z0-9_]{1,60}", str(r["i"])) or fanza_https(r["i"], DMM)):
        here.append("顔写真が、ファイル名でも FANZA(DMM) の https でもない")
    if r.get("l") and not fanza_https(r["l"], FANZA_LINK):
        here.append("全作品リンクが FANZA の https ではない")
    if not (int_in(r.get("a"), 18, 80) and int_in(r.get("h"), 120, 210) and int_in(r.get("b"), 50, 160) and int_in(r.get("wa"), 40, 130) and int_in(r.get("hi"), 50, 160)):
        here.append("年齢・身長・サイズが範囲外")
    if "c" in r and not (isinstance(r["c"], str) and re.fullmatch(r"[A-Z]", r["c"])):
        here.append("カップが英字1文字でない")
    if any(v is None or v == "" for v in r.values()):
        here.append("値が空の項目が入っている（無い値は、項目ごと入れない）")
    if here:
        bad_rows.append((r.get("n"), here))
check("索引の各項目: 決まった項目だけ・ページの有無が作品数と合う・URLがFANZAのhttps・数字が範囲内・空の項目なし", not bad_rows, bad_rows[:3])
check("索引はこのサイトの作品の多い順", all(rows[i].get("k", 0) >= rows[i + 1].get("k", 0) for i in range(len(rows) - 1)) if rows and all(isinstance(r, dict) for r in rows) else True)
check("索引の大きさが 3MB 以内（女優検索のページを開くたびにダウンロードされるため）", (not os.path.isfile(idx_path)) or os.path.getsize(idx_path) <= 3 * 1024 * 1024, os.path.getsize(idx_path) if os.path.isfile(idx_path) else 0)
if os.path.isfile(search_page):
    stext = read(search_page)
    check("検索のスクリプト（actress-search.js）が公開されている", os.path.isfile(os.path.join(DIST, "actress-search.js")))
    if rows:
        section = [t for t in tags(stext, "section") if t.get("id") == "actress-search"]
        check("検索の部品がある（最初は隠れていて、索引のURLを持つ）", bool(section) and "hidden" in section[0] and section[0].get("data-index") == "/data/actresses-index.json" and 'src="/actress-search.js"' in stext, section[:1])
        names = {t.get("name") for tag in ("input", "select") for t in tags(stext, tag)}
        need = {"q", "cup", "site", "face", "sort", "bust", "waist", "hip"} | {f"{k}_{e}" for k in ("age", "height") for e in ("min", "max")}
        check("検索の入力欄が揃っている（名前・年齢/身長の下限と上限・バスト/ウエスト/ヒップの幅・カップ・このサイトの作品・顔写真・並び順）", need <= names, sorted(need - names))
        # スリーサイズは、数字を入れる欄ではなく、幅をタップで選ぶ（運営者の希望。2026-10-05）。幅は site/src/lib/profiles.js の SIZE_BUCKETS
        _buckets_src = read(os.path.join(ROOT, "site", "src", "lib", "profiles.js"))
        size_buckets = {k: re.findall(r"'([^']*)'", v) for k, v in re.findall(r"(bust|waist|hip): \[([^\]]*)\]", re.search(r"export const SIZE_BUCKETS = \{(.*?)\};", _buckets_src, re.S).group(1))}
        bad_size = []
        for key_, idx_key in (("bust", "b"), ("waist", "wa"), ("hip", "hi")):
            got_ = [t.get("value") for t in tags(stext, "input") if t.get("name") == key_]
            if got_ != size_buckets.get(key_) or any(t.get("type") != "checkbox" for t in tags(stext, "input") if t.get("name") == key_):
                bad_size.append((key_, got_))
            counts_ = []
            for b_ in size_buckets.get(key_, []):
                lo_, hi_ = (None if v == "" else int(v) for v in b_.split("-"))
                counts_.append(sum(1 for r in rows if isinstance(r, dict) and isinstance(r.get(idx_key), int) and (lo_ is None or r[idx_key] >= lo_) and (hi_ is None or r[idx_key] <= hi_)))
            common_ = size_buckets[key_][counts_.index(max(counts_))] if counts_ and max(counts_) > 0 else ""
            label_ = {"bust": "バスト", "waist": "ウエスト", "hip": "ヒップ"}[key_]
            want_hint = f"いちばん多いのは{common_.replace('-', '〜')}cm" if common_ else ""
            legend_ = re.search(r'<fieldset class="as-cups as-sizes">\s*<legend class="as-range-label">\s*%s（cm・いくつでも選べます）(.*?)</legend>' % label_, stext, re.S)
            if not legend_ or strip_tags(legend_.group(1)).strip() != want_hint:
                bad_size.append((key_, "目安", strip_tags(legend_.group(1)).strip() if legend_ else None, want_hint))
            if any(t.get("name") in (f"{key_}_min", f"{key_}_max") for t in tags(stext, "input")):
                bad_size.append((key_, "数字の欄が残っている"))
        check("スリーサイズは、幅（〜79・80〜84 など）をタップで選ぶ（数字を入れる欄は無い）。いちばん人数の多い幅を、目安として添える", not bad_size, bad_size[:3])
        sort_sel = re.search(r'<select name="sort">(.*?)</select>', stext, re.S)
        values = [t.get("value", "") for t in tags(sort_sel.group(1) if sort_sel else "", "option")]
        bad_values = [v for v in values if v not in ("works", "bust", "cup", "young", "old", "tall", "short", "waist", "hip", "newest", "name")]
        check("並び順の値が、スクリプトの読める形だけ", not bad_values and len(values) == 11, bad_values[:5])
        # 所属事務所で絞り込む（索引に所属の分かる人がいるときだけ）。選択肢は「指定なし」と、索引の agencies の事務所（人数の多い順）
        ag_sel = re.search(r'<select name="ag">(.*?)</select>', stext, re.S)
        idx_agencies = act_index.get("agencies", {}) if isinstance(act_index, dict) and isinstance(act_index.get("agencies"), dict) else {}
        ag_counts = {}
        for r in rows:
            if isinstance(r, dict) and r.get("g"):
                ag_counts[r["g"]] = ag_counts.get(r["g"], 0) + 1
        want_opts = [("", "指定なし")] + [(k_, f"{idx_agencies.get(k_, k_)}（{c_}人）") for k_, c_ in sorted(ag_counts.items(), key=lambda kv: (-kv[1], idx_agencies.get(kv[0], kv[0])))]
        got_opts = [(t_.get("value", ""), strip_tags(o_).strip()) for t_, o_ in zip(tags(ag_sel.group(1), "option"), re.findall(r"<option\b[^>]*>(.*?)</option>", ag_sel.group(1), re.S))] if ag_sel else []
        check("所属事務所の選択肢（所属の分かる人がいるときだけ。「指定なし」と、事務所ごとの人数）", got_opts == want_opts if ag_counts else not ag_sel, (got_opts[:3], want_opts[:3]))
        bad_g = [r.get("n") for r in rows if isinstance(r, dict) and r.get("g") and (r["g"] not in idx_agencies or r["g"] not in AGENCY_SITES or agency_by_name.get(r.get("n"), {}).get("agency") != r["g"])]
        check("索引の所属（g）は、決まった事務所で、データのとおり（同じ名前の人がいれば付けない）", not bad_g and set(idx_agencies) <= set(AGENCY_SITES), bad_g[:3])
        cup_values = [t.get("value") for t in tags(stext, "input") if t.get("name") == "cup"]
        check("カップの選択肢: A〜K と L以上（L+）", cup_values == list("ABCDEFGHIJK") + ["L+"], cup_values)
        ids = {t.get("id") for tag in ("ul", "p", "button", "section") for t in tags(stext, tag)}
        check("検索結果の表示先（#as-list・#as-count・#as-more・#as-note）がある", {"as-list", "as-count", "as-more", "as-note"} <= ids, sorted({"as-list", "as-count", "as-more", "as-note"} - ids))
    else:
        check("索引が空のときは、検索の部品を出さない", 'id="actress-search"' not in stext and 'src="/actress-search.js"' not in stext)
    static_rows = len([t for t in tags(stext, "li") if has_class(t, "actress-row")])
    index_limit = int(re.search(r"export const INDEX_LIST_LIMIT = (\d+);", read(os.path.join(ROOT, "site", "src", "config.js"))).group(1))
    check(f"JavaScriptが使えないとき用の一覧に、専用ページのある出演者がいる（{len(actress_pages)}人。多いときは作品数の多い順に{index_limit}人まで）", static_rows == min(len(actress_pages), index_limit) and any(t.get("id") == "actress-static" for t in tags(stext, "section")), (static_rows, len(actress_pages)))
    check("検索の注意書き（載っていない人は絞り込みで外れる・データのある人数・FANZA公式のデータ）が、ページにある", (not rows) or ("結果に出ません" in stext and "いま探せる" in stext and "FANZA公式" in stext))

print("\n■ トップ: きょうの新着人気TOP3・きょうの話題")
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
# トップの検索欄: 作品検索のページ（/search/）へ、キーワード（q）を送る。JavaScript が無くても動く（ふつうのフォーム）
hero_forms = [t for t in tags(home_html, "form") if has_class(t, "hero-search")]
check("トップに検索欄があり、/search/ にキーワード（q）を送る", len(hero_forms) == 1 and hero_forms[0].get("action") == "/search/" and hero_forms[0].get("method", "get").lower() == "get" and any(t.get("name") == "q" for t in tags(home_html, "input")), hero_forms)
check("トップの見出しは「きょうのFANZA新作」で、更新した日付が入っている", re.search(r'<h1 class="today-title">きょうのFANZA新作</h1>', home_html) is not None and f'<time datetime="{JST_TODAY}">' in home_html)

# TOP3: この1週間に発売された作品を、新着の人気順に6本（画面に出すのは先頭の3本）。まだ無いときは売れ筋（ranking.json）で代わりにする
_top_from = (datetime.date.fromisoformat(JST_TODAY) - datetime.timedelta(days=7)).isoformat()
want_top = sorted((c for c in everything if c in pop_new and _top_from <= str(everything[c]["date"])[:10] <= JST_TODAY),
                  key=lambda c: (pop_new[c], -int(str(everything[c]["date"])[:10].replace("-", "")), c))[:6]
home_sections = [t for t in tags(home_html, "section") if t.get("id") == "ranking"]
medal_cells = [(m.group(1), m.group(2), m.group(3)) for m in re.finditer(r'<li class="medal-cell([^"]*)"([^>]*)>(.*?)</li>', home_html, re.S)]
top_rows = [{"cid": c, "url": everything[c].get("url"), "title": everything[c]["title"], "vr": is_vr_raw(everything[c])} for c in want_top] if want_top else (
    [{"cid": str(r["cid"]), "url": r["url"], "title": str(r["title"]).strip(), "vr": r.get("vr") is True or bool(re.search(r"【[^】]*VR[^】]*】", str(r["title"]), re.I)) or (str(r["cid"]) in valid and is_vr_raw(valid[str(r["cid"])]))} for r in rk_items] if rk_fresh else [])
top_hrefs = []
if top_rows:
    title_ = "きょうの新着人気TOP3" if want_top else "売れ筋TOP3"
    check(f"TOP3の欄がある（見出し「{title_}」）・本数が合う（{len(top_rows)}本）", len(home_sections) == 1 and f'id="ranking-title" class="today-sec-title">{title_}</h2>' in home_html and len(medal_cells) == len(top_rows), (len(home_sections), len(medal_cells), len(top_rows)))
    podium = next((t for t in tags(home_html, "ol") if has_class(t, "medals")), None)
    shown_n = min(len(top_rows), 3)
    check("TOP3の並びに、出す本数（data-show=3）・見えている本数（data-visible）の印がある（VR作品を隠したとき、vr-filter.js が付け直す）", bool(podium) and has_class(podium, "rank-podium") and podium.get("data-show") == "3" and podium.get("data-visible") == str(shown_n), podium)
    cell_attrs = [tags(f'<li class="medal-cell{cls}"{attrs}>', "li")[0] for cls, attrs, _ in medal_cells]
    check("TOP3: 先頭の3本だけが見えていて、4位以降は rank-off（VR作品を隠したとき、差し替えに使う）。各マスに順位（data-rank）と、先頭の3本にメダルの色（data-place 1 金・2 銀・3 銅）",
          [has_class(a, "rank-off") for a in cell_attrs] == [i >= 3 for i in range(len(cell_attrs))] and [a.get("data-rank") for a in cell_attrs] == [str(i) for i in range(1, len(cell_attrs) + 1)]
          and [a.get("data-place") for a in cell_attrs] == [str(i + 1) if i < 3 else None for i in range(len(cell_attrs))], [(a.get("class"), a.get("data-rank"), a.get("data-place")) for a in cell_attrs])
    badges = [re.search(r'<span class="medal rank-badge">(\d+)位</span>', inner) for _, _, inner in medal_cells]
    check("TOP3: メダルに順位（1位から順に）", [b.group(1) if b else None for b in badges] == [str(i) for i in range(1, len(medal_cells) + 1)])
    bad_link, bad_order, bad_vr = [], [], []
    for (cls, attrs, inner), row in zip(medal_cells, top_rows):
        a_ = next((t for t in tags(inner, "a") if has_class(t, "medal-card")), {})
        href = a_.get("href", "")
        top_hrefs.append(href)
        if href == f"/item/{row['cid']}/":
            if row["cid"] not in paged:
                bad_link.append((row["cid"], href))
        elif href != row["url"] or not SPONSORED <= set(a_.get("rel", "").split()) or a_.get("target") != "_blank":
            bad_link.append((row["cid"], href))
        elif row["cid"] in paged:
            bad_link.append((row["cid"], "作品ページがあるのにFANZAへ"))
        t_ = re.search(r'<span class="medal-title">(.*?)</span>', inner, re.S)
        if not t_ or htmllib.unescape(re.sub(r"<[^>]+>", "", t_.group(1))) != row["title"].strip():
            bad_order.append(row["cid"])
        if ('data-vr="true"' in attrs) != row["vr"]:
            bad_vr.append((row["cid"], row["vr"]))
    check("TOP3: 各作品のリンクは、作品ページがあれば作品ページ・無ければFANZA（広告のリンクの属性つき）", not bad_link, bad_link[:3])
    check("TOP3: 並び（作品）が、順位のファイルから決めたものと同じ", not bad_order, bad_order[:3])
    check("TOP3: VR作品にだけ data-vr が付いている（VR作品を隠すと、次の順位から差し替える）", not bad_vr, bad_vr[:3])
    check("TOP3の見出しの横に、「VRを除く」の注記（最初は隠れている。VR作品を隠したとき、JavaScriptが出す）がある", re.search(r'<span class="rank-vr-note" hidden>｜VRを除く</span>', home_html) is not None)
    check("「人気順」と書いてある（FANZAのデイリーランキングと同じとは書かない）", "人気順" in home_html and "デイリーランキング" not in home_html)
    check("TOP3の欄は、トップのはじめのほう（発売中の新作より前）にあり、ランキングのページ（新着・全体）への案内がある", home_html.find('id="ranking"') < home_html.find('id="released"') and 'class="today-links"' in home_html and 'href="/ranking/"' in home_html and 'href="/ranking/all/"' in home_html)
else:
    check("新着の人気順も売れ筋（新しいもの）も無いときは、TOP3の欄を出さない", not home_sections and not medal_cells and 'href="#ranking"' not in home_html)

# きょうの数字（発売本数の欄）は、運営者の判断で外した（2026-10-05。today.json の本数は、いまは画面に出さない）
check("トップに「きょうの数字」（発売本数の欄）が無い", 'id="stats"' not in home_html and "FANZA動画（ビデオ）全体の本数" not in home_html)

# きょうの話題: 種類ごとの札・リンク先（作品ページ・女優のページ・まとめ記事・セールのページ・FANZA）
TOPIC_LABELS = {"rise": "急上昇", "today": "きょう発売", "upcoming": "予約で人気", "entry": "予約に初登場", "debut": "デビュー作", "actress": "人気の女優", "weekly": "週のまとめ", "salenew": "セール開始", "sale": "もうすぐ終わる"}
# 話題の作品がVR作品のときは、すぐ後ろに、同じ種類のVRでない次の作品（.topic-alt。「VR作品を隠す」のときだけ出る）が付くことがある
topic_all = [(m.group(1), bool(m.group(2)), m.group(3), m.group(4)) for m in re.finditer(r'<li class="topic topic-([a-z]+)( topic-alt)?"([^>]*)>(.*?)</li>', home_html, re.S)]
topic_cells = [(k, a, inner) for k, alt, a, inner in topic_all if not alt]
bad_alt = [k for n, (k, alt, a, _) in enumerate(topic_all) if alt and ('data-vr="true"' in a or n == 0 or topic_all[n - 1][0] != k or topic_all[n - 1][1] or 'data-vr="true"' not in topic_all[n - 1][2])]
check(f"きょうの話題: VR作品の話題の繰り上げ（{sum(1 for x in topic_all if x[1])}件）は、VR作品の話題のすぐ後ろで同じ種類・VRの印なし", not bad_alt, bad_alt[:3])
bad_topic = []
for kind, attrs, inner in [(k, a, inner) for k, _, a, inner in topic_all]:
    a_ = next((t for t in tags(inner, "a") if has_class(t, "topic-link")), {})
    href = a_.get("href", "")
    label = re.search(r'<span class="topic-tag">([^<]*)</span>', inner)
    if kind not in TOPIC_LABELS or not label or label.group(1) != TOPIC_LABELS[kind]:
        bad_topic.append((kind, "札"))
    elif href.startswith("/"):
        if not os.path.isfile(page_file(href)) or (kind not in ("actress", "weekly", "sale", "salenew") and not href.startswith("/item/")):
            bad_topic.append((kind, href))
        elif kind in ("sale", "salenew") and not re.fullmatch(r"/sale/#sale-\d+", href):  # セールの話題は、セールのページの、その特集の見出しへ
            bad_topic.append((kind, href))
    elif not (fanza_https(href, FANZA_LINK) and SPONSORED <= set(a_.get("rel", "").split()) and a_.get("target") == "_blank") or kind in ("weekly", "sale", "salenew"):
        bad_topic.append((kind, href))
    if href in top_hrefs[:3]:
        bad_topic.append((kind, "TOP3と同じ作品"))
    if ("data-sale-end" in attrs) != (kind in ("sale", "salenew")) or (kind in ("sale", "salenew") and not re.search(r'data-sale-end="\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:59\+09:00"', attrs)):
        bad_topic.append((kind, "セールの終わり"))
check(f"きょうの話題（{len(topic_cells)}件。8件まで）: 種類ごとの札と、リンク先（サイトの中はあるページ・外はFANZAで広告のリンクの属性つき）。TOP3の作品は出さない",
      len(topic_cells) <= 8 and not bad_topic and (not topic_cells or 'id="topics"' in home_html), bad_topic[:3])
# セールの話題の見出しは、FANZAの特集の名前そのまま（「今月のおすすめ30％OFF」など）なので、評価の言葉の検査からは外す
topic_text = " ".join(re.sub(r"<[^>]+>", "", re.sub(r'<span class="topic-title">.*?</span>', "", inner, flags=re.S) if k in ("sale", "salenew") else inner) for k, _, _, inner in topic_all)
check("きょうの話題: 評価の言葉を書かない（データで決まった形の文だけ）", not re.search(r"おすすめ|話題作|必見|最高傑作|大人気|神作", topic_text))
if any(k in ("sale", "salenew") for k, _, _ in topic_cells):
    check("きょうの話題に、セール開始・もうすぐ終わるセールがあるときは、終わったら隠すスクリプト（sale.js）がある", 'src="/sale.js"' in home_html)
warn("きょうの話題が、トップにある（データがそろっていれば出る）", bool(topic_cells) or not pop_new)

# 女優の顔写真と誕生日の月日（site/src/lib/data.js の faceOfName・birthOfName と同じ決まり）: プロフィール（同じ名前で id が1つの人）を先に、
# 無ければ名簿（同じ名前の人が1人だけ）。誕生日は、年齢が18〜80歳になるときだけ
def _age_ok(b):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(b or "")):
        return False
    try:
        bd = datetime.date.fromisoformat(b)
    except ValueError:
        return False
    t = datetime.date.fromisoformat(JST_TODAY)
    age = t.year - bd.year - ((t.month, t.day) < (bd.month, bd.day))
    return 18 <= age <= 80


_prof_rows = [r for r in (act_raw.get("actresses", []) if isinstance(act_raw, dict) else []) if isinstance(r, dict) and re.fullmatch(r"\d{1,12}", str(r.get("id", "")).strip()) and str(r.get("name", "")).strip()]
_prof_ids = {}
for r in _prof_rows:
    _prof_ids.setdefault(str(r["name"]).strip(), set()).add(str(r["id"]).strip())
_prof_by = {}
for r in _prof_rows:
    n_ = str(r["name"]).strip()
    if len(_prof_ids[n_]) == 1 and n_ not in _prof_by:
        _prof_by[n_] = r
_dir_rows = [r for r in (dir_raw.get("rows") if isinstance(dir_raw, dict) and isinstance(dir_raw.get("rows"), list) else []) if isinstance(r, dict) and str(r.get("name", "")).strip() and re.fullmatch(r"\d{1,12}", str(r.get("id", "")).strip())]
_dir_count = {}
for r in _dir_rows:
    _dir_count[str(r["name"]).strip()] = _dir_count.get(str(r["name"]).strip(), 0) + 1
_dir_by = {str(r["name"]).strip(): r for r in _dir_rows if _dir_count[str(r["name"]).strip()] == 1}


def has_face_name(n):
    p_ = _prof_by.get(n)
    if p_ and (fanza_https(p_.get("image_large"), DMM + ["fanza.co.jp"]) or fanza_https(p_.get("image_small"), DMM + ["fanza.co.jp"])):
        return True
    d_ = _dir_by.get(n)
    return bool(d_ and re.fullmatch(r"[a-z0-9_]{1,60}", str(d_.get("img") or "")))


def birth_md(n):
    for src in (_prof_by.get(n), _dir_by.get(n)):
        if src and _age_ok(src.get("birthday")):
            return src["birthday"][5:10]
    return ""


# いま人気の女優（site/src/lib/topics.js の hotActresses と同じ数え方）: この1週間の発売で、新着の人気順が100位までの作品
# （出演者が1〜4人の作品だけ）に、101−順位の点を足す。顔写真がある人だけ、上から3人
def hot_names(exclude_vr):
    board = {}
    for c in sorted((c for c in everything if c in pop_new and pop_new[c] <= 100 and _top_from <= str(everything[c]["date"])[:10] <= JST_TODAY),
                    key=lambda c: (pop_new[c], -int(str(everything[c]["date"])[:10].replace("-", "")), c))[:100]:
        x = everything[c]
        if exclude_vr and is_vr_raw(x):
            continue
        cast = list(dict.fromkeys(a for a in (x.get("actress") or []) if a))
        if not 1 <= len(cast) <= 4:
            continue
        for n in cast:
            sc, best = board.get(n, (0, pop_new[c]))
            board[n] = (sc + 101 - pop_new[c], min(best, pop_new[c]))
    return [n for n, _ in sorted(((n, v) for n, v in board.items() if has_face_name(n)), key=lambda kv: (-kv[1][0], kv[1][1], kv[0]))[:3]]


def hot_list(cls):
    m = re.search(r'<ol class="%s">(.*?)</ol>' % cls, home_html, re.S)
    return [htmllib.unescape(re.sub(r"<[^>]+>", "", n)) for n in re.findall(r'<span class="hot-name"><span class="visually-hidden">[^<]*</span>(.*?)</span>', m.group(1), re.S)] if m else None


want_hot, want_hot_novr = hot_names(False), hot_names(True)
if want_hot:
    got = hot_list("hot") if want_hot == want_hot_novr else hot_list("hot hot-all")
    got_novr = None if want_hot == want_hot_novr else hot_list("hot hot-novr")
    check(f"いま人気の女優: {len(want_hot)}人が、新着の人気順の点の順に並ぶ（オムニバスの作品は数えない）", 'id="hot"' in home_html and got == want_hot, (got, want_hot))
    check("いま人気の女優: VR作品を隠すときの並び（VR作品を数えない）は、ちがうときだけ、もう1つ用意する", (got_novr is None and want_hot == want_hot_novr) or got_novr == want_hot_novr, (got_novr, want_hot_novr))
    check("いま人気の女優: 「顔」という言葉は使わず「いま人気の女優」（運営者の希望）", 'id="hot-title" class="today-sec-title">いま人気の女優</h2>' in home_html)
    hot_block = re.search(r'<section id="hot".*?</section>', home_html, re.S)
    check("いま人気の女優: 全員に顔写真がある・選んだ理由（人気作○本・最高○位）は書かない（運営者の希望）", bool(hot_block) and hot_block.group(0).count('class="face-img"') == hot_block.group(0).count('class="hot-cell"') and "人気作" not in hot_block.group(0) and "section-note" not in hot_block.group(0))
else:
    check("人気の作品が無いときは、いま人気の女優の欄を出さない", 'id="hot"' not in home_html)

# 人気のジャンル（いま人気の女優の真下）: 同じ数え方を、ジャンルのページの一覧（TAG_PAGE_GENRES。ベスト・総集編は除く）のジャンルごとに足して3つ
_tag_genres = re.findall(r"'([^']+)'", re.search(r"export const TAG_PAGE_GENRES = \[(.*?)\];", read(os.path.join(ROOT, "site", "src", "config.js")), re.S).group(1))
_gboard = {}
for c in sorted((c for c in everything if c in pop_new and pop_new[c] <= 100 and _top_from <= str(everything[c]["date"])[:10] <= JST_TODAY),
                key=lambda c: (pop_new[c], -int(str(everything[c]["date"])[:10].replace("-", "")), c))[:100]:
    for g in dict.fromkeys(everything[c].get("genres") or []):
        if g in _tag_genres and g != "ベスト・総集編":
            sc, n = _gboard.get(g, (0, 0))
            _gboard[g] = (sc + 101 - pop_new[c], n + 1)
want_genres = [g for g, _ in sorted(_gboard.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))[:3]]
genre_m = re.search(r'<ol class="hot-genres">(.*?)</ol>', home_html, re.S)
got_genres = [htmllib.unescape(re.sub(r"<[^>]+>", "", n)) for n in re.findall(r'<span class="genre-name"><span class="visually-hidden">[^<]*</span>(.*?)</span>', genre_m.group(1), re.S)] if genre_m else []
if want_genres:
    check(f"人気のジャンル: {len(want_genres)}つが、いま人気の女優と同じ数え方の順に並ぶ（ジャンルのページの一覧のジャンルだけ）・いま人気の女優の真下", got_genres == want_genres and home_html.find('id="hot"') < home_html.find('id="genres"') < home_html.find('id="topics"'), (got_genres, want_genres))
    bad_glink = [h for h in re.findall(r'<a class="genre-link" href="([^"]+)"', genre_m.group(1)) if not (h.startswith("/tag/") and os.path.isfile(page_file(h))) and not h.startswith("/search/?tag=")]
    check("人気のジャンル: タップで、ジャンルのページ（無ければ作品検索のジャンル絞り込み）へ", not bad_glink, bad_glink[:3])
else:
    check("人気のジャンルが無いときは、欄を出さない", 'id="genres"' not in home_html)

# 発売中の新作の、きょうの日付のすぐ下のコーナー（運命の作品・今週のデビュー作・誕生日の近い女優。運営者の希望。2026-10-05）
rel_start = home_html.find('id="released"')
days_in_rel = [m.start() for m in re.finditer(r'<section class="day"', home_html) if m.start() > rel_start and (home_html.find('id="upcoming"') < 0 or m.start() < home_html.find('id="upcoming"'))]
corner_at = home_html.find('<div class="corner"')
if corner_at >= 0:
    check("おすすめのコーナーは、発売中の新作の、いちばん新しい日付のすぐ下（次の日付の上）", len(days_in_rel) >= 1 and days_in_rel[0] < corner_at and (len(days_in_rel) < 2 or corner_at < days_in_rel[1]), (days_in_rel[:2], corner_at))

# 運命の作品（スロットで3本。ひとことコメントのある・作品ページのある・発売済みの人気作。未成年を連想させるタイトルは入れない）
gacha_m = re.search(r'<script type="application/json" id="gacha-data">(.*?)</script>', read_raw(index_path), re.S)
if gacha_m:
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import claude_comments as _cc
    gacha_rows = json.loads(gacha_m.group(1))
    bad_gacha = [r.get("c") for r in gacha_rows if r.get("c") not in paged or not has_comment(everything.get(r.get("c"), {})) or str(everything[r["c"]]["date"])[:10] > JST_TODAY
                 or _cc.title_block_reason(everything[r["c"]]) == "minor" or bool(r.get("v")) != is_vr_raw(everything[r["c"]]) or bool(r.get("o")) != is_solo_raw(everything[r["c"]]) or not fanza_https(r.get("i"), DMM)]
    check(f"運命の作品: 候補（{len(gacha_rows)}本。80本まで）は、ひとことコメントと作品ページのある発売済みの作品だけ・未成年を連想させるタイトルは入れない・VR・単体作品の印が合う", 3 <= len(gacha_rows) <= 80 and not bad_gacha, bad_gacha[:3])
    gacha_sec = re.search(r'<section id="gacha".*?</section>', home_html, re.S)
    check("運命の作品: 見出し「運命の作品」・窓が3つ・「まわす」ボタン・最初は隠れている（JavaScript が出す）・スクリプト（gacha.js）がある",
          bool(gacha_sec) and 'id="gacha-title" class="corner-title">運命の作品</h3>' in gacha_sec.group(0) and gacha_sec.group(0).count('class="reel"') == 3 and ">まわす</button>" in gacha_sec.group(0)
          and re.search(r'<section id="gacha"[^>]*\bhidden\b', home_html) is not None and 'src="/gacha.js"' in home_html and os.path.isfile(os.path.join(DIST, "gacha.js")) and corner_at < home_html.find('id="gacha"'))
    check("運命の作品: ページに入れたデータの中に、タグの始まり（<）が無い", "<" not in gacha_m.group(1))
else:
    check("運命の作品の候補が無いときは、欄もスクリプトも出さない", 'id="gacha"' not in home_html and 'src="/gacha.js"' not in home_html)

# 今週のデビュー作: きょうまでの7日間に発売された「デビュー作品」を、新着の人気順に6本（出すのは3本。残りは差し替え用）
_wk_from = (datetime.date.fromisoformat(JST_TODAY) - datetime.timedelta(days=6)).isoformat()
want_debut = sorted((c for c in everything if "デビュー作品" in (everything[c].get("genres") or []) and _wk_from <= str(everything[c]["date"])[:10] <= JST_TODAY),
                    key=lambda c: (pop_new.get(c, float("inf")), -int(str(everything[c]["date"])[:10].replace("-", "")), c))[:6]
debut_cells = [(m.group(1), m.group(2), m.group(3)) for m in re.finditer(r'<li class="debut-cell([^"]*)"([^>]*)>(.*?)</li>', home_html, re.S)]
if want_debut:
    got_debut = []
    for cls, attrs, inner in debut_cells:
        a_ = next((t for t in tags(inner, "a") if has_class(t, "debut-card")), {})
        h = a_.get("href", "")
        m_ = re.match(r"/item/([^/]+)/$", h)
        got_debut.append(m_.group(1) if m_ else next((c for c in want_debut if everything[c].get("url") == h), h))
    check(f"今週のデビュー作: {len(want_debut)}本が人気順に並び、出すのは3本（残りは rank-off）・VR・単体作品の印が合う", got_debut == want_debut and [" rank-off" in cls for cls, _, _ in debut_cells] == [i >= 3 for i in range(len(debut_cells))]
          and all(('data-vr="true"' in attrs) == is_vr_raw(everything[c]) and ('data-solo="true"' in attrs) == is_solo_raw(everything[c]) for (cls, attrs, _), c in zip(debut_cells, want_debut)), (got_debut, want_debut))
else:
    check("今週のデビュー作が無いときは、欄を出さない", 'id="debuts"' not in home_html)

# 誕生日の近い女優: このサイトに作品があり、顔写真と誕生日（FANZA公式）が分かる人で、きょうから14日のうちに誕生日が来る人を、近い順に3人
_works = {}
for x in everything.values():
    for n in dict.fromkeys(a for a in (x.get("actress") or []) if a):
        _works[n] = _works.get(n, 0) + 1


def _days_until(md):
    t = datetime.date.fromisoformat(JST_TODAY)
    for y in (t.year, t.year + 1):
        leap = (y % 4 == 0 and y % 100 != 0) or y % 400 == 0
        d = datetime.date.fromisoformat(f"{y}-{'02-28' if md == '02-29' and not leap else md}")
        if d >= t:
            return (d - t).days
    return None


want_bday = sorted(((n, _days_until(birth_md(n)), w) for n, w in _works.items() if birth_md(n) and has_face_name(n)), key=lambda r: (r[1], -r[2], r[0]))
want_bday = [r for r in want_bday if r[1] is not None and r[1] < 14][:3]
bday_m = re.search(r'<ol class="hot bday">(.*?)</ol>', home_html, re.S)
got_bday = [htmllib.unescape(re.sub(r"<[^>]+>", "", n)) for n in re.findall(r'<span class="hot-name">(.*?)</span>', bday_m.group(1), re.S)] if bday_m else []
if want_bday:
    check(f"誕生日の近い女優: {len(want_bday)}人（このサイトに作品がある・顔写真がある人）が、誕生日の近い順", got_bday == [r[0] for r in want_bday] and bday_m.group(1).count('class="face-img"') == len(want_bday), (got_bday, want_bday))
    check("誕生日の近い女優: 出すのは月日だけ（生まれた年は出さない）", not re.search(r"(19|20)\d\d年", bday_m.group(1)))
else:
    check("誕生日の近い女優がいないときは、欄を出さない", 'id="birthdays"' not in home_html)

# 一覧のカードの出演者は3名まで（オムニバスなど、出演者が多い作品で、カードが長くならないように。運営者の希望。2026-10-05）
bad_cast = []
for lp in [index_path] + sorted(glob.glob(os.path.join(DIST, "archive", "*", "index.html")))[:3]:
    for line in re.findall(r'<p class="item-cast">(.*?)</p>', read(lp), re.S):
        text = htmllib.unescape(re.sub(r"<[^>]+>", "", line))
        names = text.split(" ほか")[0].split("、")
        more = re.search(r" ほか(\d+)名$", text)
        if len(names) > 3 or (len(names) == 3 and "ほか" in text and not more):
            bad_cast.append(text[:40])
check("一覧のカードの出演者は3名まで（4名以上は「ほか○名」）", not bad_cast, bad_cast[:3])

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
fav_index = None
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
    own_titles = [str(valid[c].get("title") or "").strip() for c in cids if c in valid]
    titles_in_summary = [t for t in summaries if any(ti and ti in t for ti in own_titles)]
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
fav_pages = fav_index.get("pages") if isinstance(fav_index, dict) and isinstance(fav_index.get("pages"), dict) else {}
for kind, label in (("actress", "出演者"), ("maker", "メーカー")):
    entity_pages = glob.glob(os.path.join(DIST, kind, "*", "index.html"))
    slugs = {os.path.basename(os.path.dirname(p)) for p in entity_pages}
    ics_files = {os.path.basename(p)[:-4] for p in glob.glob(os.path.join(DIST, "calendar", kind, "*.ics"))}
    # カレンダーは、ページがある人・メーカーのうち、毎日の更新で載せた作品（新作・予約）がある人だけ（過去作品だけの人は作らない）
    names_of = (lambda x: x.get("actress") or []) if kind == "actress" else (lambda x: [x.get("maker")] if x.get("maker") and x.get("maker") != "不明" else [])
    curated_slugs = {entity_slug(n) for x in curated.values() for n in names_of(x) if n}
    want_ics = slugs & curated_slugs
    check(f"{label}ごとのカレンダー（{len(ics_files)}）は、{label}ページ（{len(slugs)}）のうち、新作・予約が載っている{label}の分だけ", ics_files == want_ics, (sorted(want_ics - ics_files)[:2], sorted(ics_files - want_ics)[:2]))
    fav_slugs = set((fav_pages.get(kind) or {}).values()) if isinstance(fav_pages.get(kind), dict) else set()
    check(f"お気に入りの索引の {kind} は、カレンダーがある{label}だけ（「お気に入り」ページは、ここにある人だけにカレンダーのリンクを出す）", fav_slugs == ics_files, (sorted(fav_slugs - ics_files)[:2], sorted(ics_files - fav_slugs)[:2]))
    bad_ics = [slug for slug in sorted(ics_files) if ics_problems(os.path.join(DIST, "calendar", kind, slug + ".ics"))]
    check(f"{label}ごとのカレンダーの形が正しい", not bad_ics, bad_ics[:3])
    no_btn = []
    for p in entity_pages:
        html = read(p)
        slug = os.path.basename(os.path.dirname(p))
        link = f'href="webcal://{page_host}/calendar/{kind}/{slug}.ics"'
        if 'data-fav-type="%s"' % kind not in html or (link in html) != (slug in ics_files) or ('class="cal-link"' in html) != (slug in ics_files):
            no_btn.append(slug)
    check(f"{label}ページに、☆ボタンがあり、カレンダーがある{label}だけに、そのページ専用のカレンダーのリンクがある", not no_btn, no_btn[:3])
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
# 書体（Google Fonts）: 表示を止めないよう preload して、読み込み終わったら stylesheet に切り替える。JavaScript が無いときのための <noscript> の読み込みもある
bad_fonts = []
for p in pages:
    html_ = read(p)
    head_ = html_[: html_.find("</head>")]
    pre = [t for t in tags(head_, "link") if t.get("rel") == "preload" and t.get("as") == "style" and str(t.get("href", "")).startswith("https://fonts.googleapis.com/css2?")]
    ns = re.search(r'<noscript><link rel="stylesheet" href="https://fonts\.googleapis\.com/css2\?[^"]*"\s*/?></noscript>', head_)
    if len(pre) != 1 or "this.rel='stylesheet'" not in pre[0].get("onload", "") or not ns or "wght@400;700" not in pre[0].get("href", ""):
        bad_fonts.append(os.path.relpath(p, DIST))
check("全ページの書体の読み込み: 表示を止めない形（preload → onload で stylesheet）＋ <noscript> の読み込み・太さは 400 と 700 だけ", not bad_fonts, bad_fonts[:3])
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
check("応答ヘッダー: 名前にハッシュが付くファイル（/_astro/*）は長くキャッシュ（immutable）。名前が変わらないスクリプト（/*.js）は、新しいページと食い違わないよう、長く置かない", re.search(r"^/_astro/\*\s*\n\s+Cache-Control: public, max-age=31536000, immutable", htext, re.M) is not None and not re.search(r"^/[^\n]*\.js\s*\n\s+Cache-Control", htext, re.M))


print("\n■ サムネの切り取り・作品検索・「VR作品を隠す」")


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
check("CSS: ほかの場所（ランキングなど）が、作品カードのサムネの比率を別の値に変えていない（3:4だと背表紙が入る）", not other_ratios, other_ratios[:2])
top_boxes = {sel: " ".join(rule_bodies(sel)) for sel in (".medal-cover", ".topic-thumb")}
check("CSS: トップのTOP3（.medal-cover）・きょうの話題（.topic-thumb）のサムネも --cover-ratio の比率", all(re.search(r"aspect-ratio\s*:\s*var\(--cover-ratio\)", b_) for b_ in top_boxes.values()), top_boxes)
img_rules = rule_bodies(".item-img")
check("CSS: サムネの画像（.item-img）は、枠いっぱいに、右端にそろえて切り出す（object-fit: cover・object-position: 100% 50%）", any(re.search(r"object-fit\s*:\s*cover", b) and re.search(r"object-position\s*:\s*100%\s*50%", b) for b in img_rules), img_rules[:1])
thumb = " ".join(rule_bodies(".fav-thumb"))
tw, th = re.search(r"width\s*:\s*(\d+)px", thumb), re.search(r"height\s*:\s*(\d+)px", thumb)
check("CSS: お気に入りのサムネ（.fav-thumb）も、表紙の比率に近い（0.68〜0.72）・右端にそろえる", bool(tw and th) and 0.68 <= int(tw.group(1)) / int(th.group(1)) <= 0.72 and re.search(r"object-position\s*:\s*100%\s*50%", thumb) is not None, thumb[:120])

# 「VR作品を隠す」の見た目の決まり
hide_rule = [b for sels, b in css_rules if ".hide-vr [data-vr]" in sels]
rank_sels = [x for sels, b in css_rules for x in sels]
check("CSS: TOP3は、メダルの色（data-place 1〜3）があり、全部がVRのときTOP3ごと隠す（#ranking.vr-empty）・4位以降（.rank-off）は隠す", all(f'.medal-cell[data-place="{n}"]' in [x.replace("'", '"') for x in rank_sels] for n in (1, 2, 3)) and any("#ranking.vr-empty" in sels and ".rank-podium .rank-cell.rank-off" in sels and re.search(r"display\s*:\s*none", b) for sels, b in css_rules), [x for x in rank_sels if "data-place" in x or "vr-empty" in x or "rank-off" in x])
vr_tag = next((g for g in glob.glob(os.path.join(DIST, "tag", "*", "index.html")) if "<h1" in read(g) and "VR作品の新作・予約作品" in read(g)), None)
if vr_tag:
    check("VR作品のページでは、「VR作品を隠す」を選んでいても作品を隠さない（data-vr を付けない。全部が消えて空になるため）", "data-vr" not in re.sub(r"data-vr-(toggle|group)", "", read(vr_tag)), os.path.relpath(vr_tag, DIST))
related_pages = [p for p in glob.glob(os.path.join(DIST, "item", "*", "index.html")) if 'id="related-title"' in read(p)]
check("作品ページの「同じ出演者・メーカーの作品」は、VRを隠して全部が消えたら見出しごと隠せる（data-vr-group）", related_pages and all(re.search(r'<section[^>]*aria-labelledby="related-title"[^>]*data-vr-group', read(p)) for p in related_pages), len(related_pages))
# 見た目の統一: 角の丸みは3つの決まった値（--r-pill / --r-panel / --r-media）だけ。丸（50%）は顔写真・丸ボタン用
css_src = read(os.path.join(ROOT, "site", "src", "styles", "site.css"))
odd_radius = [m.group(0) for m in re.finditer(r"border-radius\s*:\s*([^;]+);", css_src) if not re.fullmatch(r"(var\(--r-(pill|panel|media)\)\s*)+0?\s*0?|50%", m.group(1).strip().replace(" 0 0", ""))]
check("CSS: 角の丸みは、決めた3つ（押せるもの・枠・画像）と丸（50%）だけ（サイト全体の見た目をそろえる）", not odd_radius, odd_radius[:3])
# 一覧のカードの「FANZAで見る」は控えめなボタン（.btn-card）。赤いボタン（.btn-hot）は、ページごとの一番の行き先だけ
hot_in_cards = []
for p in pages:
    for card_ in re.finditer(r'<article class="item[^"]*">[\s\S]*?</article>', read(p)):
        if "btn-hot" in card_.group(0) or "btn-card" not in card_.group(0) and "FANZAで見る" in card_.group(0):
            hot_in_cards.append(os.path.relpath(p, DIST))
            break
check("一覧のカードの「FANZAで見る」は、控えめなボタン（.btn-card）。赤いボタンは使わない", not hot_in_cards, hot_in_cards[:3])
check("CSS: きょうの話題の繰り上げ（.topic-alt）は、ふだんは隠れていて、「VR作品を隠す」のときだけ出る", any(sels == [".topic-alt"] and re.search(r"display\s*:\s*none", b) for sels, b in css_rules) and any(".hide-vr .topic-alt" in sels and re.search(r"display\s*:\s*block", b) for sels, b in css_rules))
check("CSS: 1行の出演者の行（.item-cast・.medal-cast）では、文節の区切り（<wbr>）を消して、2行にしない（Chromium は nowrap でも <wbr> で改行する）", all(any(f"{c} wbr" in sels and re.search(r"display\s*:\s*none", b) for sels, b in css_rules) for c in (".item-cast", ".medal-cast")))
check("CSS: 全部がVRのまとまり（[data-vr-group].vr-empty）を隠す", any("[data-vr-group].vr-empty" in sels and re.search(r"display\s*:\s*none", b) for sels, b in css_rules))
check("CSS: html.hide-vr のとき、VR作品の目印（data-vr）のマスと、全部がVRの日付（.day.vr-empty）を隠す", bool(hide_rule) and all(re.search(r"display\s*:\s*none", b) for b in hide_rule) and any(".day.vr-empty" in sels for sels, b in css_rules if ".hide-vr [data-vr]" in sels), hide_rule[:1])
hidden_ok = [sels for sels, b in css_rules if ".vr-toggle[hidden]" in sels and re.search(r"display\s*:\s*none", b)]
check("CSS: 隠れているスイッチ・検索（hidden）が、display の指定に負けずに隠れる", bool(hidden_ok) and any(".work-search[hidden]" in sels for sels in hidden_ok), hidden_ok[:1])

# 全ページ: 先に印を付ける小さなスクリプト・スイッチのスクリプト・検索へのリンク
no_head_vr, no_vr_js, no_nav_search, no_foot_search = [], [], [], []
for p in pages:
    html_ = read(p)
    head_ = html_[: html_.find("</head>")] if "</head>" in html_ else ""
    if not re.search(r"localStorage\.getItem\('hide-vr'\)\s*===\s*'1'", head_) or "classList.add('hide-vr')" not in head_ or "classList.add('only-solo')" not in head_:
        no_head_vr.append(os.path.relpath(p, DIST))
    if 'src="/vr-filter.js"' not in html_:
        no_vr_js.append(os.path.relpath(p, DIST))
    nav_ = html_[html_.find('<nav class="site-nav"') : html_.find("</nav>", html_.find('<nav class="site-nav"'))] if '<nav class="site-nav"' in html_ else ""
    if 'href="/search/"' not in nav_:
        no_nav_search.append(os.path.relpath(p, DIST))
    foot_ = html_[html_.find("<footer") :] if "<footer" in html_ else ""
    if 'href="/search/"' not in foot_:
        no_foot_search.append(os.path.relpath(p, DIST))
check(f"全ページの <head> に、「VR作品を隠す」「単体作品のみ表示」の印を先に付ける小さなスクリプトがある（開いた瞬間にチラつかない。{len(pages)}ページ）", not no_head_vr, no_head_vr[:3])
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
        if ('data-solo="true"' in attrs) != is_solo_raw(valid[cid]):
            wrong_mark.append((os.path.relpath(lp, DIST), cid, "単体作品の印"))
check(f"作品の一覧のマス（{marked_total}個）: VR作品（データのタイトル・形式・ジャンルから判定）にだけ data-vr、単体作品にだけ data-solo が付いている", not wrong_mark, wrong_mark[:3])
warn("VR作品のマスが、一覧のどこかにある（目印のテストが空振りしていない）", vr_total > 0)

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
bad_solo_toggle = []
for tp in toggle_pages:
    if os.path.isfile(tp):
        btns = [t for t in tags(read(tp), "button") if "data-solo-toggle" in t]
        if len(btns) != 1 or "hidden" not in btns[0] or btns[0].get("aria-pressed") != "false" or btns[0].get("data-off") != "単体作品のみ表示" or not btns[0].get("data-on"):
            bad_solo_toggle.append((os.path.relpath(tp, DIST), btns[:1]))
check("「単体作品のみ表示」スイッチが、「VR作品を隠す」の隣に1つずつある（最初は隠れている・押された状態ではない）", not bad_solo_toggle, bad_solo_toggle[:3])
check("CSS: html.only-solo のとき、単体作品の印（data-solo）の無いマスを隠す", any(".only-solo .shelf-cell:not([data-solo])" in sels and re.search(r"display\s*:\s*none", b) for sels, b in css_rules))

# 作品ページ: ジャンルは、ジャンルのページ（/tag/…。ページがあるジャンル）か、そのジャンルで絞り込んだ検索へのリンク
import urllib.parse as _up


def config_value(name):
    """site/src/config.js の export const NAME = … の値（数字・文字列のリスト）を読む"""
    text_ = read(os.path.join(ROOT, "site", "src", "config.js"))
    m_ = re.search(r"export const %s = (\[.*?\]|\d+);" % name, text_, re.S)
    assert m_, name
    return int(m_.group(1)) if m_.group(1).isdigit() else re.findall(r"'([^']+)'", m_.group(1))


TAG_MIN = config_value("TAG_MIN_ITEMS")
TAG_GENRES = config_value("TAG_PAGE_GENRES")
genre_counts = {}
for x in curated.values():  # ジャンルのページ・月ごとのページは、毎日の更新で載せた作品だけで作る
    for g in set(g for g in (x.get("genres") or []) if g):
        genre_counts[g] = genre_counts.get(g, 0) + 1
tag_pages_expected = {g for g in TAG_GENRES if genre_counts.get(g, 0) >= TAG_MIN}
bad_chip, chip_pages = [], 0
for cid, x in valid.items():
    fp = os.path.join(DIST, "item", cid, "index.html")
    genres_ = [g for g in (x.get("genres") or []) if g]
    if not genres_ or not os.path.isfile(fp):
        continue
    chip_pages += 1
    links_ = [t.get("href") for t in tags(read(fp), "a") if has_class(t, "chip-tag")]
    want_ = [(f"/tag/{entity_slug(g)}/" if g in tag_pages_expected else "/search/?tag=" + _up.quote(g, safe="")) for g in genres_]
    if links_ != want_:
        bad_chip.append((cid, links_[:2], want_[:2]))
check(f"作品ページのジャンル（{chip_pages}ページ）が、ジャンルのページ（ある場合）か、そのジャンルで絞り込んだ検索（/search/?tag=…）へのリンクになっている", not bad_chip, bad_chip[:2])
warn("ジャンルのある作品が1本以上ある", chip_pages > 0)

print("\n■ 品番・作品ページの情報欄・月ごとのページ・ジャンルのページ（検索から来てもらうための作り）")


def product_code(cid):
    """site/src/lib/facts.js の productCode と同じ（作品ID → 品番。作れなければ ''）。突き合わせるため、別に書いてある"""
    m_ = re.match(r"^(?:h_\d+|\d{1,3})?([a-z]{2,10})(\d{3,5})$", str(cid).lower())
    return f"{m_.group(1).upper()}-{int(m_.group(2)):03d}" if m_ else ""


def ymd_jp(day):
    return f"{int(day[:4])}年{int(day[5:7])}月{int(day[8:10])}日"


by_date_count = {}
for x in everything.values():  # 「この作品のデータ」欄は、過去作品も含めて数える
    by_date_count[x["date"][:10]] = by_date_count.get(x["date"][:10], 0) + 1
bad_code, bad_facts, with_code = [], [], 0
for cid, x in valid.items():
    fp = os.path.join(DIST, "item", cid, "index.html")
    if not os.path.isfile(fp):
        continue
    html_ = read(fp)
    code_ = product_code(cid)
    row_ = re.search(r'<dt class="spec-term">品番</dt>\s*<dd class="spec-desc">([^<]*)</dd>', html_)
    title_ = re.search(r"<title>(.*?)</title>", html_, re.S).group(1)
    desc_ = re.search(r'<meta name="description" content="([^"]*)"', html_)
    if code_:
        with_code += 1
        if not (row_ and row_.group(1) == code_ and htmllib.unescape(title_).startswith(code_ + " ") and desc_ and code_ in htmllib.unescape(desc_.group(1))):
            bad_code.append((cid, code_, row_.group(1) if row_ else None, title_[:30]))
    elif row_ or re.match(r"^[A-Z0-9]+-\d{3,} ", htmllib.unescape(title_)):
        bad_code.append((cid, "品番を作れないのに出ている", title_[:30]))
    # 情報欄: 「同じ発売日」の行（いつも出る）の本数が、データを数えた値と同じ
    facts_ = re.search(r'<h2 id="facts-title"[^>]*>この作品のデータ</h2>\s*<ul class="facts">(.*?)</ul>', html_, re.S)
    rows_ = re.findall(r'<li class="facts-row">\s*<span class="facts-label">(.*?)</span>\s*<span class="facts-text">(.*?)</span>\s*</li>', facts_.group(1), re.S) if facts_ else []
    n_same = by_date_count[x["date"][:10]]
    want_day = f"{ymd_jp(x['date'][:10])}発売の作品は、" + ("この1本だけです。" if n_same == 1 else f"掲載中で{n_same}本あります。")
    if not rows_ or rows_[0][0] != "同じ発売日" or want_day not in htmllib.unescape(re.sub(r"<[^>]+>", "", rows_[0][1])):
        bad_facts.append((cid, want_day, (rows_[0] if rows_ else None)))
    if any(label == "収録時間" for label, _ in rows_):  # 収録時間の長さくらべは出さない（運営者の判断。2026-10-05）
        bad_facts.append((cid, "収録時間の長さくらべの行が出ている"))
check(f"作品ページの品番（作れる{with_code}ページ）: 「品番」の欄・タイトルの先頭・説明文に、同じ品番が出ている。作れない作品には出ていない", not bad_code, bad_code[:3])
check("作品ページに「この作品のデータ」欄があり、先頭の行（同じ発売日）の本数が、データを数えた値と同じ・収録時間の長さくらべの行は無い", not bad_facts, bad_facts[:2])
warn("品番を作れる作品が1本以上ある", with_code > 0)

MONTH_MIN = config_value("MONTH_MIN_ITEMS")
TAG_LIMIT = config_value("TAG_PAGE_LIMIT")
month_counts = {}
for x in curated.values():
    month_counts[x["date"][:7]] = month_counts.get(x["date"][:7], 0) + 1
months_want = {ym: n for ym, n in month_counts.items() if n >= MONTH_MIN}
month_files = {os.path.basename(os.path.dirname(f)): f for f in glob.glob(os.path.join(DIST, "month", "*", "index.html"))}
check(f"月ごとのページが、作品が{MONTH_MIN}本以上ある月（{len(months_want)}か月）だけ作られている", set(month_files) == set(months_want), (sorted(month_files), sorted(months_want)))
bad_month = []
for ym, f in month_files.items():
    html_ = read(f)
    h1_ = re.search(r'<h1 class="hero-title">(.*?)</h1>', html_, re.S)
    cards_ = len(re.findall(r'<article class="item">', html_))
    if not (h1_ and f"{int(ym[:4])}年{int(ym[5:7])}月発売" in h1_.group(1) and cards_ == months_want.get(ym) and 'name="robots" content="noindex' not in html_):
        bad_month.append((ym, h1_.group(1)[:30] if h1_ else None, cards_, months_want.get(ym)))
check("月ごとのページ: 見出しに「○年○月発売」・並んでいる作品の数が、その月の作品の数と同じ・noindexではない", not bad_month, bad_month[:3])
month_index = os.path.join(DIST, "month", "index.html")
if months_want:
    check("月の一覧ページ（/month/）がある。すべての月のページへのリンクがある", os.path.isfile(month_index) and all(f'href="/month/{ym}/"' in read(month_index) for ym in months_want))
    check("月の一覧・月ごとのページが、sitemap に入っている", "/month/" in sm_paths and all(f"/month/{ym}/" in sm_paths for ym in months_want), [p for p in sm_paths if p.startswith("/month")][:3])
else:
    check("月ごとのページが1つも無いときは、一覧ページも作らず、sitemap にも入れない", not os.path.isfile(month_index) and not [p for p in sm_paths if p.startswith("/month")])

tag_counts = {entity_slug(g): (g, n) for g, n in ((g, genre_counts.get(g, 0)) for g in TAG_GENRES) if n >= TAG_MIN}
vr_n = sum(1 for x in curated.values() if is_vr_raw(x))
if vr_n >= TAG_MIN:
    tag_counts[entity_slug("VR作品")] = ("VR作品", vr_n)
tag_files = {os.path.basename(os.path.dirname(f)): f for f in glob.glob(os.path.join(DIST, "tag", "*", "index.html"))}
check(f"ジャンルのページが、許可したジャンル（config.js の TAG_PAGE_GENRES）で作品が{TAG_MIN}本以上あるものと、VR作品だけ作られている（{len(tag_counts)}ページ）", set(tag_files) == set(tag_counts), (len(tag_files), len(tag_counts)))
bad_tag = []
for slug_, f in tag_files.items():
    html_ = read(f)
    name_, n_ = tag_counts.get(slug_, ("", 0))
    cards_ = len(re.findall(r'<article class="item">', html_))
    h1_ = re.search(r'<h1 class="hero-title">(.*?)</h1>', html_, re.S)
    if not (h1_ and name_.replace("VR作品", "VR作品") in h1_.group(1) and cards_ == min(n_, TAG_LIMIT) and 'name="robots" content="noindex' not in html_):
        bad_tag.append((slug_, name_, cards_, min(n_, TAG_LIMIT)))
check("ジャンルのページ: 見出しにジャンル名・並んでいる作品の数が、そのジャンルの作品の数（多いときは上限まで）と同じ・noindexではない", not bad_tag, bad_tag[:3])
tag_index = os.path.join(DIST, "tag", "index.html")
if tag_counts:
    check("ジャンルの一覧ページ（/tag/）がある。すべてのジャンルのページへのリンクがある", os.path.isfile(tag_index) and all(f'href="/tag/{sl}/"' in read(tag_index) for sl in tag_counts))
    check("ジャンルの一覧・ジャンルのページが、sitemap に入っている", "/tag/" in sm_paths and all(f"/tag/{sl}/" in sm_paths for sl in tag_counts), [p for p in sm_paths if p.startswith("/tag")][:3])
else:
    check("ジャンルのページが1つも無いときは、一覧ページも作らず、sitemap にも入れない", not os.path.isfile(tag_index) and not [p for p in sm_paths if p.startswith("/tag")])
no_sensitive_tag = [g for g, _ in tag_counts.values() if re.search(r"制服|校生|学生|少女|ロリ|幼|中出|顔射|フェラ|レイプ|痴漢|盗撮|調教|ドラッグ|放尿", g)]
check("ジャンルのページに、過激な行為・未成年を連想させる名前のものが無い", not no_sensitive_tag, no_sensitive_tag)

# 人気ランキング（/ranking/ 新着の人気順・/ranking/all/ 全体の人気順）
print("\n■ 人気ランキング")
JST_DAY = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d")
_from = (datetime.date.fromisoformat(JST_DAY) - datetime.timedelta(days=7)).isoformat()  # 新着は1週間（lib/popularity.js の NEW_RANK_DAYS）
want_new = sorted((c for c in everything if c in pop_new and _from <= str(everything[c]["date"])[:10] <= JST_DAY),
                  key=lambda c: (pop_new[c], -int(str(everything[c]["date"])[:10].replace("-", "")), c))[:100]
want_all = sorted((c for c in everything if all_rank_of(c) and str(everything[c]["date"])[:10] <= JST_DAY),
                  key=lambda c: (all_rank_of(c), -int(str(everything[c]["date"])[:10].replace("-", "")), c))[:100]
for path_, want, label in (("ranking/index.html", want_new, "新着の人気順"), ("ranking/all/index.html", want_all, "全体の人気順")):
    f = os.path.join(DIST, path_)
    if not os.path.isfile(f):
        check(f"{label}のページ（/{path_[:-10]}）がある", False)
        continue
    html_ = read(f)
    cells = [m.group(1) for m in re.finditer(r'<li class="shelf-cell"[^>]*>(.*?)</li>', html_, re.S)]
    badges = [re.search(r'<span class="rank-badge">(\d+)位</span>', c) for c in cells]
    order = []
    for c in cells:
        m_ = re.search(r'href="/item/([^/"]+)/"', c) or re.search(r'cid%3D([A-Za-z0-9_]+)|id%3D([A-Za-z0-9_]+)', c)
        order.append(next((g for g in (m_.groups() if m_ else ()) if g), None))
    check(f"{label}: 作品の数（{len(cells)}）と並び（順位の順）が、順位のファイルから決めたものと同じ・札は1位から順に", len(cells) == len(want) and [b.group(1) if b else None for b in badges] == [str(n) for n in range(1, len(cells) + 1)]
          and all(o is None or o == w for o, w in zip(order, want)), (len(cells), len(want), order[:3], want[:3]))
    has_noindex = 'name="robots" content="noindex' in read_raw(f)
    check(f"{label}: 作品が無い・コメントのある作品が1本も無いときだけ noindex", has_noindex == (not want or not any(has_comment(everything[c]) for c in want)))
check("ヘッダーに人気ランキングへのリンクがある", 'href="/ranking/"' in home_html)

# セール・キャンペーン（/sale/。sale.json から。キャンペーンは終わりが近い順・終わったものはブラウザで隠す）
print("\n■ セール・キャンペーン")
SALE = os.path.join(ROOT, "site", "src", "data", "sale.json")
try:
    _sale = json.load(open(SALE, encoding="utf-8"))
except (OSError, ValueError):
    _sale = {}
_camps = _sale.get("campaigns") if isinstance(_sale, dict) and isinstance(_sale.get("campaigns"), list) else []
_sale_rows = [r for r in (_sale.get("items") if isinstance(_sale, dict) and isinstance(_sale.get("items"), list) else []) if isinstance(r, dict) and isinstance(r.get("k"), int) and 0 <= r["k"] < len(_camps)]
want_camps = sorted({r["k"] for r in _sale_rows if r.get("c") in everything and str(_camps[r["k"]].get("title", "")).strip() and str(_camps[r["k"]].get("end", ""))[:10] >= JST_DAY})
# 特集（キャンペーン）ごとの作品（このサイトの作品だけ。作品は、いちばん早く終わるキャンペーン1つに入っている）
_camp_works = {k: [everything[r["c"]] for r in _sale_rows if r["k"] == k and r.get("c") in everything] for k in want_camps}
_camp_order = sorted(want_camps, key=lambda k: (str(_camps[k]["end"]), -len(_camp_works[k]), str(_camps[k]["title"])))
_content_genres = set(_tag_genres) - {"ベスト・総集編"}


def _top_counts(names, limit=3, minimum=1):
    """多い順に3つ（同数なら名前の順。site/src/lib/sale.js の topCounts と同じ）"""
    counts = {}
    for n_ in names:
        counts[n_] = counts.get(n_, 0) + 1
    return [(n_, c_) for n_, c_ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if c_ >= minimum][:limit]


def _cast(x):
    return [a for a in (x.get("actress") or []) if a]


def camp_summary(k):
    """特集の中身（site/src/lib/sale.js の campaignSummary と同じ数え方）"""
    works_ = _camp_works[k]
    makers_ = _top_counts([str(x.get("maker") or "") for x in works_ if str(x.get("maker") or "") not in ("", "不明")])
    actresses_ = _top_counts([a for x in works_ if len(_cast(x)) <= 4 for a in dict.fromkeys(_cast(x))], minimum=2)
    genres_ = _top_counts([g for x in works_ for g in set(x.get("genres") or []) if g in _content_genres])
    return makers_, actresses_, genres_


def end_iso(end):
    return f"{end[:10]}T{end[11:16] if len(end) >= 16 else '23:59'}:59+09:00"


def end_label(end):
    return f"{int(end[5:7])}月{int(end[8:10])}日" + (f" {int(end[11:13])}:{end[14:16]}" if len(end) >= 16 else "")


def soon_tag(end):
    tomorrow = (datetime.date.fromisoformat(JST_DAY) + datetime.timedelta(days=1)).isoformat()
    return "きょうまで" if end[:10] == JST_DAY else "あすまで" if end[:10] == tomorrow else ""


sale_page = os.path.join(DIST, "sale", "index.html")
check("セール・キャンペーンのページ（/sale/）と、終わったものを隠すスクリプト（sale.js）がある", os.path.isfile(sale_page) and os.path.isfile(os.path.join(DIST, "sale.js")))
if os.path.isfile(sale_page):
    sh = read(sale_page)
    head_ids = re.findall(r'<h2 id="sale-(\d+)" class="section-title">(.*?)</h2>', sh)
    heads = [t for _, t in head_ids]
    check(f"キャンペーンのまとまりの数（{len(heads)}）が、データ（今日より前に終わったものを除く・このサイトの作品があるもの）と同じ", len(heads) == len(want_camps), (len(heads), len(want_camps)))
    if heads:
        check("セールのページに「○日の時点」「くわしくはFANZAで確かめて」の注意書き・終わりの時刻の印（data-sale-end）・sale.js がある", "時点" in sh and "FANZAの作品ページで確かめてください" in sh and "data-sale-end=" in sh and 'src="/sale.js"' in sh)
        bad_badge = [b for b in re.findall(r'<span class="rank-badge">([^<]*)</span>', sh) if not re.fullmatch(r"\d{1,2}%OFF|セール", b)]
        check("セールの札は「○%OFF」か「セール」だけ", not bad_badge, bad_badge[:3])
        check("特集の見出しの id は、キャンペーンの番号（sale-番号。トップ・きょうの話題からのリンク先）・終わりが近い順",
              [int(k) for k, _ in head_ids] == _camp_order and all(strip_tags(t) == str(_camps[int(k)]["title"]).strip() for k, t in head_ids), [k for k, _ in head_ids])
        jump = re.search(r'<nav class="sale-jump" aria-label="特集">(.*?)</nav>', sh, re.S)
        jump_links = [(a.get("href"), a.get("data-sale-end")) for a in tags(jump.group(1), "a")] if jump else []
        check("セールのページのはじめに、特集への目次（見出しへのリンク・終わったら隠す印）がある",
              jump_links == [(f"#sale-{k}", end_iso(str(_camps[k]["end"]))) for k in _camp_order], jump_links[:3])
        # 特集ごとの中身（おもなメーカー・よく出ている女優・多いジャンル。このサイトの作品から数えた本数）
        bad_facts = []
        for k, block in zip(_camp_order, re.split(r'<section class="section sale-camp"', sh)[1:]):
            want_rows = [(label, rows) for label, rows in zip(("おもなメーカー", "よく出ている女優", "多いジャンル"), camp_summary(k)) if rows]
            got_rows = [(strip_tags(dt), strip_tags(dd)) for dt, dd in re.findall(r'<div class="camp-fact">\s*<dt>(.*?)</dt>\s*<dd>(.*?)</dd>', block, re.S)]
            if got_rows != [(label, "・".join(f"{n_}（{c_}本）" for n_, c_ in rows)) for label, rows in want_rows]:
                bad_facts.append((_camps[k]["title"], got_rows[:1], want_rows[:1]))
            note = re.search(r'<p class="section-note">(.*?)</p>', block, re.S)
            tag_ = soon_tag(str(_camps[k]["end"]))
            if not note or (tag_ and f'<span class="camp-soon">{tag_}</span>' not in note.group(1)) or (not tag_ and "camp-soon" in note.group(1)) or f"{end_label(str(_camps[k]['end']))}まで・{len(_camp_works[k])}本" not in strip_tags(note.group(1)):
                bad_facts.append((_camps[k]["title"], "終わり・本数"))
        check("特集ごとに、おもなメーカー・よく出ている女優（2本以上・出演者4人までの作品）・多いジャンル（ジャンルのページの一覧）と本数・いつまで（きょう・あすなら札）",
              not bad_facts, bad_facts[:2])
        fact_links = [a.get("href", "") for blk in re.findall(r'<dl class="camp-facts">(.*?)</dl>', sh, re.S) for a in tags(blk, "a")]
        check("特集の中身のリンクは、このサイトにあるメーカー・女優・ジャンルのページへ", all(re.fullmatch(r"/(maker|actress|tag)/[0-9a-f]{10}/", h) and os.path.isfile(page_file(h)) for h in fact_links), [h for h in fact_links if not os.path.isfile(page_file(h))][:3])
    else:
        check("セール中の作品が無いときは、その旨を出す", "セール・キャンペーン中のものはありません" in sh)

# セール中の特集（トップ）: キャンペーンごとのカード（運営者の希望「何の特集で、どういう関連作品がセールなのか知りたい」。2026-10-05）
camp_ul = re.search(r'<ul class="camps" data-sale-show="(\d+)">(.*?)</ul>', home_html, re.S)
home_sale = re.search(r'<section id="sale"[^>]*>(.*?)</section>', home_html, re.S)
if want_camps:
    check("トップに「セール中の特集」があり、発売中の新作より前・作品の棚は無い（特集のカードだけ）・終わったら隠すスクリプト（sale.js）がある",
          bool(home_sale) and "セール中の特集" in home_sale.group(1) and "shelf-cell" not in home_sale.group(1) and home_html.find('id="sale"') < home_html.find('id="released"') and 'src="/sale.js"' in home_html)
    cards = re.findall(r'<li class="camp( sale-more)?" data-sale-end="([^"]+)">(.*?)</li>', camp_ul.group(2), re.S) if camp_ul else []
    show_n = int(camp_ul.group(1)) if camp_ul else 0
    bad_card = []
    for i, (k, (more, end_, inner)) in enumerate(zip(_camp_order, cards)):
        camp = _camps[k]
        works_ = _camp_works[k]
        makers_ = camp_summary(k)[0]
        a_ = next((t for t in tags(inner, "a") if has_class(t, "camp-link")), {})
        title_ = re.search(r'<span class="camp-title">(.*?)</span>', inner, re.S)
        maker_line = re.search(r'<span class="camp-makers">(.*?)</span>', inner, re.S)
        covers_ = re.findall(r'<span class="camp-cover"( data-vr="true")?>\s*<img ([^>]*)>', inner)
        off_ = re.search(r"(\d{1,2})\s*[％%]\s*OFF", str(camp["title"]), re.I)
        sticker = re.search(r'<span class="camp-off">([^<]*)</span>', inner)
        want_maker = "・".join(n_ for n_, _ in makers_) + (" など" if sum(c_ for _, c_ in makers_) < len(works_) else "")
        tag_ = soon_tag(str(camp["end"]))
        vr_flags = [bool(v) for v, _ in covers_]
        problems = []
        if bool(more) != (i >= show_n): problems.append("見せる数")
        if a_.get("href") != f"/sale/#sale-{k}": problems.append(a_.get("href"))
        if end_ != end_iso(str(camp["end"])): problems.append("終わりの印")
        if not title_ or strip_tags(title_.group(1)) != str(camp["title"]).strip(): problems.append("名前")
        if f"{end_label(str(camp['end']))}まで・{len(works_):,}本" not in strip_tags(inner): problems.append("いつまで・本数")
        if (f'<span class="camp-soon">{tag_}</span>' in inner) != bool(tag_) or (not tag_ and "camp-soon" in inner): problems.append("きょう・あすの札")
        if (strip_tags(maker_line.group(1)) if maker_line else "") != (f"メーカー：{want_maker}" if makers_ else ""): problems.append(("メーカー", strip_tags(maker_line.group(1)) if maker_line else ""))
        if not 1 <= len(covers_) <= 3 or vr_flags != sorted(vr_flags) or any(not fanza_https(dict(re.findall(r'(\w+)="([^"]*)"', img)).get("src", ""), ["dmm.co.jp", "fanza.co.jp"]) for _, img in covers_): problems.append("表紙")
        if (sticker.group(1) if sticker else "") != (f"{off_.group(1)}%OFF" if off_ else ""): problems.append("値引きの札")
        if problems:
            bad_card.append((camp["title"], problems))
    check(f"セール中の特集のカード（{len(cards)}枚。先頭{show_n}枚を見せる）: 終わりが近い順・その特集の見出しへのリンク・名前・いつまで・本数・おもなメーカー・表紙（VRでない作品が先）・値引きの札",
          len(cards) == len(want_camps) and show_n >= 1 and not bad_card, bad_card[:2])
else:
    check("セール中の特集が無いときは、トップに欄を出さない", not home_sale and not camp_ul)
check("フッターにセール・キャンペーンへのリンクがある", 'href="/sale/"' in home_html)

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
    check("選択肢の値が、スクリプトの読める形（''・released・upcoming / new・old・popnew・pop）だけ", sel_values == [["", "released", "upcoming"], ["new", "old", "popnew", "pop"]], sel_values)
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
        check("索引の項目が、短い名前（c,p,t,d,a,m,g,i,v,o,r,n）だけで、データにある作品・長い文やURLは入っていない", all(isinstance(r, dict) and set(r) <= set("cptdamgivorn") and {"c", "t", "d", "a", "m", "g", "i"} <= set(r) and r["c"] in valid and DAY.match(str(r["d"])) and isinstance(r["a"], list) and isinstance(r["g"], list) for r in irows) and "al.fanza.co.jp" not in read(ii), [r for r in irows if not (isinstance(r, dict) and set(r) <= set("cptdamgivorn"))][:1])
        bad_rn = [r["c"] for r in irows if r.get("r") != all_rank_of(r["c"]) or r.get("n") != pop_new.get(r["c"])]
        check("索引の人気順（r: 全体・n: 新着）が、順位のファイルと同じ（分からない作品には無い）", not bad_rn, bad_rn[:3])
        bad_p = [(r["c"], r.get("p")) for r in irows if (r.get("p") or "") != product_code(r["c"])]
        check("索引の品番（p）が、作品ページと同じ品番（作れない作品には無い）", not bad_p, bad_p[:3])
        bad_t = [r["c"] for r in irows if r["c"] in valid and r["t"].replace("\u200b", "").replace("\u2060", "").replace("\u00a0", " ") != str(valid[r["c"]].get("title", "")).strip()]
        check("索引のタイトルは、文節の区切り（U+200B）と改行を止める文字（U+2060・U+00A0）を戻すと、データのタイトルと同じ", not bad_t, bad_t[:3])
        check("索引のタイトルに、文節の区切り（U+200B）が入っている（ブラウザで語の途中で改行しないため）", any("\u200b" in r["t"] for r in irows))
        check(f"索引の作品の数（{len(irows)}）= min(データの件数 {len(valid)}, 3000)", len(irows) == min(len(valid), 3000), (len(irows), len(valid)))
        check("索引は発売日の新しい順", [r["d"] for r in irows] == sorted((r["d"] for r in irows), reverse=True))
        check("ジャンルの番号（g）が、すべて genres の範囲内で、作品のジャンルの名前に戻る", all(all(isinstance(n, int) and 0 <= n < len(igenres) for n in r["g"]) and sorted(igenres[n] for n in r["g"]) == sorted(set(g for g in (valid[r["c"]].get("genres") or []) if g)) for r in irows), [r["c"] for r in irows if sorted(igenres[n] for n in r["g"] if isinstance(n, int) and 0 <= n < len(igenres)) != sorted(set(g for g in (valid[r["c"]].get("genres") or []) if g))][:2])
        check("ジャンルの一覧は、重複なし・作品の多い順", len(set(igenres)) == len(igenres) and [sum(1 for r in irows if i in r["g"]) for i in range(len(igenres))] == sorted((sum(1 for r in irows if i in r["g"]) for i in range(len(igenres))), reverse=True))
        check("VRの印（v:1）が、データから判定したVR作品と一致する（VR作品にだけ付く）", all((r.get("v") == 1) == is_vr_raw(valid[r["c"]]) and r.get("v") in (None, 1) for r in irows), [r["c"] for r in irows if (r.get("v") == 1) != is_vr_raw(valid[r["c"]])][:3])
        warn("索引にVR作品が1本以上ある（VRの除外のテストが空振りしていない）", any(r.get("v") == 1 for r in irows))
        check("単体作品の印（o:1）が、データから判定した単体作品と一致する（ジャンル「単体作品」、ジャンルが無ければ出演者1人）", all((r.get("o") == 1) == is_solo_raw(valid[r["c"]]) and r.get("o") in (None, 1) for r in irows), [r["c"] for r in irows if (r.get("o") == 1) != is_solo_raw(valid[r["c"]])][:3])
        bad_img = [r["c"] for r in irows if r["i"] and not fanza_https(r["i"] if r["i"].startswith("https://") else "https://pics.dmm.co.jp/" + r["i"], ["dmm.co.jp"])]
        check("索引の画像が、FANZA(DMM)の画像に戻せる形（先頭を省いた形）", not bad_img, bad_img[:3])
        check("索引の大きさが 1.5MB 以内（検索ページを開くたびにダウンロードされるため）", os.path.getsize(ii) <= 1500 * 1024, os.path.getsize(ii))

print("\n■ 日本語の文章の改行（文節の区切り）")
# 日本語の文章は、ビルドの最後に、文節の区切り（<wbr>）と包み（<span class="ph">）が足される（site/src/lib/phrase.js・Astro の拡張 phrase-breaks）。
# iPhone/iPadのSafari系には、CSSで文節ごとに改行する機能が無いため、「あ／り」のような語の途中の改行を、これで防いでいる
html_files = glob.glob(os.path.join(DIST, "**", "*.html"), recursive=True)
PH_BLOCK = re.compile(r'<span class="ph">(?:[^<]|<wbr>|<span class="nb">[^<]*</span>)*</span>')
NB_SPAN = re.compile(r'<span class="nb">([^<]*)</span>')
SKIP_EL = re.compile(r"<(script|style|title|textarea|button|option|select|pre|code|noscript|svg|template)\b[^>]*>[\s\S]*?</\1\s*>", re.I)
stray_wbr, tag_in_ph, ph_in_skip, with_ph = [], [], [], 0
for p in html_files:
    raw = read_raw(p)
    if PH_BLOCK.search(raw):
        with_ph += 1
    if "<wbr" in PH_BLOCK.sub("", raw):
        stray_wbr.append(rel(p))
    if any("<" in NB_SPAN.sub("", re.sub(r"<wbr>", "", m.group(0)[len('<span class="ph">'):-len("</span>")])) for m in PH_BLOCK.finditer(raw)):
        tag_in_ph.append(rel(p))
    if any('class="ph"' in m.group(0) or "<wbr" in m.group(0) for m in SKIP_EL.finditer(raw)):
        ph_in_skip.append(rel(p))
check("全ページで、文節の区切り（<wbr>）が、すべて <span class=\"ph\"> の中にある", not stray_wbr, stray_wbr[:3])
check("<span class=\"ph\"> の中には、<wbr> と名前の <span class=\"nb\"> のほか、タグが入っていない（文章だけ）", not tag_in_ph, tag_in_ph[:3])
# 出演者名・メーカー名の途中には、区切り（<wbr>）が入っていない（運営者が見つけた「波多｜野結衣」のような改行を防ぐ）
name_set = {n for it in everything.values() for n in [*(it.get("actress") or []), it.get("maker") or ""] if n and n != "不明" and len(n) >= 2}
name_heads = {}  # 名前の先頭2文字 → 長さ（名前が数万あっても速く探すため）
for n in name_set:
    name_heads.setdefault(n[:2], set()).add(len(n))


def names_in(text):
    """text の中に出てくる名前（すべての位置・すべての長さ）"""
    found = set()
    for i in range(len(text) - 1):
        for size in name_heads.get(text[i:i + 2], ()):
            if text[i:i + size] in name_set:
                found.add(text[i:i + size])
    return found


split_names = []
for p in html_files:
    raw = read_raw(p)
    for m in PH_BLOCK.finditer(raw):
        if "<wbr>" not in m.group(0):
            continue  # 区切りが無ければ、名前が分かれることもない
        inner = NB_SPAN.sub(r"\1", m.group(0)[len('<span class="ph">'):-len("</span>")])
        flat = inner.replace("<wbr>", "")
        for n in names_in(flat):
            if n not in inner:
                split_names.append((rel(p), n))
check("出演者名・メーカー名の途中に、文節の区切り（<wbr>）が入っていない", not split_names, split_names[:5])
nb_rules = [body for sels, body in css_rules if ".nb" in sels]
check("CSS: 短い名前の包み（.nb）は white-space: nowrap（途中で改行しない）", any(re.search(r"white-space\s*:\s*nowrap", b) for b in nb_rules), nb_rules[:1])
nb_long = sorted({m.group(1) for p in html_files for m in NB_SPAN.finditer(read_raw(p)) if len(re.sub(r"(さん|ちゃん|様)$", "", m.group(1))) > 10})
check("改行しない包み（.nb）は、短い名前だけ（長いと、狭い画面ではみ出すため）", not nb_long, nb_long[:3])
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
