"""ジャンルの「FANZA全体で人気の作品」を集める道具（scripts/genre_tops.py）のテスト。
実行: python3 tests/test_genre_tops.py（ネットには出ない。APIの答えは作ったもの）"""
import json
import os
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp()
os.environ["GENRE_TOPS_PATH"] = os.path.join(TMP, "genre_tops.json")
os.environ["FLOOR_GENRE_TOPS_PATH"] = os.path.join(TMP, "floor_genre_tops.json")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import genre_tops as T  # noqa: E402

T.G.DMM_INTERVAL_SEC = 0
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


def raw(cid, title="作品", actress=("女優A",), genre=("巨乳",), image=True):
    return {"content_id": cid, "title": title, "date": "2026-09-01 10:00:00", "affiliateURL": f"https://al.fanza.co.jp/?lurl=x&cid={cid}",
            "imageURL": {"large": f"https://pics.dmm.co.jp/digital/video/{cid}/{cid}pl.jpg"} if image else {},
            "iteminfo": {"actress": [{"name": a} for a in actress], "genre": [{"name": g} for g in genre], "maker": [{"name": "メーカー"}]}}


calls = []


def fake(endpoint, params):
    calls.append((endpoint, params.get("article_id"), params.get("sort"), params.get("lte_date", "")[:10]))
    if endpoint == "GenreSearch":
        return {"total_count": "3", "genre": [{"genre_id": "2001", "name": "巨乳"}, {"genre_id": "1031", "name": "痴女"}, {"genre_id": "x", "name": "壊れた"}]}
    if params["article_id"] == 1031:
        raise RuntimeError("テストの失敗")
    rows = [raw(f"a{n:03d}") for n in range(30)]
    rows[0] = raw("minor", title="女子校生の作品")
    rows[1] = raw("minor2", genre=("巨乳", "女子校生"))
    rows[2] = raw("noimg", image=False)
    rows[3] = raw("a004")  # 同じ作品がもう一度
    return {"items": rows}


print("■ ページを作るジャンル")
names = T.page_genres()
check("config.js の TAG_PAGE_GENRES から（ベスト・総集編は除く）", "巨乳" in names and "ベスト・総集編" not in names and len(names) >= 10, names)

print("\n■ 集める")
now = datetime(2026, 10, 10, 0, 5, tzinfo=T.G.JST)
lines = T.update(now, call=fake, genres=["巨乳", "痴女", "無いジャンル"])
data = json.load(open(T.PATH, encoding="utf-8"))
top = data["genres"]["巨乳"]["items"]
check("ジャンルの id で、発売済み（きょうまで）を人気順に", ("ItemList", 2001, "rank", "2026-10-10") in calls, calls)
check("未成年を連想させる作品（タイトル・ジャンル）・画像の無い作品・同じ作品は入れず、20本",
      len(top) == 20 and not any(r["c"] in ("minor", "minor2", "noimg") for r in top) and len({r["c"] for r in top}) == 20, [r["c"] for r in top][:5])
check("作品の形は予約の人気順と同じ（c・t・d・a・m・i・u。順位は並びの順）",
      set(top[0]) >= {"c", "t", "d", "a", "m", "i", "u"} and "r" not in top[0] and top[0]["d"] == "2026-09-01" and top[0]["u"].startswith("https://al.fanza.co.jp/"), top[0])
check("取れなかったジャンル・一覧に無いジャンルは、作らない", set(data["genres"]) == {"巨乳"} and data["updated"] == "2026-10-10", list(data["genres"]))
text = open(T.PATH, encoding="utf-8").read()
check("1作品1行（読み直しても同じ）", T.dump(T.load(T.PATH)) == text and text.count("\n") == 20 + 4, text.count("\n"))

print("\n■ 取れなかった日")


def down(endpoint, params):
    raise RuntimeError("テストの失敗")


T.update(datetime(2026, 10, 15, 0, 5, tzinfo=T.G.JST), call=down, genres=["巨乳"])
data = json.load(open(T.PATH, encoding="utf-8"))
check("前の日の作品のまま（ジャンルの一覧を読めなくても、前の id で試す）", data["genres"]["巨乳"]["date"] == "2026-10-10" and len(data["genres"]["巨乳"]["items"]) == 20)
T.update(datetime(2026, 10, 20, 0, 5, tzinfo=T.G.JST), call=down, genres=["巨乳"])
check("7日をすぎたら消す", json.load(open(T.PATH, encoding="utf-8"))["genres"] == {})
open(T.PATH, "w").write("{壊れた")
check("壊れたファイルは空から", T.load(T.PATH) == {"updated": "", "genres": {}})

