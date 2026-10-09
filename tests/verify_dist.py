"""ビルド結果（site/dist）の点検

`npm run build` のあとに実行します。ページが揃っているか、サイトに必ず必要な表記
（18歳確認・広告表記・FANZAクレジット・RTA）が全ページに残っているかを確かめます。
実行: python3 tests/verify_dist.py [distのパス]   （省略時は site/dist）
"""
import datetime
import glob
import hashlib as _hl
import html as htmllib
import importlib.util
import json
import os
import re
import sys
import unicodedata as _ud
from collections import Counter
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
    "FANZAクレジット（DMMの規定のHTMLのまま）": '<p class="foot-credit">Powered by <a href="https://affiliate.dmm.com/api/">FANZA Webサービス</a></p>',
}

# DMMアフィリエイト公式「クレジット表示」の FANZA クレジット（テキスト形式）。規定のHTMLは改変しない（2026-10-07 に運営者が公式のページで確かめた）
DMM_CREDIT_OFFICIAL = 'Powered by <a href="https://affiliate.dmm.com/api/">FANZA Webサービス</a>'
problems = []
LD_BLOCK = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)  # 構造化データ（JSON-LD）


_cc_mod = None


def is_minor_title(title):
    """未成年を連想させるタイトルか（scripts/claude_comments.py の title_block_reason と同じ。site/src/lib/gacha.js の isMinorTitle とテストで突き合わせ済み）"""
    global _cc_mod
    if _cc_mod is None:
        spec_ = importlib.util.spec_from_file_location("claude_comments_minor", os.path.join(ROOT, "scripts", "claude_comments.py"))
        _cc_mod = importlib.util.module_from_spec(spec_)
        spec_.loader.exec_module(_cc_mod)
    return _cc_mod.title_block_reason({"title": str(title or "")}) == "minor"


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
strip_tags_keep_p = lambda h: re.sub(r"</?(?:span|wbr)[^>]*>", "", h)  # 文節の区切りの <span>・<wbr> だけを外す


def config_value(name):
    """site/src/config.js の export const NAME = … の値（数字・文字列のリスト）を読む"""
    text_ = read(os.path.join(ROOT, "site", "src", "config.js"))
    m_ = re.search(r"export const %s = (\[.*?\]|\d+);" % name, text_, re.S)
    assert m_, name
    return int(m_.group(1)) if m_.group(1).isdigit() else re.findall(r"'([^']+)'", m_.group(1))



def sale_js_ok(h):
    """セールの「終わったら隠す」（public/sale.js の中身）が、ページの中の、最初の終わりの印（data-sale-end）より前に入っているか（2026-10-07。
    前は、読み込みのあとで隠していたので、終わったものが見えてから消えて、下がずれていた）"""
    i = h.find('<script id="sale-early">')
    j = h.find("data-sale-end=")
    return i >= 0 and (j < 0 or i < j) and "shownSlots" in h[i:i + 8000] and "MutationObserver" in h[i:i + 8000] and 'src="/sale.js' not in h

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
    for kind in ("actress", "maker", "series", "label"):
        entity_pages = glob.glob(os.path.join(DIST, kind, "*", "index.html"))
        in_sitemap = {p for p in sm_paths if p.startswith(f"/{kind}/") and p != f"/{kind}/"}
        indexable = {f"/{kind}/{os.path.basename(os.path.dirname(p))}/" for p in entity_pages if 'name="robots" content="noindex' not in read_raw(p)}
        check(f"{kind} ページのうち、noindex でないもの（{len(indexable)}/{len(entity_pages)}ページ）が、すべて sitemap に入っている", indexable == in_sitemap, (len(indexable), len(in_sitemap)))

print("\n■ シリーズ・レーベルのページ・作品ページの人気の動きと内部リンク（2026-10-07。運営者の「独自の価値を足す」）")
check("シリーズの一覧（/series/）・レーベルの一覧（/label/）のページがある", os.path.isfile(os.path.join(DIST, "series", "index.html")) and os.path.isfile(os.path.join(DIST, "label", "index.html")))
bad_entry = []
for kind, word, about in (("series", "シリーズ", "CreativeWorkSeries"), ("label", "レーベル", "Brand")):
    for pth in glob.glob(os.path.join(DIST, kind, "*", "index.html")):
        slug_ = os.path.basename(os.path.dirname(pth))
        raw_ = read_raw(pth)
        tm = re.search(r"<title>(.*?)</title>", raw_, re.S)
        title_ = htmllib.unescape(tm.group(1)) if tm else ""
        here = []
        if not re.fullmatch(r"\d{1,9}", slug_):
            here.append("URLは FANZA の id")
        if not re.search(r"（" + word + r"）の新作(・予約)?・作品一覧【\d{4}年\d{1,2}月】（(\d+)本）｜", title_):
            here.append(("タイトル", title_[:60]))
        if not re.search(r'"@type":\s*"CollectionPage"', raw_) or f'"{about}"' not in raw_ or '"BreadcrumbList"' not in raw_:
            here.append("構造化データ")
        if is_minor_title(htmllib.unescape(re.sub(r"<[^>]+>", "", re.search(r'<h1 class="hero-title">(.*?)</h1>', raw_, re.S).group(1)))):
            here.append("未成年を連想させる名前")
        if here:
            bad_entry.append((kind, slug_, here))
check("シリーズ・レーベルのページ: URLは FANZA の id・タイトル「○○（シリーズ）の新作・作品一覧【年月】（○本）」・CollectionPage（CreativeWorkSeries / Brand）・パンくず・未成年を連想させる名前のページは無い",
      not bad_entry, bad_entry[:3])
bad_links, bad_trend, n_trend, n_chart = [], [], 0, 0
for pth in sorted(glob.glob(os.path.join(DIST, "item", "*", "index.html"))):
    raw_ = read_raw(pth)
    cid_ = os.path.basename(os.path.dirname(pth))
    # 作品ページのシリーズ・レーベル・人気のジャンル・週のまとめへのリンクは、すべて実在するページ
    for href_ in re.findall(r'href="(/(?:series|label|tag|weekly)/[^"]*)"', raw_):
        if not os.path.isfile(page_file(href_)):
            bad_links.append((cid_, href_))
    tr = re.search(r'<section class="subsection" aria-labelledby="trend-title">(.*?)</section>', raw_, re.S)
    if tr:
        n_trend += 1
        body_ = tr.group(1)
        if "新着の人気順で最高" not in strip_tags(body_):
            bad_trend.append((cid_, "文"))
        if "<svg" in body_:
            n_chart += 1
            if len(re.findall(r"<circle", body_)) < 1 or 'class="trend-line"' not in body_ or "<title>" not in body_ or 'class="visually-hidden"' not in body_:
                bad_trend.append((cid_, "グラフ"))
check("作品ページのシリーズ・レーベル・ジャンル・週のまとめへのリンクは、すべて実在するページ", not bad_links, bad_links[:3])
check(f"作品ページの「発売後の人気の動き」（{n_trend}ページ・うちグラフ {n_chart}ページ）: 最高順位の文・グラフ（線・点・点の上の順位・読み上げ用の一覧）", not bad_trend, bad_trend[:3])
_rh_path = os.path.join(ROOT, "site", "src", "data", "rank_history.json")
if os.path.isfile(_rh_path):
    _rh = json.load(open(_rh_path, encoding="utf-8")).get("items", {})
    _want_trend = {c for c, r in _rh.items() if any(isinstance(v, int) and v > 0 for v in r.get("n", [])) and os.path.isfile(os.path.join(DIST, "item", c, "index.html"))}
    _got_trend = {os.path.basename(os.path.dirname(p_)) for p_ in glob.glob(os.path.join(DIST, "item", "*", "index.html")) if 'aria-labelledby="trend-title"' in read_raw(p_)}
    check("人気の動きの記録があり、新着の人気順に入った作品のページには、すべて「発売後の人気の動き」がある（無い作品には出さない）", _want_trend == _got_trend, (sorted(_want_trend - _got_trend)[:3], sorted(_got_trend - _want_trend)[:3]))
_rk = read_raw(os.path.join(DIST, "ranking", "index.html")) if os.path.isfile(os.path.join(DIST, "ranking", "index.html")) else ""
check("新着の人気ランキング: 前日からの動き・最高順位の1行は、セールの価格と別の見た目（item-note is-rank）", 'class="item-note is-rank"' in _rk or "item-note" not in _rk, re.findall(r'class="item-note[^"]*"', _rk)[:2])

print("\n■ 週のまとめ記事")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_trend_facts(label, body_, fx, period, prev):
    """まとめ記事の傾向の表（components/TrendFacts.astro）が、記事と一緒に保存した数字（facts）と同じか。週・月で共通"""
    nums_ = re.findall(r'<span class="tf-num">(\d+)</span>', body_)
    check(f"{label}: 本数の札が facts と同じ（発売・VR・デビュー作）", nums_ == [str(fx["total"]), str(fx["vr"]), str(fx["debut"])], nums_)
    has_prev = fx["prev_total"] > 0
    if has_prev:
        check(f"{label}: {prev}の本数と増減が出ている", f'{prev} {fx["prev_total"]}本' in strip_tags(body_) and 'class="tf-move' in body_)
    else:
        check(f"{label}: {prev}の作品が無い（記録の始まり）ときは比べない（「{prev}の記録なし」・増減・{prev}の棒を出さない）",
              f"{prev}の記録なし" in strip_tags(body_) and 'class="tf-move' not in body_ and "tf-bar is-before" not in body_ and "tf-legend" not in body_)
    shown_g = [g for g in fx.get("genres", []) if g.get("count") or (has_prev and g.get("prev"))]
    rows_ = re.findall(r'<li class="tf-row" aria-label="([^"]*)"', body_)
    want_ = [f'{g["name"]}: {period}{g["count"]}本、{prev}{g["prev"]}本' if has_prev else f'{g["name"]}: {period}{g["count"]}本' for g in shown_g]
    check(f"{label}: ジャンルの横棒が facts のジャンルの数だけあり、読み上げ用の文に本数が入っている", [htmllib.unescape(a) for a in rows_] == want_, rows_[:2])
    pop = re.search(r'<div class="tf-popular"[\s\S]*?</ul>', body_)
    pop_titles = [htmllib.unescape(strip_tags(t)) for t in re.findall(r'<a class="item-title-link"[^>]*>(.*?)</a>', pop.group(0), re.S)] if pop else []
    check(f"{label}: 人気順で上位の作品に、未成年を連想させるタイトルの作品が無い", not any(is_minor_title(t) for t in pop_titles), pop_titles[:2])
    check(f"{label}: 人気順で上位の作品は facts の5本まで", len(pop_titles) <= min(5, len(fx.get("popular", []))), len(pop_titles))



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
        # 注目の作品は、こちらから勧める欄なので、未成年を連想させるタイトルの作品は出さない（2026-10-07）
        minor_picks = [q["cid"] for q in (r.get("picks") or []) if isinstance(q, dict) and q.get("cid") in valid and is_minor_title(valid[q["cid"]].get("title"))]
        picked = [q["cid"] for q in (r.get("picks") or []) if isinstance(q, dict) and q.get("cid") in valid and q["cid"] not in minor_picks]
        check(f"{week}: 未成年を連想させるタイトルの作品は、注目の作品のカードに出さない", all(f'href="/item/{c}/"' not in re.sub(r'<section class="section" aria-labelledby="week-list-title">[\s\S]*', "", html) for c in minor_picks), minor_picks)
        check(f"{week}: 注目の作品（{len(picked)}件）へのリンクが記事にある", all(f'href="/item/{c}/"' in html for c in picked), [c for c in picked if f'href="/item/{c}/"' not in html][:3])
        if picked:
            notes_ = [str(q.get("note", "")).strip() for q in r["picks"] if isinstance(q, dict) and q.get("cid") in picked]
            check(f"{week}: 注目の作品は、横長のカード（表紙・タイトル・出演者/メーカー/発売日・ひとこと）で読みやすく（運営者の指摘。2026-10-05）",
                  html.count('<article class="pick-card">') == len(picked) and html.count('class="pick-note"') == len(picked) and all(n[:15] in html for n in notes_), (html.count('<article class="pick-card">'), len(picked)))
        # この週の傾向（2026-10-07 から）: 文と、書いたときの数字（facts）の表。表の作品に、未成年を連想させるタイトルの作品を入れない
        trend_ = str(r.get("trend") or "").strip()
        if not trend_:
            check(f"{week}: 傾向の無い記事には「この週の傾向」の欄を出さない", 'id="week-trend-title"' not in html)
        else:
            tsec = re.search(r'<section class="section" aria-labelledby="week-trend-title">([\s\S]*?)</section>', html)
            body_ = tsec.group(1) if tsec else ""
            check(f"{week}: 「この週の傾向」の欄に、記事の傾向の文がある", bool(tsec) and trend_[:20] in body_ and trend_[-12:] in body_)
            fx = r.get("facts") if isinstance(r.get("facts"), dict) else None
            if fx:
                check_trend_facts(week, body_, fx, "この週", "前の週")


# ---- 月のまとめ記事（monthly.json。2026-10-07 から）: 月のページのいちばん上に、導入文・この月の傾向・注目の作品 ----
print("\n■ 月のまとめ記事")
MONTHLY = os.path.join(ROOT, "site", "src", "data", "monthly.json")
months_raw = json.load(open(MONTHLY, encoding="utf-8")) if os.path.isfile(MONTHLY) else []
month_dir = os.path.join(DIST, "month")
month_pages_built = {os.path.basename(os.path.dirname(f)) for f in glob.glob(os.path.join(month_dir, "*", "index.html"))}
shown_months = 0
for r in months_raw if isinstance(months_raw, list) else []:
    if not (isinstance(r, dict) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(r.get("month", ""))) and str(r.get("lead", "")).strip() and DAY.match(str(r.get("written", "")))):
        continue
    ym = r["month"]
    if ym not in month_pages_built:
        continue
    shown_months += 1
    html = read(os.path.join(month_dir, ym, "index.html"))
    art = re.search(r'<article class="month-article"[\s\S]*?</article>\s*(?=<section|</div>)', html)
    body_ = art.group(0) if art else ""
    check(f"{ym}: 月のページのいちばん上（作品の一覧より前）に、月のまとめ記事（導入文・公開日）がある",
          bool(art) and r["lead"].strip()[:20] in body_ and f'datetime="{r["written"]}"' in body_ and html.find('class="month-article"') < html.find('id="works-title"'))
    arts = [a for a in (json.loads(b) for b in LD_BLOCK.findall(html)) if isinstance(a, dict) and a.get("@type") == "Article"]
    check(f"{ym}: 記事の構造化データ（Article）の公開日がデータの written と同じ", len(arts) == 1 and arts[0].get("datePublished") == r["written"], arts[:1])
    check(f"{ym}: sitemap の lastmod が公開日より前でない", lastmod_of.get(f"/month/{ym}/", "") >= r["written"], lastmod_of.get(f"/month/{ym}/"))
    check(f"{ym}: 説明文(description)は記事の導入文から", r["lead"].strip()[:20] in htmllib.unescape(re.search(r'<meta name="description" content="([^"]*)"', html).group(1)))
    picked = [q["cid"] for q in (r.get("picks") or []) if isinstance(q, dict) and q.get("cid") in valid and str(everything.get(q["cid"], {}).get("date", ""))[:7] == ym
              and not is_minor_title(valid[q["cid"]].get("title"))]
    check(f"{ym}: 注目の作品（{len(picked)}件）のカード", body_.count('<article class="pick-card">') == len(picked) and all(f'href="/item/{c}/"' in body_ for c in picked),
          body_.count('<article class="pick-card">'))
    trend_ = str(r.get("trend") or "").strip()
    if trend_:
        tsec = re.search(r'<section class="section" aria-labelledby="month-trend-title">([\s\S]*?)</section>', body_)
        check(f"{ym}: 「この月の傾向」の欄に、記事の傾向の文がある", bool(tsec) and trend_[:20] in tsec.group(1))
        if tsec and isinstance(r.get("facts"), dict):
            check_trend_facts(ym, tsec.group(1), r["facts"], "この月", "前の月")
check("月のまとめ記事の無い月のページには、記事の欄を出さない", all('class="month-article"' not in read(os.path.join(month_dir, m, "index.html"))
      for m in month_pages_built - {r.get("month") for r in months_raw if isinstance(r, dict)}))
print(f"  （月のまとめ記事 {shown_months}本を確認）")

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
    has_script = 'src="/lightbox.js?v=' in html
    if shown:
        if not (links == shown and has_dialog and has_script):
            bad_samples.append((cid, shown, links, has_dialog, has_script))
    elif links or has_dialog:
        bad_samples.append((cid, 0, links, has_dialog, has_script))
check("サンプル画像のある作品ページに、拡大表示の部品（リンク・ダイアログ・スクリプト）が揃っている", not bad_samples, bad_samples[:3])
bad_actions = []
for p_ in sorted(glob.glob(os.path.join(DIST, "item", "*", "index.html")))[:400]:
    h_ = read_raw(p_)
    m_ = re.search(r'<div class="detail-actions">([\s\S]*?)</div>', h_)
    if not m_ or 'class="fav-btn' not in m_.group(1) or ('detail-cta' in h_ and 'detail-cta' not in m_.group(1)):
        bad_actions.append(rel(p_))
