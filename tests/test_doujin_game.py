"""FANZA同人・FANZAゲームを集める道具（scripts/doujin_game.py・scripts/floor_data.py）のテスト。実行: python3 tests/test_doujin_game.py
（ネットには出ない。APIの答えは、作った作品で差し替える。名前・タイトルは、どれも作ったもの）"""
import contextlib
import io
import json
import os
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import doujin_game as D  # noqa: E402
import floor_data as F  # noqa: E402

D.G.DMM_INTERVAL_SEC = 0
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


TODAY = datetime(2026, 10, 9, tzinfo=D.G.JST)


def raw(n, kind="doujin", title=None, genres=("巨乳", "男性向け", "成人向け"), date="2026-09-30 00:00:00", **extra):
    """API の1件（作った作品）"""
    cid = f"d_{100000 + n}" if kind == "doujin" else f"brand_{n:04d}"
    item = {
        "content_id": cid,
        "title": title or f"作った作品その{n}",
        "date": date,
        "affiliateURL": f"https://al.fanza.co.jp/?lurl=https%3A%2F%2Fwww.dmm.co.jp%2Fdc%2Fdoujin%2F-%2Fdetail%2F%3D%2Fcid%3D{cid}%2F&af_id=test-990&ch=api",
        "imageURL": ({"list": f"https://doujin-assets.dmm.co.jp/digital/comic/{cid}/{cid}pt.jpg", "large": f"https://doujin-assets.dmm.co.jp/digital/comic/{cid}/{cid}pl.jpg"}
                     if kind == "doujin" else
                     {"list": f"https://pics.dmm.co.jp/digital/pcgame/{cid}/{cid}pt.jpg", "small": f"https://pics.dmm.co.jp/digital/pcgame/{cid}/{cid}ps.jpg", "large": f"https://pics.dmm.co.jp/digital/pcgame/{cid}/{cid}pl.jpg"}),
        "sampleImageURL": ({"sample_l": {"image": [f"https://doujin-assets.dmm.co.jp/digital/comic/{cid}/{cid}jp-{i:03d}.jpg" for i in range(1, 11)]}}
                           if kind == "doujin" else
                           {"sample_s": {"image": [f"https://pics.dmm.co.jp/digital/pcgame/{cid}/{cid}js-{i:03d}.jpg" for i in range(1, 25)]}}),
        "prices": ({"price": "1155", "list_price": "1650"} if kind == "doujin" else {"price": "8800", "deliveries": {"delivery": [{"type": "download", "price": "8800", "list_price": ""}]}}),
        "iteminfo": {
            "genre": [{"id": i, "name": g} for i, g in enumerate(genres)],
            "maker": [{"id": 200000 + (n % 7), "name": f"サークル{n % 7}"}],
        },
    }
    if kind == "game":
        item["iteminfo"]["author"] = [{"id": 1, "name": "作った原画家"}]
    item.update(extra)
    return item


class FakeAPI:
    """人気順の一覧（rows）を100本ずつ返す。fail_at の offset では失敗する"""

    def __init__(self, rows, upcoming=(), fail_at=()):
        self.rows, self.upcoming, self.fail_at, self.calls = rows, list(upcoming), set(fail_at), []

    def __call__(self, endpoint, params):
        self.calls.append(dict(params))
        if params.get("gte_date"):
            return {"items": self.upcoming[: params["hits"]]}
        off = int(params["offset"])
        if off in self.fail_at:
            raise RuntimeError("テストの失敗")
        return {"items": self.rows[off - 1: off - 1 + params["hits"]]}