print("\n■ 素人の女の子のタイプごとの人気TOP20（floor_genre_tops.json。2026-10-12）")
fcalls = []


def am_raw(cid, title="ゆい", genre=("人妻・主婦",), image=True, url=True):
    return {"content_id": cid, "title": title, "date": "2026-09-01 10:00:00",
            "affiliateURL": f"https://al.fanza.co.jp/?lurl=https%3A%2F%2Fvideo.dmm.co.jp%2Famateur%2Fcontent%2F%3Fid%3D{cid}&af_id=t-990&ch=api" if url else "",
            "imageURL": {"small": f"https://pics.dmm.co.jp/digital/amateur/{cid}/{cid}jp.jpg"} if image else {},
            "volume": "1:00:00", "iteminfo": {"genre": [{"id": 1, "name": g} for g in genre], "maker": [{"id": 5, "name": "素人メーカー"}], "label": [{"id": 6, "name": "素人レーベル"}]}}


def ffake(endpoint, params):
    fcalls.append((endpoint, params.get("floor_id"), params.get("floor"), params.get("article_id"), params.get("sort")))
    if endpoint == "GenreSearch":
        return {"total_count": "2", "genre": [{"genre_id": "6001", "name": "人妻・主婦"}, {"genre_id": "6002", "name": "巨乳"}]}
    if params["article_id"] == 6002:
        raise RuntimeError("テストの失敗")
    rows = [am_raw(f"am{n:03d}") for n in range(30)]
    rows[0] = am_raw("minor", genre=("人妻・主婦", "女子校生"))
    rows[1] = am_raw("noimg", image=False)
    rows[2] = am_raw("am005")  # 同じ作品がもう一度
    return {"items": rows}


check("タイプは floor_data.py の GIRL_TYPES の順（属性・雰囲気・体型）", T.girl_type_names()[:2] == ["人妻・主婦", "熟女"] and "巨乳" in T.girl_type_names() and len(T.girl_type_names()) == len(set(T.girl_type_names())))
flines = T.update_floor_types(now, call=ffake)
fdata = json.load(open(T.FLOOR_PATH, encoding="utf-8"))
ftop = fdata["amateur"]["人妻・主婦"]["items"]
check("素人のジャンルの一覧（floor_id=44）から id を引き、素人（videoc）の人気順で", ("GenreSearch", 44, None, None, None) in fcalls and ("ItemList", None, "videoc", 6001, "rank") in fcalls, fcalls[:3])
check("未成年を連想させる作品・表紙の無い作品・同じ作品は入れず、20本。形は c・t・d・m・i・u だけ",
      len(ftop) == 20 and not any(r["c"] in ("minor", "noimg") for r in ftop) and len({r["c"] for r in ftop}) == 20
      and all(set(r) == {"c", "t", "d", "m", "i", "u"} and r["u"].startswith("https://al.fanza.co.jp/") and r["i"].startswith("https://pics.dmm.co.jp/") for r in ftop), ftop[:1])
check("取れなかったタイプ・一覧に無いタイプは作らない（ほかのタイプは集める）", set(fdata["amateur"]) == {"人妻・主婦"} and fdata["updated"] == "2026-10-10", list(fdata["amateur"]))
ftext = open(T.FLOOR_PATH, encoding="utf-8").read()
check("1作品1行（読み直しても同じ）", T.dump_floor_tops(T.load_floor_tops(T.FLOOR_PATH)) == ftext, ftext[:200])
later = datetime(2026, 10, 12, 0, 5, tzinfo=T.G.JST)
T.update_floor_types(later, call=lambda e, p: (_ for _ in ()).throw(RuntimeError("down")))
check("取れなかった日は、前の日の作品のまま（7日まで）", json.load(open(T.FLOOR_PATH, encoding="utf-8"))["amateur"]["人妻・主婦"]["date"] == "2026-10-10")
open(T.FLOOR_PATH, "w").write("{壊れた")
check("壊れたファイルは空から", T.load_floor_tops(T.FLOOR_PATH) == {"updated": "", "amateur": {}})

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
