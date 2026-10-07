"""scripts/claude_monthly.py（Claude が月のまとめ記事を書くための道具。2026-10-07 から）のテスト

本番データではなく、このテストの中で作った固定のデータ（2026年10月に40本・9月に6本・11月に3本）で試します。
実行: python3 tests/test_claude_monthly.py   （どこから実行してもOK）
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "claude_monthly.py")

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ✅ " if cond else "  ❌ ") + name + (f"  → {detail}" if (detail and not cond) else ""))


tmp = tempfile.mkdtemp(prefix="claude_monthly_test_")
DATA = os.path.join(tmp, "items.json")
MONTHLY = os.path.join(tmp, "monthly.json")
ROUNDUPS = os.path.join(tmp, "roundups.json")
RANKS = os.path.join(tmp, "rank_history.json")
CATALOG = os.path.join(tmp, "catalog")


def make_items():
    """10月に40本（1日〜31日にばらける）・9月に6本・11月に3本"""
    makers = ["メーカーA", "メーカーA", "メーカーB", "メーカーC", "メーカーD", "メーカーE", "メーカーF"]
    actresses = ["花子", "葵", "彩", "", "花子", "葵", "単発"]
    rows = []

    def add(cid, day, n):
        a = actresses[n % len(actresses)]
        rows.append({
            "cid": cid, "title": f"秘密のタイトル{cid}" + ("の少女" if cid == "oc07" else ""),  # oc07 は注目の作品に選べない "url": "https://example.com/" + cid, "image_url": "", "sample_images": [],
            "date": f"{day} 10:00:00", "maker": makers[n % len(makers)] if n % 11 != 10 else "不明",
            "actress": [a] if a else [],
            "genres": ["内容を表すジャンル"] + (["巨乳"] if n % 2 == 0 else ["熟女"]) + (["デビュー作品"] if n % 9 == 0 else []),
            "tags": ["VR"] if n % 4 == 0 else (["8K"] if n % 4 == 1 else []),
            "duration_min": 120 if n % 3 == 0 else (None if n % 3 == 1 else 95),
            "comment": f"コメント{cid}", "comment_kind": "ai", "comment_tries": 0, "updated": "2026-10-01",
        })

    n = 0
    for i in range(40):
        add(f"oc{i:02d}", f"2026-10-{(i % 31) + 1:02d}", n)
        n += 1
    for i in range(6):
        add(f"sp{i}", f"2026-09-{20 + i:02d}", n)
        n += 1
    for i in range(3):
        add(f"nv{i}", "2026-11-02", n)
        n += 1
    return rows


RANK_ROWS = {
    "oc00": {"d": "2026-10-01", "n": [9, 4, 2, 3, 0, 0, 0, 0]},    # 最高2位（10月3日）・10位以内4日
    "oc05": {"d": "2026-10-06", "n": [30, 15]},                      # 最高15位
    "cat1": {"d": "2026-10-20", "n": [1, 1, 3]},                     # 過去作品の作品（10月20日発売）が最高1位
    "sp0": {"d": "2026-09-20", "n": [1]},                            # 9月の作品（10月の人気には入らない）
}
CAT_ROW = {"cid": "cat1", "title": "過去作品のタイトル", "url": "https://example.com/cat1", "image_url": "", "sample_images": [],
           "date": "2026-10-20 10:00:00", "maker": "メーカーX", "actress": ["カタ子"], "genres": ["巨乳"], "tags": [],
           "duration_min": 150, "comment": "", "comment_kind": "none", "comment_tries": 0, "updated": "2026-10-20"}


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def fresh():
    write_json(DATA, make_items())
    for p in (MONTHLY, ROUNDUPS):
        if os.path.exists(p):
            os.remove(p)
    write_json(RANKS, {"updated": "2026-11-01", "items": RANK_ROWS})
    os.makedirs(CATALOG, exist_ok=True)
    write_json(os.path.join(CATALOG, "2026-10.json"), [CAT_ROW])
    write_json(ROUNDUPS, [{"week_start": "2026-10-05", "lead": "x", "picks": [], "written": "2026-10-12"}])


def run(*args):
    env = dict(os.environ, DATA_PATH=DATA, MONTHLY_PATH=MONTHLY, ROUNDUPS_PATH=ROUNDUPS)
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=env, encoding="utf-8")


def listing(*args):
    r = run("list", *args)
    return json.loads(r.stdout) if r.returncode == 0 else None


def monthly_text():
    return open(MONTHLY, encoding="utf-8").read() if os.path.exists(MONTHLY) else None


def article_file(name, article):
    path = os.path.join(tmp, name)
    write_json(path, article)
    return path


fresh()
items = make_items()
octo = [x for x in items if x["date"].startswith("2026-10")]

print("■ list（書く対象の月を出す）")
out = listing("--today", "2026-11-01")
check("今日が11月1日なら、10月が対象", out and out["month"] == "2026-10" and out["first"] == "2026-10-01" and out["last"] == "2026-10-31" and out["status"] == "ready", out and out.get("status"))
check("11月5日でも同じ月が対象（1日の実行がずれても大丈夫）", listing("--today", "2026-11-05")["month"] == "2026-10")
check("1月なら前の年の12月", listing("--today", "2027-01-01")["month"] == "2026-12")
check("10月31日の今日は、10月はまだ終わっていない", listing("--today", "2026-10-31", "--month", "2026-10")["status"] == "not_finished")
check("作品が少ない月は作らない（too_few_items）", listing("--today", "2026-11-01", "--month", "2026-09")["status"] == "too_few_items")
check("月の形が違えば断る", run("list", "--month", "2026-13").returncode != 0 and run("list", "--month", "10月").returncode != 0)
check("その月の作品だけが入る", sorted(x["cid"] for x in out["items"]) == sorted(x["cid"] for x in octo) and out["total"] == 40)
check("作品タイトル・一覧に無いジャンルを出さない", "秘密のタイトル" not in json.dumps(out, ensure_ascii=False) and "内容を表すジャンル" not in json.dumps(out, ensure_ascii=False)
      and "過去作品のタイトル" not in json.dumps(out, ensure_ascii=False)
      and all(set(x) == {"cid", "date", "actress", "maker", "formats", "duration_min", "genres", "debut", "best_rank", "no_pick"} for x in out["items"]))
check("未成年を連想させるタイトルの作品は no_pick: true", [x["cid"] for x in out["items"] if x["no_pick"]] == ["oc07"] and "少女" not in json.dumps(out, ensure_ascii=False))
mk = {}
for x in octo:
    if x["maker"] != "不明":
        mk[x["maker"]] = mk.get(x["maker"], 0) + 1
check("メーカー別の本数（多い順・同数は名前順・5つまで）", out["makers"] == [{"name": k, "count": v} for k, v in sorted(mk.items(), key=lambda p: (-p[1], p[0]))][:5], out["makers"])
check("週ごとの本数の合計 = 全体の本数（週は月曜で区切る）", sum(w["count"] for w in out["per_week"]) == 40 and out["per_week"][0]["week_start"] == "2026-09-28", out["per_week"])
check("掲載の多かった日（多い順に3日）", len(out["busy_days"]) == 3 and out["busy_days"][0]["count"] >= out["busy_days"][-1]["count"] and out["busy_days"][0]["count"] == 2, out["busy_days"])
check("この月の週のまとめの週（月曜がこの月に入る記事）", out["weekly"] == ["2026-10-05"], out["weekly"])
tr = out["trend"]
check("傾向: 本数・前の月の本数・前の月", tr["total"] == 40 and tr["prev_total"] == 6 and tr["prev_month"] == "2026-09", tr)
check("傾向: 人気の作品は、その月に発売された作品の最高順位の順（過去作品も入る・前の月の作品は入らない）",
      [p["cid"] for p in tr["popular"]] == ["cat1", "oc00", "oc05"], [p["cid"] for p in tr["popular"]])
check("作品ごとの最高順位", {x["cid"]: x["best_rank"] for x in out["items"]}["oc00"] == 2)

print("\n■ apply（点検して書き込む）")


def good_article(**override):
    a = {
        "month": "2026-10",
        "lead": "2026年10月に発売された新作のうち、このサイトで紹介したのは40本でした。10月1日から10月31日までまんべんなく並び、メーカーではメーカーAが12本と最も多く、花子さんが出演作の多い月です。VRや8Kの作品も含まれています。",
        "trend": "前の月の6本から34本増えて、40本を掲載しました。ジャンルでは巨乳と熟女が20本ずつ並んでいます。新着の人気順では、10月20日発売のメーカーXの作品が最高1位、メーカーAの作品が最高2位まで上がり、10位以内に4日入りました。",
        "picks": [
            {"cid": "oc00", "note": "メーカーAの作品で、花子さんが出演。VR形式で、10月1日に発売されました。収録時間は120分です。"},
            {"cid": "oc01", "note": "10月2日に発売された、葵さん出演の作品です。メーカーAの一本で、8K形式となっています。"},
            {"cid": "oc02", "note": "メーカーBから10月3日に発売された、彩さん出演の作品です。収録時間は95分です。"},
            {"cid": "oc05", "note": "10月6日発売のメーカーEの作品で、新着の人気順では最高15位まで上がりました。出演者は葵さんです。"},
        ],
    }
    a.update(override)
    return a


g = good_article()
path = article_file("good.json", g)
r = run("apply", path, "--dry-run", "--today", "2026-11-01")
check("--dry-run は成功して、ファイルを作らない", r.returncode == 0 and monthly_text() is None, r.stdout + r.stderr)
r = run("apply", path, "--today", "2026-11-01")
check("正しい記事は書き込める", r.returncode == 0, r.stdout + r.stderr)
saved = json.loads(monthly_text()) if monthly_text() else []
check("保存の形: month・lead・trend・picks・written・facts", len(saved) == 1 and set(saved[0]) == {"month", "lead", "trend", "picks", "written", "facts"}
      and saved[0]["written"] == "2026-11-01" and saved[0]["picks"][0] == g["picks"][0], saved)
check("facts は、週のまとめと同じ形（本数・前の月・VR・デビュー作・ジャンル・人気の作品5本まで）",
      saved and set(saved[0]["facts"]) == {"total", "prev_total", "vr", "prev_vr", "debut", "genres", "popular"} and saved[0]["facts"]["total"] == 40
      and [p["cid"] for p in saved[0]["facts"]["popular"]] == ["cat1", "oc00", "oc05"], saved and saved[0]["facts"])
check("書き方が決まった形（インデント1・日本語そのまま・末尾に改行）", monthly_text() == json.dumps(saved, ensure_ascii=False, indent=1) + "\n")
check("作業用の .tmp ファイルが残らない", not os.path.exists(MONTHLY + ".tmp"))
check("書いたあとの list は「もう書いてある」", listing("--today", "2026-11-01")["status"] == "already_written")
before = monthly_text()
r = run("apply", path, "--today", "2026-11-02")
check("同じ月をもう一度書こうとしたら断る（上書きしない）", r.returncode == 1 and "もうあります" in r.stdout and monthly_text() == before, r.stdout)

print("\n■ apply が断るもの（1件でも問題があれば何も書かない）")
fresh()


def rejected(label, article, expect=None, today="2026-11-01"):
    r = run("apply", article_file("bad.json", article), "--today", today)
    msg = r.stdout + r.stderr
    check(label, r.returncode == 1 and monthly_text() is None and (expect is None or expect in msg), f"終了コード{r.returncode} / {msg[:240]}")


rejected("導入文が短すぎる", good_article(lead="短い導入文です。"), "文字数")
rejected("導入文に「今月」など古くなる言い方", good_article(lead=g["lead"] + "今月の新作です。"), "古くなる")
no_trend = good_article()
del no_trend["trend"]
rejected("傾向が無い", no_trend, "trend")
rejected("傾向が導入文と同じ", good_article(trend=g["lead"]), "導入文と同じ")
rejected("傾向に確かめられない評価（待望・必見）", good_article(trend=g["trend"] + "待望の必見作がそろいました。"), "確かめられない評価")
rejected("傾向に一覧にない数字（最高88位）", good_article(trend=g["trend"].replace("最高2位", "最高88位")), "一覧にない数字")
rejected("注目の作品が3件しかない", good_article(picks=g["picks"][:3]), "4〜8件")
rejected("注目の作品が9件ある", good_article(picks=[{"cid": f"oc{i:02d}", "note": f"メーカーの作品です。発売日と形式を確かめておける、{'ABCDEFGHI'[i]}番目の候補として並べた一本になります。"} for i in range(9)]), "4〜8件")
rejected("この月にない cid（前の月の作品）", good_article(picks=g["picks"][:3] + [{"cid": "sp0", "note": g["picks"][3]["note"]}]), "この月の作品にありません")
rejected("この月にない cid（過去作品の作品は選べない）", good_article(picks=g["picks"][:3] + [{"cid": "cat1", "note": g["picks"][3]["note"]}]), "この月の作品にありません")
rejected("未成年を連想させるタイトルの作品（no_pick）は選べない", good_article(picks=g["picks"][:3] + [{"cid": "oc07", "note": g["picks"][3]["note"]}]), "選べません")
rejected("cid が重複している", good_article(picks=g["picks"][:3] + [dict(g["picks"][0], note=g["picks"][3]["note"])]), "重複")
rejected("同じひとことの使い回し", good_article(picks=g["picks"][:3] + [dict(g["picks"][2], cid="oc05")]), "同じ文章")
rejected("ひとことに直接的な言葉", good_article(picks=g["picks"][:3] + [dict(g["picks"][3], note=g["picks"][3]["note"] + "中出し")]), "使えない言葉")
rejected("ひとことに一覧にない収録時間（999分）", good_article(picks=g["picks"][:3] + [dict(g["picks"][3], note="10月6日発売のメーカーEの作品で、収録時間は999分と長めです。気になる方は確かめてみてください。")]), "一覧にない数字")
rejected("まだ終わっていない月", g, "まだ終わっていません", today="2026-10-31")
rejected("作品が少ない月", good_article(month="2026-09"), "満たない")
rejected("月の形が違う", good_article(month="2026/10"), "YYYY-MM")
rejected("記事の形が違う（リスト）", [g], "形")

print("\n■ 数字のチェックで、うっかり断らないもの")
r = run("apply", article_file("ok_days.json", good_article(lead=g["lead"].replace("10月31日まで", "10月31日まで、4つの週に"))), "--dry-run", "--today", "2026-11-01")
check("月の日（31日）・前の月（9月）・週の数は使える", r.returncode == 0, r.stdout + r.stderr)
r = run("apply", article_file("ok_cat.json", good_article(trend=g["trend"] + "カタ子さんの作品です。")), "--dry-run", "--today", "2026-11-01")
check("人気の作品（過去作品）の出演者名・メーカー名は使える", r.returncode == 0, r.stdout + r.stderr)

print("\n■ 保存データが壊れているとき")
fresh()
open(DATA, "w", encoding="utf-8").write("{壊れている")
check("list は止まる", run("list", "--today", "2026-11-01").returncode != 0)
fresh()
open(MONTHLY, "w", encoding="utf-8").write('{"month": "x"}')
check("月のまとめ記事のデータが壊れていたら、書き込まずに止まる", run("apply", article_file("g3.json", good_article()), "--today", "2026-11-01").returncode != 0
      and monthly_text() == '{"month": "x"}')
fresh()
os.remove(RANKS)
check("人気の動きの記録が無くても書ける（人気の作品が空になるだけ）", listing("--today", "2026-11-01")["trend"]["popular"] == [])

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
