"""scripts/claude_comments.py（Claude がコメントを書くための道具）のテスト

本番データではなく、固定した20件（tests/fixtures/archive_20items.json）のコピーで試します。
実行: python3 tests/test_claude_comments.py   （どこから実行してもOK）
"""
import json
import os
import re
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
    """固定データのコピー。AIコメント（ai）のうち先頭の2件は、Claude が仕上げたもの（claude）にしておく"""
    with open(FIXTURE, encoding="utf-8") as f:
        items = json.load(f)
    n = 0
    for x in items:
        if x["comment_kind"] == "ai" and n < 2:
            x["comment_kind"] = "claude"
            n += 1
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
        f.write("\n")


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
    """条件を満たす（100文字以上・出演者名1回・絵文字なし・確かめられない評価や古くなる言い方なし）コメントを、作品ごとに違う文で作る"""
    who = (item.get("actress") or ["出演者"])[0]
    bodies = [
        f"{who}が出演する、発売日の決まっている新作です。作品の情報は、この詳細のページにまとめて載っていて、メーカーの一覧からも、同じメーカーのほかの作品をたどれます。収録時間や形式も、上の表で確かめられます。",
        f"{who}の出演作が、新作の棚に並びました。メーカーのページからは、同じメーカーのほかの作品もたどれます。くわしい内容はFANZAのページで確かめてください。発売日と収録時間は、上の表にまとめてあります。",
        f"新作の棚にまた一本が加わりました。出演は{who}で、収録時間や形式は、上の表にまとめて載せてあります。出演者の名前から、ほかの出演作もたどれます。くわしい内容は、FANZAの作品ページで確かめられます。",
    ]
    return bodies[n % len(bodies)] + f"（その{n}）"  # 末尾の数字で、1件ごとに別の文になる


fresh_data()
original = read_data()
templates = [x for x in original if x["comment_kind"] == "template"]
drafts = [x for x in original if x["comment_kind"] == "ai"]       # Gemini の下書き（仕上げの対象）
finals = [x for x in original if x["comment_kind"] == "claude"]   # Claude が仕上げたもの（対象外）
pending = templates + drafts

print("■ 前提（固定データ）")
check("固定データに、定型文・Geminiの下書き・Claudeが仕上げたものがある", len(templates) >= 5 and len(drafts) >= 2 and len(finals) == 2, (len(templates), len(drafts), len(finals)))
check("何も変えずに書き戻すと、ファイルが1バイトも変わらない（差分が余計に出ない）",
      json.dumps(original, ensure_ascii=False, indent=1) + "\n" == read_text())

print("\n■ list（コメントを書く対象を出す）")
r = run("list", "--today", "2026-11-03", "--limit", "100")
check("list が成功する", r.returncode == 0, r.stderr)
out = json.loads(r.stdout)
cids = [x["cid"] for x in out["items"]]
check("対象は、定型文とGeminiの下書き（Claudeが仕上げたものは出ない）", set(cids) == {x["cid"] for x in pending} and not (set(cids) & {x["cid"] for x in finals}), cids)
check("total_pending が、定型文と下書きの件数と同じ", out["total_pending"] == len(pending) == out["shown"])
check("タイトルは、安全チェックを通ったものだけ title に出す（それ以外は title_hidden: true で、タイトルを出さない）",
      all(("title" in x) != bool(x.get("title_hidden")) for x in out["items"])
      and all(x["title"] == next(o["title"] for o in original if o["cid"] == x["cid"]) for x in out["items"] if "title" in x)
      and all(next(o["title"] for o in original if o["cid"] == x["cid"]) not in r.stdout for x in out["items"] if x.get("title_hidden")))
BASE_KEYS = {"cid", "reason", "status", "date", "actress", "maker", "tags", "duration_min", "genres", "sample_movie", "sample_images", "min_len"}
check("画像やURLなど、不要な項目も出さない（サンプル動画・画像は、有無と枚数だけ）",
      all(set(x) - {"title", "title_hidden", "content_off", "fiction_theme"} == BASE_KEYS | ({"draft"} if x["reason"] == "下書きを仕上げる" else set()) for x in out["items"]) and "http" not in r.stdout,
      [sorted(set(x) - BASE_KEYS) for x in out["items"]])
check("下書きの作品には、いまの文（draft）を出す。定型文には出さない",
      all(x["draft"] == next(o["comment"] for o in original if o["cid"] == x["cid"]) for x in out["items"] if x["reason"] == "下書きを仕上げる")
      and all("draft" not in x for x in out["items"] if x["reason"] == "定型文"))
check("reason: 定型文は「定型文」、Geminiの下書きは「下書きを仕上げる」",
      {x["cid"]: x["reason"] for x in out["items"]} == {**{t["cid"]: "定型文" for t in templates}, **{d["cid"]: "下書きを仕上げる" for d in drafts}})
check("サンプル動画は true/false、サンプル画像は枚数", all(isinstance(x["sample_movie"], bool) and isinstance(x["sample_images"], int) for x in out["items"])
      and {x["cid"]: x["sample_images"] for x in out["items"]} == {t["cid"]: len(t.get("sample_images") or []) for t in pending})
check("収録時間（分）を出す。無いものは null", all((x["duration_min"] is None) or (isinstance(x["duration_min"], int) and x["duration_min"] > 0) for x in out["items"])
      and any(x["duration_min"] for x in out["items"]) and {x["cid"]: x["duration_min"] for x in out["items"]} == {t["cid"]: (t.get("duration_min") or None) for t in pending},
      {x["cid"]: x["duration_min"] for x in out["items"]})