check("作品ページの「FANZAで詳細を見る」と「お気に入りに追加」は、すき間のある並び（.detail-actions）の中（くっつかない）", not bad_actions, bad_actions[:3])
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
        if 'src="/movie.js?v=' not in text:
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
        if 'src="/movie.js?v=' in text:
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
_py_sites = re.findall(r'\{"key": "([a-z]+)", "name": "([^"]+)", "url": "([^"]+)"', read(os.path.join(ROOT, "scripts", "agency_links.py")))
check("所属事務所のデータ（agencies.json）: 決まった事務所だけ（画面の一覧と、集める道具の一覧が同じ）・出どころが事務所の公式サイト・生年月日などの項目は無い",
      len(AGENCY_SITES) >= 5 and [(k, n, u) for k, (n, u) in AGENCY_SITES.items()] == _py_sites and all(_agency_ok(r) for r in _agency_rows) and not any(k in r for r in _agency_rows for k in ("birthday", "birth", "blood", "pref", "hobby")),
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
        check("検索の部品がある（ページを開いたときから見える＝索引を待たない。索引のURLを持つ）", bool(section) and "hidden" not in section[0] and section[0].get("data-index") == "/data/actresses-index.json" and 'src="/actress-search.js?v=' in stext, section[:1])
        # はじめの一覧（条件なし・作品の多い順の、はじめの30人。2026-10-07）: ブラウザの actress-search.js と同じ並び（作品の多い順・同じ本数は読みの順）・同じ人数の文
        _page_size = int(re.search(r"export const ACTRESS_PAGE_SIZE = (\d+);", read(os.path.join(ROOT, "site", "src", "lib", "profiles.js"))).group(1))
        def _as_text(t):
            t = "" if t is None else str(t)
            if re.fullmatch(r"[ぁ-ゖー]*", t):
                return t
            t = _ud.normalize("NFKC", t).lower()
            t = re.sub(r"[ァ-ヶ]", lambda m_: chr(ord(m_.group(0)) - 0x60), t)
            return re.sub(r"[\s　・·.・]", "", t)
        _tmpl = act_index.get("list", "") if isinstance(act_index, dict) else ""
        def _row_ok(r):
            if isinstance(r.get("s"), str) and re.fullmatch(r"[0-9a-f]{10}", r["s"]):
                return True
            if r.get("l"):
                return fanza_https(r["l"], ["fanza.co.jp", "dmm.co.jp"])
            return bool(re.fullmatch(r"\d{1,12}", str(r.get("id", "")))) and isinstance(_tmpl, str) and _tmpl.count("{ID}") == 1 and fanza_https(_tmpl, ["fanza.co.jp", "dmm.co.jp"])
        _valid = [(i_, r) for i_, r in enumerate(x for x in rows if isinstance(x, dict) and isinstance(x.get("n"), str) and x.get("n"))]
        _order = sorted(_valid, key=lambda p_: (-(p_[1].get("k") or 0), _as_text(p_[1].get("r") or p_[1]["n"]), p_[0]))
        _want = [r for _, r in _order if _row_ok(r)]
        _ul = re.search(r'<ul id="as-list" class="actress-list" data-first="1">(.*?)</ul>', stext, re.S)
        _got_keys = [t.get("data-key") for t in tags(_ul.group(1), "li")] if _ul else []
        _want_keys = [f"{r.get('id', '')}|{r['n']}" for r in _want[:_page_size]]
        _count = re.search(r'<p id="as-count" class="as-count" aria-live="polite">(.*?)</p>', stext, re.S)
        check(f"女優検索: はじめの一覧（条件なし・作品の多い順の、はじめの{_page_size}人）がページに入っていて、ブラウザで作る一覧と同じ並び・同じ人数の文（索引を待たずに見える）",
              bool(_ul) and _got_keys == _want_keys and bool(_count) and strip_tags(_count.group(1)).strip() == f"{len(_want):,}人が見つかりました",
              (_got_keys[:3], _want_keys[:3], strip_tags(_count.group(1)).strip() if _count else None, len(_want)))
        _more = [t for t in tags(stext, "button") if t.get("id") == "as-more"]
        check("女優検索: 「もっと見る」は、はじめの一覧より多いときだけ、はじめから出ている", bool(_more) and (("hidden" in _more[0]) == (len(_want) <= _page_size)), _more[:1])
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
            want_hint = f"多いのは{common_.replace('-', '〜')}cm" if common_ else ""
            legend_ = re.search(r'<fieldset class="as-cups as-sizes">\s*<legend class="as-range-label">\s*%s（cm）(.*?)</legend>' % label_, stext, re.S)
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
        check("索引が空のときは、検索の部品を出さない", 'id="actress-search"' not in stext and 'src="/actress-search.js?v=' not in stext)
    _static_m = re.search(r'<section id="actress-static"[^>]*>(.*?)</section>', stext, re.S)
    static_rows = len([t for t in tags(_static_m.group(1) if _static_m else "", "li") if has_class(t, "actress-row")])
    index_limit = int(re.search(r"export const ACTRESS_FALLBACK_LIMIT = (\d+);", read(os.path.join(ROOT, "site", "src", "config.js"))).group(1))
    check(f"JavaScriptが使えないとき用の一覧に、専用ページのある出演者がいる（{len(actress_pages)}人。多いときは作品数の多い順に{index_limit}人まで）", static_rows == min(len(actress_pages), index_limit) and any(t.get("id") == "actress-static" for t in tags(stext, "section")), (static_rows, len(actress_pages)))
    check("検索の注意書き（載っていない人は絞り込みで外れる・FANZA公式のデータ。短い1文。2026-10-06）が、ページにある", (not rows) or ("結果に出ません" in stext and "FANZA公式の情報" in stext))

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
    top3_html = re.search(r'<section id="ranking"[\s\S]*?</section>', home_html)
    check("TOP3の欄は、トップのはじめのほう（発売中の新作より前）にあり、欄の中にランキングのページへのボタンは置かない（運営者の希望。2026-10-05）",
          home_html.find('id="ranking"') < home_html.find('id="released"') and top3_html is not None and 'chip-link' not in top3_html.group(0) and 'today-links' not in home_html)
else:
    check("新着の人気順も売れ筋（新しいもの）も無いときは、TOP3の欄を出さない", not home_sections and not medal_cells and 'href="#ranking"' not in home_html)

# きょうの数字（発売本数の欄）は、運営者の判断で外した（2026-10-05。today.json の本数は、いまは画面に出さない）
check("トップに「きょうの数字」（発売本数の欄）が無い", 'id="stats"' not in home_html and "FANZA動画（ビデオ）全体の本数" not in home_html)

# きょうの話題: 種類ごとの札・リンク先（作品ページ・女優のページ・まとめ記事・セールのページ・FANZA）
TOPIC_LABELS = {"rise": "急上昇", "today": "きょう発売", "upcoming": "予約で人気", "entry": "予約に初登場", "debut": "デビュー作", "actress": "人気の女優", "weekly": "週のまとめ",
                "salenew": "セール開始", "sale": "もうすぐ終わる", "salehot": "セールで人気", "event": "イベント"}
TOPICS_LIMIT = int(re.search(r"TOPICS_LIMIT = (\d+)", read(os.path.join(ROOT, "site", "src", "lib", "topics.js"))).group(1))
SALE_END_KINDS = ("sale", "salenew", "salehot")  # セールの終わりの時刻（data-sale-end）を持つ話題
# 話題の作品がVR作品のときは、すぐ後ろに、同じ種類のVRでない次の作品（.topic-alt。「VR作品を隠す」のときだけ出る）が付くことがある
topic_all = [(m.group(1), bool(m.group(2)), m.group(3), m.group(4)) for m in re.finditer(r'<li class="topic topic-([a-z]+)( topic-alt)?"([^>]*)>(.*?)</li>', home_html, re.S)]
topic_cells = [(k, a, inner) for k, alt, a, inner in topic_all if not alt]
bad_alt = [k for n, (k, alt, a, _) in enumerate(topic_all) if alt and ('data-vr="true"' in a or n == 0 or topic_all[n - 1][0] != k or topic_all[n - 1][1] or 'data-vr="true"' not in topic_all[n - 1][2])]
check(f"きょうの話題: VR作品の話題の繰り上げ（{sum(1 for x in topic_all if x[1])}件）は、VR作品の話題のすぐ後ろで同じ種類・VRの印なし", not bad_alt, bad_alt[:3])
# こちらから案内する欄なので、作品の話題に、未成年を連想させるタイトルの作品は出さない（運命の作品と同じ。2026-10-06）
_minor_topics = [htmllib.unescape(strip_tags(t)) for k, _, _, inner in topic_all if k in ("rise", "today", "upcoming", "entry", "salehot")
                 for t in re.findall(r'<span class="topic-title">(.*?)</span>', inner, re.S) if is_minor_title(htmllib.unescape(strip_tags(t)))]
check("きょうの話題の作品に、未成年を連想させるタイトルの作品が無い", not _minor_topics, _minor_topics[:2])
bad_topic = []
for kind, attrs, inner in [(k, a, inner) for k, _, a, inner in topic_all]:
    a_ = next((t for t in tags(inner, "a") if has_class(t, "topic-link")), {})
    href = a_.get("href", "")
    label = re.search(r'<span class="topic-tag">([^<]*)</span>', inner)
    if kind not in TOPIC_LABELS or not label or label.group(1) != TOPIC_LABELS[kind]:
        bad_topic.append((kind, "札"))
    elif href.startswith("/"):
        if not os.path.isfile(page_file(href)) or (kind not in ("actress", "weekly", "sale", "salenew", "event") and not href.startswith("/item/")):
            bad_topic.append((kind, href))
        elif kind in ("sale", "salenew") and not re.fullmatch(r"/sale/#sale-\d+|/sale/[0-9a-f]{10}/", href):  # セールの話題は、その特集のページ（無ければ、セールのページの、その特集の見出し）へ
            bad_topic.append((kind, href))
        elif kind == "event" and not re.fullmatch(r"/event/#ev-\d{8}-[a-z0-9]+", href):  # イベントの話題は、イベント情報のページの、そのイベントの行へ
            bad_topic.append((kind, href))
    elif not (fanza_https(href, FANZA_LINK) and SPONSORED <= set(a_.get("rel", "").split()) and a_.get("target") == "_blank") or kind in ("weekly", "sale", "salenew", "event"):
        bad_topic.append((kind, href))
    if href in top_hrefs[:3]:
        bad_topic.append((kind, "TOP3と同じ作品"))
    if ("data-sale-end" in attrs) != (kind in SALE_END_KINDS) or (kind in SALE_END_KINDS and not re.search(r'data-sale-end="\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:59\+09:00"', attrs)):
        bad_topic.append((kind, "セールの終わり"))
check(f"きょうの話題（{len(topic_cells)}件。{TOPICS_LIMIT}件まで）: 種類ごとの札と、リンク先（サイトの中はあるページ・外はFANZAで広告のリンクの属性つき）。TOP3の作品は出さない",
      len(topic_cells) <= TOPICS_LIMIT and not bad_topic and (not topic_cells or 'id="topics"' in home_html), bad_topic[:3])
# セールの話題の見出しは、FANZAの特集の名前そのまま（「今月のおすすめ30％OFF」など）なので、評価の言葉の検査からは外す
topic_text = " ".join(re.sub(r"<[^>]+>", "", re.sub(r'<span class="topic-title">.*?</span>', "", inner, flags=re.S) if k in ("sale", "salenew") else inner) for k, _, _, inner in topic_all)
check("きょうの話題: 評価の言葉を書かない（データで決まった形の文だけ）", not re.search(r"おすすめ|話題作|必見|最高傑作|大人気|神作", topic_text))
if any(k in SALE_END_KINDS for k, _, _ in topic_cells):
    check("きょうの話題に、セール開始・もうすぐ終わるセール・セールで人気があるときは、終わったら隠すスクリプト（sale.js）がある", sale_js_ok(read_raw(os.path.join(DIST, 'index.html'))))
warn("きょうの話題が、トップにある（データがそろっていれば出る）", bool(topic_cells) or not pop_new)

# 女優のイベント情報（data/events.json。所属事務所の公式サイトのイベントの一覧から毎日。運営者の希望。2026-10-05）。
# 決まった項目だけ（住所・電話などは無い）・決まった事務所・URLは事務所の公式サイト・きょうから60日先までを、/event/ に日付ごとに。
# 公式サイトへのリンクは広告ではない（sponsored を付けない）。トップの「きょうの話題」のイベントは、/event/ のそのイベントの行へ
print("\n■ 女優のイベント情報")
_events_src = read(os.path.join(ROOT, "site", "src", "lib", "events.js"))
EVENT_KINDS = re.findall(r"'([^']+)'", re.search(r"EVENT_KINDS = \[([^\]]+)\]", _events_src).group(1))
EVENT_DAYS = int(re.search(r"EVENT_DAYS = (\d+)", _events_src).group(1))
try:
    _events_data = json.load(open(os.path.join(ROOT, "site", "src", "data", "events.json"), encoding="utf-8"))
except (OSError, ValueError):
    _events_data = {}
_event_rows = [r for r in (_events_data.get("rows") if isinstance(_events_data, dict) and isinstance(_events_data.get("rows"), list) else []) if isinstance(r, dict)]
_cc_spec = importlib.util.spec_from_file_location("claude_comments_v", os.path.join(ROOT, "scripts", "claude_comments.py"))
_cc = importlib.util.module_from_spec(_cc_spec)
_cc_spec.loader.exec_module(_cc)
_ev_end = (datetime.date.fromisoformat(JST_TODAY) + datetime.timedelta(days=EVENT_DAYS)).isoformat()
_ev_ok = lambda r: (r.get("agency") in AGENCY_SITES and r.get("kind") in EVENT_KINDS and str(r.get("url", "")).startswith(AGENCY_SITES[r["agency"]][1])
                    and not re.search(r"[\s\"'<>\\]", str(r.get("url", ""))) and isinstance(r.get("names"), list) and any(isinstance(n, str) and n.strip() for n in r["names"])
                    and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("date", ""))) and _cc.title_block_reason({"title": r.get("title", "")}) != "minor"
                    and _cc.title_block_reason({"title": r.get("place", "")}) != "minor")
check("イベントのデータ（events.json）: 決まった項目だけ（住所・電話・料金などは無い）・決まった事務所・URLは事務所の公式サイト・知っている種類",
      all(set(r) <= {"date", "time", "names", "agency", "kind", "title", "place", "url", "seen"} and _ev_ok(r) for r in _event_rows),
      [r for r in _event_rows if not (set(r) <= {"date", "time", "names", "agency", "kind", "title", "place", "url", "seen"} and _ev_ok(r))][:2])
event_want = [r for r in _event_rows if _ev_ok(r) and JST_TODAY <= r["date"] <= _ev_end]
event_page = os.path.join(DIST, "event", "index.html")
event_html = read(event_page) if os.path.isfile(event_page) else ""
event_ids = re.findall(r'<li class="event-row" id="(ev-\d{8}-[a-z0-9]+)"', event_html)
home_foot = re.search(r'<nav class="foot-nav"[\s\S]*?</nav>', home_html)
if event_want:
    check(f"イベント情報のページ（/event/）: きょうから{EVENT_DAYS}日先までのイベント（{len(event_want)}件）が1行ずつ・行の印（id）は1つずつ違う・検索エンジンに出す・sitemap にある",
          len(event_ids) == len(event_want) and len(set(event_ids)) == len(event_ids) and 'name="robots" content="noindex' not in read_raw(event_page)
          and (not os.path.isfile(sitemap_path) or "/event/" in sm_paths), (len(event_ids), len(event_want)))
    src_links = [t for t in tags(event_html, "a") if has_class(t, "event-src")]
    bad_src = [t.get("href") for t in src_links if set(t.get("rel", "").split()) != {"nofollow", "noopener", "noreferrer"} or t.get("target") != "_blank"
               or not any(str(t.get("href", "")).startswith(u) for _, u in AGENCY_SITES.values())]
    check("イベントの「公式サイトで見る」: 1行に1つ・事務所の公式サイトへ・広告ではないので sponsored なし（nofollow noopener noreferrer・新しいタブ）", len(src_links) == len(event_ids) and not bad_src, bad_src[:3])
    check("イベント情報のページに「○日の時点」「公式サイトで確かめて」の注記・出どころの事務所の名前", "の時点" in event_html and "公式サイトで確かめて" in event_html and "出どころは" in event_html)
    check("フッターに、イベント情報のページへのリンク", bool(home_foot) and 'href="/event/"' in home_foot.group(0))
    ev_topics = [(re.search(r'href="([^"]+)"', inner) or [None, ""])[1] for k, _, _, inner in topic_all if k == "event"]
    check(f"きょうの話題のイベント（{len(ev_topics)}件。2件まで）: イベント情報のページにある行へ", len(ev_topics) <= 2 and all(h.split("#", 1)[-1] in event_ids for h in ev_topics), ev_topics)
    check("きょうの話題の下に「女優のイベントの予定（○件）」のリンク", f'href="/event/">女優のイベントの予定（{len(event_want)}件）' in re.sub(r"<wbr>|</?span[^>]*>", "", home_html))
else:
    check("イベントが無いあいだは、イベント情報のページが noindex で、sitemap・フッター・きょうの話題に出さない",
          (not event_html or 'name="robots" content="noindex' in read_raw(event_page)) and (not os.path.isfile(sitemap_path) or "/event/" not in sm_paths)
          and not (home_foot and 'href="/event/"' in home_foot.group(0)) and not any(k == "event" for k, _, _ in topic_cells))
