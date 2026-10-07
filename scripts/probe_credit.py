#!/usr/bin/env python3
"""作業用: DMMアフィリエイト公式のAPIのページから、クレジット表示の決まりと規定のHTMLを読む（1ページだけ。読むだけ）。main には入れない。"""
import html, re, urllib.request
def note(t, s):
    s = str(s).replace("\n", " ⏎ ").replace("%", "%25"); print(f"::notice title={t}::{s[:3800]}", flush=True)
for url in ("https://affiliate.dmm.com/api/",):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
        raw = r.read().decode("utf-8", "replace")
    note("len", (url, len(raw)))
    i = raw.find("クレジット")
    hits = [m.start() for m in re.finditer("クレジット", raw)]
    note("hits", hits[:20])
    # クレジットのあたり（タグごと）
    for n, k in enumerate(hits[:3]):
        note(f"near{n}", raw[max(0, k - 300):k + 2500])
    # 規定のHTMLらしいもの（エスケープされた <a ...>Powered by など）
    snippets = set(re.findall(r"(?:&lt;|<)a[^\n]{0,300}?(?:Powered by|WEB SERVICE|web_service|Webサービス)[^\n]{0,300}?(?:&lt;|<)/a(?:&gt;|>)", raw))
    note("snippets", [html.unescape(s) for s in list(snippets)[:8]])
