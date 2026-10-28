"""公開のしくみ（Cloudflare Workers への直接アップロード scripts/deploy_workers.sh・戻すときのための Pages の scripts/deploy_pages.sh と .github/workflows/）のテスト。
実行: python3 tests/test_deploy.py
（ネットには出ない。wrangler は、受け取った引数を書き出すだけの、にせものに差しかえる。鍵も作ったもの）"""
import os
import re
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "deploy_pages.sh")
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


tmp = tempfile.mkdtemp()
FAKE_TOKEN = "fake-token-0123456789abcdef"


def make_repo(changed_files):
    """作業用の git の置き場（scripts/deploy_pages.sh と、できあがったサイトのつもりの dist）。
    1つ目のコミットのあと、changed_files を変えて2つ目のコミットを作る"""
    repo = tempfile.mkdtemp(dir=tmp)
    git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *a], cwd=repo, check=True, capture_output=True)
    git("init", "-q")
    os.makedirs(os.path.join(repo, "scripts"))
    with open(os.path.join(repo, "scripts", "deploy_pages.sh"), "w", encoding="utf-8") as f:
        f.write(read("scripts", "deploy_pages.sh"))
    for path in ["site/src/data/new_releases.json", "site/src/pages/index.astro", "README.md"]:
        os.makedirs(os.path.dirname(os.path.join(repo, path)) or repo, exist_ok=True)
        open(os.path.join(repo, path), "w").write("1")
    git("add", "-A")
    git("commit", "-q", "-m", "first")
    for path in changed_files:
        os.makedirs(os.path.dirname(os.path.join(repo, path)) or repo, exist_ok=True)
        open(os.path.join(repo, path), "w").write("2")
    git("add", "-A")
    git("commit", "-q", "--allow-empty", "-m", "second")
    os.makedirs(os.path.join(repo, "site", "dist"))
    open(os.path.join(repo, "site", "dist", "index.html"), "w").write("<!doctype html><title>t</title>")
    open(os.path.join(repo, "site", "dist", "sitemap.xml"), "w").write("<urlset></urlset>")
    return repo


def make_wrangler(exit_code=0, url_prefix="abc123"):
    """にせものの wrangler（受け取った引数と、鍵が環境変数で届いたかを書き出す）"""
    folder = tempfile.mkdtemp(dir=tmp)
    log = os.path.join(folder, "args.txt")
    path = os.path.join(folder, "wrangler")
    with open(path, "w") as f:
        f.write(f"""#!/usr/bin/env bash
printf '%s\\n' "$@" > {log}
echo "token_set=${{CLOUDFLARE_API_TOKEN:+yes}} account=${{CLOUDFLARE_ACCOUNT_ID}}" >> {log}
echo "Uploading... (2/2)"
if [ {exit_code} -ne 0 ]; then echo "✘ [ERROR] A request to the Cloudflare API failed."; exit {exit_code}; fi
echo "✨ Deployment complete! Take a peek over at https://{url_prefix}.fanza-ranking.pages.dev"
echo "✨ Deployment alias URL: https://claude-test.fanza-ranking.pages.dev"
""")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path, log


