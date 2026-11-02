"""週1回の見張り番（scripts/health.py・.github/workflows/health.yml。2026-10-13）のテスト。
実行: python3 tests/test_health.py（ネットには出ない。GitHub の答えは作ったもの）"""
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import health as H  # noqa: E402

os.environ.pop("GITHUB_STEP_SUMMARY", None)  # CI の中でも、表を実行の要約ではなく out に出す（テストで見るため）

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
w, row = H.check_runs("ten-yen.yml", "10円セール", [run("2026-10-18T03:00:00Z")] + [run(f"2026-10-1{d}T03:00:00Z", "failure") for d in (3, 4, 5)], since)
check("この7日に何回失敗しても、もう直っていれば注意なし・回数は表に（失敗はそのたびに mihari.yml が知らせる）",
      w == [] and row == "10円セール: 4回・失敗3回", (w, row))
w, row = H.check_runs("deploy.yml", "公開", [run(f"2026-10-1{d}T03:00:00Z", "failure") for d in (8, 7, 6, 5, 4)], since)
check("失敗が続いていれば、注意は「いちばん新しい実行」の1つだけ", w == ["公開（deploy.yml）のいちばん新しい実行が failure です"] and "失敗5回" in row, (w, row))
w, row = H.check_runs("ten-yen.yml", "10円セール", [run("2026-10-18T03:00:00Z")] + [run(f"2026-10-0{d}T03:00:00Z", "failure") for d in (3, 4, 5)], since)
check("7日より前の失敗は数えない", w == [] and row == "10円セール: 1回・失敗0回", (w, row))
check("失敗の回数の決まり（FAILS_MAX）はもう無い", not hasattr(H, "FAILS_MAX"))
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
# 11/2 の本物の記録（一回りの番号, 本数。新しい順）: 外した日にへって、一回りのあいだにふくらむ（のこぎりの歯）
real = [(10, 14367), (10, 14071), (9, 19343), (9, 18277), (9, 17081), (8, 15264), (8, 14766), (8, 13828),
        (7, 15155), (7, 14498), (7, 13104), (6, 12340), (6, 11959), (6, 11374), (5, 23254)]
pts = H.pruned_points(real)
check("一回りごとに、外し終わった直後の本数を古い順に（いちばん古い番号は途中からかもしれないので使わない）",
      pts == [11374, 13104, 13828, 17081, 14071], pts)
check("記録が1回りぶんしか無ければ空", H.pruned_points([(3, 100), (3, 90)]) == [])
w, row = H.check_catalog(14367, 271, 10000, pts)
check("11/2 の本物: 外したあと 14,071本（コメントの無い作品 13,800本）・最後にへっているので注意なし",
      w == [] and row.startswith("過去作品: 外したあと 14,071本（コメントの無い作品 13,800本・深さ 10,000本・外したあとの移り 13,104→13,828→17,081→14,071・いま 14,367本）"), (w, row))
stuck = [12000, 15000, 18000, 21000]
w, _ = H.check_catalog(23000, 900, 10000, stuck)
check("外したあとが1.5倍をこえて、3回続けてふえていれば注意（外すしくみが止まっている形）", w and "20,100" in w[0] and "prune_catalog" in w[0], w)
w, _ = H.check_catalog(23254, 0, 10000, [14754, 18466, 20629, 23010])
check("10/18 の本物（外すしくみが止まっていたころの外したあとの本数）なら注意", len(w) == 1, w)
w, _ = H.check_catalog(23000, 900, 10000, [12000, 15000, 18000, 17500, 21000])
check("あいだで1回でもへっていれば注意なし", w == [], w)
w, _ = H.check_catalog(17000, 0, 10000, [16000, 16100, 16200, 16300])
check("コメントの付いた分くらいの少しのふえ方（300本に満たない）は、ふえたに数えない", w == [], w)
w, _ = H.check_catalog(16000, 2000, 10000, [9000, 12000, 15000, 16500])
check("コメントのある作品（外さない）は数えない（1.5倍をこえていなければ注意なし）", w == [], w)
w, _ = H.check_catalog(18000, 0, 10000, [15000, 18000, 21000])
check("外したあとの記録が4回ぶん無ければ、ふえ続けているとは言わない", w == [], w)
w, row = H.check_catalog(9000, 0, 10000, [])
check("外したあとの本数が読めなければ注意なし・表にそう書く", w == [] and "読めず" in row, (w, row))

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
