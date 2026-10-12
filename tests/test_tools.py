"""Claude のトークンを節約する道具のテスト（2026-10-13。運営者の希望「クロードのトークンをできるだけ節約したい。サイトが確実に運用されることが優先」）。
  - scripts/wait_run.py   … GitHub の実行（毎日の更新・CI・公開）が終わるまで待って、結果を1行で出す
  - scripts/quiet_step.sh … テストの出力を、成功は1行・失敗だけくわしく
  - claude_comments.dumps_lines … list の出力を1行に1件の JSON に
実行: python3 tests/test_tools.py（ネットには出ない。GitHub への問い合わせは、にせものに差しかえる）"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import claude_comments as cc  # noqa: E402
import wait_run as W  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


class FakeGh:
    """gh api のにせもの。path の始まりで答えを決める（答えが関数なら、呼んだ回数を渡す）"""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, path, method="GET", fields=()):
        self.calls.append((path, method, list(fields)))
        for key, ans in self.answers.items():
            if key in path:
                if isinstance(ans, Exception):
                    raise ans
                return ans(len([c for c in self.calls if key in c[0]])) if callable(ans) else ans
        raise W.ApiError("知らない問い合わせ: " + path)


def use(fake):
    W.gh = fake
    return fake


class Clock:
    def __init__(self):
        self.t = 0.0
        self.slept = 0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s
        self.slept += 1


class Seq:
    """poll の答えを、順番に返す"""
    name = "テスト"

    def __init__(self, *answers):
        self.answers = list(answers)

    def poll(self):
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return a


print("━━ 待つ道具（scripts/wait_run.py の wait）")
c = Clock()
code, line = W.wait(Seq(("wait", "動いています"), ("wait", "動いています"), ("ok", "成功")), wait_max=540, step=30, now=c.now, sleep=c.sleep)
check("終わるまで待って、成功なら 0 と1行", code == 0 and line.startswith("✅ テスト: 成功") and "1分00秒" in line and c.slept == 2, (code, line))
c = Clock()
code, line = W.wait(Seq(("wait", "x"), ("fail", "failure（理由: テストの失敗）")), wait_max=540, step=30, now=c.now, sleep=c.sleep)
check("失敗なら 1 と理由", code == 1 and line == "❌ テスト: failure（理由: テストの失敗）", (code, line))
c = Clock()
code, line = W.wait(Seq(("wait", "公開が動いています")), wait_max=540, step=30, now=c.now, sleep=c.sleep)
check("決めた時間（9分）をこえそうなら、待つのをやめて 3（もう一度）", code == 3 and line.startswith("⏳ テスト: 公開が動いています") and c.t <= 540, (code, line, c.t))
c = Clock()
code, line = W.wait(Seq(W.ApiError("502"), ("ok", "成功")), wait_max=540, step=30, now=c.now, sleep=c.sleep)
check("GitHub に1回聞けなくても、聞き直して続ける", code == 0, (code, line))
c = Clock()
code, line = W.wait(Seq(W.ApiError("502")), wait_max=540, step=30, now=c.now, sleep=c.sleep)
check("3回続けて聞けなければ 2", code == 2 and "GitHub に聞けませんでした" in line and c.slept == 2, (code, line, c.slept))
c = Clock()
code, line = W.wait(Seq(("ok", "済んでいます")), wait_max=540, step=30, now=c.now, sleep=c.sleep)
check("はじめから終わっていれば、待たない", code == 0 and c.slept == 0 and "0秒" in line, (code, line))

print("━━ CI（check）")
SHA = "0123456789abcdef0123456789abcdef01234567"
run = lambda **k: dict({"id": 7, "name": "check", "status": "completed", "conclusion": "success", "started_at": "2026-10-13T00:00:00Z", "html_url": "https://github.com/x"}, **k)
use(FakeGh({"/check-runs?": {"check_runs": []}}))
check("CI が始まっていなければ待つ", W.Ci(SHA).poll()[0] == "wait")
use(FakeGh({"/check-runs?": {"check_runs": [run(name="Cloudflare Pages", status="queued", conclusion=None), run(status="in_progress", conclusion=None)]}}))
check("動いていれば待つ（check 以外の名前は見ない）", W.Ci(SHA).poll() == ("wait", "CI が動いています"))
use(FakeGh({"/check-runs?": {"check_runs": [run(name="Cloudflare Pages", status="queued", conclusion=None), run()]}}))
check("check が成功なら ok", W.Ci(SHA).poll() == ("ok", "成功"))
fake = use(FakeGh({"/check-runs?": {"check_runs": [run(conclusion="failure")]},
                   "/check-runs/7/annotations": [{"message": "❌ tests/test_data.py\n  ❌ 形が違う"}, {"message": "Process completed with exit code 1."}]}))
state, msg = W.Ci(SHA).poll()
check("失敗なら、注釈（失敗の理由）を短く添える", state == "fail" and msg.startswith("failure（理由: ❌ tests/test_data.py / ❌ 形が違う / Process completed"), msg)
use(FakeGh({"/check-runs?": {"check_runs": [run(conclusion="failure", started_at="2026-10-13T00:00:00Z"), run(id=8, started_at="2026-10-13T01:00:00Z")]}}))
check("同じコミットで何回か動いたら、いちばん新しい結果", W.Ci(SHA).poll()[0] == "ok")

print("━━ 公開（Deploy）")
dep = lambda sha, created, status="completed", conclusion="success", rid=1: {"id": rid, "head_sha": sha, "created_at": created, "status": status, "conclusion": conclusion, "html_url": "https://github.com/run"}
OTHER = "fedcba9876543210fedcba9876543210fedcba98"
use(FakeGh({"deploy.yml/runs": {"workflow_runs": [dep(OTHER, "2026-10-13T00:00:00Z")]}}))
check("その Merge の公開がまだ無ければ待つ", W.Deploy(SHA).poll()[0] == "wait")
use(FakeGh({"deploy.yml/runs": {"workflow_runs": [dep(SHA, "2026-10-13T01:00:00Z", status="in_progress", conclusion=None)]}}))
check("動いていれば待つ", W.Deploy(SHA).poll() == ("wait", "公開が動いています"))
use(FakeGh({"deploy.yml/runs": {"workflow_runs": [dep(SHA, "2026-10-13T01:00:00Z")]}}))
check("成功なら ok（短いコミットの印でも探せる）", W.Deploy(SHA[:7]).poll() == ("ok", "成功（本番に公開済み）"))
use(FakeGh({"deploy.yml/runs": {"workflow_runs": [dep(OTHER, "2026-10-13T01:05:00Z"), dep(SHA, "2026-10-13T01:00:00Z", conclusion="cancelled")]}}))
state, msg = W.Deploy(SHA).poll()
check("取り消し（あとの Merge）なら、いちばん新しい公開の結果", state == "ok" and "あとの Merge の公開に含まれて" in msg, msg)
use(FakeGh({"deploy.yml/runs": {"workflow_runs": [dep(OTHER, "2026-10-13T01:05:00Z", status="in_progress", conclusion=None), dep(SHA, "2026-10-13T01:00:00Z", conclusion="cancelled")]}}))
check("あとの公開が動いていれば待つ", W.Deploy(SHA).poll()[0] == "wait")
use(FakeGh({"deploy.yml/runs": {"workflow_runs": [dep(SHA, "2026-10-13T01:00:00Z", conclusion="cancelled")]}}))
check("あとの公開も無い取り消しは失敗", W.Deploy(SHA).poll()[0] == "fail")
use(FakeGh({"deploy.yml/runs": {"workflow_runs": [dep(SHA, "2026-10-13T01:00:00Z", conclusion="failure", rid=9)]},
            "/runs/9/jobs": {"jobs": [{"steps": [{"name": "Build", "conclusion": "success"}, {"name": "Verify every page", "conclusion": "failure"}]}]}}))
state, msg = W.Deploy(SHA).poll()
check("失敗なら、失敗した手順の名前と「前の公開のまま」", state == "fail" and "Verify every page" in msg and "前の公開のまま" in msg, msg)

print("━━ 今日の更新（update.yml）")
W.today_jst = lambda: "2026-10-13"
check("日本時間の日付（UTC の 15:21 は次の日）", W.jst_date("2026-10-12T15:21:15Z") == "2026-10-13" and W.jst_date("2026-10-12T14:59:59Z") == "2026-10-12" and W.jst_date(None) == "")
fake = use(FakeGh({}))
check("記録に今日の更新があれば、GitHub に聞かずに ok", W.Update(updated=lambda: True).poll()[0] == "ok" and fake.calls == [])
upd = lambda created, status="completed", conclusion="success": {"created_at": created, "status": status, "conclusion": conclusion}
use(FakeGh({"update.yml/runs": {"workflow_runs": [upd("2026-10-12T15:21:15Z", status="in_progress", conclusion=None)]}}))
check("更新が動いていれば待つ", W.Update(updated=lambda: False).poll() == ("wait", "更新が動いています"))
fake = use(FakeGh({"update.yml/runs": {"workflow_runs": [upd("2026-10-12T15:21:15Z")]}}))
state, msg = W.Update(updated=lambda: False).poll()
check("今日の更新が成功で終わっていれば（保存するものが無かった）、もう一度動かさない", state == "ok" and not any("dispatches" in c[0] for c in fake.calls), msg)
use(FakeGh({"update.yml/runs": {"workflow_runs": [upd("2026-10-12T15:21:15Z", conclusion="failure"), upd("2026-10-11T15:21:15Z")]}}))
state, msg = W.Update(updated=lambda: False).poll()
check("今日の更新が失敗していれば、動かし直さずに失敗（いまのデータのまま続ける）", state == "fail" and "failure" in msg, msg)
fake = use(FakeGh({"update.yml/runs": {"workflow_runs": [upd("2026-10-11T15:21:15Z")]}, "update.yml/dispatches": None}))
u = W.Update(updated=lambda: False)
first, second = u.poll(), u.poll()
dispatches = [c for c in fake.calls if "dispatches" in c[0]]
check("今日の更新が無ければ、1回だけ動かして待つ", first[0] == "wait" and second[0] == "wait" and len(dispatches) == 1
      and dispatches[0][1] == "POST" and dispatches[0][2] == [("ref", "main")], (first, second, dispatches))

print("━━ 使い方")
check("コミットの印の形", W.valid_sha("0123abc") and W.valid_sha(SHA) and not W.valid_sha("main") and not W.valid_sha("abc") and not W.valid_sha("0123abc;rm"))
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "wait_run.py"), "ci", "main"], capture_output=True, text=True)
check("間違った使い方は 2 で、GitHub に聞かない", r.returncode == 2 and "使い方" in r.stdout, r.stdout)
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "wait_run.py")], capture_output=True, text=True)
check("何も渡さなければ使い方", r.returncode == 2 and "update | ci" in r.stdout, r.stdout)
src = open(os.path.join(ROOT, "scripts", "wait_run.py"), encoding="utf-8").read()
check("1回に待つのは Bash の上限（10分）より短い", W.WAIT_MAX + W.STEP < 600 and 'os.environ.get("WAIT_MAX", "540")' in src)

print("━━ テストの出力を静かに（scripts/quiet_step.sh）")
script = """
failed=0; verbose=0
. scripts/quiet_step.sh
run "うまくいくテスト" bash -c 'for i in $(seq 1 300); do echo "  ✅ 点検$i"; done'
run "失敗するテスト" bash -c 'echo "  ✅ よい点検"; echo "  ❌ 悪い点検 → 理由"; for i in $(seq 1 100); do echo "行$i"; done; exit 1' || echo "返り値は1"
echo "failed=$failed"
"""
r = subprocess.run(["bash", "-c", script], cwd=ROOT, capture_output=True, text=True)
out = r.stdout.splitlines()
check("成功したテストは1行だけ", out[0] == "✅ うまくいくテスト" and "点検1" not in r.stdout, out[:3])
check("失敗したテストは ❌ の行と、出力の後ろだけ", out[1] == "❌ 失敗するテスト" and any(l.strip() == "❌ 悪い点検 → 理由" for l in out) and "   行100" in out and "   行50" not in out and "よい点検" not in r.stdout, out)
check("失敗すると failed=1 になり、1 を返す", "返り値は1" in out and out[-1] == "failed=1", out[-3:])
r = subprocess.run(["bash", "-c", script.replace("verbose=0", "verbose=1")], cwd=ROOT, capture_output=True, text=True)
check("--verbose のときは、前と同じく全部出す", "━━ うまくいくテスト" in r.stdout and "  ✅ 点検300" in r.stdout and "行50" in r.stdout and r.stdout.strip().endswith("failed=1"))
chk = open(os.path.join(ROOT, "scripts", "check.sh"), encoding="utf-8").read()
check("GitHub Actions（CI）では全部出す（失敗の注釈・記録のため）", '[ -n "${CI:-}" ] && verbose=1' in chk and "--verbose" in chk)
listed = set(l.split()[-1] for l in chk.splitlines() if l.strip().startswith(("run ", "if run ")) and "tests/" in l)
tests = set(f"tests/{f}" for f in os.listdir(os.path.join(ROOT, "tests")) if f.startswith("test_") and f.endswith((".py", ".mjs")))
check("tests/ のテストが、すべて check.sh に入っている", tests <= listed, sorted(tests - listed))

print("━━ list の出力（1行に1件。claude_comments.dumps_lines）")
sample = {"today": "2026-10-13", "total_pending": 3, "floor_pending": {"doujin": 1}, "items": [{"cid": "a", "genres": ["OL", "ドラマ"], "draft": "下書き。"}, {"cid": "b", "title": "x\"y"}],
          "trend": {"total": 5, "genres": [{"name": "OL", "count": 2}], "popular": []}, "empty": [], "none": None}
text = cc.dumps_lines(sample)
check("読みこむと前と同じ中身", json.loads(text) == sample, text)
lines = text.splitlines()
check("作品は1行に1件", '{"cid":"a","genres":["OL","ドラマ"],"draft":"下書き。"},' in lines and '{"cid":"b","title":"x\\"y"}' in lines, lines)
check("字下げの空白を入れない", not any(l.startswith(" ") for l in lines), lines)
check("前の形（indent=1）より短い", len(text) < len(json.dumps(sample, ensure_ascii=False, indent=1)))
for name in ("claude_comments.py", "claude_roundups.py", "claude_monthly.py"):
    s = open(os.path.join(ROOT, "scripts", name), encoding="utf-8").read()
    check(f"{name} の list は dumps_lines で出す", "dumps_lines(" in s and "indent=1))" not in s)

print("━━ CLAUDE.md の長さ（毎回の会話で自動で読み込まれるので、短く保つ）")
md = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
check("CLAUDE.md は2万文字まで（くわしいことは docs/architecture.md へ）", len(md) <= 20000, len(md))
check("CLAUDE.md から docs/architecture.md へ案内している", "docs/architecture.md" in md and os.path.exists(os.path.join(ROOT, "docs", "architecture.md")))
check("守ることは CLAUDE.md に残す", "## 守ること" in md and "DMM_CREDIT_HTML" in md and "main へ直接 push しない" in md)

print()
print(f"結果: {passed} 成功 / {failed} 失敗")
sys.exit(1 if failed else 0)