print("■ 入れない作品（未成年を連想させる言葉）")
check("タイトル・ジャンル・シリーズ・サークル・作家のどれかに未成年を連想させる言葉があれば入れない",
      D.blocked_reason(raw(1, title="放課後のなにか")) == "タイトル"
      and D.blocked_reason(raw(2, genres=("巨乳", "ロリ"))) == "ジャンル"
      and D.blocked_reason(raw(3, genres=("学園もの",))) == "ジャンル"
      and D.blocked_reason(dict(raw(4), iteminfo={**raw(4)["iteminfo"], "series": [{"id": 9, "name": "制服シリーズ"}]})) == "シリーズ"
      and D.blocked_reason(dict(raw(5), iteminfo={**raw(5)["iteminfo"], "maker": [{"id": 1, "name": "ロリ工房"}]})) == "サークル・ブランド"
      and D.blocked_reason(dict(raw(6, kind="game"), iteminfo={**raw(6, kind="game")["iteminfo"], "author": [{"id": 1, "name": "JK太郎"}]})) == "作家")
check("大人どうしの言葉（幼なじみ・処女・姉妹）や、ふつうの作品は入れる",
      D.blocked_reason(raw(7, title="幼なじみと過ごす休日")) == "" and D.blocked_reason(raw(8, genres=("処女", "巨乳"))) == "" and D.blocked_reason(raw(9)) == "")

print("\n■ 1件の読み方")
it = D.parse_floor_item(raw(10), "doujin")
check("同人: 品番・タイトル・アフィリエイトのURL・大きい表紙・サンプル画像は6枚まで・サークル（id つき）",
      it["cid"] == "d_100010" and it["url"].startswith("https://al.fanza.co.jp/") and it["image_url"].endswith("d_100010pl.jpg")
      and len(it["sample_images"]) == 6 and it["maker"] == "サークル3" and it["maker_id"] == 200003, it)
check("同人: 画像は、同じ場所の pics.dmm.co.jp にする（doujin-assets は、運営者のiPhoneでページの中に出なかったため。2026-10-09）",
      it["image_url"] == "https://pics.dmm.co.jp/digital/comic/d_100010/d_100010pl.jpg" and all(u.startswith("https://pics.dmm.co.jp/digital/comic/d_100010/") for u in it["sample_images"])
      and D.pics_url("https://doujin-assets.dmm.co.jp/a/b.jpg") == "https://pics.dmm.co.jp/a/b.jpg" and D.pics_url("https://pics.dmm.co.jp/x.jpg") == "https://pics.dmm.co.jp/x.jpg", it["image_url"])
check("同人: ジャンルは中身と形式に分ける（男性向け・成人向けは形式）・価格と定価",
      it["genres"] == ["巨乳"] and it["formats"] == ["男性向け", "成人向け"] and it["price"] == 1155 and it["list_price"] == 1650 and it["campaign"] is None, it)
it_c = D.parse_floor_item(raw(11, campaign=[{"date_begin": "2026-10-01T00:00:00Z", "date_end": "", "title": "30%OFF"}]), "doujin")
check("同人: キャンペーン（30%OFF・始まった日）", it_c["campaign"] == {"title": "30%OFF", "begin": "2026-10-01"}, it_c["campaign"])
g = D.parse_floor_item(raw(12, kind="game", genres=("恋愛", "最大90%OFFセール【感謝祭オータム2026】", "3点以上で5%OFFクーポン／感謝祭オータム2026対象",
                                                    "Windows11対応作品", "DL版独占販売", "CGがいい", "エロに定評")), "game")
check("ゲーム: セールの札・形式・中身のジャンルに分け、評価の札（○○がいい・○○に定評）は持たない",
      g["genres"] == ["恋愛"] and g["sales"] == ["最大90%OFFセール【感謝祭オータム2026】", "3点以上で5%OFFクーポン／感謝祭オータム2026対象"]
      and g["formats"] == ["Windows11対応作品", "DL版独占販売"], g)
check("ゲーム: サンプル画像は大きい版（js- → jp-）を8枚まで・作家・定価が空なら null",
      len(g["sample_images"]) == 8 and all("jp-" in u and "js-" not in u for u in g["sample_images"]) and g["authors"] == ["作った原画家"] and g["price"] == 8800 and g["list_price"] is None, g)
check("URL・画像が FANZA(DMM) の https でなければ使わない（作品ごと入れない・画像は空）",
      D.parse_floor_item(dict(raw(13), affiliateURL="https://evil.example/x"), "doujin") is None
      and D.parse_floor_item(dict(raw(14), imageURL={"large": "https://evil.example/a.jpg"}), "doujin")["image_url"] == "")
