#!/usr/bin/env python3
"""作業用: FANZAのパッケージ画像（pl.jpg）の縦横の大きさと、顔の位置を調べる（読むだけ。画像は保存しない）。
人気のジャンルの四角い表紙の切り出しを、見開きのパッケージと1枚絵で分けるための下調べ。main には入れない。
結果は、ログが読めない環境でも読めるよう、注釈（notice）で出す。"""
import glob
import json
import os
import random
import time
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

D = os.path.join("site", "src", "data")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


curated = load(os.path.join(D, "new_releases.json"))
catalog = []
for p in sorted(glob.glob(os.path.join(D, "catalog", "*.json"))):
    catalog += load(p)
newrank = load(os.path.join(D, "popularity.json")).get("new", {})
random.seed(7)
pick = {i["cid"]: i for i in curated}
for i in catalog:
    if i["cid"] in newrank:
        pick.setdefault(i["cid"], i)
for i in random.sample(catalog, min(350, len(catalog))):
    pick.setdefault(i["cid"], i)
todo = [(cid, it) for cid, it in pick.items() if (it.get("image_url") or "").startswith("https://pics.dmm.co.jp/")]
print("todo", len(todo), flush=True)

CASCADE = cv2.CascadeClassifier(os.path.join(getattr(getattr(cv2, "data", None), "haarcascades", ""), "haarcascade_frontalface_default.xml"))
if CASCADE.empty():  # OpenCV 5 には入っていない。OpenCV の公式リポジトリから取る
    try:
        xml = "/tmp/haarcascade_frontalface_default.xml"
        with urllib.request.urlopen("https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/haarcascade_frontalface_default.xml", timeout=30) as res:
            open(xml, "wb").write(res.read())
        CASCADE = cv2.CascadeClassifier(xml)
    except Exception as e:  # noqa: BLE001
        print("::notice title=cascade::" + repr(e)[:200])
CASCADE_OK = not CASCADE.empty()
FAKE = os.environ.get("PROBE_FAKE_FACES") == "1"
print("cascade ok", CASCADE_OK, flush=True)