_ev_names = {n.strip() for r in event_want for n in r["names"] if isinstance(n, str)}
bad_ev_actress = []
for pth in actress_pages:
    text = read(pth)
    m = re.search(r'<h1 class="hero-title">(.*?)</h1>', text, re.S)
    h1_text = htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""
    name = h1_text[: -len("の新作・出演作品")] if h1_text.endswith("の新作・出演作品") else ""
    if ('id="events-title"' in text) != (name in _ev_names):
        bad_ev_actress.append(name)
check("出演者のページの「イベントの予定」: イベントがある人だけ", not bad_ev_actress, bad_ev_actress[:3])

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
_gcand = {}  # ジャンルごとの、札の表紙に使える作品の本数
for c in sorted((c for c in everything if c in pop_new and pop_new[c] <= 100 and _top_from <= str(everything[c]["date"])[:10] <= JST_TODAY),
                key=lambda c: (pop_new[c], -int(str(everything[c]["date"])[:10].replace("-", "")), c))[:100]:
    for g in dict.fromkeys(everything[c].get("genres") or []):
        if g in _tag_genres and g != "ベスト・総集編":
            sc, n, ok_ = _gboard.get(g, (0, 0, False))
            _gboard[g] = (sc + 101 - pop_new[c], n + 1, ok_ or not is_minor_title(everything[c].get("title")))
            if not is_minor_title(everything[c].get("title")):
                _gcand[g] = _gcand.get(g, 0) + 1
# 上から3つのうち、札の表紙に使える作品（未成年を連想させるタイトルでない作品）が無いジャンルは出さない（site/src/lib/topics.js の hotGenres と同じ）
want_genres = [g for g, v in sorted(_gboard.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))[:3] if v[2]]
genre_m = re.search(r'<ol class="hot-genres">(.*?)</ol>', home_html, re.S)
got_genres = [htmllib.unescape(re.sub(r"<[^>]+>", "", n)) for n in re.findall(r'<span class="genre-name"><span class="visually-hidden">[^<]*</span>(.*?)</span>', genre_m.group(1), re.S)] if genre_m else []
if want_genres:
    check(f"人気のジャンル: {len(want_genres)}つが、いま人気の女優と同じ数え方の順に並ぶ（ジャンルのページの一覧のジャンルだけ）・いま人気の女優の真下", got_genres == want_genres and home_html.find('id="hot"') < home_html.find('id="genres"') < home_html.find('id="topics"'), (got_genres, want_genres))
    bad_glink = [h for h in re.findall(r'<a class="genre-link" href="([^"]+)"', genre_m.group(1)) if not (h.startswith("/tag/") and os.path.isfile(page_file(h))) and not h.startswith("/search/?tag=")]
    check("人気のジャンル: タップで、ジャンルのページ（無ければ作品検索のジャンル絞り込み）へ", not bad_glink, bad_glink[:3])
    # 札の表紙は、上のジャンルで使った作品を使わず、次の作品へ繰り下げる（運営者の希望。2026-10-07）。どのジャンルにも3本以上あれば、必ず別々になる
    genre_srcs = re.findall(r'<img class="genre-img[^"]*" src="([^"]+)"', genre_m.group(1))
    if all(_gcand.get(g, 0) >= len(want_genres) for g in want_genres):
        check("人気のジャンル: 札の表紙が重ならない（上のジャンルで使った作品は、人気順に次の作品へ繰り下げる）", len(genre_srcs) == len(want_genres) and len(set(genre_srcs)) == len(genre_srcs), genre_srcs)
else:
    check("人気のジャンルが無いときは、欄を出さない", 'id="genres"' not in home_html)

# 発売中の新作の、きょうの日付のすぐ下のコーナー（今週のデビュー作・誕生日の近い女優。運営者の希望。2026-10-05）。
# 運命の作品は、発売中の新作のいちばん下（予約受付中の真上。2026-10-05 夜）
rel_start = home_html.find('id="released"')
days_in_rel = [m.start() for m in re.finditer(r'<section class="day"', home_html) if m.start() > rel_start and (home_html.find('id="upcoming"') < 0 or m.start() < home_html.find('id="upcoming"'))]
corner_at = home_html.find('<div id="pick-corner" class="corner"')
check("おすすめのコーナーの目印（id=\"pick-corner\"）が、コーナーがあるときだけある", (corner_at >= 0) == ('class="corner"' in home_html))
if corner_at >= 0:
    check("おすすめのコーナーは、発売中の新作の、いちばん新しい日付のすぐ下（次の日付の上）", len(days_in_rel) >= 1 and days_in_rel[0] < corner_at and (len(days_in_rel) < 2 or corner_at < days_in_rel[1]), (days_in_rel[:2], corner_at))
gacha_home_at = home_html.find('<div id="gacha-home" class="gacha-home">')
if gacha_home_at >= 0:
    up_at = home_html.find('<section id="upcoming"')
    more_at = home_html.find('過去の作品をすべて見る', rel_start)
    check("運命の作品は、発売中の新作のいちばん下（日付の棚と「過去の作品をすべて見る」の後ろ・予約受付中の前）にあり、おすすめのコーナーの中には無い",
          bool(days_in_rel) and days_in_rel[-1] < gacha_home_at and (more_at < 0 or more_at < gacha_home_at) and (up_at < 0 or gacha_home_at < up_at)
          and home_html.find('<section id="gacha"') > gacha_home_at and (corner_at < 0 or home_html.find('<section id="gacha"') > home_html.find('</div>', corner_at)),
          (days_in_rel[-1:] , gacha_home_at, up_at))

# 予約受付中: 発売日が近い12本だけを先に見せ、残りは「もっと見る」（運営者の「下のほうが重い」。2026-10-07）。残りもHTMLには入れる（予約の一覧ページは無いため）
_shown_m = re.search(r"export const HOME_UPCOMING_SHOWN = (\d+);", read(os.path.join(ROOT, "site", "src", "config.js")))
_up_m = re.search(r'<section id="upcoming"[^>]*>(.*?)</section>\s*(?=</div>)', home_html, re.S)
if _shown_m and _up_m:
    _fold_n = int(_shown_m.group(1))
    _up_open = re.search(r'<section id="upcoming"[^>]*>', home_html).group(0)
    _up_cells = re.findall(r'<li class="shelf-cell([^"]*)"[^>]*>(.*?)</li>', _up_m.group(1), re.S)
    _note_n = re.search(r'発売日が近い順・(\d+)本', _up_m.group(1))
    check("予約受付中: 「○本」と同じ数の作品が、HTMLにすべて入っている（予約の一覧ページは無いため）", bool(_note_n) and int(_note_n.group(1)) == len(_up_cells), (_note_n.group(1) if _note_n else None, len(_up_cells)))
    if len(_up_cells) > _fold_n:
        _offs = ["fold-off" in c for c, _ in _up_cells]
        _btn = re.search(r'<button type="button" class="btn btn-quiet more-btn" data-fold-more>もっと見る（あと<span data-fold-rest>(\d+)</span>本）</button>', _up_m.group(1))
        check(f"予約受付中: 発売日が近い{_fold_n}本だけを先に見せ、残りはたたむ（data-fold・fold-off）。「もっと見る（あと○本）」のボタンは、はじめから出ている（あとから出てきて下がずれないように。JavaScript が使えないときだけ CSS で隠す）",
              f'data-fold="{_fold_n}"' in _up_open and _offs == [i >= _fold_n for i in range(len(_offs))] and bool(_btn) and int(_btn.group(1)) == len(_up_cells) - _fold_n, (_up_open, sum(_offs), _btn.group(0) if _btn else None))
        check("予約受付中: たたんだ作品の画像は、すぐには読まない（loading=\"lazy\"）", all('loading="lazy"' in inner and 'loading="eager"' not in inner for c, inner in _up_cells if "fold-off" in c))
        _days = re.findall(r'<section class="day([^"]*)"[^>]*>(.*?)</section>', _up_m.group(1), re.S)
        check("予約受付中: 全部がたたまれた日付は、見出しごとたたむ（fold-empty）・一部だけの日付は、たたまない",
              all(("fold-empty" in dc) == all("fold-off" in c for c in re.findall(r'<li class="shelf-cell([^"]*)"', inner)) for dc, inner in _days), [dc for dc, _ in _days])
    else:
        check("予約受付中: 先に見せる本数以下のときは、たたまない（ボタンも無い）", 'data-fold' not in _up_m.group(0) and "fold-off" not in _up_m.group(1) and "data-fold-more" not in _up_m.group(1))

# パソコンの右の欄（運営者の希望「右のカラム（きょうの話題）の下に全て並べる」「作品を探すも右のカラムの上に」「週のまとめは概要だけ」「月のまとめはバックナンバー」。2026-10-05）:
# 作品を探す・いま人気の女優・人気のジャンル・きょうの話題・週のまとめ・月のまとめは .home-side の中。おすすめのコーナーは、HTMLではスマホの場所（発売中の中）にあり、パソコンのときだけ小さなスクリプトで右の欄へ移す
home_m = re.search(r'<div class="home has-side" style="--side-span: (\d+)">', home_html)
side_start = home_html.find('<div class="home-side">')
side_end = min([p for p in (home_html.find('<section id="sale"'), home_html.find('<section id="released"')) if p >= 0] or [-1])
side_html = home_html[side_start:side_end] if 0 <= side_start < side_end else ""
check("トップは .home で包まれ、右の欄（.home-side）が TOP3 の後・セール/発売中の前にある", home_m is not None and side_html != "" and home_html.find('<section id="ranking"') < side_start, (home_m.group(0) if home_m else None, side_start, side_end))
side_ids = [i for i in ("hot", "genres", "topics") if f'<section id="{i}"' in home_html]
check("右の欄に、作品を探す（いちばん先）と、ある欄（いま人気の女優・人気のジャンル・きょうの話題）がすべて入っている",
      side_html.find('<section class="find"') >= 0 and all(f'<section id="{i}"' in side_html for i in side_ids) and side_html.find('<section class="find"') < min([side_html.find(f'<section id="{i}"') for i in side_ids] or [len(side_html)]), side_ids)
main_ids = [home_html.find('<section id="ranking"') >= 0, home_html.find('<section id="sale"') >= 0, True, home_html.find('<section id="upcoming"') >= 0]
check(f"右の欄がまたぐ行の数（--side-span）= 左の欄の欄の数（TOP3・セール・発売中・予約のうち、あるもの）", home_m is not None and int(home_m.group(1)) == sum(main_ids), (home_m.group(1) if home_m else None, main_ids))
find_html = re.search(r'<section class="find"[\s\S]*?</section>', side_html)
side_month_counts = {}
for x in curated.values():
    side_month_counts[x["date"][:7]] = side_month_counts.get(x["date"][:7], 0) + 1
side_months = sorted([ym for ym, n in side_month_counts.items() if n >= config_value("MONTH_MIN_ITEMS")], reverse=True)
check("作品を探すの「月ごと」「週のまとめ」は、スマホだけ（only-narrow。パソコンは右の欄に専用の欄がある）",
      bool(find_html) and all(re.search(r'<a class="chip-link only-narrow" href="' + h, find_html.group(0)) for h, want in (("/month/", bool(side_months)), ("/weekly/", bool(rounds))) if want)
      and not re.search(r'<a class="chip-link" href="/(month|weekly)/', find_html.group(0)))
if rounds:
    newest_w = max(rounds)
    wk = re.search(r'<section id="weekly" class="side-weekly side-only"[\s\S]*?</section>', side_html)
    check("右の欄の週のまとめ: いちばん新しい週の概要（はじめの1文）と、記事・一覧へのリンク", bool(wk) and f'href="/weekly/{newest_w}/"' in wk.group(0) and 'href="/weekly/"' in wk.group(0)
          and strip_tags(wk.group(0)).find(rounds[newest_w]["lead"].strip().split("。")[0][:20]) >= 0, wk.group(0)[:200] if wk else None)
else:
    check("週のまとめが無いあいだは、右の欄に週のまとめの欄を出さない", 'id="weekly"' not in home_html)
months_back = [ym for ym in side_months if ym <= JST_TODAY[:7]]
mo = re.search(r'<section id="months" class="side-months side-only"[\s\S]*?</section>', side_html)
if months_back:
    got_m = re.findall(r'<a class="backnumber-link" href="/month/(\d{4}-\d{2})/">', mo.group(0)) if mo else []
    check(f"右の欄のいちばん下の月のまとめ: きょうの月までの月のページが、新しい月から並ぶ（{len(months_back)}か月。12か月まで）", got_m == months_back[:12] and side_html.rfind("</section>") <= side_html.find('id="months"') + len(mo.group(0)) + 20 if mo else False, (got_m, months_back[:12]))
else:
    check("月のページが無いあいだは、月のまとめの欄を出さない", 'id="months"' not in home_html)
if corner_at >= 0:
    move = re.search(r"</div>\s*<script>(\(function\(\)\{var c=document\.getElementById\('pick-corner'\)[^<]*)</script>", home_html[corner_at:])
    check("パソコンでは、おすすめのコーナーを右の欄（#side-corner）へ移す小さなスクリプトが、コーナーのすぐ後ろにある（幅が変われば戻す）",
          '<div id="side-corner" class="side-corner"></div>' in side_html and '<div id="corner-home" class="corner-home">' in home_html[:corner_at]
          and move is not None and "min-width: 960px" in move.group(1) and "'side-corner'" in move.group(1) and "'corner-home'" in move.group(1) and "addEventListener('change'" in move.group(1))

if gacha_home_at >= 0:
    gmove = re.search(r"</div>\s*<script>(\(function\(\)\{var c=document\.getElementById\('gacha'\)[^<]*)</script>", home_html[gacha_home_at:])
    check("パソコンでは、運命の作品も右の欄の先頭（今週のデビュー作の上）へ移す小さなスクリプトが、すぐ後ろにある（幅が変われば戻す）",
          '<div id="side-corner" class="side-corner"></div>' in side_html and gmove is not None and "'gacha-home'" in gmove.group(1)
          and "insertBefore(c,t.firstChild)" in gmove.group(1) and "t===s&&true" in gmove.group(1) and "addEventListener('change'" in gmove.group(1))

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
    check("運命の作品: 見出し「運命の作品」・窓が3つ・「まわす」ボタン（候補がそろうまで押せない）・はじめから出ている（あとから出てきて下がずれないように。JavaScript が使えないときだけ CSS で隠す）・スクリプト（gacha.js）がある",
          bool(gacha_sec) and 'id="gacha-title" class="corner-title">運命の作品</h3>' in gacha_sec.group(0) and gacha_sec.group(0).count('class="reel"') == 3 and re.search(r'<button type="button" class="btn btn-hot gacha-btn" data-gacha-draw disabled>まわす</button>', gacha_sec.group(0)) is not None
          and re.search(r'<section id="gacha"[^>]*\bhidden\b', home_html) is None and 'src="/gacha.js?v=' in home_html and os.path.isfile(os.path.join(DIST, "gacha.js")) and gacha_home_at >= 0)
    check("運命の作品: ページに入れたデータの中に、タグの始まり（<）が無い", "<" not in gacha_m.group(1))
else:
    check("運命の作品の候補が無いときは、欄もスクリプトも出さない", 'id="gacha"' not in home_html and 'src="/gacha.js?v=' not in home_html)

