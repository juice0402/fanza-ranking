"""10円セールを集める道具（scripts/ten_yen.py）のテスト。実行: python3 tests/test_ten_yen.py
（ネットには出ない。APIの答えは、作った作品で差し替える。名前・タイトルは、どれも作ったもの）"""
import json
import os
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ten_yen as T  # noqa: E402

T.G.DMM_INTERVAL_SEC = 0
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


NOW = datetime(2026, 10, 9, 10, 15, tzinfo=T.G.JST)


def video(n, price="10~", list_price="2,980~", title=None, camp=None, date="2024-05-01 10:00:00"):
    cid = f"abc{n:05d}"
    item = {
        "content_id": cid, "title": title or f"作った動画その{n}", "date": date,
        "affiliateURL": f"https://al.fanza.co.jp/?lurl=https%3A%2F%2Fvideo.dmm.co.jp%2Fav%2Fcontent%2F%3Fid%3D{cid}&af_id=test-990&ch=api",
        "imageURL": {"large": f"https://pics.dmm.co.jp/digital/video/{cid}/{cid}pl.jpg"},
        "prices": {"price": price, "list_price": list_price},
        "iteminfo": {"maker": [{"id": 1, "name": "作ったメーカー"}], "actress": [{"id": 9, "name": "作った女優"}], "genre": [{"id": 1, "name": "単体作品"}]},
    }
    if camp:
        item["campaign"] = [camp]
    return item


def floor(n, key="doujin", price="10", list_price="1100", title=None, genres=("巨乳", "男性向け"), camp=None):
    cid = f"d_{200000 + n}" if key == "doujin" else f"brand_{n:04d}"
    path = "comic" if key == "doujin" else "pcgame"
    item = {
        "content_id": cid, "title": title or f"作った作品その{n}", "date": "2025-01-10 00:00:00",
        "affiliateURL": f"https://al.fanza.co.jp/?lurl=https%3A%2F%2Fwww.dmm.co.jp%2Fdc%2Fdoujin%2F-%2Fdetail%2F%3D%2Fcid%3D{cid}%2F&af_id=test-990&ch=api",
        "imageURL": {"large": f"https://pics.dmm.co.jp/digital/{path}/{cid}/{cid}pl.jpg"},
        "prices": {"price": price, **({"list_price": list_price} if list_price is not None else {})},
        "iteminfo": {"genre": [{"id": i, "name": g} for i, g in enumerate(genres)], "maker": [{"id": 300 + n, "name": f"サークル{n}"}]},
    }
    if camp:
        item["campaign"] = [camp]
    return item


class FakeAPI:
    """売り場（service）と並び順（sort）ごとの一覧を、100本ずつ返す。fail に入れた (service, sort) は失敗する"""

    def __init__(self, lists, fail=()):
        self.lists, self.fail, self.calls = lists, set(fail), []

    def __call__(self, endpoint, params):
        self.calls.append(dict(params))
        key = (params["service"], params["sort"])
        if key in self.fail:
            raise RuntimeError("テストの失敗")
        rows = self.lists.get(key, [])
        off = int(params["offset"])
        return {"items": rows[off - 1: off - 1 + params["hits"]]}


cheap_video = [
    video(1, camp={"title": "10円セール第1弾", "date_begin": "2026-10-09 10:00:00", "date_end": "2026-10-11 09:59:59"}),
    video(2, camp={"title": "10円セール第1弾", "date_begin": "2026-10-09 10:00:00", "date_end": "2026-10-11 09:59:59"}),
    video(3, list_price="10~"),  # 値引きでない10円
    video(4, title="放課後のなにか"),  # 未成年を連想させる
    video(5, price="60~", list_price="60~"),
    *[video(100 + i, price="99~", list_price="99~") for i in range(150)],
]
doujin_rank = [
    floor(1),  # 1,100円 → 10円
    floor(2, list_price="110"),  # ふだんの安売り（110円の作品が10円）
    floor(3, list_price="110", camp={"title": "10円セール", "date_begin": "2026-10-09T03:00:00Z", "date_end": "2026-10-16T02:59:59Z"}),
    floor(4, price="5", list_price="110"),
    floor(5, title="制服のなにか"),
    *[floor(10 + i, price="770", list_price="1100") for i in range(250)],
]
game_rank = [floor(1, key="game", price="8800", list_price=None)] * 1 + [floor(i, key="game", price="5500", list_price=None) for i in range(2, 120)]
game_cheap = [floor(500, key="game", price="0", list_price=None), floor(501, key="game", price="10", list_price=None, genres=("10円セール【秋の大感謝祭】", "男性向け")),
              floor(502, key="game", price="10", list_price=None)]
