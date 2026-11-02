"""マージの印（.github/workflows/merge-ok.yml。2026-11-02 司令塔「マージを GitHub に任せる」）。

しょーくんが司令塔で「マージして」と言ったあとにだけ、司令塔が PR にラベル merge-ok を付ける。
この道具は、開いている PR のうち merge-ok が付いたものを、番号の小さい順に1つずつ見て、点検（CI）が通ったらマージする。
merge-ok の付いていない PR は絶対にマージしない（予約タスクが自分でマージするデータの PR もさわらない）。
  1. base が main で、draft でないこと
  2. 本文の「#数字 の PR #数字 のあとにマージ」「PR #数字 のあとにマージ」「#数字 のあとにマージ」の PR
     （issue の番号なら、その issue を閉じる PR）がまだ開いていれば待つ
  3. head の check-runs と commit statuses: まだ終わっていなければ待つ（次の workflow_run で見直す）。
     失敗があれば、コメントして merge-ok を外し merge-blocked を付ける。check-runs が1つもないときは、ラベルから10分たったらマージしてよい
  4. mergeable: null なら5秒待って2回まで見直す。false（main とぶつかった）ならコメントして merge-blocked
  5. squash でマージ（題は「<PR の題> (#番号)」・本文は「マージの印（merge-ok）で #番号 をマージ」。
     本文を空にすると、GitHub がブランチのコミットの一覧で埋めることがあるため）
  6. 1本でもマージしたら、最後に1回だけ公開（deploy.yml）を ref=main で動かす（GITHUB_TOKEN のマージでは push で動く workflow が動かないため）。
     公開の結果は待たない（見張り mihari.yml が見る）
  7. ラベル merge-ok・merge-blocked がなければ作る

使い方（merge-ok.yml から。GitHub の鍵 GH_TOKEN が要る）:
  python3 scripts/merge_ok.py   MERGE_OK_DRY_RUN=true ならマージ・コメント・ラベル・公開をせず、するはずのことを出す
                                MERGE_OK_PR=番号 なら、その PR だけ見る（空なら merge-ok の付いた PR を全部）
標準ライブラリだけ。テストは tests/test_merge_ok.py
"""
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone

REPO = os.environ.get("GITHUB_REPOSITORY", "juice0402/fanza-ranking")
BASE = "main"
PUBLISH = "deploy.yml"   # 公開の workflow（マージしたら workflow_dispatch で ref=main に1回）
SELF_CHECK = "merge-ok"  # この workflow 自身のジョブの名前（check-run の名前）。点検に数えない
OK = {"name": "merge-ok", "color": "0e8a16", "description": "しょーくんの OK。点検が通ったら GitHub がマージ"}
BLOCKED = {"name": "merge-blocked", "color": "b60205", "description": "印を付けたがマージできなかった。司令塔が見る"}
FAIL = ("failure", "timed_out", "cancelled", "action_required", "startup_failure")
PASS = ("success", "skipped", "neutral")
GRACE = 600            # check-runs が1つもない PR は、ラベルからこの秒数たったらマージしてよい（点検のない PR のため）
MERGEABLE_RETRY = 2    # mergeable が null のとき、見直す回数
MERGEABLE_WAIT = 5     # そのあいだに待つ秒数

sleep = time.sleep  # テストで差しかえる


def utcnow():  # テストで差しかえる
    return datetime.now(timezone.utc)


class ApiError(RuntimeError):
    pass


