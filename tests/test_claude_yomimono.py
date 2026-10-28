"""scripts/claude_yomimono.py（Claude が読み物の記事を書くための道具）のテスト

本番データではなく、このテストの中で作った固定のデータ（全部で442本。うち AIリマスター の題の作品が12本）で試します。
今日は 2026-10-28 として動かします。
実行: python3 tests/test_claude_yomimono.py   （どこから実行してもOK）
"""
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "claude_yomimono.py")
TODAY = "2026-10-28"

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ✅ " if cond else "  ❌ ") + name + (f"  → {detail}" if (detail and not cond) else ""))


tmp = tempfile.mkdtemp(prefix="claude_yomimono_test_")
DATA = os.path.join(tmp, "new_releases.json")
CATALOG = os.path.join(tmp, "catalog")
YOMI = os.path.join(tmp, "yomimono.json")


def work(cid, date, maker, actress, minutes, genres, title, **extra):
    row = {"cid": cid, "title": title, "url": "https://example.com/" + cid, "image_url": "", "sample_images": [],
           "date": f"{date} 00:00:00", "maker": maker, "actress": actress, "genres": genres, "tags": [],
           "series": "", "label": "", "duration_min": minutes, "comment": "", "comment_kind": "none", "comment_tries": 0, "updated": date}
    row.update(extra)
    return row


AI = "【AIリマスター版】"
# AIリマスター の題の作品（a10 は外す題の言葉「痴漢」、a11 は未成年を連想させる題、a12 は予約）
AI_WORKS = [
    work("h_1abc00001ai", "2024-03-10", "メーカーA", ["花子"], 120, ["ドラマ", "熟女", "ハイビジョン"], AI + "湖畔の朝の物語01", series="シリーズ甲", label="レーベルA"),
    work("abc00002ai", "2024-08-01", "メーカーA", ["花子"], 250, ["女優ベスト・総集編", "4時間以上作品"], AI + "名場面をまとめた特別版02", series="シリーズ甲", label="レーベルA"),
    work("abc00003ai", "2025-02-14", "メーカーA", ["葵", "彩"], 90, ["巨乳", "騎乗位"], AI + "夜明けの港町で待ちわびる物語03", series="シリーズ乙", label="レーベルA"),
    work("abc00004ai", "2025-06-20", "メーカーB", ["葵"], 300, ["ベスト・総集編"], AI + "長い一日の記録04"),
    work("abc00005ai", "2025-11-05", "メーカーB", [], 100, ["巨乳", "クラシック"], AI + "古い町並みの思い出05"),
    work("xyz00006", "2026-01-15", "メーカーC", ["月"], 140, ["ドラマ"], AI + "冬の旅路06"),
    work("xyz00007", "2026-09-03", "メーカーC", ["月"], 60, ["美乳", "復刻"], AI + "海辺の午後07"),
    work("abc00008ai", "2026-10-02", "メーカーD", ["桜"], 245, ["ドラマ"], AI + "秋の夜長の物語08"),
    work("abc00009ai", "2026-10-10", "メーカーE", ["星"], 130, ["熟女"], AI + "山あいの宿09"),
    work("xyz00010", "2026-10-20", "メーカーA", ["花子"], 115, ["巨乳"], AI + "満員電車の痴漢10"),
    work("abc00011ai", "2026-10-21", "メーカーB", ["葵"], None, [], AI + "女子校生の放課後11"),
    work("abc00012ai", "2026-11-05", "メーカーD", ["桜"], None, [], AI + "予約の作品12"),
]


def filler():
    rows = []
    from datetime import date, timedelta
    for n in range(120):  # 熟女（j000〜j059 はドラマも、j000〜j104 はお姉さんも）
        d = (date(2024, 1, 5) + timedelta(days=5 * n)).isoformat()
        g = ["熟女", "ハイビジョン"] + (["ドラマ"] if n < 60 else []) + (["お姉さん"] if n < 105 else [])
        rows.append(work(f"j{n:03d}", d, f"熟メーカー{n % 5}", [f"熟{n % 7}"], 120, g, f"静かな午後の時間{n:03d}"))
    for n in range(105):  # 未成年を連想させるジャンル（テーマの候補にしない）
        rows.append(work(f"s{n:03d}", "2026-10-15", "学メーカー", [], 60, ["女子校生"], f"題s{n:03d}"))
    for n in range(105):  # 行為そのもののジャンル（テーマの候補にしない）
        rows.append(work(f"k{n:03d}", "2026-09-15", "騎メーカー", [], 60, ["騎乗位"], f"題k{n:03d}"))
    for n in range(100):  # 人妻・主婦（テーマの候補にする）
        rows.append(work(f"h{n:03d}", "2026-08-15", f"妻メーカー{n % 4}", [], 90, ["人妻・主婦"], f"題h{n:03d}"))
    return rows


FILLER = filler()
CATALOG_CIDS = {"h_1abc00001ai", "abc00002ai", "abc00003ai", "abc00004ai", "abc00005ai"}
ALL = AI_WORKS + FILLER


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


REVIEWS = {"h_1abc00001ai": [450, 20], "abc00002ai": [400, 5], "abc00004ai": [500, 12], "abc00008ai": [370, 3]}
REVIEWS.update({f"j{n:03d}": [420, 4] for n in range(10)})
REVIEWS["broken"] = [600, 1]   # 形が違う（5より大きい）値は読まない


