"""売り場のセール（キャンペーン）ごとの本数と対象作品を集める道具（scripts/floor_sales.py）のテスト。実行: python3 tests/test_floor_sales.py
（ネットには出ない。APIの答えは、作った作品で差し替える。名前・タイトルは、どれも作ったもの）"""
import json
import os
import re
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import floor_sales as S  # noqa: E402
import floor_data as F  # noqa: E402
import floor_history as H  # noqa: E402

S.G.DMM_INTERVAL_SEC = 0
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


NOW = datetime(2026, 10, 12, 10, 20, tzinfo=S.G.JST)
HOIHOI = {"title": "作ったメーカー他30％OFF", "date_begin": "2026-10-07 00:10:00", "date_end": "2026-10-13 23:59:59"}
DAILY = {"title": "作った日替わりセール", "date_begin": "2026-10-12 00:00:00", "date_end": "2026-10-12 23:59:59"}
ENDED = {"title": "終わったセール", "date_begin": "2026-10-01 00:00:00", "date_end": "2026-10-12 09:59:59"}
LATER = {"title": "これからのセール", "date_begin": "2026-10-13 00:00:00", "date_end": "2026-10-20 23:59:59"}


def raw(n, camp=None, title=None, genres=("巨乳", "素人", "ハイビジョン"), price="343", list_price="490", date="2026-09-30 10:00:00"):
    cid = f"amt{n:05d}"
    item = {
        "content_id": cid,
        "title": title or f"作った素人作品その{n}",
        "date": date,
        "affiliateURL": f"https://al.fanza.co.jp/?lurl=https%3A%2F%2Fwww.dmm.co.jp%2Fdigital%2Fvideoc%2F-%2Fdetail%2F%3D%2Fcid%3D{cid}%2F&af_id=test-990&ch=api",
        "imageURL": {"list": f"https://pics.dmm.co.jp/digital/amateur/{cid}/{cid}jm.jpg", "small": f"https://pics.dmm.co.jp/digital/amateur/{cid}/{cid}jp.jpg"},
        "prices": {"price": price + "~", "list_price": list_price},
        "volume": "1:03:00",
        "iteminfo": {
            "genre": [{"id": i, "name": g} for i, g in enumerate(genres)],
            "maker": [{"id": 300000 + (n % 3), "name": f"作ったメーカー{n % 3}"}],
            "actress": [{"id": 1, "name": "作った名前"}],
        },
    }
    if camp:
        item["campaign"] = [camp]
    return item


class FakeAPI:
    def __init__(self, rows, fail_at=()):
        self.rows, self.fail_at, self.calls = rows, set(fail_at), []

    def __call__(self, endpoint, params):
        self.calls.append(dict(params))
        off = int(params["offset"])
        if off in self.fail_at:
            raise RuntimeError("テストの失敗")
        return {"items": self.rows[off - 1: off - 1 + params["hits"]]}


def load_text(text):
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "f.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return S.load(p)


LAST = {}