def gh(path, method="GET", body=None):
    cmd = ["gh", "api", "-X", method, path]
    if body is not None:
        cmd += ["--input", "-"]
    r = subprocess.run(cmd, input=None if body is None else json.dumps(body), capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise ApiError((r.stderr or r.stdout).strip()[:300])
    return json.loads(r.stdout) if r.stdout.strip() else None


def gh_all(path, key=None, pages=10):
    """ページをめくって全部（100件ずつ）。key があれば、その欄の配列を集める"""
    items = []
    sep = "&" if "?" in path else "?"
    for page in range(1, pages + 1):
        got = gh(f"{path}{sep}per_page=100&page={page}")
        part = ((got or {}).get(key) if key else got) or []
        items += part
        if len(part) < 100:
            break
    return items


def out(line=""):
    print(line, flush=True)


# ---- 判定（GitHub に聞かない。テストする所） ----

_SP = r"[ \t]*"  # 行はまたがない
_JOIN = rf"{_SP}(?:の{_SP}(?:PR|プルリクエスト)|と|、|,|・|/|&)?{_SP}(?:PR{_SP})?"
ORDER_RE = re.compile(rf"(#\d+(?:{_JOIN}#\d+)*){_SP}の{_SP}(?:あと|後){_SP}(?:に|で)?{_SP}マージ", re.I)


def order_refs(body, me=None):
    """本文の「#44 の PR #51 のあとにマージ」「PR #51 のあとにマージ」「#51 のあとにマージ」から番号（小さい順。自分は除く）"""
    text = unicodedata.normalize("NFKC", str(body or ""))  # ＃１２ → #12
    nums = set()
    for chain in ORDER_RE.findall(text):
        nums.update(int(n) for n in re.findall(r"#(\d+)", chain))
    nums.discard(me)
    return sorted(nums)


def closes(pr, n):
    """その PR が issue #n に対応するか（本文の Closes #n などの閉じる書き方・夜のブランチ night-n）"""
    body = unicodedata.normalize("NFKC", str(pr.get("body") or ""))
    if re.search(rf"(?<![A-Za-z])(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?){_SP}:?{_SP}#{n}(?!\d)", body, re.I):
        return True
    return bool(re.search(rf"(?:^|/)night-{n}$", str((pr.get("head") or {}).get("ref") or "")))


def blockers(pr, open_prs):
    """順番の指定で待つ理由（空ならマージしてよい）。open_prs は 番号 → 開いている PR"""
    me = pr.get("number")
    why = []
    for n in order_refs(pr.get("body"), me):
        if n in open_prs:
            why.append(f"PR #{n} がまだ開いている")
            continue
        why += [f"#{n} の PR #{o} がまだ開いている" for o in sorted(open_prs) if o != me and closes(open_prs[o], n)]
    return why


def parse_time(iso):
    try:
        return datetime.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def labeled_at(events):
    """issue の events から、いちばん新しい「merge-ok が付いた」時刻"""
    times = [e.get("created_at") for e in events
             if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == OK["name"]]
    return max(times) if times else None


def _uniq(names):
    return list(dict.fromkeys(str(n or "（名前なし）") for n in names))


def judge(check_runs, statuses, label_time, now):
    """点検の判定 → (判定, 説明, 待つ秒数)。判定は 'merge'・'wait'・'fail'。
    待つ秒数は、check-runs が1つもなくて10分たっていないときだけ（ほかは None）"""
    runs = [c for c in check_runs if c.get("name") != SELF_CHECK]
    waiting = [c.get("name") for c in runs if c.get("status") != "completed" or c.get("conclusion") not in FAIL + PASS]
    waiting += [s.get("context") for s in statuses if s.get("state") == "pending"]
    if waiting:
        return "wait", f"点検がまだ終わっていない（{'、'.join(_uniq(waiting))}）", None
    failed = [c.get("name") for c in runs if c.get("conclusion") in FAIL]
    failed += [s.get("context") for s in statuses if s.get("state") in ("failure", "error")]
    if failed:
        return "fail", "、".join(_uniq(failed)), None
    if not runs:
        t = parse_time(label_time)
        if t is None:
            return "wait", "点検（check-runs）が1つもなく、ラベルの時刻もわからない", None
        passed = (now - t).total_seconds()
        if passed < GRACE:
            left = int(GRACE - passed) + 1
            return "wait", f"点検（check-runs）がまだ1つもない。ラベルから10分たつまで待つ（あと {left} 秒）", left
        return "merge", "点検（check-runs）が無いまま、ラベルから10分たった", None
    return "merge", "点検が通った", None


def commit_title(pr):
    return f"{pr.get('title', '')} (#{pr.get('number')})"


def commit_message(pr):
    """squash の本文（空にしない。空だと GitHub がブランチのコミットの一覧で埋めることがあるため）"""
    return f"マージの印（merge-ok）で #{pr.get('number')} をマージ"


def has_label(pr, name):
    return any(lb.get("name") == name for lb in pr.get("labels") or [])


# ---- GitHub に聞く・書く ----

def ensure_labels():
    have = {lb.get("name") for lb in gh_all(f"repos/{REPO}/labels")}
    for lb in (OK, BLOCKED):
        if lb["name"] not in have:
            try:
                gh(f"repos/{REPO}/labels", "POST", lb)
                out(f"ラベル {lb['name']} を作った")
            except ApiError as e:
                if "already_exists" not in str(e):
                    raise


def block(n, text, dry):
    if dry:
        out(f"（ためし）#{n} に「{text}」とコメントし、{OK['name']} を外して {BLOCKED['name']} を付けるはず")
        return
    gh(f"repos/{REPO}/issues/{n}/comments", "POST", {"body": text})
    try:
        gh(f"repos/{REPO}/issues/{n}/labels/{OK['name']}", "DELETE")
    except ApiError as e:
        if "404" not in str(e) and "Not Found" not in str(e):
            raise
    gh(f"repos/{REPO}/issues/{n}/labels", "POST", {"labels": [BLOCKED["name"]]})
    out(f"#{n}: マージしなかった（{text}）。{BLOCKED['name']} を付けた")


def process(pr, open_prs, dry, now):
    """PR 1つ → ('merged' | 'wait' | 'grace' | 'blocked' | 'skip', 待つ秒数)"""
    n = pr["number"]
    if not has_label(pr, OK["name"]):
        return "skip", None  # 念のため（印のない PR は絶対にマージしない）
    base = (pr.get("base") or {}).get("ref")
    if base != BASE or pr.get("draft"):
        out(f"#{n}: base が {base}・draft={bool(pr.get('draft'))}。マージしない")
        return "skip", None
    why = blockers(pr, open_prs)
    if why:
        out(f"#{n}: 順番を待つ（{'・'.join(why)}）")
        return "wait", None
    sha = pr["head"]["sha"]
    runs = gh_all(f"repos/{REPO}/commits/{sha}/check-runs?filter=latest", "check_runs")
    statuses = gh_all(f"repos/{REPO}/commits/{sha}/status", "statuses")
    label_time = None
    if not [c for c in runs if c.get("name") != SELF_CHECK]:  # ラベルの時刻は、check-runs が無いときだけ聞く
        label_time = labeled_at(gh_all(f"repos/{REPO}/issues/{n}/events"))
    verdict, text, left = judge(runs, statuses, label_time, now)
    if verdict == "wait":
        out(f"#{n}: 待つ（{text}）")
        return ("grace" if left else "wait"), left
    if verdict == "fail":
        block(n, f"点検が通らなかったのでマージしなかった（{text}）", dry)
        return "blocked", None
    full = None
    for i in range(MERGEABLE_RETRY + 1):
        full = gh(f"repos/{REPO}/pulls/{n}") or {}
        if full.get("mergeable") is not None:
            break
        if i < MERGEABLE_RETRY:
            sleep(MERGEABLE_WAIT)
    if full.get("state") != "open" or not has_label(full, OK["name"]):
        out(f"#{n}: もう開いていない・印が外れた。マージしない")
        return "skip", None
    if full.get("mergeable") is None:
        out(f"#{n}: マージできるか GitHub がまだ調べている。次に見直す")
        return "wait", None
    if full.get("mergeable") is False:
        block(n, "main とぶつかったのでマージしなかった。司令塔で main を取りこむ", dry)
        return "blocked", None
    body = {"merge_method": "squash", "sha": sha, "commit_title": commit_title(pr), "commit_message": commit_message(pr)}
    if dry:
        out(f"（ためし）#{n} を squash でマージするはず（{text}。題「{body['commit_title']}」）")
        return "merged", None
    try:
        res = gh(f"repos/{REPO}/pulls/{n}/merge", "PUT", body) or {}
    except ApiError as e:
        if "409" in str(e):  # head が変わった → 新しい点検を待つ
            out(f"#{n}: head が変わった。新しい点検のあとに見直す")
            return "wait", None
        block(n, f"マージできなかった（GitHub の答え: {str(e)[:150]}）", dry)
        return "blocked", None
    if not res.get("merged"):
        block(n, f"マージできなかった（GitHub の答え: {str(res.get('message', ''))[:150]}）", dry)
        return "blocked", None
    out(f"#{n}: マージした（{text}）")
    return "merged", None


def run_once(dry, now=None, only=None):
    """1回ぶん見る → (マージした番号, いちばん早く10分たつまでの秒数 or None, 失敗があったか)。
    only（PR の番号）があれば、その PR だけ見る（それでも merge-ok が無ければマージしない）"""
    now = now or utcnow()
    prs = gh_all(f"repos/{REPO}/pulls?state=open")
    open_prs = {p["number"]: p for p in prs}  # 順番の指定は、ほかの開いている PR も見る
    marked = sorted((p for p in prs if has_label(p, OK["name"]) and only in (None, p["number"])), key=lambda p: p["number"])
    if not marked:
        out(f"{OK['name']} の付いた PR はない" + (f"（#{only} だけ見た）" if only else ""))
    merged, grace, error = [], [], False
    for pr in marked:
        try:
            state, left = process(pr, open_prs, dry, now)
        except ApiError as e:
            out(f"#{pr['number']}: GitHub に聞けなかった（{e}）。次に見直す")
            error = True
            continue
        if state == "merged":
            merged.append(pr["number"])
            open_prs.pop(pr["number"], None)  # このあとの PR の順番の指定のため
        elif state == "grace":
            grace.append(left)
    return merged, (min(grace) if grace else None), error


def publish(dry):
    if dry:
        out(f"（ためし）公開（{PUBLISH}）を {BASE} で1回動かすはず")
        return
    gh(f"repos/{REPO}/actions/workflows/{PUBLISH}/dispatches", "POST", {"ref": BASE})
    out(f"公開（{PUBLISH}）を {BASE} で動かした（結果は見張りが見る）")


def main():
    dry = os.environ.get("MERGE_OK_DRY_RUN", "").lower() == "true"
    only = os.environ.get("MERGE_OK_PR", "").strip()
    if only and not only.isdigit():
        out("MERGE_OK_PR は数字だけ")
        return 2
    only = int(only) if only else None
    if dry:
        out("ためし（dry_run）: マージ・コメント・ラベル・公開はしない")
    else:
        ensure_labels()
    merged, grace, error = run_once(dry, only=only)
    if grace and not dry:  # 点検のない PR: 10分たつまでここで待って、もう1回だけ見る
        out(f"点検（check-runs）のない PR があるので、{grace} 秒待って見直す")
        sleep(min(grace, GRACE) + 5)
        more, _, error2 = run_once(dry, only=only)
        merged += more
        error = error or error2
    if merged:
        publish(dry)
    return 1 if error else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ApiError as e:
        print(f"マージの印: GitHub に聞けませんでした（{e}）")
        sys.exit(1)