# 今週のデビュー作: きょうまでの7日間に発売された「デビュー作品」を、新着の人気順に6本（出すのは3本。残りは差し替え用）
_wk_from = (datetime.date.fromisoformat(JST_TODAY) - datetime.timedelta(days=6)).isoformat()
want_debut = sorted((c for c in everything if "デビュー作品" in (everything[c].get("genres") or []) and _wk_from <= str(everything[c]["date"])[:10] <= JST_TODAY and not is_minor_title(everything[c].get("title"))),
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
no_fav_parts = [os.path.relpath(p, DIST) for p in all_pages if 'src="/favorites.js?v=' not in read(p) or 'href="/favorites/"' not in read(p)]
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
    _fav_html = read_raw(os.path.join(DIST, "favorites", "index.html")) if os.path.isfile(os.path.join(DIST, "favorites", "index.html")) else ""
    _fav_msg = re.search(r'<p class="empty" data-fav-empty>(.*?)</p>', _fav_html, re.S)
    _fav_js = read(os.path.join(DIST, "favorites.js")) if os.path.isfile(os.path.join(DIST, "favorites.js")) else ""
    check("お気に入りページ: お気に入りが無い人（html.fav-none）には「まだお気に入りがありません」を、はじめから出しておく（スクリプトと同じ文。あとから出てきて下がずれないように。2026-10-07）",
          bool(_fav_msg) and strip_tags(_fav_msg.group(1)).strip().replace("\u200b", "") in _fav_js.replace("\u200b", "") and "classList.add('fav-none')" in read_raw(os.path.join(DIST, "index.html")),
          _fav_msg.group(1)[:60] if _fav_msg else None)
check("トップに、お気に入りのお知らせ欄（#fav-banner）がある（ふだんは隠れていて、お気に入りの出演者・メーカーがある人（html.has-favs）には、はじめから場所を出す。はじめの文字つき）",
      bool(re.search(r'<a id="fav-banner"[^>]*\bhidden\b[^>]*>★ お気に入りの新作・予約を見る</a>', home_html)))

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
    # FANZAクレジット: DMMアフィリエイト公式の規定のHTML（FANZA クレジットのテキスト形式）を、1文字も変えずに（文節の区切りも入れずに）入れている。
    # ほかの形のクレジットのリンクは無い（2026-10-07。前は文字ぜんぶをリンクにして、class・target・rel を足していた）
    raw_ = read_raw(p)
    credit = [t for t in tags(raw_, "a") if str(t.get("href", "")).startswith("https://affiliate.dmm.com/api")]
    if raw_.count(DMM_CREDIT_OFFICIAL) != 1 or len(credit) != 1 or set(credit[0]) != {"href"}:
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
check(f"全ページの FANZA のクレジットが、DMMの規定のHTML（テキスト形式）のまま・1つだけ・items.js の DMM_CREDIT_HTML と同じ",
      not bad_credit and re.search(r"export const DMM_CREDIT_HTML = '([^']+)';", read(os.path.join(ROOT, "site", "src", "lib", "items.js"))).group(1) == DMM_CREDIT_OFFICIAL, bad_credit[:3])
bad_about = []
for p in pages:
    foot_ = read(p)[read(p).find("<footer") :]
    fa_ = re.search(r'<p class="foot-about">(.*?)</p>', foot_, re.S)
    if (not fa_ or '<a class="foot-link foot-small" href="/about/">このサイトについて</a>' not in fa_.group(1) or 'href="/feed.xml">RSS</a>' not in fa_.group(1)
            or not re.search(r'<button type="button" id="install-btn"[^>]*hidden>ホーム画面に追加</button>', fa_.group(1)) or foot_.find('class="foot-about"') < foot_.find('class="foot-credit"')):
        bad_about.append(os.path.relpath(p, DIST))
    head_ = read_raw(p).split("</head>", 1)[0]
    if '<link rel="manifest" href="/site.webmanifest"' not in head_ or 'type="application/rss+xml"' not in head_ or 'src="/install.js?v=' not in read_raw(p):
        bad_about.append(("head", os.path.relpath(p, DIST)))
check("全ページのフッターのいちばん下に、小さな「このサイトについて」「RSS」「ホーム画面に追加」（最初は隠れている）があり、<head> にホーム画面に追加の設定と RSS の案内がある（運営者の希望。2026-10-06）", not bad_about, bad_about[:3])
# ホーム画面に追加の設定（/site.webmanifest）とアイコン、RSS（/feed.xml・/weekly/feed.xml）
try:
    _mf = json.load(open(os.path.join(DIST, "site.webmanifest"), encoding="utf-8"))
except (OSError, ValueError):
    _mf = {}
check("ホーム画面に追加の設定（/site.webmanifest）: 名前・開くページ・表示のしかた（iPhone で戻るボタンが使える minimal-ui）・アイコン（192・512・maskable）がある",
      _mf.get("name") and _mf.get("start_url") == "/" and _mf.get("display") == "minimal-ui" and {i.get("sizes") for i in _mf.get("icons", [])} >= {"192x192", "512x512"}
      and any(i.get("purpose") == "maskable" for i in _mf.get("icons", [])) and all(os.path.isfile(os.path.join(DIST, str(i.get("src", "")).lstrip("/"))) for i in _mf.get("icons", [])))
import xml.etree.ElementTree as _ET
SITE_URL_V = re.search(r"export const SITE_URL = '([^']+)'", read(os.path.join(ROOT, "site", "src", "config.js"))).group(1)
for _fp in ("feed.xml", os.path.join("weekly", "feed.xml")):
    try:
        _feed = _ET.parse(os.path.join(DIST, _fp)).getroot()
    except (OSError, _ET.ParseError) as e_:
        _feed = None
    _links = [x.findtext("link") for x in (_feed.iter("item") if _feed is not None else [])]
    _titles = [x.findtext("title") for x in (_feed.iter("item") if _feed is not None else [])]
    check(f"RSS（/{_fp}）: 読める XML・RSS 2.0・リンク先はサイトにあるページ・未成年を連想させるタイトルは無い（{len(_links)}件）",
          _feed is not None and _feed.tag == "rss" and _feed.get("version") == "2.0" and all(l and l.startswith(SITE_URL_V) and os.path.isfile(page_file(l[len(SITE_URL_V):])) for l in _links)
          and not any(is_minor_title(t) for t in _titles), _links[:2])
_about = page_file("/about/")
_about_html = read(_about) if os.path.isfile(_about) else ""
check("このサイトについて（/about/）: 情報の出どころ（FANZA公式のAPI・所属事務所の公式サイト）・更新のしかた・自動で作成の注記・広告・お気に入りの保存先・検索エンジンに出す・sitemap にある・AboutPage",
      '<h1 class="hero-title">このサイトについて</h1>' in _about_html and "FANZA Webサービス" in _about_html and "所属事務所の公式サイト" in _about_html
      and "自動で作成しており、内容の正確さは保証できません" in _about_html.split("<footer", 1)[0] and "アフィリエイト広告" in _about_html.split("<footer", 1)[0]
      and "端末のブラウザの中にだけ保存" in _about_html and 'name="robots" content="noindex' not in read_raw(_about) and "/about/" in sm_paths and '"AboutPage"' in read_raw(_about))
check(f"全ページの <head>: 画面幅・OGP・Twitterカード・アイコン（ico / svg / apple-touch）", not bad_head, bad_head[:3])
# 書体（Google Fonts）: 表示を止めないよう preload して、読み込み終わったら stylesheet に切り替える。JavaScript が無いときのための <noscript> の読み込みもある
bad_fonts = []
for p in pages:
    html_ = read(p)
    head_ = html_[: html_.find("</head>")]
    pre = [t for t in tags(head_, "link") if t.get("rel") == "preload" and t.get("as") == "style" and str(t.get("href", "")).startswith("https://fonts.googleapis.com/css2?")]
    ns = re.search(r'<noscript><link rel="stylesheet" href="https://fonts\.googleapis\.com/css2\?[^"]*"\s*/?></noscript>', head_)
    if len(pre) != 1 or "this.rel='stylesheet'" not in pre[0].get("onload", "") or not ns or "family=Dela+Gothic+One" not in pre[0].get("href", "") or "Zen+Kaku" in pre[0].get("href", ""):
        bad_fonts.append(os.path.relpath(p, DIST))
check("全ページの書体の読み込み: 表示を止めない形（preload → onload で stylesheet）＋ <noscript> の読み込み・見出しの書体だけ（本文は端末の書体。軽くするため）", not bad_fonts, bad_fonts[:3])
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
corner_frames = [body for sels, body in css_rules if (".corner" in sels or ".gacha-solo" in sels) and re.search(r"border(?:-[a-z]+)?\s*:[^;]*dashed", body)]
check("CSS: おすすめのコーナー・運命の作品に、点線の囲みが無い（運営者の希望「囲む必要はない」。2026-10-05 夜）", not corner_frames, corner_frames[:1])
chip_rules = [body for sels, body in css_rules if ".pr-chip" in sels]
chip_hidden = [b for b in chip_rules if re.search(r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?![.\d])|clip\s*:|height\s*:\s*0", b)]
chip_small = [b for b in chip_rules for m in [re.search(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", b)] if m and float(m.group(1)) < 11]
check("CSS: 広告ラベル（.pr-chip）が、隠されていない・小さすぎない（11px以上）", bool(chip_rules) and not chip_hidden and not chip_small, (len(chip_rules), chip_hidden[:1], chip_small[:1]))
check("CSS: 動画の枠（.movie-box）に contain: paint と isolation: isolate がある（枠の外に出ない）", movie_clip)
# 余白（運営者の指摘「ボタン同士・ボタンと作品がくっついている」。2026-10-05）と、メーカー・ジャンル・月の一覧のタイル（「文字数の差でボコボコ」）
def css_has(selector, pattern):
    return any(selector in sels and re.search(pattern, body) for sels, body in css_rules)
check("CSS: 一覧のタイル（.name-link）は、どれも同じ高さで、名前は2行まで（文字数でタイルの高さが変わらない）",
      css_has(".name-link", r"(?<![-\w])height\s*:\s*\d+px") and css_has(".name-link-name", r"line-clamp\s*:\s*2") and css_has(".name-grid>li", r"display\s*:\s*grid") or (css_has(".name-link", r"(?<![-\w])height\s*:\s*\d+px") and css_has(".name-link-name", r"line-clamp\s*:\s*2") and css_has(".name-grid > li", r"display\s*:\s*grid")))
check("CSS: すき間 — ジャンルなどの札（.chips）は8px以上・スイッチのすぐ下の作品（.list-tools + .shelf）・作品ページのボタンの並び（.detail-actions）にすき間がある",
      css_has(".chips", r"gap\s*:\s*(8|9|1\d)px") and (css_has(".list-tools+.shelf", r"margin-top\s*:\s*\d{2}px") or css_has(".list-tools + .shelf", r"margin-top\s*:\s*\d{2}px")) and css_has(".detail-actions", r"gap\s*:\s*1\dpx"))
# どんな画面の大きさにも（運営者の希望。2026-10-05）: 3つ並びは列の幅に合わせて大きさが変わる・棚などは置かれた場所の幅で列の数を決める
trio_ok = all(css_has(sel, r"gap\s*:\s*var\(--trio-gap\)") and css_has(sel, r"max-width\s*:\s*var\(--trio-max\)") for sel in (".medals", ".hot", ".hot-genres", ".slot-reels", ".debut-list"))
check("CSS: 3つ並び（TOP3・いま人気の女優・人気のジャンル・運命の作品・今週のデビュー作）は、同じすき間・同じ最大の幅の3等分の列で、丸は列の幅に合わせる（.hot-face は%）",
      trio_ok and css_has(".hot-face", r"width\s*:\s*\d+%") and css_has(".genre-thumb", r"width\s*:\s*100%") and not css_has(".genre-thumb", r"max-width\s*:\s*\d+px"))
# 人気のジャンルの表紙: 見開きでない形（VRなどの横長・表紙だけの縦長）は、読み込んだあとに印 is-flat を付けて、画像の全体から切り出す（運営者の指摘「右上しか写ってない」。2026-10-07）
_gimgs = re.findall(r'<img class="genre-img[^"]*"[^>]*>', genre_m.group(1)) if genre_m else []
check("人気のジャンル: 表紙は、見開きでない形（横長・縦長）なら印 is-flat を付ける（onload で縦横の比を見る）・CSS は、その印のとき画像の全体から切り出す（横長は右・縦長は上から少し下）",
      (not _gimgs or all("naturalWidth" in g_ and "is-flat" in g_ and "onload=" in g_ for g_ in _gimgs))
      and css_has(".genre-img.is-flat", r"object-fit\s*:\s*cover") and css_has(".genre-img.is-flat", r"object-position\s*:\s*100%\s+\d{1,2}%") and css_has(".genre-img.is-flat", r"(?<![-\w])height\s*:\s*100%"),
      _gimgs[:1])
all_css = "".join(read(p_) for p_ in glob.glob(os.path.join(DIST, "**", "*.css"), recursive=True))
check("CSS: 棚・作品検索の結果・注目の作品は、置かれた場所の幅で列の数を決める（コンテナクエリ）。使えない古いブラウザには、画面の幅で決める予備がある",
      re.search(r"container-type\s*:\s*inline-size", all_css) is not None
      # ビルドの道具が「(min-width: 600px)」を範囲の書き方「(width>=600px)」に縮めることがある（どちらも同じ意味）
      and len(re.findall(r"@container\s*\(\s*(?:min-width\s*:|width\s*>=?)", all_css)) >= 6 and "@supports not" in all_css)
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
check("応答ヘッダー: 名前にハッシュが付くファイル（/_astro/*）と、中身の印つきで読むスクリプト（/*.js）は、長くキャッシュ（immutable）",
      re.search(r"^/_astro/\*\s*\n\s+Cache-Control: public, max-age=31536000, immutable", htext, re.M) is not None and re.search(r"^/\*\.js\s*\n\s+Cache-Control: public, max-age=31536000, immutable", htext, re.M) is not None)
# スクリプトを長く置くので、ページからは必ず中身の印つき（?v=8けた）で読む（印が無いと、新しくしても古いものが使われ続ける）。印は今のファイルの中身と同じ
_js_hash = {f: _hl.sha1(open(os.path.join(DIST, f), "rb").read()).hexdigest()[:8] for f in os.listdir(DIST) if f.endswith(".js")}
bad_js_ref = []
for p_ in pages:
    for t_ in tags(read(p_), "script"):
        src_ = t_.get("src", "")
        if src_.startswith("/") and not src_.startswith("/_astro/"):
            m_ = re.fullmatch(r"/([\w.-]+\.js)\?v=([0-9a-f]{8})", src_)
            if not m_ or _js_hash.get(m_.group(1)) != m_.group(2):
                bad_js_ref.append((rel(p_), src_))
check("ページから読むスクリプト（/*.js）は、すべて今の中身の印つき（?v=…）", not bad_js_ref, bad_js_ref[:3])


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
check("CSS: お気に入りのサムネが表紙だけの軽い画像（印 is-small）のときは、まん中で切る", css_has(".fav-thumb.is-small", r"object-position\s*:\s*(50%\s+50%|50%|center)\s*[;}]?"))

# スマホのサムネ（運営者の希望「スマホの低速な回線だと画像が重い。サムネだけ画素数を落として最高速化。開いたときは元のまま」。2026-10-07）:
# スマホ（THUMB_MEDIA）のときだけ <picture> の <source> で小さい版を読む（components/Thumb.astro）。パソコン・タブレットは今までどおり
THUMB_MEDIA = re.search(r"export const THUMB_MEDIA = '([^']+)';", read(os.path.join(ROOT, "site", "src", "lib", "items.js"))).group(1)
_media_px = re.fullmatch(r"\(max-width: (\d+)px\)", THUMB_MEDIA).group(1)
_media_css = {f"(max-width:{_media_px}px)", f"(width<={_media_px}px)"}  # ビルド後のCSSは空白が縮む（範囲の書き方に変わることもある）


def _media_rule(sel, pattern):
    """@media THUMB_MEDIA の中に、sel の規則があり、pattern を満たす（空白の有無は問わない）"""
    for m in re.finditer(r"@media([^{]*)\{((?:[^{}]*\{[^{}]*\})*)[^{}]*\}", all_css):
        if re.sub(r"\s+", "", m.group(1)) not in _media_css:
            continue
        for r_ in re.finditer(r"([^{}]+)\{([^{}]*)\}", m.group(2)):
            if sel in [x.strip() for x in r_.group(1).split(",")] and re.search(pattern, r_.group(2)):
                return True
    return False


check(f"CSS: スマホ（{THUMB_MEDIA}）のときだけ、作品カード・TOP3の表紙だけの画像（印 has-small）はまん中で切る・人気のジャンルは画像の全体から切り出す・<picture> は箱を作らない",
      _media_rule(".item-img.has-small", r"object-position\s*:\s*(50%\s+50%|50%|center)")
      and _media_rule(".genre-img.has-small", r"object-fit\s*:\s*cover") and _media_rule(".genre-img.has-small", r"(?<![-\w])height\s*:\s*100%")
      and css_has(".pic", r"display\s*:\s*contents"))
_PIC = re.compile(r'<picture class="pic"><source media="([^"]*)" srcset="([^"]*)"><img ([^>]*)></picture>')
# スマホの版（2026-10-09 から。運営者の「少し粗すぎた。もう少しだけきれいに。同じしくみを同人とゲームにも」）:
# FANZA の「縮めて返す版」（awsimgsrc.dmm.co.jp/pics_dig/＋pics.dmm.co.jp と同じ道すじ＋?w=幅&q=75。lib/items.js の resizedImage）
_PICS_HOST, _AWS_HOST = "https://pics.dmm.co.jp/", "https://awsimgsrc.dmm.co.jp/pics_dig/"
def _resized(u, w):
    return _AWS_HOST + u[len(_PICS_HOST):] + f"?w={w}&q=75" if u.startswith(_PICS_HOST) else u
def _is_video_img(u):
    return re.match(r"^https://pics\.dmm\.co\.jp/digital/video/[^?#]+p[ls]\.jpg$", u) is not None
def _is_game_img(u):
    return re.match(r"^https://pics\.dmm\.co\.jp/digital/pcgame/[^?#]+pl\.jpg$", u) is not None
def _as_ps(u):
    return re.sub(r"p[ls]\.jpg$", "ps.jpg", u)
bad_pic, bad_bare, n_pic, pic_kinds = [], [], 0, Counter()
for pth in all_html:
    h_ = read_raw(pth)
    if "<picture" not in h_ and "pl.jpg" not in h_:
        continue
    rel_ = os.path.relpath(pth, DIST)
    if h_.count("<picture") != len(_PIC.findall(h_)):
        bad_pic.append((rel_, "形が違う <picture>"))
    for media_, small_, img_ in _PIC.findall(h_):
        n_pic += 1
        a_ = dict((k, htmllib.unescape(v)) for k, v in re.findall(r'([\w-]+)="([^"]*)"', img_))
        cls_ = a_.get("class", "").split()
        src_ = a_.get("src", "")
        small_ = htmllib.unescape(small_)
        if "floor-img" in cls_:
            kind_, want_ = "doujin", (src_.startswith(_PICS_HOST) and src_.endswith("pl.jpg") and small_ in (_resized(src_, 300), _resized(src_, 240))
                                      and a_.get("referrerpolicy") == "no-referrer")
        elif "is-small" in cls_:
            kind_, want_ = "tiny", (src_.endswith("ps.jpg") and _is_video_img(src_) and small_ == _resized(src_, 200))
        elif "genre-img" in cls_:
            kind_, want_ = "genre", (src_.endswith("pl.jpg") and _is_video_img(src_) and small_ == _resized(_as_ps(src_), 200) and "has-small" in cls_)
        elif "item-img" in cls_ and _is_game_img(src_):
            kind_, want_ = "game-card", (small_ == _resized(src_, 300) and "has-small" not in cls_)
        elif "item-img" in cls_:
            kind_, want_ = "card", (src_.endswith("pl.jpg") and _is_video_img(src_) and small_ == _resized(_as_ps(src_), 300) and "has-small" in cls_)
        else:
            kind_, want_ = "?", False
        pic_kinds[kind_] += 1
        onerr_ = a_.get("onerror", "")
        # alt="" は、Astro が値の無い「alt」だけで書く（どちらも空の代替テキスト）
        has_alt_ = a_.get("alt") is not None or re.search(r'(?:^|\s)alt(?=\s|/?$)', re.sub(r'"[^"]*"', '""', img_)) is not None
        back_ = "doujin-assets.dmm.co.jp" in onerr_ if kind_ == "doujin" else "pl.jpg" in onerr_  # 元の画像も読めなければ、の戻し先
        if media_ != THUMB_MEDIA or not want_ or not fanza_https(src_, DMM) or not fanza_https(small_, DMM) or "previousElementSibling" not in onerr_ or "matchMedia(s.media)" not in onerr_ or not back_ or not has_alt_:
            bad_pic.append((rel_, kind_, src_[-20:], small_[-20:]))
    # 一覧のサムネ（item-img・genre-img）で、パッケージ画像（pl.jpg）を <picture> の外で読んでいるもの（スマホで重いまま）
    for t in tags(re.sub(r"<picture class=\"pic\">.*?</picture>", "", h_), "img"):
        if (has_class(t, "item-img") or has_class(t, "genre-img") or has_class(t, "floor-img")) and str(t.get("src", "")).endswith("pl.jpg"):
            bad_bare.append((rel_, t.get("src", "")[-24:]))
    # 作品ページの大きな表紙・パッケージ写真・サンプル画像は、元の画像のまま（<picture> に入れない）
    for cls_name in ("detail-cover", "package-img", "sample-img"):
        if re.search(r'<picture class="pic"><source [^>]*><img class="%s' % cls_name, h_):
            bad_pic.append((rel_, cls_name + " が小さい版になっている"))
_has_doujin = os.path.isdir(os.path.join(DIST, "doujin"))
check(f"スマホのサムネ（{n_pic}枚 {dict(pic_kinds)}）: 縮めて返す版で、動画のカード・TOP3は表紙の幅300・小さな表紙と人気のジャンルは表紙の幅200・"
      f"ゲームのカードはパッケージの幅300・同人は幅300/240（どのページから読んだかを送らない）。幅は {THUMB_MEDIA}・読めなければ元の画像に戻す",
      n_pic > 0 and pic_kinds["card"] > 0 and (pic_kinds["doujin"] > 0 or not _has_doujin) and not bad_pic, bad_pic[:4])
check("スマホのサムネ: 一覧のパッケージ画像（pl.jpg。同人の表紙も）は、すべて <picture> の中（スマホは小さい版を読む）・作品ページの表紙・パッケージ写真・サンプル画像は元のまま", not bad_bare, bad_bare[:4])
_home_raw = read_raw(os.path.join(DIST, "index.html"))
_top3 = re.search(r'<ol class="medals rank-podium".*?</ol>', _home_raw, re.S)
_top3_imgs = re.findall(r'<img ([^>]*)>', _top3.group(0)) if _top3 else []
check("トップのTOP3: スマホは表紙（幅300に縮めた版）を <picture> で読み、1本目はすぐに・優先して読む（fetchpriority=high）",
      bool(_top3_imgs) and _top3.group(0).count('<picture class="pic">') == len(_top3_imgs) and 'fetchpriority="high"' in _top3_imgs[0] and 'loading="eager"' in _top3_imgs[0], _top3_imgs[:1])

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
as_rules = [b for sels, b in css_rules if any(re.sub(r"\s+", " ", s_) in ("html:not(.js) .actress-search", ".js .actress-static:not(.is-fallback)") for s_ in sels)]
check("CSS: 女優検索の部品は JavaScript が使えるとき（html.js）だけ出し、使えないとき用の一覧は、使えるときは、はじめから隠す（索引を読めなかったら is-fallback で出す）",
      len(as_rules) >= 1 and all(re.search(r"display\s*:\s*none", b) for b in as_rules) and sum(1 for sels, b in css_rules for s_ in sels if re.sub(r"\s+", " ", s_) in ("html:not(.js) .actress-search", ".js .actress-static:not(.is-fallback)")) == 2, as_rules[:1])
fold_rule = [b for sels, b in css_rules if any(re.sub(r"\s+", " ", s_) == ".js [data-fold]:not(.is-open) .fold-off" for s_ in sels)]
check("CSS: 「もっと見る」でたたんだ作品は、JavaScript が使えるとき（html.js）だけ、開くまで隠す（使えないときは全部見える）",
      bool(fold_rule) and all(re.search(r"display\s*:\s*none", b) for b in fold_rule) and not any(".fold-off" in s_ and ".js" not in s_ for sels, b in css_rules for s_ in sels), fold_rule[:1])
js_only = {re.sub(r"\s+", " ", s_) for sels, b in css_rules for s_ in sels if re.search(r"display\s*:\s*none", b)}
check("CSS: JavaScript が使えるときだけ使える部品（VR・単体のスイッチ・お気に入りのボタン・運命の作品・「もっと見る」・作品検索）は、使えないときだけ隠す（はじめから出しておき、あとから出てきて下がずれないように。2026-10-07）",
      {"html:not(.js) .vr-toggle", "html:not(.js) .fav-btn", "html:not(.js) #gacha", "html:not(.js) [data-fold-more]", "html:not(.js) .work-search", ".js .ws-fallback:not(.is-fallback)"} <= js_only,
      sorted({"html:not(.js) .vr-toggle", "html:not(.js) .fav-btn", "html:not(.js) #gacha", "html:not(.js) [data-fold-more]", "html:not(.js) .work-search", ".js .ws-fallback:not(.is-fallback)"} - js_only))
check("CSS: お気に入りの出演者・メーカーがある人（html.has-favs）には、トップのお知らせの場所を、はじめから出す（あとから上に出てきて、ページ全体がずれないように）",
      any(".has-favs .fav-banner[hidden]" in [re.sub(r"\s+", " ", x) for x in sels] and re.search(r"display\s*:\s*block", b) for sels, b in css_rules))
_press = [sels for sels, b in css_rules if any(re.sub(r"\s+", " ", s_) == ".hide-vr .vr-toggle[data-vr-toggle]" for s_ in sels) and re.search(r"border-color", b)]
check("CSS: VR・単体のスイッチの押した見た目は、html の印（hide-vr・only-solo）でもすぐに出る（スクリプトを待たない）", bool(_press) and any(".only-solo .vr-toggle[data-solo-toggle]" in [re.sub(r"\s+", " ", x) for x in sels] for sels in _press), _press[:1])
hidden_ok = [sels for sels, b in css_rules if ".vr-toggle[hidden]" in sels and re.search(r"display\s*:\s*none", b)]
check("CSS: 隠れているスイッチ・検索（hidden）が、display の指定に負けずに隠れる", bool(hidden_ok) and any(".work-search[hidden]" in sels for sels in hidden_ok), hidden_ok[:1])

# 全ページ: 先に印を付ける小さなスクリプト・スイッチのスクリプト・検索へのリンク
no_head_vr, no_vr_js, no_nav_search, no_foot_search = [], [], [], []
for p in pages:
    html_ = read(p)
    head_ = html_[: html_.find("</head>")] if "</head>" in html_ else ""
    if not re.search(r"localStorage\.getItem\('hide-vr'\)\s*===\s*'1'", head_) or "classList.add('hide-vr')" not in head_ or "classList.add('only-solo')" not in head_ or "classList.add('js')" not in head_ or "classList.add('has-favs')" not in head_:
        no_head_vr.append(os.path.relpath(p, DIST))
    if 'src="/vr-filter.js?v=' not in html_:
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
    if len(btns) != 1 or "hidden" in btns[0] or btns[0].get("aria-pressed") != "false" or not btns[0].get("data-on") or not btns[0].get("data-off") or btns[0].get("type") != "button":
        bad_toggle.append((os.path.relpath(tp, DIST), btns[:1]))
check("「VR作品を隠す」スイッチが、トップ・検索・過去の作品・出演者・メーカーのページに1つずつある（はじめから出ている＝JavaScript が使えないときだけ CSS で隠す・押された状態ではない・文言つき）", not bad_toggle, bad_toggle[:3])
bad_solo_toggle = []
for tp in toggle_pages:
    if os.path.isfile(tp):
        btns = [t for t in tags(read(tp), "button") if "data-solo-toggle" in t]
        if len(btns) != 1 or "hidden" in btns[0] or btns[0].get("aria-pressed") != "false" or btns[0].get("data-off") != "単体作品のみ" or not btns[0].get("data-on"):
            bad_solo_toggle.append((os.path.relpath(tp, DIST), btns[:1]))
check("「単体作品のみ表示」スイッチが、「VR作品を隠す」の隣に1つずつある（はじめから出ている＝JavaScript が使えないときだけ CSS で隠す・押された状態ではない）", not bad_solo_toggle, bad_solo_toggle[:3])
check("CSS: html.only-solo のとき、単体作品の印（data-solo）の無いマスを隠す", any(".only-solo .shelf-cell:not([data-solo])" in sels and re.search(r"display\s*:\s*none", b) for sels, b in css_rules))

# 作品ページ: ジャンルは、ジャンルのページ（/tag/…。ページがあるジャンル）か、そのジャンルで絞り込んだ検索へのリンク
import urllib.parse as _up


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
    want_day = "この1本だけ" if n_same == 1 else f"{n_same}本"  # 短い形（「6本（うちムーディーズ 6本）」。2026-10-06）
    got_day = htmllib.unescape(re.sub(r"<[^>]+>", "", rows_[0][1])).strip() if rows_ else ""
    if not rows_ or rows_[0][0] != "同じ発売日" or not (got_day == want_day or got_day.startswith(want_day + "（") or got_day.startswith(want_day + " ")):
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
    cards_ = len(re.findall(r'<article class="item">', html_[html_.find('id="works-title"'):]))  # 作品の一覧の中だけ（上の月のまとめ記事の行は数えない）
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

# 人気ランキング（/ranking/ 新着の人気順。「全体の人気ランキング」（/ranking/all/）は運営者の判断でやめた。2026-10-05）
print("\n■ 人気ランキング")
JST_DAY = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d")
_from = (datetime.date.fromisoformat(JST_DAY) - datetime.timedelta(days=7)).isoformat()  # 新着は1週間（lib/popularity.js の NEW_RANK_DAYS）
want_new = sorted((c for c in everything if c in pop_new and _from <= str(everything[c]["date"])[:10] <= JST_DAY),
                  key=lambda c: (pop_new[c], -int(str(everything[c]["date"])[:10].replace("-", "")), c))[:100]
want_all = sorted((c for c in everything if all_rank_of(c) and str(everything[c]["date"])[:10] <= JST_DAY),
                  key=lambda c: (all_rank_of(c), -int(str(everything[c]["date"])[:10].replace("-", "")), c))[:100]
for path_, want, label in (("ranking/index.html", want_new, "新着の人気順"),):
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
redirects_ = read(os.path.join(DIST, "_redirects")) if os.path.isfile(os.path.join(DIST, "_redirects")) else ""
check("全体の人気ランキングのページは無く、sitemap にも無く、古いURLは新着の人気ランキングへ移す（_redirects）",
      not os.path.exists(os.path.join(DIST, "ranking", "all")) and "/ranking/all/" not in sm_paths and re.search(r"^/ranking/all/\s+/ranking/\s+301\s*$", redirects_, re.M) is not None)
links_all = [rel(p) for p in glob.glob(os.path.join(DIST, "**", "*.html"), recursive=True) if 'href="/ranking/all/"' in read_raw(p)]
check("どのページからも、全体の人気ランキングへリンクしない", not links_all, links_all[:3])
find_nav = re.search(r'<nav class="hero-jump"[\s\S]*?</nav>', home_html)
check("作品を探すの1つ目は「新着の人気ランキング」（横いっぱい）。「予約○本」のボタンは置かない（運営者の希望。2026-10-05）",
      bool(find_nav) and re.search(r'<a class="chip-link chip-link-wide" href="/ranking/">新着の人気ランキング</a>', find_nav.group(0)) is not None
      and find_nav.group(0).find('chip-link-wide') < find_nav.group(0).find('href="/', find_nav.group(0).find('chip-link-wide') + 60) and 'href="#upcoming"' not in find_nav.group(0))
if find_nav:
    labels_ = [strip_tags(x) for x in re.findall(r'<a class="chip-link[^"]*" href="[^"]*">(.*?)</a>', find_nav.group(0))]
    want_ = ["新着の人気ランキング"] + (["ジャンル検索"] if 'href="/tag/"' in find_nav.group(0) else []) + ["女優検索", "メーカー検索"] + (["週のまとめ"] if rounds else []) + (["月のまとめ"] if 'href="/month/"' in find_nav.group(0) else [])
    check("作品を探すのボタンの並びと名前: 新着の人気ランキング → ジャンル検索・女優検索・メーカー検索 → 週のまとめ（左）・月のまとめ（右）（運営者の希望。2026-10-05）", labels_ == want_, labels_)

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


def camp_slug(title):
    """特集ごとのページの印（site/src/lib/sale.js の campaignSlug と同じ: NFKC・空白を除く → NFC → sha1 の先頭10文字）"""
    t = re.sub(r"\s+", "", _ud.normalize("NFKC", str(title)))
    return _hl.sha1(_ud.normalize("NFC", t).encode("utf-8")).hexdigest()[:10]


def camp_max_off(k):
    """特集のいちばん大きい割引（このサイトの作品で、値引きの分かるもの。site/src/lib/sale.js の maxOff と同じ）"""
    offs = [int((1 - r["p"] / r["l"]) * 100 + 0.5) for r in _sale_rows if r["k"] == k and r.get("c") in everything
            and isinstance(r.get("p"), int) and isinstance(r.get("l"), int) and 0 < r["p"] < r["l"]]
    return max(offs) if offs else None


camp_minor = lambda title: _cc.title_block_reason({"title": str(title)}) == "minor"  # noqa: E731
sale_page = os.path.join(DIST, "sale", "index.html")
check("セール・キャンペーンのページ（/sale/）と、終わったものを隠すスクリプト（sale.js）がある", os.path.isfile(sale_page) and os.path.isfile(os.path.join(DIST, "sale.js")))
if os.path.isfile(sale_page):
    sh = read(sale_page)
    head_ids = re.findall(r'<h2 id="sale-(\d+)" class="section-title">(.*?)</h2>', sh)
    heads = [t for _, t in head_ids]
    check(f"キャンペーンのまとまりの数（{len(heads)}）が、データ（今日より前に終わったものを除く・このサイトの作品があるもの）と同じ", len(heads) == len(want_camps), (len(heads), len(want_camps)))
    if heads:
        check("セールのページに「○日の時点」「くわしくはFANZAで確かめて」の注意書き・終わりの時刻の印（data-sale-end）・sale.js がある", "時点" in sh and "FANZAの作品ページで確かめてください" in sh and "data-sale-end=" in sh and sale_js_ok(read_raw(sale_page)))
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
            mo_ = camp_max_off(k)
            if not note or (tag_ and f'<span class="camp-soon">{tag_}</span>' not in note.group(1)) or (not tag_ and "camp-soon" in note.group(1)) \
                    or f"{end_label(str(_camps[k]['end']))}まで{f'・最大{mo_}%OFF' if mo_ else ''}・{len(_camp_works[k])}本" not in strip_tags(note.group(1)):
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
          bool(home_sale) and "セール中の特集" in home_sale.group(1) and "shelf-cell" not in home_sale.group(1) and home_html.find('id="sale"') < home_html.find('id="released"') and sale_js_ok(read_raw(os.path.join(DIST, 'index.html'))))
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
        covers_ = re.findall(r'<span class="camp-cover"( data-vr="true")?>\s*(?:<picture class="pic"><source [^>]*>)?<img ([^>]*)>', inner)
        off_ = re.search(r"(\d{1,2})\s*[％%]\s*OFF", str(camp["title"]), re.I)
        sticker = re.search(r'<span class="camp-off">([^<]*)</span>', inner)
        want_maker = "・".join(n_ for n_, _ in makers_) + (" など" if sum(c_ for _, c_ in makers_) < len(works_) else "")
        tag_ = soon_tag(str(camp["end"]))
        vr_flags = [bool(v) for v, _ in covers_]
        card_problems = []  # （前は problems という名前で、全体の失敗の一覧を上書きして消していた。2026-10-07 に直した）
        if bool(more) != (i >= show_n): card_problems.append("見せる数")
        if a_.get("href") != (f"/sale/{camp_slug(camp['title'])}/" if not camp_minor(camp["title"]) else f"/sale/#sale-{k}"): card_problems.append(a_.get("href"))
        if end_ != end_iso(str(camp["end"])): card_problems.append("終わりの印")
        if not title_ or strip_tags(title_.group(1)) != str(camp["title"]).strip(): card_problems.append("名前")
        if f"{end_label(str(camp['end']))}まで・{len(works_):,}本" not in strip_tags(inner): card_problems.append("いつまで・本数")
        if (f'<span class="camp-soon">{tag_}</span>' in inner) != bool(tag_) or (not tag_ and "camp-soon" in inner): card_problems.append("きょう・あすの札")
        if (strip_tags(maker_line.group(1)) if maker_line else "") != (f"メーカー：{want_maker}" if makers_ else ""): card_problems.append(("メーカー", strip_tags(maker_line.group(1)) if maker_line else ""))
        if not 1 <= len(covers_) <= 3 or vr_flags != sorted(vr_flags) or any(not fanza_https(dict(re.findall(r'(\w+)="([^"]*)"', img)).get("src", ""), ["dmm.co.jp", "fanza.co.jp"]) for _, img in covers_): card_problems.append("表紙")
        if (sticker.group(1) if sticker else "") != (f"{off_.group(1)}%OFF" if off_ else ""): card_problems.append("値引きの札")
        if card_problems:
            bad_card.append((camp["title"], card_problems))
    check(f"セール中の特集のカード（{len(cards)}枚。先頭{show_n}枚を見せる）: 終わりが近い順・その特集のページへのリンク・名前・いつまで・本数・おもなメーカー・表紙（VRでない作品が先）・値引きの札",
          len(cards) == len(want_camps) and show_n >= 1 and not bad_card, bad_card[:2])
else:
    check("セール中の特集が無いときは、トップに欄を出さない", not home_sale and not camp_ul)
check("フッターにセール・キャンペーンへのリンクがある", 'href="/sale/"' in home_html)

# 特集ごとのページ（/sale/<印>/）と「FANZAのセールはいつ？」（/sale/history/）（運営者の希望「SEOを上位に」→ ①セールを検索の入り口に。2026-10-06）
print("\n■ 特集ごとのページ・セールの履歴")
try:
    _sh = json.load(open(os.path.join(ROOT, "site", "src", "data", "sale_history.json"), encoding="utf-8"))
except (OSError, ValueError):
    _sh = {}
_hist_rows = [r for r in (_sh.get("campaigns") if isinstance(_sh, dict) and isinstance(_sh.get("campaigns"), list) else []) if isinstance(r, dict) and str(r.get("title", "")).strip()]
_hist_ok = [r for r in _hist_rows if not camp_minor(r["title"])]
_since90 = (datetime.date.fromisoformat(JST_DAY) - datetime.timedelta(days=90)).isoformat()
_active_titles = {str(_camps[k]["title"]).strip() for k in want_camps if not camp_minor(_camps[k]["title"])}
_recent_titles = {str(r["title"]).strip() for r in _hist_ok if str(r.get("last", "")) >= _since90}
want_camp_slugs = {camp_slug(t): t for t in _active_titles | _recent_titles}
got_camp_slugs = {os.path.basename(os.path.dirname(f)) for f in glob.glob(os.path.join(DIST, "sale", "*", "index.html")) if re.fullmatch(r"[0-9a-f]{10}", os.path.basename(os.path.dirname(f)))}
check(f"特集ごとのページ（{len(got_camp_slugs)}ページ）: 開催中の特集と、最後に見かけてから90日のあいだの特集だけ（未成年を連想させる名前の特集には作らない）",
      got_camp_slugs == set(want_camp_slugs), (sorted(set(want_camp_slugs) - got_camp_slugs)[:3], sorted(got_camp_slugs - set(want_camp_slugs))[:3]))
bad_camp_pages = []
for slug_, title_ in want_camp_slugs.items():
    f_ = os.path.join(DIST, "sale", slug_, "index.html")
    if not os.path.isfile(f_):
        continue
    html_ = read(f_)
    raw_ = read_raw(f_)
    t_ = re.search(r"<title>(.*?)</title>", raw_, re.S)
    t_ = htmllib.unescape(t_.group(1)) if t_ else ""
    h1_ = re.search(r'<h1 class="hero-title">(.*?)</h1>', html_, re.S)
    noidx = 'name="robots" content="noindex' in raw_
    in_sm = f"/sale/{slug_}/" in sm_paths
    here = []
    if not h1_ or strip_tags(h1_.group(1)) != title_:
        here.append("見出し")
    if title_ in _active_titles:
        ks_ = [k for k in want_camps if str(_camps[k]["title"]).strip() == title_]
        mo_ = max([camp_max_off(k) or 0 for k in ks_]) or None
        in_name_ = bool(mo_) and f"{mo_}%OFF" in _ud.normalize("NFKC", title_).upper()
        if not t_.startswith(f"{title_}の対象作品【") or "まで】" not in t_ or (mo_ and ((f"最大{mo_}%OFF" in t_) == in_name_)):
            here.append(("タイトル", t_))
        if "shelf-cell" not in html_ or 'data-sale-over="' not in raw_ or not sale_js_ok(raw_):
            here.append("作品・終わったときの印")
    else:
        if "いまは開催していません" not in html_ or not noidx or "shelf-cell" in html_:
            here.append("開催していないとき")
    if noidx == in_sm:
        here.append(("noindexとsitemap", noidx, in_sm))
    if 'href="/sale/history/"' not in raw_ or 'href="/sale/"' not in raw_:
        here.append("セールのページ・履歴へのリンク")
    if here:
        bad_camp_pages.append((title_, here))
check("特集ごとのページ: 見出しは特集の名前・開催中はタイトルに「○○の対象作品【○月○日まで】最大○%OFF」と作品・終わったら出す注意・sale.js、開催していないあいだは「いまは開催していません」で noindex・sitemap は検索エンジンに出すページだけ",
      not bad_camp_pages, bad_camp_pages[:2])
hist_page = os.path.join(DIST, "sale", "history", "index.html")
if _hist_ok:
    hh = read(hist_page) if os.path.isfile(hist_page) else ""
    # 帯のグラフ（運営者の希望「文字が多くて見づらい」。2026-10-06）: 月ごとの帯の、読み上げの文（aria-label）に、記録したすべての回の期間が入っている
    def _run_range(r):
        b_ = str(r.get("begin") or "")
        return (f"{int(b_[5:7])}月{int(b_[8:10])}日" if len(b_) >= 10 else "") + "〜" + end_label(str(r["end"]))
    _month_blocks = re.findall(r'<details class="month-fold"[^>]*>(.*?)</details>', hh, re.S)
    _month_aria = " / ".join(htmllib.unescape(x) for blk in _month_blocks for x in re.findall(r'class="bars-track" role="img" aria-label="([^"]*)"', blk))
    _missing_runs = [r["title"] for r in _hist_ok if _run_range(r) not in _month_aria]
    _now_rows = re.findall(r'<li class="bars-row" data-sale-end="[^"]+">', hh)
    check(f"「FANZAのセールはいつ？」（/sale/history/）: 見出し・よくある質問（答えの数字を先に）・月ごとの帯のグラフ（{len(_month_blocks)}か月・{len(_hist_ok)}回すべて）・いまの月だけ開く・記録の始まりの注記・検索エンジンに出す・sitemap にある",
          '<h1 class="hero-title">FANZAのセールはいつ？</h1>' in hh and "よくある質問" in hh and "次のセールはいつ？" in hh and 'class="faq-key"' in hh and _month_blocks and not _missing_runs
          and len(re.findall(r'<details class="month-fold" open', hh)) == 1 and hh.find('<details class="month-fold" open') == hh.find('<details class="month-fold"')
          and "記録は2026年10月5日から" in hh and 'name="robots" content="noindex' not in read_raw(hist_page) and "/sale/history/" in sm_paths, (len(_month_blocks), _missing_runs[:3]))
    check(f"「FANZAのセールはいつ？」のいま開催中の帯（{len(_now_rows)}件）: 開催中の特集の数と同じ・終わったら隠す印・帯の見かた・きょうの印・sale.js",
          len(_now_rows) == len(_active_titles) and (not _active_titles or ('class="bars-legend"' in hh and "is-today" in hh and sale_js_ok(read_raw(hist_page)))), (len(_now_rows), len(_active_titles)))
    check("「FANZAのセールはいつ？」に、予想の言葉を書かない（データから数えた事実だけ）", not re.search(r"予想|予測|はずです|でしょう|見込み", strip_tags(hh)))
else:
    check("セールの履歴が無いあいだは、「FANZAのセールはいつ？」を検索エンジンに出さない", not os.path.isfile(hist_page) or 'name="robots" content="noindex' in read_raw(hist_page))
if want_camps and os.path.isfile(sale_page):
    st_ = re.search(r"<title>(.*?)</title>", read_raw(sale_page), re.S)
    st_ = htmllib.unescape(st_.group(1)) if st_ else ""
    check("セールのページのタイトルに「開催中」「○月○日更新」・特集の数、はじめに「セールはいつ？」へのリンク",
          st_.startswith("FANZAセール開催中の作品一覧【") and "更新】" in st_ and f"特集{len(want_camps)}件" in st_ and 'href="/sale/history/"' in read_raw(sale_page), st_)

# 出演者のページ（運営者の希望「SEOを上位に」→ ②女優のページを強く。2026-10-06）: タイトルに年月・次の新作・セール中の作品・更新日・ProfilePage
_ym = f"【{int(JST_TODAY[:4])}年{int(JST_TODAY[5:7])}月】"
_works_of = {}
for c_, x_ in everything.items():
    for a_ in set(x_.get("actress") or []):
        _works_of.setdefault(a_, []).append(c_)
_live_k = {k for k in range(len(_camps)) if str(_camps[k].get("end", ""))[:10] >= JST_DAY}
_on_sale = {r["c"] for r in _sale_rows if r["k"] in _live_k}
bad_act2 = []
for pth in actress_pages:
    html_ = read(pth)
    raw_ = read_raw(pth)
    m_ = re.search(r'<h1 class="hero-title">(.*?)</h1>', html_, re.S)
    h1_ = htmllib.unescape(re.sub(r"<[^>]+>", "", m_.group(1))).strip() if m_ else ""
    name_ = h1_[: -len("の新作・出演作品")] if h1_.endswith("の新作・出演作品") else ""
    cids_ = _works_of.get(name_, [])
    up_ = any(str(everything[c].get("date", ""))[:10] > JST_TODAY for c in cids_)
    # 次の新作・セール中の作品の欄は、未成年を連想させるタイトルの作品を入れない（タイトルの「予約」は、全部の作品で決める）
    up_next_ = any(str(everything[c].get("date", ""))[:10] > JST_TODAY and not is_minor_title(everything[c].get("title")) for c in cids_)
    sale_ = any(c in _on_sale and str(everything[c].get("date", ""))[:10] <= JST_TODAY and not is_minor_title(everything[c].get("title")) for c in cids_)
    t_ = re.search(r"<title>(.*?)</title>", raw_, re.S)
    t_ = htmllib.unescape(t_.group(1)) if t_ else ""
    here = []
    if _ym not in t_ or (("・予約・" in t_) != up_):
        here.append(("タイトル", t_))
    if ('id="next-title"' in raw_) != up_next_:
        here.append("次の新作")
    if ('id="onsale-title"' in raw_) != sale_:
        here.append("セール中の作品")
    if not re.search(r'"@type":\s*"ProfilePage"', raw_) or f'"name":"{name_}"'.replace(" ", "") not in raw_.replace(" ", ""):
        here.append("ProfilePage")
    if 'class="page-updated"' not in raw_:
        here.append("更新日")
    if here:
        bad_act2.append((name_, here))
check(f"出演者のページ（{len(actress_pages)}ページ）: タイトルに年月（予約があれば「予約」も）・次の新作・セール中の作品（あるときだけ）・更新日・ProfilePage の構造化データ",
      not bad_act2, bad_act2[:2])

# メーカーのページ（女優のページと同じように強くする。運営者の希望「素晴らしいサイトを目指して完璧に」。2026-10-06）:
# タイトルに年月・次の新作・セール中の作品と入っているセール・よく出ている女優（顔の丸）・多いジャンル・更新日・CollectionPage
_maker_works = {}
for c_, x_ in everything.items():
    m_ = str(x_.get("maker") or "")
    if m_ and m_ != "不明":
        _maker_works.setdefault(m_, []).append(c_)
maker_pages = glob.glob(os.path.join(DIST, "maker", "*", "index.html"))
bad_mk = []
for pth in maker_pages:
    html_ = read(pth)
    raw_ = read_raw(pth)
    m_ = re.search(r'<h1 class="hero-title">(.*?)</h1>', html_, re.S)
    h1_ = htmllib.unescape(re.sub(r"<[^>]+>", "", m_.group(1))).strip() if m_ else ""
    name_ = h1_[: -len("の新作・作品一覧")] if h1_.endswith("の新作・作品一覧") else ""
    cids_ = _maker_works.get(name_, [])
    works_ = [everything[c] for c in cids_]
    up_ = any(str(x.get("date", ""))[:10] > JST_TODAY for x in works_)
    up_next_ = any(str(x.get("date", ""))[:10] > JST_TODAY and not is_minor_title(x.get("title")) for x in works_)
    sale_ = any(c in _on_sale and str(everything[c].get("date", ""))[:10] <= JST_TODAY and not is_minor_title(everything[c].get("title")) for c in cids_)
    cast_ = _top_counts([a for x in works_ if len(_cast(x)) <= 4 for a in dict.fromkeys(_cast(x))], limit=6, minimum=2)
    genres_ = _top_counts([g for x in works_ for g in set(x.get("genres") or []) if g in _content_genres], limit=8)
    t_ = re.search(r"<title>(.*?)</title>", raw_, re.S)
    t_ = htmllib.unescape(t_.group(1)) if t_ else ""
    here = []
    if not name_ or not t_.startswith(f"{name_}の新作") or _ym not in t_ or (("・予約・" in t_) != up_) or f"（{len(works_)}本）" not in t_:
        here.append(("タイトル", t_))
    if ('id="next-title"' in raw_) != up_next_:
        here.append("次の新作")
    if ('id="onsale-title"' in raw_) != sale_:
        here.append("セール中の作品")
    if sale_ and ('class="in-sales"' not in raw_ or not sale_js_ok(raw_)):
        here.append("入っているセール")
    faces_ = re.findall(r'<li class="hot-cell">.*?<span class="hot-name">(?:<span class="visually-hidden">[^<]*</span>)?(.*?)</span>\s*<span class="cast-count">(\d+)本</span>', html_, re.S)
    got_cast = [(htmllib.unescape(strip_tags(n)).strip(), int(c)) for n, c in faces_]
    if got_cast != cast_:
        here.append(("よく出ている女優", got_cast[:3], cast_[:3]))
    chips_ = re.findall(r'class="chip-link[^"]*"[^>]*>([^<]*)<span class="chip-count">(\d+)本</span>', html_.split('id="genre-title"', 1)[1].split("</section>", 1)[0]) if 'id="genre-title"' in html_ else []
    if [(htmllib.unescape(n).strip(), int(c)) for n, c in chips_] != genres_:
        here.append(("多いジャンル", chips_[:3], genres_[:3]))
    if not re.search(r'"@type":\s*"CollectionPage"', raw_) or '"Organization"' not in raw_:
        here.append("CollectionPage")
    if 'class="page-updated"' not in raw_:
        here.append("更新日")
    if here:
        bad_mk.append((name_, here))
check(f"メーカーのページ（{len(maker_pages)}ページ）: タイトルに年月・予約・本数・次の新作・セール中の作品と入っているセール（あるときだけ）・よく出ている女優（出演者4人までの作品で2本以上・6人まで）・多いジャンル・更新日・CollectionPage",
      not bad_mk, bad_mk[:2])
# 作品ページの「次に見るもの」（運営者の希望「サイト滞在時間を伸ばしたい」。2026-10-06）: セール中の札・次の新作・小さな表紙の棚・運命の作品
_item_pages = sorted(glob.glob(os.path.join(DIST, "item", "*", "index.html")))
bad_stay = []
for pth in _item_pages:
    cid_ = os.path.basename(os.path.dirname(pth))
    raw_ = read_raw(pth)
    x_ = everything.get(cid_, {})
    on_ = cid_ in _on_sale and str(x_.get("date", ""))[:10] <= JST_TODAY
    here = []
    if ('class="sale-strip"' in raw_) != on_ or (on_ and not sale_js_ok(raw_)):
        here.append("セールの札")
    if not re.search(r'<section id="gacha"[^>]*data-src="/data/gacha.json"[^>]*data-exclude="' + re.escape(cid_) + '"', raw_) or 'src="/gacha.js?v=' not in raw_:
        here.append("運命の作品")
    shown_titles = [htmllib.unescape(strip_tags(t)) for t in re.findall(r'class="mini-title">(.*?)</h3>', raw_, re.S)]
    nx = re.search(r'<section class="subsection" aria-labelledby="next-title">(.*?)</section>', raw_, re.S)
    if nx:
        shown_titles += [htmllib.unescape(strip_tags(t)) for t in re.findall(r'class="item-title-link"[^>]*>(.*?)</a>', nx.group(1), re.S)]
    if any(is_minor_title(t) for t in shown_titles):
        here.append("未成年を連想させるタイトル")
    # 小さな表紙の棚（同じシリーズ・同じ出演者/メーカー・同じジャンルで人気。2026-10-07 から3つ）: どれも6本まで・同じ作品が2つの棚に出ない・その作品自身は出ない
    shelves_ = re.findall(r'<ul class="mini-shelf">(.*?)</ul>', raw_, re.S)
    shelf_links = [h_ for sh_ in shelves_ for h_ in re.findall(r'<a class="mini-card" href="([^"]+)"', sh_)]
    if any(len(re.findall(r'class="shelf-cell mini-cell"', sh_)) > 6 for sh_ in shelves_) or len(shelves_) > 3:
        here.append("小さな表紙の棚の本数")
    if len(set(shelf_links)) != len(shelf_links) or f"/item/{cid_}/" in shelf_links:
        here.append("棚の重なり・その作品自身")
    if here:
        bad_stay.append((cid_, here))
check(f"作品ページ（{len(_item_pages)}ページ）の次に見るもの: セール中の作品だけに札（と sale.js）・運命の作品（/data/gacha.json・その作品を除く）・小さな表紙の棚は3つまで・どれも6本まで・同じ作品が2つの棚に出ない・未成年を連想させるタイトルを出さない",
      not bad_stay, bad_stay[:2])
_gj = os.path.join(DIST, "data", "gacha.json")
try:
    _gacha_rows = json.load(open(_gj, encoding="utf-8"))
except (OSError, ValueError):
    _gacha_rows = None
check("運命の作品の候補のファイル（/data/gacha.json）: 3〜80本・作品ページのある発売済みの作品・未成年を連想させるタイトルは無い",
      isinstance(_gacha_rows, list) and 3 <= len(_gacha_rows) <= 80 and all(r.get("c") in everything and str(everything[r["c"]].get("date", ""))[:10] <= JST_TODAY
                                                                         and os.path.isfile(os.path.join(DIST, "item", r["c"], "index.html")) and not is_minor_title(everything[r["c"]].get("title")) for r in _gacha_rows),
      (len(_gacha_rows) if isinstance(_gacha_rows, list) else _gacha_rows))
# お気に入りを目立たせる（運営者の希望「リピーターをつけたい」。2026-10-06）: 出演者・メーカーのページの見出しの下に、黄色のお気に入りのボタン
_lead_missing = [os.path.relpath(p_, DIST) for p_ in (actress_pages + maker_pages) if not re.search(r'<button[^>]*class="fav-btn fav-btn-lead"[^>]*data-off="お気に入り（新作をお知らせ）"', read_raw(p_))]
check("出演者・メーカーのページに、目立つお気に入りのボタン（新作をお知らせ）がある", not _lead_missing, _lead_missing[:3])
check("トップの検索欄は、紙の色の検索バー（虫めがね・赤い「探す」）", re.search(r'<form class="hero-search search-bar"', home_html) is not None and 'class="search-bar-btn"' in home_html)
_pf_missing = [os.path.relpath(p_, DIST) for p_ in glob.glob(os.path.join(DIST, "month", "*", "index.html")) + glob.glob(os.path.join(DIST, "tag", "*", "index.html"))
               if os.path.basename(os.path.dirname(p_)) not in ("month", "tag") and not re.search(r'<p class="page-facts">\d+本・.+発売</p>', strip_tags_keep_p(read(p_)))]
check("月・ジャンルのページの見出しの下は、長い紹介文ではなく「○本・○月○日〜○月○日発売」の1行", not _pf_missing, _pf_missing[:3])
_mi = page_file("/maker/")
if os.path.isfile(_mi):
    _mt = re.search(r"<title>(.*?)</title>", read_raw(_mi), re.S)
    _mt = htmllib.unescape(_mt.group(1)) if _mt else ""
    check("メーカー一覧のタイトルに「FANZAのメーカー一覧」・社数・年月", _mt.startswith("FANZAのメーカー一覧（") and "社）" in _mt and _ym in _mt, _mt)

# 検索ページ
sp = os.path.join(DIST, "search", "index.html")
check("検索ページ（/search/）がある", os.path.isfile(sp))
if os.path.isfile(sp):
    stext_ = read(sp)
    check("検索ページは noindex で、sitemap に入っていない（条件ごとに内容が変わる画面のため）", 'name="robots" content="noindex' in stext_ and "/search/" not in sm_paths)
    section_ = next((t for t in tags(stext_, "section") if t.get("id") == "work-search"), None)
    check("検索の部品（#work-search）: ページを開いたときから見える（索引を待たない）・索引は /data/items-index.json・search.js を読む", section_ is not None and "hidden" not in section_ and section_.get("data-index") == "/data/items-index.json" and 'src="/search.js?v=' in stext_, section_)
    # はじめの一覧（条件なし・新しい順の、はじめの24本）・本数・ジャンルのボタンが、索引と同じ（2026-10-07）
    _ii = load_json(os.path.join(DIST, "data", "items-index.json")) if os.path.isfile(os.path.join(DIST, "data", "items-index.json")) else None
    if isinstance(_ii, dict) and isinstance(_ii.get("items"), list) and isinstance(_ii.get("genres"), list):
        _sps = int(re.search(r"export const SEARCH_PAGE_SIZE = (\d+);", read(os.path.join(ROOT, "site", "src", "lib", "search.js"))).group(1))
        _stc = int(re.search(r"export const SEARCH_TAGS_COLLAPSED = (\d+);", read(os.path.join(ROOT, "site", "src", "lib", "search.js"))).group(1))
        _want_c = [r["c"] for r in sorted(_ii["items"], key=lambda r: (-int(r["d"].replace("-", "")), r["c"]))[:_sps]]
        _wl = re.search(r'<ul id="ws-list" class="ws-list" data-first="1" data-today="(\d{4}-\d{2}-\d{2})">(.*?)</ul>', stext_, re.S)
        _got_c = [t.get("data-c") for t in tags(_wl.group(2), "li")] if _wl else []
        _cnt = re.search(r'<p id="ws-count" class="as-count ws-count" aria-live="polite">(.*?)</p>', stext_, re.S)
        _gcount = [0] * len(_ii["genres"])
        for r in _ii["items"]:
            for n in r.get("g", []):
                if 0 <= n < len(_gcount):
                    _gcount[n] += 1
        _tag_ul = re.search(r'<ul id="ws-tag-list" class="ws-tag-list" data-first="1">(.*?)</ul>', stext_, re.S)
        _tag_lis = re.findall(r'<li( hidden)?><button type="button" class="tag-btn" aria-pressed="false" data-n="(\d+)" data-name="([^"]*)"[^>]*><span class="tag-name">(.*?)</span><span class="tag-count">(\d+)</span>', _tag_ul.group(1), re.S) if _tag_ul else []
        _tags_ok = [(htmllib.unescape(nm), int(ct), bool(hd)) for hd, n_, nm, _, ct in _tag_lis] == [(g, _gcount[i], i >= _stc) for i, g in enumerate(_ii["genres"])]
        # 本数は、絞り込んだときだけ。条件なしは「ーー本」（索引の本数（最大3,000本）が、掲載している作品の数と誤解されるため。運営者の希望。2026-10-09）
        _blank = re.search(r"export const SEARCH_COUNT_BLANK = '([^']*)';", read(os.path.join(ROOT, "site", "src", "lib", "search.js"))).group(1)
        _blank_note = re.search(r"export const SEARCH_COUNT_BLANK_NOTE = '([^']*)';", read(os.path.join(ROOT, "site", "src", "lib", "search.js"))).group(1)
        check(f"作品検索: はじめの一覧（新しい順の、はじめの{_sps}本）・ジャンルのボタン（本数・はじめに出す{_stc}個）が、ページに入っていて、索引と同じ（索引を待たずに見える）",
              bool(_wl) and _wl.group(1) == JST_TODAY and _got_c == _want_c and _tags_ok,
              (_got_c[:3], _want_c[:3], _tag_lis[:2]))
        _cnt_text = strip_tags(_cnt.group(1)).strip() if _cnt else None
        check(f"作品検索: 条件なしの本数は「{_blank}本」（読み上げは「{_blank_note}」）で、索引の本数（{len(_ii['items']):,}本）をページに出さない",
              _cnt_text == f"{_blank}本{_blank_note}" and 'aria-hidden="true"' in _cnt.group(1) and 'class="ws-num ws-num-blank"' in _cnt.group(1) and f"{len(_ii['items']):,}本" not in strip_tags(stext_),
              _cnt_text)
    names_ = {t.get("name") for tag in ("input", "select") for t in tags(stext_, tag)}
    ids_ = {t.get("id") for tag in ("ul", "p", "button", "section") for t in tags(stext_, tag)}
    check("検索のフォーム（q・status・sort）と、結果の表示先（#ws-tag-list・#ws-tag-more・#ws-count・#ws-list・#ws-more）がある", {"q", "status", "sort"} <= names_ and {"ws-tag-list", "ws-tag-more", "ws-count", "ws-list", "ws-more"} <= ids_, (sorted({"q", "status", "sort"} - names_), sorted({"ws-tag-list", "ws-tag-more", "ws-count", "ws-list", "ws-more"} - ids_)))
    # 発売・並び順は、押して選ぶ丸いボタン（ラジオボタン。2026-10-06）
    radios_ = [t for t in tags(stext_, "input") if t.get("type") == "radio"]
    sel_values = [[t.get("value") for t in radios_ if t.get("name") == n] for n in ("status", "sort")]
    checked_ = [(t.get("name"), t.get("value")) for t in radios_ if "checked" in t]
    check("選択肢の値が、スクリプトの読める形（''・released・upcoming / new・popnew・pop・old）だけ・はじめは「すべて」「新しい順」",
          sel_values == [["", "released", "upcoming"], ["new", "popnew", "pop", "old"]] and sorted(checked_) == [("sort", "new"), ("status", "")], (sel_values, checked_))
    check("作品検索の検索バー（紙の色のバー・探すボタン）がある", 'class="search-bar"' in stext_ and 'class="search-bar-btn"' in stext_)
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
        check("索引の項目が、短い名前（c,p,t,d,a,m,g,i,v,o,r,n）だけで、データにある作品・長い文やURLは入っていない（i は、決まった形の画像なら省く）", all(isinstance(r, dict) and set(r) <= set("cptdamgivorn") and {"c", "t", "d", "a", "m", "g"} <= set(r) and r["c"] in valid and DAY.match(str(r["d"])) and isinstance(r["a"], list) and isinstance(r["g"], list) for r in irows) and "al.fanza.co.jp" not in read(ii), [r for r in irows if not (isinstance(r, dict) and set(r) <= set("cptdamgivorn"))][:1])
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
        bad_img = [r["c"] for r in irows if r.get("i") and not fanza_https(r["i"] if r["i"].startswith("https://") else "https://pics.dmm.co.jp/" + r["i"], ["dmm.co.jp"])]
        check("索引の画像が、FANZA(DMM)の画像に戻せる形（先頭を省いた形）", not bad_img, bad_img[:3])

        def index_image(r):
            """ブラウザ（public/search.js の rowImage）と同じ戻し方: i が無ければ決まった形、空なら画像なし"""
            if "i" not in r:
                return f"https://pics.dmm.co.jp/digital/video/{r['c']}/{r['c']}pl.jpg"
            return r["i"] if not r["i"] or r["i"].startswith("https://") else "https://pics.dmm.co.jp/" + r["i"]
        bad_back = [r["c"] for r in irows if index_image(r) != (str(valid[r["c"]].get("image_url") or "") if fanza_https(valid[r["c"]].get("image_url"), DMM) else "")]
        check("索引の画像（i。決まった形なら省いてある）を戻すと、作品データの画像と同じ", not bad_back, bad_back[:3])
        check("索引の画像は、決まった形（digital/video/作品ID/作品IDpl.jpg）なら項目ごと省いてある（索引を軽くするため）", not [r["c"] for r in irows if r.get("i") == f"digital/video/{r['c']}/{r['c']}pl.jpg"])
        sjs = read(os.path.join(DIST, "search.js"))
        check("search.js が、省いた画像を決まった形に戻し（rowImage）、結果のサムネは小さな表紙（ps.jpg）にして、無ければ大きい表紙に戻す", "function rowImage" in sjs and "'digital/video/' + row.c + '/' + row.c + 'pl.jpg'" in sjs and "smallImageUrl(rowImage(row))" in sjs and "pl.jpg" in sjs)
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

print("\n■ FANZA同人・FANZAゲーム（/doujin/・/game/。運営者の希望。2026-10-09）")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import floor_data as _FD  # noqa: E402
from claude_comments import title_block_reason as _tbr  # noqa: E402
_floor_src = read(os.path.join(ROOT, "site", "src", "lib", "floors.js"))
for _fk in _FD.FLOORS:
    _flabel = _FD.FLOORS[_fk]["label"]
    _fpath = os.path.join(ROOT, "site", "src", "data", _FD.FLOORS[_fk]["file"])
    _fdata = _FD.load_floor(_fpath) if os.path.isfile(_fpath) else None
    _fitems = list(_fdata["items"].values()) if _fdata else []
    # 画面でも、未成年を連想させる名前の作品は外す（二重の備え）。ページを作る作品は、そのあと
    _fshow = [x for x in _fitems if not any(_tbr({"title": t}) == "minor" for t in [x["title"], *x["genres"], *x["formats"], *x["sales"], x["series"], x["maker"], *x["authors"]] if t)
              and str(x["url"]).startswith("https://")]
    if not _fshow:
        check(f"{_flabel}: データが無いあいだは、ページを作らない・フッターにもリンクを出さない",
              not os.path.exists(os.path.join(DIST, _fk)) and f'href="/{_fk}/"' not in read_raw(os.path.join(DIST, "index.html")))
        continue
    _item_pages = glob.glob(os.path.join(DIST, _fk, "item", "*", "index.html"))
    check(f"{_flabel}: トップ・人気ランキング・作品ページ（{len(_item_pages)}/{len(_fshow)}）がある",
          os.path.isfile(os.path.join(DIST, _fk, "index.html")) and os.path.isfile(os.path.join(DIST, _fk, "ranking", "index.html")) and len(_item_pages) == len(_fshow),
          (len(_item_pages), len(_fshow)))
    _maker_count = Counter(x["maker_id"] for x in _fshow if x["maker_id"])
    _maker_pages = glob.glob(os.path.join(DIST, _fk, "maker", "*", "index.html"))
    check(f"{_flabel}: サークル/ブランドのページは、作品が2本以上のものだけ（{len(_maker_pages)}ページ）",
          {os.path.basename(os.path.dirname(p_)) for p_ in _maker_pages} == {str(m_) for m_, n_ in _maker_count.items() if n_ >= 2})
    _bad_minor, _bad_links, _bad_covers = [], [], []
    for p_ in glob.glob(os.path.join(DIST, _fk, "**", "*.html"), recursive=True):
        h_ = read(p_)
        t_ = re.search(r"<title>(.*?)</title>", h_, re.S)
        h1_ = re.search(r"<h1[^>]*>(.*?)</h1>", h_, re.S)
        for text_ in (htmllib.unescape(t_.group(1)) if t_ else "", strip_tags(h1_.group(1)) if h1_ else ""):
            if _tbr({"title": text_}) == "minor":
                _bad_minor.append(os.path.relpath(p_, DIST))
        for a_ in tags(h_, "a"):
            if "al.fanza.co.jp" in str(a_.get("href", "")) and (not SPONSORED <= set(str(a_.get("rel", "")).split()) or a_.get("target") != "_blank"):
                _bad_links.append(os.path.relpath(p_, DIST))
        for img_ in tags(h_, "img"):
            if has_class(img_, "floor-img") and not fanza_https(img_.get("src"), DMM):
                _bad_covers.append(os.path.relpath(p_, DIST))
            # 同人の画像は pics.dmm.co.jp から読む（doujin-assets は、運営者のiPhoneでページの中に出なかった。2026-10-09）。どのページから読んだかも送らない
            if "doujin-assets.dmm.co.jp" in str(img_.get("src", "")):
                _bad_covers.append(os.path.relpath(p_, DIST) + "（doujin-assets から読んでいる）")
            if has_class(img_, "floor-img") and img_.get("referrerpolicy") != "no-referrer":
                _bad_covers.append(os.path.relpath(p_, DIST) + "（referrerpolicy が無い）")
    check(f"{_flabel}: どのページのタイトル・見出しにも、未成年を連想させる言葉が無い", not _bad_minor, _bad_minor[:3])
    check(f"{_flabel}: FANZAへのリンクは、すべて広告の印（sponsored・nofollow）つき・新しいタブ", not _bad_links, _bad_links[:3])
    check(f"{_flabel}: 表紙の画像は DMM の https だけ・同人の画像は pics.dmm.co.jp から読み、どのページから読んだかを送らない（referrerpolicy=no-referrer）", not _bad_covers, _bad_covers[:3])
    _hub = read(os.path.join(DIST, _fk, "index.html"))
    if _fk == "doujin":
        # 同人の横長の表紙の札（順位・割引）は、表紙の左下のふちに半分かける（顔に重ねない。運営者の指摘。2026-10-09）
        check("同人: 札（順位・割引・セール中）は、表紙の上ではなく左下のふちに半分かける（枠で切らず、画像の角を丸める）・札のある棚は、どのカードもタイトルを同じだけ下げる（高さをそろえる）",
              css_has(".item-cover.is-wide .rank-badge", r"(?<![-\w])top\s*:\s*auto") and css_has(".item-cover.is-wide .rank-badge", r"bottom\s*:\s*-\d+px")
              and css_has(".item-cover.is-wide", r"overflow\s*:\s*visible") and css_has(".item-cover.is-wide .floor-img", r"border-radius\s*:\s*var\(--r-media\)")
              and any(any(re.search(r"^\.shelf:has\(\.item-cover\.is-wide \.rank-badge\) \.item-cover\.is-wide ?\+ ?\.item-title$", x_) for x_ in sels_) and re.search(r"margin-top\s*:\s*1\dpx", body_) for sels_, body_ in css_rules)
              and 'rank-badge' in _hub)
    check(f"{_flabel}: トップに「○日の時点」と「FANZAで確かめて」の注記がある（価格・セールは変わるため）", "の時点の情報です" in _hub and "FANZAで確かめて" in _hub)
    _commented = {x["cid"] for x in _fshow if x["comment_kind"] == "claude" and x["comment"]}
    _sm_floor_items = {p_[len(f"/{_fk}/item/"):-1] for p_ in sm_paths if p_.startswith(f"/{_fk}/item/")}
    check(f"{_flabel}: sitemap の作品ページ = コメントのある作品（{len(_commented)}本）・コメントの無い作品ページは noindex",
          _sm_floor_items == _commented and all(('name="robots" content="noindex' in read_raw(os.path.join(DIST, _fk, "item", c_, "index.html"))) != (c_ in _commented) for c_ in list(_fdata["items"])[:200] if c_ in {x["cid"] for x in _fshow}),
          (sorted(_commented - _sm_floor_items)[:3], sorted(_sm_floor_items - _commented)[:3]))
    # コレクション（ジャンル・シリーズ・作家・発売月のページ。運営者の希望「動画と同じレベルのコレクションを。SEO対策も徹底的に」。2026-10-09）
    # ページのある名前 = ここで数えた、決まった本数以上の名前（ジャンルはおだやかなものだけ）。ページがあれば一覧もある
    _ok_genres = set(re.findall(r"'([^']+)'", re.search(r"FLOOR_GENRE_OK = \[([\s\S]*?)\];", _floor_src).group(1)))
    _cslug = lambda s_: _hl.sha1(_ud.normalize("NFC", s_).encode("utf-8")).hexdigest()[:10]  # noqa: E731  items.js の entitySlug と同じ
    _cnames = lambda v_, n_: [t_ for t_ in (str(u_).strip() for u_ in (v_ or [])) if t_][:n_]  # noqa: E731  floors.js の names と同じ
    _cwant = {"genre": {}, "series": {}, "author": {}, "month": {}, "type": {}, "theme": {}}
    # 同人の形式（表紙の置き場所）・特集（floors.js の FLOOR_THEMES・comiketTheme と同じ条件。2026-10-09）
    _jst = datetime.date.fromisoformat(JST_TODAY)
    _ago = lambda n_: (_jst - datetime.timedelta(days=n_)).isoformat()  # noqa: E731
    _fmt = lambda name_: (lambda x: name_ in _cnames(x["formats"], 12))  # noqa: E731
    _gen = lambda name_: (lambda x: name_ in _cnames(x["genres"], 30))  # noqa: E731
    _rel = lambda x: str(x["date"])[:10] <= JST_TODAY  # noqa: E731
    _yen = lambda x: x["price"] if isinstance(x["price"], int) and 0 < x["price"] < 10_000_000 else 0  # noqa: E731
    _themes = {
        "doujin": [("senbai", _fmt("専売")), ("anime", _gen("動画・アニメーション")), ("ku100", _gen("KU100")), ("trial", _fmt("デモ・体験版あり")),
                   ("coin", lambda x: 0 < _yen(x) <= 500), ("longseller", lambda x: _rel(x) and str(x["date"])[:10] <= _ago(365))],
        "game": [("trial", _fmt("デモ・体験版あり")), ("browser", _fmt("ブラウザ対応")), ("win11", _fmt("Windows11対応作品")), ("dlonly", _fmt("DL版独占販売")),
                 ("set", _fmt("セット商品")), ("bestprice", _gen("BEST PRICE版")), ("budget", lambda x: 0 < _yen(x) <= 2000), ("anime", _gen("アニメーション")),
                 ("longseller", lambda x: _rel(x) and str(x["date"])[:10] <= _ago(365 * 5))],
    }[_fk]
    for x in _fshow:
        _m = re.match(r"^https://(?:pics|doujin-assets)\.dmm\.co\.jp/digital/(comic|cg|voice|game)/", str(x["image_url"] or "")) if _fk == "doujin" else None
        if _m:
            _cwant["type"].setdefault(_m.group(1), []).append(x)
        if _fk == "doujin":
            for f_ in set(_cnames(x["formats"], 12)):
                _cm = re.match(r"^コミケ(\d{2,3})（(\d{4})(夏|冬)）$", f_)
                if _cm:
                    _cwant["theme"].setdefault(f"comiket{_cm.group(1)}", []).append(x)
        for s_, t_ in _themes:
            if t_(x):
                _cwant["theme"].setdefault(s_, []).append(x)
    for x in _fshow:
        for g_ in set(_cnames(x["genres"], 30)) & _ok_genres:
            _cwant["genre"].setdefault(_cslug(g_), []).append(x)
        if isinstance(x["series_id"], int) and x["series_id"] > 0 and str(x["series"]).strip():
            _cwant["series"].setdefault(str(x["series_id"]), []).append(x)
        for a_ in set(_cnames(x["authors"], 4)):
            _cwant["author"].setdefault(_cslug(a_), []).append(x)
        _cwant["month"].setdefault(str(x["date"])[:7], []).append(x)
    _cmin = {"genre": 3, "series": 3, "author": 2, "month": 5, "type": 3, "theme": 3}
    _col_bad, _col_sm, _col_noidx, _col_n = [], [], [], {}
    for kind_, groups_ in _cwant.items():
        want_ = {s_ for s_, xs_ in groups_.items() if len(xs_) >= _cmin[kind_]}
        got_ = {os.path.basename(os.path.dirname(p_)) for p_ in glob.glob(os.path.join(DIST, _fk, kind_, "*", "index.html"))}
        _col_n[kind_] = len(got_)
        if want_ != got_:
            _col_bad.append((kind_, sorted(want_ - got_)[:3], sorted(got_ - want_)[:3]))
        if bool(want_) != os.path.isfile(os.path.join(DIST, _fk, kind_, "index.html")):
            _col_bad.append((kind_, "一覧のページ"))
        for s_ in got_ & want_:
            path_ = f"/{_fk}/{kind_}/{s_}/"
            noidx_ = 'name="robots" content="noindex' in read_raw(os.path.join(DIST, _fk, kind_, s_, "index.html"))
            if noidx_ == (path_ in sm_paths):
                _col_sm.append(path_)
            if not noidx_ and not any(x["comment_kind"] == "claude" and x["comment"] for x in groups_[s_]):
                _col_noidx.append(path_)
        idx_ = os.path.join(DIST, _fk, kind_, "index.html")
        if os.path.isfile(idx_) and ('name="robots" content="noindex' in read_raw(idx_)) == (f"/{_fk}/{kind_}/" in sm_paths):
            _col_sm.append(f"/{_fk}/{kind_}/")
    check(f"{_flabel}: コレクションのページは、決まった本数以上の名前だけ（ジャンル{_col_n['genre']}・シリーズ{_col_n['series']}・作家{_col_n['author']}・発売月{_col_n['month']}・形式{_col_n['type']}・特集{_col_n['theme']}）・ページがあれば一覧もある",
          not _col_bad, _col_bad[:3])
    check(f"{_flabel}: コレクションのページ・一覧: sitemap に入っている ⇔ noindex でない・コメントのある作品が1本も無いページは noindex",
          not _col_sm and not _col_noidx, (_col_sm[:3], _col_noidx[:3]))
    if _col_n["genre"]:
        check(f"{_flabel}: 売り場のトップの「作品を探す」から「ジャンル検索」へリンクしている", f'href="/{_fk}/genre/"' in read_raw(os.path.join(DIST, _fk, "index.html")))
    # 人気サークル/ブランド・作家ランキング・作品検索・運命の作品・パソコン用の2列（運営者の希望。2026-10-09）
    _released = [x for x in _fshow if str(x["date"])[:10] <= JST_TODAY]
    _show_cids = {x["cid"] for x in _fshow}
    _er_bad = []
    for by_ in ("maker", "author"):
        p_ = os.path.join(DIST, _fk, "ranking", by_, "index.html")
        if not os.path.isfile(p_):
            continue
        h_ = read_raw(p_)
        if len(re.findall(r'<span class="erank-no">', h_)) < 1 or "の時点" not in read(p_):
            _er_bad.append((by_, "行・注記"))
        if ('name="robots" content="noindex' in h_) == (f"/{_fk}/ranking/{by_}/" in sm_paths):
            _er_bad.append((by_, "sitemap"))
    _want_maker_rank = any(x["maker_id"] for x in _released if x["cid"] in _fdata["ranks"])
    check(f"{_flabel}: 人気{'サークル' if _fk == 'doujin' else 'ブランド'}ランキングがある・行に順位・「○日の時点」・sitemap に入っている ⇔ noindex でない",
          not _er_bad and os.path.isfile(os.path.join(DIST, _fk, "ranking", "maker", "index.html")) == _want_maker_rank, _er_bad)
    _sp = os.path.join(DIST, _fk, "search", "index.html")
    _six = os.path.join(DIST, "data", f"{_fk}-index.json")
    _six_ok = False
    if os.path.isfile(_six):
        _sj = json.load(open(_six, encoding="utf-8"))
        _six_ok = len(_sj.get("items", [])) == len(_fshow) and all(re.match(r"^[A-Za-z0-9_-]+$", r_["c"]) for r_ in _sj["items"]) and set(_sj.get("genres", [])) <= _ok_genres
    check(f"{_flabel}: 作品検索のページ（noindex・sitemap なし）と索引（全作品・おだやかなジャンルだけ）がある",
          os.path.isfile(_sp) and 'name="robots" content="noindex' in read_raw(_sp) and f"/{_fk}/search/" not in sm_paths and _six_ok and 'id="fs-list"' in read_raw(_sp))
    _gj = os.path.join(DIST, "data", f"{_fk}-gacha.json")
    _gpool = json.load(open(_gj, encoding="utf-8")) if os.path.isfile(_gj) else []
    _hub_raw = read_raw(os.path.join(DIST, _fk, "index.html"))
    check(f"{_flabel}: 運命の作品の候補（{len(_gpool)}本）は、この売り場の作品ページへ・トップと作品ページに運命の作品の欄（VR・単体の絞り込みを使わない）",
          len(_gpool) >= 3 and all(re.match(rf"^/{_fk}/item/[A-Za-z0-9_-]+/$", r_["h"]) and r_["c"] in _show_cids for r_ in _gpool)
          and 'id="gacha-data"' in _hub_raw and "data-nofilter" in _hub_raw
          and all(f'data-src="/data/{_fk}-gacha.json"' in read_raw(p_) for p_ in _item_pages[:20]))
    # 動画のトップと同じ形・同じ CSS（運営者の希望「動画のページと、ほぼ同じ要領で」。2026-10-09）。ボタンを並べた案内（タブ）は、どのページにも出さない（運営者の指摘「ボタンが大量に並んで見づらい」）
    _tabs = [os.path.relpath(p_, DIST) for p_ in glob.glob(os.path.join(DIST, _fk, "**", "index.html"), recursive=True) if 'class="floor-tabs' in read_raw(p_)]
    check(f"{_flabel}: トップは動画のトップと同じ形（見出し・きょうの人気TOP3・作品を探す・パソコンは右の欄）・ボタンを並べた案内（タブ）はどのページにも無い",
          'class="home has-side"' in _hub_raw and 'class="home-side"' in _hub_raw and 'class="today-title"' in _hub_raw and 'class="medals' in _hub_raw
          and f'action="/{_fk}/search/"' in _hub_raw and not _tabs, _tabs[:3])
    # セールごと（ゲーム）・割引ごと（同人）のページ（運営者の希望「セールの充実」。2026-10-09）: 対象が3本以上のものだけ
    _released = [x for x in _fshow if str(x["date"])[:10] <= JST_TODAY]
    if _fk == "game":
        _tagc = Counter(t_ for x in _released for t_ in _cnames(x["sales"], 8) if "セール" in t_ and not re.search(r"クーポン|還元", t_))
        _sp_want = {_cslug(t_) for t_, n_ in _tagc.items() if n_ >= 3}
    else:
        _offs = [int((1 - x["price"] / x["list_price"]) * 100 + 0.5) for x in _released
                 if isinstance(x["price"], int) and isinstance(x["list_price"], int) and 0 < x["price"] < x["list_price"] < 10_000_000]
        _sp_want = {f"off{m_}" for m_ in (90, 70, 50) if sum(1 for o_ in _offs if o_ >= m_) >= 3}
    _sp_pages = {os.path.basename(os.path.dirname(p_)): p_ for p_ in glob.glob(os.path.join(DIST, _fk, "sale", "*", "index.html"))}
    _sp_pages.pop("history", None)
    check(f"{_flabel}: セールのページ（{'セールの札ごと' if _fk == 'game' else '割引ごと'}・{len(_sp_pages)}ページ）は、対象が3本以上のものだけ", set(_sp_pages) == _sp_want, (sorted(_sp_want - set(_sp_pages))[:3], sorted(set(_sp_pages) - _sp_want)[:3]))
    _sp_bad = []
    for s_, p_ in _sp_pages.items():
        h_ = read(p_)
        path_ = f"/{_fk}/sale/{s_}/"
        if "の時点" not in h_ or "FANZAの作品ページで確かめて" not in h_:
            _sp_bad.append((path_, "注記"))
        if ('name="robots" content="noindex' in read_raw(p_)) == (path_ in sm_paths):
            _sp_bad.append((path_, "sitemap"))
    check(f"{_flabel}: セールのページに「○日の時点」「FANZAの作品ページで確かめて」の注記がある・sitemap に入っている ⇔ noindex でない", not _sp_bad, _sp_bad[:3])
    # 「セールはいつ？」（/…/sale/history/）: データから数えた事実だけ。記録が7日に満たないあいだは noindex
    _hist_page = os.path.join(DIST, _fk, "sale", "history", "index.html")
    _hh = read(_hist_page) if os.path.isfile(_hist_page) else ""
    check(f"{_flabel}: 「セールはいつ？」のページがある・予想は書かない・sitemap に入っている ⇔ noindex でない",
          bool(_hh) and "次の開催日は分かりません" in _hh and not re.search(r"予想されます|見込みです|はずです", _hh)
          and ('name="robots" content="noindex' in read_raw(_hist_page)) != (f"/{_fk}/sale/history/" in sm_paths))
    # 人気の動き（毎日の順位の記録。2026-10-09）: 上位300本に入ったことのある作品のページにだけ「人気の動き」がある
    _frh_path = os.path.join(ROOT, "site", "src", "data", "floor_rank_history.json")
    _frh = (json.load(open(_frh_path, encoding="utf-8")).get(_fk) or {}) if os.path.isfile(_frh_path) else {}
    _show_cids = {x["cid"] for x in _fshow}
    _trend_want = {c_ for c_, r_ in _frh.items() if c_ in _show_cids and isinstance(r_, dict) and re.match(r"^\d{4}-\d{2}-\d{2}$", str(r_.get("d", "")))
                   and any(type(v_) is int and 0 < v_ <= 100000 for v_ in (r_.get("r") or [])[:30])
                   and sum(1 for v_ in (r_.get("r") or [])[:30] if type(v_) is int and 0 <= v_ <= 100000) >= 2}
    _trend_got = {os.path.basename(os.path.dirname(p_)) for p_ in _item_pages if 'aria-labelledby="trend-title"' in read_raw(p_)}
    check(f"{_flabel}: 人気ランキングの上位300本に入ったことがあり、2日以上の記録がある作品（{len(_trend_want)}本）のページにだけ「人気の動き」がある", _trend_want == _trend_got,
          (sorted(_trend_want - _trend_got)[:3], sorted(_trend_got - _trend_want)[:3]))
    _sale_page = os.path.join(DIST, _fk, "sale", "index.html")
    if os.path.isfile(_sale_page):
        _sh = read(_sale_page)
        check(f"{_flabel}: セールのページに「○日の時点」の注記と、FANZA動画のセールへのリンクがある", "の時点の情報です" in _sh and 'href="/sale/"' in _sh)
check("サイトの「セール・キャンペーン」（/sale/）から、同人・ゲームのセールのページへリンクしている（ページがあるものだけ）",
      all((f'href="/{k_}/sale/"' in read_raw(os.path.join(DIST, "sale", "index.html"))) == os.path.isfile(os.path.join(DIST, k_, "sale", "index.html")) for k_ in _FD.FLOORS))
check("同人・ゲームの見出しに出すジャンルの一覧（floors.js）に、行為・未成年を連想させる言葉が無い",
      not any(_tbr({"title": g_}) == "minor" for g_ in re.findall(r"'([^']+)'", re.search(r"FLOOR_GENRE_OK = \[([\s\S]*?)\];", _floor_src).group(1))))

if problems:
    print("\n失敗:", problems)
    sys.exit(1)
print("\n=== ビルド結果 OK ===")