def fresh():
    shutil.rmtree(CATALOG, ignore_errors=True)
    os.makedirs(CATALOG)
    write_json(DATA, [x for x in ALL if x["cid"] not in CATALOG_CIDS])
    cat = [x for x in AI_WORKS if x["cid"] in CATALOG_CIDS]
    cat.append(dict(AI_WORKS[5], maker="カタログ側のメーカー"))   # 毎日の更新にある作品（数えない。毎日の更新のほうを使う）
    cat.append(dict(AI_WORKS[0], cid="nourl00001ai", url=""))        # FANZAのURLが無い過去作品（サイトに無いので数えない）
    write_json(os.path.join(CATALOG, "2025-01.json"), cat)
    write_json(os.path.join(tmp, "reviews.json"), {"updated": TODAY, "cursor": 0, "items": REVIEWS})
    write_json(os.path.join(tmp, "sale.json"), {"date": TODAY, "campaigns": [
        {"title": "セールA", "begin": "2026-10-25 00:00", "end": "2026-11-03 23:59"},
        {"title": "終わったセール", "begin": "2026-10-10 00:00", "end": "2026-10-20 23:59"}],
        "items": [{"c": "h_1abc00001ai", "k": 0, "p": 700, "l": 1000}, {"c": "abc00004ai", "k": 0, "p": 500, "l": 1000},
                  {"c": "xyz00007", "k": 1, "p": 100, "l": 1000}, {"c": "abc00012ai", "k": 0, "p": 100, "l": 1000}],
        "extra": [{"c": "zzz00001ai", "k": 0, "p": 300, "l": 1000, "t": "【AIリマスター版】よその作品", "d": "2026-10-01", "g": ["巨乳"]},
                  {"c": "zzz00002ai", "k": 0, "p": 100, "l": 1000, "t": "【AIリマスター版】盗撮もの", "d": "2026-10-01", "g": []},
                  {"c": "zzz00003ai", "k": 1, "p": 100, "l": 1000, "t": "【AIリマスター版】終わったセール", "d": "2026-10-01", "g": []},
                  {"c": "zzz00004", "k": 0, "p": 100, "l": 1000, "t": "テーマに入らない作品", "d": "2026-10-01", "g": []}]})
    write_json(os.path.join(tmp, "popularity.json"), {"date": TODAY, "new": {"abc00009ai": 3}, "all": {"h_1abc00001ai": 120, "abc00008ai": 15}})
    write_json(os.path.join(tmp, "catalog_rank.json"), {"abc00004ai": [800, 3], "abc00002ai": [50000, 1]})
    if os.path.exists(YOMI):
        os.remove(YOMI)


def run(*args, env_extra=None):
    env = dict(os.environ, DATA_PATH=DATA, YOMIMONO_PATH=YOMI)
    env.pop("CATALOG_DIR", None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=env, encoding="utf-8")


def listing(*args, env_extra=None):
    r = run("list", *args, "--today", TODAY, env_extra=env_extra)
    return (json.loads(r.stdout) if r.returncode == 0 else None), r


def themes(today=TODAY, cmd="themes"):
    r = run(cmd, "--today", today)
    return json.loads(r.stdout) if r.returncode == 0 else None


def yomi_text():
    return open(YOMI, encoding="utf-8").read() if os.path.exists(YOMI) else None


fresh()
print("■ list（テーマの数字と、選べる作品）")
out, r = listing("--slug", "ai-remaster")
check("はじめの4本のテーマ（ai-remaster）は、--genres・--keywords なしで出せる", out and out["status"] == "new" and out["theme"] == {"genres": [], "keywords": ["AIリマスター"]}, r.stdout[-300:] + r.stderr)
f = out["facts"]
text = json.dumps(out, ensure_ascii=False)
check("作品タイトルを出さない（題の言葉が出力のどこにも無い）",
      all(w not in text for w in ("湖畔", "港町", "痴漢", "女子校生", "放課後", "静かな午後", "【AIリマスター版】")), text[:200])
check("テーマの作品の数: 題に入ったキーワードで数える（外す作品・予約も数に入れる。URLの無い過去作品・重なった作品は数えない）",
      f["total"] == 12 and f["released"] == 11 and f["upcoming"] == 1 and f["excluded"] == 2 and f["site_total"] == len(ALL), (f["total"], f["upcoming"], f["excluded"], f["site_total"]))
check("全体の何本に1本か（四捨五入）", f["share"] == {"pct": round(12 / len(ALL) * 100, 1), "one_in": round(len(ALL) / 12), "phrase": f"{round(len(ALL) / 12)}本に1本"}, f["share"])
check("年ごとの本数（予約も入れる・間の年も0で出す・合計は total）", f["years"] == [{"y": 2024, "n": 2}, {"y": 2025, "n": 3}, {"y": 2026, "n": 7}], f["years"])
month_all = Counter(x["date"][:7] for x in ALL)
check("月ごとの本数は、今日の月までの12か月（古い順）", [m["m"] for m in f["months"]] == [f"2025-{m}" for m in ("11", "12")] + [f"2026-{m:02d}" for m in range(1, 11)], [m["m"] for m in f["months"]])
oct_ = f["months"][-1]
check("月ごとの割合: その月にサイトが集めた作品のうちの本数・%・「N本に1本」",
      oct_ == {"m": "2026-10", "n": 4, "all": month_all["2026-10"], "pct": round(4 / month_all["2026-10"] * 100, 1),
               "one_in": round(month_all["2026-10"] / 4), "phrase": f"{round(month_all['2026-10'] / 4)}本に1本"}
      and f["months"][1] == {"m": "2025-12", "n": 0, "all": 0, "pct": 0.0, "one_in": None, "phrase": None}, (oct_, f["months"][1]))
