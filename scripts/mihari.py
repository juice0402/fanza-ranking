"""見張り（.github/workflows/mihari.yml。2026-11-02 司令塔「見張りをサイトのプログラムにする」）。

公開・毎日の更新など、止まると困る実行が終わるたびに（workflow_run）動く。Claude を使わない＝トークンの節約。
前は Claude の予約タスク「FANZA 公開の失敗の見張り」（1日2回）が見ていた。
  - 失敗（failure・timed_out・startup_failure）→ GitHub の issue（ラベル mihari＝しょーくんに知らせるだけ）を作る。
    同じ題の開いた issue があれば作らず、その日（日本時間）にまだなら「まだ続いている（実行の URL）」のコメントを1つだけ。
  - 成功 → 同じ題の開いた issue に「直った（実行の URL）」とコメントして閉じる。
  - cancelled（あとの公開に含まれた）などは何もしない。
issue の本文: 何が止まったか・いつ・失敗した実行の URL・最後にうまくいった時刻とそのあとの失敗の回数・失敗したジョブとステップ・
失敗の注記（はじめの3つ。1つ200字まで）・週1回の見張り番（health.yml）のときは見張り番の注意。ログの全体は貼らない。

使い方（mihari.yml から。GitHub の鍵 GH_TOKEN が要る）:
  python3 scripts/mihari.py   workflow_run のときは、その実行を見る。
                              手で動かしたとき（workflow_dispatch）は、見張る workflow ごとに main のいちばん新しい実行
                              （cancelled 以外）を見る。MIHARI_RUN_ID があれば、その実行だけ。
                              MIHARI_DRY_RUN=true なら issue を作らず、作るはずの題と本文を出す。
標準ライブラリだけ。テストは tests/test_mihari.py
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

REPO = os.environ.get("GITHUB_REPOSITORY", "juice0402/fanza-ranking")
JST = timezone(timedelta(hours=9))
BOT = "github-actions[bot]"
LABEL = {"name": "mihari", "color": "d93f0b", "description": "見張りが見つけた。しょーくんに知らせるだけ"}
FAIL = ("failure", "timed_out", "startup_failure")
NOTES_MAX = 3        # 失敗の注記は、はじめのこの数だけ
WARNS_MAX = 5        # 見張り番の注意は、この数まで
TEXT_MAX = 200       # 注記は1つこの字数まで
SIGN = "見張り（.github/workflows/mihari.yml）が作った"

# 見張る workflow（ファイルの名前 → issue の題・何が止まったか）。mihari.yml の workflows: も name: で同じものを並べる
WATCH = {
    "deploy.yml": {"title": "【見張り】公開が失敗した",
                   "what": "サイトの公開（Deploy）が失敗して、本番のサイトが前のままになっています。",
                   "ask": "公開が止まってる"},
    "update.yml": {"title": "【見張り】毎日の更新が失敗した",
                   "what": "毎日の更新（新作・予約・セールなどを集める）が失敗して、データが新しくなっていません。",
                   "ask": "毎日の更新が止まってる"},
    "sale-refresh.yml": {"title": "【見張り】セールの読み直しが失敗した",
                         "what": "セールの読み直しが失敗して、セールの値段が新しくなっていないかもしれません。",
                         "ask": "セールの読み直しが止まってる"},
    "ten-yen.yml": {"title": "【見張り】10円セールの確認が失敗した",
                    "what": "10円セールの確認が失敗して、10円セールのページが新しくなっていないかもしれません。",
                    "ask": "10円セールの確認が止まってる"},
    "health.yml": {"title": "【見張り】週1回の見張り番が注意を出した",
                   "what": "週1回の見張り番（health.yml）が、この7日の運用に注意を見つけました（または見張り番が動けませんでした）。",
                   "ask": "見張り番が注意を出してる",
                   "warn_title": "見張り番"},  # scripts/health.py の TITLE（::warning title=見張り番::…）
}


class ApiError(RuntimeError):
    pass


def gh(path, method="GET", body=None):
    cmd = ["gh", "api", "-X", method, path]
    if body is not None:
        cmd += ["--input", "-"]
    r = subprocess.run(cmd, input=None if body is None else json.dumps(body), capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise ApiError((r.stderr or r.stdout).strip()[:200])
    return json.loads(r.stdout) if r.stdout.strip() else None


def out(line=""):
    print(line, flush=True)


# ---- 判定（GitHub に聞かない。テストする所） ----

def jst(iso):
    """GitHub の時刻（UTC・…Z）を日本時間に"""
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(JST)
    except (TypeError, ValueError):
        return None


def when(iso):
    t = jst(iso)
    return f"{t.month}月{t.day}日 {t.hour}:{t.minute:02d}（日本時間）" if t else "（時刻がわからない）"


def workflow_file(run):
    """実行の path（.github/workflows/deploy.yml）からファイルの名前"""
    return str(run.get("path") or "").split("@", 1)[0].rsplit("/", 1)[-1]


def kind(conclusion):
    """'fail'（issue を作る）・'ok'（閉じる）・None（何もしない。cancelled・skipped など）"""
    if conclusion in FAIL:
        return "fail"
    return "ok" if conclusion == "success" else None


def short(text):
    text = " ".join(str(text or "").split())
    return text if len(text) <= TEXT_MAX else text[:TEXT_MAX - 1] + "…"


def pick_notes(notes, warn_title=None):
    """check-runs の annotations から (失敗の注記 はじめの3つ, 見張り番の注意)。
    「Process completed with exit code 1.」は理由にならないので後ろへ回す"""
    fails = [short(a.get("message")) for a in notes if a.get("annotation_level") == "failure"]
    fails = [m for m in fails if not m.startswith("Process completed")] + [m for m in fails if m.startswith("Process completed")]
    warns = [short(a.get("message")) for a in notes
             if warn_title and a.get("annotation_level") == "warning" and a.get("title") == warn_title]
    return fails[:NOTES_MAX], warns[:WARNS_MAX]


def failed_parts(jobs):
    """失敗したジョブとステップ（「ジョブ / ステップ」）"""
    ok = ("success", "skipped", "neutral", None)
    parts = []
    for job in jobs:
        if job.get("conclusion") in ok:
            continue
        steps = [s.get("name", "") for s in job.get("steps") or [] if s.get("conclusion") not in ok]
        parts.append(f"{job.get('name', '')} / {'・'.join(steps)}" if steps else f"{job.get('name', '')}（{job.get('conclusion')}）")
    return parts


def history(runs, run_id):
    """runs（新しい順。同じ workflow の main の実行）から、この実行までで (最後の成功の時刻, そのあとの失敗の回数)"""
    done = [r for r in runs if r.get("status") == "completed" and int(r.get("id") or 0) <= int(run_id or 0)]
    last_ok, fails = None, 0
    for r in done:
        k = kind(r.get("conclusion"))
        if k == "ok":
            last_ok = r.get("updated_at")
            break
        if k == "fail":
            fails += 1
    return last_ok, max(fails, 1)


def build_body(cfg, run, parts, fails, warns, last_ok, n_fails):
    lines = [cfg["what"], "",
             f"- いつ: {when(run.get('updated_at'))}",
             f"- 失敗した実行: {run.get('html_url', '')}（{run.get('conclusion')}）"]
    if last_ok:
        lines.append(f"- 最後にうまくいったのは {when(last_ok)}。そのあとの失敗は {n_fails} 回（この回をふくむ）")
    else:
        lines.append(f"- 最近の実行に成功が見つからない（失敗 {n_fails} 回）")
    if parts:
        lines.append(f"- 失敗したところ: {'、'.join(parts)}")
    if fails:
        lines += ["", "失敗の注記（はじめの3つ）:"] + [f"- {m}" for m in fails]
    if warns:
        lines += ["", "見張り番の注意:"] + [f"- {m}" for m in warns]
    lines += ["", f"直すときは、FANZAのチャットで「{cfg['ask']}」と伝える（この issue の番号も）。", SIGN]
    return "\n".join(lines)


def midnight_utc(now):
    """その日（日本時間）の0時を、GitHub の時刻（UTC）で"""
    d = now.astimezone(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def noted_today(issue, comments, now):
    """その日（日本時間）に、もう知らせたか（issue を作った・見張りがコメントした）"""
    today = now.astimezone(JST).date()
    t = jst(issue.get("created_at"))
    if t and t.date() == today:
        return True
    return any((c.get("user") or {}).get("login") == BOT and (jst(c.get("created_at")) or now).date() == today
               for c in comments)


# ---- GitHub に聞く・書く ----

def find_open(title):
    for i in gh(f"repos/{REPO}/issues?state=open&labels={LABEL['name']}&per_page=100") or []:
        if i.get("title") == title and "pull_request" not in i:
            return i
    return None


def ensure_label():
    try:
        gh(f"repos/{REPO}/labels/{LABEL['name']}")
    except ApiError as e:
        if "404" not in str(e) and "Not Found" not in str(e):
            raise
        try:
            gh(f"repos/{REPO}/labels", "POST", LABEL)
        except ApiError as e2:
            if "already_exists" not in str(e2) and "422" not in str(e2):
                raise


def notes_of(jobs):
    notes = []
    for job in jobs:
        if job.get("conclusion") in ("success", "skipped", None):
            continue
        cid = str(job.get("check_run_url", "")).rsplit("/", 1)[-1]
        if cid.isdigit():
            notes += gh(f"repos/{REPO}/check-runs/{cid}/annotations") or []
    return notes


def handle(run, dry, now, runs=None):
    name = workflow_file(run)
    cfg = WATCH.get(name)
    if not cfg:
        out(f"{name or '（不明）'} は見張っていない。何もしない")
        return
    if run.get("head_branch") != "main":
        out(f"{name}: main ではない（{run.get('head_branch')}）。何もしない")
        return
    k = kind(run.get("conclusion"))
    if k is None:
        out(f"{name}: {run.get('conclusion')}。何もしない")
        return
    title = cfg["title"]
    issue = find_open(title)
    url = run.get("html_url", "")
    if k == "ok":
        if not issue:
            out(f"{name}: 成功。開いた issue なし")
            return
        if dry:
            out(f"（ためし）#{issue['number']} に「直った（{url}）」とコメントして閉じるはず")
            return
        gh(f"repos/{REPO}/issues/{issue['number']}/comments", "POST", {"body": f"直った（{url}）"})
        gh(f"repos/{REPO}/issues/{issue['number']}", "PATCH", {"state": "closed", "state_reason": "completed"})
        out(f"{name}: 成功。#{issue['number']} を閉じた")
        return
    if issue:
        comments = gh(f"repos/{REPO}/issues/{issue['number']}/comments?since={midnight_utc(now)}&per_page=100") or []
        if noted_today(issue, comments, now):
            out(f"{name}: 失敗。#{issue['number']} で今日はもう知らせた")
            return
        if dry:
            out(f"（ためし）#{issue['number']} に「まだ続いている（{url}）」とコメントするはず")
            return
        gh(f"repos/{REPO}/issues/{issue['number']}/comments", "POST", {"body": f"まだ続いている（{url}）"})
        out(f"{name}: 失敗。#{issue['number']} に「まだ続いている」とコメントした")
        return
    jobs = (gh(f"repos/{REPO}/actions/runs/{run['id']}/jobs?filter=latest") or {}).get("jobs") or []
    fails, warns = pick_notes(notes_of(jobs), cfg.get("warn_title"))
    if runs is None:
        runs = (gh(f"repos/{REPO}/actions/workflows/{name}/runs?branch=main&status=completed&per_page=50") or {}).get("workflow_runs") or []
    last_ok, n_fails = history(runs, run["id"])
    body = build_body(cfg, run, failed_parts(jobs), fails, warns, last_ok, n_fails)
    if dry:
        out(f"（ためし）作るはずの issue: {title}\n{body}")
        return
    ensure_label()
    made = gh(f"repos/{REPO}/issues", "POST", {"title": title, "body": body, "labels": [LABEL["name"]]}) or {}
    out(f"{name}: 失敗。issue #{made.get('number')} を作った")


def main():
    dry = os.environ.get("MIHARI_DRY_RUN", "").lower() == "true"
    now = datetime.now(timezone.utc)
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    if event == "workflow_run":
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
            handle(json.load(f).get("workflow_run") or {}, dry, now)
        return 0
    run_id = os.environ.get("MIHARI_RUN_ID", "").strip()
    if run_id:
        if not run_id.isdigit():
            out("MIHARI_RUN_ID は数字だけ")
            return 2
        handle(gh(f"repos/{REPO}/actions/runs/{run_id}") or {}, dry, now)
        return 0
    for name in WATCH:  # 手で動かしたとき: いちばん新しい実行を見る
        runs = (gh(f"repos/{REPO}/actions/workflows/{name}/runs?branch=main&status=completed&per_page=50") or {}).get("workflow_runs") or []
        latest = next((r for r in runs if kind(r.get("conclusion"))), None)
        if latest:
            handle(latest, dry, now, runs)
        else:
            out(f"{name}: 見る実行なし")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ApiError as e:
        print(f"見張り: GitHub に聞けませんでした（{e}）")
        sys.exit(1)
