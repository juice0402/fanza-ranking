#!/usr/bin/env python3
"""下調べ（このブランチだけ）: FANZA の画像に、どんな大きさの版があるか（スマホのサムネの画質を決めるため）。
結果は注釈（::notice）に出す。データは保存しない。"""
import json
import struct
import urllib.error
import urllib.request


def dims(b):
    try:
        if b[:2] == b"\xff\xd8":
            i = 2
            while i < len(b) - 9:
                if b[i] != 0xFF:
                    i += 1
                    continue
                m = b[i + 1]
                if m in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", b[i + 5:i + 9])
                    return f"{w}x{h}"
                ln = struct.unpack(">H", b[i + 2:i + 4])[0]
                i += 2 + ln
        if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            k = b[12:16]
            if k == b"VP8X":
                return f"{1 + int.from_bytes(b[24:27], 'little')}x{1 + int.from_bytes(b[27:30], 'little')}"
            if k == b"VP8 ":
                w, h = struct.unpack("<HH", b[26:30])
                return f"{w & 0x3fff}x{h & 0x3fff}"
            if k == b"VP8L":
                v = int.from_bytes(b[21:25], "little")
                return f"{(v & 0x3fff) + 1}x{((v >> 14) & 0x3fff) + 1}"
        if b[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", b[16:24])
            return f"{w}x{h}"
    except Exception:
        pass
    return "?"


UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"


def get(url, accept="image/webp,image/*,*/*;q=0.8"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Referer": "https://fanza-ranking.pages.dev/"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            b = r.read()
            moved = "" if r.url == url else " → " + r.url[:90]
            return f"{r.status} {r.headers.get('Content-Type', '')} {len(b) // 1024}KB {dims(b)}{moved}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return f"ERR {type(e).__name__}"


def load(path):
    d = json.load(open(path, encoding="utf-8"))
    return d if isinstance(d, list) else d["items"]


video = [i for i in load("site/src/data/new_releases.json") if "vr" not in i["cid"] and i.get("image_url", "").endswith("pl.jpg")][:2]
doujin = load("site/src/data/doujin.json")
dj = [next(i for i in doujin if f"/{k}/" in i["image_url"]) for k in ("comic", "voice", "cg")]
game = load("site/src/data/game.json")[:2]


def notice(title, rows):
    msg = "\n".join(rows).replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::notice title={title}::{msg}")


def head(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://fanza-ranking.pages.dev/"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return f"cache-control={r.headers.get('Cache-Control')} age={r.headers.get('Age')} via={r.headers.get('Via') or r.headers.get('Server')} x-cache={r.headers.get('X-Cache')}"
    except Exception as e:  # noqa: BLE001
        return f"ERR {e}"


for kind, it in [("video", v) for v in video] + [("doujin", d) for d in dj] + [("game", g) for g in game]:
    pl = it["image_url"]
    base = pl[:-len("pl.jpg")]
    aws = base.replace("https://pics.dmm.co.jp/", "https://awsimgsrc.dmm.co.jp/pics_dig/")
    rows = []
    if kind == "video":
        for q in ["?w=300&q=75", "?w=320&q=75", "?w=360&q=75", "?w=300&q=80", "?w=200&q=75", "?w=240&q=75"]:
            rows.append(f"aws ps{q}: {get(aws + 'ps.jpg' + q)}")
        rows.append("headers ps?w=300&q=75: " + head(aws + "ps.jpg?w=300&q=75"))
    else:
        for q in ["?w=240&q=75", "?w=300&q=75", "?w=360&q=75", "?w=360&q=80"]:
            rows.append(f"aws pl{q}: {get(aws + 'pl.jpg' + q)}")
        rows.append("headers pl?w=360&q=75: " + head(aws + "pl.jpg?w=360&q=75"))
    rows.append("headers pics pl: " + head(pl))
    notice(f"{kind} {it['cid']}", rows)
