"""女優の歩みを集める道具（scripts/actress_history.py）のテスト。実行: python3 tests/test_actress_history.py
（ネットには出ない。APIの答えは、作った作品で差し替える。名前・タイトルは、どれも作ったもの）"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import actress_history as H  # noqa: E402

H.G.DMM_INTERVAL_SEC = 0
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


def work(n, date, maker="メーカーA", cast=("花子",), genres=(), title=None):
    return {"cid": f"abc{n:05d}", "title": title or f"作品{n}", "date": f"{date} 10:00:00", "maker": maker, "actress": list(cast), "genres": list(genres), "tags": []}


print("■ 1人分のまとめ（summarize）")
items = [work(i, f"20{18 + i // 40}-0{1 + i % 9}-1{i % 10}", maker="メーカーA" if i < 70 else "メーカーB") for i in range(120)]
items.append(work(500, "2026-12-01"))  # 予約（発売前）
items.append(items[0])  # 同じ作品が2回（ページの境目）
items.append(work(501, "2025-05-05", maker="メーカーC", cast=("花子", "月子"), genres=("ベスト・総集編",), title="【VR】作品501"))
items.append(work(502, "2025-05-06", maker="メーカーC", cast=("花子", "月子", "星子")))
items.append(work(503, "2025-05-07", maker="不明", cast=("花子", "月子")))
items.append(work(504, "2025-05-08", maker="メーカーC", cast=tuple(f"人{k}" for k in range(5)) + ("花子",)))  # 5人以上は共演に数えない
s = H.summarize("花子", items, "2026-10-27")
check("発売済みの本数・予約は別（同じ作品は1回）", s["total"] == 124 and s["upcoming"] == 1, (s["total"], s["upcoming"]))
check("いちばん古い作品・いちばん新しい作品", s["first"]["c"] == "abc00000" and s["first"]["d"] == "2018-01-10" and s["latest"]["d"] == max(H.G.day_key(i["date"]) for i in items if H.G.day_key(i["date"]) <= "2026-10-27"), (s["first"], s["latest"]))
check("年ごとの本数とメーカー（「不明」は名前に出さない）", sum(y["n"] for y in s["years"].values()) == 124 and all(m != "不明" for y in s["years"].values() for m, _ in y["m"]) and list(s["years"]) == sorted(s["years"]))
check("100本目の節目（発売日の古い順）", [m["n"] for m in s["milestones"]] == [100] and s["milestones"][0]["c"], s["milestones"])
check("メーカーごと（多い順・はじめての日）", s["makers"][0]["m"] == "メーカーA" and s["makers"][0]["n"] == 70 and s["makers"][0]["f"] == "2018-01-10", s["makers"][:2])
check("VR（タイトルの【VR】）の本数と、はじめてのVR", s["vr"]["n"] == 1 and s["vr"]["first"]["c"] == "abc00501")
check("ベスト・総集編・単体の本数", s["best"] == 1 and s["solo"] == 120, (s["best"], s["solo"]))
check("よく共演している人（2本以上・4人までの作品だけ）", s["costars"] == [["月子", 3]], s["costars"])
check("ジャンルは、ベスト・総集編を除く", all(g != "ベスト・総集編" for g, _ in s["genres"]))
empty = H.summarize("花子", [work(1, "2027-01-01")], "2026-10-27")
check("発売済みが無いときは本数だけ", empty["total"] == 0 and empty["upcoming"] == 1 and "first" not in empty)

print("■ 読む人の順番（pick_targets）")
profiles = [{"id": 1, "name": "花子"}, {"id": 2, "name": "月子"}, {"id": 3, "name": "星子"}, {"id": 4, "name": "少ない人"}, {"id": 5, "name": "古い人"}]
counts = {"花子": 30, "月子": 50, "星子": 20, "少ない人": 3, "古い人": 40}
history = {"3": {"checked": "2026-10-20"}, "5": {"checked": "2026-09-01"}}
order = [n for _, n in H.pick_targets(profiles, counts, history, "2026-10-27")]
check("まだの人（本数の多い順）→ 古くなった人。少ない人・新しい人は入れない", order == ["月子", "花子", "古い人"], order)

print("■ 全作品を読む（fetch_all）と、保存（run）")
calls = []
tops = []


def fake_call(endpoint, params):
    if params["sort"] != "date":  # 人気順・評価順（fetch_tops）
        tops.append(params["sort"])
        rows = [{"content_id": f"t{k}", "title": "女子校生の作品" if k == 0 else f"人気{k}", "date": "2024-02-01 10:00:00",
                 "affiliateURL": f"https://al.dmm.co.jp/?lurl=t{k}", "imageURL": {"large": f"https://pics.dmm.co.jp/t{k}.jpg"},
                 "iteminfo": {"maker": [{"name": "メーカーA"}], "actress": [{"name": "花子"}]},
                 **({"review": {"count": 5, "average": "4.50"}} if k % 2 else {})} for k in range(15)]
        return {"total_count": 15, "items": rows}
    calls.append(params["offset"])
    total = 250
    start = params["offset"]
    rows = [{"content_id": f"x{k:05d}", "title": f"作品{k}", "date": f"2024-01-{1 + k % 28:02d} 10:00:00", "iteminfo": {"maker": [{"name": "メーカーA"}], "actress": [{"name": "花子"}]}} for k in range(start, min(start + 99, total) + 1)]
    return {"total_count": total, "items": rows}


got, n = H.fetch_all(1, 10, call=fake_call)
check("100本ずつ3回で250本", n == 3 and len(got) == 250 and calls == [1, 101, 201], (n, len(got or []), calls))
calls.clear()
got, n = H.fetch_all(1, 2, call=fake_call)
check("予算が足りないときは、本数だけ見て次に回す", got is None and n == 1 and calls == [1])

with tempfile.TemporaryDirectory() as d:
    H.PATH = os.path.join(d, "actress_history.json")
    H.DATA_DIR_ORIG = H.DATA_DIR
    os.makedirs(os.path.join(d, "catalog"))
    json.dump({"actresses": [{"id": 1, "name": "花子"}, {"id": 2, "name": "月子"}]}, open(os.path.join(d, "actresses.json"), "w"))
    json.dump([{"cid": f"a{k}", "actress": ["花子"] if k < 12 else ["月子"]} for k in range(24)], open(os.path.join(d, "new_releases.json"), "w"))
    H.DATA_DIR = d
    done = H.run("2026-10-27", max_calls=6, sleep=lambda s: None, call=fake_call)
    saved = json.load(open(H.PATH))
    check("予算の中で読めた人だけ保存（全作品3回＋人気順・評価順2回で1人・残り1回では次の人は読めない）", done == 1 and list(saved["actresses"]) in (["1"], ["2"]) and saved["updated"] == "2026-10-27", (done, list(saved["actresses"])))
    one = next(iter(saved["actresses"].values()))
    pop, rated = one.get("popular") or [], one.get("rated") or []
    check("人気順・評価順を1回ずつ読む", tops == ["rank", "review"], tops)
    check("人気順は10本まで・未成年を連想させるタイトルは入れない・表示に要るものだけ", len(pop) == 10 and pop[0]["c"] == "t1" and all(set(r) <= {"c", "t", "d", "a", "m", "i", "u", "v", "rv"} for r in pop), pop[:1])
    check("評価順は、レビューのある作品だけ（★の平均×100と件数）", len(rated) == 7 and all(r["rv"] == [450, 5] for r in rated), [r["c"] for r in rated])

    ticks = iter([0, 0, 999, 999, 999])
    os.remove(H.PATH)
    done = H.run("2026-10-27", max_calls=100, sleep=lambda s: None, call=fake_call, max_minutes=1, clock=lambda: next(ticks))
    check("時間の上限をこえたら、そこまでで止めて保存する", done == 1 and len(json.load(open(H.PATH))["actresses"]) == 1, done)

    def broken(endpoint, params):
        raise RuntimeError("つながらない")

    before = open(H.PATH).read()
    done = H.run("2026-10-27", max_calls=10, sleep=lambda s: None, call=broken)
    check("読めなかった人は保存しない（前のデータのまま）", done == 0 and open(H.PATH).read() == before)
    H.DATA_DIR = H.DATA_DIR_ORIG

print(f"\n=== {passed}/{passed + failed} 合格 ===")
sys.exit(1 if failed else 0)