check("メーカー: 本数の多い順・出した月の数・いちばん多いシリーズとレーベル（過去作品のメーカー名ではなく毎日の更新のほう）",
      f["makers"][0] == {"name": "メーカーA", "n": 4, "months": 4, "series": {"name": "シリーズ甲", "n": 2}, "label": {"name": "レーベルA", "n": 3}}
      and [m["name"] for m in f["makers"]] == ["メーカーA", "メーカーB", "メーカーC", "メーカーD", "メーカーE"] and f["makers"][1]["series"] is None, f["makers"])
check("出演者: 2本以上の人だけ・多い順（同数は名前順）", f["actresses"] == [{"name": "花子", "n": 3}, {"name": "葵", "n": 3}, {"name": "月", "n": 2}, {"name": "桜", "n": 2}], f["actresses"])
check("収録時間: 真ん中の値・240分以上の本数・そのうちの総集編（2つのジャンルを両方数える）",
      f["minutes"] == {"known": 10, "median": 125, "long": 3, "long_best": 2, "best": 2, "best_general": 1, "best_actress": 1}, f["minutes"])
check("1人だけが出ている作品・出演者の無い作品", f["single"] == 10 and f["no_actress"] == 1, (f["single"], f["no_actress"]))
site_avg = round(statistics.mean([4.5, 4.0, 5.0, 3.7] + [4.2] * 10), 2)
check("レビュー: テーマの★の平均・サイト全体の平均・件数の合計・1本あたりの件数（形が違う値は読まない）",
      f["reviews"] == {"reviewed": 4, "avg": 4.3, "site_avg": site_avg, "count": 40, "per_work": 10.0}, f["reviews"])
check("セール: いまセール中の本数（終わったセール・予約・外す題は数えない。サイトに無いセール中の作品 extra はテーマに入れば数える）と、いちばん大きい割引",
      f["sale"] == {"now": 3, "max_off": 70}, f["sale"])
check("人気の順位: いちばん上・100位以内・1000位以内（「まだ分からない」50000は数えない）", f["rank"] == {"best": 3, "top100": 2, "top1000": 4, "ranked": 4}, f["rank"])
check("いっしょに付いているジャンル（多い順・ハイビジョンのような中身を表さないもの・行為のジャンルは出さない）",
      [g["name"] for g in f["genres"][:3]] == ["ドラマ", "巨乳", "熟女"] and f["genres"][0]["n"] == 3
      and not any(g["name"] in ("ハイビジョン", "騎乗位") for g in f["genres"]), f["genres"])
check("番号の終わりが ai の作品の数・クラシック/復刻の作品の数", f["cid_ai"] == 9 and f["classic"] == 2, (f["cid_ai"], f["classic"]))
check("数えた日", f["today"] == TODAY)

cands = out["candidates"]
cc_ = [c["cid"] for c in cands]
check("選べる作品: 外す作品（未成年を連想させる題・外す題の言葉）と予約は入らない",
      set(cc_) == {x["cid"] for x in AI_WORKS[:9]} and not ({"xyz00010", "abc00011ai", "abc00012ai"} & set(cc_)), cc_)
check("選べる作品の項目（タイトルは無い）", all(set(c) == {"cid", "date", "maker", "actress", "minutes", "genres", "series", "rank", "stars", "reviews", "sale"} for c in cands))
check("並べ順: 人気の順位・評価（件数でならす）・セールの点の高い順", cc_[:4] == ["abc00004ai", "h_1abc00001ai", "abc00009ai", "abc00008ai"], cc_)
by = {c["cid"]: c for c in cands}
check("作品ごとの数字（順位・★・件数・セールの割引・収録時間）と、行為のジャンルを出さないこと",
      by["abc00004ai"]["rank"] == 800 and by["abc00004ai"]["stars"] == 5.0 and by["abc00004ai"]["reviews"] == 12
      and by["abc00004ai"]["sale"] == {"off": 50, "end": "2026-11-03 23:59"} and by["abc00003ai"]["genres"] == ["巨乳"]
      and by["xyz00007"]["sale"] is None and by["abc00003ai"]["minutes"] == 90, (by["abc00004ai"], by["abc00003ai"]))

print("\n■ テーマの決まり（ジャンルか、題のキーワード）")
extra = [work("g1", "2026-05-01", "原メーカー", ["原"], 100, ["原作コラボ"], "ジャンルだけの作品"),
         work("g2", "2026-05-02", "原メーカー", ["原"], 100, [], "実写版の作品"),
         work("g3", "2026-05-03", "原メーカー", ["原"], 100, ["原作コラボ"], "実写化の作品"),
         work("g4", "2026-05-04", "原メーカー", ["原"], 100, ["ドラマ"], "関係のない作品")]
