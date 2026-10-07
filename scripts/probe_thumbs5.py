#!/usr/bin/env python3
"""作業用: 見開きのパッケージの ps.jpg が、表紙だけ（右の 379/800）を縮めたものか、背表紙を少し含む切り出しかを調べる。読むだけ。main には入れない。"""
import io, json, random, urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageChops, ImageStat
def note(t, s):
    s = str(s).replace("\n", " | ").replace("%", "%25"); print(f"::notice title={t}::{s[:3800]}", flush=True)
UA = {"User-Agent": "Mozilla/5.0"}
def img(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20) as r:
        if "now_printing" in r.geturl(): return None
        return Image.open(io.BytesIO(r.read())).convert("L")
cur = json.load(open("site/src/data/new_releases.json", encoding="utf-8"))
todo = [i for i in cur if (i.get("image_url") or "").endswith("pl.jpg")][:120]
def d(a, b): return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]
def probe(it):
    try:
        pl = img(it["image_url"]); ps = img(it["image_url"][:-6] + "ps.jpg"); pt = img(it["image_url"][:-6] + "pt.jpg")
        if not pl or not ps: return None
        w, h = pl.size
        if not 1.35 <= w / h <= 1.53: return None
        res = {}
        for name, small in (("ps", ps), ("pt", pt)):
            W, H = small.size
            best = None
            # 右端から、いろいろな幅で切り出して比べる（表紙の幅 / 高さ の比 0.66〜0.78）
            for r100 in range(66, 79):
                cw = h * r100 / 100
                for off in (0, 4, 8):  # 右端を少し内側にずらす（ふちの白い線など）
                    c = pl.crop((w - cw - off, 0, w - off, h)).resize((W, H))
                    sc = d(c, small)
                    if best is None or sc < best[0]: best = (round(sc, 1), r100, off)
            res[name] = best
        return res
    except Exception as e:
        return {"err": repr(e)[:60]}
with ThreadPoolExecutor(8) as ex:
    rows = [r for r in ex.map(probe, todo) if r]
for k in ("ps", "pt"):
    good = [r[k] for r in rows if k in r]
    note(f"fit-{k}", f"n={len(good)} ratio={Counter(g[1] for g in good).most_common(8)} off={Counter(g[2] for g in good).most_common(3)} score_med={sorted(g[0] for g in good)[len(good)//2] if good else -1} score_lt10={sum(1 for g in good if g[0] < 10)}")
