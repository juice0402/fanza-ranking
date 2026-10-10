"""読みがなを集める道具（scripts/readings.py）のテスト。
実行: python3 tests/test_readings.py（ネットには出ない。APIの答えは作ったもの）"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp()
os.environ["READINGS_PATH"] = os.path.join(TMP, "readings.json")
for env in ("DOUJIN_PATH", "GAME_PATH", "ANIME_PATH", "AMATEUR_PATH", "CINEMA_PATH", "COMIC_PATH", "PHOTO_PATH", "VR_PATH"):
    os.environ[env] = os.path.join(TMP, f"{env.lower()}.json")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import readings as R  # noqa: E402
import floor_data as F  # noqa: E402

R.G.DMM_INTERVAL_SEC = 0
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


# APIの一覧（作ったもの）: 売り場ごと・種類ごとに、id・名前・読み
LISTS = {
    (43, "maker"): [{"maker_id": "1", "name": "ムーディーズ", "ruby": "むーでぃーず"}, {"maker_id": "2", "name": "エスワン", "ruby": "えすわん"},
                    {"maker_id": "3", "name": "載っていない", "ruby": "のっていない"}],
    (43, "genre"): [{"genre_id": "10", "name": "巨乳", "ruby": "きょにゅう"}, {"genre_id": "11", "name": "単体作品", "ruby": "たんたいさくひん"}],
    (43, "series"): [{"series_id": str(i), "name": f"シリーズ{i}", "ruby": f"しりーず {i}"} for i in range(1, 8)],
    (81, "maker"): [{"maker_id": "500", "name": "サークルA", "ruby": "さーくるえー"}],
    (80, "author"): [{"author_id": "9", "name": "作家B", "ruby": "さっかびー"}],
}
calls = []


def fake(endpoint, params):
    kind = {"MakerSearch": "maker", "GenreSearch": "genre", "SeriesSearch": "series", "AuthorSearch": "author"}[endpoint]
    calls.append((params["floor_id"], kind, params["offset"], params["hits"]))
    if params["hits"] == 500 and (params["floor_id"], kind) == (43, "genre"):
        raise RuntimeError("hits の範囲の外（テスト）")
    rows = LISTS.get((params["floor_id"], kind), [])
    hits = 3 if kind == "series" else params["hits"]  # シリーズは3件ずつ返す（続きを読むかを見るため）
    page = rows[params["offset"] - 1: params["offset"] - 1 + hits]
    return {"total_count": str(len(rows)), kind: page}


want = {k: {kind: set() for kind in R.KINDS} for k in R.LISTS}
want["video"]["maker"] = {"ムーディーズ", "エスワン", "見つからない"}
want["video"]["genre"] = {"巨乳"}
want["video"]["series"] = {"1", "5", "7"}
want["doujin"]["maker"] = {"500"}
want["game"]["author"] = {"作家B"}

print("■ 読みがなを集める")
check("売り場の id は、動画 43・同人 81・ゲーム 80（作家の一覧はゲームだけ）",
      R.FLOOR_IDS["video"] == 43 and R.FLOOR_IDS["doujin"] == 81 and R.FLOOR_IDS["game"] == 80
      and "author" in R.LISTS["game"] and "author" not in R.LISTS["video"] and "author" not in R.LISTS["doujin"])
lines = R.update("2026-10-10", call=fake, want=want, max_calls=4)
data = json.load(open(R.PATH, encoding="utf-8"))
check("このサイトに載っている名前の読みだけ保存する（メーカーは動画は名前、同人は id で引く。空白はつめる）",
      data["video"]["maker"] == {"ムーディーズ": "むーでぃーず", "エスワン": "えすわん"} and data["video"]["genre"] == {"巨乳": "きょにゅう"}
      and data["video"]["series"] == {"1": "しりーず1", "5": "しりーず5"}, data["video"])
check("500件ずつが使えない一覧は100件ずつで読み直す", (43, "genre", 1, 100) in calls and (43, "genre", 1, 500) in calls, calls)
check("1回に読む回数をこえたら、途中の一覧は次の日に続きから（next）。一回りが終わるまで updated は進めない",
      data["next"].get("video.series") == 7 and data["updated"] == "" and "doujin.maker" in data["next"], data["next"])
calls.clear()
R.update("2026-10-11", call=fake, want=want, max_calls=50)
data = json.load(open(R.PATH, encoding="utf-8"))
check("続きの日は、途中の一覧だけを続きから読む", calls[0] == (43, "series", 7, 500) and all(c[1] != "maker" or c[0] != 43 for c in calls), calls[:3])
check("読み終えたら next が空になり updated が進む・前に集めた読みも残る",
      data["next"] == {} and data["updated"] == "2026-10-11" and data["video"]["series"] == {"1": "しりーず1", "5": "しりーず5", "7": "しりーず7"}
      and data["doujin"]["maker"] == {"500": "さーくるえー"} and data["game"]["author"] == {"作家B": "さっかびー"}, data)
calls.clear()
check("前に集めてから7日たっていない日は、何もしない", "お休み" in R.update("2026-10-15", call=fake, want=want)[0] and calls == [])
want2 = {k: {kind: set(v) for kind, v in kinds.items()} for k, kinds in want.items()}
want2["video"]["maker"] = {"ムーディーズ"}


def broken(endpoint, params):
    if endpoint == "MakerSearch":
        raise RuntimeError("テストの失敗")
    return fake(endpoint, params)


R.update("2026-10-18", call=broken, want=want2)
data = json.load(open(R.PATH, encoding="utf-8"))
check("読めなかった一覧は前の読みのまま。載らなくなった名前の読みは消す",
      data["video"]["maker"] == {"ムーディーズ": "むーでぃーず"} and data["doujin"]["maker"] == {"500": "さーくるえー"}, data["video"]["maker"])
text = open(R.PATH, encoding="utf-8").read()
check("1つの読みを1行に（読み直しても同じ）", R.dump(R.load(R.PATH)) == text and text.count("\n") >= 6)
open(R.PATH, "w").write("{壊れた")
check("漢字の入った読み（FANZAの一覧に、名前がそのまま入っているもの）は使わない", R.clean_ruby("桃太郎 映像") == "" and R.clean_ruby("えす わん") == "えすわん")
check("壊れたファイルは空から（読みは、また集まる）", R.load(R.PATH)["video"]["maker"] == {} and R.load(R.PATH)["next"] == {})

print("\n■ このサイトに載っている名前")
d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, "catalog"))
json.dump([{"cid": "a", "maker": "ムーディーズ", "series_id": 12, "genres": ["巨乳"]}, {"cid": "b", "maker": "不明", "series_id": 0}],
          open(os.path.join(d, "new_releases.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump([{"cid": "c", "maker": "エスワン", "genres": ["単体作品"]}], open(os.path.join(d, "catalog", "2020-01.json"), "w", encoding="utf-8"), ensure_ascii=False)
row = {"cid": "d1", "title": "作品", "date": "2026-10-01", "maker": "サークルA", "maker_id": 500, "series_id": 3, "authors": ["作家C"],
       "genres": ["ファンタジー"], "formats": ["男性向け"]}
open(F.floor_path("doujin"), "w", encoding="utf-8").write(json.dumps({"items": [row]}, ensure_ascii=False))
w = R.wanted(d)
check("動画は毎日の更新と過去作品から（「不明」・シリーズ 0 は入れない）、同人・ゲームは各売り場のデータから",
      w["video"]["maker"] == {"ムーディーズ", "エスワン"} and w["video"]["series"] == {"12"} and w["video"]["genre"] == {"巨乳", "単体作品"}
      and w["doujin"]["maker"] == {"500"} and w["doujin"]["series"] == {"3"} and w["doujin"]["genre"] == {"ファンタジー", "男性向け"}
      and w["doujin"]["author"] == {"作家C"}, w)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
