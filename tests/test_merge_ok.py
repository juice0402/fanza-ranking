"""マージの印（scripts/merge_ok.py・.github/workflows/merge-ok.yml。2026-11-02）のテスト。
実行: python3 tests/test_merge_ok.py（ネットには出ない。GitHub の答えは作ったもの）"""
import io
import os
import re
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import merge_ok as M  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


NOW = datetime(2026, 11, 2, 4, 0, tzinfo=timezone.utc)

print("━━ 順番の指定の読み取り")
cases = [
    ("#44 の PR #51 のあとにマージ", [44, 51]),
    ("⚠️ #44 の PR #51 のあとにマージ（作業中に #51 がマージされたので main を取りこみ済み）", [44, 51]),
    ("PR #51 のあとにマージ", [51]),
    ("#136 のあとにマージ（衝突したら main を取りこむ）", [136]),
    ("#184 のあとにマージ(衝突したら main を取りこむ)。この PR は guide.js をさわらない", [184]),
    ("**#12のあとにマージ**", [12]),
    ("#33 と #34 のあとにマージ", [33, 34]),
    ("#33、#34 の後にマージ", [33, 34]),
    ("＃１２ の後でマージ", [12]),  # 全角
    ("Closes #12\n\n#11 のあとにマージ", [11]),  # 行はまたがない
    ("#12 のあとの本番の更新で、棚が12件にふえた", []),
    ("**Google の有効化(11/1 19:00)のあとにマージ**", []),
    ("マージは 11/1 9:00 のあとにして", []),
    ("Closes #198", []),
    ("", []),
    (None, []),
]
for body, want in cases:
    got = M.order_refs(body)
    check(f"「{str(body)[:30]}」→ {want}".replace("\n", "⏎"), got == want, got)
check("自分の番号は数えない", M.order_refs("#20 と #21 のあとにマージ", 21) == [20])

print("━━ 順番の指定で待つか")
def pr(n, body="", ref="claude/x", labels=("merge-ok",), base="main", draft=False, sha=None):
    return {"number": n, "title": f"題{n}", "body": body, "head": {"ref": ref, "sha": sha or f"sha{n}"},
            "base": {"ref": base}, "draft": draft, "labels": [{"name": x} for x in labels], "state": "open"}

me = pr(52, "⚠️ #44 の PR #51 のあとにマージ")
check("指定の PR が開いている → 待つ", M.blockers(me, {51: pr(51), 52: me}) == ["PR #51 がまだ開いている"], M.blockers(me, {51: pr(51), 52: me}))
check("指定の PR が閉じた → 待たない", M.blockers(me, {52: me}) == [])
me = pr(60, "#44 のあとにマージ")
check("issue の番号 → その issue を閉じる PR が開いていれば待つ",
      M.blockers(me, {59: pr(59, "Closes #44"), 60: me}) == ["#44 の PR #59 がまだ開いている"])
check("閉じる書き方のゆれ（fixes: ・小文字）", M.closes(pr(1, "fixes: #44"), 44) and M.closes(pr(1, "（resolved #44）"), 44))
check("#440 は #44 ではない", not M.closes(pr(1, "Closes #440"), 44))
check("夜のブランチ night-44 も、その issue の PR", M.blockers(me, {59: pr(59, "", "claude/night-44"), 60: me}) == ["#44 の PR #59 がまだ開いている"])
check("ただ #44 と書いてある PR は待たない（おたがい待ちにならない）", M.blockers(me, {61: pr(61, "#44 のあとにマージ"), 60: me}) == [])
check("自分が閉じる issue なら待たない", M.blockers(pr(62, "Closes #44\n#44 のあとにマージ"), {62: pr(62, "Closes #44")}) == [])

print("━━ 点検の判定")
def cr(name, status="completed", conclusion="success"):
    return {"name": name, "status": status, "conclusion": conclusion if status == "completed" else None}

LABEL_OLD = "2026-11-02T03:00:00Z"   # 60分前
LABEL_NEW = "2026-11-02T03:57:00Z"   # 3分前
check("success だけ → マージ", M.judge([cr("check")], [], LABEL_OLD, NOW)[0] == "merge")
check("skipped・neutral もマージ", M.judge([cr("a"), cr("b", conclusion="skipped"), cr("c", conclusion="neutral")], [], LABEL_OLD, NOW)[0] == "merge")
v = M.judge([cr("check", "in_progress"), cr("x")], [], LABEL_OLD, NOW)
check("終わっていない → 待つ（10分の待ちではない）", v[0] == "wait" and "check" in v[1] and v[2] is None, v)
check("queued も待つ", M.judge([cr("check", "queued")], [], LABEL_OLD, NOW)[0] == "wait")
for c in ("failure", "timed_out", "cancelled", "action_required", "startup_failure"):  # 仕様の5つ
    v = M.judge([cr("check", conclusion=c), cr("other")], [], LABEL_OLD, NOW)
    check(f"{c} → 失敗（点検の名前）", v[0] == "fail" and v[1] == "check", v)
