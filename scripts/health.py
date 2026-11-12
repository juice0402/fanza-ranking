"""週1回の見張り番（運営者の希望「週1回の点検にしよう。タイミングは日曜日から月曜日に日付が変わるとき」。2026-10-13）。

Claude を使わずに、GitHub Actions（.github/workflows/health.yml。毎週月曜 0:01・日本時間）が、この7日（月曜〜日曜）の
運用の数字を見て、おかしいときだけ知らせる（注釈 ::warning と実行の失敗。実行の失敗は mihari.yml が issue にする）。前は、Claude の予約タスク
（過去作品の点検・半年ごとのリポジトリの大きさ）が見ていた。

見ること（どれも、データから数えた事実だけ）:
  1. 毎日の更新: この7日の「データ更新: 日付」の記録がそろっているか
  2. 公開・毎日の更新・セールの読み直し・10円セール（deploy.yml・update.yml・sale-refresh.yml・ten-yen.yml）:
     main の実行で、いちばん新しい実行が失敗していないか（mihari.yml が動いていなかったときの念のため）・公開が70分をこえていないか（上限は100分）。
     この7日の失敗の回数は表に書くだけで、注意にしない（失敗はそのたびに mihari.yml が issue にして、次の成功で閉じる。
     もう直った失敗で毎週知らせない。2026-11-02。前は3回以上で注意にしていて、引っ越しの日の失敗で4週続けて失敗になった）
  3. Claude のコメント（毎日 0:20 の予約タスク）: この7日に Merge された「コメントの仕上げ」の日数（5日に満たなければ注意）
  4. 過去作品の数: 一回り（3日ほど）の終わりに外し終わったあとの本数で見る。外したあとのコメントの無い過去作品が、決めた深さ
     （catalog_state.json の limit）の1.5倍をこえて、外したあとの本数が3回続けてふえていたら注意（外すしくみ＝prune_catalog が止まっている形。
     10/18 にあった）。人気順は毎日入れかわるので、本数は一回りのあいだにふくらみ、外した日にへる（のこぎりの歯）。
     前は「いま」と「7日前」をくらべていて、山と谷のどちらに当たるかで注意が出たり出なかったりした（2026-11-02 に直した）
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
DEPLOY_WARN_MIN = 70     # 公開がこの分数をこえたら注意（deploy.yml の上限は100分。2026-11-12 に30から＝人気の女優を深く集めてファイルが6万ほどに）
COMMENT_DAYS_MIN = 5     # コメントの仕上げが Merge された日が、この日数に満たなければ注意
CATALOG_SLACK = 1.5      # 外したあとのコメントの無い過去作品が、深さのこの倍をこえて、
CATALOG_GROWS = 3        # 外したあとの本数が、この回数続けて
CATALOG_GROW_MIN = 300   # この本数以上ずつふえていたら注意（コメントの付いた作品は外さないので、少しずつはふえる。1日60件×3日でも180本）
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
    """runs: GitHub の workflow_runs（新しい順）。since: 見る始まり（日本時間の datetime）。
    失敗の回数は表に書くだけ（注意は、いちばん新しい実行がまだ失敗のときと、公開が長いときだけ。失敗は mihari.yml が知らせる）"""
    done = [r for r in runs if r.get("status") == "completed" and (jst(r.get("created_at")) or since) >= since]
    fails = [r for r in done if r.get("conclusion") == "failure"]
    warn = []
    latest = next((r for r in runs if r.get("status") == "completed" and r.get("conclusion") != "cancelled"), None)
    if latest and latest.get("conclusion") != "success":
        warn.append(f"{label}（{name}）のいちばん新しい実行が {latest.get('conclusion')} です")
    longest = 0
    if name == "deploy.yml":
        for r in done:
            a, b = jst(r.get("run_started_at")), jst(r.get("updated_at"))
            if a and b and r.get("conclusion") == "success":
                longest = max(longest, int((b - a).total_seconds() // 60))
        if longest > DEPLOY_WARN_MIN:
            warn.append(f"公開にいちばん長くて {longest} 分かかりました（上限は100分）")
    row = f"{label}: {len(done)}回・失敗{len(fails)}回" + (f"・いちばん長くて{longest}分" if name == "deploy.yml" else "")
    return warn, row


def check_comments(prs, today):
    days = set(week_days(today))
    merged = {jst(p.get("merged_at")).date().isoformat() for p in prs
              if p.get("merged_at") and str((p.get("head") or {}).get("ref", "")).startswith("claude/comments-") and jst(p.get("merged_at"))}
    n = len(merged & days)
    row = f"コメントの仕上げ（Claude）の Merge: {n}/{DAYS}日"
    return ([f"コメントの仕上げ（毎日 0:20 の予約タスク）が Merge された日が {n} 日だけです"] if n < COMMENT_DAYS_MIN else []), row


def pruned_points(history):
    """history: catalog_state.json の (一回りの番号 cycle, 本数 items) を、新しいコミットから順に。
    一回りごとに、その番号になった最初のコミット（外し終わった直後）の本数を、古い順に返す。
    いちばん古い番号は、記録の途中から始まっているかもしれないので使わない"""
    first = {}
    for cycle, items in history:  # 新しい順なので、あとから来たもの（古いコミット）で上書きすると、その番号の最初になる
        first[cycle] = items
    cycles = sorted(first)[1:]
    return [first[c] for c in cycles]


def check_catalog(items_now, commented, limit, points):
    """items_now: いまの過去作品の本数・commented: そのうち Claude のコメントのある本数（外さないので数えない）・
    points: 外し終わったあとの本数（古い順。pruned_points）"""
    if not points:
        return [], f"過去作品: いま {items_now:,}本（外したあとの本数は読めず・深さ {limit:,}本）"
    plain = points[-1] - commented  # コメントの数は、いまの数で引く（外さないので前の数より多い＝少なめに出る）
    recent = points[-(CATALOG_GROWS + 1):]
    growing = len(recent) == CATALOG_GROWS + 1 and all(b - a >= CATALOG_GROW_MIN for a, b in zip(recent, recent[1:]))
    row = (f"過去作品: 外したあと {points[-1]:,}本（コメントの無い作品 {plain:,}本・深さ {limit:,}本・"
           f"外したあとの移り {'→'.join(f'{p:,}' for p in recent)}・いま {items_now:,}本）")
    if limit and plain > limit * CATALOG_SLACK and growing:
        return [f"外したあとのコメントの無い過去作品が {plain:,} 本で、深さ（{limit:,}本）の{CATALOG_SLACK}倍をこえ、"
                f"外したあとの本数が{CATALOG_GROWS}回続けてふえています。過去作品を外すしくみ（prune_catalog）が止まっているかもしれません"], row
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
    history = []  # (一回りの番号, 本数)。新しいコミットから（health.yml の fetch-depth の中だけ。400 で4週ほど）
    for rev in git("log", "--first-parent", "--format=%H", "-n", "60", "HEAD", "--", "site/src/data/catalog_state.json").split():
        try:
            s = json.loads(git("show", f"{rev}:site/src/data/catalog_state.json") or "{}")
            history.append((int(s["cycle"]), int(s["items"])))
        except (TypeError, ValueError, KeyError):
            continue
    # 深さ＝人気の上位の本数（limit）＋人気の女優を深く集めて外さない作品の数（deep。2026-11-12。get_new_releases.py の deep_kept）
    return int(state.get("items") or 0), commented, int(state.get("limit") or 0) + int(state.get("deep") or 0), pruned_points(history)


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