check("品番・タイトル・発売日が無い作品は読まない", D.parse_floor_item(dict(raw(15), content_id=""), "doujin") is None and D.parse_floor_item(dict(raw(16), date=""), "doujin") is None)

print("\n■ 集め方（人気順の上から、決めた本数まで）")
saved = dict(F.FLOORS["doujin"])
F.FLOORS["doujin"].update(target=150, max_calls=5)
rows = [raw(n, title=("放課後のなにか" if n % 4 == 0 else None)) for n in range(1, 401)]
api = FakeAPI(rows)
picked, st = D.scan("doujin", TODAY, api)
check("未成年を連想させる作品を飛ばして、150本そろうまで読む（1/4を飛ばすので、上位200本まで・2回）",
      len(picked) == 150 and st["skipped"] == 49 and st["calls"] == 2 and st["complete"] and picked[0]["rank"] == 1 and picked[-1]["rank"] == 199, (len(picked), st))
check("問い合わせは人気順（sort=rank）・発売済みだけ（lte_date）・同人の売り場",
      all(c["sort"] == "rank" and c["service"] == "doujin" and c["floor"] == "digital_doujin" and c.get("lte_date") for c in api.calls))
api_f = FakeAPI(rows, fail_at={101})
with contextlib.redirect_stdout(io.StringIO()):
    picked_f, st_f = D.scan("doujin", TODAY, api_f)
check("続けて3回失敗したら止めて、最後まで読めなかった印（complete: false）", not st_f["complete"] and len(picked_f) == 75 and st_f["fails"] == 3, st_f)
picked_s, st_s = D.scan("doujin", TODAY, FakeAPI(rows[:120]))
check("一覧が途中で終わったら、そこまで（最後まで読めた扱い）", st_s["complete"] and len(picked_s) == 90, (len(picked_s), st_s))
F.FLOORS["doujin"].update(saved)

saved_g = dict(F.FLOORS["game"])
F.FLOORS["game"].update(target=5, max_calls=3)
game_rows = [raw(n, kind="game", date="2026-08-01 00:00:00") for n in range(1, 101)]
up = [raw(900, kind="game", date="2026-11-20 00:00:00"), raw(901, kind="game", date="2026-11-21 00:00:00", title="制服のなにか")]
picked_g, st_g = D.scan("game", TODAY, FakeAPI(game_rows, upcoming=up))
check("ゲーム: 人気順の5本＋予約（未成年を連想させるものは除く。順位は無し）",
      [p["cid"] for p in picked_g] == ["brand_0001", "brand_0002", "brand_0003", "brand_0004", "brand_0005", "brand_0900"] and picked_g[-1]["rank"] is None, [p["cid"] for p in picked_g])
F.FLOORS["game"].update(saved_g)

print("\n■ 前の日のデータとまぜる")
old_items = {}
for n in (1, 2, 3):
    x = D.parse_floor_item(raw(n), "doujin")
    x["updated"] = "2026-10-01"
    old_items[x["cid"]] = x
old_items["d_100002"].update(comment="Claudeが書いたコメントです。" * 5, comment_kind="claude", updated="2026-10-05")
old_items["d_100003"].update(comment="Claudeが書いた別のコメントです。" * 5, comment_kind="claude", updated="2026-10-06")
old = {"items": old_items, "ranks": {"d_100001": 1, "d_100002": 2, "d_100003": 3}}
fresh = []
for n, r in ((1, 5), (3, 1), (50, 2)):
    x = D.parse_floor_item(raw(n), "doujin")
    x["rank"] = r
    fresh.append(x)
data, res = D.merge(old, [dict(x) for x in fresh], {"complete": True, "scanned": 200, "skipped": 3}, "2026-10-09")
check("前からある作品はコメントと updated を引き継ぐ・新しい作品は none で今日・順位は今日のもの",
      data["items"]["d_100003"]["comment_kind"] == "claude" and data["items"]["d_100003"]["updated"] == "2026-10-06"
      and data["items"]["d_100050"]["comment_kind"] == "none" and data["items"]["d_100050"]["updated"] == "2026-10-09"
      and data["ranks"] == {"d_100001": 5, "d_100003": 1, "d_100050": 2}, data["ranks"])
