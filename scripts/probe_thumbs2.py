#!/usr/bin/env python3
"""作業用: ps.jpg / pt.jpg が、pl.jpg のどこを縮めたものか（右の表紙の切り出し・全体の余白つき縮小）を調べる。読むだけ。main には入れない。"""
import glob, io, json, os, random, urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageChops, ImageStat

D = os.path.join("site", "src", "data")
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://fanza-ranking.pages.dev/"}
def load(p):
    with open(p, encoding="utf-8") as f: return json.load(f)
def note(t, s):
    s = str(s).replace("\n", " | ").replace("%", "%25")
    print(f"::notice title={t}::{s[:3800]}", flush=True)
def img(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        if "now_printing" in r.geturl(): return None
        return Image.open(io.BytesIO(r.read())).convert("L")
curated = load(os.path.join(D, "new_releases.json"))
catalog = []
for p in sorted(glob.glob(os.path.join(D, "catalog", "*.json"))): catalog += load(p)
random.seed(5)
pool = curated + random.sample(catalog, 200)
todo = [i for i in pool if (i.get("image_url") or "").endswith("pl.jpg")]
def shape(w, h):
    r = w / h
    return "spread" if 1.35 <= r <= 1.53 else ("wide" if r > 1 else "tall")
def diff(a, b):
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]
def bands(s):
    w, h = s.size
    px = s.load()
    def flat_row(y): 
        v = [px[x, y] for x in range(w)]; m = sum(v)/w
        return max(abs(t-m) for t in v) < 12
    def flat_col(x):
        v = [px[x, y] for y in range(h)]; m = sum(v)/h
        return max(abs(t-m) for t in v) < 12
    top = next((y for y in range(h) if not flat_row(y)), h)
    bot = next((y for y in range(h) if not flat_row(h-1-y)), h)
    left = next((x for x in range(w) if not flat_col(x)), w)
    right = next((x for x in range(w) if not flat_col(w-1-x)), w)
    return top, bot, left, right
def cands(pl, W, H):
    w, h = pl.size
    out = {}
    cw = h * W / H
    out["right"] = pl.crop((w - cw, 0, w, h)).resize((W, H)) if cw <= w else None
    out["center"] = pl.crop(((w - cw) / 2, 0, (w + cw) / 2, h)).resize((W, H)) if cw <= w else None
    out["left"] = pl.crop((0, 0, cw, h)).resize((W, H)) if cw <= w else None
    # 全体を余白つきで入れる
    sc = min(W / w, H / h); nw, nh = round(w * sc), round(h * sc)
    canvas = Image.new("L", (W, H), 255); canvas.paste(pl.resize((nw, nh)), ((W - nw) // 2, (H - nh) // 2))
    out["fit"] = canvas
    # 高さが入りきらない縦長: 上の切り出し・全体の切り出し（横幅に合わせる）
    ch = w * H / W
    if ch <= h:
        out["topcrop"] = pl.crop((0, 0, w, ch)).resize((W, H))
        out["midcrop"] = pl.crop((0, (h - ch) / 2, w, (h + ch) / 2)).resize((W, H))
    return {k: v for k, v in out.items() if v is not None}
def probe(it):
    try:
        pl = img(it["image_url"])
        if pl is None: return None
        res = {"shape": shape(*pl.size), "size": pl.size}
        for k, (W, H) in (("ps", (147, 200)), ("pt", (90, 122))):
            s = img(it["image_url"][:-6] + k + ".jpg")
            if s is None: return None
            res[k + "_size"] = s.size
            c = cands(pl, *s.size)
            scores = {n: diff(v, s) for n, v in c.items()}
            best = min(scores, key=scores.get)
            res[k] = (best, round(scores[best], 1))
            res[k + "_bands"] = bands(s)
        return res
    except Exception as e:
        return {"err": repr(e)[:80]}
with ThreadPoolExecutor(8) as ex:
    rows = [r for r in ex.map(probe, todo) if r]
by = defaultdict(Counter)
bandinfo = defaultdict(list)
for r in rows:
    if "err" in r: by["err"][r["err"]] += 1; continue
    by[r["shape"]]["n"] += 1
    for k in ("ps", "pt"):
        by[r["shape"]][f"{k}:{r[k][0]}{'' if r[k][1] < 25 else '?'}"] += 1
    b = r["ps_bands"]
    bandinfo[r["shape"]].append(b)
note("match", "; ".join(f"{s}: {dict(c.most_common(10))}" for s, c in by.items()))
for s, bl in bandinfo.items():
    withband = [b for b in bl if b[0] > 6 or b[1] > 6]
    sideband = [b for b in bl if b[2] > 6 or b[3] > 6]
    note(f"bands-{s}", f"n={len(bl)} topbottom>6px={len(withband)} ex={withband[:8]} side>6px={len(sideband)} ex={sideband[:8]}")
sz = Counter(str(r["size"]) for r in rows if "size" in r)
note("plsizes", sz.most_common(12))
