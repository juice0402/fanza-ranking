"""公開のしくみ（Cloudflare Pages への直接アップロード。scripts/deploy_pages.sh と .github/workflows/）のテスト。
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
      deploy.index("npm run build") < deploy.index("python3 tests/verify_dist.py") < deploy.index("bash scripts/deploy_pages.sh production"))
check("deploy.yml: 本番になるのは main のときだけ（ほかのブランチはプレビュー）",
      'if [ "$REF_NAME" = "main" ]; then\n            bash scripts/deploy_pages.sh production\n          else\n            bash scripts/deploy_pages.sh preview "$REF_NAME"' in deploy
      and "REF_NAME: ${{ github.ref_name }}" in deploy)
check("deploy.yml: 鍵は Secrets から・権限は読むだけ・続けて Merge したら新しいほうだけ",
      "${{ secrets.CLOUDFLARE_API_TOKEN }}" in deploy and "${{ secrets.CLOUDFLARE_ACCOUNT_ID }}" in deploy
      and "permissions:\n  contents: read\n" in deploy and "cancel-in-progress: true" in deploy)
check("deploy.yml: Gemini・FANZA の鍵は渡さない", "GEMINI" not in deploy and "API_ID" not in deploy and "AFFILIATE_ID" not in deploy)

for name in ("update.yml", "refresh-data.yml"):
    wf = read(".github", "workflows", name)
    step = wf[wf.index("Commit and push if changed"):]
    check(f"{name}: 保存（push）したあとで、公開（deploy.yml）を頼む",
          step.index('git push origin "HEAD:${GITHUB_REF_NAME}"') < step.index('gh workflow run deploy.yml --ref "${GITHUB_REF_NAME}"')
          and "GH_TOKEN: ${{ github.token }}" in step and re.search(r"permissions:\s*\n\s*contents: write\s*\n\s*actions: write", wf))
    check(f"{name}: 変更が無い日は、保存も公開もしない", step.index("exit 0") < step.index("gh workflow run deploy.yml"))

ci = read(".github", "workflows", "ci.yml")
prev = ci[ci.index("Preview on Cloudflare Pages"):]
check("ci.yml: PRのプレビューは、テスト・ビルド・点検のあと・同じリポジトリのPRだけ・失敗してもチェックの結果は変えない",
      ci.index("bash scripts/check.sh --build") < ci.index("Preview on Cloudflare Pages")
      and "github.event.pull_request.head.repo.full_name == github.repository" in prev and "continue-on-error: true" in prev[:600])
check("ci.yml: ブランチの名前は環境変数で渡す（そのまま命令に埋め込まない）・Merge の元（HEAD^1）と比べる",
      "HEAD_REF: ${{ github.head_ref }}" in prev and 'bash scripts/deploy_pages.sh preview "$HEAD_REF" HEAD^1' in prev
      and "fetch-depth: 2" in ci)

print("\n■ 設定の突き合わせ")
site_url = re.search(r"SITE_URL = '([^']+)'", read("site", "src", "config.js")).group(1)
check("送り先のプロジェクト（fanza-ranking）は、サイトのURL（config.js の SITE_URL）と同じ",
      'PROJECT="${PAGES_PROJECT:-fanza-ranking}"' in read("scripts", "deploy_pages.sh") and site_url == "https://fanza-ranking.pages.dev")
check("本番の確認先も、サイトのURL", f'LIVE_URL="${{LIVE_URL-{site_url}}}"' in read("scripts", "deploy_pages.sh"))

print(f"\n=== {passed}/{passed + failed} 合格 ===")
sys.exit(1 if failed else 0)