v = M.judge([cr("check", "in_progress"), cr("lint", conclusion="failure")], [], LABEL_OLD, NOW)
check("終わっていないものがあれば、失敗があっても待つ（次の workflow_run で見直す）", v[0] == "wait", v)
check("stale など知らない結果は待つ（マージしない）", M.judge([cr("check", conclusion="stale")], [], LABEL_OLD, NOW)[0] == "wait")
v = M.judge([cr("merge-ok", "in_progress"), cr("check")], [], LABEL_OLD, NOW)
check("この workflow 自身の check-run は数えない", v[0] == "merge", v)
v = M.judge([cr("merge-ok", conclusion="failure"), cr("check")], [], LABEL_OLD, NOW)
check("自身の前の回の失敗も数えない", v[0] == "merge", v)
check("commit status の pending → 待つ", M.judge([cr("check")], [{"context": "cf", "state": "pending"}], LABEL_OLD, NOW)[0] == "wait")
v = M.judge([cr("check")], [{"context": "cf", "state": "error"}, {"context": "ok", "state": "success"}], LABEL_OLD, NOW)
check("commit status の failure・error → 失敗", v == ("fail", "cf", None), v)
v = M.judge([cr("a", conclusion="failure"), cr("a", conclusion="failure")], [], LABEL_OLD, NOW)
check("同じ名前は1回だけ", v[1] == "a", v)

print("━━ check-runs が1つもないとき（10分の待ち）")
v = M.judge([], [], LABEL_NEW, NOW)
check("ラベルから3分 → 待つ（あと約7分）", v[0] == "wait" and 415 <= v[2] <= 425, v)
v = M.judge([cr("merge-ok", "in_progress")], [], LABEL_NEW, NOW)
check("自身の check-run だけのときも「1つもない」", v[0] == "wait" and v[2], v)
check("ラベルから11分 → マージ", M.judge([], [], "2026-11-02T03:49:00Z", NOW)[0] == "merge")
check("ちょうど10分 → マージ", M.judge([], [], "2026-11-02T03:50:00Z", NOW)[0] == "merge")
check("9分59秒 → 待つ", M.judge([], [], "2026-11-02T03:50:01Z", NOW)[0] == "wait")
check("check-runs が無くても commit status の失敗は失敗", M.judge([], [{"context": "cf", "state": "failure"}], LABEL_OLD, NOW)[0] == "fail")
check("ラベルの時刻がわからない → 待つ（すぐはマージしない）", M.judge([], [], None, NOW)[:3:2] == ("wait", None))
events = [{"event": "labeled", "label": {"name": "merge-ok"}, "created_at": "2026-11-02T01:00:00Z"},
          {"event": "unlabeled", "label": {"name": "merge-ok"}, "created_at": "2026-11-02T02:00:00Z"},
          {"event": "labeled", "label": {"name": "night"}, "created_at": "2026-11-02T03:30:00Z"},
          {"event": "labeled", "label": {"name": "merge-ok"}, "created_at": "2026-11-02T03:00:00Z"}]
check("ラベルの時刻は、いちばん新しい merge-ok の付いた時", M.labeled_at(events) == "2026-11-02T03:00:00Z")
check("マージの題は「<PR の題> (#番号)」", M.commit_title({"title": "見張り [CI Skip]", "number": 9}) == "見張り [CI Skip] (#9)")

print("━━ 動き（GitHub の答えは作ったもの）")
R = f"repos/{M.REPO}"
M.sleep = lambda s: SLEPT.append(s)
M.utcnow = lambda: NOW


class Seq:
    """聞くたびに順に答える（最後の答えはくり返す）"""
    def __init__(self, *answers):
        self.answers = list(answers)

    def next(self):
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


def fake(answers):
    calls = []

    def gh(path, method="GET", body=None):
        calls.append((method, path, body))
        for key, val in answers.items():
            if method == key[0] and path.startswith(key[1]):
                if isinstance(val, Seq):
                    val = val.next()
                if isinstance(val, Exception):
                    raise val
                return val
        return None
    return gh, calls


