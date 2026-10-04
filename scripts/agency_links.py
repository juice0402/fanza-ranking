"""所属事務所の公式サイトから、所属女優の「所属事務所の名前・X・Instagram」を集める（見本づくり用。2026-10-05）。

運営者の希望「所属を、所属先の公式的な情報から反映できないか。そこにTwitterやインスタのリンクがあったら確実な情報として」。
まずは見本で確かめる（運営者の判断）ので、いまはサイトには載せず、集めた結果を JSON に書き出すだけ。

決まり:
- 読むのは、robots.txt で止められていない、所属女優の一覧とプロフィールのページだけ（urllib.robotparser で確かめる）。
- 相手のサイトに負担をかけないよう、1回ずつ間をあける（INTERVAL_SEC）。
- 保存するのは「事務所・名前・プロフィールのURL・X・Instagram」だけ。生年月日・出身地・血液型・画像・文章は保存しない。
- FANZA の名前と照らし合わせるのは、空白を除いて完全に一致し、FANZA 側に同じ名前が1人だけのときだけ（推測で選ばない）。
- Python の標準ライブラリだけ。

使い方: python scripts/agency_links.py 出力先.json
"""
import html as htmllib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timedelta, timezone

USER_AGENT = "Mozilla/5.0 (compatible; fanza-ranking-bot/1.0; +https://fanza-ranking.pages.dev/)"
INTERVAL_SEC = float(os.environ.get("AGENCY_INTERVAL_SEC", "2"))
MAX_PROFILES = int(os.environ.get("AGENCY_MAX_PROFILES", "500"))  # 1つの事務所で読むプロフィールの上限
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "site", "src", "data")

# 事務所ごとの、一覧のページと、プロフィールのページのURLの形（2026-10-05 に下調べ。robots.txt で止められていない・プロフィールにSNSのリンクがある所）
SITES = [
    {"key": "tpowers", "name": "ティーパワーズ", "roster": ["https://www.t-powers.co.jp/talent/"],
     "profile": r"^https://www\.t-powers\.co\.jp/talent/[A-Za-z0-9_-]+/?$"},
    {"key": "mines", "name": "マインズ", "roster": ["https://mines-pro.jp/model/"],
     "profile": r"^https://mines-pro\.jp/model/\d+/?$"},
    {"key": "bambi", "name": "バンビプロモーション", "roster": ["https://bambi.ne.jp/models.html"],
     "profile": r"^https://bambi\.ne\.jp/model\.php\?id=\d+$"},
    {"key": "soagent", "name": "SO MODELAGENT", "roster": ["https://so-agent.jp/model.php"],
     "profile": r"^https://so-agent\.jp/model/[A-Za-z0-9_-]+/?$"},
    {"key": "alive", "name": "プロダクションALIVE", "roster": ["https://alive-pro.tokyo/model"],
     "profile": r"^https://alive-pro\.tokyo/model/[A-Za-z0-9_-]+/?$"},
]

X_LINK = re.compile(r"^https?://(?:www\.|mobile\.)?(?:twitter|x)\.com/(?:#!/)?@?([A-Za-z0-9_]{1,15})/?(?:\?.*)?$", re.I)
IG_LINK = re.compile(r"^https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]{1,30})/?(?:\?.*)?$", re.I)
X_RESERVED = {"share", "intent", "home", "search", "hashtag", "i", "login", "signup", "explore", "settings", "privacy", "tos"}
IG_RESERVED = {"p", "reel", "reels", "explore", "accounts", "stories", "tv", "about", "legal", "developer"}

_robots = {}
_last = [0.0]


def jst_today():
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")


def allowed(url):
    """robots.txt で止められていないか（robots.txt が無い・読めない（404）ときは止められていない、と同じあつかい）"""
    parts = urllib.parse.urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            body = fetch_raw(base + "/robots.txt", check_robots=False)
            rp.parse(body.splitlines())
        except urllib.error.HTTPError as e:
            rp.parse([] if e.code in (404, 410) else ["User-agent: *", "Disallow: /"])  # 401/403/5xx は、念のため読まない
        except (urllib.error.URLError, OSError, ValueError):
            rp.parse(["User-agent: *", "Disallow: /"])
        _robots[base] = rp
    return _robots[base].can_fetch(USER_AGENT, url)


def fetch_raw(url, check_robots=True):
    if check_robots and not allowed(url):
        raise PermissionError(f"robots.txt で止められている: {url}")
    wait = INTERVAL_SEC - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ja"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            raw = res.read(3_000_000)
            charset = res.headers.get_content_charset() or ""
    finally:
        _last[0] = time.time()
    if not charset:
        m = re.search(rb'charset=["\']?([A-Za-z0-9_-]+)', raw[:4000])
        charset = m.group(1).decode() if m else "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def links(page_html, base_url):
    """ページの中のリンク（絶対URL）と、その文字（タグを外したもの）"""
    out = []
    for m in re.finditer(r"<a\b[^>]*?\bhref\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a>", page_html, re.I | re.S):
        href = htmllib.unescape(m.group(2)).strip()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        out.append((urllib.parse.urljoin(base_url, href), text_of(m.group(3))))
    return out


def text_of(fragment):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def meta_content(page_html, prop):
    m = re.search(r"<meta\b[^>]*(?:property|name)\s*=\s*[\"']%s[\"'][^>]*>" % re.escape(prop), page_html, re.I)
    if not m:
        return ""
    c = re.search(r"\bcontent\s*=\s*([\"'])(.*?)\1", m.group(0), re.I | re.S)
    return htmllib.unescape(c.group(2)).strip() if c else ""


