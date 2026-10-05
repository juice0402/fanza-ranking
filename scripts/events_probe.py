"""イベント情報の読み取り方を決めるための下調べ（2026-10-05。運営者の「本番に作る」）。
決めたページ（所属事務所の公式サイトのイベントのページ・お知らせのRSS）から、はじめの数件の「HTMLの形」を取り出す（読み取りの作りを決めるため。作業用ブランチにだけ置く）。
使い方: python scripts/events_probe.py discovery/events_probe.json
"""
import json
import os
import re
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agency_links as A  # noqa: E402

SOURCES = [
    ("tpowers", "https://www.t-powers.co.jp/event/"),
    ("capsule", "https://capsule.bz/category/event/"),
    ("capsule_feed", "https://capsule.bz/feed/"),
    ("esflat_feed", "http://www.style-1.jp/feed/"),
    ("life", "https://life-promotion.com/blog/event/"),
    ("cmore", "https://cmore.jp/official/event.html"),
]
DATE = re.compile(r"(20\d{2})\s*[./年-]\s*(\d{1,2})\s*[./月-]\s*(\d{1,2})")


def main(argv):
    out = argv[1] if len(argv) > 1 else "discovery/events_probe.json"
    res = {}
    for key, url in SOURCES:
        try:
            text = A.fetch_raw(url)
        except (PermissionError, urllib.error.URLError, OSError, ValueError) as e:
            res[key] = {"url": url, "error": str(e)[:100]}
            continue
        entry = {"url": url, "length": len(text), "snippets": []}
        if "feed" in key:
            for block in re.findall(r"<item\b[\s\S]*?</item>", text, re.I)[:3]:
                block = re.sub(r"<content:encoded>[\s\S]*?</content:encoded>", "<content:encoded>…</content:encoded>", block)
                entry["snippets"].append(block[:1500])
        else:
            used = 0
            for m in re.finditer(r"<a\b[^>]*?\bhref\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a>", text, re.I | re.S):
                window = text[max(0, m.start() - 500):m.end() + 500]
                if not DATE.search(A.text_of(window)) and not re.search(r"\d{1,2}/\d{1,2}", A.text_of(m.group(3))):
                    continue
                if used and entry["snippets"] and m.start() - used < 300:
                    continue
                entry["snippets"].append(window[:1600])
                used = m.start()
                if len(entry["snippets"]) >= 4:
                    break
        res[key] = entry
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv)
