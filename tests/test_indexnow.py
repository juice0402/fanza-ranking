"""検索エンジンへのお知らせ（IndexNow。scripts/indexnow.py）のテスト。
実行: python3 tests/test_indexnow.py
（ネットには出ない。本番の記録と IndexNow の受け口は、この中で立てる小さなサーバー（127.0.0.1）で代わりをする）"""
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import indexnow  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


S = indexnow.SITE_URL

print("■ えらび方（choose）")
now = {"/": "2026-10-17", "/item/a1/": "2026-10-17", "/doujin/item/d1/": "2026-10-16", "/weekly/2026-10-12/": "2026-10-13",
       "/ranking/": "2026-10-17", "/actress/x/": "2026-10-17", "/month/2026-09/": "2026-10-13", "/month/2026-10/": "2026-10-17", "/new/": "2026-10-17"}
prev = {"/": ["2026-10-12", "2026-10-12"],            # 一覧（トップ）: 5日前に知らせた → 待つ
        "/item/a1/": ["2026-10-15", "2026-10-15"],     # 作品ページ: コメントを書き直した → すぐ
        "/doujin/item/d1/": ["2026-10-16", "2026-10-16"],  # 変わっていない
        "/weekly/2026-10-12/": ["2026-10-13", "2026-10-13"],
        "/ranking/": ["2026-10-09", "2026-10-10"],     # 一覧（ランキング）: 7日たった → 知らせる
        "/actress/x/": ["2026-10-16", "2026-10-11"],   # 6日 → 待つ
        "/month/2026-09/": ["2026-10-08", "2026-10-09"],  # 月のまとめ記事が10/13に入った → すぐ
        "/month/2026-10/": ["2026-10-16", "2026-10-16"],  # 今月のページ（毎日変わる）→ 待つ
        "/gone/": ["2026-10-01", "2026-10-01"]}        # sitemap から消えた
send, record, count = indexnow.choose(now, prev, "2026-10-17", {"/month/2026-09/": "2026-10-13"})
check("新しいページ（前回の記録に無い）は知らせる", "/new/" in send, send)
check("作品ページ（売り場も）は、lastmod（コメントを書いた日）が変わったらすぐ", "/item/a1/" in send and "/doujin/item/d1/" not in send, send)
check("月のまとめ記事が新しく入った月のページは、すぐ", "/month/2026-09/" in send, send)
check("一覧・ランキング・今月のページは、前に知らせてから7日たつまで待つ", not {"/", "/actress/x/", "/month/2026-10/"} & set(send), send)
check("7日たった一覧は知らせる", "/ranking/" in send, send)
check("変わっていないページは知らせない", "/weekly/2026-10-12/" not in send and "/doujin/item/d1/" not in send, send)
check("内訳を数える（新しい1・作品と記事2・一覧など1）", count == {"new": 1, "content": 2, "list": 1}, count)
check("知らせたページの記録は、今回の lastmod と今日", record["/item/a1/"] == ["2026-10-17", "2026-10-17"] and record["/new/"] == ["2026-10-17", "2026-10-17"], record)
check("待っているページは、前の記録のまま持ち越す（7日たったら知らせるように）", record["/"] == prev["/"] and record["/actress/x/"] == prev["/actress/x/"], record)
check("sitemap に無いページは、記録からも消す", "/gone/" not in record and set(record) == set(now), sorted(record))
send2, _, _ = indexnow.choose(now, record, "2026-10-17", {"/month/2026-09/": "2026-10-13"})
check("同じ日にもう一度公開しても、同じページを知らせ直さない", send2 == [], send2)
send3, _, _ = indexnow.choose(now, record, "2026-10-19", {})
check("2日後、7日たった一覧（前に知らせたのが10/12のトップ・10/11の女優）だけを知らせる", send3 == ["/", "/actress/x/"], send3)
first, rec1, c1 = indexnow.choose(now, None, "2026-10-17", {})
check("はじめて（前回の記録が無い）は、sitemap の全部", sorted(first) == sorted(now) and c1["new"] == len(now), first)

