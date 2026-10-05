"""所属事務所の公式サイトから所属・SNSを集める道具（scripts/agency_links.py）のテスト。実行: python3 tests/test_agencies.py
（ネットには出ない。ページの読み込みは、固定の文字で差し替える）"""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("agency_links", os.path.join(ROOT, "scripts", "agency_links.py"))
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


SITE_T = next(s for s in A.SITES if s["key"] == "tpowers")
SITE_ALIVE = next(s for s in A.SITES if s["key"] == "alive")

print("■ ページから取り出す")
roster = '''<a href="/talent/%e8%92%bc/"><img src="a.jpg" alt="蒼乃 美月"></a>
<a href="/talent/abc/">河北 彩花</a><a href="javascript:void(0)">x</a><a href="#top">上へ</a>'''
got = A.links(roster, "https://www.t-powers.co.jp/talent/")
check("リンクは絶対URLに・文字が無ければ中の画像の alt・javascript: と # は捨てる",
      got == [("https://www.t-powers.co.jp/talent/%e8%92%bc/", "蒼乃 美月"), ("https://www.t-powers.co.jp/talent/abc/", "河北 彩花")], got)
profile = '''<h1>河北 彩花</h1><a href="https://twitter.com/Saika_Kawakita">X</a><a href="https://x.com/share?text=1">共有</a>
<a href="https://twitter.com/intent/tweet">t</a><a href="https://x.com/Saika_Kawakita">X2</a>
<a href="https://www.instagram.com/saika_kawakita__official/">IG</a><a href="https://www.instagram.com/p/abc/">投稿</a>'''
check("SNS: アカウント名だけ・共有ボタンや投稿へのリンクは除く・同じものは1つ", A.sns_links(profile, "https://x/") == (["Saika_Kawakita"], ["saika_kawakita__official"]), A.sns_links(profile, "https://x/"))
check("見出しの候補（h1・og:title・title。区切りで分ける）", A.name_candidates('<title>石川 澪 | ALIVE</title><h1>アライブ所属のモデル 石川 澪</h1>')[:3] == ["アライブ所属のモデル 石川 澪", "石川 澪", "ALIVE"], A.name_candidates('<title>石川 澪 | ALIVE</title><h1>アライブ所属のモデル 石川 澪</h1>'))
check("事務所の側の名前: 一覧の文字（うしろのローマ字は外す）",
      A.agency_name(SITE_T, "美乃すずめ Suzume Mino", []) == "美乃すずめ" and A.agency_name(SITE_T, " 河北  彩花 ", ["鹿野あも"]) == "河北 彩花")
SITE_CAPSULE = next(s for s in A.SITES if s["key"] == "capsule")
SITE_NAX = next(s for s in A.SITES if s["key"] == "nax")
SITE_DUO = next(s for s in A.SITES if s["key"] == "duo")
check("事務所の側の名前: 決まった形の一覧の文字（「（七沢みあ）AV女優」→「七沢みあ」。形が違えば名前にしない）",
      A.agency_name(SITE_CAPSULE, "（七沢みあ）AV女優", []) == "七沢みあ" and A.agency_name(SITE_CAPSULE, "七沢みあ", []) == "")
check("事務所の側の名前: 一覧が画像だけの事務所は、決まった形のページのタイトルから（うしろのローマ字は外す）",
      A.agency_name(SITE_NAX, "", ["鹿野あも"], "松永 あかり | AVプロダクション NAX(ナックス)公式") == "松永 あかり"
      and A.agency_name(SITE_DUO, "", [], "希島あいり Airi Kijima – Duo Entertainment 株式会社") == "希島あいり"
      and A.agency_name(SITE_NAX, "", [], "モデル一覧") == "")
check("事務所の側の名前: 一覧の文字がローマ字だけなら、事務所ごとの決まった見出しから（無ければ、そのまま）",
      A.agency_name(SITE_ALIVE, "MIO ISHIKAWA", ["鹿野あも", "アライブ所属のモデル 石川 澪"]) == "石川 澪" and A.agency_name(SITE_T, "MINAMO", ["鹿野あも"]) == "MINAMO")

print("\n■ FANZA の名前との照らし合わせ")
with tempfile.TemporaryDirectory() as tmp:
    json.dump({"rows": [{"id": 1, "name": "河北彩花（河北彩伽）"}, {"id": 2, "name": "彩花"}, {"id": 3, "name": "同名さん"}, {"id": 4, "name": "同名さん"}, {"id": 5, "name": "夏川未来（小春）"}]},
              open(os.path.join(tmp, "actress_directory.json"), "w"))
    json.dump({"actresses": [{"id": "6", "name": "MINAMO"}, {"id": "7", "name": "Lisa"}]}, open(os.path.join(tmp, "actresses.json"), "w"))
    json.dump([{"actress": ["作品だけ子", "彩花"]}], open(os.path.join(tmp, "new_releases.json"), "w"))
    os.makedirs(os.path.join(tmp, "catalog"))
    json.dump([{"actress": ["過去作品の人"]}], open(os.path.join(tmp, "catalog", "2026-01.json"), "w"))
    table = A.fanza_names(tmp)