check("今日の上位に無い作品: コメントのある作品は残す（順位は無し）", "d_100002" in data["items"] and "d_100002" not in data["ranks"] and res["kept"] == 1 and res["removed"] == 0, res)
old2 = {"items": {**old_items, "d_100099": D.parse_floor_item(raw(99), "doujin")}, "ranks": {**old["ranks"], "d_100099": 4}}
data2, res2 = D.merge(old2, [dict(x) for x in fresh], {"complete": True, "scanned": 200, "skipped": 3}, "2026-10-09")
check("今日の上位に無い、コメントの無い作品は外す", "d_100099" not in data2["items"] and res2["removed"] == 1, res2)
data3, res3 = D.merge(old2, [dict(x) for x in fresh], {"complete": False, "scanned": 100, "skipped": 0}, "2026-10-09")
check("最後まで読めなかった日は、前の作品を外さない（順位も前のまま）", "d_100099" in data3["items"] and data3["ranks"]["d_100099"] == 4 and not res3["trusted"], res3)
big_old = {"items": {f"d_{200000 + i}": D.parse_floor_item(raw(100000 + i), "doujin") for i in range(200)}, "ranks": {}}
big_old["items"] = {x["cid"]: x for x in big_old["items"].values()}
big_old["ranks"] = {c: i + 1 for i, c in enumerate(big_old["items"])}
data4, res4 = D.merge(big_old, [dict(x) for x in fresh], {"complete": True, "scanned": 300, "skipped": 0}, "2026-10-09")
check("そろった本数が前の半分より少ない日は、APIの答えがおかしいものとして、前の作品を外さない", not res4["trusted"] and len(data4["items"]) == 203, (res4, len(data4["items"])))

print("\n■ ファイルの読み書き（scripts/floor_data.py）")
tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "doujin.json")
F.save_floor(path, data)
text = open(path, encoding="utf-8").read()
back = F.load_floor(path)
check("書いて読み直すと同じ（作品・順位・集めた日）", back["items"] == data["items"] and back["ranks"] == data["ranks"] and back["updated"] == "2026-10-09" and back["scanned"] == 200, back["ranks"])
lines = text.split("\n")
check("1作品1行・品番の順（毎日の差分が、変わった行だけになるように）",
      sum(1 for ln in lines if ln.startswith('{"cid"')) == len(data["items"]) and [json.loads(ln.rstrip(","))["cid"] for ln in lines if ln.startswith('{"cid"')] == sorted(data["items"]))
F.save_floor(path, back)
check("読んで書き直しても、1文字も変わらない", open(path, encoding="utf-8").read() == text)
check("無いファイルは None・壊れたファイルは ValueError（上書きしないため）", F.load_floor(os.path.join(tmp, "none.json")) is None)
open(os.path.join(tmp, "broken.json"), "w").write("{broken")
try:
    F.load_floor(os.path.join(tmp, "broken.json"))
    check("壊れたファイルは ValueError", False)
except ValueError:
    check("壊れたファイルは ValueError", True)
check("読むときに、決まった項目だけ・コメントの無い claude は none に",
      F.clean_item({**data["items"]["d_100050"], "extra": 1, "comment_kind": "claude", "comment": ""})["comment_kind"] == "none"
      and "extra" not in F.clean_item({**data["items"]["d_100050"], "extra": 1}))

print("\n■ 1つの売り場を集め直して保存する（update_floor）")
os.environ["DOUJIN_PATH"] = path
os.environ["FLOOR_RANK_HISTORY_PATH"] = os.path.join(tmp, "floor_rank_history.json")  # 本物のデータに書かないように
os.environ["FLOOR_SALE_HISTORY_PATH"] = os.path.join(tmp, "floor_sale_history.json")
F.FLOORS["doujin"].update(target=3, max_calls=2)
before = open(path, encoding="utf-8").read()
with contextlib.redirect_stdout(io.StringIO()) as out:
    line = D.update_floor("doujin", TODAY, FakeAPI([]))