def fetch(pair):
    cid, it = pair
    try:
        with urllib.request.urlopen(urllib.request.Request(it["image_url"], headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as res:
            buf = res.read()
        img = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return cid, it, None, None
        h, w = img.shape
        if FAKE:
            faces = [(random.randint(0, w - 80), random.randint(0, h - 80), 70, 70)]
        elif CASCADE_OK:
            faces = CASCADE.detectMultiScale(img, scaleFactor=1.1, minNeighbors=6, minSize=(max(24, h // 12), max(24, h // 12)))
        else:
            faces = []
        faces = sorted([tuple(int(v) for v in f) for f in faces], key=lambda f: -f[2] * f[3])
        return cid, it, (w, h), faces
    except Exception as e:  # noqa: BLE001
        return cid, it, repr(e)[:60], None


rows = []
fails = 0
t0 = time.time()
with ThreadPoolExecutor(8) as ex:
    for cid, it, d, faces in ex.map(fetch, todo):
        if not isinstance(d, tuple):
            fails += 1
            continue
        rows.append({"cid": cid, "w": d[0], "h": d[1], "maker": it.get("maker", ""), "rank": newrank.get(cid), "faces": faces or []})
print("measured", len(rows), "fails", fails, round(time.time() - t0), "s", flush=True)

notes = []


def kind(r):
    q = r["w"] / r["h"]
    if abs(q - 800 / 538) < 0.03:
        return "std"
    if q > 1.6:
        return "wide"
    if q > 1.2:
        return "mid"
    if q > 0.85:
        return "square"
    return "tall"


c = Counter((r["w"], r["h"]) for r in rows)
notes.append(("sizes", f"measured {len(rows)} fails {fails} | " + " / ".join(f"{w}x{h}:{n}(r{w / h:.3f})" for (w, h), n in c.most_common(25))))
kc = Counter(kind(r) for r in rows)
notes.append(("kinds", " / ".join(f"{k}:{n}" for k, n in kc.most_common())))
by = defaultdict(Counter)
for r in rows:
    by[r["maker"]][kind(r)] += 1
ns = sorted(((m, cc) for m, cc in by.items() if sum(v for k, v in cc.items() if k != "std")), key=lambda kv: -sum(v for k, v in kv[1].items() if k != "std"))
notes.append(("makers-nonstd", " / ".join(f"{m}:{dict(cc)}" for m, cc in ns[:40])))
# 人気の上位（新着の人気順100位まで）の中の、見開きでない作品
hot_ns = sorted([r for r in rows if r["rank"] and r["rank"] <= 100 and kind(r) != "std"], key=lambda r: r["rank"])
notes.append(("hot-nonstd", f"{len(hot_ns)} of {sum(1 for r in rows if r['rank'] and r['rank'] <= 100)} | " + " / ".join(f"#{r['rank']} {r['cid']} {r['w']}x{r['h']} {r['maker']}" for r in hot_ns[:30])))
t = next((r for r in rows if r["cid"] == "1hnamh00028"), None)
notes.append(("1hnamh00028", json.dumps(t, ensure_ascii=False)))

# 顔の位置: 見開き（std）は、表紙（右端の 379/800）の中での位置。ほかは画像全体の中での位置
def face_in(r):
    w, h = r["w"], r["h"]
    if kind(r) == "std":
        x0 = w * 421 / 800
        fs = [f for f in r["faces"] if f[0] >= x0 - 4]
        if not fs:
            return None
        x, y, fw, fh = fs[0]
        cw = w - x0
        return ((x - x0) / cw, y / h, (x - x0 + fw) / cw, (y + fh) / h, cw / h)
    if not r["faces"]:
        return None
    x, y, fw, fh = r["faces"][0]
    return (x / w, y / h, (x + fw) / w, (y + fh) / h, w / h)


for k in ("std", "wide", "mid", "square", "tall"):
    fr = [(r, face_in(r)) for r in rows if kind(r) == k]
    got = [(r, f) for r, f in fr if f]
    if not fr:
        continue
    line = f"{k}: images {len(fr)} with face {len(got)}"
    if got:
        cy = sorted((f[1] + f[3]) / 2 for _, f in got)
        cx = sorted((f[0] + f[2]) / 2 for _, f in got)
        pct = lambda a, p: round(a[min(len(a) - 1, int(p * len(a)))], 3)
        line += f" | face center x p10/50/90 {pct(cx, .1)}/{pct(cx, .5)}/{pct(cx, .9)} y p10/50/90 {pct(cy, .1)}/{pct(cy, .5)}/{pct(cy, .9)}"
        # 四角の切り出し: 枠の幅 = 対象の幅（std は表紙・横長は高さ）。縦横の位置 pos（0=上/左, 1=下/右）ごとに、顔がまるごと入る割合
        res = []
        if k == "std" or k in ("square", "tall"):
            for pos in (0, 0.1, 0.2, 0.3, 0.4, 0.5):
                ok = 0
                for r, f in got:
                    ar = f[4]  # 幅/高さ（std は表紙の）
                    side = ar  # 高さを1としたときの四角の一辺
                    if side >= 1:
                        ok += 1
                        continue
                    top = pos * (1 - side)
                    ok += f[1] >= top - 0.005 and f[3] <= top + side + 0.005
                res.append(f"v{pos}:{ok * 100 // len(got)}%")
        else:
            for pos in (0.3, 0.4, 0.5, 0.6, 1.0):
                ok = 0
                for r, f in got:
                    side = 1 / f[4]  # 幅を1としたときの四角の一辺
                    left = pos * (1 - side)
                    ok += f[0] >= left - 0.005 and f[2] <= left + side + 0.005
                res.append(f"h{pos}:{ok * 100 // len(got)}%")
        line += " | inside " + " ".join(res)
    notes.append((f"face-{k}", line))

# 人気の上位30本: 大きさと、いちばん大きい顔の位置（画像全体の中で、x0-x1,y0-y1 の割合）
def fbox(r):
    if not r["faces"]:
        return "-"
    x, y, fw, fh = r["faces"][0]
    return f"{x / r['w']:.2f}-{(x + fw) / r['w']:.2f},{y / r['h']:.2f}-{(y + fh) / r['h']:.2f}"


top30 = sorted([r for r in rows if r["rank"]], key=lambda r: r["rank"])[:30]
notes.append(("top30", " / ".join(f"#{r['rank']} {r['cid']} {r['w']}x{r['h']} {fbox(r)}" for r in top30)))
std_left = [r for r in rows if kind(r) == "std" and r["faces"] and (r["faces"][0][0] + r["faces"][0][2] / 2) / r["w"] < 0.47]
notes.append(("std-left-face", f"{len(std_left)} of {sum(1 for r in rows if kind(r) == 'std' and r['faces'])} | " + " / ".join(f"{r['cid']} {r['maker']} {fbox(r)}" for r in std_left[:25])))

for title, body in notes:
    print(title, body, flush=True)
    print(f"::notice title={title}::{body[:3900]}")
