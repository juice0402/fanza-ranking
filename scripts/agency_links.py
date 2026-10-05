"""所属事務所の公式サイトから、所属女優の「所属事務所・X・Instagram」を集めて site/src/data/agencies.json に保存する（週1回）。

運営者の希望（2026-10-05）「所属を、所属先の公式的な情報から反映できないか。そこにTwitterやインスタのリンクがあったら確実な情報として」
→ 見本で確かめてから採用（「今後も所属が増えたり移籍したりするので、自動で進めたい」）。
毎日の更新（.github/workflows/update.yml）の中で動き、前に集めてから7日たっていなければ何もしない（--force で、すぐ集め直す）。

決まり:
- 読むのは、robots.txt で止められていない、所属女優の一覧とプロフィールのページだけ（urllib.robotparser で確かめる）。
  相手のサイトに負担をかけないよう、1回ずつ間をあける（INTERVAL_SEC）。
- 保存するのは「FANZAの名前・id・事務所・X・Instagram（アカウント名だけ）・情報を取ったページのURL・見かけた日」だけ。
  事務所のページにある生年月日・出身地・血液型・画像・文章は保存しない。
- 事務所の側の名前は、プロフィール1つにつき1つ（一覧のリンクの文字など）。その名前の全体（空白を除く）が、FANZA の名前（かっこの前）と
  完全に同じで、FANZA に同じ名前が1人だけのときだけ結びつける（名前の一部・前の名前・ページの中のほかの見出しでは合わせない。人違いを防ぐ）。
  短い名前（日本語で2文字まで・ローマ字だけで4文字まで）は、ほかの人と同じになりやすいので結びつけない。
- どのプロフィールにも出てくるSNS（事務所のアカウント）と、2人以上のプロフィールに出てくるSNSは、本人のものと決められないので外す。
- 事務所のサイトが読めない・作り替えで前の半分も読めないときは、その事務所の分は前の情報を残す（見かけてから30日まで）。
  読めた事務所の一覧から消えた人（移籍・引退など）は、その事務所の情報を消す。2つの事務所に同じ人がいたら、新しく読めたほうにする。
- Python の標準ライブラリだけ。

使い方:
  python scripts/agency_links.py --update          7日たっていれば集め直して保存する（毎日の更新から）
  python scripts/agency_links.py --update --force  すぐ集め直して保存する（「Refresh FANZA Data」から）
"""
import html as htmllib
import json
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

USER_AGENT = "Mozilla/5.0 (compatible; fanza-ranking-bot/1.0; +https://fanza-ranking.pages.dev/)"
INTERVAL_SEC = float(os.environ.get("AGENCY_INTERVAL_SEC", "2"))  # 同じサイトへ続けて読みに行くときの間（サイトごと。事務所どうしは同時に読む）
MAX_PROFILES = 500  # 1つの事務所で読むプロフィールの上限
REFRESH_DAYS = 7  # 前に集めてから、この日数がたったら集め直す
KEEP_DAYS = 30  # 事務所のサイトが読めないあいだ、前の情報を残す日数（見かけた日から）
MIN_RATIO = 0.5  # 読めたプロフィールが、前の回のこの割合より少なければ、作り替えなどで読めていないとみなす
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "site", "src", "data")
AGENCY_PATH = os.environ.get("AGENCY_PATH", os.path.join(DATA_DIR, "agencies.json"))