look = lambda n: A.lookup(table, n)[:2]
check("名前の全体（空白・全角半角の違いは無視）が同じなら結びつく・FANZA の id も", look("河北 彩花") == ("河北彩花（河北彩伽）", "1") and look("ＭＩＮＡＭＯ") == ("MINAMO", "6"))
check("かっこの中（前の名前）では引かない（「小春」→「夏川未来（小春）」のような取り違えを防ぐ）", look("河北彩伽") == ("", "") and look("小春") == ("", ""))
check("名前の一部では引かない（「河北 彩花」は「彩花」さんにならない）", look("河北 彩花")[0] != "彩花")
check("FANZA に同じ名前が何人もいれば結びつけない", A.lookup(table, "同名さん") == ("", "", "FANZAに同じ名前が何人もいる"))
check("このサイトの作品の出演者・過去作品の出演者の名前でも引ける（id は無し）", look("作品だけ子") == ("作品だけ子", "") and look("過去作品の人") == ("過去作品の人", ""))
check("短い名前（日本語で2文字まで・ローマ字だけで4文字まで）は結びつけない", A.lookup(table, "彩花")[2] == "名前が短くて決められない" and A.lookup(table, "Lisa")[2] == "名前が短くて決められない" and A.name_ok("MINAMO") and A.name_ok("めぐり") and not A.name_ok("小春"))

pages = [
    ("https://www.t-powers.co.jp/talent/a/", "河北 彩花", [], ["Saika_Kawakita", "tpowers_office"], ["saika_ig"]),
    ("https://www.t-powers.co.jp/talent/b/", "MINAMO", [], ["M_I_N_A_M_O_", "tpowers_office", "Co_Star"], []),
    ("https://www.t-powers.co.jp/talent/c/", "知らない人", [], ["unknown_x", "tpowers_office", "co_star"], []),
]
rows = A.match_profiles(SITE_T, pages, table)
check("事務所のアカウント（どのページにもある）・2人以上のページにあるSNS（大文字小文字は同じあつかい）は外す",
      rows[0]["x"] == ["Saika_Kawakita"] and rows[1]["x"] == ["M_I_N_A_M_O_"] and rows[2]["x"] == ["unknown_x"], [r["x"] for r in rows])
check("結びついた人・結びつかない人と理由", rows[0]["fanza_name"] == "河北彩花（河北彩伽）" and rows[2]["fanza_name"] == "" and rows[2]["match"] == "FANZAの名前と合わない")

print("\n■ 一覧の読み方（プロフィールの横に全員が並ぶ事務所）")
SITE_ES = next(s for s in A.SITES if s["key"] == "esflat")
fake_pages = {
    "http://www.style-1.jp/": '<a href="/category/actress/a/">あ子さん</a><a href="/news/1/">お知らせ</a>',
    "http://www.style-1.jp/category/actress/a/": '<title>あ子さん | S</title><a href="/category/actress/a/">あ子さん</a><a href="/category/actress/b/">び子さん</a><a href="/category/actress/c/">し子さん</a><a href="https://x.com/sflirt">x</a>',
    "http://www.style-1.jp/category/actress/b/": '<a href="https://x.com/sflirt">x</a><a href="https://x.com/biko">x</a>',
    "http://www.style-1.jp/category/actress/c/": '<a href="https://x.com/sflirt">x</a>',
}
saved_fetch = A.fetch_raw
A.fetch_raw = lambda url, check_robots=True: fake_pages[url]
rep_, rows_ = A.collect_site(SITE_ES, {})
A.fetch_raw = saved_fetch
check("一覧のページの分に、最初のプロフィールのページの横の全員を足す・プロフィールの形のリンクだけ",
      rep_["found"] == 3 and rep_["read"] == 3 and [r["agency_name"] for r in rows_] == ["あ子さん", "び子さん", "し子さん"], (rep_, [r["agency_name"] for r in rows_]))
check("事務所のアカウント（どのページにもある）は外し、本人のアカウントだけ残す", [r["x"] for r in rows_] == [[], ["biko"], []], [r["x"] for r in rows_])

print("\n■ 相手のサイトに負担をかけない（同じサイトへは間をあける・事務所どうしは同時に）")
import time as _time
saved_urlopen, saved_interval = A.urllib.request.urlopen, A.INTERVAL_SEC


