"""所属事務所の公式サイトからイベント情報を集める道具（scripts/agency_events.py）のテスト。実行: python3 tests/test_events.py
（ネットには出ない。ページの読み込みは、固定の文字で差し替える。名前は、どれも作った名前）"""
import contextlib
import io
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import agency_events as E  # noqa: E402

A = E.A
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


TODAY = "2026-10-05"

print("■ 日付・時刻・種類")
check("年のある日付と、すぐ後ろの時刻", E.find_date("2026年10月31日（土）12:00〜仙台", TODAY) == ("2026-10-31", "12:00"), E.find_date("2026年10月31日（土）12:00〜仙台", TODAY))
check("「2026/9/19(土) 10:30 〜」の形", E.find_date("2026/9/19(土) 10:30 〜", TODAY) == ("2026-09-19", "10:30"))
check("年の無い「10/1（木）18:00～」は、きょうにいちばん近い年", E.find_date("【振替】10/1（木）18:00～イベント", TODAY) == ("2026-10-01", "18:00"))
check("年の無い月日は、記事を出した日にいちばん近い年（12月の記事の「1/10(土)」は次の年）", E.find_date("1/10(土) 撮影会", "2026-12-20") == ("2027-01-10", ""))
check("「10月3日」の形・時刻が無ければ空", E.find_date("10月3日 来店", TODAY) == ("2026-10-03", ""))
check("曜日の無い「1/2」や、ありえない日付は日付にしない", E.find_date("1/2の確率", TODAY) == ("", "") and E.find_date("2026年2月30日", TODAY) == ("", ""))
check("種類は見出しの言葉から（サインと撮影の両方・来店・発売記念・当たらなければイベント）",
      [E.kind_of(t) for t in ["サイン・撮影会＠店", "個人撮影会(名古屋)", "ウエスタン店来店", "S1リリースイベント！", "6周年記念オフ会", "イベント開催！"]]
      == ["サイン・撮影会", "撮影会", "来店イベント", "発売記念イベント", "オフ会", "イベント"])

print("\n■ 見出しの中の名前（所属の人だけ・前後が区切られた形だけ）")
ROSTER = ["架空ゆめか", "見本はるな（見本はる）", "空ゆめか", "ゆめ", "めぐり"]
check("名前＋敬称・名前＋空白", E.names_in_title("10/3(土) 架空ゆめかちゃんイベント", ROSTER) == ["架空ゆめか"] and E.names_in_title("見本はるな サイン会", ROSTER) == ["見本はるな（見本はる）"])
check("かっこの中の前の名前では合わせない", E.names_in_title("見本はる 撮影会", ROSTER) == [])
check("長い名前に重なる短い名前は合わせない・2文字の名前は合わせない", E.names_in_title("架空ゆめか 撮影会", ROSTER) == ["架空ゆめか"])
check("名前の後ろに、ほかの言葉のかな・漢字が続くときは合わせない", E.names_in_title("架空ゆめかこ撮影会", ROSTER) == [] and E.names_in_title("めぐり逢いの夜", ROSTER) == [])
check("名前の前に、ほかの言葉の漢字が続くときは合わせない（「専属女優」などの言葉の後ろは合わせる）",
      E.names_in_title("新架空ゆめか", ["架空ゆめか"]) == [] and E.names_in_title("専属女優架空ゆめか来店", ["架空ゆめか"]) == ["架空ゆめか"])
check("見出しの名前に空白があっても合わせる・2人とも", E.names_in_title("架空 ゆめか＆見本はるな 撮影会", ROSTER) == ["架空ゆめか", "見本はるな（見本はる）"])

