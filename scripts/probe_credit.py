#!/usr/bin/env python3
"""作業用: DMMアフィリエイト公式のAPIのページから、クレジット表示の決まりと規定のHTMLを読む（数ページだけ。読むだけ）。main には入れない。"""
import html, re, urllib.request, urllib.parse
def note(t, s):
    s = str(s).replace("\n", " ⏎ ").replace("%", "%25"); print(f"::notice title={t}::{s[:3800]}", flush=True)
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ja"}), timeout=30) as r:
        return r.geturl(), r.read().decode("utf-8", "replace")
final, raw = get("https://affiliate.dmm.com/api/")
note("top", (final, raw[:3300]))
# ページの中のリンクとスクリプト
links = sorted(set(re.findall(r'(?:href|src)="([^"]+)"', raw)))
note("links", links[:80])
found = []
for u in links:
    full = urllib.parse.urljoin(final, u)
    if "dmm.com" not in full or not re.search(r"api|credit|guide|rule|term", full, re.I) or full.endswith((".css", ".png", ".gif", ".jpg", ".ico")):
        continue
    try:
        f2, body = get(full)
    except Exception as e:
        continue
    if "クレジット" in body or "Powered by" in body or "WEB SERVICE" in body:
        found.append(f2)
        k = body.find("クレジット")
        note("page", (f2, len(body)))
        note("near", body[max(0, k - 200):k + 3000])
        sn = set(re.findall(r"(?:&lt;|<)a[^\n]{0,300}?(?:Powered by|WEB SERVICE|web_service|Webサービス)[^\n]{0,300}?(?:&lt;|<)/a(?:&gt;|>)", body))
        note("snippets", [html.unescape(x) for x in list(sn)[:8]])
        break
note("found", found)