# 事務所ごとの、公式サイト・一覧のページ・プロフィールのページのURLの形（2026-10-05 に下調べ。robots.txt で止められていない・所属女優の一覧がある所。
# SNS が載っていない事務所も、所属は付ける（運営者の希望）。
# 画面に出す名前・URLは site/src/lib/agencies.js の AGENCIES と同じ（tests/test_agencies.mjs で突き合わせている）
SITES = [
    {"key": "tpowers", "name": "ティーパワーズ", "url": "https://www.t-powers.co.jp/", "roster": ["https://www.t-powers.co.jp/talent/"],
     "profile": r"^https://www\.t-powers\.co\.jp/talent/[^/?#]+/?$"},
    {"key": "mines", "name": "マインズ", "url": "https://mines-pro.jp/", "roster": ["https://mines-pro.jp/model/"],
     "profile": r"^https://mines-pro\.jp/model/\d+/?$"},
    {"key": "bambi", "name": "バンビプロモーション", "url": "https://bambi.ne.jp/", "roster": ["https://bambi.ne.jp/models.html"],
     "profile": r"^https://bambi\.ne\.jp/model\.php\?id=\d+$"},
    {"key": "soagent", "name": "SO MODELAGENT", "url": "https://so-agent.jp/", "roster": ["https://so-agent.jp/model.php"],
     "profile": r"^https://so-agent\.jp/model/[A-Za-z0-9_-]+/?$"},
    {"key": "alive", "name": "プロダクションALIVE", "url": "https://alive-pro.tokyo/", "roster": ["https://alive-pro.tokyo/model"],
     "profile": r"^https://alive-pro\.tokyo/model/[A-Za-z0-9_-]+/?$",
     "name_prefix": r"^アライブ所属のモデル\s*"},  # 一覧のリンクの文字がローマ字なので、プロフィールの見出し「アライブ所属のモデル 石川 澪」から
    # ここから下は 2026-10-05 の2回目の下調べ（scripts/agency_discover.py。日本プロダクション協会の加盟社などの公式サイト）で足したもの
    {"key": "esflat", "name": "エスフラート", "url": "http://www.style-1.jp/", "roster": ["http://www.style-1.jp/"],
     "profile": r"^http://www\.style-1\.jp/category/actress/[A-Za-z0-9_-]+/$", "via_profile": True},  # プロフィールの横に全員が並ぶ
    {"key": "capsule", "name": "カプセルエージェンシー", "url": "https://capsule.bz/", "roster": ["https://capsule.bz/model/"],
     "profile": r"^https://capsule\.bz/model/[A-Za-z0-9_-]+/$", "label_name": r"（([^）]{2,20})）"},  # 一覧の文字が「（七沢みあ）AV女優」
    {"key": "cmore", "name": "C-more ENTERTAINMENT", "url": "https://cmore.jp/official/", "roster": ["https://cmore.jp/official/model.html"],
     "profile": r"^https://cmore\.jp/official/model-[A-Za-z0-9_-]+\.html$"},
    {"key": "light", "name": "LIGHT promotion", "url": "https://lightpro.jp/", "roster": ["https://lightpro.jp/talent"],
     "profile": r"^https://lightpro\.jp/talent/[A-Za-z0-9_-]+\.html$"},
    {"key": "life", "name": "ライフプロモーション", "url": "https://life-promotion.com/", "roster": ["https://life-promotion.com/"],
     "profile": r"^https://life-promotion\.com/model/[A-Za-z0-9_-]+\.php$"},
    {"key": "linx", "name": "LINX", "url": "https://pub.linx.live/", "roster": ["https://pub.linx.live/contents/"],
     "profile": r"^https://pub\.linx\.live/contents/\?mode=model&model_id=\d+$"},
    {"key": "nax", "name": "NAX", "url": "https://official.nax-pro.com/", "roster": ["https://official.nax-pro.com/model/"],
     "profile": r"^https://official\.nax-pro\.com/model/\d+/?$", "title_name": r"^(.+?)\s*[|｜]\s*AVプロダクション"},  # 一覧が画像だけなので、タイトル「松永 あかり | AVプロダクション NAX」から
    {"key": "duo", "name": "Duo Entertainment", "url": "https://www.duo-official.com/", "roster": ["https://www.duo-official.com/models/"],
     "profile": r"^https://www\.duo-official\.com/models/[A-Za-z0-9_-]+/?$", "title_name": r"^(.+?)\s*[–—|｜-]\s*Duo"},  # タイトル「希島あいり Airi Kijima – Duo …」から
]