def run(repo, args, wrangler, secrets=True, extra_env=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLOUDFLARE_", "GITHUB_"))}
    env.update({"WRANGLER": wrangler, "LIVE_URL": "", "GITHUB_STEP_SUMMARY": os.path.join(repo, "summary.md")})
    if secrets:
        env.update({"CLOUDFLARE_API_TOKEN": FAKE_TOKEN, "CLOUDFLARE_ACCOUNT_ID": "0" * 32})
    env.update(extra_env or {})
    r = subprocess.run(["bash", "scripts/deploy_pages.sh", *args], cwd=repo, env=env, capture_output=True, text=True)
    summary = open(env["GITHUB_STEP_SUMMARY"], encoding="utf-8").read() if os.path.exists(env["GITHUB_STEP_SUMMARY"]) else ""
    return r.returncode, r.stdout + r.stderr, summary


def args_of(log):
    return open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []


print("■ 本番への公開（scripts/deploy_pages.sh production）")
repo = make_repo(["site/src/pages/index.astro"])
w, log = make_wrangler()
code, out, summary = run(repo, ["production"], w)
a = args_of(log)
check("成功で終わる", code == 0, out)
check("site/dist を fanza-ranking の main（本番）へ送る",
      a[:2] == ["pages", "deploy"] and a[2] == "site/dist" and "--project-name=fanza-ranking" in a and "--branch=main" in a, a)
check("コミットの印（40文字）と、英数字だけの説明を付ける",
      any(re.fullmatch(r"--commit-hash=[0-9a-f]{40}", x) for x in a)
      and any(x.startswith("--commit-message=") and x.isascii() for x in a) and "--commit-dirty=true" in a, a)
check("鍵は環境変数で wrangler に届く（引数には入れない）", "token_set=yes account=" + "0" * 32 in a and not any(FAKE_TOKEN in x for x in a[:-1]), a)
check("鍵をログ・要約に出さない", FAKE_TOKEN not in out and FAKE_TOKEN not in summary)
check("実行結果の要約に「本番に公開しました」", "本番に公開しました" in summary, summary)

code, out, _ = run(repo, ["production"], w, secrets=False)
check("鍵が無ければ、本番は失敗にする（気づけるように）", code == 1 and "CLOUDFLARE_API_TOKEN" in out, out)

w_bad, _ = make_wrangler(exit_code=1)
code, out, summary = run(repo, ["production"], w_bad)
check("アップロードに失敗したら、失敗で終わり、理由を注釈（::error）に出す", code == 1 and "::error title=公開に失敗しました" in out and "Cloudflare API failed" in out, out)

repo_nodist = make_repo(["README.md"])
os.remove(os.path.join(repo_nodist, "site", "dist", "index.html"))
w2, log2 = make_wrangler()
code, out, _ = run(repo_nodist, ["production"], w2)
check("ビルドができていなければ送らない", code == 1 and not os.path.exists(log2), out)

print("\n■ 本番が新しくなったかの確認")
srv = tempfile.mkdtemp(dir=tmp)
open(os.path.join(srv, "sitemap.xml"), "w").write("<urlset></urlset>")
w3, _ = make_wrangler()
code, out, summary = run(repo, ["production"], w3, extra_env={"LIVE_URL": "file://" + srv, "CHECK_TRIES": "1", "CHECK_WAIT": "0"})
check("公開先の sitemap.xml が、いま作ったものと同じなら「確かめました」", code == 0 and "確かめました" in summary, out + summary)
open(os.path.join(srv, "sitemap.xml"), "w").write("<urlset>old</urlset>")
code, out, summary = run(repo, ["production"], w3, extra_env={"LIVE_URL": "file://" + srv, "CHECK_TRIES": "2", "CHECK_WAIT": "0"})
check("古いままでも失敗にはしない（注意書きだけ）", code == 0 and "::warning title=公開の確認" in out, out)

print("\n■ プレビュー（scripts/deploy_pages.sh preview <ブランチ名> [比べる元]）")
w4, log4 = make_wrangler()
code, out, summary = run(repo, ["preview", "claude/test", "HEAD^1"], w4)
a = args_of(log4)
check("コード・デザインの変更は、そのブランチのプレビューへ送る（本番の main には送らない）",
      code == 0 and "--branch=claude/test" in a and "--branch=main" not in a, (code, a, out))
check("プレビューのURLを、注釈（::notice）と要約に出す",
      "::notice title=プレビュー::https://claude-test.fanza-ranking.pages.dev" in out and "https://abc123.fanza-ranking.pages.dev" in summary, out)

repo_data = make_repo(["site/src/data/new_releases.json", "site/src/data/catalog/2026-01.json"])
w5, log5 = make_wrangler()
code, out, summary = run(repo_data, ["preview", "claude/comments-20261010-0021", "HEAD^1"], w5)
check("データ（site/src/data/）だけの変更には、プレビューを作らない", code == 0 and not os.path.exists(log5) and "データだけ" in summary, out)

repo_mix = make_repo(["site/src/data/new_releases.json", "site/src/pages/index.astro"])
w6, log6 = make_wrangler()
code, out, _ = run(repo_mix, ["preview", "claude/mix", "HEAD^1"], w6)
check("データとコードの両方が変わっていれば、プレビューを作る", code == 0 and os.path.exists(log6), out)

repo_docs = make_repo(["README.md", "docs/notes.md", "tests/test_x.py"])
w_docs, log_docs = make_wrangler()
code, out, summary = run(repo_docs, ["preview", "claude/docs", "HEAD^1"], w_docs)
check("サイトの作り（site/）が変わらない変更（手順書・テストだけ）には、プレビューを作らない",
      code == 0 and not os.path.exists(log_docs) and "site/）が変わっていない" in summary, out + summary)

w7, log7 = make_wrangler()
code, out, summary = run(repo, ["preview", "claude/test", "HEAD^1"], w7, secrets=False)
check("鍵が無ければ、プレビューは作らずに成功で終わる（ほかの人のPRなど）", code == 0 and not os.path.exists(log7) and "鍵が無い" in summary, out)

w8, _ = make_wrangler(exit_code=1)
code, out, _ = run(repo, ["preview", "claude/test"], w8)
check("プレビューの失敗は注意書き（::warning）", code == 1 and "::warning title=プレビューを作れませんでした" in out, out)

for bad in (["preview", "main"], ["preview"], ["publish"], []):
    w9, log9 = make_wrangler()
    code, _, _ = run(repo, bad, w9)
    check(f"まちがった使い方（{' '.join(bad) or '引数なし'}）では送らない", code == 2 and not os.path.exists(log9))

print("\n■ ワークフロー")
deploy = read(".github", "workflows", "deploy.yml")
check("deploy.yml: main に入ったとき・手動実行で動く", re.search(r"push:\s*\n\s*branches: \[main\]", deploy) and "workflow_dispatch:" in deploy)
check("deploy.yml: ビルド → 全ページの点検 → アップロードの順（点検に落ちたら公開しない）",
      deploy.index("npm run build") < deploy.index("python3 tests/verify_dist.py") < deploy.index("bash scripts/deploy_workers.sh production"))
check("deploy.yml: 本番になるのは main のときだけ（ほかのブランチは Workers のプレビュー）",
      'if [ "$REF_NAME" = "main" ]; then\n            bash scripts/deploy_workers.sh production\n          else\n            bash scripts/deploy_workers.sh preview "$REF_NAME"' in deploy
      and "REF_NAME: ${{ github.ref_name }}" in deploy)
check("deploy.yml: Pages には出さない（2万ファイルまでのため。issue #188）・アップロードできたら IndexNow の印",
      "bash scripts/deploy_pages.sh" not in deploy and "UPLOADED_MARK: ${{ runner.temp }}/uploaded" in deploy[deploy.index("- name: Upload to Cloudflare Workers"):])
check("deploy.yml: 鍵は Secrets から・権限は読むだけ・続けて Merge したら新しいほうだけ",
      "${{ secrets.CLOUDFLARE_WORKERS_TOKEN }}" in deploy and "${{ secrets.CLOUDFLARE_ACCOUNT_ID }}" in deploy
      and "permissions:\n  contents: read\n" in deploy and "cancel-in-progress: true" in deploy)
check("deploy.yml: Gemini・FANZA の鍵は渡さない", "GEMINI" not in deploy and "API_ID" not in deploy and "AFFILIATE_ID" not in deploy)

for name in ("update.yml", "refresh-data.yml"):
    wf = read(".github", "workflows", name)
    step = wf[wf.index("Commit and push if changed"):]
    check(f"{name}: 保存（push）したあとで、公開（deploy.yml）を頼む",
          step.index('git push origin "HEAD:${GITHUB_REF_NAME}"') < step.index('gh workflow run deploy.yml --ref "${GITHUB_REF_NAME}"')
          and "GH_TOKEN: ${{ github.token }}" in step and re.search(r"permissions:\s*\n\s*contents: write\s*\n\s*actions: write", wf))
    check(f"{name}: 変更が無い日は、保存も公開もしない", step.index("exit 0") < step.index("gh workflow run deploy.yml"))

# 10円セールの確認（1日に数回。2026-10-09）: 変わったときだけ保存して公開を頼む・保存するのは10円セールのデータだけ・毎日の更新と同じ順番待ち・Gemini の鍵は渡さない
ten = read(".github", "workflows", "ten-yen.yml")
tstep = ten[ten.index("Commit and deploy if changed"):]
check("ten-yen.yml: 10円の作品が変わったときだけ、保存（push）してから公開を頼む・保存するのは ten_yen.json だけ",
      "steps.ten.outputs.saved == '1'" in tstep and "--if-changed" in ten
      and tstep.index('git push origin "HEAD:${GITHUB_REF_NAME}"') < tstep.index('gh workflow run deploy.yml --ref "${GITHUB_REF_NAME}"')
      and "git add -- site/src/data/ten_yen.json" in tstep and "git add -A" not in tstep and tstep.index("exit 0") < tstep.index("gh workflow run deploy.yml"))
check("ten-yen.yml: 毎日の更新と同じ順番待ち（データが混ざらない）・Gemini の鍵は渡さない・1日に数回の定時実行",
      "group: daily-update" in ten and "GEMINI" not in ten and len(re.findall(r"- cron: '\d+ \d+ \* \* \*'", ten)) >= 3
      and re.search(r"permissions:\s*\n\s*contents: write\s*\n\s*actions: write", ten))
# 日中のセールの読み直し（運営者の「FANZAの動画は、だいたい10時にいつもセールの更新が入る」。2026-10-10）
sr = read(".github", "workflows", "sale-refresh.yml")
sstep = sr[sr.index("Commit and deploy if changed"):]
check("sale-refresh.yml: 10時すぎに動画のセールを読み直し、変わったときだけ保存（push）してから公開を頼む",
      "python get_new_releases.py --sales-only" in sr and "- cron: '17 1 * * *'" in sr
      and sstep.index('git push origin "HEAD:${GITHUB_REF_NAME}"') < sstep.index('gh workflow run deploy.yml --ref "${GITHUB_REF_NAME}"')
      and "git add -- site/src/data/sale.json site/src/data/sale_history.json" in sstep and "git add -A" not in sstep and sstep.index("exit 0") < sstep.index("gh workflow run deploy.yml"))
# 運営者の「動画基準で全ての売り場はもう10時更新で統一しちゃおう」（2026-10-10）: 売り場も同じ時刻に集め直す。保存するのは売り場のデータ・人気の動き・セールの記録だけ
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import floor_data as _FD  # noqa: E402
_sr_files = re.findall(r"site/src/data/[a-z_]+\.json", sstep[:sstep.index("git diff --staged")])
check("sale-refresh.yml: 全部の売り場も10時すぎに集め直す（失敗しても止めない）・保存するのは、どの売り場のデータと、人気の動き・セールの記録",
      "python scripts/doujin_game.py --update" in sr and sr.index("python get_new_releases.py --sales-only") < sr.index("python scripts/doujin_game.py")
      and "continue-on-error: true" in sr[sr.rindex("- name:", 0, sr.index("python scripts/doujin_game.py")):sr.index("python scripts/doujin_game.py")]
      and set(_sr_files) == {"site/src/data/sale.json", "site/src/data/sale_history.json", "site/src/data/floor_rank_history.json", "site/src/data/floor_sale_history.json",
                             "site/src/data/price_history.json", *(f"site/src/data/{k}.json" for k in _FD.FLOORS)}, _sr_files)
# 作品ごとの値段の記録（issue #183）: はじめて書く日まで無いので、あるときだけ git add する（無いファイルを名前で指定すると git add が失敗して、保存も公開も止まる）
check("sale-refresh.yml: 作品ごとの値段の記録（price_history.json）も保存する・ファイルがあるときだけ git add",
      "if [ -f site/src/data/price_history.json ]; then git add -- site/src/data/price_history.json; fi" in sstep[:sstep.index("git diff --staged")])
# 素人・アニメ・成人映画のキャンペーンごと（運営者の「素人のセールも、動画みたいに『○○セール』ごとに」。2026-10-12）:
# 0:35（と手動）だけ（キャンペーンは0時に入れかわる。10時の読み直しが20分遅れないように。運営者の「20分って結構かかるね。最適化できない？」。2026-10-12）。
# 動画のセールを保存・公開したあとに読み（日替わりセールの公開が遅れない）、もう一度、キャンペーンのデータだけを保存・公開する。失敗しても止めない
_fsl = sr.index("python scripts/floor_sales.py --update")
_fsl_step = sr[sr.rindex("- name:", 0, _fsl):_fsl]
_fsl_commit = sr[sr.index("Commit and deploy floor campaigns if changed"):]
check("sale-refresh.yml: 素人などのキャンペーンは 0:35（と手動）だけ・動画のセールを保存・公開したあとに読み、キャンペーンのデータだけをもう一度保存・公開する（失敗しても止めない）",
      "continue-on-error: true" in _fsl_step and "if: github.event.schedule != '17 1 * * *'" in _fsl_step and sr.index("Commit and deploy if changed") < _fsl
      and "if: github.event.schedule != '17 1 * * *'" in _fsl_commit[:200]
      and set(re.findall(r"site/src/data/[a-z_]+\.json", _fsl_commit[:_fsl_commit.index("git diff --staged")])) == {"site/src/data/floor_sale.json", "site/src/data/floor_sale_history.json"}
      and _fsl_commit.index('git push origin "HEAD:${GITHUB_REF_NAME}"') < _fsl_commit.index('gh workflow run deploy.yml --ref "${GITHUB_REF_NAME}"')
      and "python scripts/floor_sales.py --update" in read(".github", "workflows", "refresh-data.yml"))
check("sale-refresh.yml: 0:35 にも動画のセールを読み直す（0時に入れかわる日替わりセール）。売り場の集め直しは 0:35 には動かさない（0:05 の毎日の更新が集める）",
      "- cron: '35 15 * * *'" in sr and "if: github.event.schedule != '35 15 * * *'" in sr[sr.rindex("- name:", 0, sr.index("python scripts/doujin_game.py")):sr.index("python scripts/doujin_game.py")]
      and "if:" not in sr[sr.rindex("- name:", 0, sr.index("python get_new_releases.py --sales-only")):sr.index("python get_new_releases.py --sales-only")])
check("sale-refresh.yml: 毎日の更新と同じ順番待ち・Gemini の鍵は渡さない",
      "group: daily-update" in sr and "GEMINI" not in sr and re.search(r"permissions:\s*\n\s*contents: write\s*\n\s*actions: write", sr))
for name in ("update.yml", "refresh-data.yml"):
    wf = read(".github", "workflows", name)
    check(f"{name}: 10円セールも集める（失敗しても、ほかの更新は止めない）・保存の前",
          "python scripts/ten_yen.py --update" in wf and wf.index("scripts/ten_yen.py") < wf.index("Commit and push if changed")
          and "continue-on-error: true" in wf[wf.rindex("- name:", 0, wf.index("scripts/ten_yen.py")):wf.index("scripts/ten_yen.py")])

ci = read(".github", "workflows", "ci.yml")
prev = ci[ci.index("Preview on Cloudflare Workers"):]
check("ci.yml: PRのプレビューは、テスト・ビルド・点検のあと・同じリポジトリのPRだけ・失敗してもチェックの結果は変えない",
      ci.index("bash scripts/check.sh --build") < ci.index("Preview on Cloudflare Workers")
      and "github.event.pull_request.head.repo.full_name == github.repository" in prev and "continue-on-error: true" in prev[:600])
check("ci.yml: ブランチの名前は環境変数で渡す（そのまま命令に埋め込まない）・Merge の元（HEAD^1）と比べる",
      "HEAD_REF: ${{ github.head_ref }}" in prev and 'bash scripts/deploy_workers.sh preview "$HEAD_REF" HEAD^1' in prev
      and "fetch-depth: 2" in ci)
check("ci.yml: プレビューは Workers の鍵で（Pages には送らない）",
      "CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_WORKERS_TOKEN }}" in prev[:900] and "bash scripts/deploy_pages.sh" not in ci)

print("\n■ Workers への公開（scripts/deploy_workers.sh production。連絡 C-012）")


def make_workers_repo(routes=False):
    """deploy_workers.sh・workers/wrangler.jsonc・dist だけの作業場所（routes=True なら av-sale-guide.com の前に置いたあとの設定）"""
    repo = tempfile.mkdtemp(dir=tmp)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    os.makedirs(os.path.join(repo, "scripts"))
    os.makedirs(os.path.join(repo, "workers"))
    os.makedirs(os.path.join(repo, "site", "dist"))
    open(os.path.join(repo, "scripts", "deploy_workers.sh"), "w", encoding="utf-8").write(read("scripts", "deploy_workers.sh"))
    # 本物の設定から routes の行を消し、routes=True のときだけ足し直す（本物に routes があってもなくても、両方をためせるように）
    conf = "\n".join(l for l in read("workers", "wrangler.jsonc").split("\n") if not re.match(r'\s*"routes"\s*:', l))
    if routes:
        conf = conf.replace('"workers_dev": true,', '"workers_dev": true,\n  "routes": [{ "pattern": "av-sale-guide.com/*", "zone_name": "av-sale-guide.com" }],')
    open(os.path.join(repo, "workers", "wrangler.jsonc"), "w", encoding="utf-8").write(conf)
    open(os.path.join(repo, "site", "dist", "index.html"), "w").write("<!doctype html><title>t</title>")
    return repo


def commit_workers_repo(repo, changed_files):
    """プレビューの「比べる元」を試すため、1つ目のコミットのあと、changed_files を変えて2つ目のコミットを作る（dist は入れない）"""
    git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *a], cwd=repo, check=True, capture_output=True)
    open(os.path.join(repo, ".gitignore"), "w").write("site/dist/\n")
    git("add", "-A")
    git("commit", "-q", "-m", "first")
    for f in changed_files:
        path = os.path.join(repo, f)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write("changed\n")
    git("add", "-A")
    git("commit", "-q", "-m", "second")
    return repo