check("1本も取れなかったら、ファイルを変えない", open(path, encoding="utf-8").read() == before and "前のデータのまま" in line, line)
open(path, "w").write("{broken")
with contextlib.redirect_stdout(io.StringIO()) as out:
    line = D.update_floor("doujin", TODAY, FakeAPI(rows))
check("前のデータが壊れていたら、集めずに知らせる（上書きしない）", open(path).read() == "{broken" and "読めなかった" in line, line)
os.remove(path)
with contextlib.redirect_stdout(io.StringIO()) as out:
    line = D.update_floor("doujin", TODAY, FakeAPI(rows))
saved_data = F.load_floor(path)
check("はじめての日（ファイルが無い）は、新しく作る", len(saved_data["items"]) == 3 and "新しく3本" in line, line)
check("集めたあと、人気の動きとセールの記録も足す（結果の要約に出る）", "人気の動き 3本を記録中" in line and "セール中" in line
      and os.path.exists(os.environ["FLOOR_RANK_HISTORY_PATH"]) and os.path.exists(os.environ["FLOOR_SALE_HISTORY_PATH"]), line)
F.FLOORS["doujin"].update(saved)
del os.environ["DOUJIN_PATH"]

print("\n■ 人気の動き（scripts/floor_history.py。2026-10-09 から）")
H = D.H
check("順位は、このサイトの人気ランキングと同じ数え方（発売済みを FANZA の人気順に並べた順位）・上位だけ",
      H.positions({"ranks": {"a": 5, "b": 2, "c": 9, "d": 0}}) == {"b": 1, "a": 2, "c": 3} and H.positions({"ranks": {"a": 5, "b": 2, "c": 9}}, track=2) == {"b": 1, "a": 2})
hist = {"updated": "", "doujin": {}, "game": {}}
H.merge_rank_history(hist, "doujin", "2026-10-09", {"a": 1, "b": 2})
H.merge_rank_history(hist, "doujin", "2026-10-10", {"a": 2, "c": 1})
check("毎日1つずつ順位を足す（載っていない日は 0・新しく入った作品はその日から）",
      hist["doujin"]["a"] == {"d": "2026-10-09", "r": [1, 2]} and hist["doujin"]["b"] == {"d": "2026-10-09", "r": [2, 0]} and hist["doujin"]["c"] == {"d": "2026-10-10", "r": [1]}, hist["doujin"])
H.merge_rank_history(hist, "doujin", "2026-10-11", None)
check("最後まで読めなかった日は「分からない」（null）", hist["doujin"]["a"]["r"] == [1, 2, None] and hist["doujin"]["c"]["r"] == [1, None])
H.merge_rank_history(hist, "doujin", "2026-10-11", {"a": 4})
H.merge_rank_history(hist, "doujin", "2026-10-11", None)
check("同じ日に動き直したら新しい順位にする・分かっている順位を「分からない」で上書きしない", hist["doujin"]["a"]["r"] == [1, 2, 4] and hist["doujin"]["b"]["r"] == [2, 0, 0])
day = "2026-10-11"
for n in range(1, 31):
    day = H.add_days("2026-10-11", n)
    H.merge_rank_history(hist, "doujin", day, {"a": 3})
check(f"{H.RANK_DAYS}日分だけ持つ（古い日は前から捨てて、最初の日を進める）・ずっと圏外だった作品は消す",
      len(hist["doujin"]["a"]["r"]) == H.RANK_DAYS and hist["doujin"]["a"]["d"] == H.add_days(day, -(H.RANK_DAYS - 1)) and "b" not in hist["doujin"] and "c" not in hist["doujin"], hist["doujin"].keys())
