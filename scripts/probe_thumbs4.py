#!/usr/bin/env python3
"""作業用: 画像の応答ヘッダー（CORS・キャッシュ）と、サンプル画像のほかの小さい版の名前を調べる。読むだけ。main には入れない。"""
import json, urllib.request
def note(t, s):
    s = str(s).replace("\n", " | ").replace("%", "%25")
    print(f"::notice title={t}::{s[:3800]}", flush=True)
cur = json.load(open("site/src/data/new_releases.json", encoding="utf-8"))
it = next(i for i in cur if i.get("sample_images"))
big = it["sample_images"][0]
base = big.rsplit("jp-", 1)[0]
out = []
for u in [it["image_url"], it["image_url"][:-6] + "ps.jpg", big, base + "-1.jpg"]:
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Origin": "https://fanza-ranking.pages.dev", "Referer": "https://fanza-ranking.pages.dev/"})
    with urllib.request.urlopen(req, timeout=20) as r:
        h = {k.lower(): v for k, v in r.headers.items()}
        out.append((u[-16:], {k: h.get(k) for k in ("access-control-allow-origin", "timing-allow-origin", "cache-control", "age", "server", "x-cache", "via", "content-length", "last-modified")}))
note("headers", out)
alt = []
for suf in ("js-1.jpg", "jm-1.jpg", "ps-1.jpg", "jl-1.jpg", "-1s.jpg", "jp-1s.jpg", "m-1.jpg"):
    u = base + suf
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
            b = r.read()
            alt.append((suf, r.status, len(b), r.geturl()[-40:]))
    except urllib.error.HTTPError as e:
        alt.append((suf, e.code))
    except Exception as e:
        alt.append((suf, repr(e)[:40]))
note("alt", alt)
