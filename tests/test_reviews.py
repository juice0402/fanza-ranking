"""FANZAのレビューの評価（get_new_releases.py の parse_review・note_reviews・update_reviews・reviews.json）のテスト。
実行: python3 tests/test_reviews.py（ネットには出ない。APIの答えは作ったもの）"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp()
os.environ["REVIEWS_PATH"] = os.path.join(TMP, "reviews.json")
sys.path.insert(0, ROOT)
import get_new_releases as G  # noqa: E402

G.DMM_INTERVAL_SEC = 0
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


def raw(cid, count=None, avg=None, floor="videoa"):
    x = {"content_id": cid, "service_code": "digital", "floor_code": floor}
    if count is not None:
        x["review"] = {"count": count, "average": avg}
    return x


print("■ APIの review の読み方")
check("{count, average} → [平均×100, 件数]（無い・0件・範囲の外・読めないときは None）",
      G.parse_review(raw("a", 31, "4.71")) == [471, 31] and G.parse_review(raw("a", 2, "5.00")) == [500, 2]
      and G.parse_review(raw("a")) is None and G.parse_review(raw("a", 0, "0.00")) is None
      and G.parse_review(raw("a", 3, "7.5")) is None and G.parse_review(raw("a", "x", "4")) is None and G.parse_review("x") is None)
G.REVIEWS_SEEN.clear()
G.note_reviews([raw("v1", 10, "4.50"), raw("v2"), raw("d1", 5, "4.00", floor="digital_doujin"), "x", {"title": "cid なし"}])
check("どの取得でも、動画（ビデオの売り場）の作品だけためる（レビューの無い作品は None）", G.REVIEWS_SEEN == {"v1": [450, 10], "v2": None}, G.REVIEWS_SEEN)

print("\n■ 毎日の更新")
state = {"updated": "", "cursor": "", "items": {"v2": [400, 3], "gone": [300, 2], "old": [420, 9]}}
calls = []


def fake(params):
    calls.append(params["cid"])
    if params["cid"] == "c3":
        raise RuntimeError("テストの失敗")
    return [raw(params["cid"], 7, "4.20")]


G.REVIEW_REFETCH_PER_RUN = 2
res = G.update_reviews(state, {"v1", "v2", "c1", "c2", "c3", "c4", "old"}, {"v1", "c1", "c2", "c3", "c4"}, "2026-10-10", call=fake)
check("きょう見かけなかった毎日の更新の作品を、品番で決めた本数だけ順番に取り直す（きょう見かけた作品は取り直さない）", calls == ["c1", "c2"] and state["cursor"] == "c2", calls)
check("見かけた評価を足し、レビューが無くなった作品は消し、このサイトに無い作品の評価は消す（見かけなかった作品の評価は残す）",
      state["items"] == {"v1": [450, 10], "c1": [420, 7], "c2": [420, 7], "old": [420, 9]} and res["rated"] == 4, state["items"])
calls.clear()
G.update_reviews(state, {"v1", "c1", "c2", "c3", "c4", "old"}, {"v1", "c1", "c2", "c3", "c4"}, "2026-10-11", call=fake)
check("次の日は、続きから（失敗した作品は飛ばして、次へ）", calls[:2] == ["c3", "c4"], calls)
G.REVIEWS_SEEN.clear()
G.REVIEWS_SEEN.update({"new": [480, 2], "old": None})
st2 = {"updated": "", "cursor": "", "items": {"old": [420, 9], "keep": [300, 1]}}
G.update_reviews(st2, None, set(), "2026-10-11", call=fake)
check("過去作品を読めなかった日（keep が None）は、前から持っている作品だけ更新して、ほかは消さない", st2["items"] == {"keep": [300, 1]}, st2["items"])

print("\n■ reviews.json")
G.save_reviews({"updated": "2026-10-10", "cursor": "c2", "items": {"b": [450, 10], "a": [400, 3]}})
text = open(os.environ["REVIEWS_PATH"], encoding="utf-8").read()
loaded = G.load_reviews()
check("1作品1行・cid の順・読み直すと同じ", text == '{"updated":"2026-10-10","cursor":"c2",\n"items":{\n"a":[400,3],\n"b":[450,10]\n}}\n'
      and loaded == {"updated": "2026-10-10", "cursor": "c2", "items": {"a": [400, 3], "b": [450, 10]}}, text)
open(os.environ["REVIEWS_PATH"], "w", encoding="utf-8").write('{"items":{"a":[99,3],"b":[450,0],"c d":[400,2],"e":[400,2]}}')
check("形の違う行は捨てる", G.load_reviews()["items"] == {"e": [400, 2]})
open(os.environ["REVIEWS_PATH"], "w", encoding="utf-8").write("{壊れた")
check("壊れていたら空から（評価は、また集まる）", G.load_reviews()["items"] == {})

print(f"\n=== {passed}/{passed + failed} 合格 ===")
sys.exit(1 if failed else 0)