rh_path = os.environ["FLOOR_RANK_HISTORY_PATH"]
H.save_rank_history(hist)
text = open(rh_path, encoding="utf-8").read()
back = H.load_rank_history()
check("書いて読み直すと同じ・1作品1行（毎日の差分を小さく）", back["doujin"] == hist["doujin"] and back["updated"] == day and sum(1 for ln in text.split("\n") if ln.startswith('"a":')) == 1, text[:200])
H.save_rank_history(back)
check("読んで書き直しても、1文字も変わらない", open(rh_path, encoding="utf-8").read() == text)
open(rh_path, "w").write("{broken")
with contextlib.redirect_stdout(io.StringIO()):
    empty = H.load_rank_history()
check("壊れていたら、空から記録し直す（ほかに元のデータが無いので）", empty["doujin"] == {} and empty["game"] == {})

print("\n■ セールの記録（scripts/floor_history.py）")
sale_data = {"items": {
    "d1": {"date": "2026-10-01", "price": 550, "list_price": 1100, "sales": [], "campaign": {"title": "50%OFF", "begin": "2026-10-01"}},
    "d2": {"date": "2026-10-02", "price": 770, "list_price": 1100, "sales": [], "campaign": {"title": "30%OFF", "begin": "2026-09-29"}},
    "d3": {"date": "2026-10-03", "price": 1100, "list_price": 1100, "sales": [], "campaign": None},
    "g1": {"date": "2026-09-01", "price": None, "list_price": None, "sales": ["最大90%OFFセール【感謝祭オータム2026】", "3点以上で5%OFFクーポン"], "campaign": None},
    "g2": {"date": "2026-12-01", "price": 500, "list_price": 1000, "sales": [], "campaign": None},  # 予約（まだ発売前）は数えない
}}
d_, t_ = H.sale_today(sale_data, "2026-10-09")
tags_ = {(t["title"], t["begin"]): t for t in t_}
check("その日のセール中の本数・最大の割引（価格と定価・札の名前の「最大90%OFF」から）。クーポンだけの作品は数えない・予約は数えない",
      d_ == {"d": "2026-10-09", "n": 3, "max": 90}, d_)
check("セールの名前ごと: 同人は名前と始まりの日・ゲームは札（クーポンも名前は残す）・名前から読める割引",
      tags_[("50%OFF", "2026-10-01")]["count"] == 1 and tags_[("最大90%OFFセール【感謝祭オータム2026】", "")]["off"] == 90
      and ("3点以上で5%OFFクーポン", "") in tags_ and H.off_in_title("アトリエかぐや25周年記念！半額セール") == 50 and H.off_in_title("500円セール") == 0, t_)
sales = {"updated": "", "doujin": {"days": [], "tags": []}, "game": {"days": [], "tags": []}}
H.merge_sale_history(sales, "doujin", "2026-10-09", d_, t_)
H.merge_sale_history(sales, "doujin", "2026-10-09", {**d_, "n": 4}, t_)
H.merge_sale_history(sales, "doujin", "2026-10-10", {**d_, "d": "2026-10-10", "n": 2}, [{**t_[0], "count": 5}])
row_ = next(t for t in sales["doujin"]["tags"] if t["title"] == t_[0]["title"] and t["begin"] == t_[0]["begin"])
check("1日1行（同じ日に動き直したら入れかえ）・名前ごとに最初と最後に見かけた日・いちばん多かった日の本数",
      [d["d"] for d in sales["doujin"]["days"]] == ["2026-10-09", "2026-10-10"] and sales["doujin"]["days"][0]["n"] == 4
      and row_["first"] == "2026-10-09" and row_["last"] == "2026-10-10" and row_["count"] == 5, sales["doujin"])
far = H.add_days("2026-10-10", H.SALE_KEEP_DAYS)
H.merge_sale_history(sales, "doujin", far, {**d_, "d": far}, [])
check(f"{H.SALE_KEEP_DAYS}日より前の記録は消す", [d["d"] for d in sales["doujin"]["days"]] == [far] and sales["doujin"]["tags"] == [], sales["doujin"])
sh_path = os.environ["FLOOR_SALE_HISTORY_PATH"]
H.save_sale_history(sales)
text = open(sh_path, encoding="utf-8").read()
check("書いて読み直すと同じ・読んで書き直しても1文字も変わらない", H.load_sale_history()["doujin"] == sales["doujin"]
      and (H.save_sale_history(H.load_sale_history()) or open(sh_path, encoding="utf-8").read() == text))
