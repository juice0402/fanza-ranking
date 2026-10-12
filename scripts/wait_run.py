"""GitHub の実行（毎日の更新・CI・公開）が終わるまで待って、結果を1行で出す道具。

Claude のトークンの節約のため（運営者の希望「クロードのトークンをできるだけ節約したい。サイトが確実に運用されることが優先」。2026-10-13）。
Claude が「終わった？」と何度も見に行くと、そのたびに会話の全部を読み直すことになる。待つのはこの道具の中（30秒ごと）にして、
Claude には結果だけを返す。

使い方（Claude の Bash は1回10分までなので、timeout を 600000 にして呼ぶ）:
  python3 scripts/wait_run.py update         今日（日本時間）の毎日の更新（update.yml）が済むまで待つ。
                                             済んでいなくて、動いている更新も、今日の更新の実行も無ければ、更新を動かしてから待つ
  python3 scripts/wait_run.py ci <コミット>    そのコミットの CI（check）が終わるまで待つ
  python3 scripts/wait_run.py deploy <コミット> そのコミット（main）の公開（deploy.yml）が終わるまで待つ。
                                             あとの Merge の公開に含まれた（cancelled）ときは、いちばん新しい公開を待つ

1回に待つのは WAIT_MAX 秒まで（ふだん 540秒＝9分）。終わりの印:
  0 成功 ／ 1 失敗（理由も出す）／ 3 まだ終わっていない（同じコマンドをもう一度）／ 2 使い方の間違い・GitHub に聞けない
標準ライブラリだけ。テストは tests/test_tools.py
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.environ.get("WAIT_REPO", "juice0402/fanza-ranking")
WAIT_MAX = int(os.environ.get("WAIT_MAX", "540"))
STEP = int(os.environ.get("WAIT_STEP", "30"))
JST = timezone(timedelta(hours=9))
# GitHub に続けて聞けなかったら、あきらめる回数
API_TRIES = 3
NOTE_LINES = 10


class ApiError(Exception):
    pass


def gh(path, method="GET", fields=()):
    """gh api を呼んで、JSON を返す（出力が空なら None）"""
    cmd = ["gh", "api", path]
    if method != "GET":
        cmd += ["-X", method]
    for k, v in fields:
        cmd += ["-f", f"{k}={v}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ApiError(str(e)[:200])
    if r.returncode != 0:
        raise ApiError((r.stderr or r.stdout).strip()[:200])
    text = r.stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        raise ApiError("GitHub の答えを読めませんでした")


def today_jst():
    return datetime.now(JST).strftime("%Y-%m-%d")


def jst_date(iso):
    """GitHub の時刻（UTC・…Z）を、日本時間の日付に"""
    try:
        t = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return ""
    return t.astimezone(JST).strftime("%Y-%m-%d")


def updated_today():
    """今日のデータ更新の記録が、いまの main に入っているか（scripts/already_updated.sh）"""
    subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=ROOT, capture_output=True, timeout=120)
    r = subprocess.run(["bash", os.path.join(ROOT, "scripts", "already_updated.sh"), "FETCH_HEAD"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    return r.returncode == 0


def valid_sha(s):
    return bool(re.fullmatch(r"[0-9a-f]{7,40}", s or ""))


def annotations(check_run_id):
    """CI の注釈（失敗の理由。ci.yml の「Show why it failed」）を、短く"""
    try:
        notes = gh(f"repos/{REPO}/check-runs/{check_run_id}/annotations?per_page=30") or []
    except ApiError:
        return []
    lines, failed_checks = [], []
    for n in notes:
        for raw in str(n.get("message") or "").splitlines():
            line = raw.strip()
            if not line:
                continue
            lines.append(line[:200])
            # テストの点検の失敗（「  ❌ 名前  → くわしく」。字下げがある）。わざと失敗させたときのエラー文（字下げなし）より先に出す
            if raw[:1].isspace() and line.startswith("❌"):
                failed_checks.append(line[:200])
    return (failed_checks or lines)[:NOTE_LINES]


def failed_steps(run_id):
    """公開の実行で、失敗した手順の名前"""
    try:
        jobs = (gh(f"repos/{REPO}/actions/runs/{run_id}/jobs") or {}).get("jobs") or []
    except ApiError:
        return []
    return [s.get("name", "") for j in jobs for s in (j.get("steps") or []) if s.get("conclusion") == "failure"]


class Ci:
    """そのコミットの CI（check）"""
    name = "CI（check）"

    def __init__(self, sha):
        self.sha = sha

    def poll(self):
        data = gh(f"repos/{REPO}/commits/{self.sha}/check-runs?per_page=100") or {}
        runs = [r for r in data.get("check_runs") or [] if r.get("name") == "check"]
        if not runs:
            return "wait", "CI はまだ始まっていません"
        run = max(runs, key=lambda r: r.get("started_at") or "")
        if run.get("status") != "completed":
            return "wait", "CI が動いています"
        if run.get("conclusion") == "success":
            return "ok", "成功"
        notes = annotations(run.get("id"))
        return "fail", f"{run.get('conclusion')}（理由: {' / '.join(notes) if notes else run.get('html_url', '')}）"


class Deploy:
    """そのコミット（main）の公開（deploy.yml）"""
    name = "公開（Deploy）"

    def __init__(self, sha):
        self.sha = sha

    def poll(self):
        data = gh(f"repos/{REPO}/actions/workflows/deploy.yml/runs?branch=main&per_page=20") or {}
        runs = data.get("workflow_runs") or []
        mine = [r for r in runs if str(r.get("head_sha", "")).startswith(self.sha)]
        if not mine:
            return "wait", "公開はまだ始まっていません"
        run = max(mine, key=lambda r: r.get("created_at") or "")
        if run.get("status") != "completed":
            return "wait", "公開が動いています"
        if run.get("conclusion") == "success":
            return "ok", "成功（本番に公開済み）"
        if run.get("conclusion") == "cancelled":
            # 続けて Merge したときは、新しいほうだけ公開する（deploy.yml）。いちばん新しい公開に含まれる
            later = [r for r in runs if (r.get("created_at") or "") > (run.get("created_at") or "")]
            if not later:
                return "fail", "取り消されました（あとの公開もありません）"
            newest = max(later, key=lambda r: r.get("created_at") or "")
            if newest.get("status") != "completed":
                return "wait", "あとの Merge の公開を待っています"
            if newest.get("conclusion") == "success":
                return "ok", "成功（あとの Merge の公開に含まれて、本番に公開済み）"
            return "fail", f"あとの Merge の公開が {newest.get('conclusion')}（サイトは前の公開のまま）"
        steps = failed_steps(run.get("id"))
        why = f"失敗した手順: {'・'.join(steps)}" if steps else run.get("html_url", "")
        return "fail", f"{run.get('conclusion')}（{why}。サイトは前の公開のまま）"


class Update:
    """今日の毎日の更新（update.yml）"""
    name = "今日の更新"

    def __init__(self, updated=None):
        self.dispatched = False
        self.updated = updated or updated_today

    def poll(self):
        if self.updated():
            return "ok", "済んでいます"
        runs = (gh(f"repos/{REPO}/actions/workflows/update.yml/runs?per_page=10") or {}).get("workflow_runs") or []
        if any(r.get("status") != "completed" for r in runs):
            return "wait", "更新が動いています"
        today = today_jst()
        todays = [r for r in runs if jst_date(r.get("created_at")) == today]
        if any(r.get("conclusion") == "success" for r in todays):
            # 今日の更新は終わったのに、記録が無い＝保存するものが無かった。もう一度動かさない（Gemini を二重に使わない）
            return "ok", "終わっています（保存するものはありませんでした）"
        if todays:
            return "fail", f"今日の更新が {todays[0].get('conclusion')} でした（いまのデータのまま続ける）"
        if self.dispatched:
            return "wait", "動かした更新が始まるのを待っています"
        gh(f"repos/{REPO}/actions/workflows/update.yml/dispatches", method="POST", fields=[("ref", "main")])
        self.dispatched = True
        print("▶ 今日の更新がまだ動いていなかったので、動かしました", flush=True)
        return "wait", "動かした更新が始まるのを待っています"


def minutes(sec):
    return f"{sec // 60}分{sec % 60:02d}秒" if sec >= 60 else f"{sec}秒"


def wait(target, wait_max=None, step=None, now=time.monotonic, sleep=time.sleep):
    """終わるまで待つ。(終わりの印, 1行) を返す"""
    wait_max = WAIT_MAX if wait_max is None else wait_max
    step = STEP if step is None else step
    start = now()
    errors = 0
    msg = ""
    while True:
        try:
            state, msg = target.poll()
            errors = 0
        except ApiError as e:
            errors += 1
            if errors >= API_TRIES:
                return 2, f"⚠️ {target.name}: GitHub に聞けませんでした（{e}）"
            state, msg = "wait", "GitHub に聞き直します"
        took = int(now() - start)
        if state == "ok":
            return 0, f"✅ {target.name}: {msg}（{minutes(took)}待ちました）"
        if state == "fail":
            return 1, f"❌ {target.name}: {msg}"
        if took + step > wait_max:
            return 3, f"⏳ {target.name}: {msg}（{minutes(took)}待ちました。同じコマンドで、もう一度待ってください）"
        sleep(step)


USAGE = "使い方: python3 scripts/wait_run.py update | ci <コミット> | deploy <コミット>"


def main(argv):
    if not argv or argv[0] not in ("update", "ci", "deploy"):
        print(USAGE)
        return 2
    kind = argv[0]
    if kind == "update":
        target = Update()
    else:
        sha = argv[1] if len(argv) > 1 else ""
        if not valid_sha(sha):
            print(USAGE + "（コミットは英数字7〜40文字）")
            return 2
        target = Ci(sha) if kind == "ci" else Deploy(sha)
    code, line = wait(target)
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
