"""見張り（scripts/mihari.py・.github/workflows/mihari.yml。2026-11-02）のテスト。
実行: python3 tests/test_mihari.py（ネットには出ない。GitHub の答えは作ったもの）"""
import io
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import mihari as M  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


NOW = datetime(2026, 11, 2, 4, 0, tzinfo=timezone.utc)  # 日本時間 11/2 13:00

print("━━ 結果の見分け")
check("failure・timed_out は issue", M.kind("failure") == "fail" and M.kind("timed_out") == "fail")
check("success は閉じる", M.kind("success") == "ok")
check("cancelled・skipped は何もしない", M.kind("cancelled") is None and M.kind("skipped") is None and M.kind(None) is None)
check("path からファイルの名前", M.workflow_file({"path": ".github/workflows/deploy.yml"}) == "deploy.yml")
check("時刻は日本時間で", M.when("2026-11-01T15:36:41Z") == "11月2日 0:36（日本時間）", M.when("2026-11-01T15:36:41Z"))

print("━━ 注記")
notes = [
    {"annotation_level": "warning", "title": "", "message": "Node.js 20 is deprecated."},
    {"annotation_level": "failure", "title": "", "message": "Process completed with exit code 1."},
    {"annotation_level": "failure", "title": "", "message": "点検: 作品ページの広告表記が無い\n（3件）"},
    {"annotation_level": "warning", "title": "見張り番", "message": "公開（deploy.yml）がこの7日に 5 回失敗しています"},
    {"annotation_level": "failure", "title": "", "message": "あ" * 300},
    {"annotation_level": "failure", "title": "", "message": "4つめ"},
]
f, w = M.pick_notes(notes)
check("失敗の注記は3つまで・exit code の行は後ろ", f[0] == "点検: 作品ページの広告表記が無い （3件）" and len(f) == 3 and "Process completed" not in " ".join(f), f)
check("1つ200字まで", len(f[1]) == 200 and f[1].endswith("…"), len(f[1]))
check("見張り番の題が無いときは注意を出さない", w == [])
f, w = M.pick_notes(notes, "見張り番")
check("見張り番の注意だけ拾う（Node の注意は拾わない）", w == ["公開（deploy.yml）がこの7日に 5 回失敗しています"], w)

print("━━ 失敗したところ")
jobs = [{"name": "deploy", "conclusion": "failure", "steps": [
    {"name": "Set up", "conclusion": "success"}, {"name": "Build and verify", "conclusion": "failure"}, {"name": "Upload", "conclusion": "skipped"}]},
    {"name": "other", "conclusion": "success", "steps": []}]
check("ジョブとステップの名前", M.failed_parts(jobs) == ["deploy / Build and verify"], M.failed_parts(jobs))

print("━━ 最後の成功と、そのあとの失敗")
runs = [{"id": 9, "status": "completed", "conclusion": "failure", "updated_at": "2026-11-02T03:00:00Z"},
        {"id": 8, "status": "completed", "conclusion": "cancelled", "updated_at": "2026-11-02T02:00:00Z"},
        {"id": 7, "status": "completed", "conclusion": "timed_out", "updated_at": "2026-11-02T01:00:00Z"},
        {"id": 6, "status": "completed", "conclusion": "success", "updated_at": "2026-11-01T15:36:41Z"},
        {"id": 5, "status": "completed", "conclusion": "failure", "updated_at": "2026-11-01T10:00:00Z"}]
check("cancelled は数えない", M.history(runs, 9) == ("2026-11-01T15:36:41Z", 2), M.history(runs, 9))
check("前の実行を見るときは、それより新しいものを数えない", M.history(runs, 5) == (None, 1), M.history(runs, 5))

print("━━ 本文")
cfg = M.WATCH["deploy.yml"]
run = {"id": 9, "html_url": "https://github.com/x/actions/runs/9", "conclusion": "failure", "updated_at": "2026-11-02T03:00:00Z"}
body = M.build_body(cfg, run, ["deploy / Build and verify"], ["点検で止まった"], [], "2026-11-01T15:36:41Z", 2)
check("何が止まったか・いつ・URL・最後の成功・失敗したところ・注記・署名", all(s in body for s in [
    "本番のサイトが前のままに", "11月2日 12:00（日本時間）", "https://github.com/x/actions/runs/9", "最後にうまくいったのは 11月2日 0:36（日本時間）",
    "失敗は 2 回", "deploy / Build and verify", "- 点検で止まった", "「公開が止まってる」"]) and body.endswith(M.SIGN), body)

print("━━ 今日もう知らせたか")
check("issue を今日作った", M.noted_today({"created_at": "2026-11-01T16:00:00Z"}, [], NOW))
check("きのう作って、今日のコメントなし", not M.noted_today({"created_at": "2026-11-01T14:00:00Z"}, [], NOW))
check("今日、見張りがコメントした", M.noted_today({"created_at": "2026-10-30T00:00:00Z"}, [{"user": {"login": M.BOT}, "created_at": "2026-11-02T01:00:00Z"}], NOW))
check("人のコメントは数えない", not M.noted_today({"created_at": "2026-10-30T00:00:00Z"}, [{"user": {"login": "juice0402"}, "created_at": "2026-11-02T01:00:00Z"}], NOW))
check("日本時間の0時（UTC）", M.midnight_utc(NOW) == "2026-11-01T15:00:00Z", M.midnight_utc(NOW))


def fake(answers):
    """GitHub の答えを作る。呼ばれた (method, path, body) を calls に残す"""
    calls = []

    def gh(path, method="GET", body=None):
        calls.append((method, path, body))
        for key, val in answers.items():
            if method == key[0] and path.startswith(key[1]):
                if isinstance(val, Exception):
                    raise val
                return val
        return None
    return gh, calls