statuses = [x["status"] for x in out["items"]]
reasons = [x["reason"] for x in out["items"]]
check("急ぐもの（定型文・予約の言い方が残っている）が先、Gemini の下書きがあと", reasons == sorted(reasons, key=lambda r: 1 if r == "下書きを仕上げる" else 0), reasons)
for label, group in (("定型文", [x for x in out["items"] if x["reason"] != "下書きを仕上げる"]), ("下書き", [x for x in out["items"] if x["reason"] == "下書きを仕上げる"])):
    st = [x["status"] for x in group]
    check(f"{label}の中は、発売済みが先、予約があと", st == sorted(st, key=lambda s: 0 if s == "発売済み" else 1), st)
check("--today を基準に 発売済み/予約 を分ける",
      all((x["status"] == "発売済み") == (x["date"] <= "2026-11-03") for x in out["items"]) and "予約" in statuses and "発売済み" in statuses,
      statuses)
tmpl_rows = [x for x in out["items"] if x["reason"] != "下書きを仕上げる"]
released_dates = [x["date"] for x in tmpl_rows if x["status"] == "発売済み"]
upcoming_dates = [x["date"] for x in tmpl_rows if x["status"] == "予約"]
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
# ジャンルは、サイトの「ジャンルのページ」と同じ、決めた一覧（config.js の TAG_PAGE_GENRES）にあるものだけ出す
data = read_data()
target = next(x for x in data if x["comment_kind"] != "claude")
target["genres"] = ["巨乳", "中出し", "ハイビジョン", "女子校生", "OL"]
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
    f.write("\n")
g_out = {x["cid"]: x["genres"] for x in json.loads(run("list", "--limit", "100").stdout)["items"]}
check("ジャンルは決めた一覧のものだけ（過激な言葉・未成年を連想させる言葉は出さない）", g_out.get(target["cid"]) == ["巨乳", "ハイビジョン", "OL"], g_out.get(target["cid"]))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import claude_comments as cc_mod  # noqa: E402
check("ジャンルの一覧を config.js から読める（10個以上）", len(cc_mod.safe_genres_from_config()) >= 10, cc_mod.safe_genres_from_config())
check("config.js が読めなければ、ジャンルを出さないだけ（止まらない）", cc_mod.safe_genres_from_config(os.path.join(tmp, "nothing.js")) == [])
data = read_data()
weird = [(data[1], 0), (data[1], -5), (data[1], "90"), (data[1], True), (data[1], 87)]
got = []
for x, v in weird:
    x["duration_min"] = v
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    row = [y for y in json.loads(run("list", "--limit", "100").stdout)["items"] if y["cid"] == x["cid"]]
    got.append(row[0]["duration_min"] if row else "対象外")
check("収録時間が 0・負の数・文字列・true のときは null、正の整数ならそのまま出す", got == [None, None, None, None, 87], got)
fresh_data()
original = read_data()

r2 = run("list", "--today", "2026-11-03", "--limit", "3")
check("--limit で件数を絞れる", json.loads(r2.stdout)["shown"] == 3 and json.loads(r2.stdout)["total_pending"] == len(pending))

print("\n■ apply（点検して書き込む）")
sample = templates[:4]
good = {x["cid"]: good_comment(x, i) for i, x in enumerate(sample)}
path = write_comments("good.json", good)

r = run("apply", path, "--dry-run")
check("--dry-run は成功して、ファイルを変えない", r.returncode == 0 and read_data() == original, r.stdout + r.stderr)

r = run("apply", path, "--today", "2026-11-03")
check("正しいコメントは書き込める", r.returncode == 0, r.stdout + r.stderr)
after = read_data()
by_cid = {x["cid"]: x for x in after}
check("書いた作品は comment と comment_kind=claude（Claude が仕上げたもの）になる",
      all(by_cid[c]["comment"] == t and by_cid[c]["comment_kind"] == "claude" for c, t in good.items()))
check("件数と並び順は変わらない", [x["cid"] for x in after] == [x["cid"] for x in original])
changed = {}
for old, new in zip(original, after):
    diff = {k for k in set(old) | set(new) if old.get(k) != new.get(k)}
    if diff:
        changed[old["cid"]] = diff
check("変わったのは、書いた作品の comment と comment_kind と updated（更新日）だけ",
      set(changed) == set(good) and all(d <= {"comment", "comment_kind", "updated"} for d in changed.values()), changed)
check("書いた作品の更新日は --today の日付になる。書いていない作品の更新日は動かない",
      all(by_cid[c]["updated"] == "2026-11-03" for c in good)
      and all(n["updated"] == o["updated"] for o, n in zip(original, after) if o["cid"] not in good), {c: by_cid[c]["updated"] for c in good})
check("タイトル・URL・画像などは1つも変わらない",
      all({k: v for k, v in o.items() if k not in ("comment", "comment_kind", "updated")} == {k: v for k, v in n.items() if k not in ("comment", "comment_kind", "updated")}
          for o, n in zip(original, after)))
