"""週1回の見張り番（運営者の希望「週1回の点検にしよう。タイミングは日曜日から月曜日に日付が変わるとき」。2026-10-13）。

Claude を使わずに、GitHub Actions（.github/workflows/health.yml。毎週月曜 0:01・日本時間）が、この7日（月曜〜日曜）の
運用の数字を見て、おかしいときだけ知らせる（注釈 ::warning と、実行の失敗＝GitHub からの知らせ）。前は、Claude の予約タスク
（過去作品の点検・半年ごとのリポジトリの大きさ）が見ていた。

見ること（どれも、データから数えた事実だけ）:
  1. 毎日の更新: この7日の「データ更新: 日付」の記録がそろっているか
  2. 公開・毎日の更新・セールの読み直し・10円セール（deploy.yml・update.yml・sale-refresh.yml・ten-yen.yml）:
     main の実行で、いちばん新しい実行が失敗していないか・この7日の失敗が3回以上ないか・公開が30分をこえていないか（上限は40分）
  3. Claude のコメント（毎日 0:20 の予約タスク）: この7日に Merge された「コメントの仕上げ」の日数（5日に満たなければ注意）
  4. 過去作品の数: コメントの無い過去作品が、決めた深さ（catalog_state.json の limit）の1.3倍をこえていて、7日前より減っていなければ注意
     （深さを浅くしたあとは、3日ごとの一回りで少しずつ外れる。2回続けて見かけなかった作品だけ外す＝scripts の prune_catalog）
  5. リポジトリの大きさ: 500MB をこえたら注意（GitHub のおすすめは1GBまで）

使い方:
  python3 scripts/health.py           見張る（health.yml から。GitHub の鍵 GH_TOKEN が要る）。注意があれば終わりの印 1
  python3 scripts/health.py --last    いちばん新しい見張りの結果を、1行ずつ出す（毎週月曜の Claude の予約タスクが、報告に書く）
標準ライブラリだけ。テストは tests/test_health.py
"""
import glob
import json
import os
import subprocess
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.environ.get("GITHUB_REPOSITORY", "juice0402/fanza-ranking")
DATA = os.path.join(ROOT, "site", "src", "data")
JST = timezone(timedelta(hours=9))
DAYS = 7
WORKFLOWS = (("deploy.yml", "公開"), ("update.yml", "毎日の更新"), ("sale-refresh.yml", "セールの読み直し"), ("ten-yen.yml", "10円セール"))
FAILS_MAX = 3            # この7日の失敗がこの回数以上なら注意
DEPLOY_WARN_MIN = 30     # 公開がこの分数をこえたら注意（deploy.yml の上限は40分）
COMMENT_DAYS_MIN = 5     # コメントの仕上げが Merge された日が、この日数に満たなければ注意
CATALOG_SLACK = 1.3      # コメントの無い過去作品が、深さのこの倍をこえていたら（7日前より減っていなければ）注意
REPO_WARN_KB = 512000    # 500MB
TITLE = "見張り番"


def gh(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:200])
    return json.loads(r.stdout or "null")


def git(*args):
    r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, timeout=120)
    return r.stdout if r.returncode == 0 else ""


def jst(iso):
    """GitHub の時刻（UTC・…Z）を日本時間に"""
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(JST)
    except (TypeError, ValueError):
        return None


def week_days(today):
    """見る7日（今日の前の日まで。月曜 0:01 なら、前の月曜〜日曜）"""
    return [(today - timedelta(days=i)).isoformat() for i in range(DAYS, 0, -1)]


# ---- 1つずつの見張り（どれも (注意の文のリスト, 表の1行) を返す。注意が無ければ空のリスト） ----

def check_updates(subjects, today):
    days = week_days(today)
    have = {s.split(": ", 1)[1] for s in subjects if s.startswith("データ更新: ")}
    missing = [d for d in days if d not in have]
    row = f"毎日の更新の記録: {DAYS - len(missing)}/{DAYS}日"
    return ([f"毎日の更新の記録が無い日があります（{'・'.join(m[5:].replace('-', '/') for m in missing)}）"] if missing else []), row