class _Res:
    headers = type("H", (), {"get_content_charset": lambda self: "utf-8"})()

    def read(self, n):
        return b"<html></html>"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


A.urllib.request.urlopen = lambda req, timeout=30: _Res()
A.INTERVAL_SEC = 0.3
A._last.clear()
t0 = _time.time()
A.fetch_raw("https://same.example/a", check_robots=False)
A.fetch_raw("https://other.example/a", check_robots=False)
t1 = _time.time()
A.fetch_raw("https://same.example/b", check_robots=False)
t2 = _time.time()
check("ちがうサイトは待たずに読む・同じサイトは間をあける", t1 - t0 < 0.25 and t2 - t1 >= 0.2, (round(t1 - t0, 2), round(t2 - t1, 2)))
A.urllib.request.urlopen, A.INTERVAL_SEC = saved_urlopen, saved_interval
A._last.clear()
print("\n■ robots.txt を守る")
saved_fetch = A.fetch_raw


def fake_robots(text=None, code=None):
    def fetch(url, check_robots=True):
        if code:
            raise A.urllib.error.HTTPError(url, code, "x", {}, None)
        return text
    return fetch


A._robots.clear()
A.fetch_raw = fake_robots("User-agent: *\nDisallow: /talent/\n")
check("robots.txt で止められているページは読まない", not A.allowed("https://example.jp/talent/a/") and A.allowed("https://example.jp/news/"))
A._robots.clear()
A.fetch_raw = fake_robots(code=404)
check("robots.txt が無い（404）ときは読んでよい", A.allowed("https://example.jp/talent/a/"))
A._robots.clear()
A.fetch_raw = fake_robots(code=403)
check("robots.txt が読めない（403 など）ときは、念のため読まない", not A.allowed("https://example.jp/talent/a/"))
A._robots.clear()
A.fetch_raw = saved_fetch

print("\n■ 保存するデータ（前の情報を壊さない）")
T = "2026-10-12"


def result(key, read, matched):
    return ({"roster_ok": True, "read": read, "found": read, "errors": []},
            [{"agency": key, "source": f"{next(s for s in A.SITES if s['key'] == key)['url']}p/{i}", "fanza_name": n, "fanza_id": "", "x": [x] if x else [], "instagram": []}
             for i, (n, x) in enumerate(matched)])


prev = {"updated": "2026-10-05", "sites": [{"key": "tpowers", "checked": "2026-10-05", "profiles": 100}, {"key": "mines", "checked": "2026-10-05", "profiles": 80}],
        "rows": [
            {"name": "移籍する人", "agency": "mines", "source": "https://mines-pro.jp/model/1", "seen": "2026-10-05"},
            {"name": "残る人", "agency": "mines", "x": "nokoru", "source": "https://mines-pro.jp/model/2", "seen": "2026-10-05"},
            {"name": "古い人", "agency": "mines", "source": "https://mines-pro.jp/model/3", "seen": "2026-08-01"},
            {"name": "辞めた人", "agency": "tpowers", "source": "https://www.t-powers.co.jp/talent/z/", "seen": "2026-10-05"},
            {"name": "悪い行", "agency": "tpowers", "source": "https://evil.example/", "seen": "2026-10-05"},
        ]}
data = A.build_dataset({"tpowers": result("tpowers", 90, [("移籍する人", "moved_x"), ("新しい人", "")]), "mines": ({"roster_ok": False, "read": 0, "found": 0, "errors": ["x"]}, [])}, prev, T)
by = {r["name"]: r for r in data["rows"]}
check("読めた事務所は今回の行に入れ替える（一覧から消えた人は消える）", "辞めた人" not in by and by["新しい人"]["agency"] == "tpowers" and by["新しい人"]["seen"] == T)
check("読めなかった事務所は前の行を残す（見かけてから30日まで）・古い行は消える", by["残る人"]["x"] == "nokoru" and by["残る人"]["seen"] == "2026-10-05" and "古い人" not in by)
check("2つの事務所にいる人は、新しく読めたほうにする（移籍）", by["移籍する人"]["agency"] == "tpowers" and by["移籍する人"]["x"] == "moved_x")
check("決まった項目だけ・出どころが事務所のサイトでない行は捨てる・アカウント名が無ければ項目ごと入れない",
      "悪い行" not in by and set(by["新しい人"]) == {"name", "agency", "source", "seen"} and data["updated"] == T)
check("事務所ごとの読めた日・人数（読めなかった事務所は前のまま）",
      [(s["key"], s["checked"], s["profiles"]) for s in data["sites"][:2]] == [("tpowers", T, 90), ("mines", "2026-10-05", 80)], data["sites"][:2])
