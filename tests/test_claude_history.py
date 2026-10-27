"""女優の歩みの紹介文を書く道具（scripts/claude_history.py）のテスト。実行: python3 tests/test_claude_history.py
（名前・数字は、どれも作ったもの）"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp()
HIST = os.path.join(tmp, "actress_history.json")
STORIES = os.path.join(tmp, "actress_stories.json")
os.environ["ACTRESS_HISTORY_PATH"] = HIST
os.environ["ACTRESS_STORIES_PATH"] = STORIES
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import claude_history as C  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


row = {
    "name": "花子", "checked": "2026-10-27", "total": 277, "upcoming": 3,
    "first": {"c": "abc00001", "d": "2018-04-14", "m": "メーカーA", "t": "タイトル"},
    "latest": {"c": "abc00200", "d": "2026-10-23", "m": "メーカーA", "t": "タイトル"},
    "years": {"2018": {"n": 6, "m": [["メーカーA", 6]]}, "2025": {"n": 59, "m": [["メーカーA", 54], ["メーカーB", 4]]}},
    "makers": [{"m": "メーカーA", "n": 248, "f": "2018-04-14", "c": "abc00001"}, {"m": "メーカーB", "n": 18, "f": "2019-12-14", "c": "b1"}],
    "milestones": [{"c": "m1", "d": "2023-09-22", "m": "メーカーA", "t": "x", "n": 100}],
    "vr": {"n": 24, "first": {"c": "v1", "d": "2021-11-25", "m": "メーカーA", "t": "x"}},
    "best": 129, "solo": 97, "costars": [["月子", 4]], "genres": [["美少女", 117]],
}
json.dump({"actresses": {"1": row, "2": dict(row, name="月子"), "3": {"name": "数字の無い人", "checked": "2026-10-27", "total": 0}}}, open(HIST, "w"))

print("■ 書く人の選び方")
rows = C.history_rows()
check("本数のある人だけ", set(rows) == {"花子", "月子"})
check("まだの人（このサイトの本数が多い順）", C.pick(rows, {}, "2026-10-28", 5, counts={"花子": 3, "月子": 9}) == ["月子", "花子"])
old = {"花子": {"text": "x", "written": "2026-06-01"}, "月子": {"text": "x", "written": "2026-10-01"}}
check("90日より前に書いて、そのあと集め直された人は書き直す", C.pick(rows, old, "2026-10-28", 5, counts={}) == ["花子"])

print("■ 紹介文の点検")
good = "花子さんのFANZAの作品は277本で、いちばん古いのは2018年4月のメーカーAの作品です。2025年は59本と多く、100本目は2023年9月でした。VR作品は24本あります。"
check("数字が facts のとおりなら通る", C.story_problems("花子", good, rows, {}) == [], C.story_problems("花子", good, rows, {}))
check("facts に無い数字は断る", any("無い数字" in p for p in C.story_problems("花子", good.replace("277本", "300本"), rows, {})))
check("「デビュー」と言い切る言い方は断る", any("デビュー" in p for p in C.story_problems("花子", good.replace("いちばん古いのは", "デビューは"), rows, {})))
check("私生活・確かめられないことは断る", any("引退" in p for p in C.story_problems("花子", good + "引退も近い。", rows, {})))
check("あおる言葉は断る", any("あおる" in p for p in C.story_problems("花子", good.replace("多く", "大人気の年で"), rows, {})))
check("名前が無いと断る", any("名前" in p for p in C.story_problems("花子", good.replace("花子さんの", "この人の"), rows, {})))
check("短すぎると断る", any("文字数" in p for p in C.story_problems("花子", "花子さんは277本。", rows, {})))
json.dump({"actresses": {"1": row, "2": dict(row, name="月子"), "4": dict(row, name="星子（星子2）")}}, open(HIST, "w"))
check("かっこの別名は外した名前で書いてよい", C.story_problems("星子（星子2）", good.replace("花子", "星子"), C.history_rows(), {}) == [], C.story_problems("星子（星子2）", good.replace("花子", "星子"), C.history_rows(), {}))
json.dump({"actresses": {"1": row, "2": dict(row, name="月子"), "3": {"name": "数字の無い人", "checked": "2026-10-27", "total": 0}}}, open(HIST, "w"))
rows = C.history_rows()
check("かんま入りの本数も読める", C.numbers_in("1,234本と2018年", []) == {1234, 2018})
same = {"月子": {"text": good.replace("花子", "月子"), "written": "2026-10-27"}}
check("ほかの人と同じ書き出しは断る（名前は入れかえて比べる）", any("書き出し" in p for p in C.story_problems("花子", good, rows, same)))

print("■ 書き込み（apply）")
inp = os.path.join(tmp, "in.json")
json.dump([{"name": "花子", "text": good}], open(inp, "w"))
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "claude_history.py"), "apply", inp, "--today", "2026-10-28"], capture_output=True, text=True, env=os.environ)
saved = json.load(open(STORIES))
check("問題が無ければ書き込む（書いた日・数えた日つき）", r.returncode == 0 and saved["stories"]["花子"]["written"] == "2026-10-28" and saved["stories"]["花子"]["checked"] == "2026-10-27", r.stdout + r.stderr)
json.dump([{"name": "月子", "text": good.replace("花子", "月子")}, {"name": "だれか", "text": good}], open(inp, "w"))
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "claude_history.py"), "apply", inp], capture_output=True, text=True, env=os.environ)
check("1件でも問題があれば何も書き込まない", r.returncode == 1 and set(json.load(open(STORIES))["stories"]) == {"花子"}, r.stdout)
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "claude_history.py"), "list", "--today", "2026-10-28"], capture_output=True, text=True, env=os.environ)
lst = json.loads(r.stdout)
check("list は書いていない人を、タイトル抜きで出す", r.returncode == 0 and [a["name"] for a in lst["actresses"]] == ["月子"] and "タイトル" not in r.stdout, r.stdout[:300])

print(f"\n=== {passed}/{passed + failed} 合格 ===")
sys.exit(1 if failed else 0)