check("書き込み後も list の対象が減っている",
      json.loads(run("list", "--limit", "100").stdout)["total_pending"] == len(pending) - len(sample))
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
rejected("長すぎるコメント", {t0["cid"]: "あ" * 201}, "文字数")
rejected("改行が入っている", {t0["cid"]: good_comment(t0)[:30] + "\n" + good_comment(t0)[30:]}, "改行")
rejected("URLが入っている", {t0["cid"]: good_comment(t0) + " https://example.com/"}, "URL")
rejected("絵文字が入っている", {t0["cid"]: good_comment(t0) + "😊"}, "絵文字")
rejected("飾りの記号（★）が入っている", {t0["cid"]: good_comment(t0) + "★"}, "絵文字や飾り")
rejected("マークダウンの記号が入っている", {t0["cid"]: "**" + good_comment(t0)}, "使えない記号")
rejected("直接的な言葉が入っている", {t0["cid"]: good_comment(t0) + "中出し"}, "使えない言葉")
rejected("未成年をにおわせる言葉が入っている", {t0["cid"]: good_comment(t0) + "少女のような"}, "使えない言葉")
rejected("「今日」など、日がたつと古くなる言い方が入っている", {t0["cid"]: good_comment(t0) + "今日の新着です"}, "古くなる")
rejected("確かめられない評価（待望・話題・注目の・ファンの…）が入っている", {t0["cid"]: good_comment(t0) + "待望の話題作で、ファンの期待も高い注目の一本です"}, "確かめられない評価")
rejected("発売日をすぎると古くなる言い方（予約受付中）が入っている", {t0["cid"]: good_comment(t0) + "いまなら予約受付中です"}, "古くなる言い方")
rejected("発売日をすぎると古くなる言い方（発売予定）が入っている", {t0["cid"]: good_comment(t0) + "11月1日に発売予定です"}, "古くなる言い方")
rejected("タイトルの言葉を、そのまま長く写している", {t0["cid"]: good_comment(t0) + t0["title"][-12:] if len(t0["title"]) >= 12 else good_comment(t0) + "あ" * 200}, None)
rejected("直接的な言葉（増やした一覧）が入っている", {t0["cid"]: good_comment(t0) + "セックス"}, "使えない言葉")
rejected("伏せ字（●）が入っている", {t0["cid"]: good_comment(t0) + "チ●"}, "使えない言葉")
rejected("出演者名が2回入っている", {t0["cid"]: good_comment(t0) + t0["actress"][0]}, "2回以上")
rejected("同じ文章を複数の作品に使い回している", {t0["cid"]: ok_text, t1["cid"]: ok_text}, "同じ文章")
rejected("保存データにない cid", {"no-such-cid": ok_text}, "ない cid")
rejected("Claude が仕上げたコメントは上書きしない", {finals[0]["cid"]: ok_text}, "上書きしません")
rejected("文字列でないコメント", {t0["cid"]: 12345}, "文字列")
rejected("良いコメントと悪いコメントが混ざっていたら、良いほうも書かない",
         {t0["cid"]: good_comment(t0), t1["cid"]: "短い"}, "文字数")

r = run("apply", write_comments("draft_ok.json", {drafts[0]["cid"]: good_comment(drafts[0], 5)}), "--dry-run")
check("Gemini の下書きは、仕上げた文で上書きできる", r.returncode == 0, r.stdout + r.stderr)
same = {drafts[0]["cid"]: drafts[0]["comment"]}
path = write_comments("same.json", same)
r = run("apply", path)
check("いまのコメント（下書き）と同じ文は断る（仕上げになっていない）", r.returncode == 1 and "いまのコメントと同じ" in r.stdout and read_text() == base, r.stdout)

print("\n■ タイトルを見せるかどうか（safe_title）・タイトルの写し（copied_from_title）")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import claude_comments as ccm  # noqa: E402
check("ふつうのタイトルは見せる", ccm.safe_title({"title": "会社の先輩とドライブデートに出かける一本"}) == "会社の先輩とドライブデートに出かける一本")
check("未成年を連想させるタイトルは見せない",
      all(ccm.safe_title({"title": t}) == "" for t in ("女子校生の放課後", "小生意気な妹2人", "J●と", "制服美少女", "")))
check("同意の無い場面・薬などのフィクションの設定は、タイトルを見せる（運営者の希望。2026-10-04）",
      all(ccm.safe_title({"title": t}) == t for t in ("痴漢電車", "媚薬で", "拘束されて", "優しく犯してあげる", "レ○プ")))
check("タイトルから10文字以上そのまま写したら見つける（出演者名・メーカー名の部分は除く）",
      ccm.copied_from_title("会社の先輩とドライブデートに出かける作品です", "会社の先輩とドライブデートに出かける一本") != ""
      and ccm.copied_from_title("先輩と出かけるドライブが舞台の作品です", "会社の先輩とドライブデートに出かける一本") == ""
      and ccm.copied_from_title("出演はとても長い名前の女優さんです", "とても長い名前の女優", ["とても長い名前の女優"]) == "")

print("\n■ apply の入力の形・特別な場合")
fresh_data()
r = run("apply", write_comments("today_bad.json", {t0["cid"]: good_comment(t0)}), "--today", "昨日")
check("--today の形が違えば断る（更新日に変な値を入れない）", r.returncode == 1 and read_text() == base, r.stdout + r.stderr)
r = run("apply", write_comments("today_ok.json", {t0["cid"]: good_comment(t0)}))
today_real = [x for x in read_data() if x["cid"] == t0["cid"]][0]["updated"]
check("--today を省略すると、日本時間の今日が更新日になる", r.returncode == 0 and re.match(r"^\d{4}-\d{2}-\d{2}$", today_real) and today_real >= "2026-10-03", today_real)
fresh_data()
path = write_comments("list_form.json", [{"cid": t0["cid"], "comment": good_comment(t0)}, {"cid": t1["cid"], "comment": good_comment(t1, 1)}])
r = run("apply", path)
check("[{cid, comment}] のリスト形式でも書き込める", r.returncode == 0 and sum(x["comment_kind"] == "claude" for x in read_data()) == len(finals) + 2, r.stdout + r.stderr)

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