shrink = A.build_dataset({"tpowers": result("tpowers", 30, [("新しい人", "")])}, prev, T)
check("前の半分も読めない（作り替えなど）ときは、読めなかったのと同じあつかい（前の行を残す）",
      {r["name"] for r in shrink["rows"] if r["agency"] == "tpowers"} == {"辞めた人"} and shrink["sites"][0]["checked"] == "2026-10-05")
both = A.build_dataset({"tpowers": result("tpowers", 90, [("ふたり", "a1")]), "mines": result("mines", 80, [("ふたり", "b1")])}, prev, T)
check("今回読めた2つの事務所に同じ人がいたら、決められないので出さない", "ふたり" not in {r["name"] for r in both["rows"]})
check("同じ事務所の2つのプロフィールが同じ人に結びついたら、出さない",
      "同じ人" not in {r["name"] for r in A.build_dataset({"tpowers": result("tpowers", 90, [("同じ人", "a"), ("同じ人", "b")])}, prev, T)["rows"]})
bad = A.clean_row({"name": "x", "agency": "tpowers", "x": "bad handle!", "instagram": "../evil", "id": "abc", "source": "https://www.t-powers.co.jp/talent/x/", "seen": T})
check("アカウント名・id の形が違えば入れない", bad == {"name": "x", "agency": "tpowers", "source": "https://www.t-powers.co.jp/talent/x/", "seen": T}, bad)
text = A.dump_dataset(data)
check("保存の形: 正しいJSON・1行に1人", json.loads(text) == data and text.count("\n") >= len(data["rows"]) + 4)

print("\n■ 動かし方（7日ごと・壊れたファイルは上書きしない）")
def run(argv):
    """main を、画面に出す文字をしまって動かす"""
    with contextlib.redirect_stdout(io.StringIO()):
        return A.main(argv)


with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "agencies.json")
    A.AGENCY_PATH = path
    called = []
    saved_collect = A.collect_site
    A.collect_site = lambda site, table: (called.append(site["key"]) or ({"roster_ok": False, "read": 0, "found": 0, "errors": []}, []))
    A.jst_today = lambda: "2026-10-08"
    open(path, "w").write(A.dump_dataset({"updated": "2026-10-05", "sites": [], "rows": []}))
    check("前に集めてから7日たっていなければ、何もしない", run(["--update"]) == 0 and called == [])
    check("--force なら、すぐ集め直す（全部の事務所）・1つも読めなければ、集め直した日にしない（次の日にまた試す）",
          run(["--update", "--force"]) == 0 and sorted(called) == sorted(s["key"] for s in A.SITES) and json.load(open(path))["updated"] == "2026-10-05")
    A.collect_site = lambda site, table: ({"roster_ok": True, "read": 1, "found": 1, "errors": []}, [])
    check("読めた事務所があれば、集め直した日になる", run(["--update", "--force"]) == 0 and json.load(open(path))["updated"] == "2026-10-08")
    open(path, "w").write("{壊れた")
    check("ファイルが壊れていたら、上書きしないで止まる", run(["--update", "--force"]) == 1 and open(path).read() == "{壊れた")
    check("--update が無ければ、使い方を出すだけ", run([]) == 2)
    open(path, "w").write(A.dump_dataset({"updated": "2026-10-01", "sites": [{"key": "mines", "checked": "2026-10-01", "profiles": 10}],
                                          "rows": [{"name": "残る人", "agency": "mines", "source": "https://mines-pro.jp/model/1", "seen": "2026-10-01"}]}))
    A.collect_site = lambda site, table: (_ for _ in ()).throw(RuntimeError("こわれた")) if site["key"] == "mines" else ({"roster_ok": True, "read": 1, "found": 1, "errors": []}, [])
    check("1つの事務所で思わぬ失敗があっても、止まらずに保存する（その事務所は前の情報を残す）",
          run(["--update", "--force"]) == 0 and [r["name"] for r in json.load(open(path))["rows"]] == ["残る人"])
    A.collect_site = saved_collect

print("\n■ 保存されているデータ（site/src/data/agencies.json）")
real = os.path.join(ROOT, "site", "src", "data", "agencies.json")
if os.path.exists(real):
    data = json.load(open(real, encoding="utf-8"))
    rows = data.get("rows", [])
    check("決まった項目だけ・形が正しい（clean_row を通しても変わらない）", all(A.clean_row(r) == r for r in rows), [r for r in rows if A.clean_row(r) != r][:2])
    check("同じ人は1行だけ", len({r["name"] for r in rows}) == len(rows))
    check("事務所は決まった5つだけ・生年月日などの項目は無い", {r["agency"] for r in rows} <= {s["key"] for s in A.SITES} and not any(k in r for r in rows for k in ("birthday", "birth", "pref", "blood")))

print(f"\n=== {passed}/{passed + failed} 合格 ===")
sys.exit(1 if failed else 0)