def name_candidates(page_html):
    """プロフィールのページから、名前らしい文字の候補（og:title・h1・h2・title）。照らし合わせは、このどれかが FANZA の名前と合うかで見る"""
    cands = [meta_content(page_html, "og:title")]
    for tag in ("h1", "h2", "h3"):
        cands += [text_of(x) for x in re.findall(r"<%s\b[^>]*>(.*?)</%s>" % (tag, tag), page_html, re.I | re.S)[:4]]
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


def norm_name(name):
    """名前の照らし合わせ用（NFKC・空白と中点を除く）"""
    s = unicodedata.normalize("NFKC", str(name or ""))
    return re.sub(r"[\s・･]", "", s)


def sns_links(page_html, base_url):
    xs, igs = [], []
    for url, _ in links(page_html, base_url):
        m = X_LINK.match(url)
        if m and m.group(1).lower() not in X_RESERVED:
            handle = m.group(1)
            if handle.lower() not in [h.lower() for h in xs]:
                xs.append(handle)
            continue
        m = IG_LINK.match(url)
        if m and m.group(1).lower() not in IG_RESERVED:
            handle = m.group(1).rstrip(".")
            if handle.lower() not in [h.lower() for h in igs]:
                igs.append(handle)
    return xs, igs


def fanza_names():
    """FANZA 公式の名前（女優検索の名簿・出演者プロフィール）→ { 照らし合わせ用の名前: [(名前, id)] }"""
    table = {}

    def add(name, id_):
        key = norm_name(name)
        if key:
            rows = table.setdefault(key, [])
            if (name, id_) not in rows and not any(r[1] == id_ and id_ for r in rows):
                rows.append((name, id_))

    try:
        for r in json.load(open(os.path.join(DATA_DIR, "actress_directory.json"), encoding="utf-8")).get("rows", []):
            add(r.get("name"), str(r.get("id") or ""))
    except (OSError, ValueError):
        pass
    try:
        for r in json.load(open(os.path.join(DATA_DIR, "actresses.json"), encoding="utf-8")).get("actresses", []):
            add(r.get("name"), str(r.get("id") or ""))
    except (OSError, ValueError):
        pass
    return table


def collect_site(site, table):
    report = {"key": site["key"], "name": site["name"], "roster_pages": 0, "profiles_found": 0, "profiles_read": 0, "errors": [], "site_wide": {}}
    rows = []
    pattern = re.compile(site["profile"])
    found = []
    for roster in site["roster"]:
        try:
            page = fetch_raw(roster)
            report["roster_pages"] += 1
        except (urllib.error.URLError, OSError, ValueError, PermissionError) as e:
            report["errors"].append(f"一覧: {type(e).__name__}: {e}"[:200])
            continue
        for url, label in links(page, roster):
            url = url.split("#")[0]
            if pattern.match(url) and url not in [f[0] for f in found]:
                found.append((url, label))
    report["profiles_found"] = len(found)
    pages = []
    for url, label in found[:MAX_PROFILES]:
        try:
            page = fetch_raw(url)
        except (urllib.error.URLError, OSError, ValueError, PermissionError) as e:
            report["errors"].append(f"{url}: {type(e).__name__}: {e}"[:200])
            continue
        report["profiles_read"] += 1
        xs, igs = sns_links(page, url)
        pages.append((url, label, name_candidates(page), xs, igs))
    # どのページにも出てくるSNS（事務所そのもののアカウント）は、本人のものではないので外す
    count_x, count_ig = {}, {}
    for _, _, _, xs, igs in pages:
        for h in xs:
            count_x[h.lower()] = count_x.get(h.lower(), 0) + 1
        for h in igs:
            count_ig[h.lower()] = count_ig.get(h.lower(), 0) + 1
    limit = max(3, len(pages) // 3)
    wide_x = {h for h, n in count_x.items() if n >= limit}
    wide_ig = {h for h, n in count_ig.items() if n >= limit}
    report["site_wide"] = {"x": sorted(wide_x), "instagram": sorted(wide_ig)}
    for url, label, cands, xs, igs in pages:
        xs = [h for h in xs if h.lower() not in wide_x]
        igs = [h for h in igs if h.lower() not in wide_ig]
        tried = ([label] if label else []) + cands
        match, how = None, "FANZAの名前と合わない"
        for cand in tried:
            for piece in [cand] + re.split(r"\s+", cand):
                hits = table.get(norm_name(piece), [])
                if len(hits) == 1:
                    match, how = hits[0], "一致"
                    break
                if len(hits) > 1:
                    how = "FANZAに同じ名前が何人もいる"
            if match:
                break
        rows.append({
            "agency": site["name"], "profile": url, "label": label[:40], "candidates": cands[:6],
            "x": xs[:2], "instagram": igs[:2],
            "fanza_name": match[0] if match else "", "fanza_id": match[1] if match else "", "match": how,
        })
    return report, rows


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "agency_sample.json"
    table = fanza_names()
    result = {"generated": jst_today(), "fanza_names": len(table), "sites": [], "rows": []}
    for site in SITES:
        report, rows = collect_site(site, table)
        result["sites"].append(report)
        result["rows"].extend(rows)
        print(f"{site['name']}: 一覧{report['roster_pages']} プロフィール{report['profiles_read']}/{report['profiles_found']} 一致{sum(1 for r in rows if r['fanza_name'])} エラー{len(report['errors'])}")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