print("\n■ 事務所ごとの読み取り")
TP = '''<div class="p-schedule__list-heading">2026年10月</div>
<article class="p-schedule__list-item"><a href="https://www.av-event.jp/event/1/" target="_blank"><div class="p-schedule__list-item-inner">
<span class="p-schedule__categpry p-schedule__categpry--event">イベント</span>
<h3 class="p-schedule__list-item-title">【延期イベント振替日】10/10（土）18:00～S1架空ゆめかちゃんS1リリースイベント！</h3>
<div class="p-schedule__meta-item"><div class="p-schedule__meta-item-heading">日付</div><div class="p-schedule__meta-item-description">2026年10月10日(土) 18:00～</div></div>
<div class="p-schedule__meta-item"><div class="p-schedule__meta-item-heading">場所</div><div class="p-schedule__meta-item-description">見本ショップ秋葉原</div></div>
</div></a></article>
<article class="p-schedule__list-item"><a href="https://www.t-powers.co.jp/event/2/" target="_slef">
<span class="p-schedule__categpry p-schedule__categpry--media">メディア</span>
<h3 class="p-schedule__list-item-title">10/12(月) 見本はるな 見本店来店</h3>
<div class="p-schedule__meta-item-heading">日付</div><div class="p-schedule__meta-item-description">2026年10月12日(月) 10:00～</div>
<div class="p-schedule__meta-item-heading">場所</div><div class="p-schedule__meta-item-description">見本店</div></a></article>
<article class="p-schedule__list-item"><a href="https://www.t-powers.co.jp/event/3/">
<span class="p-schedule__categpry p-schedule__categpry--media">メディア</span>
<h3 class="p-schedule__list-item-title">見本はるな 雑誌に登場</h3>
<div class="p-schedule__meta-item-heading">日付</div><div class="p-schedule__meta-item-description">2026年10月20日(火)</div></a></article>'''
got = E.parse_tpowers(TP, "https://www.t-powers.co.jp/event/")
check("ティーパワーズ: 1件ずつ、見出し・リンク・日付・場所・メディアかどうか",
      [(g["title"][:12], g["url"], g["date_text"], g["place"], g["media"]) for g in got] == [
          ("【延期イベント振替日】1", "https://www.av-event.jp/event/1/", "2026年10月10日(土) 18:00～", "見本ショップ秋葉原", False),
          ("10/12(月) 見本は", "https://www.t-powers.co.jp/event/2/", "2026年10月12日(月) 10:00～", "見本店", True),
          ("見本はるな 雑誌に登場", "https://www.t-powers.co.jp/event/3/", "2026年10月20日(火)", "", True)], got)
CAP = '''<ul><li class="cat-item cat-item-6"><a href="https://capsule.bz/category/event/">EVENT</a> </li></ul>
<ul class="slide-cnt"><li><p class="cat"><a href="https://capsule.bz/category/event/" rel="category tag">EVENT</a></p>
<div class="info"><p class="title"><a href="https://capsule.bz/20261031a/">【架空ゆめか】2026年10月31日（土）12:00〜仙台イベント【見本BOX仙台店】</a></p>
<div class="tag"><a href="https://capsule.bz/tag/x/" rel="tag">架空ゆめか</a></div></div></li></ul>
<li><p class="cat"><a href="https://capsule.bz/category/event/" rel="category tag">EVENT</a></p>
<div class="info"><p class="title"><a href="https://capsule.bz/20261031a/">【架空ゆめか】2026年10月31日（土）12:00〜仙台イベント【見本BOX仙台店】</a></p></div></li>
<li><p class="cat"><a href="https://capsule.bz/category/news/" rel="category tag">NEWS</a></p>
<div class="info"><p class="title"><a href="https://capsule.bz/news1/">お知らせ</a></p></div></li>'''
got = E.parse_capsule(CAP, "https://capsule.bz/category/event/")
check("カプセル: イベントの記事だけ・同じ記事は1つ・名前はタグ・会場は見出しの最後の【】",
      len(got) == 1 and got[0]["names"] == ["架空ゆめか"] and got[0]["place"] == "見本BOX仙台店" and got[0]["url"] == "https://capsule.bz/20261031a/", got)
