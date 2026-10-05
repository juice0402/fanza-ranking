"""「FANZA セール」「FANZA 情報」などで上位に出るページの作りの下調べ（2026-10-06。運営者の希望「SEOを上位に。上に来ている人は、どんな部分を
頑張って、どんなブログを作っているのか」）。作業用ブランチにだけ置く。robots.txt を守り、1ページずつ読む。
保存するのは、ページの形（タイトル・見出し・文字数・表の数・更新日・構造化データの種類・リンクの数など）だけ（本文は保存しない）。"""
import html as htmllib
import json
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

UA = "Mozilla/5.0 (compatible; fanza-ranking-bot/1.0; +https://fanza-ranking.pages.dev/)"
URLS = [
    "https://dmmtv-navi.com/fanza-sale/",
    "https://dmmtv-navi.com/10yen/",
    "https://erogumi.net/fanza-sale-guide/",
    "https://otoko-review.com/fanza-sale-schedule-matome/",
    "https://yoru-salon.com/howto/fanza-sell/",
    "https://fanzafan.com/category/%E3%82%A2%E3%83%80%E3%83%AB%E3%83%88%E5%8B%95%E7%94%BB/%E3%82%BB%E3%83%BC%E3%83%AB%E6%83%85%E5%A0%B1/",
    "https://www.leawo.org/jp/tips/fanza-%E3%82%BB%E3%83%BC%E3%83%AB-1352.html",
    "https://netatopi.jp/article/2050447.html",
    "https://note.com/lucky_azalea6228/n/n3b2073f46413",
    "https://dmm-lover.com/fanza-coupon/",
    "https://www.areus.jp/column/fanza10-yen-sale-list-dmm-comparison-guide",
    "https://avdrifters.blog.jp/",
    "https://fanza-ranking.pages.dev/sale/",
    "https://fanza-ranking.pages.dev/",
]
_robots = {}


def allowed(url):
    p = urllib.parse.urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                rp.parse(r.read(300000).decode("utf-8", "replace").splitlines())
        except urllib.error.HTTPError as e:
            rp.parse([] if e.code in (404, 410) else ["User-agent: *", "Disallow: /"])
        except Exception:  # noqa: BLE001
            rp.parse(["User-agent: *", "Disallow: /"])
        _robots[base] = rp
    return _robots[base].can_fetch(UA, url)


def text_of(f):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", f or ""))).strip()


def analyze(url):
    if not allowed(url):
        return {"url": url, "skipped": "robots.txt"}
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read(4_000_000)
        cs = r.headers.get_content_charset() or "utf-8"
        status, final = r.status, r.geturl()
    page = raw.decode(cs, "replace")
    body = re.sub(r"<(script|style|noscript|svg)\b[\s\S]*?</\1>", " ", page, flags=re.I)
    main = re.search(r"<(article|main)\b[\s\S]*?</\1>", body, re.I)
    main_html = main.group(0) if main else body
    title = re.search(r"<title\b[^>]*>(.*?)</title>", page, re.I | re.S)
    desc = re.search(r'<meta\b[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)', page, re.I)
    heads = []
    for m in re.finditer(r"<(h[1-4])\b[^>]*>(.*?)</\1>", main_html, re.I | re.S):
        t = text_of(m.group(2))
        if t:
            heads.append(f"{m.group(1).lower()}: {t[:70]}")
    ld_types, dates, authors = [], {}, []
    for blk in re.findall(r'<script[^>]*application/ld\+json[^>]*>([\s\S]*?)</script>', page, re.I):
        for t in re.findall(r'"@type"\s*:\s*"([^"]+)"', blk):
            if t not in ld_types:
                ld_types.append(t)
        for k in ("datePublished", "dateModified"):
            m = re.search(r'"%s"\s*:\s*"([^"]+)"' % k, blk)
            if m:
                dates.setdefault(k, m.group(1))
        for a in re.findall(r'"author"\s*:\s*\{[^{}]*"name"\s*:\s*"([^"]+)"', blk):
            authors.append(a[:40])
    for k in ("article:published_time", "article:modified_time"):
        m = re.search(r'<meta\b[^>]*property=["\']%s["\'][^>]*content=["\']([^"\']+)' % k, page, re.I)
        if m:
            dates.setdefault(k, m.group(1))
    links = re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\']', main_html, re.I)
    host = urllib.parse.urlsplit(final).netloc
    ext = {}
    internal = 0
    for h in links:
        u = urllib.parse.urljoin(final, htmllib.unescape(h))
        n = urllib.parse.urlsplit(u).netloc
        if not n or n == host:
            internal += 1
        else:
            ext[n] = ext.get(n, 0) + 1
    txt = text_of(main_html)
    visible_dates = re.findall(r"(?:更新日?|最終更新|公開日|投稿日)[:：\s]*(20\d\d[年/.\-]\d{1,2}[月/.\-]\d{1,2})", txt)[:3]
    words = {w: txt.count(w) for w in ("目次", "よくある質問", "Q.", "Q&A", "まとめ", "体験", "元社員", "監修", "比較", "表", "注意", "PR", "広告", "アフィリエイト", "クーポン", "ポイント", "次回", "予想", "履歴", "年間", "カレンダー", "スケジュール", "ランキング", "おすすめ", "レビュー")}
    return {
        "url": url, "status": status, "final": final, "title": text_of(title.group(1))[:120] if title else "", "description": (desc.group(1)[:160] if desc else ""),
        "chars_main": len(txt), "headings_count": len(heads), "headings": heads[:45], "tables": len(re.findall(r"<table\b", main_html, re.I)),
        "images": len(re.findall(r"<img\b", main_html, re.I)), "list_items": len(re.findall(r"<li\b", main_html, re.I)),
        "ld_types": ld_types[:15], "dates": dates, "visible_dates": visible_dates, "authors": authors[:3],
        "internal_links": internal, "external_links": sorted(ext.items(), key=lambda kv: -kv[1])[:12], "words": {k: v for k, v in words.items() if v},
        "has_toc": bool(re.search(r"目次|toc|table-of-contents|ez-toc", main_html, re.I)), "has_faq_schema": "FAQPage" in ld_types,
        "comment_area": bool(re.search(r"comment-respond|コメントを残す|コメントする", page)),
    }


def main(argv):
    out = argv[1]
    res = []
    for u in URLS:
        try:
            res.append(analyze(u))
        except Exception:  # noqa: BLE001
            res.append({"url": u, "crash": traceback.format_exc()[-600:]})
        json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        time.sleep(2)


if __name__ == "__main__":
    main(sys.argv)