X_LINK = re.compile(r"^https?://(?:www\.|mobile\.)?(?:twitter|x)\.com/(?:#!/)?@?([A-Za-z0-9_]{1,15})/?(?:\?.*)?$", re.I)
IG_LINK = re.compile(r"^https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]{1,30})/?(?:\?.*)?$", re.I)
X_HANDLE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
IG_HANDLE = re.compile(r"^[A-Za-z0-9_.]{1,30}$")
X_RESERVED = {"share", "intent", "home", "search", "hashtag", "i", "login", "signup", "explore", "settings", "privacy", "tos"}
IG_RESERVED = {"p", "reel", "reels", "explore", "accounts", "stories", "tv", "about", "legal", "developer"}
CJK = re.compile(r"[぀-ヿ㐀-鿿]")

_robots = {}
_last = {}  # サイト（ホスト）ごとの、最後に読みに行った時刻
_lock = threading.Lock()


def jst_today():
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")


def days_between(a, b):
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------
# 読み込み（robots.txt を守る・間をあける）
# ------------------------------------------------------------------

def allowed(url):
    """robots.txt で止められていないか（robots.txt が無い（404）ときは止められていない、と同じあつかい。読めないときは読まない）"""
    parts = urllib.parse.urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.parse(fetch_raw(base + "/robots.txt", check_robots=False).splitlines())
        except urllib.error.HTTPError as e:
            rp.parse([] if e.code in (404, 410) else ["User-agent: *", "Disallow: /"])
        except (urllib.error.URLError, OSError, ValueError):
            rp.parse(["User-agent: *", "Disallow: /"])
        _robots[base] = rp
    return _robots[base].can_fetch(USER_AGENT, url)


def fetch_raw(url, check_robots=True):
    if check_robots and not allowed(url):
        raise PermissionError(f"robots.txt で止められている: {url}")
    host = urllib.parse.urlsplit(url).netloc
    with _lock:  # 同じサイトへは INTERVAL_SEC 秒ずつ間をあける（順番を先に決めてから待つ）
        now = time.time()
        start = max(now, _last.get(host, 0.0) + INTERVAL_SEC)
        _last[host] = start
    if start > now:
        time.sleep(start - now)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ja"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            raw = res.read(3_000_000)
            charset = res.headers.get_content_charset() or ""
    finally:
        with _lock:
            _last[host] = max(_last.get(host, 0.0), time.time())
    if not charset:
        m = re.search(rb'charset=["\']?([A-Za-z0-9_-]+)', raw[:4000])
        charset = m.group(1).decode() if m else "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


# ------------------------------------------------------------------
# ページから取り出す
# ------------------------------------------------------------------

def text_of(fragment):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def links(page_html, base_url):
    """ページの中のリンク（絶対URL）と、その文字（文字が無ければ、中の画像の alt）"""
    out = []
    for m in re.finditer(r"<a\b[^>]*?\bhref\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a>", page_html, re.I | re.S):
        href = htmllib.unescape(m.group(2)).strip()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        label = text_of(m.group(3)) or " ".join(htmllib.unescape(a) for a in re.findall(r"<img\b[^>]*\balt\s*=\s*[\"']([^\"']+)[\"']", m.group(3), re.I)).strip()
        out.append((urllib.parse.urljoin(base_url, href), label))
    return out


def meta_content(page_html, prop):
    m = re.search(r"<meta\b[^>]*(?:property|name)\s*=\s*[\"']%s[\"'][^>]*>" % re.escape(prop), page_html, re.I)
    if not m:
        return ""
    c = re.search(r"\bcontent\s*=\s*([\"'])(.*?)\1", m.group(0), re.I | re.S)
    return htmllib.unescape(c.group(2)).strip() if c else ""