RSS = '''<rss><channel><item><title>見本はるな個人撮影会(名古屋)</title><link>http://www.style-1.jp/2026/10/01/a/</link>
<pubDate>Thu, 01 Oct 2026 04:11:21 +0000</pubDate><category><![CDATA[イベント情報]]></category><category><![CDATA[女優]]></category><category><![CDATA[見本はるな]]></category>
<description><![CDATA[<p>場所 見本スタジオ 日時 2026/10/17(土) 10:30 〜 女優名 見本はるな 住所 どこか tel 000 URL https://www ...</p>]]></description></item>
<item><title>新しい女優が入りました</title><link>http://www.style-1.jp/2026/10/01/b/</link><category><![CDATA[お知らせ]]></category></item></channel></rss>'''
got = E.parse_rss(RSS, "http://www.style-1.jp/feed/")
ev = [g for g in got if g]
check("エスフラート（RSS）: 記事は全部数えて、イベント情報のカテゴリだけ読む・場所・日時・名前（カテゴリと女優名）・記事を出した日",
      len(got) == 2 and len(ev) == 1 and ev[0]["place"] == "見本スタジオ" and ev[0]["date_text"].startswith("2026/10/17(土) 10:30")
      and ev[0]["names"] == ["見本はるな", "見本はるな"] and ev[0]["base"] == "2026-10-01", got)
LIFE = '''<div class="blog"><div class="blog_l"><a href="https://life-promotion.com/blog/event/a/"><img src="x.webp"></a></div>
<div class="blog_r"><p class="event">イベント情報</p><p class="date">2026.10.01</p>
<h2><a href="https://life-promotion.com/blog/event/a/">10/18（日）架空ゆめかちゃんイベントin岡山</a></h2>
<p>恒例の日がやってまいりました！ 開催情報1 開催日時 2026/10/18(日) 11:30 〜 会場情報 見本まっくす 岡山店 住所 どこか&#8230;</p></div></div>
<div class="blog"><div class="blog_r"><p class="date">2026.10.02</p><h2><a href="https://life-promotion.com/blog/event/b/">10/25（日）姫、久、水の撮影会！！</a></h2><p>本文</p></div></div>'''
got = E.parse_life(LIFE, "https://life-promotion.com/blog/event/")
check("ライフ: 見出し・リンク・開催日時・会場情報（後ろに次の項目があるときだけ）・記事を出した日",
      [(g["title"], g["date_text"], g["place"], g["base"]) for g in got] == [
          ("10/18（日）架空ゆめかちゃんイベントin岡山", "2026/10/18(日) 11:30", "見本まっくす 岡山店", "2026-10-01"),
          ("10/25（日）姫、久、水の撮影会！！", "", "", "2026-10-02")], got)

print("\n■ 保存する形に（採らないイベント）")
with tempfile.TemporaryDirectory() as tmp:
    json.dump({"rows": [{"id": 1, "name": "架空ゆめか"}, {"id": 2, "name": "見本はるな（見本はる）"}, {"id": 3, "name": "同名みき"}, {"id": 4, "name": "同名みき"}]},
              open(os.path.join(tmp, "actress_directory.json"), "w"))
    TABLE = A.fanza_names(tmp)
ROSTER_T = ["架空ゆめか", "見本はるな（見本はる）"]


def entry(**kw):
    return {"title": "", "url": "https://www.t-powers.co.jp/event/9/", "date_text": "", "place": "", "names": [], "base": "", "media": False, **kw}


row, why = E.make_row(E.parse_tpowers(TP, "https://www.t-powers.co.jp/event/")[0], "tpowers", ROSTER_T, TABLE, TODAY)
check("見出しの中の所属の人・日付と時刻は日付の欄から・種類・見出しは日付と時刻を外す・事務所のサイトの外へのリンクは、事務所の一覧のページに",
      row == {"date": "2026-10-10", "time": "18:00", "names": ["架空ゆめか"], "agency": "tpowers", "kind": "発売記念イベント",
              "title": "【延期イベント振替日】S1架空ゆめかちゃんS1リリースイベント！", "place": "見本ショップ秋葉原", "url": "https://www.t-powers.co.jp/event/", "seen": TODAY}, row)
