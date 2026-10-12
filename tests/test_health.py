"""週1回の見張り番（scripts/health.py・.github/workflows/health.yml。2026-10-13）のテスト。
実行: python3 tests/test_health.py（ネットには出ない。GitHub の答えは作ったもの）"""
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import health as H  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


MON = date(2026, 10, 19)  # 月曜
print("━━ 見る7日")
check("月曜 0:01 なら、前の月曜〜日曜", H.week_days(MON) == ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-17", "2026-10-18"])
since = H.jst("2026-10-11T15:00:00Z")

print("━━ 毎日の更新の記録")
subs = [f"データ更新: 2026-10-{d}" for d in range(12, 20)] + ["セールの読み直し: 2026-10-18 01:24", "Merge #130: なにか"]
w, row = H.check_updates(subs, MON)
check("7日そろっていれば注意なし", w == [] and row == "毎日の更新の記録: 7/7日", (w, row))
w, row = H.check_updates([s for s in subs if "10-15" not in s and "10-17" not in s], MON)
check("無い日があれば、その日を書いて注意", w == ["毎日の更新の記録が無い日があります（10/15・10/17）"] and row == "毎日の更新の記録: 5/7日", (w, row))

print("━━ 公開・更新などの実行")
run = lambda created, conclusion="success", started=None, ended=None: {"status": "completed", "conclusion": conclusion, "created_at": created,
                                                                     "run_started_at": started or created, "updated_at": ended or created}
ok_runs = [run("2026-10-18T03:00:00Z", started="2026-10-18T03:00:00Z", ended="2026-10-18T03:13:00Z"),
           run("2026-10-16T03:00:00Z", "failure"), run("2026-10-15T03:00:00Z", "cancelled")]
w, row = H.check_runs("deploy.yml", "公開", ok_runs, since)
check("失敗が1回でも、いちばん新しい実行が成功なら注意なし（すぐ直った失敗で騒がない）", w == [] and row == "公開: 3回・失敗1回・いちばん長くて13分", (w, row))
w, _ = H.check_runs("deploy.yml", "公開", [run("2026-10-18T03:00:00Z", "cancelled"), run("2026-10-18T02:00:00Z", "failure")] + ok_runs, since)
check("いちばん新しい実行（取り消しは数えない）が失敗なら注意", w == ["公開（deploy.yml）のいちばん新しい実行が failure です"], w)
w, _ = H.check_runs("ten-yen.yml", "10円セール", [run("2026-10-18T03:00:00Z")] + [run(f"2026-10-1{d}T03:00:00Z", "failure") for d in (3, 4, 5)], since)
check("この7日に3回以上の失敗は注意", w == ["10円セール（ten-yen.yml）がこの7日に 3 回失敗しています"], w)
w, _ = H.check_runs("ten-yen.yml", "10円セール", [run("2026-10-18T03:00:00Z")] + [run(f"2026-10-0{d}T03:00:00Z", "failure") for d in (3, 4, 5)], since)
check("7日より前の失敗は数えない", w == [], w)
w, _ = H.check_runs("deploy.yml", "公開", [run("2026-10-18T03:00:00Z", started="2026-10-18T03:00:00Z", ended="2026-10-18T03:35:00Z")], since)
check("公開が30分をこえたら注意（上限は40分）", w == ["公開にいちばん長くて 35 分かかりました（上限は40分）"], w)

print("━━ コメントの仕上げ（Claude の予約タスク）")
pr = lambda ref, merged: {"head": {"ref": ref}, "merged_at": merged}
prs = [pr(f"claude/comments-202610{d}-0021", f"2026-10-{d - 1}T15:40:00Z") for d in range(13, 19)] + [pr("claude/roundup-x", "2026-10-18T16:00:00Z"), pr("claude/comments-y", None)]
w, row = H.check_comments(prs, MON)
check("Merge された日を日本時間で数える（6日あれば注意なし）", w == [] and row == "コメントの仕上げ（Claude）の Merge: 6/7日", (w, row))
w, row = H.check_comments(prs[:3], MON)
check("5日に満たなければ注意", w == ["コメントの仕上げ（毎日 0:20 の予約タスク）が Merge された日が 3 日だけです"], (w, row))

print("━━ 過去作品の数")
w, row = H.check_catalog(18900, 900, 10000, 18466)
check("深さの1.3倍をこえて、7日前より増えていれば注意", w and "18,000" in w[0] and row == "過去作品: 18,900本（コメントの無い作品 18,000本・深さ 10,000本・7日前 18,466本）", (w, row))
w, _ = H.check_catalog(15000, 900, 10000, 18900)
check("こえていても、7日前より減っていれば注意なし（一回りごとに外れている途中）", w == [], w)
w, _ = H.check_catalog(14000, 1200, 10000, 13000)
check("コメントのある作品（外さない）は数えない", w == [], w)
w, row = H.check_catalog(9000, 0, 10000, None)
check("7日前が分からなくても、こえていなければ注意なし", w == [] and "7日前" not in row, (w, row))

print("━━ リポジトリの大きさ")
check("500MB 未満なら注意なし", H.check_repo(13 * 1024) == ([], "リポジトリの大きさ: 13MB"))
check("500MB 以上なら注意", H.check_repo(512000)[0] and "500MB" in H.check_repo(512000)[0][0])

print("━━ 結果の出し方")
out = []
code = H.report([([], "毎日の更新の記録: 7/7日"), ([], "公開: 3回")], MON, out=out.append)
check("注意が無ければ ::notice（問題なし）と、終わりの印 0", code == 0 and out[0] == "::notice title=見張り番::問題なし（10月19日・この7日）", out)
out = []
code = H.report([(["公開に35分"], "公開: 3回"), ([], "x")], MON, out=out.append)
check("注意があれば ::warning と、終わりの印 1（GitHub から知らせが届く）", code == 1 and out[0] == "::warning title=見張り番::公開に35分" and "| 公開: 3回 | ⚠️ 公開に35分 |" in out[-1], out)

print("━━ --last（毎週月曜の Claude の予約タスクが報告に書く）")
def fake(answers):
    return lambda path: next(v for k, v in answers.items() if k in path)
lines = []
H.last(api=fake({"health.yml/runs": {"workflow_runs": [{"id": 5, "status": "completed", "conclusion": "success", "created_at": "2026-10-18T15:01:00Z"}]},
                 "runs/5/jobs": {"jobs": [{"check_run_url": "https://api.github.com/repos/x/check-runs/77"}]},
                 "check-runs/77/annotations": [{"title": "見張り番", "annotation_level": "notice", "message": "問題なし"}]}), out=lines.append)
check("問題が無ければ1行（日本時間の日付）", lines == ["✅ 見張り番（10月19日）: 問題なし"], lines)
lines = []
H.last(api=fake({"health.yml/runs": {"workflow_runs": [{"id": 5, "status": "completed", "conclusion": "failure", "created_at": "2026-10-18T15:01:00Z"}]},
                 "runs/5/jobs": {"jobs": [{"check_run_url": "https://api.github.com/repos/x/check-runs/77"}]},
                 "check-runs/77/annotations": [{"title": "見張り番", "annotation_level": "warning", "message": "公開に35分"},
                                               {"title": "ほか", "annotation_level": "warning", "message": "関係ない注釈"}]}), out=lines.append)
check("注意は1つずつ1行（見張り番の注釈だけ）", lines == ["⚠️ 見張り番（10月19日）: 公開に35分"], lines)
lines = []
H.last(api=fake({"health.yml/runs": {"workflow_runs": []}}), out=lines.append)
check("まだ動いていなければ、そう書く", lines == ["見張り番: まだ動いていません"], lines)

print("━━ ワークフロー")
wf = open(os.path.join(ROOT, ".github", "workflows", "health.yml"), encoding="utf-8").read()
check("毎週月曜 0:01（日本時間）＝日曜 15:01（UTC）に動く・手動でも動かせる", "cron: '1 15 * * 0'" in wf and "workflow_dispatch:" in wf)
check("読むだけ（サイトのデータに書かない・公開しない）", "contents: read" in wf and "contents: write" not in wf and "deploy.yml" not in wf.split("jobs:")[1])
check("7日分の記録を見られる深さで取る", "fetch-depth: 400" in wf)

print()
print(f"結果: {passed} 成功 / {failed} 失敗")
sys.exit(1 if failed else 0)