open(sh_path, "w").write("{broken")
with contextlib.redirect_stdout(io.StringIO()) as out_:
    note_ = H.record("doujin", {"ranks": {"d1": 3}, "items": sale_data["items"]}, "2026-10-12", True)
check("セールの記録が壊れていたら、上書きせずに、その日は記録しない（人気の動きは記録する）", open(sh_path).read() == "{broken" and "読めなかった" in note_, note_)
with contextlib.redirect_stdout(io.StringIO()):
    note_ = H.record("game", {"ranks": {"g1": 1}, "items": sale_data["items"]}, "2026-10-12", False)
check("最後まで読めなかった日は、順位を「分からない」にして、セールは記録しない", "記録しない" in note_ and H.load_rank_history()["game"] == {}, note_)
for k in ("FLOOR_RANK_HISTORY_PATH", "FLOOR_SALE_HISTORY_PATH"):
    del os.environ[k]
check("本物の置き場所は site/src/data（毎日の更新が保存する場所）", H.rank_history_path().endswith(os.path.join("site", "src", "data", "floor_rank_history.json"))
      and H.sale_history_path().endswith(os.path.join("site", "src", "data", "floor_sale_history.json")))

print("\n■ 本番の設定")
check("同人は1,000本・ゲームは500本（運営者の希望。2026-10-09）・ゲームは予約も", F.FLOORS["doujin"]["target"] == 1000 and F.FLOORS["game"]["target"] == 500 and F.FLOORS["game"]["upcoming"] > 0)
check("同人は service=doujin・floor=digital_doujin、ゲームは service=pcgame・floor=digital_pcgame（2026-10-09 に本物のAPIで確認）",
      (F.FLOORS["doujin"]["service"], F.FLOORS["doujin"]["floor"], F.FLOORS["game"]["service"], F.FLOORS["game"]["floor"]) == ("doujin", "digital_doujin", "pcgame", "digital_pcgame"))
wf = open(os.path.join(ROOT, ".github", "workflows", "update.yml"), encoding="utf-8").read()
check("毎日の更新から動かす・失敗しても更新を止めない・Gemini のキーは渡さない・保存の前",
      "python scripts/doujin_game.py --update" in wf and "continue-on-error: true" in wf[wf.index("Update doujin and games"):wf.index("python scripts/doujin_game.py")]
      and "GEMINI" not in wf[wf.index("Update doujin and games"):wf.index("python scripts/doujin_game.py")]
      and wf.index("python scripts/doujin_game.py") < wf.index("git add -A -- site/src/data"))
rf = open(os.path.join(ROOT, ".github", "workflows", "refresh-data.yml"), encoding="utf-8").read()
check("取り直しのワークフロー: 「同人・ゲームだけ」のときは、ほかの取り直しを動かさない",
      "floors_only" in rf and rf.count("inputs.floors_only != '1'") >= 4 and "python scripts/doujin_game.py --update" in rf)

print("\n■ 新しい売り場（アニメ・素人・成人映画・コミック・写真集・VR見放題。2026-10-10）")
check("本数: アニメ・成人映画・コミック・写真集・VR見放題は100本・素人は500本（運営者の希望）。API の service/floor は 2026-10-10 に本物で確認したもの",
      all(F.FLOORS[k]["target"] == 100 for k in ("anime", "cinema", "comic", "photo", "vr")) and F.FLOORS["amateur"]["target"] == 500
      and [(F.FLOORS[k]["service"], F.FLOORS[k]["floor"]) for k in ("anime", "amateur", "cinema", "comic", "photo", "vr")]
      == [("digital", "anime"), ("digital", "videoc"), ("digital", "nikkatsu"), ("ebook", "comic"), ("ebook", "photo"), ("monthly", "vr")]
      and len({F.FLOORS[k]["file"] for k in F.FLOORS}) == len(F.FLOORS) and len({F.FLOORS[k]["env"] for k in F.FLOORS}) == len(F.FLOORS))
