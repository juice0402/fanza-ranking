#!/usr/bin/env python3
"""下調べ用（このブランチだけ）その3: 同人・ゲームの画像が、ページから読めるか（Referer ごとの答え）と、プレビューのHTMLの img"""
import os
import re
import urllib.request

lines = []


def say(t=""):
    print(t)
    lines.append(t)


IMGS = {
    "動画 pl": "https://pics.dmm.co.jp/digital/video/ssis00001/ssis00001pl.jpg",
    "ゲーム pl": "https://pics.dmm.co.jp/digital/pcgame/7color_0003/7color_0003pl.jpg",
    "ゲーム ps": "https://pics.dmm.co.jp/digital/pcgame/7color_0003/7color_0003ps.jpg",
    "ゲーム jp-001": "https://pics.dmm.co.jp/digital/pcgame/7color_0003/7color_0003jp-001.jpg",
    "同人 pl": "https://doujin-assets.dmm.co.jp/digital/comic/d_111223/d_111223pl.jpg",
    "同人 jp-001": "https://doujin-assets.dmm.co.jp/digital/comic/d_111223/d_111223jp-001.jpg",
}
REFS = {"なし": None, "本番": "https://fanza-ranking.pages.dev/", "プレビュー": "https://claude-doujin-game.fanza-ranking.pages.dev/doujin/"}
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"


def get(url, ref):
    h = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    if ref:
        h["Referer"] = ref
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=20) as r:
            body = r.read(400000)
            return f"{r.status} {r.headers.get('content-type')} {len(body)}B 最終={re.sub(r'[0-9]+', '#', r.geturl())[-60:]}"
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {str(e)[:80]}"


def headers_of(url, extra):
    h = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8", "Referer": "https://claude-doujin-game.fanza-ranking.pages.dev/doujin/",
         "Sec-Fetch-Dest": "image", "Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Site": "cross-site", "Accept-Language": "ja-JP,ja;q=0.9"}
    h.update(extra)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=20) as r:
            body = r.read(400000)
            keep = {k: v for k, v in r.headers.items() if k.lower().startswith(("cross-origin", "content-security", "x-frame", "access-control", "timing", "vary", "content-type", "set-cookie", "x-cache", "server", "via", "cache-control"))}
            return f"{r.status} {len(body)}B 最終={re.sub(r'[0-9]+', '#', r.geturl())[-50:]} ヘッダー={keep}"
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {str(e)[:120]}"


def browser_check():
    """GitHub の Chrome でプレビューを開いて、画像が読めているかを数える"""
    import json as _j
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        subprocess.run(["npm", "i", "--no-save", "--prefix", here, "puppeteer-core@23"], check=True, capture_output=True, timeout=240)
        r = subprocess.run(["node", os.path.join(here, "probe_browser.mjs")], capture_output=True, text=True, timeout=600, cwd=here)
        rows = _j.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else [r.stderr[-300:]]
    except Exception as e:  # noqa: BLE001
        rows = [f"{type(e).__name__}: {str(e)[:200]}"]
    say("## 本物のブラウザ（Chrome）で、画像が読めているか")
    for row in rows:
        say("- " + row)


def main():
    browser_check()
    say("## ブラウザと同じ形の問い合わせ（Sec-Fetch・日本語）での答えとヘッダー")
    for name, url in IMGS.items():
        say(f"- {name}: {headers_of(url, {})}")
    say("## 画像を、Referer ごとに読む")
    for name, url in IMGS.items():
        for rn, ref in REFS.items():
            say(f"- {name}（Referer {rn}）: {get(url, ref)}")
    say("## プレビューのHTMLの img")
    for path in ("/doujin/", "/game/", "/"):
        try:
            with urllib.request.urlopen(urllib.request.Request("https://claude-doujin-game.fanza-ranking.pages.dev" + path, headers={"User-Agent": UA}), timeout=30) as r:
                html = r.read().decode("utf-8", "replace")
            imgs = re.findall(r"<(?:img|source)[^>]*>", html)
            say(f"- {path}: img/source {len(imgs)}個。先頭3つ: " + " | ".join(i[:220] for i in imgs[:3]))
            cov = re.findall(r'<a class="item-cover[^"]*"[^>]*>.{0,400}', html, re.S)[:1]
            say(f"  表紙の枠の例: {cov[0][:400] if cov else 'なし'}")
        except Exception as e:  # noqa: BLE001
            say(f"- {path}: {type(e).__name__}: {str(e)[:100]}")
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