write_json(DATA, [x for x in ALL if x["cid"] not in CATALOG_CIDS] + extra)
g, _ = listing("--slug", "gensaku")
check("ジャンルが1つでも付いているか、題にキーワードが入っていればテーマの作品（両方あっても1本）", g["facts"]["total"] == 3 and g["status"] == "too_few", g["facts"]["total"])
g2, _ = listing("--slug", "my-theme", "--genres", "ドラマ", "--keywords", "実写")
check("新しいテーマを --genres・--keywords で（カンマ区切り）", g2["theme"] == {"genres": ["ドラマ"], "keywords": ["実写"]}
      and g2["facts"]["total"] == len({x["cid"] for x in ALL + extra if "ドラマ" in x["genres"] or "実写" in x["title"]}), g2["facts"]["total"])
check("選べる作品が5本に満たないテーマは too_few", g["status"] == "too_few" and "書けません" in g["message"])
fresh()
_, r = listing("--slug", "new-theme")
check("新しい slug は、ジャンルかキーワードが要る", r.returncode != 0 and "--genres" in r.stdout + r.stderr)
_, r = listing("--slug", "Bad_Slug")
check("slug の形が違えば断る", r.returncode != 0 and "slug" in r.stdout + r.stderr)
_, r = listing("--slug", "school", "--genres", "女子校生")
check("未成年を連想させるテーマは断る", r.returncode != 0 and "読み物にしません" in r.stdout + r.stderr)
_, r = listing("--slug", "force", "--keywords", "催眠")
check("無理やり・犯罪を思わせるテーマ（外す題の言葉）は断る", r.returncode != 0 and "読み物にしません" in r.stdout + r.stderr)

print("\n■ 外す題の言葉は site/src/lib/yomimono-exclude.json から読む")
ex = os.path.join(tmp, "exclude.json")
write_json(ex, {"title_words": ["湖畔"]})
o2, _ = listing("--slug", "ai-remaster", env_extra={"YOMIMONO_EXCLUDE_PATH": ex})
c2 = {c["cid"] for c in o2["candidates"]}
check("ファイルの言葉が入った題の作品は外す（未成年を連想させる題は、ファイルに無くても外す）",
      "h_1abc00001ai" not in c2 and "xyz00010" in c2 and "abc00011ai" not in c2 and o2["facts"]["excluded"] == 2, sorted(c2))
open(ex, "w").write("{壊れている")
_, r = listing("--slug", "ai-remaster", env_extra={"YOMIMONO_EXCLUDE_PATH": ex})
check("外す言葉のファイルが読めなければ止まる", r.returncode != 0 and "外す題の言葉" in r.stdout + r.stderr)
real = json.load(open(os.path.join(ROOT, "site", "src", "lib", "yomimono-exclude.json"), encoding="utf-8"))
check("本物のファイルには title_words がある（痴漢・催眠など）", "痴漢" in real["title_words"] and "催眠" in real["title_words"])

print("\n■ apply（点検して書き込む）")
FILL = ["作品ページでは、サンプル動画で画面の様子を確かめられます。",
        "レビューの件数も作品ページに出ているので、星の数字とあわせて見ておくと判断しやすくなります。",
        "気になった作品はお気に入りに入れておくと、あとで見くらべられます。",
        "メーカーごとに出す時期がずれているので、月によって並ぶ作品の顔ぶれが変わります。",
        "同じシリーズの作品は続けて並ぶことが多く、順に見ていく選び方もできます。",
        "出演者の名前から、同じ人の別の作品を探すこともできます。",
        "発売日の新しい順に並べると、出方の変化がよく分かります。",
        "ジャンルの名前は作品ページにも出ているので、気になる言葉から探していけます。"]


def para(head, k):
    return head + "".join(FILL[(k + i) % len(FILL)] for i in range(4))