print("\n■ sitemap の読み取り")
tmp = tempfile.mkdtemp()
dist = os.path.join(tmp, "dist")
os.makedirs(dist)
sm = ('<?xml version="1.0"?><urlset>'
      f"<url><loc>{S}/</loc><lastmod>2026-10-17</lastmod></url>"
      f"<url><loc>{S}/item/a1/</loc><lastmod>2026-10-16T00:00:00+09:00</lastmod></url>"
      f"<url><loc>{S}/about/</loc></url>"
      "<url><loc>https://example.com/x/</loc></url></urlset>")
open(os.path.join(dist, "sitemap.xml"), "w", encoding="utf-8").write(sm)
pages = indexnow.read_sitemap(os.path.join(dist, "sitemap.xml"))
check("サイトの中の道と lastmod（日付まで）。lastmod の無いページは ''・ほかのサイトは入れない",
      pages == {"/": "2026-10-17", "/item/a1/": "2026-10-16", "/about/": ""}, pages)

print("\n■ 鍵")
key = indexnow.find_key()
check("site/public に、名前が英数字32文字で中身が鍵だけのファイルが1つ", re.fullmatch(r"[A-Za-z0-9]{32}", key)
      and open(os.path.join(ROOT, "site", "public", key + ".txt"), encoding="utf-8").read() == key, key)
check("_headers で、鍵と記録を検索結果に出さない・記録はいつも新しいものを返す",
      all(s in open(os.path.join(ROOT, "site", "public", "_headers"), encoding="utf-8").read()
          for s in [f"/{key}.txt\n  X-Robots-Tag: noindex", "/indexnow-pages.json\n  X-Robots-Tag: noindex\n  Cache-Control: no-cache"]))

print("\n■ 実際に動かす（本番の記録と IndexNow の受け口は、にせもの）")
state = {"record": None, "record_code": 404, "codes": [], "posts": []}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        code = state["record_code"]
        body = json.dumps(state["record"]).encode() if code == 200 else b"<html>not found</html>"
        self.send_response(code)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        state["posts"].append((self.headers.get("Content-Type"), data))
        code = state["codes"].pop(0) if state["codes"] else 200
        self.send_response(code)
        self.end_headers()
        self.wfile.write(b"" if code in (200, 202) else b'{"message":"bad"}')


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"
summary = os.path.join(tmp, "summary.md")
env = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy") and not k.startswith("GITHUB_")}
env.update({"DIST_DIR": dist, "LIVE_URL": base, "INDEXNOW_ENDPOINT": base + "/indexnow", "INDEXNOW_RETRY_WAIT": "0",
            "NO_PROXY": "*", "no_proxy": "*", "GITHUB_STEP_SUMMARY": summary})
listf = os.path.join(tmp, "urls.json")
mark = os.path.join(tmp, "uploaded")


def run(*args):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "indexnow.py"), *args], env=env, capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


many = "".join(f"<url><loc>{S}/item/c{i}/</loc><lastmod>2026-10-17</lastmod></url>" for i in range(12_345))
open(os.path.join(dist, "sitemap.xml"), "w", encoding="utf-8").write(f'<?xml version="1.0"?><urlset>{many}</urlset>')
code, out = run("prepare", "--out", listf)
rec = json.load(open(os.path.join(dist, "indexnow-pages.json"), encoding="utf-8"))
lst = json.load(open(listf, encoding="utf-8"))
check("はじめて（本番に記録が無い＝404）: 全部をえらび、今回の記録を dist に置く",
      code == 0 and len(lst["urls"]) == 12_345 and len(rec["pages"]) == 12_345 and lst["urls"][0].startswith(S + "/"), out)
code, out = run("send", "--list", listf, "--uploaded", mark)
check("アップロードの印が無ければ、知らせない", code == 0 and not state["posts"], out)
open(mark, "w").close()
state["codes"] = [202, 200]
code, out = run("send", "--list", listf, "--uploaded", mark)
p = state["posts"]
check("1万件ずつに分けて送る（10,000件・2,345件）", [len(x[1]["urlList"]) for x in p] == [10_000, 2_345], [len(x[1]["urlList"]) for x in p])
check("送る中身: host・鍵・鍵の場所・JSON", p and p[0][1]["host"] == S.split("://")[1] and p[0][1]["key"] == key
      and p[0][1]["keyLocation"] == f"{S}/{key}.txt" and p[0][0].startswith("application/json"), p[0][1] if p else None)
