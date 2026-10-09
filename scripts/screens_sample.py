#!/usr/bin/env python3
"""画面の写真の道具（.github/workflows/screens.yml）で、まだ本番に無い状態の見た目を確かめるための「見本のデータ」を作る（Python標準ライブラリだけ）。

  python3 scripts/screens_sample.py ten_yen

・ten_yen: 10円セールの開催中の見た目（運営者の希望「10円セールは大イベント」。2026-10-09）。
  いまのデータ（new_releases.json・doujin.json・game.json）から作品を選び、価格を10円にした ten_yen.json を書く。
  GitHub の上の、写真を撮るためだけのビルドで使う（保存も公開もしない。リポジトリにも入れない）。
  セールの名前は「見本」と分かる名前にする
"""
import json
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ten_yen as T  # noqa: E402

DATA = os.path.join(ROOT, "site", "src", "data")


def ten_yen_sample():
    now = datetime.now(T.G.JST)
    end = (now + timedelta(days=2)).strftime("%Y-%m-%d") + " 09:59"
    today = now.strftime("%Y-%m-%d")
    out = {"checked": now.strftime("%Y-%m-%d %H:%M"), "video": [], "doujin": [], "game": [], "runs": []}
    videos = json.load(open(os.path.join(DATA, "new_releases.json"), encoding="utf-8"))
    for x in [v for v in videos if v.get("image_url") and v.get("url") and str(v.get("date"))[:10] <= today][:9]:
        row = {k: x.get(k) for k in T.VIDEO_KEYS}
        row.update(price=10, list_price=2980, sale_title="見本の10円セール", sale_end=end)
        out["video"].append(row)
    for key, n in (("doujin", 14), ("game", 3)):
        data = json.load(open(os.path.join(DATA, f"{key}.json"), encoding="utf-8"))
        ranks = data.get("ranks") or {}
        items = sorted((x for x in data["items"] if x["cid"] in ranks), key=lambda x: ranks[x["cid"]])[:n]
        for x in items:
            row = {k: x.get(k) for k in T.FLOOR_ITEM_KEYS}
            row.update(price=10, list_price=max(x.get("list_price") or 0, 1100), sale_title="", sale_end="", rank=ranks[x["cid"]])
            out[key].append(row)
    out["runs"] = [
        {"floor": "video", "first": today, "last": today, "count": len(out["video"]), "end": end, "titles": ["見本の10円セール"]},
        {"floor": "doujin", "first": today, "last": today, "count": len(out["doujin"]), "end": "", "titles": []},
        {"floor": "video", "first": "2026-09-12", "last": "2026-09-18", "count": 10, "end": "", "titles": ["見本の前の回"]},
    ]
    with open(os.path.join(DATA, "ten_yen.json"), "w", encoding="utf-8") as f:
        f.write(T.dump(out))
    print(f"見本: 動画{len(out['video'])}本・同人{len(out['doujin'])}本・ゲーム{len(out['game'])}本")


if __name__ == "__main__":
    {"ten_yen": ten_yen_sample}[sys.argv[1]]()