def run(answers, dry=False, fn="run_once", only=None):
    global SLEPT
    SLEPT = []
    gh, calls = fake(answers)
    M.gh = gh
    buf = io.StringIO()
    with redirect_stdout(buf):
        if fn == "main":
            os.environ["MERGE_OK_DRY_RUN"] = "true" if dry else ""
            os.environ["MERGE_OK_PR"] = str(only or "")
            res = M.main()
        else:
            res = M.run_once(dry, NOW, only)
    return res, calls, buf.getvalue()


def writes(calls):
    return [c for c in calls if c[0] != "GET"]


green = {"check_runs": [cr("check")]}
def ans(prs, extra=None):
    a = {("GET", f"{R}/pulls?state=open"): prs, ("GET", f"{R}/labels"): [{"name": "merge-ok"}, {"name": "merge-blocked"}]}
    for p in prs:
        a[("GET", f"{R}/commits/{p['head']['sha']}/check-runs")] = green
        a[("GET", f"{R}/commits/{p['head']['sha']}/status")] = {"statuses": []}
        a[("GET", f"{R}/pulls/{p['number']}")] = dict(p, mergeable=True)
        a[("PUT", f"{R}/pulls/{p['number']}/merge")] = {"merged": True}
    a.update(extra or {})
    return a


res, calls, log = run(ans([pr(5, labels=())]))
check("merge-ok の無い PR は何もしない（点検も聞かない）", res[0] == [] and writes(calls) == [] and len(calls) == 1, calls)
res, calls, log = run(ans([pr(5, labels=("night",)), pr(6, labels=("merge-blocked",))]))
check("ほかのラベルの PR もマージしない", writes(calls) == [], calls)

res, calls, log = run(ans([pr(7, "", "claude/a")]))
put = [c for c in calls if c[0] == "PUT"]
check("点検が通った → squash でマージ（sha・題・本文は空にしない）", res[0] == [7] and put == [("PUT", f"{R}/pulls/7/merge", {
    "merge_method": "squash", "sha": "sha7", "commit_title": "題7 (#7)", "commit_message": "マージの印（merge-ok）で #7 をマージ"})], put)
check("check-runs は filter=latest で全部（100件ずつ）", any(c[1].startswith(f"{R}/commits/sha7/check-runs?filter=latest&per_page=100") for c in calls), calls)

check("本文は空にしない", all(c[2]["commit_message"].strip() for c in put), put)

res, calls, log = run(ans([pr(3), pr(7)]), only=7)
check("番号を指定 → その PR だけ見る", res[0] == [7] and not any("sha3" in c[1] for c in calls), calls)
res, calls, log = run(ans([pr(3, labels=()), pr(7)]), only=3)
check("番号を指定しても、merge-ok が無ければマージしない", res[0] == [] and writes(calls) == [], calls)
res, calls, log = run(ans([pr(9, "#3 のあとにマージ"), pr(3, labels=())]), only=9)
check("番号を指定しても、順番の指定はほかの開いている PR で見る", res[0] == [] and "PR #3 がまだ開いている" in log, log)
res, calls, log = run(ans([pr(3), pr(4)]), fn="main", only=4)
check("番号を指定（main）→ その PR だけマージして公開1回", [c[1] for c in calls if c[0] == "PUT"] == [f"{R}/pulls/4/merge"]
      and len([c for c in calls if c[1].endswith("/dispatches")]) == 1, calls)
res, calls, log = run(ans([pr(3)]), fn="main", only="x")
check("番号が数字でない → 何もしない", res == 2 and calls == [], calls)

res, calls, log = run(ans([pr(7)]), dry=True)
check("ためし（dry_run）は書かずに、するはずのことを出す", res[0] == [7] and writes(calls) == [] and "squash でマージするはず" in log, log)

res, calls, log = run(ans([pr(7, base="develop"), pr(8, draft=True)]))
check("base が main でない・draft → マージしない", res[0] == [] and writes(calls) == [], calls)

res, calls, log = run(ans([pr(9, "#3 のあとにマージ"), pr(3, labels=())]))
check("順番の指定の PR が開いている → 待つ（点検も聞かない）", res[0] == [] and writes(calls) == []
      and not any("sha9" in c[1] for c in calls) and "PR #3 がまだ開いている" in log, log)
res, calls, log = run(ans([pr(9, "#3 のあとにマージ"), pr(3)]))
check("前の PR をこの回でマージしたら、続けてマージ（番号の小さい順）", res[0] == [3, 9], res)