check("結果は注記に1行（件数・返事）", code == 0 and "::notice title=IndexNow" in out and "12,345件を知らせました" in out and "返事 202・200" in out, out)
check("実行結果の要約にも出す", "12,345件を知らせました" in open(summary, encoding="utf-8").read())

state.update(record=rec, record_code=200, posts=[], codes=[])
code, out = run("prepare", "--out", listf)
code, out = run("send", "--list", listf, "--uploaded", mark)
check("本番の記録と同じなら、知らせない（「変わったページが無い」）", code == 0 and not state["posts"] and "変わったページが無い" in out, out)

state.update(posts=[], codes=[403, 403])
open(os.path.join(dist, "sitemap.xml"), "w", encoding="utf-8").write(f'<?xml version="1.0"?><urlset>{many}<url><loc>{S}/item/new1/</loc><lastmod>2026-10-17</lastmod></url></urlset>')
code, out = run("prepare", "--out", listf)
check("新しいページが1つ増えたら、それだけえらぶ", json.load(open(listf, encoding="utf-8"))["urls"] == [S + "/item/new1/"], out)
code, out = run("send", "--list", listf, "--uploaded", mark)
check("断られても失敗にはしない（注意書きに返事の番号）", code == 0 and "::warning title=IndexNow" in out and "403" in out and len(state["posts"]) == 1, out)

state.update(posts=[], codes=[500, 200])
code, out = run("send", "--list", listf, "--uploaded", mark)
check("混んでいる・つながらない（500など）ときは、1回だけやり直す", code == 0 and len(state["posts"]) == 2 and "1件を知らせました" in out, out)

state.update(record_code=500, posts=[])
code, out = run("prepare", "--out", listf)
code2, out2 = run("send", "--list", listf, "--uploaded", mark)
check("前回の記録を読めないときは、全部を送り直さない（知らせない・注意書き）。今回の状態は記録する",
      code == 0 and code2 == 0 and not state["posts"] and "::warning" in out2 and "読めなかった" in out2
      and len(json.load(open(os.path.join(dist, "indexnow-pages.json"), encoding="utf-8"))["pages"]) == 12_346, out + out2)

print("\n■ 受け付けてもらえなかったページの送り直し（GitHub の Actions の置き場 cache にとっておく）")
recf = os.path.join(dist, "indexnow-pages.json")
retryf = os.path.join(tmp, "retry.json")
ghout = os.path.join(tmp, "gh_output")
env["GITHUB_OUTPUT"] = ghout
new2 = f"<url><loc>{S}/item/new2/</loc><lastmod>2026-10-17</lastmod></url>"
open(os.path.join(dist, "sitemap.xml"), "w", encoding="utf-8").write(f'<?xml version="1.0"?><urlset>{many}{new2}</urlset>')
state.update(record=json.load(open(recf, encoding="utf-8")), record_code=200, posts=[], codes=[403])
run("prepare", "--out", listf, "--retry", retryf)
code, out = run("send", "--list", listf, "--uploaded", mark, "--retry-out", retryf)
kept = json.load(open(retryf, encoding="utf-8"))
check("断られたページを書き出し、置き場にとっておく合図（retry=written）を出す",
      list(kept) == [S + "/item/new2/"] and "retry=written" in open(ghout, encoding="utf-8").read() and "次の公開で送り直します" in out, (kept, out))
state.update(record=json.load(open(recf, encoding="utf-8")), posts=[], codes=[200])
code, out = run("prepare", "--out", listf, "--retry", retryf)
lst = json.load(open(listf, encoding="utf-8"))
check("次の公開で、記録の上では送った扱いのページを、もう一度えらぶ", lst["urls"] == [S + "/item/new2/"] and "前に断られたページ 1" in lst["note"], lst)
code, out = run("send", "--list", listf, "--uploaded", mark, "--retry-out", retryf)
check("受け付けてもらえたら、送り直しの一覧は空になる", state["posts"] and state["posts"][0][1]["urlList"] == [S + "/item/new2/"]
      and json.load(open(retryf, encoding="utf-8")) == {}, out)