LISTS = {("digital", "-price"): cheap_video, ("doujin", "rank"): doujin_rank, ("pcgame", "rank"): game_rank, ("pcgame", "-price"): game_cheap}

print("■ 10円の作品の見分け方")
check("価格がちょうど10円で、値引きされているものだけ（動画は定価が10円より高いか分からないもの・同人とゲームは定価300円以上か名前に「10円」）",
      T.is_ten_yen("video", 10, 2980, []) and T.is_ten_yen("video", 10, None, []) and not T.is_ten_yen("video", 10, 10, [])
      and not T.is_ten_yen("video", 11, 2980, []) and T.is_ten_yen("doujin", 10, 1100, []) and not T.is_ten_yen("doujin", 10, 110, [])
      and T.is_ten_yen("doujin", 10, 110, ["10円セール"]) and not T.is_ten_yen("game", 10, None, []) and T.is_ten_yen("game", 10, None, ["10円セール【秋】"]))
check("終わりの日時は「YYYY-MM-DD HH:MM」の形のときだけ（Z の付いた形は、日本時間か分からないので使わない）",
      T.campaigns({"campaign": [{"title": "a", "date_end": "2026-10-11 09:59:59"}, {"title": "b", "date_end": "2026-10-16T02:59:59Z"}, {"title": " ", "date_end": ""}]})
      == [("a", "2026-10-11 09:59"), ("b", "")])

print("\n■ 集める（作ったAPIの答えで）")
api = FakeAPI(LISTS)
rows, ok = T.fetch_video(api, NOW)
check("動画: 安い順の先頭から、10円の作品だけ（値引きでない10円・未成年を連想させる作品は入れない）", ok and [r["cid"] for r in rows] == ["abc00001", "abc00002"], rows)
check("動画: 10円より高い作品が出てきたら、そこでやめる（1回だけ読む）", sum(1 for c in api.calls if c["service"] == "digital") == 1)
check("動画: キャンペーンの名前・終わり・定価・価格を持つ（作品の項目は new_releases.json と同じ名前）",
      rows[0]["sale_title"] == "10円セール第1弾" and rows[0]["sale_end"] == "2026-10-11 09:59" and rows[0]["price"] == 10 and rows[0]["list_price"] == 2980
      and rows[0]["actress"] == ["作った女優"] and rows[0]["maker"] == "作ったメーカー" and rows[0]["url"].startswith("https://al.fanza.co.jp/"))
api = FakeAPI(LISTS)
rows, ok = T.fetch_floor("doujin", api, NOW)
check("同人: 人気順の上から、定価300円以上の10円か、名前に「10円」のあるキャンペーンの作品だけ（5円・ふだんの安売り・未成年を連想させる作品は入れない）",
      ok and [r["cid"] for r in rows] == ["d_200001", "d_200003"], [r["cid"] for r in rows])
check("同人: 人気順の順位・キャンペーンの名前を持ち、Z の付いた終わりは使わない",
      rows[0]["rank"] == 1 and rows[1]["rank"] == 3 and rows[1]["sale_title"] == "10円セール" and rows[1]["sale_end"] == "" and rows[0]["list_price"] == 1100)
check("同人: 人気順を最後まで読む（作品が尽きたらやめる。安い順は読まない）",
      [c["offset"] for c in api.calls if c["service"] == "doujin"] == [1, 101, 201] and all(c["sort"] == "rank" and c.get("lte_date") for c in api.calls))
api = FakeAPI(LISTS)
rows, ok = T.fetch_floor("game", api, NOW)
check("ゲーム: 人気順と、安い順の先頭も読む。セールの札に「10円」がある10円の作品だけ（定価の分からない10円は入れない）",
      ok and [r["cid"] for r in rows] == ["brand_0501"] and rows[0]["sale_title"] == "10円セール【秋の大感謝祭】" and rows[0]["rank"] is None, rows)
rows, ok = T.fetch_floor("doujin", FakeAPI(LISTS, fail={("doujin", "rank")}), NOW)
check("続けて失敗したら「最後まで読めなかった」", not ok)