print("\n■ 発売日をすぎたのに「予約」の言い方が残っているコメント（書き直しの対象）")
fresh_data()
stale_data = read_data()
ai_item = next(x for x in stale_data if x["comment_kind"] == "claude")
plain_ai = next(x for x in stale_data if x["comment_kind"] == "claude" and x["cid"] != ai_item["cid"])
ai_item["comment"] = "予約受付中のVR作品です。" + good_comment(ai_item, 3)  # 出演者名入り・文字数も足りる（情報が増えた、では対象にならない形）
ai_item["date"] = "2026-11-01 00:00:00"
open(DATA, "w", encoding="utf-8").write(json.dumps(stale_data, ensure_ascii=False, indent=1) + "\n")
stale_base = read_text()
out_before = json.loads(run("list", "--limit", "100", "--today", "2026-10-30").stdout)
check("まだ発売前の作品に「予約受付中」とあっても、対象にならない", ai_item["cid"] not in {x["cid"] for x in out_before["items"]}, out_before["total_pending"])
out_after = json.loads(run("list", "--limit", "100", "--today", "2026-11-02").stdout)
row = next((x for x in out_after["items"] if x["cid"] == ai_item["cid"]), None)
check("発売日をすぎたのに「予約受付中」が残っている仕上げ済みのコメントは、list の対象になる（reason つき・draft つき）", row is not None and row["reason"] == "予約の言い方が残っている" and row["status"] == "発売済み" and row.get("draft") == ai_item["comment"], row)
check("ほかの対象は、定型文と下書きのまま", all(x["reason"] in ("定型文", "下書きを仕上げる") for x in out_after["items"] if x["cid"] != ai_item["cid"]) and out_after["total_pending"] == len(pending) + 1, out_after["total_pending"])
check("ふつうの仕上げ済みのコメントは、対象にならない", plain_ai["cid"] not in {x["cid"] for x in out_after["items"]})
r = run("apply", write_comments("stale_ok.json", {ai_item["cid"]: good_comment(ai_item, 2)}), "--today", "2026-11-02")
now_item = next(x for x in read_data() if x["cid"] == ai_item["cid"])
check("書き直せる（コメントが入れ替わり、更新日が今日になる）", r.returncode == 0 and now_item["comment"] == good_comment(ai_item, 2) and now_item["updated"] == "2026-11-02", r.stdout + r.stderr)
check("書き直したあとは、対象から外れる", ai_item["cid"] not in {x["cid"] for x in json.loads(run("list", "--limit", "100", "--today", "2026-11-02").stdout)["items"]})
open(DATA, "w", encoding="utf-8").write(stale_base)
r = run("apply", write_comments("plain_ai.json", {plain_ai["cid"]: good_comment(plain_ai, 2)}), "--today", "2026-11-02")
check("ふつうの仕上げ済みのコメント（予約の言い方なし）は、上書きできない", r.returncode == 1 and "上書きしません" in r.stdout and read_text() == stale_base, r.stdout)
r = run("apply", write_comments("stale_early.json", {ai_item["cid"]: good_comment(ai_item, 2)}), "--today", "2026-10-30")
check("まだ発売前なら、「予約受付中」の仕上げ済みのコメントも書き直さない", r.returncode == 1 and "上書きしません" in r.stdout and read_text() == stale_base, r.stdout)

print("\n■ 同じ言い回しが多すぎるときの警告")
fresh_data()
many = {x["cid"]: good_comment(x, i).replace("の棚に", "の棚に。気になる方はチェックを。", 1) for i, x in enumerate(templates[:7])}
r = run("apply", write_comments("many.json", many), "--dry-run")
check("「チェック」が多すぎると、警告を出す（書き込みは止めない）", r.returncode == 0 and "「チェック」を使ったコメント" in r.stdout and "「気になる方は」を使ったコメント" in r.stdout, r.stdout + r.stderr)
varied = {x["cid"]: good_comment(x, i) for i, x in enumerate(templates[:7])}
r = run("apply", write_comments("varied.json", varied), "--dry-run")
check("言い回しがばらけていれば、警告は出ない", r.returncode == 0 and "を使ったコメント" not in r.stdout, r.stdout + r.stderr)

print("\n■ 同じ型の結びが多すぎるときは断る（試運転で、40本ほぼすべてが「サンプル動画と…で雰囲気を確かめられます」だったため）")
fresh_data()
seven = templates[:7]
same_end = {x["cid"]: good_comment(x, i) + "サンプル画像で雰囲気を確かめられます。" for i, x in enumerate(seven)}
r = run("apply", write_comments("same_end.json", same_end), "--dry-run")
check("7本中7本が「サンプル」で終わると断る（何も書き込まない）", r.returncode == 1 and "「サンプル」を使ったコメントが 7/7 件" in r.stdout and read_data() == original, r.stdout + r.stderr)
few_end = {x["cid"]: good_comment(x, i) + ("サンプル画像は12枚です。" if i < 2 else "") for i, x in enumerate(seven)}
r = run("apply", write_comments("few_end.json", few_end), "--dry-run")
check("3本に1本まで（7本中2本）なら通る", r.returncode == 0, r.stdout + r.stderr)
small = {x["cid"]: good_comment(x, i) + "サンプル画像は12枚です。" for i, x in enumerate(templates[:3])}
r = run("apply", write_comments("small.json", small), "--dry-run")
check("5本以下のときは数えない（毎日の少ない本数で、書けなくならないように）", r.returncode == 0, r.stdout + r.stderr)

print("\n■ 同じことの言い直し（水増し）を断る・決まり文句を使いすぎない（2回目の試運転で見つかったもの）")
fresh_data()
one = templates[0]
padded = good_comment(one, 0) + "長めの作品を探す方に向いています。長めの作品を探す方にも向いています。"
r = run("apply", write_comments("padded.json", {one["cid"]: padded}), "--dry-run")
check("1つのコメントに、ほぼ同じ文が2回あると断る", r.returncode == 1 and "同じ内容の文が2回" in r.stdout, r.stdout)
check("repeated_sentence: 言い直しの部分を返す・ちがう文なら空", cc_mod.repeated_sentence("短時間なので、気軽に内容を確かめたい方に。短時間なので、気軽に確かめられます。").startswith("短時間なので、気軽に")
      and cc_mod.repeated_sentence("職場の先輩とのドライブから始まる一本です。〇〇さんが出演する作品で、収録は約246分です。") == "")