def good_article(**override):
    share = round(len(ALL) / 12)
    a = {
        "title": "AIリマスター版ってなに？本数とメーカーで見る",
        "description": "FANZAで見かけるAIリマスター版は、前に出た作品の映像を整え直したものです。このサイトの12本を、年ごとの本数やメーカー、収録時間、レビューの数字で見ていき、最初に見る5本を選びました。",
        "lead": para(f"最近、FANZAの新作の一覧で【AIリマスター版】という文字をよく見かけるようになりました。このサイトの{len(ALL)}本のうち12本が、題にAIリマスターと入った作品です。", 0)
        + "\n" + para(f"およそ{share}本に1本の割合で、いつごろ増えたのか、どのメーカーが多いのかを、数字といっしょに見ていきます。", 1),
        "sections": [
            {"h": "AIリマスター版ってなに？", "text": para("以前に発売された作品の映像を、見やすい画質に整え直したものです。番号の終わりがaiの作品は9本でした。", 2)
             + "\n" + para("ジャンルにクラシックや復刻が付いた作品もあり、前の時代の作品だと分かります。", 3)},
            {"h": "2026年は、もう去年の本数をこえた", "chart": "years", "text": para("2024年は2本、2025年は3本でしたが、2026年は7本と、すでに去年をこえています。", 4)
             + "\n" + para("2026年10月は4本で、毎月少しずつではなく、まとめて出ることが多いテーマです。", 5)},
            {"h": "メーカーAが多い", "text": para("メーカー別では、メーカーAが4本でいちばん多く、4か月に分けて出しています。", 6)
             + "\n" + para("出演者では、花子さんと葵さんが3本ずつで並びます。", 7)},
            {"h": "こんな人に向いています", "text": para("収録時間の真ん中の値は125分で、2時間ほどの作品が中心です。", 0)
             + "\n" + para(f"FANZAのレビューの★の平均は4.3で、サイト全体の{site_avg}と近い数字です。", 1)},
            {"h": "選ぶ前に知っておきたいこと", "text": para("4時間以上の作品は3本あり、そのうち2本は総集編です。", 2)
             + "\n" + para("1つの物語を通して見たいときは、作品ページでジャンルと収録時間を先に確かめておくと迷いません。", 3)},
        ],
        "picks": [
            {"cid": "abc00004ai", "why": "メーカーBの300分の作品で、葵さんが出演しています。長い作品をまとめて見たい人に向いています。"},
            {"cid": "h_1abc00001ai", "why": "メーカーAの1本で、花子さんが出演する120分のドラマものです。物語のある作品を探している人に向いています。"},
            {"cid": "abc00009ai", "why": "メーカーEの130分の作品で、星さんが出演。熟女のジャンルが付いた作品を探している人に向いています。"},
            {"cid": "abc00008ai", "why": "メーカーDの245分の作品で、桜さんが出演しています。時間をかけて1本を見たい人に向いています。"},
            {"cid": "xyz00006", "why": "メーカーCの140分のドラマもので、月さんが出演しています。落ち着いた物語を見たい人に向いています。"},
        ],
    }
    a.update(override)
    return a


def article_file(name, articles):
    path = os.path.join(tmp, name)
    write_json(path, articles)
    return path


def apply(articles, *extra, today=TODAY, name="art.json"):
    return run("apply", article_file(name, articles), "--today", today, *extra)


fresh()
r = apply({"ai-remaster": good_article()}, "--dry-run")
check("--dry-run は成功して、ファイルを作らない", r.returncode == 0 and yomi_text() is None, r.stdout + r.stderr)
r = apply({"ai-remaster": good_article()})
check("正しい記事は書き込める", r.returncode == 0 and "書き込みました" in r.stdout, r.stdout + r.stderr)
saved = json.loads(yomi_text())
art = saved["articles"]["ai-remaster"]
check("保存の形: updated と articles[slug]", set(saved) == {"updated", "articles"} and saved["updated"] == TODAY)
check("記事の形: theme・title・description・lead・sections・picks_h（決まった見出し）・picks・years・total・written・checked",
      list(art) == ["theme", "title", "description", "lead", "sections", "picks_h", "picks", "years", "total", "written", "checked"]
      and art["picks_h"] == "最初に見るならこの5本" and art["total"] == 12 and art["written"] == TODAY and art["checked"] == TODAY
      and art["theme"] == {"genres": [], "keywords": ["AIリマスター"]}, list(art))
check("グラフの節には chart: years、記事には years（facts の年ごとの本数）", art["sections"][1]["chart"] == "years" and "chart" not in art["sections"][0]
      and art["years"] == [{"y": 2024, "n": 2}, {"y": 2025, "n": 3}, {"y": 2026, "n": 7}], art["years"])
check("lead・本文は段落を改行1つで区切ったまま、picks は {cid, why}", art["lead"].count("\n") == 1 and art["picks"][0] == good_article()["picks"][0])
check("書き方が決まった形（インデント1・日本語そのまま・末尾に改行）", yomi_text() == json.dumps(saved, ensure_ascii=False, indent=1) + "\n")
check("作業用の .tmp ファイルが残らない", not os.path.exists(YOMI + ".tmp"))
lo, _ = listing("--slug", "ai-remaster")
check("書いたあとの list は status: rewrite と、前の記事の題・日付", lo["status"] == "rewrite" and lo["previous"] == {"title": good_article()["title"], "written": TODAY, "checked": TODAY})

r = apply({"ai-remaster": good_article(title="AIリマスター版ってなに？2026年の本数で見る")}, today="2026-11-30", name="re.json")
re_art = json.loads(yomi_text())["articles"]["ai-remaster"] if r.returncode == 0 else {}
check("書き直しでは、書いた日 written をそのままにして、確かめた日 checked と updated を新しくする",
      r.returncode == 0 and re_art["written"] == TODAY and re_art["checked"] == "2026-11-30" and json.loads(yomi_text())["updated"] == "2026-11-30"
      and re_art["title"].endswith("本数で見る") and "書き直しました" in r.stdout, r.stdout + r.stderr)