def name_candidates(page_html):
    """プロフィールのページの見出しの文字（h1〜h3・class に name を含む要素・og:title・title）。事務所ごとの決まった見出しから名前を取るときに使う"""
    cands = []
    for tag in ("h1", "h2", "h3"):
        cands += [text_of(x) for x in re.findall(r"<%s\b[^>]*>(.*?)</%s>" % (tag, tag), page_html, re.I | re.S)[:4]]
    cands += [text_of(x) for x in re.findall(r"<(?:p|div|span|dd|li|strong)\b[^>]*\bclass\s*=\s*[\"'][^\"']*name[^\"']*[\"'][^>]*>(.*?)</(?:p|div|span|dd|li|strong)>", page_html, re.I | re.S)[:6]]
    cands.append(meta_content(page_html, "og:title"))
    t = re.search(r"<title\b[^>]*>(.*?)</title>", page_html, re.I | re.S)
    if t:
        cands.append(text_of(t.group(1)))
    out = []
    for c in cands:
        for part in re.split(r"\s*[|｜/／\-–—:：「」【】\[\]()（）]\s*", c or ""):
            part = part.strip()
            if 1 < len(part) <= 30 and part not in out:
                out.append(part)
    return out


def sns_links(page_html, base_url):
    """ページの中の X・Instagram のアカウント名（共有ボタンなどは除く）"""
    xs, igs = [], []
    for url, _ in links(page_html, base_url):
        m = X_LINK.match(url)
        if m and m.group(1).lower() not in X_RESERVED:
            if m.group(1).lower() not in [h.lower() for h in xs]:
                xs.append(m.group(1))
            continue
        m = IG_LINK.match(url)
        if m and m.group(1).lower() not in IG_RESERVED:
            handle = m.group(1).rstrip(".")
            if handle and handle.lower() not in [h.lower() for h in igs]:
                igs.append(handle)
    return xs, igs


def strip_romaji(name):
    """「美乃すずめ Suzume Mino」→「美乃すずめ」（うしろのローマ字を外す）"""
    return re.sub(r"(?:\s+[A-Za-z][A-Za-z.'-]*)+$", "", name).strip()


def agency_name(site, label, cands, title=""):
    """プロフィール1つにつき、事務所の側の名前を1つだけ決める（ページの中のほかの女優の名前を拾わないように）。順に:
    1. 事務所ごとの決まった形の一覧のリンクの文字（label_name。「（七沢みあ）AV女優」→「七沢みあ」）
    2. 一覧のリンクの文字（「美乃すずめ Suzume Mino」ならローマ字を外す）
    3. 事務所ごとの決まった見出し（name_prefix。「アライブ所属のモデル 石川 澪」→「石川 澪」）
    4. 事務所ごとの決まった形のページのタイトル（title_name。「松永 あかり | AVプロダクション NAX」→「松永 あかり」）
    5. 一覧のリンクの文字（ローマ字だけ）"""
    label = re.sub(r"\s+", " ", label or "").strip()
    if site.get("label_name"):
        m = re.search(site["label_name"], label)
        if m and CJK.search(m.group(1)):
            return strip_romaji(m.group(1).strip())
    if CJK.search(label) and not site.get("label_name"):
        return strip_romaji(label)
    if site.get("name_prefix"):
        for c in cands:
            m = re.match(site["name_prefix"], c)
            if m and CJK.search(c[m.end():]):
                return c[m.end():].strip()
    if site.get("title_name"):
        m = re.search(site["title_name"], re.sub(r"\s+", " ", title or "").strip())
        if m and CJK.search(m.group(1)):
            return strip_romaji(m.group(1).strip())
    return "" if site.get("label_name") else label


# ------------------------------------------------------------------
# FANZA の名前との照らし合わせ
# ------------------------------------------------------------------

def norm_name(name):
    """名前の照らし合わせ用（NFKC・空白と中点を除く）"""
    return re.sub(r"[\s・･]", "", unicodedata.normalize("NFKC", str(name or "")))