names = {x["cid"]: good_comment(x, i) + "メーカーの名前からも、別の作品を探せます。" for i, x in enumerate(templates[:7])}
r = run("apply", write_comments("names.json", names), "--dry-run")
check("「名前から」のような決まり文句が3本に1本より多いと断る", r.returncode == 1 and "「名前から」を使ったコメント" in r.stdout, r.stdout)

print("\n■ --rewrite（仕上げ済みのコメントを直すときだけ）")
fresh_data()
final = finals[0]
fixed = good_comment(final, 1)
r = run("apply", write_comments("fix.json", {final["cid"]: fixed}), "--today", "2026-11-02")
check("ふだんは、仕上げ済みのコメントを上書きしない", r.returncode == 1 and "上書きしません" in r.stdout, r.stdout)
r = run("apply", write_comments("fix.json", {final["cid"]: fixed}), "--today", "2026-11-02", "--rewrite")
after = {x["cid"]: x for x in read_data()}
check("--rewrite なら書き直せる（点検は同じ・更新日も進む）", r.returncode == 0 and after[final["cid"]]["comment"] == fixed and after[final["cid"]]["updated"] == "2026-11-02", r.stdout + r.stderr)
r = run("apply", write_comments("fix_bad.json", {final["cid"]: "短い文です。"}), "--rewrite", "--dry-run")
check("--rewrite でも、点検に通らない文は書き込まない", r.returncode == 1 and "文字数" in r.stdout, r.stdout)

print("\n■ 1日に仕上げるのは40件まで（試運転で、1回の予約タスクが40件を2回続けて書いたため）")
fresh_data()
first = {x["cid"]: good_comment(x, i) for i, x in enumerate(pending[:4])}
r = run("apply", write_comments("day1.json", first), "--today", "2026-11-05")
check("同じ日の1回目は書ける", r.returncode == 0, r.stdout + r.stderr)
saved_limit = cc_mod.DAILY_LIMIT
env_limit = dict(os.environ, DATA_PATH=DATA)
rest = {x["cid"]: good_comment(x, i + 4) for i, x in enumerate(pending[4:7])}
code = ("import sys, runpy; sys.argv = ['claude_comments.py', 'apply', sys.argv[1], '--today', '2026-11-05', '--dry-run']; "
        "import claude_comments as m; m.DAILY_LIMIT = 6; m.main()")
r = subprocess.run([sys.executable, "-c", code, write_comments("day1b.json", rest)], capture_output=True, text=True, env=dict(env_limit, PYTHONPATH=os.path.join(ROOT, "scripts")), encoding="utf-8")
check("上限をこえる分は断る（上限6・今日4件済み・今回3件 → 断る。残りの数を出す）", r.returncode == 1 and "1日に仕上げるのは 6 件まで" in r.stdout and "今回は 2 件まで" in r.stdout, r.stdout + r.stderr)
r = subprocess.run([sys.executable, "-c", code.replace("'--today', '2026-11-05'", "'--today', '2026-11-06'"), write_comments("day2.json", rest)], capture_output=True, text=True, env=dict(env_limit, PYTHONPATH=os.path.join(ROOT, "scripts")), encoding="utf-8")
check("次の日なら、また書ける", r.returncode == 0, r.stdout + r.stderr)
check("--rewrite・--no-daily-limit は数えない（仕上げ済みを直すとき・運営者に頼まれて会話の中で書くとき）", "if not args.rewrite and not args.no_daily_limit:" in open(SCRIPT, encoding="utf-8").read())

print("\n■ 全作品の点検（2026-10-04 夕方）: 伏せ字・「×」の見分け、同意の無い場面の言葉、事実が少ない作品の文字数")
st = lambda t: cc_mod.safe_title({"title": t})
check("行為・体の言葉の伏せ字（中●し・チ○ポ・マ●コ）だけなら、タイトルを見せる", all(st(t) == t for t in ("お姉さん10人！思わず中●ししちゃいました", "撮影会に潜入！チ○ポ中毒", "作業員が性処理エコマ●コに再利用")))
check("「A×B」の区切りの×は伏せ字として数えない", st("金玉からっぽにしてあげる 逢沢みゆ×幸村泉希") != "" and st("JOI×射精管理×ご褒美") != "")
check("未成年を伏せた形（J× J〇 女子○生 ●学生）は見せない",
      all(st(t) == "" for t in ("巨乳ギャルJ×。留年回避と", "ウブJ〇", "アヘ顔女子○生下品", "パイパン●学生いおり")))
check("同意の無い行為を伏せた形（レ●プ 痴● 強●）は見せて、fiction_theme にする",
      all(st(t) == t and cc_mod.title_block_reason({"title": t}) == "theme" for t in ("1週間レ●プ！", "潜入！【痴●団地】", "強●クスリ漬け")))
check("全角の英字（ＪＫ）も見分ける・タイトルもコメントも", st("ＪＫと放課後") == "" and st("ｊｋ") == "")
check("嫌がらせ・制裁・寝取りなどは見せる（fiction_theme）。家出少女・筆おろしは未成年を連想させるので見せない",
      all(st(t) == t and cc_mod.title_block_reason({"title": t}) == "theme" for t in ("【授乳手コキセクハラ】残業中のオフィス", "電車生姦制裁 ＃014", "人妻寝取られ"))
      and all(st(t) == "" for t in ("家出少女を", "母の筆おろし")) and st("家出した人妻") != "")
check("大人どうしの言葉の一部（幼なじみ・姉妹・母娘・男の娘・女の子・処女）では、未成年あつかいしない",
      all(cc_mod.title_block_reason({"title": t}) != "minor" for t in ("隣の幼なじみが", "隣の巨乳姉妹に", "いいなり母娘", "むっつりスケベな女の子", "処女11人を", "2穴肛門娘"))
      and cc_mod.title_block_reason({"title": "男の娘J系ギャル"}) == "minor")