def run(rows, site=(), keys=("amateur",), fail_at=(), old=None, calls=None, now=NOW, quick=None, site_titles=()):
    """テスト用のファイルに集める → (保存したか, 要約, ファイルの中身, 文字)。APIを呼んだ回数は LAST["calls"]"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "floor_sale.json")
        os.environ["FLOOR_SALE_HISTORY_PATH"] = os.path.join(tmp, "floor_sale_history.json")
        if old is not None:
            with open(path, "w", encoding="utf-8") as f:
                f.write(old)
        saved_site, saved_titles, saved_quick = S.site_cids, S.site_campaign_titles, S.QUICK_CALLS
        S.site_cids = lambda key: set(site)
        S.site_campaign_titles = lambda key: set(site_titles)
        if quick:
            S.QUICK_CALLS = quick
        before = F.FLOORS["amateur"]["campaign_calls"]
        if calls:
            F.FLOORS["amateur"]["campaign_calls"] = calls
        api = FakeAPI(rows, fail_at)
        try:
            saved, lines = S.update(now, list(keys), api, path)
        finally:
            S.site_cids, S.site_campaign_titles, S.QUICK_CALLS = saved_site, saved_titles, saved_quick
            F.FLOORS["amateur"]["campaign_calls"] = before
        LAST["calls"] = len(api.calls)
        text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        hist = open(os.environ["FLOOR_SALE_HISTORY_PATH"], encoding="utf-8").read() if os.path.exists(os.environ["FLOOR_SALE_HISTORY_PATH"]) else ""
        del os.environ["FLOOR_SALE_HISTORY_PATH"]
    try:
        data = json.loads(text) if text else None
    except ValueError:
        data = None
    return saved, lines, data, text, hist


print("■ 設定")
check("名前のあるキャンペーンが付く売り場（素人・アニメ・成人映画）だけを読む（同人は割引ごと・ゲームは札ごと・ブックス・見放題は無し）",
      S.KEYS == ["anime", "amateur", "cinema"], S.KEYS)
floors_js = open(os.path.join(ROOT, "site", "src", "lib", "floors.js"), encoding="utf-8").read()
check("キャンペーンのページに並べる本数（FLOOR_SALE_PAGE_LIST）と、集める本数が同じ",
      f"FLOOR_SALE_PAGE_LIST = {S.EXTRA_PER_CAMPAIGN};" in floors_js)
js_camp = re.findall(r"(\w+): \{ key: '\w+'[^\n]*campaigns: true", floors_js)
check("lib/floors.js の FLOORS の campaigns と、同じ売り場", sorted(js_camp) == sorted(S.KEYS), js_camp)

print("■ キャンペーンごとの本数と、このサイトに無い作品")
rows = [raw(n, HOIHOI if n % 2 else (DAILY if n % 5 == 0 else None)) for n in range(1, 251)]
rows[2] = raw(3, ENDED)
rows[4] = raw(5, LATER)
rows[6] = raw(7, HOIHOI, title="放課後のなにか")  # 未成年を連想させる作品は、数えるが入れない
saved, lines, data, text, hist = run(rows, site={"amt00001", "amt00009"})
am = data["amateur"]
hoi = [c for c in am["campaigns"] if c["title"] == HOIHOI["title"]]
check("保存した・確かめた時刻", saved and data["checked"] == "2026-10-12 10:20", lines)
check("期間中のキャンペーンだけ（終わった・これからのは数えない）・終わりが近い順",
      [c["title"] for c in am["campaigns"]] == ["作った日替わりセール", HOIHOI["title"]], am["campaigns"])
check("本数は、未成年を連想させる作品・このサイトの作品も入れて数える（終わった・これからのセールの作品は数えない）", hoi and hoi[0]["n"] == 125 - 2,
      hoi)
check("期間は「YYYY-MM-DD HH:MM」", hoi and hoi[0]["begin"] == "2026-10-07 00:10" and hoi[0]["end"] == "2026-10-13 23:59", hoi)
ex = am["extra"]
check("このサイトに無い作品だけ・キャンペーンごとに60本まで・未成年を連想させる作品は入れない",
      all(r["cid"] not in ("amt00001", "amt00009", "amt00007") for r in ex)
      and sum(1 for r in ex if r["campaign"]["title"] == HOIHOI["title"]) == S.EXTRA_PER_CAMPAIGN
      and sum(1 for r in ex if r["campaign"]["title"] == "作った日替わりセール") == 25, len(ex))
first = next(r for r in ex if r["cid"] == "amt00003" or r["cid"] == "amt00011")
check("作品の形（品番・タイトル・URL・表紙・発売日・メーカー・出演者・ジャンル・価格・定価・キャンペーン・人気の順位）",
      set(first) == {"cid", "title", "url", "image_url", "date", "maker", "maker_id", "actress", "genres", "price", "list_price", "campaign", "rank"}
      and first["price"] == 343 and first["list_price"] == 490 and first["rank"] == int(first["cid"][3:]) and first["campaign"]["begin"] in ("2026-10-07", "2026-10-12")
      and first["image_url"].startswith("https://pics.dmm.co.jp/"), first)
check("1作品1行（差分が読みやすい）", all(line.startswith("{\"cid\"") for line in text.split("\n") if "\"cid\"" in line) and text.count("\n{\"cid\"") == len(ex))
check("読んで書き直しても1文字も変わらない", S.dump(load_text(text)) == text)
check("セールの記録（floor_sale_history.json）に、キャンペーンの名前と本数を足す（始まりは日付）",
      '"title":"作ったメーカー他30％OFF","begin":"2026-10-07","first":"2026-10-12","last":"2026-10-12","count":123,"off":30' in hist, hist[:300])

print("■ 読めなかったとき・変わらないとき")
old_text = text
saved2, lines2, data2, text2, _ = run(rows, site={"amt00001", "amt00009"}, old=old_text)
check("中身が同じなら保存しない", not saved2 and text2 == old_text, lines2)
saved3, lines3, data3, text3, hist3 = run(rows, fail_at={1, 101, 201}, old=old_text, calls=10)
check("最後まで読めなかったら、前のデータのうち、まだ期間中のキャンペーンだけ残す（同じなら保存しない）・セールの記録は足さない",
      not saved3 and text3 == old_text and [c["title"] for c in data3["amateur"]["campaigns"]] == [c["title"] for c in am["campaigns"]] and not hist3, lines3)
old_ended = old_text.replace("2026-10-12 23:59", "2026-10-12 09:59")
saved4, lines4, data4, _, _ = run(rows, fail_at={1, 101, 201}, old=old_ended, calls=10)
check("終わったキャンペーンと、その作品は外す", [c["title"] for c in data4["amateur"]["campaigns"]] == [HOIHOI["title"]]
      and all(r["campaign"]["title"] == HOIHOI["title"] for r in data4["amateur"]["extra"]), data4["amateur"]["campaigns"])
saved5, lines5, data5, _, _ = run(rows, old='{"checked":', calls=10)
check("前のファイルが壊れていたら、保存しない（壊れたまま残す）", not saved5 and data5 is None, lines5)
saved6, _, data6, _, _ = run(rows, keys=("anime",), old=old_text)
check("ほかの売り場だけを集めた日も、素人の前のデータ（期間中のもの）は残す", data6 and data6.get("amateur", {}).get("campaigns") == am["campaigns"], data6)

print("■ 読むときの見張り")
bad = json.loads(old_text)
bad["amateur"]["campaigns"].append({"title": "", "begin": "", "end": "2026-10-13 23:59", "n": 3})
bad["amateur"]["campaigns"].append({"title": "形の違う終わり", "begin": "", "end": "そのうち", "n": 3})
bad["amateur"]["extra"].append({"cid": "x y", "title": "形の違う作品"})
bad["amateur"]["extra"].append(dict(ex[0], url="https://example.com/x"))
with tempfile.TemporaryDirectory() as tmp:
    p = os.path.join(tmp, "f.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(bad, f, ensure_ascii=False)
    got = S.load(p)
check("名前・終わりの形が違うキャンペーン、品番・URLの形が違う作品は捨てる",
      len(got["amateur"]["campaigns"]) == len(am["campaigns"]) and len(got["amateur"]["extra"]) == len(ex), (len(got["amateur"]["campaigns"]), len(got["amateur"]["extra"])))

print("■ はじめは上位1万本だけ（セールの顔ぶれが前と同じなら、そこでやめる。運営者の「先に終わったかどうかを見れば」。2026-10-12）")
# 上位100本（テストでは1回分）にキャンペーンの作品があり、その下にもある売り場（300本。最後まで読むと4回＝4回目が空）
deep = [raw(n, HOIHOI if n % 3 == 0 else None) for n in range(1, 301)]
saved_a, lines_a, data_a, text_a, _ = run(deep, quick=1)
check("前のデータが無い日は、最後まで読む（5万本まで読んだ日を full に）", LAST["calls"] == 4 and data_a["amateur"]["full"] == "2026-10-12"
      and data_a["amateur"]["campaigns"][0]["n"] == 100, (LAST["calls"], data_a["amateur"]["campaigns"]))
NEXT = datetime(2026, 10, 13, 0, 35, tzinfo=S.G.JST)
saved_b, lines_b, data_b, text_b, hist_b = run(deep, quick=1, old=text_a, now=NEXT)
check("次の日、顔ぶれが同じなら、上位1万本だけ（1回）でやめる・本数は前に5万本まで数えたまま・full の日も前のまま",
      LAST["calls"] == 1 and data_b["amateur"]["campaigns"][0]["n"] == 100 and data_b["amateur"]["full"] == "2026-10-12" and data_b["amateur"]["date"] == "2026-10-13"
      and any("顔ぶれが前と同じ" in l for l in lines_b), (LAST["calls"], lines_b))
check("このサイトに無い作品は、上位1万本で見かけたもの（新しい順位）を先に、足りない分は前のデータから（60本まで）",
      len(data_b["amateur"]["extra"]) == 60 and [r["cid"] for r in data_b["amateur"]["extra"]] == [r["cid"] for r in data_a["amateur"]["extra"]][:60]
      and '"count":100' in hist_b, len(data_b["amateur"]["extra"]))
check("顔ぶれが同じでも、このサイトに入った作品は外す", all(r["cid"] != "amt00003" for r in run(deep, quick=1, old=text_a, now=NEXT, site={"amt00003"})[2]["amateur"]["extra"]))
_, lines_c, data_c, _, _ = run(deep, quick=1, old=text_a, now=datetime(2026, 10, 15, 0, 35, tzinfo=S.G.JST))
check("前に最後まで読んでから3日たったら、最後まで読む", LAST["calls"] == 4 and data_c["amateur"]["full"] == "2026-10-15" and any("3日" in l for l in lines_c), lines_c)
fresh_rows = list(deep)
fresh_rows[1] = raw(2, LATER)
_, lines_d, data_d, _, _ = run(fresh_rows, quick=1, old=text_a, now=datetime(2026, 10, 13, 0, 35, tzinfo=S.G.JST).replace(day=13))
check("上位1万本に新しいセールがあれば、最後まで読む", LAST["calls"] == 4 and any("新しいセール" in l for l in lines_d) and len(data_d["amateur"]["campaigns"]) == 2, lines_d)
ended_old = text_a.replace("2026-10-13 23:59", "2026-10-12 23:59")
_, lines_e, _, _, _ = run(deep, quick=1, old=ended_old, now=NEXT)
check("前のセールのどれかが終わっていたら、最後まで読む", LAST["calls"] == 4 and any("終わったセール" in l for l in lines_e), lines_e)
gone_rows = [raw(n, HOIHOI if n % 3 == 0 and n > 100 else None) for n in range(1, 301)]
_, lines_f, _, _, _ = run(gone_rows, quick=1, old=text_a, now=NEXT)
check("前は上位1万本に作品があったセールを、上位1万本で見かけなかったら、最後まで読む", LAST["calls"] == 4 and any("見かけなくなった" in l for l in lines_f), lines_f)
deep_only_old = text_a
_, lines_g, _, _, _ = run(gone_rows, quick=1, old=run(gone_rows, quick=1)[3], now=NEXT)
check("もともと上位1万本より下にしか作品の無いセールは、上位1万本で見かけなくても、そのまま（最後まで読まない）", LAST["calls"] == 1, lines_g)
_, lines_h, _, _, _ = run(gone_rows, quick=1, old=run(gone_rows, quick=1)[3], now=NEXT, site_titles={HOIHOI["title"]})
check("このサイトの作品に付いているセールを、上位1万本で見かけなかったら、最後まで読む", LAST["calls"] == 4, lines_h)

print(f"\n{passed} 件成功 / {failed} 件失敗")
sys.exit(1 if failed else 0)