def fanza_names(data_dir=None):
    """FANZA 公式の名前（女優検索の名簿・出演者プロフィール・このサイトの作品の出演者）→ { 照らし合わせ用の名前: { FANZAの名前: {id, …} } }。
    「河北彩花（河北彩伽）」のような名前は、かっこの前の名前でも引けるようにする（かっこの中＝前の名前などでは引かない）"""
    data_dir = data_dir or DATA_DIR
    table = {}

    def add(name, id_=""):
        name = str(name or "").strip()
        if not name:
            return
        for key in {name, re.split(r"[（(]", name)[0]}:
            k = norm_name(key)
            if len(k) >= 2:
                ids = table.setdefault(k, {}).setdefault(name, set())
                if id_:
                    ids.add(id_)

    for path, field in (("actress_directory.json", "rows"), ("actresses.json", "actresses")):
        try:
            for r in json.load(open(os.path.join(data_dir, path), encoding="utf-8")).get(field, []):
                add(r.get("name"), str(r.get("id") or ""))
        except (OSError, ValueError, AttributeError):
            pass
    shards = [os.path.join(data_dir, "new_releases.json")]
    catalog_dir = os.path.join(data_dir, "catalog")
    if os.path.isdir(catalog_dir):
        shards += [os.path.join(catalog_dir, f) for f in sorted(os.listdir(catalog_dir)) if f.endswith(".json")]
    for path in shards:
        try:
            for item in json.load(open(path, encoding="utf-8")):
                for name in item.get("actress") or []:
                    add(name)
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    return table


def name_ok(name):
    """結びつけてよい長さの名前か（短い名前は、ほかの人と同じになりやすいので使わない）。日本語は3文字以上、ローマ字だけなら5文字以上"""
    key = norm_name(name)
    return len(key) >= 3 if CJK.search(key) else len(key) >= 5


def lookup(table, name):
    """事務所の側の名前 → (FANZAの名前, id, 理由)。1人に決まらなければ名前は空"""
    if not name_ok(name):
        return "", "", "名前が短くて決められない"
    hits = table.get(norm_name(name), {})
    if not hits:
        return "", "", "FANZAの名前と合わない"
    if len(hits) > 1 or any(len(ids) > 1 for ids in hits.values()):
        return "", "", "FANZAに同じ名前が何人もいる"
    (fanza, ids), = hits.items()
    return fanza, next(iter(ids), ""), "一致"


def match_profiles(site, pages, table):
    """読んだプロフィール [(URL, 一覧の文字, 見出しの候補, X, Instagram, ページのタイトル)] → 行（FANZA の名前と結びついたかどうかも）"""
    count_x, count_ig = {}, {}
    for p in pages:
        xs, igs = p[3], p[4]
        for h in {h.lower() for h in xs}:
            count_x[h] = count_x.get(h, 0) + 1
        for h in {h.lower() for h in igs}:
            count_ig[h] = count_ig.get(h, 0) + 1
    # どのプロフィールにも出てくるSNS（事務所のアカウント）・2人以上のプロフィールに出てくるSNSは、本人のものと決められないので外す
    shared_x = {h for h, n in count_x.items() if n >= 2}
    shared_ig = {h for h, n in count_ig.items() if n >= 2}
    rows = []
    for p in pages:
        url, label, cands, xs, igs = p[:5]
        name = agency_name(site, label, cands, p[5] if len(p) > 5 else "")
        fanza, fid, how = lookup(table, name) if name else ("", "", "名前が読めない")
        rows.append({
            "agency": site["key"], "source": url, "agency_name": name, "fanza_name": fanza, "fanza_id": fid, "match": how,
            "x": [h for h in xs if h.lower() not in shared_x][:1],
            "instagram": [h for h in igs if h.lower() not in shared_ig][:1],
        })
    return rows