print("\n■ 開催の記録")
found = {"video": [{"sale_title": "10円セール第1弾", "sale_end": "2026-10-11 09:59"}] * 3}
runs = T.merge_runs([], found, "2026-10-09")
check("はじめて見かけた日に、新しい回", runs == [{"floor": "video", "first": "2026-10-09", "last": "2026-10-09", "count": 3, "end": "2026-10-11 09:59", "titles": ["10円セール第1弾"]}], runs)
runs = T.merge_runs(runs, {"video": [{"sale_title": "10円セール第2弾", "sale_end": "2026-10-13 09:59"}] * 5}, "2026-10-10")
check("次の日も見かけたら、同じ回を延ばす（本数はいちばん多い日・終わりは遅いほう・名前は足す）",
      len(runs) == 1 and runs[0]["last"] == "2026-10-10" and runs[0]["count"] == 5 and runs[0]["end"] == "2026-10-13 09:59" and runs[0]["titles"] == ["10円セール第1弾", "10円セール第2弾"])
runs = T.merge_runs(runs, {"video": [], "doujin": [{"sale_title": "", "sale_end": ""}]}, "2026-10-13")
runs = T.merge_runs(runs, {"video": [{"sale_title": "", "sale_end": ""}]}, "2026-10-13")
check("1日より空いたら別の回・売り場ごとに分ける・新しい順", [(r["floor"], r["first"]) for r in runs] == [("video", "2026-10-13"), ("doujin", "2026-10-13"), ("video", "2026-10-09")], runs)
old = [{"floor": "video", "first": "2025-01-01", "last": "2025-01-03", "count": 2, "end": "", "titles": []}, {"floor": "x", "first": "2026-01-01", "last": "2026-01-01"}]
check("400日より前の回・形の違う行は消す", T.merge_runs(old, {}, "2026-10-09") == [])

print("\n■ 保存（1日に数回の確認は、変わったときだけ）")
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "ten_yen.json")
    saved, lines = T.update(NOW, FakeAPI(LISTS), path)
    data = json.load(open(path, encoding="utf-8"))
    raw_text = open(path, encoding="utf-8").read()
    check("保存する（確かめた時刻・売り場ごとの作品・開催の記録）",
          saved and data["checked"] == "2026-10-09 10:15" and len(data["video"]) == 2 and len(data["doujin"]) == 2 and len(data["game"]) == 1
          and {r["floor"] for r in data["runs"]} == {"video", "doujin", "game"}, lines)
    check("1作品・1回を1行に書く（読んで書き直しても同じ）", sum(1 for ln in raw_text.splitlines() if ln.startswith('{"cid"')) == 5 and sum(1 for ln in raw_text.splitlines() if ln.startswith('{"floor"')) == 3 and T.dump(T.load(path)) == raw_text)
    later = NOW.replace(hour=12, minute=15)
    saved, lines = T.update(later, FakeAPI(LISTS), path, if_changed=True)
    check("変わっていなければ保存しない（確かめた時刻も書かない）", not saved and json.load(open(path, encoding="utf-8"))["checked"] == "2026-10-09 10:15", lines)
    saved, _ = T.update(later, FakeAPI({**LISTS, ("digital", "-price"): cheap_video[1:]}), path, if_changed=True)
    data = json.load(open(path, encoding="utf-8"))
    check("変わったら保存する", saved and [r["cid"] for r in data["video"]] == ["abc00002"] and data["checked"] == "2026-10-09 12:15")
    saved, _ = T.update(later.replace(hour=13), FakeAPI(LISTS, fail={("doujin", "rank")}), path)
    data = json.load(open(path, encoding="utf-8"))
    check("最後まで読めなかった売り場は、前の作品のまま", saved and [r["cid"] for r in data["doujin"]] == ["d_200001", "d_200003"])
    saved, _ = T.update(later.replace(day=10, hour=0, minute=5), FakeAPI({}), path)
    data = json.load(open(path, encoding="utf-8"))
    check("毎日の更新は、変わらなくても確かめた時刻を書く・10円の作品が無くなったら空に（開催の記録は残す）",
          saved and data["checked"] == "2026-10-10 00:05" and not data["video"] and not data["doujin"] and not data["game"] and len(data["runs"]) == 3)
    open(path, "w", encoding="utf-8").write("{壊れた")
    try:
        T.update(NOW, FakeAPI(LISTS), path)
        broken = False
    except ValueError:
        broken = True
    check("前のデータが壊れていたら、上書きしない", broken and open(path, encoding="utf-8").read() == "{壊れた")

print(f"\n=== {passed}/{passed + failed} 合格 ===")
sys.exit(1 if failed else 0)