def make_workers_wrangler(exit_code=0):
    folder = tempfile.mkdtemp(dir=tmp)
    log = os.path.join(folder, "args.txt")
    path = os.path.join(folder, "wrangler")
    with open(path, "w") as f:
        f.write(f"""#!/usr/bin/env bash
printf '%s\\n' "$@" > {log}
echo "token_set=${{CLOUDFLARE_API_TOKEN:+yes}}" >> {log}
if [ {exit_code} -ne 0 ]; then echo "✘ [ERROR] A request to the Cloudflare API failed."; exit {exit_code}; fi
echo "Uploaded av-sale-guide"
if [ "$1" = "versions" ]; then
  echo "Version Preview URL: https://1a2b3c4d-av-sale-guide.juice-juice-0402.workers.dev"
  for i in "$@"; do if [ "$prev" = "--preview-alias" ]; then echo "Version Preview Alias URL: https://$i-av-sale-guide.juice-juice-0402.workers.dev"; fi; prev="$i"; done
else
  echo "Deployed av-sale-guide triggers"
fi
""")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path, log


def run_workers(repo, wrangler, secrets=True, args=("production",), extra_env=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLOUDFLARE_", "GITHUB_"))}
    env.update({"WRANGLER": wrangler, "LIVE_URL": "", "CHECK_TRIES": "1", "CHECK_WAIT": "0",
                "GITHUB_STEP_SUMMARY": os.path.join(repo, "summary.md")})
    if secrets:
        env.update({"CLOUDFLARE_API_TOKEN": FAKE_TOKEN, "CLOUDFLARE_ACCOUNT_ID": "0" * 32})
    env.update(extra_env or {})
    r = subprocess.run(["bash", "scripts/deploy_workers.sh", *args], cwd=repo, env=env, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


repo = make_workers_repo()
w, log = make_workers_wrangler()
code, out = run_workers(repo, w)
a = args_of(log)
check("Workers: workers/wrangler.jsonc で deploy する・鍵は環境変数で届く", code == 0 and a[:3] == ["deploy", "--config", "workers/wrangler.jsonc"] and "token_set=yes" in a, out)
check("Workers: どこから出ているかの印（__served-by.txt）を、コミットの印つきで作る",
      open(os.path.join(repo, "site", "dist", "__served-by.txt")).read().startswith("workers "))
mark = os.path.join(tmp, "uploaded-w")
code, out = run_workers(make_workers_repo(routes=True), make_workers_wrangler()[0], extra_env={"UPLOADED_MARK": mark})
check("Workers: アップロードできたら、IndexNow の印（UPLOADED_MARK）を付ける", code == 0 and os.path.exists(mark), out)
mark2 = os.path.join(tmp, "uploaded-w2")
code, out = run_workers(make_workers_repo(routes=True), make_workers_wrangler(exit_code=1)[0], extra_env={"UPLOADED_MARK": mark2})
check("Workers: アップロードに失敗したら、印は付けない", code == 1 and not os.path.exists(mark2), out)
check("Workers: 鍵がまだ無いときは、何もせずに成功（本番は Pages のまま）",
      run_workers(make_workers_repo(), make_workers_wrangler()[0], secrets=False)[0] == 0)
code, out = run_workers(make_workers_repo(), make_workers_wrangler(exit_code=1)[0])
check("Workers: routes の前の失敗は注意だけ（本番は Pages のまま）", code == 0 and "::warning" in out, out)
code, out = run_workers(make_workers_repo(routes=True), make_workers_wrangler(exit_code=1)[0])
check("Workers: routes のあと（本番が Workers）の失敗は、公開の失敗", code == 1 and "::error" in out, out)
code, out = run_workers(make_workers_repo(routes=True), make_workers_wrangler()[0], secrets=False)
check("Workers: routes のあとで鍵が無いのも、公開の失敗", code == 1 and "CLOUDFLARE_WORKERS_TOKEN" in out, out)
print("\n■ Workers のプレビュー（scripts/deploy_workers.sh preview <ブランチ名> [比べる元]。issue #188）")
repo = commit_workers_repo(make_workers_repo(routes=True), ["site/src/pages/index.astro"])
w, log = make_workers_wrangler()
code, out = run_workers(repo, w, args=("preview", "claude/Night_188.test", "HEAD^1"))
a = args_of(log)
summary = open(os.path.join(repo, "summary.md"), encoding="utf-8").read() if os.path.exists(os.path.join(repo, "summary.md")) else ""
check("プレビューは versions upload（本番の deploy はしない）・名前は英小文字と数字とハイフンだけ",
      code == 0 and a[:4] == ["versions", "upload", "--config", "workers/wrangler.jsonc"] and "deploy" not in a
      and a[a.index("--preview-alias") + 1] == "claude-night-188-test" and "token_set=yes" in a, (a, out))
check("プレビューの名前つきの URL を、注釈（::notice）と要約に出す（名前つきを先に）",
      "::notice title=プレビュー::https://claude-night-188-test-av-sale-guide.juice-juice-0402.workers.dev" in out
      and summary.index("claude-night-188-test-av-sale-guide") < summary.index("1a2b3c4d-av-sale-guide"), out + summary)
check("鍵をログ・要約に出さない（プレビュー）", FAKE_TOKEN not in out and FAKE_TOKEN not in summary)
w, log = make_workers_wrangler()
code, out = run_workers(commit_workers_repo(make_workers_repo(), ["site/src/pages/x.astro"]), w,
                        args=("preview", "claude/" + "very-long-branch-name-" * 4, "HEAD^1"))
al = args_of(log)[args_of(log).index("--preview-alias") + 1] if "--preview-alias" in args_of(log) else ""
check("長いブランチ名は40文字までに短くする（終わりにハイフンを残さない）", code == 0 and 0 < len(al) <= 40 and not al.endswith("-") and al.startswith("claude-"), al)
w, log = make_workers_wrangler()
code, out = run_workers(commit_workers_repo(make_workers_repo(), ["site/src/pages/x.astro"]), w, args=("preview", "123_fix", "HEAD^1"))
check("数字ではじまる名前は、英字ではじめる", "b-123-fix" in args_of(log), args_of(log))
w, log = make_workers_wrangler()
repo = commit_workers_repo(make_workers_repo(), ["site/src/data/new_releases.json"])
code, out = run_workers(repo, w, args=("preview", "claude/comments-20261010-0021", "HEAD^1"))
check("データ（site/src/data/）だけの変更には、プレビューを作らない", code == 0 and not os.path.exists(log) and "データだけ" in open(os.path.join(repo, "summary.md"), encoding="utf-8").read(), out)
w, log = make_workers_wrangler()
repo = commit_workers_repo(make_workers_repo(), ["docs/architecture.md", "tests/test_x.py"])
code, out = run_workers(repo, w, args=("preview", "claude/docs", "HEAD^1"))
check("サイトの作り（site/）が変わらない変更には、プレビューを作らない", code == 0 and not os.path.exists(log) and "変わっていない" in open(os.path.join(repo, "summary.md"), encoding="utf-8").read(), out)
w, log = make_workers_wrangler()
code, out = run_workers(commit_workers_repo(make_workers_repo(), ["site/src/data/a.json", "site/src/lib/a.js"]), w, args=("preview", "claude/mix", "HEAD^1"))
check("データとコードの両方が変わっていれば、プレビューを作る", code == 0 and os.path.exists(log), out)
w, log = make_workers_wrangler()
code, out = run_workers(commit_workers_repo(make_workers_repo(), ["site/src/lib/a.js"]), w, secrets=False, args=("preview", "claude/x", "HEAD^1"))
check("鍵が無ければ、プレビューは作らずに成功で終わる（ほかの人のPRなど）", code == 0 and not os.path.exists(log), out)
code, out = run_workers(commit_workers_repo(make_workers_repo(routes=True), ["site/src/lib/a.js"]), make_workers_wrangler(exit_code=1)[0], args=("preview", "claude/x"))
check("プレビューの失敗は注意書き（::warning。routes があっても本番の失敗にしない）", code == 1 and "::warning title=プレビューを作れませんでした" in out and "::error" not in out, out)
for bad in (("preview", "main"), ("preview",), ("publish",), ()):
    w, log = make_workers_wrangler()
    code, _ = run_workers(make_workers_repo(), w, args=bad)
    check(f"まちがった使い方（{' '.join(bad) or '引数なし'}）では送らない（Workers）", code == 2 and not os.path.exists(log))

conf = read("workers", "wrangler.jsonc")
check("workers/wrangler.jsonc: プレビューの URL を使う（preview_urls）", '"preview_urls": true' in conf)
check("workers/wrangler.jsonc: 静的ファイルだけ（main なし）・site/dist・Pages と同じ末尾の / と 404 の扱い",
      '"directory": "../site/dist"' in conf and '"html_handling": "auto-trailing-slash"' in conf
      and '"not_found_handling": "404-page"' in conf and '"main"' not in conf)
check("workers/wrangler.jsonc: routes を置くなら av-sale-guide.com だけ（custom_domain は使わない＝DNS の CNAME → Pages を残して、すぐ戻せる）",
      not re.search(r'^\s*"routes"\s*:', conf, re.M)
      or ('"pattern": "av-sale-guide.com/*"' in conf and '"zone_name": "av-sale-guide.com"' in conf and "custom_domain" not in conf))
deploy = read(".github", "workflows", "deploy.yml")
wstep = deploy[deploy.index("- name: Upload to Cloudflare Workers"):]
check("deploy.yml: Workers へは Workers 用の鍵で",
      "CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_WORKERS_TOKEN }}" in wstep[:600])

print("\n■ 設定の突き合わせ")
site_url = re.search(r"SITE_URL = '([^']+)'", read("site", "src", "config.js")).group(1)
check("送り先のプロジェクト（fanza-ranking）は、サイトのURL（config.js の SITE_URL）と同じ",
      'PROJECT="${PAGES_PROJECT:-fanza-ranking}"' in read("scripts", "deploy_pages.sh") and site_url == "https://av-sale-guide.com")
check("本番の確認先も、サイトのURL", f'LIVE_URL="${{LIVE_URL-{site_url}}}"' in read("scripts", "deploy_pages.sh"))

print(f"\n=== {passed}/{passed + failed} 合格 ===")
sys.exit(1 if failed else 0)