row, why = E.make_row(E.parse_capsule(CAP, "https://capsule.bz/category/event/")[0], "capsule", [], TABLE, TODAY)
check("タグの名前は、FANZA の名前と完全に同じ1人のとき・名前と会場だけの【】は見出しから外す",
      row and row["names"] == ["架空ゆめか"] and row["title"] == "仙台イベント" and row["place"] == "見本BOX仙台店" and row["url"] == "https://capsule.bz/20261031a/", row)
check("メディアの情報は、会場があるときだけ（来店）", E.make_row(E.parse_tpowers(TP, "https://www.t-powers.co.jp/event/")[1], "tpowers", ROSTER_T, TABLE, TODAY)[0]["kind"] == "来店イベント"
      and E.make_row(E.parse_tpowers(TP, "https://www.t-powers.co.jp/event/")[2], "tpowers", ROSTER_T, TABLE, TODAY) == (None, "会場の無いメディアの情報"))
cases = [
    ("中止", entry(title="【中止】10/10(土) 架空ゆめか 撮影会"), "中止・延期"),
    ("延期（振替の日が無い）", entry(title="【延期】10/10(土) 架空ゆめか 撮影会"), "中止・延期"),
    ("未成年を連想させる見出し", entry(title="10/10(土) 架空ゆめか 制服撮影会"), "見出しに未成年を連想させる言葉"),
    ("日付が無い", entry(title="架空ゆめか 撮影会"), "日付が読めない"),
    ("すぎた日", entry(title="10/1(木) 架空ゆめか 撮影会"), "期間の外"),
    ("60日より先", entry(title="2026年12月20日(日) 架空ゆめか 撮影会"), "期間の外"),
    ("名前が結びつかない（所属に無い・同じ名前が2人）", entry(title="10/10(土) 知らないひと 撮影会", names=["同名みき"]), "FANZAの名前と結びつく人がいない"),
]
for label, e, want in cases:
    got = E.make_row(e, "tpowers", ROSTER_T, TABLE, TODAY)
    check(f"採らない: {label}", got == (None, want), got)
row, _ = E.make_row(entry(title="10/10(土) 架空ゆめか エロ撮影会", place="見本スタジオ"), "tpowers", ROSTER_T, TABLE, TODAY)
check("行為などの言葉がある見出しは、見出しだけ出さない（種類・会場は出す）", row and "title" not in row and row["kind"] == "撮影会" and row["place"] == "見本スタジオ", row)
row, _ = E.make_row(entry(title="10/10(土) 架空ゆめか サイン会＠見本ショップ", place="見本ショップ"), "tpowers", ROSTER_T, TABLE, TODAY)
check("「＠会場」は見出しから外す", row["title"] == "架空ゆめか サイン会", row)
row, _ = E.make_row(entry(title="10/10(土) 架空ゆめか 撮影会", place="とても長い会場の名前とても長い会場の名前とても長い会場の名前とても長い"), "tpowers", ROSTER_T, TABLE, TODAY)
check("長すぎる会場の名前は保存しない", row and "place" not in row, row)
row, _ = E.make_row(entry(title="10/10(土) 架空ゆめか 撮影会", place="東京都 千代田区見本 3-8-15 見本ビル"), "tpowers", ROSTER_T, TABLE, TODAY)
check("住所らしい会場は保存しない", row and "place" not in row, row)
check("見出しから、続きの日・残った曜日・年・「12時~」の形の時刻も外す",
      [E.clean_title(t, ["架空ゆめか"], "") for t in [
          "10/16(金)～18(日) 架空ゆめか 写真展「見本」", "12時~＆17時～架空ゆめかイベントin見本店", "【見本】10/17,18日（土,日） 専属 架空ゆめか 撮影会イベント",
          "【架空ゆめか】2026年10月17日(土)岡山・18日(日)神戸イベント", "【見本】10/10（土曜日）架空ゆめか イベント", "２０２６年 架空ゆめかオフ会開催決定！！"]]
      == ["架空ゆめか 写真展「見本」", "架空ゆめかイベントin見本店", "【見本】専属 架空ゆめか 撮影会イベント", "岡山 神戸イベント", "【見本】架空ゆめか イベント", "架空ゆめかオフ会開催決定！！"])
