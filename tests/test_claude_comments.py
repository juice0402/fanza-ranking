"""scripts/claude_comments.py（Claude がコメントを書くための道具）のテスト

本番データではなく、固定した20件（tests/fixtures/archive_20items.json）のコピーで試します。
実行: python3 tests/test_claude_comments.py   （どこから実行してもOK）
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "claude_comments.py")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "archive_20items.json")

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ✅ " if cond else "  ❌ ") + name + (f"  → {detail}" if (detail and not cond) else ""))


tmp = tempfile.mkdtemp(prefix="claude_comments_test_")
DATA = os.path.join(tmp, "data.json")


def fresh_data():
    shutil.copy(FIXTURE, DATA)


def run(*args):
    env = dict(os.environ, DATA_PATH=DATA)
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=env, encoding="utf-8")


def read_text():
    with open(DATA, encoding="utf-8") as f:
        return f.read()


def read_data():
    return json.loads(read_text())


def write_comments(name, payload):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return path


def good_comment(item, n=0):
    """条件を満たす（40文字以上・出演者名1回・絵文字なし）コメントを、作品ごとに違う文で作る"""
    who = (item.get("actress") or ["注目の出演者"])[0]
    bodies = [
        f"{who}の出演作が発売に向けて登場。発売日が近づくほど気になってくる、新作棚の注目の一本です。",
        f"{who}が出演する新作です。発売日に合わせてチェックしておきたい、見逃せない作品のひとつ。",
        f"新作棚にまた一本。{who}の出演で、発売日をいまから楽しみにしている方も多そうな作品です。",
    ]
    return bodies[n % len(bodies)] + f"（見どころその{n}）"  # 末尾の数字で、1件ごとに別の文になる


fresh_data()
original = read_data()
templates = [x for x in original if x["comment_kind"] == "template"]
ais = [x for x in original if x["comment_kind"] == "ai"]

print("■ 前提（固定データ）")
check("固定データに定型文とAIコメントの両方がある", len(templates) >= 5 and len(ais) >= 2, (len(templates), len(ais)))
check("何も変えずに書き戻すと、ファイルが1バイトも変わらない（差分が余計に出ない）",
      json.dumps(original, ensure_ascii=False, indent=1) + "\n" == read_text())

print("\n■ list（コメントを書く対象を出す）")
r = run("list", "--today", "2026-11-03", "--limit", "100")
check("list が成功する", r.returncode == 0, r.stderr)
out = json.loads(r.stdout)
cids = [x["cid"] for x in out["items"]]
check("対象は定型文の作品だけ（AIコメントの作品は出ない）", set(cids) == {x["cid"] for x in templates}, cids)
check("total_pending が定型文の件数と同じ", out["total_pending"] == len(templates) == out["shown"])
check("作品タイトルは出力しない", "title" not in r.stdout and not any(x["title"] in r.stdout for x in original))
check("画像やURLなど、不要な項目も出さない", all(set(x) == {"cid", "status", "date", "actress", "maker", "tags"} for x in out["items"]))
statuses = [x["status"] for x in out["items"]]
check("発売済みが先、予約があと", statuses == sorted(statuses, key=lambda s: 0 if s == "発売済み" else 1), statuses)
check("--today を基準に 発売済み/予約 を分ける",
      {x["cid"] for x in out["items"] if x["status"] == "発売済み"} == {"urvrsp00633", "savr01219", "1dldss00568", "1dldss00567", "1dldss00560"},
      statuses)
released_dates = [x["date"] for x in out["items"] if x["status"] == "発売済み"]
upcoming_dates = [x["date"] for x in out["items"] if x["status"] == "予約"]
check("発売済みは新しい順、予約は発売日の近い順", released_dates == sorted(released_dates, reverse=True) and upcoming_dates == sorted(upcoming_dates))
check("日付は YYYY-MM-DD", all(len(x["date"]) == 10 for x in out["items"]))
# 作品の内容を表す日本語のタグ（タイトルの【…】由来）は、書き手に見せない
data = read_data()
data[1]["tags"] = ["VR", "痴●団地", "8K", "授乳"]
data[2]["tags"] = ["ケツずり"]
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
    f.write("\n")
tag_out = {x["cid"]: x["tags"] for x in json.loads(run("list", "--limit", "100").stdout)["items"]}
mixed = [c for c in (data[1]["cid"], data[2]["cid"]) if c in tag_out]
check("list の形式タグは英数字（VR・8K など）だけ。日本語のタグは出さない",
      "痴" not in json.dumps(tag_out, ensure_ascii=False) and "ケツ" not in json.dumps(tag_out, ensure_ascii=False)
      and (data[1]["cid"] not in tag_out or tag_out[data[1]["cid"]] == ["VR", "8K"])
      and (data[2]["cid"] not in tag_out or tag_out[data[2]["cid"]] == []), tag_out)
check("確認に使った項目が、実際に list の対象に入っていた（確認が空振りでない）", len(mixed) >= 1, mixed)
fresh_data()
original = read_data()

r2 = run("list", "--today", "2026-11-03", "--limit", "3")
check("--limit で件数を絞れる", json.loads(r2.stdout)["shown"] == 3 and json.loads(r2.stdout)["total_pending"] == len(templates))

print("\n■ apply（点検して書き込む）")
sample = templates[:4]
good = {x["cid"]: good_comment(x, i) for i, x in enumerate(sample)}
path = write_comments("good.json", good)

r = run("apply", path, "--dry-run")
check("--dry-run は成功して、ファイルを変えない", r.returncode == 0 and read_data() == original, r.stdout + r.stderr)

r = run("apply", path)
check("正しいコメントは書き込める", r.returncode == 0, r.stdout + r.stderr)
after = read_data()
by_cid = {x["cid"]: x for x in after}
check("書いた作品は comment と comment_kind=ai になる",
      all(by_cid[c]["comment"] == t and by_cid[c]["comment_kind"] == "ai" for c, t in good.items()))
check("件数と並び順は変わらない", [x["cid"] for x in after] == [x["cid"] for x in original])
changed = {}
for old, new in zip(original, after):
    diff = {k for k in set(old) | set(new) if old.get(k) != new.get(k)}
    if diff:
        changed[old["cid"]] = diff
check("変わったのは、書いた作品の comment と comment_kind だけ",
      set(changed) == set(good) and all(d <= {"comment", "comment_kind"} for d in changed.values()), changed)
check("タイトル・URL・画像などは1つも変わらない",
      all({k: v for k, v in o.items() if k not in ("comment", "comment_kind")} == {k: v for k, v in n.items() if k not in ("comment", "comment_kind")}
          for o, n in zip(original, after)))
check("書き込み後も list の対象が減っている",
      json.loads(run("list", "--limit", "100").stdout)["total_pending"] == len(templates) - len(sample))
check("書き込み後のファイルの書き方が元と同じ（インデント1・日本語そのまま・末尾に改行）",
      read_text() == json.dumps(after, ensure_ascii=False, indent=1) + "\n")
check("作業用の .tmp ファイルが残らない", not os.path.exists(DATA + ".tmp"))

print("\n■ apply が断るもの（1件でも問題があれば何も書かない）")
fresh_data()
base = read_text()
t0, t1 = templates[0], templates[1]


def rejected(label, comments, expect=None):
    path = write_comments("bad.json", comments)
    r = run("apply", path)
    untouched = read_text() == base
    msg = r.stdout + r.stderr
    ok = r.returncode == 1 and untouched and (expect is None or expect in msg)
    check(label, ok, f"終了コード{r.returncode} / 変更なし={untouched} / {msg[:200]}")


ok_text = good_comment(t1, 1)
rejected("短すぎるコメント", {t0["cid"]: "短い文です。"}, "文字数")
rejected("長すぎるコメント", {t0["cid"]: "あ" * 121}, "文字数")
rejected("改行が入っている", {t0["cid"]: good_comment(t0)[:30] + "\n" + good_comment(t0)[30:]}, "改行")
rejected("URLが入っている", {t0["cid"]: good_comment(t0) + " https://example.com/"}, "URL")
rejected("絵文字が入っている", {t0["cid"]: good_comment(t0) + "😊"}, "絵文字")
rejected("飾りの記号（★）が入っている", {t0["cid"]: good_comment(t0) + "★"}, "絵文字や飾り")
rejected("マークダウンの記号が入っている", {t0["cid"]: "**" + good_comment(t0)}, "使えない記号")
rejected("直接的な言葉が入っている", {t0["cid"]: good_comment(t0) + "中出し"}, "使えない言葉")
rejected("未成年をにおわせる言葉が入っている", {t0["cid"]: good_comment(t0) + "少女のような"}, "使えない言葉")
rejected("「今日」など、日がたつと古くなる言い方が入っている", {t0["cid"]: good_comment(t0) + "今日の新着です"}, "古くなる")
rejected("出演者名が2回入っている", {t0["cid"]: good_comment(t0) + t0["actress"][0]}, "2回以上")
rejected("同じ文章を複数の作品に使い回している", {t0["cid"]: ok_text, t1["cid"]: ok_text}, "同じ文章")
rejected("保存データにない cid", {"no-such-cid": ok_text}, "ない cid")
rejected("Geminiが書いたAIコメントは上書きしない", {ais[0]["cid"]: ok_text}, "上書きしません")
rejected("文字列でないコメント", {t0["cid"]: 12345}, "文字列")
rejected("良いコメントと悪いコメントが混ざっていたら、良いほうも書かない",
         {t0["cid"]: good_comment(t0), t1["cid"]: "短い"}, "文字数")

same = {t0["cid"]: t0["comment"]}
path = write_comments("same.json", same)
r = run("apply", path)
check("いまのコメントと同じ文は断る", r.returncode == 1 and "いまのコメントと同じ" in r.stdout and read_text() == base, r.stdout)

print("\n■ apply の入力の形・特別な場合")
fresh_data()
path = write_comments("list_form.json", [{"cid": t0["cid"], "comment": good_comment(t0)}, {"cid": t1["cid"], "comment": good_comment(t1, 1)}])
r = run("apply", path)
check("[{cid, comment}] のリスト形式でも書き込める", r.returncode == 0 and sum(x["comment_kind"] == "ai" for x in read_data()) == len(ais) + 2, r.stdout + r.stderr)

fresh_data()
path = write_comments("dup_list.json", [{"cid": t0["cid"], "comment": good_comment(t0)}, {"cid": t0["cid"], "comment": good_comment(t0, 1)}])
r = run("apply", path)
check("リスト形式で cid が重複していたら断る", r.returncode == 1 and read_text() == base, r.stdout + r.stderr)

path = write_comments("empty.json", {})
r = run("apply", path)
check("空のコメントは「何もしない」で成功（毎日の予約タスクで対象が0件の日のため）", r.returncode == 0 and read_text() == base, r.stdout + r.stderr)

r = run("apply", os.path.join(tmp, "missing.json"))
check("ファイルが無ければ断る", r.returncode != 0 and read_text() == base)
broken = os.path.join(tmp, "broken.json")
open(broken, "w").write("{not json")
r = run("apply", broken)
check("壊れたJSONは断る", r.returncode != 0 and read_text() == base)

print("\n■ 保存データが壊れているとき")
open(DATA, "w", encoding="utf-8").write("{壊れている")
check("list は止まる", run("list").returncode != 0)
check("apply も止まる（データを上書きしない）", run("apply", write_comments("g.json", {"x": ok_text})).returncode != 0
      and read_text() == "{壊れている")
open(DATA, "w", encoding="utf-8").write('{"cid": "a"}')
check("リストでないデータも止まる", run("list").returncode != 0)

print("\n■ 全件を書き換えた後")
fresh_data()
everything = {x["cid"]: good_comment(x, i) for i, x in enumerate(templates)}
r = run("apply", write_comments("all.json", everything))
check("定型文を全部まとめて書き換えられる", r.returncode == 0 and "残り0件" in r.stdout, r.stdout + r.stderr)
check("そのあと list は空になる", json.loads(run("list").stdout)["items"] == [])
check("全件が comment_kind ai になる", all(x["comment_kind"] == "ai" for x in read_data()))

print("\n■ ソースの安全チェック")
src = open(SCRIPT, encoding="utf-8").read()
check("標準ライブラリだけを使う（pip不要）", not any(l.startswith(("import requests", "from requests", "import anthropic")) for l in src.splitlines()))
check("APIキーなどの秘密を扱わない", "API_KEY" not in src and "os.environ.get(\"API_ID\"" not in src)

shutil.rmtree(tmp)
failed = [n for n, ok in results if not ok]
print(f"\n=== {len(results) - len(failed)}/{len(results)} 合格 ===")
if failed:
    print("失敗:", failed)
    sys.exit(1)
