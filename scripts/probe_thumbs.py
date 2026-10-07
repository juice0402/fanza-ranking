#!/usr/bin/env python3
"""作業用: FANZAの画像の「小さい版」があるか・大きさ・重さを調べる（読むだけ。画像は保存しない）。
スマホのサムネを軽い画像にするための下調べ。main には入れない。
結果は、ログが読めない環境でも読めるよう、注釈（notice）で出す。"""
import glob
import json
import os
import random
import struct
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

D = os.path.join("site", "src", "data")
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)", "Referer": "https://fanza-ranking.pages.dev/"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def note(title, text):
    text = str(text).replace("\n", " | ").replace("%", "%25")
    for i in range(0, len(text), 3500):
        print(f"::notice title={title}{'' if i == 0 else '-' + str(i // 3500)}::{text[i:i + 3500]}", flush=True)


def dims(buf):
    """JPEG / PNG / WebP / GIF の縦横（読めなければ None）"""
    try:
        if buf[:2] == b"\xff\xd8":
            i = 2
            while i < len(buf) - 9:
                if buf[i] != 0xFF:
                    i += 1
                    continue
                m = buf[i + 1]
                if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", buf[i + 5:i + 9])
                    return (w, h)
                if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                    i += 2
                    continue
                ln = struct.unpack(">H", buf[i + 2:i + 4])[0]
                i += 2 + ln
            return None
        if buf[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", buf[16:24])
        if buf[:4] == b"RIFF" and buf[8:12] == b"WEBP":
            k = buf[12:16]
            if k == b"VP8X":
                w = 1 + int.from_bytes(buf[24:27], "little")
                h = 1 + int.from_bytes(buf[27:30], "little")
                return (w, h)
            if k == b"VP8 ":
                w, h = struct.unpack("<HH", buf[26:30])
                return (w & 0x3FFF, h & 0x3FFF)
            if k == b"VP8L":
                b = int.from_bytes(buf[21:25], "little")
                return ((b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1)
        if buf[:3] == b"GIF":
            return struct.unpack("<HH", buf[6:10])
    except Exception:  # noqa: BLE001
        return None
    return None


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as res:
            buf = res.read()
            return {"ok": True, "status": res.status, "final": res.geturl(), "type": res.headers.get("Content-Type", ""),
                    "cache": res.headers.get("Cache-Control", ""), "bytes": len(buf), "dims": dims(buf)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "final": url}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": repr(e)[:80], "final": url}


curated = load(os.path.join(D, "new_releases.json"))
catalog = []
for p in sorted(glob.glob(os.path.join(D, "catalog", "*.json"))):
    catalog += load(p)
random.seed(11)
pick = {i["cid"]: i for i in curated}
for i in random.sample(catalog, min(150, len(catalog))):
    pick.setdefault(i["cid"], i)
todo = [it for it in pick.values() if (it.get("image_url") or "").endswith("pl.jpg")]
print("todo", len(todo), flush=True)


def shape(d):
    if not d:
        return "?"
    w, h = d
    r = w / h
    return "spread" if 1.35 <= r <= 1.53 else ("wide" if r > 1 else "tall")


def probe(it):
    pl = it["image_url"]
    out = {"cid": it["cid"], "pl": get(pl), "ps": get(pl[:-6] + "ps.jpg"), "pt": get(pl[:-6] + "pt.jpg")}
    s = [u for u in it.get("sample_images") or [] if u]
    if s:
        big = s[0]
        small = big.replace("jp-", "-") if "jp-" in big else big
        out["sl"] = get(big)
        out["ss"] = get(small)
    return out


with ThreadPoolExecutor(8) as ex:
    rows = list(ex.map(probe, todo))


def summary(kind, rows_, by=None):
    st = Counter()
    dm = Counter()
    sizes = []
    redirect = Counter()
    for r in rows_:
        g = r.get(kind)
        if not g:
            continue
        st[g["status"]] += 1
        if g["ok"]:
            dm[g["dims"]] += 1
            sizes.append(g["bytes"])
            if g["final"] != (r["pl"]["final"] if kind == "pl" else g["final"]) or "noimage" in g["final"] or "now_printing" in g["final"]:
                redirect[g["final"][-60:]] += 1
    sizes.sort()
    med = sizes[len(sizes) // 2] if sizes else 0
    p90 = sizes[int(len(sizes) * 0.9)] if sizes else 0
    avg = sum(sizes) // len(sizes) if sizes else 0
    return f"status={dict(st)} dims={dm.most_common(6)} bytes avg={avg} med={med} p90={p90} redirects={redirect.most_common(4)}"


for k in ("pl", "ps", "pt", "sl", "ss"):
    note(f"probe-{k}", summary(k, rows))

# 見開きかどうか別の ps / pt の形
by = defaultdict(Counter)
for r in rows:
    if r["pl"]["ok"]:
        sh = shape(r["pl"]["dims"])
        by[sh]["n"] += 1
        for k in ("ps", "pt"):
            g = r[k]
            by[sh][f"{k}:{g['dims'] if g['ok'] else g['status']}"] += 1
note("probe-shape", "; ".join(f"{sh}: {dict(c.most_common(8))}" for sh, c in by.items()))

# 失敗の例（ps・pt・小さいサンプル）
for k in ("ps", "pt", "ss"):
    bad = [f"{r['cid']}:{r[k]['status']}" for r in rows if r.get(k) and not r[k]["ok"]]
    note(f"probe-bad-{k}", f"{len(bad)} {bad[:12]}")
# 最終のURL（転送されたもの）
fin = Counter()
for r in rows:
    for k in ("ps", "pt", "ss"):
        g = r.get(k)
        if g and g["ok"]:
            base = r["pl"]["final"][:-6] if k != "ss" else None
            if k != "ss" and not g["final"].startswith(base):
                fin[f"{k}->{g['final'][-50:]}"] += 1
note("probe-final", str(fin.most_common(8)))
# ヘッダーの例
ex = next((r for r in rows if r["ps"]["ok"]), None)
if ex:
    note("probe-headers", f"pl type={ex['pl'].get('type')} cache={ex['pl'].get('cache')} | ps type={ex['ps'].get('type')} cache={ex['ps'].get('cache')}")

# サンプル画像: 大きいもの（jp-N）が全部あるとき、小さいもの（-N）も全部あるか（20本）
miss = Counter()
checked = 0
for it in [t for t in todo if t.get("sample_images")][:20]:
    for big in it["sample_images"][:8]:
        if "jp-" not in big:
            continue
        checked += 1
        g = get(big.replace("jp-", "-"))
        miss["ok" if g["ok"] else g["status"]] += 1
note("probe-samples-all", f"checked={checked} {dict(miss)}")

# 画像を小さくしてくれる配信（awsimgsrc）があるか（参考。5本だけ）
aws = []
for it in todo[:5]:
    path = it["image_url"].split("pics.dmm.co.jp/", 1)[1]
    for q in ("", "?w=360", "?w=360&f=webp", "?f=webp"):
        g = get("https://awsimgsrc.dmm.co.jp/pics_dig/" + path + q)
        aws.append(f"{q or 'plain'}:{g['status']}:{g.get('type', '')}:{g.get('bytes', '')}:{g.get('dims', '')}")
note("probe-aws", " ".join(aws))
