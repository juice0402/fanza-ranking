"""scripts/claude_roundups.py（Claude が週のまとめ記事を書くための道具）のテスト

本番データではなく、このテストの中で作った固定のデータ（2026-09-28〜10-04 の週に24本）で試します。
実行: python3 tests/test_claude_roundups.py   （どこから実行してもOK）
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "claude_roundups.py")

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ✅ " if cond else "  ❌ ") + name + (f"  → {detail}" if (detail and not cond) else ""))


tmp = tempfile.mkdtemp(prefix="claude_roundups_test_")
DATA = os.path.join(tmp, "items.json")
ROUNDUPS = os.path.join(tmp, "roundups.json")


def make_items():
    """2026-09-28(月)〜10-04(日) に24本。前の週に3本、次の週に4本。"""
    makers = ["メーカーA", "メーカーA", "メーカーA", "メーカーB", "メーカーB", "メーカーC", "メーカー2号", "メーカーD", "メーカーE", "メーカーF"]
    # 6人以上が2本以上に出る（上位5人までの切り捨てを試す）・1本だけの人もいる・出演者なしもいる・名前に数字が入る人もいる
    actresses = ["花子", "葵", "彩", "月", "桜", "星", "", "花子", "NO.99みゆ", "葵", "彩", "月", "単発"]
    rows = []

    def add(cid, date, n):
        a = actresses[n % len(actresses)]
        rows.append({
            "cid": cid, "title": f"【VR】秘密のタイトル{cid}", "url": "https://example.com/" + cid, "image_url": "", "sample_images": [],
            "date": f"{date} 00:00:00", "maker": makers[n % len(makers)] if n % 9 != 8 else "不明",
            "actress": [a] if a else [], "genres": ["内容を表すジャンル"],
            "tags": ["VR"] if n % 3 == 0 else (["8K", "痴漢もの"] if n % 3 == 1 else []),
            "duration_min": 120 if n % 4 == 0 else (None if n % 4 == 1 else 87),
            "comment": f"コメント{cid}", "comment_kind": "ai", "comment_tries": 0, "updated": "2026-10-01",
        })

    days = ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
    n = 0
    for i in range(24):
        add(f"wk{i:02d}", days[(0, 0, 0, 1, 1, 2, 3, 3, 3, 3, 4, 4, 4, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6)[i]], n)
        n += 1
    for i in range(3):
        add(f"pre{i}", "2026-09-22", n); n += 1
    for i in range(4):
        add(f"nxt{i}", "2026-10-06", n); n += 1
    return rows


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def fresh():
    write_json(DATA, make_items())
    if os.path.exists(ROUNDUPS):
        os.remove(ROUNDUPS)


def run(*args):
    env = dict(os.environ, DATA_PATH=DATA, ROUNDUPS_PATH=ROUNDUPS)
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=env, encoding="utf-8")


def listing(*args):
    r = run("list", *args)
    return json.loads(r.stdout) if r.returncode == 0 else None


def roundups_text():
    return open(ROUNDUPS, encoding="utf-8").read() if os.path.exists(ROUNDUPS) else None


def article_file(name, article):
    path = os.path.join(tmp, name)
    write_json(path, article)
    return path


fresh()
items = make_items()
week = [x for x in items if "2026-09-28" <= x["date"][:10] <= "2026-10-04"]

print("■ list（書く対象の週を出す）")
out = listing("--today", "2026-10-05")
check("今日が月曜なら、昨日終わった週（9/28〜10/4）が対象", out and out["week_start"] == "2026-09-28" and out["week_end"] == "2026-10-04" and out["status"] == "ready", out and out.get("status"))
check("水曜でも同じ週が対象（月曜の実行が1日ずれても大丈夫）", listing("--today", "2026-10-07")["week_start"] == "2026-09-28")
check("日曜の今日は、その週はまだ終わっていないので、前の週が対象", listing("--today", "2026-10-04")["week_start"] == "2026-09-21")
check("その週の作品だけが入る（前の週・次の週は入らない）", sorted(x["cid"] for x in out["items"]) == sorted(x["cid"] for x in week) and out["total"] == 24)
check("作品タイトルやジャンルを出さない（出演者・メーカー・形式・発売日・収録時間だけ）",
      "秘密のタイトル" not in json.dumps(out, ensure_ascii=False) and "内容を表すジャンル" not in json.dumps(out, ensure_ascii=False)
      and all(set(x) == {"cid", "date", "actress", "maker", "formats", "duration_min"} for x in out["items"]))
check("形式は英数字のタグだけ（日本語のタグは出さない）", all(f in ("VR", "8K") for x in out["items"] for f in x["formats"]) and "痴漢" not in json.dumps(out, ensure_ascii=False))
check("メーカー「不明」は null", any(x["maker"] is None for x in out["items"]) and all(x["maker"] != "不明" for x in out["items"]))
check("収録時間は正の整数か null", all(x["duration_min"] is None or (isinstance(x["duration_min"], int) and x["duration_min"] > 0) for x in out["items"]))
# 集計を、テストの中で別の方法でも数えて突き合わせる
mk = {}
for x in week:
    if x["maker"] != "不明":
        mk[x["maker"]] = mk.get(x["maker"], 0) + 1
expect_makers = [{"name": n, "count": c} for n, c in sorted(mk.items(), key=lambda p: (-p[1], p[0]))][:5]
check("メーカー別の本数（多い順・同数は名前順・5つまで。6つ以上あるデータで切り捨てを確認）", out["makers"] == expect_makers and len(mk) > 5 and len(expect_makers) == 5, out["makers"])
ac = {}
for x in week:
    for a in x["actress"]:
        ac[a] = ac.get(a, 0) + 1
expect_actresses = [{"name": n, "count": c} for n, c in sorted(ac.items(), key=lambda p: (-p[1], p[0])) if c >= 2][:5]
check("出演者別の本数（2本以上の人だけ・5人まで。6人以上・1本だけの人もいるデータで確認）",
      out["actresses"] == expect_actresses and all(a["count"] >= 2 for a in out["actresses"]) and len(expect_actresses) == 5
      and len([a for a in ac if ac[a] >= 2]) > 5 and any(c == 1 for c in ac.values()), out["actresses"])
fm = {}
for x in week:
    for f in dict.fromkeys(t for t in x["tags"] if t in ("VR", "8K")):
        fm[f] = fm.get(f, 0) + 1
check("形式別の本数", out["formats"] == [{"name": n, "count": c} for n, c in sorted(fm.items(), key=lambda p: (-p[1], p[0]))], out["formats"])
dd = {}
for x in week:
    dd[x["date"][:10]] = dd.get(x["date"][:10], 0) + 1
check("発売日別の本数（日付順）", out["per_day"] == [{"date": d, "count": c} for d, c in sorted(dd.items())] and sum(p["count"] for p in out["per_day"]) == 24, out["per_day"])
check("終わっていない週を指定すると何もしない（not_finished）", listing("--today", "2026-10-07", "--week-start", "2026-10-05")["status"] == "not_finished")
check("週の最後の日（日曜）の今日は、まだ終わっていない。翌日の月曜からは書ける",
      listing("--today", "2026-10-04", "--week-start", "2026-09-28")["status"] == "not_finished" and listing("--today", "2026-10-05", "--week-start", "2026-09-28")["status"] == "ready")
check("作品が少ない週は作らない（too_few_items）", listing("--today", "2026-10-07", "--week-start", "2026-09-21")["status"] == "too_few_items")
r = run("list", "--today", "2026-10-07", "--week-start", "2026-09-29")
check("月曜でない日付を --week-start に指定したら断る", r.returncode != 0 and "月曜日" in r.stdout + r.stderr)

print("\n■ apply（点検して書き込む）")


def good_article(**override):
    a = {
        "week_start": "2026-09-28",
        "lead": "9月28日から10月4日までの1週間に、24本の作品が発売されました。メーカーAの作品が最も多く、花子さんが3本に出演しています。10月3日と10月4日に発売が集中した週で、VRや8Kの作品も含まれています。",
        "picks": [
            {"cid": "wk00", "note": "メーカーAの作品で、花子さんが出演。VR形式で、9月28日に発売されました。収録時間は120分です。"},
            {"cid": "wk04", "note": "9月29日に発売された、桜さん出演の作品です。メーカーBの一本で、8K形式、収録時間は120分となっています。"},
            {"cid": "wk06", "note": "10月1日発売のメーカー2号の作品です。VR形式で、収録時間は87分。出演者の記載はありません。"},
        ],
    }
    a.update(override)
    return a


path = article_file("good.json", good_article())
r = run("apply", path, "--dry-run", "--today", "2026-10-05")
check("--dry-run は成功して、ファイルを作らない", r.returncode == 0 and roundups_text() is None, r.stdout + r.stderr)
r = run("apply", path, "--today", "2026-10-05")
check("正しい記事は書き込める", r.returncode == 0, r.stdout + r.stderr)
saved = json.loads(roundups_text())
check("保存の形: week_start・lead・picks・written（公開日=--today）", len(saved) == 1 and set(saved[0]) == {"week_start", "lead", "picks", "written"}
      and saved[0]["written"] == "2026-10-05" and saved[0]["picks"][0] == {"cid": "wk00", "note": good_article()["picks"][0]["note"]}, saved)
check("書き方が決まった形（インデント1・日本語そのまま・末尾に改行）", roundups_text() == json.dumps(saved, ensure_ascii=False, indent=1) + "\n")
check("作業用の .tmp ファイルが残らない", not os.path.exists(ROUNDUPS + ".tmp"))
check("書いたあとの list は「もう書いてある」", listing("--today", "2026-10-05")["status"] == "already_written")
before = roundups_text()
r = run("apply", path, "--today", "2026-10-06")
check("同じ週をもう一度書こうとしたら断る（上書きしない）", r.returncode == 1 and "もうあります" in r.stdout and roundups_text() == before, r.stdout)

# 2本目（前の週）を足すと、新しい週が先頭に並ぶ
items2 = make_items()
for i in range(12):
    items2.append(dict(items2[0], cid=f"old{i:02d}", date="2026-09-21 00:00:00", actress=[], maker="メーカーZ", tags=[], duration_min=None))
items2.append(dict(items2[0], cid="dupA", date="2026-09-21 00:00:00", actress=["双子", "双子"], maker="メーカーZ", tags=["VR", "VR"], duration_min=None))
write_json(DATA, items2)
wk21 = listing("--today", "2026-10-07", "--week-start", "2026-09-21")
check("出演者別は2本以上の人だけ。1本だけの人や、同じ作品に同じ名前が2回あるだけの人は載せない", wk21["status"] == "ready" and wk21["actresses"] == [], wk21["actresses"])
other_vr = sum(1 for x in items2 if "2026-09-21" <= x["date"][:10] <= "2026-09-27" and "VR" in x["tags"] and x["cid"] != "dupA")
check("同じ作品に同じ形式が2回あっても1本と数える", [f["count"] for f in wk21["formats"] if f["name"] == "VR"] == [1 + other_vr], (wk21["formats"], other_vr))
second = good_article(
    week_start="2026-09-21",
    lead="9月21日から9月27日までの1週間に発売された作品のまとめです。メーカーZの作品が13本と最も多く、そのすべてが9月21日の発売です。ほかの日の発売は少なめの週でした。",
    picks=[{"cid": f"old{i:02d}", "note": f"メーカーZの作品です。9月21日に発売された一本で、{'ABC'[i - 1]}番目の候補として、発売日をチェックしておきたい作品です。"} for i in range(1, 4)])
r = run("apply", article_file("second.json", second), "--today", "2026-10-06")
rows = json.loads(roundups_text()) if r.returncode == 0 else []
check("2本目も書き込める", r.returncode == 0, r.stdout)
check("記事は新しい週が先頭", [x["week_start"] for x in rows] == ["2026-09-28", "2026-09-21"], [x["week_start"] for x in rows])

print("\n■ apply が断るもの（1件でも問題があれば何も書かない）")
fresh()
base = roundups_text()


def rejected(label, article, expect=None, today="2026-10-05"):
    path = article_file("bad.json", article)
    r = run("apply", path, "--today", today)
    msg = r.stdout + r.stderr
    ok = r.returncode == 1 and roundups_text() == base and (expect is None or expect in msg)
    check(label, ok, f"終了コード{r.returncode} / 変更なし={roundups_text() == base} / {msg[:240]}")


g = good_article()
rejected("導入文が短すぎる", good_article(lead="短い導入文です。"), "文字数")
rejected("導入文が長すぎる", good_article(lead="あ" * 301), "文字数")
rejected("導入文に改行が入っている", good_article(lead=g["lead"][:40] + "\n" + g["lead"][40:]), "改行")
rejected("導入文にURLが入っている", good_article(lead=g["lead"] + " https://example.com/"), "URL")
rejected("導入文に絵文字が入っている", good_article(lead=g["lead"] + "😊"), "絵文字")
rejected("導入文に「今週」など古くなる言い方が入っている", good_article(lead=g["lead"] + "今週の注目です。"), "古くなる")
rejected("導入文に直接的な言葉が入っている", good_article(lead=g["lead"] + "中出し"), "使えない言葉")
rejected("導入文に未成年をにおわせる言葉が入っている", good_article(lead=g["lead"] + "少女のような"), "使えない言葉")
rejected("導入文が文字列でない", good_article(lead=123), "lead")
rejected("注目の作品が2件しかない", good_article(picks=g["picks"][:2]), "3〜6件")
rejected("注目の作品が7件ある", good_article(picks=[{"cid": f"wk{i:02d}", "note": f"メーカーAの作品です。発売日と形式をチェックしておける、{'ABCDEFG'[i]}番目の候補として並べた一本になります。"} for i in range(7)]), "3〜6件")
rejected("注目の作品がリストでない", good_article(picks="wk00"), "リスト")
rejected("注目の作品の項目が {cid, note} でない", good_article(picks=[g["picks"][0], g["picks"][1], "wk13"]), "cid")
rejected("この週にない cid（前の週の作品）", good_article(picks=[g["picks"][0], g["picks"][1], {"cid": "pre0", "note": g["picks"][2]["note"]}]), "この週の作品にありません")
rejected("この週にない cid（存在しない）", good_article(picks=[g["picks"][0], g["picks"][1], {"cid": "no-such", "note": g["picks"][2]["note"]}]), "この週の作品にありません")
rejected("cid が重複している", good_article(picks=[g["picks"][0], g["picks"][1], dict(g["picks"][1], note=g["picks"][2]["note"])]), "重複")
rejected("ひとことが短すぎる", good_article(picks=[g["picks"][0], g["picks"][1], {"cid": "wk13", "note": "短い"}]), "文字数")
rejected("ひとことが長すぎる", good_article(picks=[g["picks"][0], g["picks"][1], {"cid": "wk13", "note": "い" * 121}]), "文字数")
rejected("ひとことに直接的な言葉が入っている", good_article(picks=[g["picks"][0], g["picks"][1], {"cid": "wk13", "note": g["picks"][2]["note"] + "輪姦"}]), "使えない言葉")
rejected("ひとことに出演者名が2回入っている", good_article(picks=[g["picks"][0], dict(g["picks"][1], note=g["picks"][1]["note"] + "桜"), g["picks"][2]]), "2回以上")
rejected("同じひとことを複数の作品に使い回している", good_article(picks=[g["picks"][0], g["picks"][1], dict(g["picks"][1], cid="wk13")]), "同じ文章")
rejected("導入文に、一覧にない数字（99本）が入っている", good_article(lead=g["lead"].replace("24本", "99本")), "一覧にない数字")
rejected("ひとことに、一覧にない数字（収録時間 999分）が入っている", good_article(picks=[g["picks"][0], g["picks"][1], {"cid": "wk13", "note": "10月3日発売のメーカーAの作品で、収録時間は999分と長めです。気になる方はチェックを。"}]), "一覧にない数字")
rejected("月曜日でない week_start", good_article(week_start="2026-09-29"), "月曜日")
rejected("日付の形が違う week_start", good_article(week_start="9/28"), "月曜日")
rejected("まだ終わっていない週", good_article(week_start="2026-09-28"), "まだ終わっていません", today="2026-10-04")
rejected("作品が少ない週", good_article(week_start="2026-09-21"), "満たない")
rejected("記事の形が違う（リスト）", [good_article()], "形")
rejected("良い項目と悪い項目が混ざっていたら、良いほうも書かない", good_article(picks=[g["picks"][0], g["picks"][1], {"cid": "wk13", "note": "短い"}]), "文字数")

path = article_file("ok_again.json", good_article())
r = run("apply", path, "--today", "bad")
check("--today の形が違えば断る", r.returncode == 1 and roundups_text() == base, r.stdout + r.stderr)
r = run("apply", os.path.join(tmp, "missing.json"), "--today", "2026-10-05")
check("ファイルが無ければ断る", r.returncode != 0 and roundups_text() == base)
broken = os.path.join(tmp, "broken.json")
open(broken, "w").write("{not json")
r = run("apply", broken, "--today", "2026-10-05")
check("壊れたJSONは断る", r.returncode != 0 and roundups_text() == base)

print("\n■ 数字のチェックで、うっかり断らないもの")
ok_numbers = good_article(picks=[
    {"cid": "wk00", "note": "メーカーAの作品で、VR形式。9月28日の発売で、収録時間は120分。8Kや4Kのような英数字は数字扱いしません。"},
    g["picks"][1], g["picks"][2]])
r = run("apply", article_file("ok_numbers.json", ok_numbers), "--dry-run", "--today", "2026-10-05")
check("VR・8K のような英数字のかたまりは、数字としては数えない", r.returncode == 0, r.stdout + r.stderr)
name_note = {"cid": "wk08", "note": "NO.99みゆさんが出演する作品で、10月1日に発売されました。メーカーの記載はなく、気になる方は発売日のチェックをおすすめします。"}
r = run("apply", article_file("ok_name.json", good_article(picks=[g["picks"][0], g["picks"][1], name_note])), "--dry-run", "--today", "2026-10-05")
check("出演者名の中の数字（NO.99みゆ の 99）は、数字として数えない", r.returncode == 0, r.stdout + r.stderr)
r = run("apply", path, "--dry-run", "--today", "2026-10-05")
check("正しい記事は、何度点検しても通る", r.returncode == 0, r.stdout + r.stderr)

print("\n■ 保存データが壊れているとき")
fresh()
open(DATA, "w", encoding="utf-8").write("{壊れている")
check("list は止まる", run("list", "--today", "2026-10-05").returncode != 0)
check("apply も止まる", run("apply", article_file("g2.json", good_article()), "--today", "2026-10-05").returncode != 0 and roundups_text() is None)
fresh()
open(ROUNDUPS, "w", encoding="utf-8").write('{"week_start": "x"}')
check("まとめ記事のデータが壊れていたら、書き込まずに止まる", run("apply", article_file("g3.json", good_article()), "--today", "2026-10-05").returncode != 0
      and roundups_text() == '{"week_start": "x"}')

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
