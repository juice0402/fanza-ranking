#!/usr/bin/env python3
"""作業用: FANZAのパッケージ画像（pl.jpg）の縦横の大きさを調べる（読むだけ。保存しない。標準ライブラリだけ）。
人気のジャンルの四角い表紙の切り出しを、見開きのパッケージと1枚絵で分けるための下調べ。main には入れない。"""
import glob
import json
import os
import random
import struct
import time
import urllib.request
from collections import Counter, defaultdict

D = os.path.join("site", "src", "data")
OUT = "probe-out"
os.makedirs(OUT, exist_ok=True)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


curated = load(os.path.join(D, "new_releases.json"))
catalog = []
for p in sorted(glob.glob(os.path.join(D, "catalog", "*.json"))):
    catalog += load(p)
pop = load(os.path.join(D, "popularity.json"))
newrank = pop.get("new", {})

random.seed(7)
pick = {i["cid"]: i for i in curated}
ranked = [i for i in catalog if i["cid"] in newrank]
for i in ranked:
    pick.setdefault(i["cid"], i)
for i in random.sample(catalog, min(250, len(catalog))):
    pick.setdefault(i["cid"], i)


def dims(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-65535"})
    with urllib.request.urlopen(req, timeout=15) as res:
        b = res.read(65536)
    i = 2
    while i < len(b) - 9:
        if b[i] != 0xFF:
            i += 1
            continue
        m = b[i + 1]
        if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        ln = struct.unpack(">H", b[i + 2:i + 4])[0]
        i += 2 + ln
    return None


rows = []
fails = 0
from concurrent.futures import ThreadPoolExecutor

todo = [(cid, it) for cid, it in pick.items() if (it.get("image_url") or "").startswith("https://pics.dmm.co.jp/")]
print("todo", len(todo), flush=True)
t0 = time.time()


def one(pair):
    cid, it = pair
    try:
        return cid, it, dims(it["image_url"])
    except Exception as e:  # noqa: BLE001
        return cid, it, repr(e)[:80]


with ThreadPoolExecutor(6) as ex:
    for n, (cid, it, d) in enumerate(ex.map(one, todo), 1):
        if not isinstance(d, tuple):
            fails += 1
            if fails <= 5:
                print("fail", cid, d, flush=True)
            continue
        rows.append({"cid": cid, "w": d[0], "h": d[1], "maker": it.get("maker", ""), "vr": "VR" in (it.get("tags") or []) or "【VR】" in it.get("title", ""), "rank": newrank.get(cid), "url": it["image_url"]})
        if n % 100 == 0:
            print(n, round(time.time() - t0), "s", flush=True)

print(f"measured {len(rows)} fails {fails}")
c = Counter((r["w"], r["h"]) for r in rows)
print("== sizes (w x h: count, ratio)")
for (w, h), n in c.most_common(40):
    print(f"{w}x{h}: {n}  r={w / h:.3f}")
by = defaultdict(Counter)
for r in rows:
    std = abs(r["w"] / r["h"] - 800 / 538) < 0.03
    by[r["maker"]]["std" if std else f"{r['w']}x{r['h']}"] += 1
print("== makers with non-standard")
for m, cc in sorted(by.items(), key=lambda kv: -sum(v for k, v in kv[1].items() if k != "std")):
    ns = {k: v for k, v in cc.items() if k != "std"}
    if ns:
        print(m, dict(cc))
with open(os.path.join(OUT, "dims.json"), "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False)

# 見本の画像（切り出しの見た目の確認用。アーティファクトは1日で消える）: 人気の上位40本と、大きさの組ごとに8本ずつ
save = set(r["cid"] for r in sorted([r for r in rows if r["rank"]], key=lambda r: r["rank"])[:40])
groups = defaultdict(list)
for r in rows:
    groups[(r["w"], r["h"])].append(r["cid"])
for k, cids in groups.items():
    save.update(cids[:8])
def grab(r):
    try:
        with urllib.request.urlopen(urllib.request.Request(r["url"], headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as res:
            open(os.path.join(OUT, r["cid"] + ".jpg"), "wb").write(res.read())
    except Exception:  # noqa: BLE001
        pass


with ThreadPoolExecutor(6) as ex:
    list(ex.map(grab, [r for r in rows if r["cid"] in save]))
print("saved", len(save))