# 2本目（新しいテーマ。theme を入れる）
fresh()
jk_out, _ = listing("--slug", "jukujo", "--genres", "熟女")
jk = jk_out["facts"]
jk_c = jk_out["candidates"]
check("同じメーカーの作品は、選べる作品に3本まで", max(Counter(c["maker"] for c in jk_c).values()) <= 3 and len(jk_c) >= 5, Counter(c["maker"] for c in jk_c))
jpicks = [{"cid": c["cid"], "why": f"{c['maker']}の{c['minutes']}分の作品です。熟女のジャンルが付いた作品を、順に見ていきたい人に向いています。{'甲乙丙丁戊'[i]}"} for i, c in enumerate(jk_c[:5])]
jart = good_article(theme={"genres": ["熟女"], "keywords": []}, title="熟女のジャンルってなに？本数とメーカーで見る",
                    lead=para(f"このサイトの{len(ALL)}本のうち{jk['total']}本に、熟女のジャンルが付いています。", 0) + "\n" + para("この記事では、本数の動きとメーカーを見ていきます。", 1),
                    description="熟女のジャンルが付いた作品を、このサイトの数字で見ていきます。年ごとの本数、メーカー、収録時間、レビューの数字をまとめ、最初に見る5本を選びました。どれも作品ページの数字から数えています。",
                    sections=[{"h": "熟女のジャンルってなに？", "text": para("大人の女性が出る作品に付くジャンルです。", 2) + "\n" + para("ドラマのジャンルと重なる作品もあります。", 5)},
                              {"h": "メーカーが分かれている", "text": para("いくつものメーカーが、同じように作品を出しています。", 3) + "\n" + para("出演者も、メーカーごとに分かれています。", 4)},
                              {"h": "こんな人に向いています", "text": para("大人の女性が出る作品を探している人に向いています。", 5) + "\n" + para("落ち着いた作品を見たい人にも合います。", 6)},
                              {"h": "選ぶ前に知っておきたいこと", "text": para("作品ページで、収録時間とジャンルを先に確かめておくと迷いません。", 7) + "\n" + para("レビューの件数も、あわせて見ておけます。", 0) + "\n" + para("セールの作品は、日によって入れかわります。", 1)},
                              {"h": "シリーズで見る", "text": para("同じシリーズを順に見ていく選び方もあります。", 2) + "\n" + para("シリーズの名前は、作品ページに出ています。", 3)}],
                    picks=jpicks)
r = apply({"jukujo": jart}, name="jk.json")
check("新しいテーマの記事も書き込める（theme を入れる）", r.returncode == 0 and json.loads(yomi_text())["articles"]["jukujo"]["theme"] == {"genres": ["熟女"], "keywords": []}
      and "years" not in json.loads(yomi_text())["articles"]["jukujo"], r.stdout + r.stderr)
r = apply({"ai-remaster": good_article()}, name="ai2.json")
check("記事は slug の順に並ぶ（2本目を足しても、前の記事はそのまま）", r.returncode == 0 and list(json.loads(yomi_text())["articles"]) == ["ai-remaster", "jukujo"], r.stdout)

print("\n■ apply が断るもの（1件でも問題があれば何も書かない）")
fresh()
apply({"ai-remaster": good_article()}, name="base.json")
base = yomi_text()
g = good_article()


def rejected(label, articles, expect=None, today=TODAY):
    r = apply(articles, today=today, name="bad.json")
    msg = r.stdout + r.stderr
    ok = r.returncode != 0 and yomi_text() == base and (expect is None or expect in msg)
    check(label, ok, f"終了コード{r.returncode} / 変更なし={yomi_text() == base} / {msg[:300]}")


def sec(i, **kw):
    s = [dict(x) for x in g["sections"]]
    s[i].update(kw)
    return s