fresh_data()
one = templates[0]
r = run("apply", write_comments("fw.json", {one["cid"]: "ＪＫ風の衣装で登場する一本です。" + good_comment(one, 0)}), "--dry-run")
check("コメントの全角の英字（ＪＫ）も断る", r.returncode == 1 and "JK" in r.stdout, r.stdout)
rich = dict(one, title="職場の先輩とのドライブデート", duration_min=120, genres=["OL"])
sparse = dict(one, title="職場の先輩とのドライブデート", duration_min=None, genres=[])
hidden = dict(one, title="制服の美少女", duration_min=120, genres=[])
check("事実が少ない作品（予約で収録時間もジャンルも無い・タイトルを見せずジャンルも無い）は80文字から、ほかは100文字から",
      cc_mod.min_length_for(rich) == 100 and cc_mod.min_length_for(sparse) == 80 and cc_mod.min_length_for(hidden) == 80)
r = run("list", "--today", "2026-11-03", "--limit", "100")
check("list に、作品ごとの文字数の下限（min_len）が出る", all(x.get("min_len") in (80, 100) for x in json.loads(r.stdout)["items"]))
code = ("import sys; sys.argv = ['claude_comments.py', 'apply', sys.argv[1], '--today', '2026-11-05', '--dry-run'] + sys.argv[2:]; "
        "import claude_comments as m; m.DAILY_LIMIT = 2; m.main()")
many3 = {x["cid"]: good_comment(x, i) for i, x in enumerate(pending[:3])}
envp = dict(os.environ, DATA_PATH=DATA, PYTHONPATH=os.path.join(ROOT, "scripts"))
r1 = subprocess.run([sys.executable, "-c", code, write_comments("lim.json", many3)], capture_output=True, text=True, env=envp, encoding="utf-8")
r2 = subprocess.run([sys.executable, "-c", code, write_comments("lim.json", many3), "--no-daily-limit"], capture_output=True, text=True, env=envp, encoding="utf-8")
check("--no-daily-limit なら、1日の上限を数えない（ふだんは断る）", r1.returncode == 1 and "1日に仕上げるのは" in r1.stdout and r2.returncode == 0, r1.stdout + r2.stdout + r2.stderr)

print("\n■ 未成年を連想させるタイトルの作品は、場面のジャンルにも触れない（content_off）")
fresh_data()
minor_item = dict(templates[0], title="制服の美少女と", genres=["ハイビジョン", "OL", "コスプレ"], duration_min=120)
check("title_block_reason: 未成年は minor・同意の無い場面の設定は theme・ふつうは空",
      cc_mod.title_block_reason(minor_item) == "minor" and cc_mod.title_block_reason(dict(minor_item, title="痴漢電車")) == "theme"
      and cc_mod.title_block_reason(dict(minor_item, title="職場の先輩とのドライブ")) == "")
check("未成年を連想させる作品には、形式のジャンルだけを渡し、文字数の下限は80", cc_mod.genres_for_comment(minor_item, {"ハイビジョン", "OL", "コスプレ"}) == ["ハイビジョン"] and cc_mod.min_length_for(minor_item) == 80)
check("その作品のコメントに場面のジャンル（コスプレ）が入っていれば断る", any("場面・関係のジャンル" in p for p in cc_mod.comment_problems("コスプレのジャンルに入る一本です。" + good_comment(minor_item, 0), dict(minor_item, comment="")))
      and cc_mod.comment_genres(minor_item) != [])
r = run("list", "--today", "2026-11-03", "--limit", "100")
outl = json.loads(r.stdout)["items"]
check("list: content_off の作品は、タイトルを出さず（title_hidden）、形式以外のジャンルも出さない",
      all(x.get("title_hidden") and set(x["genres"]) <= set(cc_mod.FORMAT_GENRES) for x in outl if x.get("content_off")))

print("\n■ フィクションの設定を表す言葉は、コメントに書ける（行為・体・暴行の言葉は書けない）")
fresh_data()
one = templates[0]
r = run("apply", write_comments("theme_ok.json", {one["cid"]: "職場のセクハラを題材にした、催眠ものの設定のドラマです。" + good_comment(one, 0)}), "--dry-run")
check("「セクハラ」「催眠」などの設定の言葉は書ける", r.returncode == 0, r.stdout + r.stderr)
for word in ("レイプ", "拉致", "便器", "中出し"):
    r = run("apply", write_comments("theme_ng.json", {one["cid"]: f"{word}を描く一本です。" + good_comment(one, 0)}), "--dry-run")
    check(f"「{word}」は書けない", r.returncode == 1 and "使えない言葉" in r.stdout, r.stdout)
r = run("list", "--today", "2026-11-03", "--limit", "100")
check("list: fiction_theme はタイトルを見せる作品にだけ付く", all(x.get("title") for x in json.loads(r.stdout)["items"] if x.get("fiction_theme")))

print("\n■ 仕上げたあとに情報が増えた作品・これから先の言い方（発売後に書き直す）")
fresh_data()
data_i = read_data()
fin = next(x for x in data_i if x["comment_kind"] == "claude" and x.get("actress"))
fin["comment"] = good_comment(fin, 0)
check("ふつうの仕上げ済み（出演者名あり・文字数も足りる）は、情報が増えた扱いにならない", cc_mod.info_added(fin) == "")
no_name = dict(fin, comment="出演者名はFANZAの作品情報に載っていません。" + good_comment(dict(fin, actress=["ほかの人"]), 0))
check("出演者が載ったのに、コメントに名前が1人も無いと「出演者が載った」", cc_mod.info_added(no_name) == "出演者が載った")
short = dict(fin, comment=good_comment(fin, 0)[:90], title="職場の先輩とのドライブ", duration_min=120)
check("事実が増えて100文字が必要になったのに、短いまま（80文字台）だと「情報が増えた」", cc_mod.info_added(short) == "情報が増えた")
check("発売後に書き直す言い方: 「発売されます」「出ます」「控えています」",
      all(cc_mod.STALE_STATUS.search(t) for t in ("11月1日に発売されます。", "同じ日には新作も出ます。", "出演も控えています。")) and not cc_mod.STALE_STATUS.search("11月1日発売の一本です。"))