def collect_site(site, table):
    """1つの事務所の一覧とプロフィールを読む → (結果のまとめ, 行)"""
    report = {"key": site["key"], "roster_ok": False, "found": 0, "read": 0, "errors": []}
    pattern = re.compile(site["profile"])
    found = []
    for roster in site["roster"]:
        try:
            page = fetch_raw(roster)
            report["roster_ok"] = True
        except Exception as e:  # noqa: BLE001 相手のサイトの不具合（途中で切れた・文字化けなど）では止まらない
            report["errors"].append(f"一覧: {type(e).__name__}: {e}"[:200])
            continue
        for url, label in links(page, roster):
            url = url.split("#")[0]
            if pattern.match(url) and url not in [f[0] for f in found]:
                found.append((url, label))
    # 一覧のページに一部しか載らず、プロフィールのページの横に全員が並ぶ事務所（via_profile）は、最初のプロフィールのページも一覧として読む
    if site.get("via_profile") and found:
        try:
            page = fetch_raw(found[0][0])
            for url, label in links(page, found[0][0]):
                url = url.split("#")[0]
                if pattern.match(url) and url not in [f[0] for f in found]:
                    found.append((url, label))
        except Exception as e:  # noqa: BLE001
            report["errors"].append(f"一覧（プロフィールの横）: {type(e).__name__}: {e}"[:200])
    report["found"] = len(found)
    pages = []
    for url, label in found[:MAX_PROFILES]:
        try:
            page = fetch_raw(url)
        except Exception as e:  # noqa: BLE001
            report["errors"].append(f"{url}: {type(e).__name__}: {e}"[:200])
            continue
        report["read"] += 1
        xs, igs = sns_links(page, url)
        t = re.search(r"<title\b[^>]*>(.*?)</title>", page, re.I | re.S)
        pages.append((url, label, name_candidates(page), xs, igs, text_of(t.group(1)) if t else ""))
    return report, match_profiles(site, pages, table)


# ------------------------------------------------------------------
# 保存するデータ（前の情報を壊さない）
# ------------------------------------------------------------------

def load_previous(path=None):
    """前に保存したデータ。無ければ空。壊れていれば ValueError（上書きしない）"""
    path = path or AGENCY_PATH
    if not os.path.exists(path):
        return {"updated": "", "sites": [], "rows": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list) or not isinstance(data.get("sites"), list):
        raise ValueError("agencies.json の形が違う")
    return data


def clean_row(r):
    """保存する1行（決まった項目だけ・アカウント名は形を確かめる）。使えなければ None"""
    site = next((s for s in SITES if s["key"] == r.get("agency")), None)
    name = str(r.get("name") or "").strip()
    source = str(r.get("source") or "")
    if not site or not name or not re.match(r"^" + re.escape(site["url"]), source) or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(r.get("seen") or "")):
        return None
    row = {"name": name}
    if re.match(r"^\d{1,12}$", str(r.get("id") or "")):
        row["id"] = str(r["id"])
    row["agency"] = site["key"]
    if X_HANDLE.match(str(r.get("x") or "")):
        row["x"] = r["x"]
    if IG_HANDLE.match(str(r.get("instagram") or "")):
        row["instagram"] = r["instagram"]
    row["source"] = source
    row["seen"] = r["seen"]
    return row


def build_dataset(results, previous, today):
    """事務所ごとの今回の結果 {key: (まとめ, 行)} と前のデータ → 保存するデータ。
    読めた事務所は今回の行に入れ替え、読めなかった事務所（作り替えで前の半分も読めないときも）は前の行を残す（見かけてから KEEP_DAYS 日まで）"""
    prev_sites = {s.get("key"): s for s in previous.get("sites", []) if isinstance(s, dict)}
    prev_rows = [r for r in (clean_row(r) for r in previous.get("rows", []) if isinstance(r, dict)) if r]
    sites, rows, fresh_keys = [], [], set()
    for site in SITES:
        key = site["key"]
        report, new_rows = results.get(key, ({"roster_ok": False, "read": 0}, []))
        before = int(prev_sites.get(key, {}).get("profiles") or 0)
        fresh = report.get("roster_ok") and report.get("read", 0) > 0 and report["read"] >= before * MIN_RATIO
        if fresh:
            fresh_keys.add(key)
            sites.append({"key": key, "checked": today, "profiles": report["read"]})
            for r in new_rows:
                if r.get("fanza_name"):
                    row = clean_row({"name": r["fanza_name"], "id": r.get("fanza_id"), "agency": key, "x": (r.get("x") or [""])[0],
                                     "instagram": (r.get("instagram") or [""])[0], "source": r["source"], "seen": today})
                    if row:
                        rows.append(row)
        else:
            old = prev_sites.get(key)
            sites.append({"key": key, "checked": old.get("checked", "") if old else "", "profiles": before})
            for r in prev_rows:
                left = days_between(r["seen"], today)
                if r["agency"] == key and left is not None and left <= KEEP_DAYS:
                    rows.append(r)
    # 同じ人が2つ以上の行にいるとき: 今回読めた事務所の行が1つだけなら、それにする（移籍）。決められなければ、どれも出さない
    by_name = {}
    for r in rows:
        by_name.setdefault(r["name"], []).append(r)
    out = []
    for name, rs in by_name.items():
        if len(rs) > 1:
            rs = [r for r in rs if r["agency"] in fresh_keys and r["seen"] == today]
        if len(rs) == 1:
            out.append(rs[0])
    out.sort(key=lambda r: (r["name"], r["agency"]))
    # 1つも読めなかったとき（ネットの不具合など）は、集め直した日にしない（次の日にまた試す）
    return {"updated": today if fresh_keys else str(previous.get("updated") or ""), "sites": sites, "rows": out}