check("「00:00」は時刻が決まっていない印として、時刻にしない", E.find_date("2026年10月24日(土) 00:00～", TODAY) == ("2026-10-24", ""))
check("「さん」の後ろの名前も合わせる（共演）・見出しに出てくる順", E.names_in_title("見本はるなさん架空ゆめかさん共演イベント！", ROSTER) == ["見本はるな（見本はる）", "架空ゆめか"])
check("くだけた性的な言い方の見出しも出さない", E.title_problem("架空ゆめかと呑みたい！夜のオカズになる話") == "hide" and E.title_problem("架空ゆめか 撮影会") == "")
got = E.parse_capsule(CAP.replace("見本BOX仙台店", "見本メーカー"), "https://capsule.bz/category/event/")
check("カプセル: 最後の【】が会場らしい言葉でなければ、会場にしない（メーカーの名前のことがある）", got[0]["place"] == "", got)
check("形の違う行は保存しない（事務所のサイトの外のURL・種類の一覧に無い・日付が変）",
      E.clean_row({"date": "2026-10-10", "names": ["架空ゆめか"], "agency": "tpowers", "kind": "イベント", "url": "https://example.com/", "seen": TODAY}) is None
      and E.clean_row({"date": "2026-10-10", "names": ["架空ゆめか"], "agency": "tpowers", "kind": "飲み会", "url": "https://www.t-powers.co.jp/event/", "seen": TODAY}) is None
      and E.clean_row({"date": "2026-02-30", "names": ["架空ゆめか"], "agency": "tpowers", "kind": "イベント", "url": "https://www.t-powers.co.jp/event/", "seen": TODAY}) is None
      and E.clean_row({"date": "2026-10-10", "names": ["架空ゆめか"], "agency": "mines", "kind": "イベント", "url": "https://mines-pro.jp/", "seen": TODAY}) is None)

print("\n■ 保存するデータ（前の情報を壊さない）")


def mk(day, name, key="tpowers", url=None, **kw):
    site = A.SITES[[s["key"] for s in A.SITES].index(key)]
    return {"date": day, "names": [name], "agency": key, "kind": "イベント", "url": url or site["url"], "seen": "2026-10-01", **kw}


prev = {"updated": "2026-10-04", "sites": [{"key": "tpowers", "checked": "2026-10-04", "found": 5}, {"key": "capsule", "checked": "2026-10-03", "found": 9}],
        "rows": [mk("2026-10-04", "架空ゆめか"), mk("2026-10-09", "架空ゆめか", time="18:00"), mk("2026-10-08", "架空ゆめか", key="capsule"),
                 mk("2026-10-03", "架空ゆめか", key="capsule"), {"date": "x"}]}
results = {"tpowers": ({"ok": True, "blocks": 3}, [mk("2026-10-20", "見本はるな（見本はる）", seen=TODAY), mk("2026-10-20", "見本はるな（見本はる）", seen=TODAY)]),
           "capsule": ({"ok": False, "blocks": 0}, []), "esflat": ({"ok": True, "blocks": 0}, [])}
data = E.build_dataset(results, prev, TODAY)
check("読めた事務所は今回の行に入れ替え・読めなかった事務所（1件も読めない所も）は前の行を残す・すぎたイベントと形の違う行は消す・同じイベントは1つ",
      [(r["date"], r["agency"]) for r in data["rows"]] == [("2026-10-08", "capsule"), ("2026-10-20", "tpowers")], data["rows"])
check("事務所ごとの、読んだ日と件数（読めなかった所は前のまま）・更新した日",
      data["sites"][:3] == [{"key": "tpowers", "checked": TODAY, "found": 3}, {"key": "capsule", "checked": "2026-10-03", "found": 9},
                            {"key": "esflat", "checked": "", "found": 0}] and data["updated"] == TODAY, data["sites"])