fail_ans = ans([pr(7)], {("GET", f"{R}/commits/sha7/check-runs"): {"check_runs": [cr("check", conclusion="failure"), cr("merge-ok", "in_progress")]}})
res, calls, log = run(fail_ans)
w = writes(calls)
check("点検の失敗 → コメント・merge-ok を外す・merge-blocked を付ける（マージしない）",
      [(c[0], c[1]) for c in w] == [("POST", f"{R}/issues/7/comments"), ("DELETE", f"{R}/issues/7/labels/merge-ok"), ("POST", f"{R}/issues/7/labels")]
      and w[0][2]["body"] == "点検が通らなかったのでマージしなかった（check）" and w[2][2] == {"labels": ["merge-blocked"]}, w)
res, calls, log = run(fail_ans, dry=True)
check("ためしの失敗は書かない", writes(calls) == [] and "merge-blocked を付けるはず" in log, log)

res, calls, log = run(ans([pr(7)], {("GET", f"{R}/commits/sha7/check-runs"): {"check_runs": [cr("check", "in_progress")]}}))
check("点検の途中 → 何もしない", writes(calls) == [] and res[1] is None, calls)

res, calls, log = run(ans([pr(7)], {("GET", f"{R}/pulls/7"): Seq(dict(pr(7), mergeable=None), dict(pr(7), mergeable=None), dict(pr(7), mergeable=False))}))
check("mergeable が null → 5秒待って2回まで見直す", SLEPT == [5, 5], SLEPT)
w = writes(calls)
check("ぶつかり → コメントして merge-blocked", w and w[0][2]["body"] == "main とぶつかったのでマージしなかった。司令塔で main を取りこむ"
      and w[-1][2] == {"labels": ["merge-blocked"]} and not [c for c in calls if c[0] == "PUT"], w)

res, calls, log = run(ans([pr(7)], {("GET", f"{R}/pulls/7"): Seq(dict(pr(7), mergeable=None))}))
check("3回とも null → 次に見直す（書かない）", writes(calls) == [] and len([c for c in calls if c[1] == f"{R}/pulls/7"]) == 3, calls)

res, calls, log = run(ans([pr(7)], {("GET", f"{R}/pulls/7"): dict(pr(7, labels=()), mergeable=True)}))
check("見直したときに印が外れていたら、マージしない", writes(calls) == [], calls)

res, calls, log = run(ans([pr(7)], {("PUT", f"{R}/pulls/7/merge"): M.ApiError("Head branch was modified (HTTP 409)")}))
check("head が変わった（409）→ 待つ（merge-blocked にしない）", res[0] == [] and [c[0] for c in writes(calls)] == ["PUT"], writes(calls))

no_checks = {("GET", f"{R}/commits/sha7/check-runs"): {"check_runs": []},
             ("GET", f"{R}/issues/7/events"): [{"event": "labeled", "label": {"name": "merge-ok"}, "created_at": LABEL_NEW}]}
res, calls, log = run(ans([pr(7)], no_checks))
check("check-runs が無い・ラベルから3分 → 待つ（あと何秒かを返す）", res[0] == [] and 415 <= (res[1] or 0) <= 425 and writes(calls) == [], res)
no_checks_old = dict(no_checks)
no_checks_old[("GET", f"{R}/issues/7/events")] = [{"event": "labeled", "label": {"name": "merge-ok"}, "created_at": LABEL_OLD}]
res, calls, log = run(ans([pr(7)], no_checks_old))
check("check-runs が無い・ラベルから10分たった → マージ", res[0] == [7], log)
res, calls, log = run(ans([pr(7)]))
check("check-runs があるときは、ラベルの時刻を聞かない", not any("/events" in c[1] for c in calls), calls)

print("━━ 公開（deploy.yml）を動かす")
res, calls, log = run(ans([pr(3), pr(4)]), fn="main")
disp = [c for c in calls if c[1].endswith("/dispatches")]
check("2本マージしても、公開は最後に1回だけ（ref=main）", disp == [("POST", f"{R}/actions/workflows/deploy.yml/dispatches", {"ref": "main"})]
      and calls.index(disp[0]) > max(i for i, c in enumerate(calls) if c[0] == "PUT"), disp)
res, calls, log = run(ans([pr(3, labels=())]), fn="main")
check("マージしなかったら、公開は動かさない", not [c for c in calls if c[1].endswith("/dispatches")], calls)
res, calls, log = run(ans([pr(3)]), dry=True, fn="main")
check("ためしは公開も動かさない・ラベルも作らない", writes(calls) == [] and "公開（deploy.yml）を main で1回動かすはず" in log, log)
a = ans([])
a[("GET", f"{R}/labels")] = [{"name": "night"}]
res, calls, log = run(a, fn="main")
check("ラベルがなければ作る（色・説明）", [c[2] for c in writes(calls)] == [M.OK, M.BLOCKED]
      and M.OK["color"] == "0e8a16" and M.BLOCKED["color"] == "b60205", writes(calls))
