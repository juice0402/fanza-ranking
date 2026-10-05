"""所属事務所の公式サイトを探して、使えるかを調べる（下調べ用。2026-10-05。運営者の「もっとたくさんの事務所と紐付けたい」）。

1. 候補: Wikipedia（日本語版）の「日本プロダクション協会」の加盟社と、AVプロダクションの分類にある会社の記事から、
   公式サイトのURL（Wikidata の「公式ウェブサイト」か、記事の中の公式サイトのリンク）を集める。下調べで分かっていた会社も足す。
2. 公式サイトごとに: robots.txt で止められていないか・トップページから所属女優の一覧らしいページを探し、
   プロフィールへのリンクの形・人数・FANZA の名前と完全に同じ名前の数・プロフィールにSNSがあるか（5人分）を調べる。
3. 結果を JSON に書く（名前・URL・数だけ。相手のページの文章や画像は保存しない）。

使い方: python scripts/agency_discover.py 出力先.json
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agency_links as A  # noqa: E402

WIKI_API = "https://ja.wikipedia.org/w/api.php"
SEED_PAGES = ["日本プロダクション協会"]
SEED_CATEGORIES = ["Category:日本のAVプロダクション", "Category:AVプロダクション", "Category:アダルトビデオのプロダクション", "Category:日本の芸能事務所 (アダルト)"]
# 下調べ（2026-10-05）で名前が出ていた会社（すでに使っている5つは除く）
EXTRA = [
    ("C-more ENTERTAINMENT", "https://cmore.work/"),
    ("Bstar", "https://bstar-pro.com/"),
    ("ビーダッシュプロモーション", "https://modelz.tv/"),
    ("LINX", "https://teamlinx.pro/"),
    ("エスフラート", "https://www.style-1.jp/"),
    ("アロッサ", "https://arrowsweb.net/"),
]
KEYWORDS = re.compile(r"(talent|model|actress|profile|member|cast|girls|lineup|所属|モデル|タレント|女優|キャスト|プロフィール|在籍)", re.I)
SKIP_HOSTS = ("wikipedia.org", "wikidata.org", "twitter.com", "x.com", "instagram.com", "youtube.com", "facebook.com", "tiktok.com",
              "dmm.co.jp", "fanza.co.jp", "amazon.co.jp", "google.com", "line.me", "ameblo.jp", "fc2.com")


def wiki(params):
    q = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    return json.loads(A.fetch_raw(f"{WIKI_API}?{q}", check_robots=False))


def wikidata_site(title):
    """記事 → Wikidata の「公式ウェブサイト」（P856）"""
    try:
        pages = wiki({"action": "query", "prop": "pageprops", "titles": title, "redirects": "1"}).get("query", {}).get("pages", [])
        qid = (pages[0].get("pageprops") or {}).get("wikibase_item") if pages else None
        if not qid:
            return ""
        data = json.loads(A.fetch_raw(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json", check_robots=False))
        claims = data["entities"][qid].get("claims", {}).get("P856", [])
        for c in claims:
            v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(v, str) and v.startswith("http"):
                return v
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError):
        pass
    return ""


def article_site(title):
    """記事の中の公式サイトのリンク（{{Official website|…}}・| URL = …・外部リンクの「公式」）"""
    try:
        text = wiki({"action": "parse", "page": title, "prop": "wikitext", "redirects": "1"}).get("parse", {}).get("wikitext", "")
    except (urllib.error.URLError, OSError, ValueError):
        return ""
    for pat in (r"\{\{\s*(?:Official website|公式サイト)\s*\|\s*(https?://[^|}\s]+)", r"\|\s*(?:URL|url|公式サイト|ウェブサイト)\s*=\s*(?:\[)?(https?://[^\s|\]}]+)",
                r"\*\s*\[(https?://[^\s\]]+)[^\]]*公式"):
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return ""


def candidates():
    titles = []
    for page in SEED_PAGES:
        try:
            text = wiki({"action": "parse", "page": page, "prop": "wikitext", "redirects": "1"}).get("parse", {}).get("wikitext", "")
        except (urllib.error.URLError, OSError, ValueError):
            text = ""
        for m in re.finditer(r"\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]", text):
            t = m.group(1).strip()
            if not t.startswith(("Category:", "ファイル:", "File:", "Wikipedia:")) and t not in titles:
                titles.append(t)
    for cat in SEED_CATEGORIES:
        try:
            members = wiki({"action": "query", "list": "categorymembers", "cmtitle": cat, "cmlimit": "200", "cmtype": "page"}).get("query", {}).get("categorymembers", [])
        except (urllib.error.URLError, OSError, ValueError):
            members = []
        for mbr in members:
            if mbr.get("title") not in titles:
                titles.append(mbr["title"])
    out = []
    for t in titles[:150]:
        site = wikidata_site(t) or article_site(t)
        if site:
            out.append((t, site))
    seen = {urllib.parse.urlsplit(u).netloc.replace("www.", "") for _, u in out}
    for name, url in EXTRA:
        if urllib.parse.urlsplit(url).netloc.replace("www.", "") not in seen:
            out.append((name, url))
    return titles, out


def pattern_of(url):
    """URL → 形（最後の部分を * に。?id=123 は ?id=*）"""
    p = urllib.parse.urlsplit(url)
    path = re.sub(r"/[^/]+/?$", "/*", p.path) if p.path not in ("", "/") else p.path
    query = re.sub(r"=[^&]*", "=*", p.query)
    return f"{p.scheme}://{p.netloc}{path}" + (f"?{query}" if query else "")


def best_group(page_html, page_url, table):
    host = urllib.parse.urlsplit(page_url).netloc
    groups = {}
    for url, label in A.links(page_html, page_url):
        url = url.split("#")[0]
        if urllib.parse.urlsplit(url).netloc != host or url.rstrip("/") == page_url.rstrip("/"):
            continue
        g = groups.setdefault(pattern_of(url), {})
        if url not in g:
            g[url] = label
    best = None
    for pat, links_ in groups.items():
        cjk = [lb for lb in links_.values() if A.CJK.search(lb or "") and len(lb) <= 30]
        if len(cjk) < 5:
            continue
        names = [A.agency_name({}, lb, []) for lb in links_.values()]
        matched = [n for n in names if n and A.lookup(table, n)[0]]
        score = (len(matched), len(cjk))
        if not best or score > best["score"]:
            best = {"pattern": pat, "links": list(links_.items()), "cjk": len(cjk), "matched": len(matched), "score": score,
                    "sample": [lb for lb in links_.values()][:8]}
    return best


def probe(name, url, table):
    rep = {"name": name, "url": url, "robots_ok": None, "home_ok": False, "gate_suspect": False, "roster": "", "pattern": "", "links": 0,
           "cjk_labels": 0, "fanza_matched": 0, "sample": [], "profiles_checked": 0, "with_x": 0, "with_ig": 0, "error": ""}
    try:
        rep["robots_ok"] = A.allowed(url)
        if not rep["robots_ok"]:
            return rep
        home = A.fetch_raw(url)
        rep["home_ok"] = True
        rep["gate_suspect"] = len(A.links(home, url)) < 8 and bool(re.search(r"18歳|年齢確認|ENTER|enter", home))
        host = urllib.parse.urlsplit(url).netloc
        cands = [url]
        for u, label in A.links(home, url):
            if urllib.parse.urlsplit(u).netloc == host and (KEYWORDS.search(urllib.parse.urlsplit(u).path) or KEYWORDS.search(label or "")) and u.split("#")[0] not in cands:
                cands.append(u.split("#")[0])
        best = None
        for c in cands[:5]:
            try:
                page = home if c == url else (A.fetch_raw(c) if A.allowed(c) else "")
            except (urllib.error.URLError, OSError, ValueError, PermissionError):
                continue
            g = best_group(page, c, table)
            if g and (not best or g["score"] > best["score"]):
                best = {**g, "roster": c}
        if not best:
            return rep
        rep.update({"roster": best["roster"], "pattern": best["pattern"], "links": len(best["links"]), "cjk_labels": best["cjk"],
                    "fanza_matched": best["matched"], "sample": best["sample"]})
        pages = []
        for u, label in best["links"][:5]:
            try:
                if A.allowed(u):
                    pages.append(A.sns_links(A.fetch_raw(u), u))
            except (urllib.error.URLError, OSError, ValueError, PermissionError):
                continue
        rep["profiles_checked"] = len(pages)
        rep["with_x"] = sum(1 for xs, _ in pages if xs)
        rep["with_ig"] = sum(1 for _, igs in pages if igs)
    except (urllib.error.URLError, OSError, ValueError, PermissionError) as e:
        rep["error"] = f"{type(e).__name__}: {e}"[:200]
    return rep


def groups_of(page_html, page_url, table):
    """ページの中の、同じ形のリンクのまとまり（日本語の名前らしい文字が5つ以上のもの）→ [{pattern, count, matched, urls}]"""
    host = urllib.parse.urlsplit(page_url).netloc
    groups = {}
    for url, label in A.links(page_html, page_url):
        url = url.split("#")[0]
        if urllib.parse.urlsplit(url).netloc != host:
            continue
        groups.setdefault(pattern_of(url), {}).setdefault(url, label)
    out = []
    for pat, links_ in groups.items():
        cjk = [lb for lb in links_.values() if A.CJK.search(lb or "") and len(lb) <= 30]
        names = [A.agency_name({}, lb, []) for lb in links_.values()]
        matched = [n for n in names if n and A.lookup(table, n)[0]]
        if len(cjk) >= 5 or len(matched) >= 3:
            out.append({"pattern": pat, "count": len(links_), "cjk": len(cjk), "matched": len(matched), "urls": list(links_.items())})
    return sorted(out, key=lambda g: (-g["matched"], -g["cjk"]))


def deep(start, table, max_pages=8):
    """入口のURLから2段まで（キーワードのあるリンクだけ）たどって、名前のリンクのまとまりを探す。いちばん良いまとまりの、プロフィール6人分のSNSとタイトルも"""
    rep = {"start": start, "robots_ok": A.allowed(start), "pages": [], "groups": [], "profiles": []}
    if not rep["robots_ok"]:
        return rep
    host = urllib.parse.urlsplit(start).netloc
    queue, seen = [start], set()
    while queue and len(seen) < max_pages:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        try:
            if not A.allowed(u):
                continue
            page = A.fetch_raw(u)
        except (urllib.error.URLError, OSError, ValueError, PermissionError) as e:
            rep["pages"].append({"url": u, "error": f"{type(e).__name__}"})
            continue
        t = re.search(r"<title\b[^>]*>(.*?)</title>", page, re.I | re.S)
        rep["pages"].append({"url": u, "title": A.text_of(t.group(1))[:60] if t else "", "links": len(A.links(page, u))})
        for g in groups_of(page, u, table):
            rep["groups"].append({**{k: v for k, v in g.items() if k != "urls"}, "on": u, "sample": [lb for _, lb in g["urls"][:6]], "sample_urls": [x for x, _ in g["urls"][:3]], "_urls": g["urls"]})
        if u == start or len(seen) <= 3:
            for v, label in A.links(page, u):
                v = v.split("#")[0]
                if urllib.parse.urlsplit(v).netloc == host and v not in seen and (KEYWORDS.search(urllib.parse.urlsplit(v).path) or KEYWORDS.search(label or "")):
                    queue.append(v)
    rep["groups"].sort(key=lambda g: (-g["matched"], -g["cjk"]))
    if rep["groups"]:
        best = rep["groups"][0]
        pages = []
        for v, label in best["_urls"][:6]:
            try:
                if A.allowed(v):
                    page = A.fetch_raw(v)
                    t = re.search(r"<title\b[^>]*>(.*?)</title>", page, re.I | re.S)
                    xs, igs = A.sns_links(page, v)
                    pages.append({"url": v, "label": label, "title": A.text_of(t.group(1))[:60] if t else "", "x": xs[:4], "ig": igs[:4], "h": A.name_candidates(page)[:4]})
            except (urllib.error.URLError, OSError, ValueError, PermissionError):
                continue
        rep["profiles"] = pages
    for g in rep["groups"]:
        g.pop("_urls", None)
    rep["groups"] = rep["groups"][:6]
    return rep


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--deep":
        table = A.fanza_names()
        out = sys.argv[2]
        reports = []
        for start in sys.argv[3:]:
            rep = deep(start, table)
            reports.append(rep)
            g = rep["groups"][0] if rep["groups"] else {}
            print(f"{start}: robots={rep['robots_ok']} best={g.get('pattern')} matched={g.get('matched')}")
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"generated": A.jst_today(), "reports": reports}, f, ensure_ascii=False, indent=1)
            f.write("\n")
        return
    out = sys.argv[1] if len(sys.argv) > 1 else "agency_discover.json"
    table = A.fanza_names()
    titles, cands = candidates()
    known = {urllib.parse.urlsplit(s["url"]).netloc for s in A.SITES}
    reports = []
    for name, url in cands:
        if urllib.parse.urlsplit(url).netloc in known or any(h in urllib.parse.urlsplit(url).netloc for h in SKIP_HOSTS):
            continue
        rep = probe(name, url, table)
        reports.append(rep)
        print(f"{name} {url}: robots={rep['robots_ok']} roster={rep['roster']} links={rep['links']} matched={rep['fanza_matched']} x={rep['with_x']}/{rep['profiles_checked']}")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"generated": A.jst_today(), "wiki_titles": titles, "candidates": cands, "reports": reports}, f, ensure_ascii=False, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