check("1つも読めなかったときは、更新した日を変えない", E.build_dataset({}, prev, TODAY)["updated"] == "2026-10-04")
check("並びは日付・時刻の順", [r["date"] for r in E.build_dataset({}, {"updated": "", "sites": [], "rows": [mk("2026-10-09", "架空ゆめか", time="18:00"), mk("2026-10-09", "見本はるな", time="10:00"), mk("2026-10-06", "架空ゆめか")]}, TODAY)["rows"]]
      == ["2026-10-06", "2026-10-09", "2026-10-09"])
with tempfile.TemporaryDirectory() as tmp:
    p = os.path.join(tmp, "events.json")
    E.save_dataset(data, p)
    text = open(p, encoding="utf-8").read()
    check("保存は1行に1件・読み直すと同じ", E.load_previous(p) == data and text.count("\n") == len(data["rows"]) + len(data["sites"]) + 5, text)
    open(p, "w").write('{"rows": 1}')
    try:
        E.load_previous(p)
        check("壊れたデータは読まない（上書きしない）", False)
    except ValueError:
        check("壊れたデータは読まない（上書きしない）", True)

print("\n■ まとめて動かす（ページの読み込みは固定の文字）")
with tempfile.TemporaryDirectory() as tmp:
    json.dump({"rows": [{"id": 1, "name": "架空ゆめか"}, {"id": 2, "name": "見本はるな（見本はる）"}]}, open(os.path.join(tmp, "actress_directory.json"), "w"))
    json.dump({"updated": TODAY, "sites": [], "rows": [{"name": "架空ゆめか", "agency": "tpowers", "source": "https://www.t-powers.co.jp/talent/a/", "seen": TODAY},
                                                       {"name": "見本はるな（見本はる）", "agency": "tpowers", "source": "https://www.t-powers.co.jp/talent/b/", "seen": TODAY},
                                                       {"name": "架空ゆめか", "agency": "life", "source": "https://life-promotion.com/model/a.php", "seen": TODAY}]},
              open(os.path.join(tmp, "agencies.json"), "w"))
    pages = {"https://www.t-powers.co.jp/event/": TP, "https://capsule.bz/category/event/": CAP, "http://www.style-1.jp/feed/": RSS}
    saved = (A.DATA_DIR, A.AGENCY_PATH, A.fetch_raw, A.jst_today, E.EVENTS_PATH)

    def fake_fetch(url, check_robots=True):
        if url not in pages:
            raise OSError("読めない")
        return pages[url]

    A.DATA_DIR, A.AGENCY_PATH, A.fetch_raw, A.jst_today, E.EVENTS_PATH = tmp, os.path.join(tmp, "agencies.json"), fake_fetch, lambda: TODAY, os.path.join(tmp, "events.json")
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = E.main(["x", "--update", "--report", os.path.join(tmp, "report.json")])
        data = json.load(open(os.path.join(tmp, "events.json"), encoding="utf-8"))
        report = json.load(open(os.path.join(tmp, "report.json"), encoding="utf-8"))
    finally:
        A.DATA_DIR, A.AGENCY_PATH, A.fetch_raw, A.jst_today, E.EVENTS_PATH = saved
check("読めた事務所のイベントを保存（見出しの中の名前は、その事務所の所属の人だけ・読めない事務所があっても止まらない）",
      code == 0 and [(r["date"], r["agency"], r["names"]) for r in data["rows"]] == [
          ("2026-10-10", "tpowers", ["架空ゆめか"]), ("2026-10-12", "tpowers", ["見本はるな（見本はる）"]),
          ("2026-10-17", "esflat", ["見本はるな（見本はる）"]), ("2026-10-31", "capsule", ["架空ゆめか"])], (code, data, out.getvalue()))
check("報告には、採らなかった理由も", any(e["result"] == "会場の無いメディアの情報" for e in report["entries"]) and len(report["sites"]) == len(E.SOURCES), report)
check("事務所のキーは、所属の一覧（agency_links.SITES）にある事務所だけ", all(E.site_of(s["key"]) for s in E.SOURCES))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