am = {"content_id": "abc123", "title": "作った素人の作品", "date": "2026-09-01 10:00:00",
      "affiliateURL": "https://al.fanza.co.jp/?lurl=https%3A%2F%2Fvideo.dmm.co.jp%2Famateur%2Fcontent%2F%3Fid%3Dabc123&af_id=test-990&ch=api",
      "imageURL": {"list": "https://pics.dmm.co.jp/digital/amateur/abc123/abc123jm.jpg", "small": "https://pics.dmm.co.jp/digital/amateur/abc123/abc123jp.jpg"},
      "sampleMovieURL": {"size_476_306": "https://www.dmm.co.jp/litevideo/-/part/=/cid=abc123/size=476_306/", "pc_flag": 1, "sp_flag": 1},
      "iteminfo": {"genre": [{"id": 1, "name": "素人"}, {"id": 2, "name": "ハイビジョン"}], "maker": [{"id": 5, "name": "作ったメーカー"}],
                   "actress": [{"id": 9, "name": "作った出演者"}, {"id": 0, "name": "----"}]}}
it = D.parse_floor_item(am, "amateur")
check("素人: 大きい表紙が無ければ小さい版（1200×1200の四角）・サンプル動画・出演者（「----」は入れない）・ハイビジョンは形式",
      it and it["image_url"].endswith("abc123jp.jpg") and it["sample_movie"].startswith("https://www.dmm.co.jp/litevideo/") and it["actress"] == ["作った出演者"]
      and "ハイビジョン" in it["formats"] and it["genres"] == ["素人"], it)
bk = {"content_id": "b123abc456", "title": "作った写真集", "date": "2026-09-01 00:00:00",
      "affiliateURL": "https://al.fanza.co.jp/?lurl=https%3A%2F%2Fbook.dmm.co.jp%2Fproduct%2F1%2Fb123abc456%2F&af_id=test-990&ch=api",
      "imageURL": {"large": "https://ebook-assets.dmm.co.jp/digital/e-book/b123abc456/b123abc456pl.jpg"},
      "tachiyomi": {"URL": "https://book.dmm.co.jp/tachiyomi/?cid=b123abc456", "affiliateURL": "https://al.fanza.co.jp/?lurl=https%3A%2F%2Fbook.dmm.co.jp%2Ftachiyomi%2F&af_id=test-990&ch=api"},
      "iteminfo": {"manufacture": [{"id": 77, "name": "作った出版社"}], "author": [{"id": 3, "name": "作った写真家"}]}}
it = D.parse_floor_item(bk, "photo")
check("ブックス: 出版社をメーカーの代わりに・ebook-assets の表紙・立ち読みのページ・サンプル画像は無し",
      it and it["maker"] == "作った出版社" and it["maker_id"] == 77 and it["image_url"].startswith("https://ebook-assets.dmm.co.jp/") and it["trial_url"].startswith("https://al.fanza.co.jp/")
      and it["sample_images"] == [] and it["authors"] == ["作った写真家"], it)
check("出演者・レーベル・監督・出版社の名前でも、未成年を連想させる作品は入れない",
      D.blocked_reason(dict(am, iteminfo=dict(am["iteminfo"], actress=[{"name": "女子校生A"}]))) == "出演者"
      and D.blocked_reason(dict(am, iteminfo=dict(am["iteminfo"], label=[{"name": "ロリ系レーベル"}]))) == "レーベル"
      and D.blocked_reason(dict(bk, iteminfo=dict(bk["iteminfo"], manufacture=[{"name": "女子中学生出版"}]))) == "出版社"
      and D.blocked_reason(am) == "")
check("保存の形: 出演者・サンプル動画・立ち読みも1行に（FANZA以外のURLは捨てる）",
      F.clean_item(dict(it, sample_movie="https://example.com/x", trial_url="javascript:alert(1)"))["sample_movie"] == ""
      and F.clean_item(dict(it, trial_url="javascript:alert(1)"))["trial_url"] == "" and "actress" in F.clean_item(it))

print(f"\n=== {passed}/{passed + failed} 合格 ===")
sys.exit(1 if failed else 0)
