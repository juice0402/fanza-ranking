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
RANKS = os.path.join(tmp, "rank_history.json")   # 人気の動き（DATA_PATH と同じ場所から読む）
CATALOG = os.path.join(tmp, "catalog")            # 過去作品（同じ）


def make_items():
    """2026-09-28(月)〜10-04(日) に24本。前の週に3本、次の週に4本。"""
    makers = ["メーカーA", "メーカーA", "メーカーA", "メーカーB", "メーカーB", "メーカーC", "メーカー2号", "メーカーD", "メーカーE", "メーカーF"]
    # 6人以上が2本以上に出る（上位5人までの切り捨てを試す）・1本だけの人もいる・出演者なしもいる・名前に数字が入る人もいる
    actresses = ["花子", "葵", "彩", "月", "桜", "星", "", "花子", "NO.99みゆ", "葵", "彩", "月", "単発"]
    rows = []

    def add(cid, date, n):
        a = actresses[n % len(actresses)]
        rows.append({
            # wk10 だけ、未成年を連想させる言葉の入ったタイトル（注目の作品に選べない・人気の作品にも入れない）
            "cid": cid, "title": f"【VR】秘密のタイトル{cid}" + ("の少女" if cid == "wk10" else ""), "url": "https://example.com/" + cid, "image_url": "", "sample_images": [],
            "date": f"{date} 00:00:00", "maker": makers[n % len(makers)] if n % 9 != 8 else "不明",
            "actress": [a] if a else [],
            # ジャンルは、サイトのジャンルのページの一覧（巨乳・人妻・主婦など）にあるものだけを出す。「内容を表すジャンル」は出さない
            "genres": ["内容を表すジャンル"] + (["巨乳"] if n % 2 == 0 else []) + (["人妻・主婦", "デビュー作品"] if n % 5 == 0 else []),
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


# 人気の動き: wk00 は 9/28 から 5→3→1→2位（最高1位・10位以内4日）、wk04 は 40→12位、wk05 は一度も入っていない。
# 過去作品の cat01（10/2発売・この週の作品データには無い）は 2位。前の週の pre0 は 1位（この週には入らない）
RANK_ROWS = {
    "wk00": {"d": "2026-09-28", "n": [5, 3, 1, 2, 0, None, 0, 0]},
    "wk04": {"d": "2026-09-29", "n": [40, 12]},
    "wk05": {"d": "2026-09-29", "n": [0, 0, 0]},
    "cat01": {"d": "2026-10-02", "n": [8, 2, 4], "a": [900]},
    "pre0": {"d": "2026-09-22", "n": [1, 1]},
    "wk10": {"d": "2026-10-02", "n": [1, 1]},   # 未成年を連想させるタイトルの作品（人気の作品に入れない）
}
CAT_ROW = {"cid": "cat01", "title": "過去作品の秘密のタイトル", "url": "https://example.com/cat01", "image_url": "", "sample_images": [],
           "date": "2026-10-02 10:00:00", "maker": "メーカーX", "actress": ["カタ子"], "genres": ["巨乳"], "tags": [],
           "duration_min": 150, "comment": "", "comment_kind": "none", "comment_tries": 0, "updated": "2026-10-02"}


def fresh():
    write_json(DATA, make_items())
    if os.path.exists(ROUNDUPS):
        os.remove(ROUNDUPS)
    write_json(RANKS, {"updated": "2026-10-05", "items": RANK_ROWS})
    os.makedirs(CATALOG, exist_ok=True)
    write_json(os.path.join(CATALOG, "2026-10.json"), [CAT_ROW])


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
check("作品タイトルや、一覧に無いジャンルを出さない（出演者・メーカー・形式・発売日・収録時間・一覧のジャンル・デビュー作か・最高順位だけ）",
      "秘密のタイトル" not in json.dumps(out, ensure_ascii=False) and "内容を表すジャンル" not in json.dumps(out, ensure_ascii=False)
      and all(set(x) == {"cid", "date", "actress", "maker", "formats", "duration_min", "genres", "debut", "best_rank", "no_pick"} for x in out["items"]))
check("未成年を連想させるタイトルの作品は no_pick: true（タイトルは出さずに、選べないことだけ知らせる）",
      [x["cid"] for x in out["items"] if x["no_pick"]] == ["wk10"] and "少女" not in json.dumps(out, ensure_ascii=False))
check("ジャンルは、サイトのジャンルのページの一覧にあるものだけ（デビュー作品は debut で）",
      all(set(x["genres"]) <= {"巨乳", "人妻・主婦"} for x in out["items"]) and any(x["genres"] for x in out["items"])
      and [x["debut"] for x in out["items"]] == ["デビュー作品" in x["genres"] for x in week])
by_list = {x["cid"]: x for x in out["items"]}
check("作品ごとの最高順位（人気の動きの記録。一度も入っていない・記録が無い作品は null）",
      by_list["wk00"]["best_rank"] == 1 and by_list["wk04"]["best_rank"] == 12 and by_list["wk05"]["best_rank"] is None and by_list["wk01"]["best_rank"] is None)

print("\n■ list の傾向（trend）")
tr = out["trend"]
prev_week = [x for x in items if "2026-09-21" <= x["date"][:10] <= "2026-09-27"]
check("本数と、前の週の本数", tr["total"] == 24 and tr["prev_total"] == len(prev_week) == 3 and tr["prev_week_start"] == "2026-09-21", (tr["total"], tr["prev_total"]))
check("VRの本数（形式のタグ・ジャンル・タイトルのどれか）と、前の週のVRの本数",
      tr["vr"] == 24 and tr["prev_vr"] == 3, (tr["vr"], tr["prev_vr"]))
check("デビュー作の本数", tr["debut"] == sum(1 for x in week if "デビュー作品" in x["genres"]), tr["debut"])
gn = {}
for x in week:
    for g_ in ("巨乳", "人妻・主婦"):
        gn[g_] = gn.get(g_, 0) + (g_ in x["genres"])
gp = {g_: sum(1 for x in prev_week if g_ in x["genres"]) for g_ in ("巨乳", "人妻・主婦")}
check("ジャンルの本数と前の週の本数（多い順。一覧にあるジャンルだけ）",
      tr["genres"] == sorted([{"name": g_, "count": gn[g_], "prev": gp[g_]} for g_ in gn], key=lambda r: (-r["count"], -r["prev"], r["name"])), tr["genres"])
check("人気の作品は、この週に発売された作品の最高順位の順（過去作品の作品も入る・前の週の作品・入っていない作品・未成年を連想させるタイトルの作品は入らない）",
      [p_["cid"] for p_ in tr["popular"]] == ["wk00", "cat01", "wk04"] and tr["popular_ranked"] == 3, tr["popular"])
p0 = tr["popular"][0]
check("最高順位・その日・10位以内の日数・100位以内の日数（記録の無い日 null は数えない）",
      (p0["best"], p0["best_date"], p0["days10"], p0["days100"]) == (1, "2026-09-30", 4, 4) and tr["popular"][2]["days10"] == 0 and tr["popular"][2]["days100"] == 2, p0)
check("人気の作品は、タイトルを出さず、メーカー・出演者だけ", tr["popular"][1]["maker"] == "メーカーX" and tr["popular"][1]["actress"] == ["カタ子"]
      and "秘密のタイトル" not in json.dumps(tr, ensure_ascii=False))
os.remove(RANKS)
tr_none = listing("--today", "2026-10-05")["trend"]
check("人気の動きの記録が無くても止まらない（人気の作品が空になるだけ）", tr_none["popular"] == [] and tr_none["total"] == 24)
open(RANKS, "w").write("{壊れている")
check("人気の動きの記録が壊れていても止まらない", listing("--today", "2026-10-05")["trend"]["popular"] == [])
fresh()
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
        "trend": "前の週の3本から21本増えて、24本の週になりました。新着の人気順では、9月30日にメーカーAの作品が最高1位まで上がり、10位以内に4日入っています。メーカーXの作品も2位に入りました。ジャンルでは巨乳が多く、全体の本数とともに増えています。",
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
check("保存の形: week_start・lead・trend・picks・written（公開日=--today）・facts", len(saved) == 1 and set(saved[0]) == {"week_start", "lead", "trend", "picks", "written", "facts"}
      and saved[0]["written"] == "2026-10-05" and saved[0]["picks"][0] == {"cid": "wk00", "note": good_article()["picks"][0]["note"]}
      and saved[0]["trend"] == good_article()["trend"], saved)
fx = saved[0]["facts"]
check("facts は、書いたときの傾向の数字（本数・前の週・VR・デビュー作・ジャンル・人気の作品5本まで。タイトル・出演者は入れない）",
      set(fx) == {"total", "prev_total", "vr", "prev_vr", "debut", "genres", "popular"} and fx["total"] == 24 and fx["prev_total"] == 3
      and fx["genres"] == tr["genres"] and fx["popular"] == [{"cid": "wk00", "best": 1, "days10": 4}, {"cid": "cat01", "best": 2, "days10": 3}, {"cid": "wk04", "best": 12, "days10": 0}]
      and "カタ子" not in json.dumps(fx, ensure_ascii=False), fx)
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
    trend="前の週の記録は無く、この週はメーカーZの作品が中心でした。新着の人気順では、9月22日発売の作品が最高1位で、10位以内に2日入っています。ジャンルの数は少なく、発売日が9月21日に集まった週です。",
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
no_trend = good_article()
del no_trend["trend"]
rejected("傾向（trend）が無い", no_trend, "trend")
rejected("傾向が短すぎる", good_article(trend="前の週より増えました。"), "文字数")
rejected("傾向が長すぎる", good_article(trend="う" * 361), "文字数")
rejected("傾向が導入文と同じ", good_article(trend=g["lead"]), "導入文と同じ")
rejected("傾向に、一覧にない数字（最高63位。記録は1位）が入っている", good_article(trend=g["trend"].replace("最高1位", "最高63位")), "一覧にない数字")
rejected("傾向に、確かめられない評価（話題・大人気）が入っている", good_article(trend=g["trend"] + "話題を集めた大人気の週です。"), "確かめられない評価")
rejected("傾向に「今週」など古くなる言い方が入っている", good_article(trend=g["trend"].replace("24本の週", "今週は24本")), "古くなる")
rejected("注目の作品が2件しかない", good_article(picks=g["picks"][:2]), "3〜6件")
rejected("未成年を連想させるタイトルの作品（no_pick）は選べない", good_article(picks=g["picks"][:2] + [{"cid": "wk10", "note": "10月2日に発売されたメーカーAの作品です。VR形式で、発売日をチェックしておきたい一本です。"}]), "選べません")
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

r = run("apply", article_file("ok_trend_words.json", good_article(trend=g["trend"] + "人気の作品の多くが10月の発売です。")), "--dry-run", "--today", "2026-10-05")
check("傾向では、人気順の数字で裏づけられる「人気の」は使える", r.returncode == 0, r.stdout + r.stderr)
r = run("apply", article_file("ok_cat_name.json", good_article(trend=g["trend"] + "カタ子さんの作品も上位です。")), "--dry-run", "--today", "2026-10-05")
check("傾向では、人気の作品（過去作品の作品も）の出演者名も使える", r.returncode == 0, r.stdout + r.stderr)

print("\n■ add-trend（傾向の無い前の記事に、あとから傾向を足す）")
fresh()
old_article = {"week_start": "2026-09-28", "lead": g["lead"], "picks": g["picks"], "written": "2026-10-05"}
write_json(ROUNDUPS, [old_article])
before = roundups_text()
lo = listing("--today", "2026-10-05")
check("傾向の無い前の記事の週は、list が「もう書いてある」と、足すための傾向の数字・導入文を出す",
      lo["status"] == "already_written" and lo["trend"]["total"] == 24 and lo["lead"] == g["lead"] and "items" not in lo, lo.get("status"))
r = run("add-trend", article_file("t_bad.json", {"week_start": "2026-09-28", "trend": "短い"}))
check("点検に通らない傾向は足さない", r.returncode == 1 and roundups_text() == before and "文字数" in r.stdout, r.stdout)
r = run("add-trend", article_file("t_none.json", {"week_start": "2026-09-21", "trend": g["trend"]}))
check("記事の無い週には足さない", r.returncode != 0 and roundups_text() == before)
r = run("add-trend", article_file("t_dry.json", {"week_start": "2026-09-28", "trend": g["trend"]}), "--dry-run")
check("--dry-run は書き込まない", r.returncode == 0 and roundups_text() == before, r.stdout + r.stderr)
r = run("add-trend", article_file("t_ok.json", {"week_start": "2026-09-28", "trend": g["trend"]}))
after = json.loads(roundups_text()) if r.returncode == 0 else []
check("傾向と facts を足し、導入文・注目の作品・公開日は変えない", r.returncode == 0 and after[0]["trend"] == g["trend"] and after[0]["facts"]["total"] == 24
      and {k: after[0][k] for k in old_article} == old_article, r.stdout + r.stderr)
again = roundups_text()
check("傾向を足したあとの list は、傾向の数字を出さない", "trend" not in listing("--today", "2026-10-05"))
r = run("add-trend", article_file("t_ok.json", {"week_start": "2026-09-28", "trend": g["trend"]}))
check("もう傾向がある記事には足さない（上書きしない）", r.returncode != 0 and roundups_text() == again)

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