json.dump({S + "/item/new2/": "2026-01-01", S + "/item/gone/": indexnow.today_jst()}, open(retryf, "w", encoding="utf-8"))
state.update(record=json.load(open(recf, encoding="utf-8")))
run("prepare", "--out", listf, "--retry", retryf)
check("はじめて断られてから14日たったページ・sitemap から消えたページは、送り直さない", json.load(open(listf, encoding="utf-8"))["urls"] == [])
open(retryf, "w").write("keep")
os.remove(ghout)
os.remove(mark)
code, out = run("send", "--list", listf, "--uploaded", mark, "--retry-out", retryf)
check("公開されなかったときは、送り直しの一覧を書きかえない（置き場の前のものをそのまま使う）",
      open(retryf).read() == "keep" and not os.path.exists(ghout), out)
open(mark, "w").close()
state.update(record={"v": 1, "pages": state["record"]["pages"]}, posts=[])
run("prepare", "--out", listf)
check("古い版（v1）の記録は「まだ無い」とみなして、全部を知らせ直す", len(json.load(open(listf, encoding="utf-8"))["urls"]) == 12_346
      and json.load(open(recf, encoding="utf-8"))["v"] == indexnow.VERSION)

os.remove(listf)
code, out = run("send", "--list", listf, "--uploaded", mark)
check("えらべていなかったら（えらぶ手順が失敗）、知らせない・失敗にもしない", code == 0 and "::warning" in out, out)
code, out = run()
check("まちがった使い方は 2", code == 2, out)
srv.shutdown()

print("\n■ ワークフロー（deploy.yml）と公開の道具")
dep = open(os.path.join(ROOT, ".github", "workflows", "deploy.yml"), encoding="utf-8").read()
check("えらぶのは、全ページの点検のあと・アップロードの前（本番のときだけ）",
      dep.index("python3 tests/verify_dist.py") < dep.index("indexnow.py prepare") < dep.index("bash scripts/deploy_workers.sh production")
      and re.search(r"Choose pages[^\n]*\n\s*if: github.ref == 'refs/heads/main'\n\s*continue-on-error: true", dep))
check("知らせるのは、アップロードのあと。あとの公開に止められても、アップロード済みなら知らせる（always()）・本番だけ・失敗しても止めない",
      dep.index("bash scripts/deploy_workers.sh production") < dep.index("indexnow.py send")
      and re.search(r"Tell search engines[^\n]*\n(?:\s*id: indexnow\n)?\s*if: always\(\) && github.ref == 'refs/heads/main'\n\s*continue-on-error: true", dep)
      and 'UPLOADED_MARK: ${{ runner.temp }}/uploaded' in dep and '--uploaded "$RUNNER_TEMP/uploaded"' in dep)
check("main にコミットを足さない（記録はサイトといっしょに公開）", "git push" not in dep and "git commit" not in dep)
check("送り直しの一覧: えらぶ前に置き場から読み、知らせたあとでとっておく（知らせる手順が動いたときだけ）",
      dep.index("actions/cache/restore@v4") < dep.index("indexnow.py prepare") < dep.index("indexnow.py send") < dep.index("actions/cache/save@v4")
      and "--retry .indexnow-retry.json" in dep and "--retry-out .indexnow-retry.json" in dep and "restore-keys: indexnow-retry-" in dep
      and "if: always() && steps.indexnow.outputs.retry == 'written'" in dep and dep.count("path: .indexnow-retry.json") == 2
      and ".indexnow-retry.json" in open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read())
sh = open(os.path.join(ROOT, "scripts", "deploy_workers.sh"), encoding="utf-8").read()
check("deploy_workers.sh: 本番のアップロードに成功したあと（確かめる前）に、印を付ける（2026-10-28 から本番は Workers。issue #188）",
      sh.index("$WRANGLER deploy") < sh.index('if [ "$rc" -ne 0 ]', sh.index("$WRANGLER deploy")) < sh.index('Workers に出しました') < sh.index(': > "$UPLOADED_MARK"') < sh.index("workers.dev で、新しい中身になったか"))
sh = open(os.path.join(ROOT, "scripts", "deploy_pages.sh"), encoding="utf-8").read()
check("deploy_pages.sh（Pages に戻すとき用）: 本番のアップロードに成功したあと（確かめる前）に、印を付ける",
      sh.index('if [ "$rc" -ne 0 ]') < sh.index('本番に公開しました') < sh.index(': > "$UPLOADED_MARK"') < sh.index("本当に新しくなったか"))

print(f"\n=== {passed}/{passed + failed} 合格 ===")
sys.exit(1 if failed else 0)
