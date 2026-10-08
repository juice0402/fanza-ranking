#!/usr/bin/env python3
"""下調べ用（このブランチだけ）その4: 同人の画像の別の置き場所（pics.dmm.co.jp）で同じ画像が読めるか"""
import json
import os
import re
import urllib.request

lines = []
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"


def say(t=""):
    print(t)
    lines.append(t)


def get(url):
    h = {"User-Agent": UA, "Accept": "image/*", "Sec-Fetch-Dest": "image", "Sec-Fetch-Site": "cross-site"}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=20) as r:
            body = r.read(600000)
            return r.status, len(body), r.headers.get("content-type"), r.geturl(), body[:4]
    except Exception as e:  # noqa: BLE001
        return type(e).__name__, 0, str(e)[:60], url, b""


def main():
    u = json.load(open(os.path.join(os.path.dirname(__file__), "probe_urls.json")))
    say("## 同人の表紙: doujin-assets と pics.dmm.co.jp の同じ場所")
    for url in u["covers"]:
        a = get(url)
        alt = url.replace("https://doujin-assets.dmm.co.jp/", "https://pics.dmm.co.jp/")
        b = get(alt)
        say(f"- {re.sub(r'[0-9]{3,}', '#', url[-48:])}: assets={a[0]} {a[1]}B / pics={b[0]} {b[1]}B {b[2]} 最終={re.sub(r'[0-9]{3,}', '#', str(b[3])[-50:])} 同じ中身={a[1] == b[1] and a[1] > 0}")
    say("## 同人のサンプル画像: 同じ")
    for url in u["samples"]:
        a = get(url)
        alt = url.replace("https://doujin-assets.dmm.co.jp/", "https://pics.dmm.co.jp/")
        b = get(alt)
        say(f"- {re.sub(r'[0-9]{3,}', '#', url[-48:])}: assets={a[0]} {a[1]}B / pics={b[0]} {b[1]}B {b[2]} 同じ中身={a[1] == b[1] and a[1] > 0}")
    if os.environ.get("GITHUB_ACTIONS"):
        secs = []
        for t in lines:
            if t.startswith("## ") or not secs:
                secs.append([t])
            else:
                secs[-1].append(t)
        for b in secs[:10]:
            body = "\n".join(b[1:]).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::notice title={b[0].lstrip('# ')[:100]}::{body}")


if __name__ == "__main__":
    main()