res, calls, log = run(ans([pr(7)], no_checks), fn="main")
check("check-runs の無い PR は、10分たつまで待ってから見直す（1回だけ）", len(SLEPT) == 1 and 415 <= SLEPT[0] <= 435
      and len([c for c in calls if c[1].startswith(f"{R}/pulls?state=open")]) == 2, SLEPT)

print("━━ merge-ok.yml")
WF = os.path.join(ROOT, ".github", "workflows")
wf = open(os.path.join(WF, "merge-ok.yml"), encoding="utf-8").read()
listed = re.search(r"workflows:\s*\[([^\]]*)\]", wf).group(1)
ci_name = next(line.split(":", 1)[1].strip() for line in open(os.path.join(WF, "ci.yml"), encoding="utf-8") if line.startswith("name:"))
check("workflow_run は PR の点検（ci.yml の name）を見る", [s.strip() for s in listed.split(",")] == [ci_name], listed)
check("動くとき: ラベル・点検の終わり・手で（dry_run）。schedule は使わない",
      "types: [labeled]" in wf and "types: [completed]" in wf and "dry_run:" in wf and "schedule" not in wf)
check("手で動かすとき、PR の番号（pr）を入れられる", re.search(r"\n      pr:\n(?:        .*\n)*?        type: number\n        required: false", wf)
      and "MERGE_OK_PR: ${{ inputs.pr }}" in wf)
check("同時に2つ動かさない", re.search(r"concurrency:\s*\n\s*group: merge-ok\s*\n\s*cancel-in-progress: false", wf))
check("権限", all(p in wf for p in ("contents: write", "pull-requests: write", "issues: write", "actions: write", "checks: read", "statuses: read")))
check("ジョブの名前が SELF_CHECK と同じ", f"name: {M.SELF_CHECK}" in wf)
check("鍵は GITHUB_TOKEN だけ", "secrets." not in wf and "GH_TOKEN: ${{ github.token }}" in wf)
deploy = open(os.path.join(WF, M.PUBLISH), encoding="utf-8").read()
check("公開の workflow（deploy.yml）は手で動かせる（workflow_dispatch）", "workflow_dispatch:" in deploy and "branches: [main]" in deploy)

print("━━ 本文の Closes #◯（マージのあとに閉じる issue）")
check("Closes：1つ", M.closes_of("Closes #150") == [150])
check("Closes：順番の指定の番号は入れない", M.closes_of("⚠️ #106 の PR #109 のあとにマージ\n\nCloses #107") == [107])
check("Closes：いろいろな書き方", M.closes_of("closed #3, fixes: #4\nResolves #5 close #6") == [3, 4, 5, 6])
check("Closes：同じ番号は1つ・全角", M.closes_of("Closes #150\nCloses ＃１５０") == [150])
check("Closes：一部・空は閉じない", M.closes_of("夜 #72 の一部") == [] and M.closes_of(None) == [])
_calls = []
def _gh(path, method="GET", body=None):
    _calls.append(f"{method} {path}")
    if path.endswith("/issues/7"):
        return {"number": 7, "state": "open"}
    if path.endswith("/issues/8"):
        return {"number": 8, "state": "closed"}
    if path.endswith("/issues/9"):
        return {"number": 9, "state": "open", "pull_request": {}}
    return {}
_orig_gh = M.gh
M.gh = _gh
with redirect_stdout(io.StringIO()):
    _done = M.close_linked({"number": 20, "body": "Closes #7\nCloses #8\nCloses #9"}, "abcdef1234")
check("Closes：開いている issue だけ閉じる（閉じた issue・PR はさわらない）", _done == [7] and any(c.endswith("/issues/7") and c.startswith("PATCH") for c in _calls) and not any(c.startswith("PATCH") and (c.endswith("/issues/8") or c.endswith("/issues/9")) for c in _calls))
_calls.clear()
with redirect_stdout(io.StringIO()):
    M.close_linked({"number": 20, "body": "Closes #7"}, "", dry=True)
check("Closes：ためしでは閉じない", _calls == [f"GET repos/{M.REPO}/issues/7"])
M.gh = _orig_gh

print()
print(f"マージの印: {passed} 成功 / {failed} 失敗")
sys.exit(1 if failed else 0)