rejected("facts にない数字（9,999本）", {"ai-remaster": good_article(lead=g["lead"].replace(f"{len(ALL)}本", "9,999本"))}, "facts にない数字")
rejected("facts にない数字（★の平均 4.9）", {"ai-remaster": good_article(sections=sec(3, text=g["sections"][3]["text"].replace("4.3", "4.9")))}, "facts にない数字")
rejected("理由に、その作品に無い収録時間（999分）", {"ai-remaster": good_article(picks=[dict(g["picks"][0], why=g["picks"][0]["why"].replace("300分", "999分"))] + g["picks"][1:])}, "facts にない数字")
rejected("1段落に数字が4つ以上", {"ai-remaster": good_article(sections=sec(3, text="収録時間の真ん中の値は125分、★の平均は4.3、件数は40件、サイト全体は" + str(site_avg) + "です。" + FILL[0] + FILL[1]))}, "数字が")
rejected("AIの文章によく出る言い方（おすすめ）", {"ai-remaster": good_article(lead=g["lead"].replace("見ていきます。", "見ていきます。おすすめです。"))}, "AIの文章によく出る")
rejected("自分の体験の言い方（私・見てみた）", {"ai-remaster": good_article(sections=sec(0, text=g["sections"][0]["text"] + "私も見てみたところ、きれいでした。"))}, "自分の体験")
rejected("決まり文句の問いかけ（〜と思ったことはありませんか）", {"ai-remaster": good_article(lead=g["lead"].replace("最近、", "古い作品をきれいに見たいと思ったことはありませんか。最近、"))}, "自分の体験")
rejected("直接的な言葉", {"ai-remaster": good_article(sections=sec(2, text=g["sections"][2]["text"] + "中出しの場面もあります。"))}, "使えない言葉")
rejected("未成年を連想させる言葉", {"ai-remaster": good_article(sections=sec(2, text=g["sections"][2]["text"] + "少女のような雰囲気です。"))}, "使えない言葉")
rejected("確かめられない評価（話題・大人気）", {"ai-remaster": good_article(sections=sec(2, text=g["sections"][2]["text"] + "話題の大人気シリーズです。"))}, "確かめられない評価")
rejected("「今月」のような古くなる言い方", {"ai-remaster": good_article(sections=sec(1, text=g["sections"][1]["text"] + "今月も出ています。"))}, "古くなる")
rejected("画面に出さない「AIによる」の言い回し", {"ai-remaster": good_article(sections=sec(0, text=g["sections"][0]["text"] + "AIによる高画質化です。"))}, "AI")
rejected("絵文字", {"ai-remaster": good_article(title=g["title"] + "😊")}, "絵文字")
rejected("作品の題の言葉を10文字以上そのまま写した", {"ai-remaster": good_article(sections=sec(2, text=g["sections"][2]["text"] + "夜明けの港町で待ちわびる物語のような作品もあります。"))}, "題の言葉")
rejected("最初に見る作品が4本", {"ai-remaster": good_article(picks=g["picks"][:4])}, "ちょうど5本")
rejected("最初に見る作品が6本", {"ai-remaster": good_article(picks=g["picks"] + [{"cid": "abc00003ai", "why": "メーカーAの90分の作品で、葵さんと彩さんが出演しています。短めの作品を見たい人に向いています。"}])}, "ちょうど5本")
rejected("外す作品（外す題の言葉の入った題）は選べない", {"ai-remaster": good_article(picks=g["picks"][:4] + [{"cid": "xyz00010", "why": "メーカーAの115分の作品で、花子さんが出演しています。短めの作品を見たい人に向いています。"}])}, "選べない作品")
rejected("外す作品（未成年を連想させる題）は選べない", {"ai-remaster": good_article(picks=g["picks"][:4] + [{"cid": "abc00011ai", "why": "メーカーBの作品で、葵さんが出演しています。出演者の作品をまとめて見たい人に向いています。"}])}, "選べない作品")
rejected("予約の作品（candidates に無い）は選べない", {"ai-remaster": good_article(picks=g["picks"][:4] + [{"cid": "abc00012ai", "why": "メーカーDの作品で、桜さんが出演しています。新しい作品を待っている人に向いています。"}])}, "candidates にありません")
rejected("cid の重複", {"ai-remaster": good_article(picks=g["picks"][:4] + [dict(g["picks"][0], why=g["picks"][4]["why"])])}, "重複")
rejected("理由が短い", {"ai-remaster": good_article(picks=g["picks"][:4] + [dict(g["picks"][4], why="短い理由です。人に向いています。")])}, "文字数")
rejected("理由が長い", {"ai-remaster": good_article(picks=g["picks"][:4] + [dict(g["picks"][4], why=g["picks"][4]["why"] * 2)])}, "文字数")
rejected("理由に、どんな人に向くかが無い", {"ai-remaster": good_article(picks=g["picks"][:4] + [dict(g["picks"][4], why="メーカーCの140分のドラマもので、月さんが出演しています。落ち着いた物語の作品として並べました。")])}, "どんな人に向くか")
rejected("同じ理由の使い回し", {"ai-remaster": good_article(picks=g["picks"][:4] + [dict(g["picks"][4], why=g["picks"][3]["why"])])}, "同じ文章")
rejected("題が長すぎる（41文字）", {"ai-remaster": good_article(title="あ" * 41)}, "文字数")
rejected("説明文が短い", {"ai-remaster": good_article(description="AIリマスター版の記事です。")}, "文字数")
rejected("導入文が1段落", {"ai-remaster": good_article(lead=g["lead"].replace("\n", ""))}, "2つの段落")
rejected("導入文が3段落", {"ai-remaster": good_article(lead=g["lead"] + "\n" + para("もう1つ段落を足しました。", 4))}, "2つの段落")
rejected("節が3つ", {"ai-remaster": good_article(sections=g["sections"][:3])}, "4〜6個")
rejected("節が7つ", {"ai-remaster": good_article(sections=g["sections"] + [dict(g["sections"][0], text=para("足した節です。", i)) for i in range(2)])}, "4〜6個")
rejected("節の本文が4段落", {"ai-remaster": good_article(sections=sec(0, text=g["sections"][0]["text"] + "\n" + para("三つめの段落です。", 5) + "\n" + para("四つめの段落です。", 6)))}, "1〜3段落")
rejected("本文の合計が短い（2,000文字に足りない）", {"ai-remaster": good_article(sections=[dict(s, text=s["text"].split("\n")[0]) for s in g["sections"]])}, "合計が")
rejected("本文の合計が長い（3,000文字をこえる）", {"ai-remaster": good_article(sections=[dict(s, text=s["text"] + "\n" + para("段落を足しました。", i) + para("さらに足しました。", i + 1)) for i, s in enumerate(g["sections"])])}, "合計が")
rejected("chart は years だけ", {"ai-remaster": good_article(sections=sec(2, chart="makers"))}, "years")
rejected("chart: years は1つの節だけ", {"ai-remaster": good_article(sections=sec(2, chart="years"))}, "1つの節だけ")
rejected("同じ段落が2回", {"ai-remaster": good_article(sections=sec(4, text=g["sections"][3]["text"]))}, "同じ段落")
rejected("知らない項目", {"ai-remaster": good_article(note="x")}, "知らない項目")
rejected("新しい slug で theme が無い", {"new-one": good_article()}, "theme")
rejected("読み物にしないテーマ（未成年を連想させるジャンル）", {"school": good_article(theme={"genres": ["女子校生"], "keywords": []})}, "読み物にしません")
rejected("slug の形が違う", {"AI_Remaster": good_article()}, "slug")
rejected("記事の形が違う（リスト）", [good_article()], "形")
rejected("良い記事と悪い記事が混ざっていたら、良いほうも書かない", {"ai-remaster": good_article(), "jukujo": good_article(theme={"genres": ["熟女"], "keywords": []}, picks=g["picks"])}, "candidates にありません")