def run_handle(run, answers, dry=False, runs=None):
    gh, calls = fake(answers)
    M.gh = gh
    buf = io.StringIO()
    with redirect_stdout(buf):
        M.handle(run, dry, NOW, runs)
    return calls, buf.getvalue()


R = f"repos/{M.REPO}"
base = {"path": ".github/workflows/deploy.yml", "head_branch": "main", "id": 9, "html_url": "https://github.com/x/actions/runs/9",
        "updated_at": "2026-11-02T03:00:00Z"}
open_issue = {"number": 12, "title": cfg["title"], "created_at": "2026-11-01T10:00:00Z"}
fail_answers = {("GET", f"{R}/issues?"): [],
                ("GET", f"{R}/actions/runs/9/jobs"): {"jobs": [dict(jobs[0], check_run_url="https://api.github.com/x/check-runs/55")]},
                ("GET", f"{R}/check-runs/55/annotations"): notes,
                ("GET", f"{R}/actions/workflows/deploy.yml/runs"): {"workflow_runs": runs},
                ("GET", f"{R}/labels/mihari"): M.ApiError("gh: Not Found (HTTP 404)")}

print("━━ 動き（GitHub の答えは作ったもの）")
calls, log = run_handle(dict(base, conclusion="cancelled"), {})
check("cancelled は GitHub に何も聞かない", calls == [] and "何もしない" in log, calls)
calls, log = run_handle(dict(base, conclusion="failure", head_branch="claude/x"), {})
check("main 以外は何もしない", calls == [], calls)
calls, log = run_handle(dict(base, path=".github/workflows/ci.yml", conclusion="failure"), {})
check("見張っていない workflow は何もしない", calls == [], calls)

calls, log = run_handle(dict(base, conclusion="failure"), fail_answers)
posts = [c for c in calls if c[0] == "POST"]
check("失敗 → ラベルを作って issue を作る", [p[1] for p in posts] == [f"{R}/labels", f"{R}/issues"] and posts[0][2]["color"] == "d93f0b", posts)
made = posts[-1][2] if posts else {}
check("issue の題・ラベル・本文", made.get("title") == "【見張り】公開が失敗した" and made.get("labels") == ["mihari"]
      and "点検: 作品ページの広告表記が無い" in made.get("body", "") and "失敗は 2 回" in made.get("body", ""), made)

calls, log = run_handle(dict(base, conclusion="failure"), fail_answers, dry=True)
check("ためし（dry_run）は書かずに題と本文を出す", not [c for c in calls if c[0] != "GET"] and "【見張り】公開が失敗した" in log and M.SIGN in log, log)

calls, log = run_handle(dict(base, conclusion="failure"), {("GET", f"{R}/issues?"): [open_issue], ("GET", f"{R}/issues/12/comments"): []})
posts = [c for c in calls if c[0] == "POST"]
check("開いた issue がある → 新しく作らず「まだ続いている」を1つ", len(posts) == 1 and posts[0][1] == f"{R}/issues/12/comments"
      and posts[0][2]["body"].startswith("まだ続いている（https://github.com/x/actions/runs/9"), posts)
check("今日のコメントだけ聞く", any("since=2026-11-01T15:00:00Z" in c[1] for c in calls), calls)

calls, log = run_handle(dict(base, conclusion="failure"), {("GET", f"{R}/issues?"): [open_issue],
                                                           ("GET", f"{R}/issues/12/comments"): [{"user": {"login": M.BOT}, "created_at": "2026-11-02T00:00:00Z"}]})
check("今日もうコメントした → 何も書かない", not [c for c in calls if c[0] != "GET"], calls)

calls, log = run_handle(dict(base, conclusion="success"), {("GET", f"{R}/issues?"): [open_issue]})
writes = [c for c in calls if c[0] != "GET"]
check("成功 → 「直った」とコメントして閉じる", [(c[0], c[1]) for c in writes] == [("POST", f"{R}/issues/12/comments"), ("PATCH", f"{R}/issues/12")]
      and writes[0][2]["body"] == "直った（https://github.com/x/actions/runs/9）" and writes[1][2]["state"] == "closed", writes)
calls, log = run_handle(dict(base, conclusion="success"), {("GET", f"{R}/issues?"): [dict(open_issue, title="【見張り】毎日の更新が失敗した")]})
check("ほかの題の issue は閉じない", not [c for c in calls if c[0] != "GET"], calls)

calls, log = run_handle(dict(base, path=".github/workflows/health.yml", conclusion="failure"),
                        {**fail_answers, ("GET", f"{R}/actions/workflows/health.yml/runs"): {"workflow_runs": []}}, dry=True)
check("見張り番の失敗は、見張り番の注意も本文に", "見張り番の注意:" in log and "この7日に 5 回失敗" in log and "Node.js" not in log, log)

print("━━ mihari.yml と見張る workflow がそろっている")
WF = os.path.join(ROOT, ".github", "workflows")
listed = next((line.split(":", 1)[1].strip() for line in open(os.path.join(WF, "mihari.yml"), encoding="utf-8")
               if line.strip().startswith("workflows:")), "")
for file in M.WATCH:
    wf_name = next((line.split(":", 1)[1].strip() for line in open(os.path.join(WF, file), encoding="utf-8") if line.startswith("name:")), "?")
    check(f"{file}（{wf_name}）が mihari.yml の workflows: にある", wf_name in [s.strip() for s in listed.strip("[]").split(",")], listed)

print()
print(f"見張り: {passed} 成功 / {failed} 失敗")
sys.exit(1 if failed else 0)