def dump_dataset(data):
    """1行に1人（毎週の差分が小さくなるように）"""
    rows = ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in data["rows"])
    sites = ",\n".join(json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in data["sites"])
    return f'{{"updated":{json.dumps(data["updated"])},\n"sites":[\n{sites}\n],\n"rows":[\n{rows}\n]}}\n'


def save_dataset(data, path=None):
    path = path or AGENCY_PATH
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(dump_dataset(data))
    os.replace(path + ".tmp", path)


def summary_lines(results, data):
    lines = ["### 所属事務所（週1回）", "", "| 事務所 | 一覧 | 読めたプロフィール | 結びついた人 | 読めなかったページ |", "|---|---|---|---|---|"]
    for site in SITES:
        report, rows = results.get(site["key"], ({"roster_ok": False, "read": 0, "found": 0, "errors": []}, []))
        lines.append(f"| {site['name']} | {'○' if report.get('roster_ok') else '×'} | {report.get('read', 0)}/{report.get('found', 0)} | "
                     f"{sum(1 for r in rows if r.get('fanza_name'))} | {len(report.get('errors', []))} |")
    lines += ["", f"保存した人数: {len(data['rows'])}"]
    return lines


def main(argv):
    if "--update" not in argv:
        print(__doc__)
        return 2
    today = jst_today()
    try:
        previous = load_previous()
    except (OSError, ValueError) as e:
        print(f"agencies.json が読めないので、上書きしません: {e}")
        return 1
    age = days_between(previous.get("updated"), today)
    if "--force" not in argv and age is not None and age < REFRESH_DAYS:
        print(f"所属事務所: 前に集めてから {age} 日なので、まだ集め直しません（{REFRESH_DAYS} 日ごと）")
        return 0
    table = fanza_names()
    # 事務所ごとに同時に読む（それぞれのサイトへは2秒ずつ間をあける。全部を順番に読むと40分ほどかかったため）
    with ThreadPoolExecutor(max_workers=len(SITES)) as pool:
        futures = {site["key"]: pool.submit(collect_site, site, table) for site in SITES}
    results = {}
    for key, f in futures.items():
        try:
            results[key] = f.result()
        except Exception as e:  # noqa: BLE001 1つの事務所の思わぬ失敗で、ほかの事務所の結果を捨てない（その事務所は前の情報を残す）
            results[key] = ({"roster_ok": False, "read": 0, "found": 0, "errors": [f"{type(e).__name__}: {e}"[:200]]}, [])
    for site in SITES:
        report, rows = results[site["key"]]
        print(f"{site['name']}: 一覧{'○' if report['roster_ok'] else '×'} プロフィール{report['read']}/{report['found']} 結びついた人{sum(1 for r in rows if r['fanza_name'])}")
    data = build_dataset(results, previous, today)
    save_dataset(data)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(summary_lines(results, data)) + "\n")
    print(f"所属事務所: {len(data['rows'])}人を保存しました")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