fut = dict(fin, comment=good_comment(fin, 0) + "11月1日に発売されます。", date="2026-11-01 00:00:00")
check("予約のうちは「発売されます」のままでよく、発売日をすぎたら書き直しの対象", cc_mod.stale_status_word(fut, "2026-10-30") == "" and cc_mod.stale_status_word(fut, "2026-11-02") == "発売されます")
for x in data_i:
    if x["cid"] == fin["cid"]:
        x["comment"] = no_name["comment"]
open(DATA, "w", encoding="utf-8").write(json.dumps(data_i, ensure_ascii=False, indent=1) + "\n")
out_i = json.loads(run("list", "--limit", "100", "--today", "2026-11-03").stdout)
row_i = next((x for x in out_i["items"] if x["cid"] == fin["cid"]), None)
check("list に「出演者が載った」で出て、仕上げ済みでも書き直せる", row_i is not None and row_i["reason"] == "出演者が載った"
      and run("apply", write_comments("refill.json", {fin["cid"]: good_comment(fin, 1)}), "--today", "2026-11-03", "--dry-run").returncode == 0)

print("\n■ 学校・子どもの生活を連想させる場面の言葉（試運転で「職業体験」「学園」「家庭教師」に触れたコメントがあったため）")
fresh_data()
for word in ("学園", "職業体験", "家庭教師", "放課後", "部活", "女の子"):
    one = templates[0]
    r = run("apply", write_comments("minor_ctx.json", {one["cid"]: f"{word}を舞台にした一本です。" + good_comment(one, 0)}), "--dry-run")
    check(f"コメントに「{word}」があると断る", r.returncode == 1 and word in r.stdout, r.stdout)
check("タイトルに「職業体験」「学園」「家庭教師」があると、Claude にも見せない（内容に触れない）",
      all(cc_mod.safe_title({"title": t}) == "" for t in ("職業体験で出会った介護士と", "学園のハーレム生活", "家庭教師の先生と二人きり"))
      and cc_mod.safe_title({"title": "職場の先輩とのドライブ"}) != "")

print("\n■ 保存データが壊れているとき")
open(DATA, "w", encoding="utf-8").write("{壊れている")
check("list は止まる", run("list").returncode != 0)
check("apply も止まる（データを上書きしない）", run("apply", write_comments("g.json", {"x": ok_text})).returncode != 0
      and read_text() == "{壊れている")
open(DATA, "w", encoding="utf-8").write('{"cid": "a"}')
check("リストでないデータも止まる", run("list").returncode != 0)

print("\n■ 過去作品（data/catalog/YYYY-MM.json）のコメント")
import importlib.util as _ilu
CAT_DIR = os.path.join(tmp, "catalog")  # DATA と同じフォルダの catalog（claude_comments.py の CATALOG_DIR の既定）
os.environ["API_ID"] = "x"
_spec = _ilu.spec_from_file_location("grn_for_catalog", os.path.join(ROOT, "get_new_releases.py"))
grn = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(grn)
grn.CATALOG_DIR = CAT_DIR
grn.CATALOG_STATE_PATH = os.path.join(tmp, "catalog_state.json")
grn.CATALOG_RANK_PATH = os.path.join(tmp, "catalog_rank.json")
fresh_data()
base_items = read_data()
cat_state = {"items": {}, "ranks": {}, "cursor": 0, "cycle": 1, "cycle_done": ""}
for i, x in enumerate(base_items[:6]):
    y = dict(x, cid=f"oldwork{i:03d}", date=f"20{19 + i % 3}-0{1 + i}-15 10:00:00", comment_kind="none", comment="", updated="2026-10-04",
             url=f"https://al.fanza.co.jp/?lurl=x{i}&af_id=x-990")
    cat_state["items"][y["cid"]] = grn.catalog_item(y)
    cat_state["ranks"][y["cid"]] = [[500, 30, 7000, 2, 9000, None][i], 1] if i != 5 else None
dup = grn.catalog_item(dict(base_items[0], comment_kind="none", comment=""))  # 毎日の更新の作品と同じ作品（サイトは毎日の更新のほうを使う）
cat_state["items"][dup["cid"]] = dup
cat_state["ranks"] = {c: r for c, r in cat_state["ranks"].items() if r}  # oldwork005 は順位が分からない作品
grn.save_catalog(cat_state)  # 毎日の更新と同じ書き方で作る
shard_before = {n: open(os.path.join(CAT_DIR, n), encoding="utf-8").read() for n in os.listdir(CAT_DIR)}
lst = json.loads(run("list", "--limit", "40").stdout)
cat_rows = [r for r in lst["items"] if r.get("catalog")]
cur_rows = [r for r in lst["items"] if not r.get("catalog")]
check("list: 毎日の更新の作品を先に、枠が余ったら過去作品（コメントがまだ無いもの）を出す", len(cur_rows) == len(pending) and len(cat_rows) == 6 and lst["items"].index(cat_rows[0]) == len(cur_rows), (len(cur_rows), len(cat_rows)))
check("list: 過去作品は reason「過去作品」・catalog: true・発売済み・FANZAの人気順の順位が上の作品から（順位が分からない作品は最後）・順位そのものは出さない",
      all(r["reason"] == "過去作品" and r["status"] == "発売済み" and "rank" not in r for r in cat_rows) and [r["cid"] for r in cat_rows] == ["oldwork003", "oldwork001", "oldwork000", "oldwork002", "oldwork004", "oldwork005"], [r["cid"] for r in cat_rows])