print("\n■ 数字の点検で、うっかり断らないもの")
ok_nums = good_article(sections=sec(0, text=g["sections"][0]["text"] + "VRや8K、4Kのような英数字は数字として数えません。"),
                       lead=g["lead"].replace(f"このサイトの{len(ALL)}本", f"このサイトの約{round(len(ALL), -2):,}本"))
r = apply({"ai-remaster": ok_nums}, "--dry-run", name="ok1.json")
check("VR・8K のような英数字・「約」のあとの丸めた数（約400本）は通る", r.returncode == 0, r.stdout + r.stderr)
pct = good_article(sections=sec(1, text=g["sections"][1]["text"].replace("2026年10月は4本で", f"2026年10月は4本で、{oct_['pct']}%にあたり")))
r = apply({"ai-remaster": pct}, "--dry-run", name="ok2.json")
check("facts の % の数字は通る", r.returncode == 0, r.stdout + r.stderr)

print("\n■ themes（毎週の予約タスク用。別名 candidates）")
fresh()
t = themes()
check("はじめの4本のテーマで、まだ書いていないもの（本数と選べる本数）", [b["slug"] for b in t["builtin"]] == ["hard", "gensaku", "ai-remaster", "vr"]
      and next(b for b in t["builtin"] if b["slug"] == "ai-remaster")["total"] == 12 and next(b for b in t["builtin"] if b["slug"] == "ai-remaster")["pickable"] == 9, t["builtin"])
names = [p["genres"][0] for p in t["new"]]
check("新しいテーマの候補: 100本以上のジャンル（未成年を連想させる・行為のジャンル・中身を表さないジャンルは出さない）",
      "熟女" in names and "人妻・主婦" in names and "お姉さん" in names and not ({"女子校生", "騎乗位", "ハイビジョン"} & set(names)), names)
check("候補の形: genres・keywords・total・pickable（熟女は120本＋AIリマスターの2本）", t["new"][0] == {"genres": ["熟女"], "keywords": [], "total": 122, "pickable": 122}, t["new"][0])
check("書き直す記事はまだ無い", t["rewrite"] == [])
check("candidates は themes の別名", themes(cmd="candidates") == t)
r1 = apply({"jukujo": jart, "ai-remaster": good_article()}, name="two.json")
aged = json.loads(yomi_text())   # 書いてから日がたった記事（テストの中の作業用のファイルだけ、確かめた日を前にずらす）
aged["articles"]["jukujo"]["checked"] = "2026-07-01"
aged["articles"]["ai-remaster"]["checked"] = "2026-09-01"
write_json(YOMI, aged)
t2 = themes()
names2 = [p["genres"][0] for p in t2["new"]]
check("書いたテーマ・ほとんど重なるジャンル（お姉さんは熟女の中）は候補から外す", "熟女" not in names2 and "お姉さん" not in names2 and "人妻・主婦" in names2, names2)
check("書いたはじめのテーマは builtin から外す", "ai-remaster" not in [b["slug"] for b in t2["builtin"]])
check("確かめた日から90日をすぎた記事は、書き直す記事に出る（古い順）", [x["slug"] for x in t2["rewrite"]] == ["jukujo"] and t2["rewrite"][0]["days"] == 119
      and t2["rewrite"][0]["checked"] == "2026-07-01", t2["rewrite"])

print("\n■ 保存データが壊れているとき")
fresh()
open(YOMI, "w", encoding="utf-8").write('{"articles": []}')
r = apply({"ai-remaster": good_article()}, name="g2.json")
check("読み物のデータの形が違えば、書き込まずに止まる", r.returncode != 0 and yomi_text() == '{"articles": []}', r.stdout + r.stderr)
fresh()
open(DATA, "w", encoding="utf-8").write("{壊れている")
check("作品データが壊れていたら list も止まる", listing("--slug", "ai-remaster")[1].returncode != 0)
check("apply も止まる", apply({"ai-remaster": good_article()}, name="g3.json").returncode != 0 and yomi_text() is None)

print("\n■ ソースの安全チェック")
src = open(SCRIPT, encoding="utf-8").read()
check("標準ライブラリだけを使う（pip不要）", not any(l.startswith(("import requests", "from requests", "import anthropic")) for l in src.splitlines()))
check("外す題の言葉の一覧はスクリプトに書かない（yomimono-exclude.json だけに置く）", '"援交"' not in src and '"盗撮"' not in src)

shutil.rmtree(tmp)
failed = [n for n, ok in results if not ok]
print(f"\n=== {len(results) - len(failed)}/{len(results)} 合格 ===")
if failed:
    print("失敗:", failed)
    sys.exit(1)
