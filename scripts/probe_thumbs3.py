#!/usr/bin/env python3
"""作業用: サンプル画像の小さい版（…-N.jpg）が、大きい版（…jp-N.jpg）を余白つきで縮めたものか・切り出したものかを調べる。読むだけ。main には入れない。"""
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
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        if "now_printing" in r.geturl(): return None
        b = r.read()
        return Image.open(io.BytesIO(b)).convert("L"), len(b)
curated = load(os.path.join(D, "new_releases.json"))
catalog = []
for p in sorted(glob.glob(os.path.join(D, "catalog", "*.json"))): catalog += load(p)
random.seed(9)
pool = [i for i in curated if i.get("sample_images")] + random.sample([i for i in catalog if i.get("sample_images")], 120)
pairs = []
for it in pool:
    s = [u for u in it["sample_images"] if "jp-" in u]
    for u in s[:3]:
        pairs.append(u)
def bands(s):
    w, h = s.size; px = s.load()
    def fr(y):
        v = [px[x, y] for x in range(w)]; m = sum(v)/w; return max(abs(t-m) for t in v) < 12
    def fc(x):
        v = [px[x, y] for y in range(h)]; m = sum(v)/h; return max(abs(t-m) for t in v) < 12
    return (next((y for y in range(h) if not fr(y)), h), next((y for y in range(h) if not fr(h-1-y)), h),
            next((x for x in range(w) if not fc(x)), w), next((x for x in range(w) if not fc(w-1-x)), w))
def kind(w, h):
    r = w / h
    return "16:9" if r > 1.6 else ("3:2" if r > 1.4 else ("4:3" if r > 1.2 else ("sq" if r > 0.9 else "tall")))
def probe(u):
    try:
        L = get(u); S = get(u.replace("jp-", "-"))
        if not L or not S: return None
        (l, lb), (s, sb) = L, S
        W, H = s.size
        # 余白つき（全体を入れる）と、切り出し（まん中を埋める）
        w, h = l.size
        sc = min(W / w, H / h); nw, nh = round(w*sc), round(h*sc)
        fit = Image.new("L", (W, H), 0); fit.paste(l.resize((nw, nh)), ((W-nw)//2, (H-nh)//2))
        sc2 = max(W / w, H / h); cw, ch = W / sc2, H / sc2
        crop = l.crop(((w-cw)/2, (h-ch)/2, (w+cw)/2, (h+ch)/2)).resize((W, H))
        # 余白の部分は比べない（中身の部分だけ）
        box = ((W-nw)//2, (H-nh)//2, (W-nw)//2+nw, (H-nh)//2+nh)
        dfit = ImageStat.Stat(ImageChops.difference(fit.crop(box), s.crop(box))).mean[0]
        dcrop = ImageStat.Stat(ImageChops.difference(crop, s)).mean[0]
        b = bands(s)
        band_px = []
        px = s.load()
        for y in list(range(b[0])) + list(range(H - b[1], H)):
            band_px += [px[x, y] for x in range(W)]
        for x in list(range(b[2])) + list(range(W - b[3], W)):
            band_px += [px[x, y] for y in range(H)]
        col = round(sum(band_px) / len(band_px)) if band_px else -1
        return {"col": col, "k": kind(w, h), "ls": (w, h), "ss": (W, H), "fit": round(dfit, 1), "crop": round(dcrop, 1), "bands": bands(s), "lb": lb, "sb": sb}
    except Exception as e:
        return {"err": repr(e)[:60]}
with ThreadPoolExecutor(8) as ex:
    rows = [r for r in ex.map(probe, pairs) if r]
by = defaultdict(Counter); bd = defaultdict(list)
for r in rows:
    if "err" in r: by["err"][r["err"]] += 1; continue
    by[r["k"]]["n"] += 1
    by[r["k"]]["fit" if r["fit"] < r["crop"] else "crop"] += 1
    by[r["k"]][f"ss{r['ss']}"] += 1
    bd[r["k"]].append(r["bands"])
note("s-match", "; ".join(f"{k}: {dict(c.most_common(8))}" for k, c in by.items()))
for k, bl in bd.items():
    tb = Counter((b[0] > 3 or b[1] > 3) for b in bl); sd = Counter((b[2] > 3 or b[3] > 3) for b in bl)
    note(f"s-bands-{k}", f"n={len(bl)} topbottom={dict(tb)} sides={dict(sd)} ex={Counter(bl).most_common(6)}")
ex = [r for r in rows if "err" not in r][:6]
note("s-color", Counter((r["col"] // 16) * 16 for r in rows if "col" in r and r["col"] >= 0).most_common(8))
# 大きさの指定（?w=）が効くか（参考）
try:
    u0 = pairs[0]
    for q in ("?w=240", "?w=240&h=160&t=margin", "?f=webp"):
        with urllib.request.urlopen(urllib.request.Request(u0 + q, headers=UA), timeout=20) as r:
            bb = r.read()
            try:
                im = Image.open(io.BytesIO(bb)); d = (im.size, im.format)
            except Exception:
                d = None
            note("s-q" + q.replace("&", "+").replace("?", "_").replace("=", "-"), (r.status, r.headers.get("Content-Type"), len(bb), d, r.geturl()[-50:]))
except Exception as e:
    note("s-q-err", repr(e)[:200])
note("s-ex", [(r["ls"], r["ss"], r["fit"], r["crop"], r["lb"], r["sb"]) for r in ex])