with open(os.path.join(tmp, "popularity.json"), "w", encoding="utf-8") as f:
    json.dump({"date": "2026-11-03", "new": {"oldwork004": 1, "oldwork005": 40}, "all": {}}, f)
cat_rows_pop = [r["cid"] for r in json.loads(run("list", "--limit", "40").stdout)["items"] if r.get("catalog")]
os.remove(os.path.join(tmp, "popularity.json"))
check("list: 新着の人気順に入っている過去作品は、その順位も使う（全体の順位と、上のほう）", cat_rows_pop[:4] == ["oldwork004", "oldwork003", "oldwork001", "oldwork005"], cat_rows_pop)
check("list: 毎日の更新の作品と同じ作品は、過去作品として出さない", dup["cid"] not in {r["cid"] for r in cat_rows})
check("list: total_pending に過去作品も入る・catalog_pending は過去作品の数", lst["total_pending"] == len(pending) + 6 and lst["catalog_pending"] == 6, (lst["total_pending"], lst["catalog_pending"]))
lst_small = json.loads(run("list", "--limit", str(len(pending) - 1)).stdout)
check("list: 枠が毎日の更新の作品で埋まるときは、過去作品を出さない", not any(r.get("catalog") for r in lst_small["items"]))
pick_cat = [r["cid"] for r in cat_rows[:2]]
by_all = {x["cid"]: x for x in base_items} | {c: it for c, it in cat_state["items"].items()}
payload = {c: good_comment(by_all[c], 30 + i) for i, c in enumerate(pick_cat + [templates[0]["cid"]])}
r = run("apply", write_comments("cat.json", payload), "--today", "2026-11-03")
check("apply: 過去作品と毎日の更新の作品を、いっしょに書き込める", r.returncode == 0 and "うち過去作品 2件" in r.stdout and "コメントがまだ無い過去作品: 4本" in r.stdout, r.stdout + r.stderr)
cat_now = {}
for n in os.listdir(CAT_DIR):
    for row in json.load(open(os.path.join(CAT_DIR, n), encoding="utf-8")):
        cat_now[row["cid"]] = (n, row)
check("apply: 過去作品のファイルに、comment_kind claude・更新日・コメントが入る", all(cat_now[c][1]["comment_kind"] == "claude" and cat_now[c][1]["updated"] == "2026-11-03" and cat_now[c][1]["comment"] == payload[c] for c in pick_cat))
check("apply: 毎日の更新の作品は new_releases.json に入る（過去作品のファイルには入れない）", next(x for x in read_data() if x["cid"] == templates[0]["cid"])["comment_kind"] == "claude" and cat_now[dup["cid"]][1]["comment_kind"] == "none")
touched = {cat_now[c][0] for c in pick_cat}
same_lines = all(
    [l for l in open(os.path.join(CAT_DIR, n), encoding="utf-8").read().split("\n") if not any(f'"cid":"{c}"' in l for c in pick_cat)]
    == [l for l in shard_before[n].split("\n") if not any(f'"cid":"{c}"' in l for c in pick_cat)] for n in shard_before)
check("apply: 書き方は毎日の更新と同じ（1作品1行）。書いた作品の行のほかは1文字も変わらない・書いていない月のファイルはそのまま", same_lines and all(open(os.path.join(CAT_DIR, n), encoding="utf-8").read() == shard_before[n] for n in shard_before if n not in touched))
check("apply のあと、毎日の更新が読み直しても同じ（過去作品の Claude のコメントは残る）", all(grn.load_catalog("2026-11-03")["items"][c]["comment_kind"] == "claude" for c in pick_cat))
r = run("apply", write_comments("cat2.json", {pick_cat[0]: good_comment(by_all[pick_cat[0]], 41)}), "--today", "2026-11-03")
check("apply: Claude が書いた過去作品のコメントは上書きしない（--rewrite のときだけ）", r.returncode == 1 and "上書きしません" in r.stdout, r.stdout)
others = [c for c in cat_state["items"] if c not in pick_cat and c != dup["cid"]]
many_cur = [x for x in read_data() if x["comment_kind"] != "claude"]
r = run("apply", write_comments("cat3.json", {c: good_comment(by_all[c], 50 + i) for i, c in enumerate(others[:2])}), "--today", "2026-11-03", "--dry-run")
check("apply: 過去作品も、点検は同じ（--dry-run で通る）", r.returncode == 0, r.stdout + r.stderr)
r = run("apply", write_comments("cat4.json", {"nosuchwork": good_comment(base_items[0], 60)}))
check("apply: どこにもない cid は断る", r.returncode == 1 and "にない cid" in r.stdout, r.stdout)
open(os.path.join(CAT_DIR, sorted(os.listdir(CAT_DIR))[0]), "w", encoding="utf-8").write("[{broken")
r = run("list")
check("過去作品のファイルが壊れていたら、止める（書き戻して壊さないように）", r.returncode != 0 and "過去作品のファイル" in (r.stdout + r.stderr), r.stdout + r.stderr)
shutil.rmtree(CAT_DIR)
os.remove(os.path.join(tmp, "catalog_state.json"))

print("\n■ 全件を書き換えた後")
fresh_data()
everything = {x["cid"]: good_comment(x, i) for i, x in enumerate(pending)}
r = run("apply", write_comments("all.json", everything))
check("定型文と下書きを全部まとめて書き換えられる", r.returncode == 0 and "残り0件" in r.stdout, r.stdout + r.stderr)
check("そのあと list は空になる", json.loads(run("list").stdout)["items"] == [])
check("全件が comment_kind claude になる", all(x["comment_kind"] == "claude" for x in read_data()))

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