def check_runs(name, label, runs, since):
    """runs: GitHub の workflow_runs（新しい順）。since: 見る始まり（日本時間の datetime）"""
    done = [r for r in runs if r.get("status") == "completed" and (jst(r.get("created_at")) or since) >= since]
    fails = [r for r in done if r.get("conclusion") == "failure"]
    warn = []
    latest = next((r for r in runs if r.get("status") == "completed" and r.get("conclusion") != "cancelled"), None)
    if latest and latest.get("conclusion") != "success":
        warn.append(f"{label}（{name}）のいちばん新しい実行が {latest.get('conclusion')} です")
    if len(fails) >= FAILS_MAX:
        warn.append(f"{label}（{name}）がこの{DAYS}日に {len(fails)} 回失敗しています")
    longest = 0
    if name == "deploy.yml":
        for r in done:
            a, b = jst(r.get("run_started_at")), jst(r.get("updated_at"))
            if a and b and r.get("conclusion") == "success":
                longest = max(longest, int((b - a).total_seconds() // 60))
        if longest > DEPLOY_WARN_MIN:
            warn.append(f"公開にいちばん長くて {longest} 分かかりました（上限は40分）")
    row = f"{label}: {len(done)}回・失敗{len(fails)}回" + (f"・いちばん長くて{longest}分" if name == "deploy.yml" else "")
    return warn, row


def check_comments(prs, today):
    days = set(week_days(today))
    merged = {jst(p.get("merged_at")).date().isoformat() for p in prs
              if p.get("merged_at") and str((p.get("head") or {}).get("ref", "")).startswith("claude/comments-") and jst(p.get("merged_at"))}
    n = len(merged & days)
    row = f"コメントの仕上げ（Claude）の Merge: {n}/{DAYS}日"
    return ([f"コメントの仕上げ（毎日 0:20 の予約タスク）が Merge された日が {n} 日だけです"] if n < COMMENT_DAYS_MIN else []), row


def check_catalog(items_now, commented, limit, items_before):
    """items_now: 過去作品の本数・commented: そのうち Claude のコメントのある本数（外さないので数えない）・items_before: 7日前の本数（分からなければ None）"""
    plain = items_now - commented
    row = f"過去作品: {items_now:,}本（コメントの無い作品 {plain:,}本・深さ {limit:,}本" + (f"・7日前 {items_before:,}本）" if items_before is not None else "）")
    if limit and plain > limit * CATALOG_SLACK and (items_before is None or items_now >= items_before):
        return [f"コメントの無い過去作品が {plain:,} 本で、深さ（{limit:,}本）の{CATALOG_SLACK}倍をこえたまま減っていません"], row
    return [], row


def check_repo(size_kb):
    mb = round(size_kb / 1024)
    row = f"リポジトリの大きさ: {mb}MB"
    return ([f"リポジトリが {mb}MB になりました（GitHub のおすすめは1GBまで）。古い記録をまとめるなどの対策を Claude に相談してください"] if size_kb >= REPO_WARN_KB else []), row


# ---- 集めて、見張る ----

def catalog_numbers():
    state = json.load(open(os.path.join(DATA, "catalog_state.json"), encoding="utf-8"))
    commented = 0
    for path in glob.glob(os.path.join(DATA, "catalog", "*.json")):
        with open(path, encoding="utf-8") as f:
            commented += sum(1 for x in json.load(f) if isinstance(x, dict) and x.get("comment_kind") == "claude")
    before = None
    rev = git("rev-list", "-n", "1", f"--before={DAYS} days ago", "HEAD").strip()
    if rev:
        try:
            before = int(json.loads(git("show", f"{rev}:site/src/data/catalog_state.json") or "{}").get("items"))
        except (TypeError, ValueError):
            before = None
    return int(state.get("items") or 0), commented, int(state.get("limit") or 0), before


def run_checks(today=None):
    today = today or datetime.now(JST).date()
    since = datetime.combine(today - timedelta(days=DAYS), datetime.min.time(), JST)
    results = []
    results.append(check_updates(git("log", "-n", "400", "--format=%s").splitlines(), today))
    for name, label in WORKFLOWS:
        q = urllib.parse.quote(f">={(today - timedelta(days=DAYS + 1)).isoformat()}")
        try:
            runs = (gh(f"repos/{REPO}/actions/workflows/{name}/runs?branch=main&per_page=100&created={q}") or {}).get("workflow_runs") or []  # プレビュー（ブランチ）の公開の失敗は数えない
            results.append(check_runs(name, label, runs, since))
        except RuntimeError as e:
            results.append(([f"{label}（{name}）の実行を読めませんでした（{e}）"], f"{label}: 読めず"))
    try:
        prs = gh(f"repos/{REPO}/pulls?state=closed&sort=updated&direction=desc&per_page=100") or []
        results.append(check_comments(prs, today))
    except RuntimeError as e:
        results.append(([f"PR を読めませんでした（{e}）"], "コメントの仕上げ: 読めず"))
    try:
        results.append(check_catalog(*catalog_numbers()))
    except (OSError, ValueError) as e:
        results.append(([f"過去作品のデータを読めませんでした（{e}）"], "過去作品: 読めず"))
    try:
        results.append(check_repo(int((gh(f"repos/{REPO}") or {}).get("size") or 0)))
    except (RuntimeError, ValueError) as e:
        results.append(([], f"リポジトリの大きさ: 読めず（{e}）"))
    return results


def report(results, today, out=print):
    """注釈（::warning・::notice）と、実行の要約の表。注意があれば 1 を返す"""
    warns = [w for ws, _ in results for w in ws]
    for w in warns:
        out(f"::warning title={TITLE}::{w}")
    if not warns:
        out(f"::notice title={TITLE}::問題なし（{today.month}月{today.day}日・この{DAYS}日）")
    lines = [f"### 見張り番（{today.isoformat()}・この{DAYS}日）", "", "| 見たこと | 結果 |", "|---|---|"]
    lines += [f"| {row} | {'⚠️ ' + ' / '.join(ws) if ws else '✅'} |" for ws, row in results]
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    else:
        out("\n".join(lines))
    return 1 if warns else 0


def last(api=gh, out=print):
    """いちばん新しい見張りの結果を1行ずつ（毎週月曜の Claude の予約タスクが、報告に書く）"""
    runs = (api(f"repos/{REPO}/actions/workflows/health.yml/runs?per_page=1") or {}).get("workflow_runs") or []
    if not runs:
        out("見張り番: まだ動いていません")
        return 0
    run = runs[0]
    when = jst(run.get("created_at"))
    day = f"{when.month}月{when.day}日" if when else "?"
    if run.get("status") != "completed":
        out(f"見張り番（{day}）: まだ動いています")
        return 0
    notes = []
    for job in (api(f"repos/{REPO}/actions/runs/{run['id']}/jobs") or {}).get("jobs") or []:
        cid = str(job.get("check_run_url", "")).rsplit("/", 1)[-1]
        if cid.isdigit():
            notes += [a for a in (api(f"repos/{REPO}/check-runs/{cid}/annotations") or []) if a.get("title") == TITLE]
    warns = [a.get("message", "") for a in notes if a.get("annotation_level") == "warning"]
    if warns:
        for w in warns:
            out(f"⚠️ 見張り番（{day}）: {w}")
    elif run.get("conclusion") == "success":
        out(f"✅ 見張り番（{day}）: 問題なし")
    else:
        out(f"⚠️ 見張り番（{day}）: 実行が {run.get('conclusion')} でした（{run.get('html_url', '')}）")
    return 0


def main(argv):
    if argv[:1] == ["--last"]:
        try:
            return last()
        except RuntimeError as e:
            print(f"見張り番: 結果を読めませんでした（{e}）")
            return 0
    today = datetime.now(JST).date()
    return report(run_checks(today), today)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
