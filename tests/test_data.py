"""保存データ（site/src/data/new_releases.json）が壊れていないかのチェック

毎日の自動更新や手作業の編集で、サイトが落ちるようなデータが入っていないかを確かめます。
実行: python3 tests/test_data.py
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "site", "src", "data", "new_releases.json")

problems = []


def check(name, cond, detail=""):
    print(("  ✅ " if cond else "  ❌ ") + name + (f"  → {detail}" if (detail and not cond) else ""))
    if not cond:
        problems.append(name)


try:
    with open(DATA, encoding="utf-8") as f:
        raw = json.load(f)
except (OSError, json.JSONDecodeError) as e:
    print(f"  ❌ データを読めません: {e}")
    sys.exit(1)

check("全体が配列(リスト)になっている", isinstance(raw, list))
items = [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []
check("すべて項目(辞書)になっている", len(items) == len(raw))

cids = [str(x.get("cid", "")).strip() for x in items]
check("cid がすべてある", all(cids))
check("cid の重複がない", len(set(cids)) == len(cids), [c for c in set(cids) if cids.count(c) > 1][:5])
check("タイトルがすべてある", all(str(x.get("title", "")).strip() for x in items))
check("発売日が YYYY-MM-DD で始まる", all(re.match(r"^\d{4}-\d{2}-\d{2}", str(x.get("date", ""))) for x in items))
check("コメントがすべてある", all(str(x.get("comment", "")).strip() for x in items))
check("comment_kind は ai（Geminiの下書き）・claude（Claudeが仕上げ）・template（定型文）のどれか", all(x.get("comment_kind") in ("ai", "claude", "template") for x in items),
      {x.get("comment_kind") for x in items})
jst_tomorrow = (datetime.now(timezone(timedelta(hours=9))) + timedelta(days=1)).strftime("%Y-%m-%d")
check("更新日(updated)がすべてある（YYYY-MM-DD）", all(re.match(r"^\d{4}-\d{2}-\d{2}$", str(x.get("updated", ""))) for x in items),
      [x.get("cid") for x in items if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(x.get("updated", "")))][:5])
check("更新日が未来の日付になっていない（sitemapのlastmodに使うため）", all(str(x.get("updated", "")) <= jst_tomorrow for x in items),
      [x.get("cid") for x in items if str(x.get("updated", "")) > jst_tomorrow][:5])
def _ok_movie(x):
    v = x.get("sample_movie")
    if not isinstance(v, str):
        return False
    if v == "":
        return True
    m = re.match(r"^https://([A-Za-z0-9.\-]+)/", v)
    return bool(m) and (m.group(1) == "dmm.co.jp" or m.group(1).endswith(".dmm.co.jp"))


check("サンプル動画(sample_movie)は、空かFANZA(DMM)のhttps", all(_ok_movie(x) for x in items), [x.get("cid") for x in items if not _ok_movie(x)][:5])
check("動画の取り直し回数(movie_tries)は 0 以上の整数", all(isinstance(x.get("movie_tries"), int) and not isinstance(x.get("movie_tries"), bool) and x.get("movie_tries") >= 0 for x in items),
      [x.get("cid") for x in items if not isinstance(x.get("movie_tries"), int)][:5])
check("アフィリエイトのURLは https", all(str(x.get("url", "")).startswith("https://") for x in items if x.get("url")))
check("cid はURLに使える文字だけ", all(re.match(r"^[A-Za-z0-9_\-]+$", c) for c in cids), [c for c in cids if not re.match(r"^[A-Za-z0-9_\-]+$", c)][:5])



def _entry_ok(x, key):
    """シリーズ・レーベル（2026-10-07 から保存）: id は0以上の整数・名前は文字。無いときは 0 と空、あるときは 1以上と空でない名前（「----」は無しとして保存しない）"""
    i, n = x.get(key + "_id"), x.get(key)
    if not (isinstance(i, int) and not isinstance(i, bool) and i >= 0 and isinstance(n, str)):
        return False
    return (i == 0 and n == "") or (i >= 1 and n.strip() == n and n not in ("", "----") and len(n) <= 80)


check("シリーズ・レーベル: どの作品にも series_id・series・label_id・label がある（無いときは 0 と空）",
      all(_entry_ok(x, "series") and _entry_ok(x, "label") for x in items), [x.get("cid") for x in items if not (_entry_ok(x, "series") and _entry_ok(x, "label"))][:5])
text = open(DATA, encoding="utf-8").read()
check("APIキーらしき文字列が入っていない", not re.search(r"AIza[0-9A-Za-z_\-]{20,}", text))

# ---- 出演者データ（actresses.json）と売れ筋ランキング（ranking.json）。毎日の更新が作る（まだ無いあいだは点検しない） ----
print("\n■ 出演者データ（actresses.json）・女優検索の名簿（actress_directory.json）・売れ筋ランキング（ranking.json）")
ACTRESSES = os.path.join(ROOT, "site", "src", "data", "actresses.json")
RANKING = os.path.join(ROOT, "site", "src", "data", "ranking.json")
FANZA_IMG = re.compile(r"^https://([A-Za-z0-9.\-]+)/")


def _fanza_https(v, hosts):
    m = FANZA_IMG.match(v) if isinstance(v, str) else None
    return bool(m) and any(m.group(1) == h or m.group(1).endswith("." + h) for h in hosts)


def _num_ok(v, lo, hi):
    return v is None or (isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi)


if not os.path.exists(ACTRESSES):
    print("  （actresses.json はまだありません。最初の毎日の更新で作られます）")
else:
    try:
        act_raw = json.load(open(ACTRESSES, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        act_raw = None
        check("actresses.json を読める", False, str(e))
    if act_raw is not None:
        check("actresses.json: {actresses: [...], unmatched: {...}} の形", isinstance(act_raw, dict) and isinstance(act_raw.get("actresses"), list) and isinstance(act_raw.get("unmatched"), dict))
        rows = [r for r in act_raw.get("actresses", []) if isinstance(r, dict)] if isinstance(act_raw, dict) else []
        ids = [str(r.get("id", "")) for r in rows]
        check("出演者: id は数字だけで重複がない・名前がある", all(re.fullmatch(r"\d{1,12}", i) for i in ids) and len(set(ids)) == len(ids) and all(str(r.get("name", "")).strip() for r in rows))
        check("出演者: 使う項目だけを持つ（血液型・趣味・出身地などは持たない）",
              all(set(r) == {"id", "name", "ruby", "image_small", "image_large", "bust", "cup", "waist", "hip", "height", "birthday", "list_url", "fetched"} for r in rows),
              sorted({k for r in rows for k in r})[:20])
        check("出演者: 顔写真・全作品リンクは、空かFANZA(DMM)のhttps", all(_fanza_https(r.get("image_small"), ["dmm.co.jp"]) or r.get("image_small") == "" for r in rows) and all(_fanza_https(r.get("image_large"), ["dmm.co.jp"]) or r.get("image_large") == "" for r in rows) and all(_fanza_https(r.get("list_url"), ["fanza.co.jp", "dmm.co.jp"]) or r.get("list_url") == "" for r in rows))

        check("出演者: 体型は、空か範囲内の整数（バスト50〜160・ウエスト40〜130・ヒップ50〜160・身長120〜210）・カップは英字1文字か空",
              all(_num_ok(r.get("bust"), 50, 160) and _num_ok(r.get("waist"), 40, 130) and _num_ok(r.get("hip"), 50, 160) and _num_ok(r.get("height"), 120, 210) and re.fullmatch(r"[A-Z]?", str(r.get("cup", "x"))) for r in rows))

        def _age_ok(b):
            if b == "":
                return True
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(b)):
                return False
            y, mo, d = int(b[:4]), int(b[5:7]), int(b[8:10])
            now = datetime.now(timezone(timedelta(hours=9)))
            age = now.year - y - ((now.month, now.day) < (mo, d))
            return 18 <= age <= 80

        check("出演者: 生年月日は空か、年齢が18〜80歳になる日付（18歳未満になる値は持たない）", all(_age_ok(r.get("birthday", "")) for r in rows), [r["name"] for r in rows if not _age_ok(r.get("birthday", ""))][:5])
        check("出演者: 取得日は空か YYYY-MM-DD", all(re.fullmatch(r"(\d{4}-\d{2}-\d{2})?", str(r.get("fetched", "x"))) for r in rows))
        check("見つからなかった名前: 値は YYYY-MM-DD", all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v)) for v in act_raw.get("unmatched", {}).values()))
        check("出演者データに、APIのIDらしき文字列が入っていない", "api_id" not in open(ACTRESSES, encoding="utf-8").read())

# ---- 女優検索の名簿（actress_directory.json）。FANZA公式の出演者検索の一覧から、毎日少しずつ作る ----
DIRECTORY = os.path.join(ROOT, "site", "src", "data", "actress_directory.json")
if not os.path.exists(DIRECTORY):
    print("  （actress_directory.json はまだありません。毎日の更新で作られます）")
else:
    try:
        dir_raw = json.load(open(DIRECTORY, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        dir_raw = None
        check("actress_directory.json を読める", False, str(e))
    if dir_raw is not None:
        check("名簿: {cursor: {filter, offset}, cycle_done, rows: [...]} の形",
              isinstance(dir_raw, dict) and isinstance(dir_raw.get("rows"), list) and isinstance(dir_raw.get("cursor"), dict)
              and re.fullmatch(r"(\d{4}-\d{2}-\d{2})?", str(dir_raw.get("cycle_done", "x"))))
        drows = [r for r in dir_raw.get("rows", []) if isinstance(r, dict)] if isinstance(dir_raw, dict) else []
        dids = [str(r.get("id", "")) for r in drows]
        check("名簿: id は数字だけで重複がない・名前がある・id の順", all(re.fullmatch(r"\d{1,12}", i) for i in dids) and len(set(dids)) == len(dids)
              and all(str(r.get("name", "")).strip() for r in drows) and dids == sorted(dids, key=int))
        check("名簿: 使う項目だけを持つ（血液型・趣味・出身地・URLなどは持たない）",
              all(set(r) == {"id", "name", "ruby", "img", "bust", "cup", "waist", "hip", "height", "birthday", "seen"} for r in drows),
              sorted({k for r in drows for k in r})[:20])
        check("名簿: 顔写真は、FANZAの画像のファイル名（英小文字・数字・_）か空", all(re.fullmatch(r"[a-z0-9_]{0,60}", str(r.get("img", "x"))) for r in drows))
        check("名簿: 体型は、空か範囲内の整数・カップは英字1文字か空",
              all(_num_ok(r.get("bust"), 50, 160) and _num_ok(r.get("waist"), 40, 130) and _num_ok(r.get("hip"), 50, 160) and _num_ok(r.get("height"), 120, 210) and re.fullmatch(r"[A-Z]?", str(r.get("cup", "x"))) for r in drows))

        def _adult_birthday(b):
            # 18歳未満になる値は持たない（毎日の更新で、80歳をこえた人の生年月日は消える。サイトに出すのも18〜80歳だけ）
            if b == "":
                return True
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(b)):
                return False
            y, mo, d = int(b[:4]), int(b[5:7]), int(b[8:10])
            now = datetime.now(timezone(timedelta(hours=9)))
            return now.year - y - ((now.month, now.day) < (mo, d)) >= 18

        check("名簿: 最後に見かけた日（seen）・一回りを始めた日は YYYY-MM-DD（一回りの始まりは、ひとつ前の分だけ空でもよい）",
              all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("seen", ""))) for r in drows)
              and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(dir_raw.get("cycle_start", ""))) and re.fullmatch(r"(\d{4}-\d{2}-\d{2})?", str(dir_raw.get("prev_cycle_start", "x"))))
        check("名簿: 生年月日は空か、18歳以上になる日付", all(_adult_birthday(r.get("birthday", "")) for r in drows), [r.get("id") for r in drows if not _adult_birthday(r.get("birthday", ""))][:5])
        check("名簿: どの人にも、検索に使える項目（体型・身長・生年月日）がある", all(any(r.get(k) for k in ("bust", "waist", "hip", "height", "birthday")) for r in drows))
        check("名簿に、APIのIDらしき文字列が入っていない", "api_id" not in open(DIRECTORY, encoding="utf-8").read())

if not os.path.exists(RANKING):
    print("  （ranking.json はまだありません。最初の毎日の更新で作られます）")
else:
    try:
        rk = json.load(open(RANKING, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        rk = None
        check("ranking.json を読める", False, str(e))
    if rk is not None:
        rk_items = rk.get("items") if isinstance(rk, dict) else None
        check("ranking.json: 日付(YYYY-MM-DD)と items（1〜6本）がある", isinstance(rk, dict) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(rk.get("date", ""))) and isinstance(rk_items, list) and 1 <= len(rk_items) <= 6, rk if not isinstance(rk, dict) else rk.get("date"))
        if isinstance(rk_items, list):
            check("ランキング: 順位は 1,2,3… の順・品番がある", [x.get("rank") for x in rk_items] == list(range(1, len(rk_items) + 1)) and all(str(x.get("cid", "")).strip() for x in rk_items))
            check("ランキング: リンクはFANZAのhttps・画像はFANZA(DMM)のhttps", all(_fanza_https(x.get("url"), ["fanza.co.jp", "dmm.co.jp"]) and (x.get("image_url") == "" or _fanza_https(x.get("image_url"), ["dmm.co.jp"])) for x in rk_items))

# ---- 過去作品（catalog/YYYY-MM.json）。毎日の更新が、FANZAの人気順に少しずつ集める（まだ無いあいだは点検しない） ----
print("\n■ 過去作品（catalog/YYYY-MM.json・catalog_state.json）")
CATALOG_DIR = os.path.join(ROOT, "site", "src", "data", "catalog")
CATALOG_STATE = os.path.join(ROOT, "site", "src", "data", "catalog_state.json")
if not os.path.isdir(CATALOG_DIR):
    print("  （過去作品はまだありません。毎日の更新で、少しずつ集まります）")
else:
    names = sorted(os.listdir(CATALOG_DIR))
    check("過去作品のフォルダには、発売月ごとのファイル（YYYY-MM.json）だけがある", all(re.fullmatch(r"\d{4}-\d{2}\.json", n) for n in names), [n for n in names if not re.fullmatch(r"\d{4}-\d{2}\.json", n)][:3])
    cat_items, bad_files, wrong_month = [], [], []
    for n in names:
        try:
            rows = json.load(open(os.path.join(CATALOG_DIR, n), encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            bad_files.append((n, str(e)[:60]))
            continue
        if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
            bad_files.append((n, "空か、作品の配列ではない"))
            continue
        cat_items += rows
        wrong_month += [r.get("cid") for r in rows if str(r.get("date", ""))[:7] != n[:7]]
    check("過去作品のファイルが、すべて読めて、作品（辞書）の配列（空のファイルは無い）", not bad_files, bad_files[:3])
    check("過去作品は、発売月のファイルに入っている", not wrong_month, wrong_month[:5])
    ccids = [str(x.get("cid", "")).strip() for x in cat_items]
    check(f"過去作品（{len(cat_items)}本）: cid がすべてあり、重複がない・URLに使える文字だけ", all(ccids) and len(set(ccids)) == len(ccids) and all(re.match(r"^[A-Za-z0-9_\-]+$", c) for c in ccids),
          [c for c in set(ccids) if ccids.count(c) > 1][:5])
    # 同じ作品が両方にあっても、サイトは毎日の更新のほうを使い、次の毎日の更新が過去作品から外すので、失敗にはしない（知らせるだけ）
    both = sorted(set(ccids) & set(cids))
    print(("  ✅ " if not both else "  ⚠️ ") + "過去作品に、毎日の更新で載せた作品（new_releases.json）と同じ作品が無い" + (f"  → {len(both)}本（次の毎日の更新で外れます）: {both[:5]}" if both else ""))
    check("過去作品: タイトル・発売日（YYYY-MM-DD）がすべてある", all(str(x.get("title", "")).strip() and re.match(r"^\d{4}-\d{2}-\d{2}", str(x.get("date", ""))) for x in cat_items))
    check("過去作品のコメントは、無し（none・空）か、Claude が書いたもの（claude・空でない）だけ",
          all((x.get("comment_kind") == "none" and x.get("comment") == "") or (x.get("comment_kind") == "claude" and str(x.get("comment", "")).strip()) for x in cat_items),
          [(x.get("cid"), x.get("comment_kind")) for x in cat_items if x.get("comment_kind") not in ("none", "claude")][:5])
    check("過去作品: 更新日(updated)が YYYY-MM-DD で、未来の日付ではない", all(re.match(r"^\d{4}-\d{2}-\d{2}$", str(x.get("updated", ""))) and str(x.get("updated")) <= jst_tomorrow for x in cat_items))
    check("過去作品: リンクは FANZA の https・サンプル動画は空かFANZA(DMM)のhttps・動画の取り直し回数は 0 以上の整数",
          all(_fanza_https(x.get("url"), ["fanza.co.jp", "dmm.co.jp"]) and _ok_movie(x) and isinstance(x.get("movie_tries"), int) and not isinstance(x.get("movie_tries"), bool) and x["movie_tries"] >= 0 for x in cat_items),
          [x.get("cid") for x in cat_items if not (_fanza_https(x.get("url"), ["fanza.co.jp", "dmm.co.jp"]) and _ok_movie(x))][:5])
    check("過去作品: サンプル画像は8枚まで", all(isinstance(x.get("sample_images"), list) and len(x["sample_images"]) <= 8 for x in cat_items))
    check("過去作品: シリーズ・レーベルの項目がある（無いときは 0 と空）", all(_entry_ok(x, "series") and _entry_ok(x, "label") for x in cat_items),
          [x.get("cid") for x in cat_items if not (_entry_ok(x, "series") and _entry_ok(x, "label"))][:5])
    check("過去作品のファイルに、APIキーらしき文字列が入っていない", not any(re.search(r"AIza[0-9A-Za-z_\-]{20,}", open(os.path.join(CATALOG_DIR, n), encoding="utf-8").read()) for n in names))
    try:
        cst = json.load(open(CATALOG_STATE, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        cst = None
    check("続きの場所（catalog_state.json）: cursor は 1〜50000・cycle（一回りの番号）は1以上・cycle_done は空か日付・limit は5万まで・items は過去作品の本数",
          isinstance(cst, dict) and isinstance(cst.get("cursor"), int) and 1 <= cst["cursor"] <= 50000 and isinstance(cst.get("cycle"), int) and cst["cycle"] >= 1
          and re.fullmatch(r"(\d{4}-\d{2}-\d{2})?", str(cst.get("cycle_done", ""))) is not None
          and isinstance(cst.get("limit"), int) and 1 <= cst["limit"] <= 50000 and cst.get("items") == len(cat_items), cst)
    CATALOG_RANK = os.path.join(ROOT, "site", "src", "data", "catalog_rank.json")
    try:
        crank = json.load(open(CATALOG_RANK, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        crank = None
    check("人気順の順位（catalog_rank.json）: {cid: [順位 1〜50000, 一回りの番号 1以上]} の形",
          isinstance(crank, dict) and all(isinstance(v, list) and len(v) == 2 and all(isinstance(n, int) and not isinstance(n, bool) for n in v) and 1 <= v[0] <= 50000 and 1 <= v[1] for v in crank.values()),
          str(crank)[:80])
    if isinstance(crank, dict):
        # 順位と作品が食い違っても、サイトは順位の無い作品を後ろに回すだけで、次の毎日の更新がそろえるので、失敗にはしない（知らせるだけ）
        odd = sorted(set(crank) ^ set(ccids))
        print(("  ✅ " if not odd else "  ⚠️ ") + "順位のある作品 = 過去作品" + (f"  → 食い違い {len(odd)}本（次の毎日の更新でそろいます）: {odd[:5]}" if odd else ""))

# ---- 人気順（popularity.json）・セール（sale.json）。毎日の更新が、その日のFANZAの人気順・キャンペーンから作る（まだ無いあいだは点検しない） ----
print("\n■ 人気順（popularity.json）・セール（sale.json）")
POPULARITY = os.path.join(ROOT, "site", "src", "data", "popularity.json")
SALE = os.path.join(ROOT, "site", "src", "data", "sale.json")
_rank_ok = lambda v: isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 50000
if not os.path.exists(POPULARITY):
    print("  （popularity.json はまだありません。毎日の更新で作られます）")
else:
    try:
        popj = json.load(open(POPULARITY, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        popj = None
        check("popularity.json を読める", False, str(e))
    if popj is not None:
        check("popularity.json: 日付（空か YYYY-MM-DD）・new と all が {cid: 順位 1〜50000} の形・日付が未来でない",
              isinstance(popj, dict) and re.fullmatch(r"(\d{4}-\d{2}-\d{2})?", str(popj.get("date", ""))) is not None and str(popj.get("date", "")) <= jst_tomorrow
              and all(isinstance(popj.get(k), dict) and all(_rank_ok(v) for v in popj[k].values()) for k in ("new", "all"))
              and isinstance(popj.get("prev", {}), dict) and all(_rank_ok(v) for v in popj.get("prev", {}).values()) and re.fullmatch(r"(\d{4}-\d{2}-\d{2})?", str(popj.get("prev_date", ""))) is not None, str(popj)[:80])
RANK_HISTORY = os.path.join(ROOT, "site", "src", "data", "rank_history.json")
if not os.path.exists(RANK_HISTORY):
    print("  （rank_history.json はまだありません。毎日の更新で作られます）")
else:
    try:
        rhj = json.load(open(RANK_HISTORY, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        rhj = None
        check("rank_history.json を読める", False, str(e))
    if rhj is not None:
        _rv = lambda v: v is None or (isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 50000)
        rows_rh = rhj.get("items") if isinstance(rhj, dict) else None
        check("人気の動き（rank_history.json）: 更新日・作品ごとに {d: 記録を始めた日, n: 新着の人気順（8日分まで）, a: 全体の人気順（30日分まで）}。順位は 0（圏外）〜50000 か null（分からない日）・未来の日付でない",
              isinstance(rows_rh, dict) and re.fullmatch(r"(\d{4}-\d{2}-\d{2})?", str(rhj.get("updated", ""))) is not None and str(rhj.get("updated", "")) <= jst_tomorrow
              and all(re.fullmatch(r"[A-Za-z0-9_\-]+", c) and isinstance(r, dict) and set(r) == {"d", "n", "a"} and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r["d"])) and r["d"] <= jst_tomorrow
                      and isinstance(r["n"], list) and len(r["n"]) <= 8 and all(_rv(v) for v in r["n"]) and isinstance(r["a"], list) and len(r["a"]) <= 30 and all(_rv(v) for v in r["a"])
                      for c, r in rows_rh.items()), str(rhj)[:80])
        print(f"  （人気の動き: 記録中 {len(rows_rh or {})}本）")
TODAY_JSON = os.path.join(ROOT, "site", "src", "data", "today.json")
if not os.path.exists(TODAY_JSON):
    print("  （today.json はまだありません。毎日の更新で作られます）")
else:
    try:
        tdj = json.load(open(TODAY_JSON, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        tdj = None
        check("today.json を読める", False, str(e))
    if tdj is not None:
        _day = lambda v: re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v or "")) is not None
        check("today.json: 日付・日ごとの発売本数（d・n）・予約受付中の本数・予約の人気順（c・t・d・r。リンクと画像は FANZA の https）・前の日の作品ID",
              isinstance(tdj, dict) and _day(tdj.get("date")) and str(tdj.get("date")) <= jst_tomorrow
              and isinstance(tdj.get("daily"), list) and all(isinstance(d, dict) and _day(d.get("d")) and isinstance(d.get("n"), int) and d["n"] >= 0 for d in tdj["daily"])
              and isinstance(tdj.get("upcoming_total"), int) and isinstance(tdj.get("upcoming"), list)
              and all(isinstance(r, dict) and str(r.get("c", "")).strip() and str(r.get("t", "")).strip() and _day(r.get("d")) and _rank_ok(r.get("r"))
                      and (not r.get("u") or _fanza_https(r["u"], ["fanza.co.jp", "dmm.co.jp"])) and (not r.get("i") or _fanza_https(r["i"], ["dmm.co.jp"])) for r in tdj["upcoming"])
              and isinstance(tdj.get("prev_upcoming", []), list), str(tdj)[:80])
if not os.path.exists(SALE):
    print("  （sale.json はまだありません。毎日の更新で作られます）")
else:
    try:
        salej = json.load(open(SALE, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        salej = None
        check("sale.json を読める", False, str(e))
    if salej is not None:
        camps = salej.get("campaigns") if isinstance(salej, dict) else None
        rows = salej.get("items") if isinstance(salej, dict) else None
        check("sale.json: 日付・キャンペーン（名前・始まり・終わり）・作品（c 作品ID・k キャンペーンの番号・p 価格 < l 定価。価格は無いこともある）",
              isinstance(camps, list) and isinstance(rows, list) and re.fullmatch(r"(\d{4}-\d{2}-\d{2})?", str(salej.get("date", ""))) is not None
              and all(isinstance(c, dict) and str(c.get("title", "")).strip() and re.match(r"^\d{4}-\d{2}-\d{2}", str(c.get("end", ""))) for c in camps)
              and all(isinstance(r, dict) and str(r.get("c", "")).strip() and isinstance(r.get("k"), int) and 0 <= r["k"] < len(camps)
                      and (("p" not in r and "l" not in r) or (isinstance(r.get("p"), int) and isinstance(r.get("l"), int) and 0 < r["p"] < r["l"])) for r in rows),
              str(salej)[:80])
        extra = salej.get("extra", []) if isinstance(salej, dict) else None
        check("sale.json: このサイトに無いセール中の作品（extra。順位 r・タイトル t・FANZAのURL u・画像 i・発売日 d・メーカー m・出演者 a・ジャンル g）・特集の本数 n（数字）",
              isinstance(extra, list) and isinstance(camps, list)
              and all(isinstance(r, dict) and str(r.get("c", "")).strip() and isinstance(r.get("k"), int) and 0 <= r["k"] < len(camps) and isinstance(r.get("r"), int) and r["r"] >= 1
                      and str(r.get("t", "")).strip() and str(r.get("u", "")).startswith("https://") and str(r.get("i", "")).startswith("https://")
                      and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("d", ""))) and isinstance(r.get("m"), str) and isinstance(r.get("a"), list) and isinstance(r.get("g"), list)
                      and (("p" not in r and "l" not in r) or (isinstance(r.get("p"), int) and isinstance(r.get("l"), int) and 0 < r["p"] < r["l"])) for r in extra)
              and all(isinstance(c.get("n", 1), int) and c.get("n", 1) > 0 for c in camps if isinstance(c, dict)), str(extra)[:80])

SALE_HISTORY = os.path.join(ROOT, "site", "src", "data", "sale_history.json")
if not os.path.exists(SALE_HISTORY):
    print("  （sale_history.json はまだありません。毎日の更新で作られます）")
else:
    try:
        sh = json.load(open(SALE_HISTORY, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        sh = None
        check("sale_history.json を読める", False, str(e))
    if sh is not None:
        rows_h = sh.get("campaigns") if isinstance(sh, dict) else None
        _dt = r"\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?"
        check("sale_history.json: 更新日・キャンペーン（名前・始まり・終わり・最初と最後に見かけた日・本数・最大の割引だけ）・名前と始まりの組は1つずつ・新しい順",
              isinstance(rows_h, list) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(sh.get("updated", ""))) is not None
              and all(isinstance(r, dict) and set(r) <= {"title", "begin", "end", "first", "last", "count", "max_off"} and str(r.get("title", "")).strip()
                      and re.fullmatch(f"({_dt})?", str(r.get("begin", ""))) and re.fullmatch(_dt, str(r.get("end", "")))
                      and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("first", ""))) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("last", "")))
                      and r["first"] <= r["last"] and isinstance(r.get("count"), int) and r["count"] >= 0
                      and ("max_off" not in r or (isinstance(r["max_off"], int) and 0 < r["max_off"] < 100)) for r in rows_h)
              and len({(r["title"], r["begin"]) for r in rows_h}) == len(rows_h)
              and [(r["begin"] or r["first"]) for r in rows_h] == sorted([(r["begin"] or r["first"]) for r in rows_h], reverse=True),
              str(sh)[:120])

# ---- FANZA同人・FANZAゲームなどの売り場の人気の動き・セールの記録（scripts/floor_history.py。2026-10-09 から。新しい売り場は 2026-10-10 から）----
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import floor_history as _FH  # noqa: E402
_FKEYS = set(_FH.FLOOR_KEYS)
FLOOR_RH = os.path.join(ROOT, "site", "src", "data", "floor_rank_history.json")
if not os.path.exists(FLOOR_RH):
    print("  （floor_rank_history.json はまだありません。毎日の更新で作られます）")
else:
    try:
        frh = json.load(open(FLOOR_RH, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        frh = None
        check("floor_rank_history.json を読める", False, str(e))
    if frh is not None:
        _fv = lambda v: v is None or (isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 100000)
        check("同人・ゲームの人気の動き（floor_rank_history.json）: 更新日・売り場ごとに {cid: {d: 最初の日, r: 順位（30日分まで。0＝圏外・null＝分からない日）}}・未来の日付でない",
              isinstance(frh, dict) and {"updated", "doujin", "game"} <= set(frh) <= {"updated", *_FKEYS} and re.fullmatch(r"(\d{4}-\d{2}-\d{2})?", str(frh.get("updated", ""))) is not None
              and all(isinstance(frh[k], dict) and all(re.fullmatch(r"[A-Za-z0-9_\-]+", c) and isinstance(r, dict) and set(r) == {"d", "r"}
                                                       and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r["d"])) and r["d"] <= jst_tomorrow
                                                       and isinstance(r["r"], list) and len(r["r"]) <= 30 and all(_fv(v) for v in r["r"]) and any(v for v in r["r"])
                                                       for c, r in frh[k].items()) for k in set(frh) - {"updated"}),
              str(frh)[:120])
FLOOR_SH = os.path.join(ROOT, "site", "src", "data", "floor_sale_history.json")
if not os.path.exists(FLOOR_SH):
    print("  （floor_sale_history.json はまだありません。毎日の更新で作られます）")
else:
    try:
        fsh = json.load(open(FLOOR_SH, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        fsh = None
        check("floor_sale_history.json を読める", False, str(e))
    if fsh is not None:
        _d = lambda v: re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v or "")) is not None
        check("同人・ゲームのセールの記録（floor_sale_history.json）: 売り場ごとに days（1日1行・本数・最大の割引）と tags（名前・始まり・最初と最後に見かけた日・本数・割引）だけ",
              isinstance(fsh, dict) and {"updated", "doujin", "game"} <= set(fsh) <= {"updated", *_FKEYS}
              and all(isinstance(fsh[k], dict) and set(fsh[k]) == {"days", "tags"}
                      and all(isinstance(d, dict) and set(d) == {"d", "n", "max"} and _d(d["d"]) and isinstance(d["n"], int) and 0 <= d["max"] < 100 for d in fsh[k]["days"])
                      and len({d["d"] for d in fsh[k]["days"]}) == len(fsh[k]["days"])
                      and all(isinstance(t, dict) and set(t) == {"title", "begin", "first", "last", "count", "off"} and str(t["title"]).strip()
                              and _d(t["first"]) and _d(t["last"]) and t["first"] <= t["last"] and isinstance(t["count"], int) and 0 <= t["off"] < 100 for t in fsh[k]["tags"])
                      for k in set(fsh) - {"updated"}),
              str(fsh)[:120])

# ---- 週のまとめ記事（roundups.json）。Claude が毎週書き足すので、壊れていないかを見張る ----
print("\n■ 週のまとめ記事（roundups.json）")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import claude_comments as cc  # 禁止語・文字の点検は、書き込み時と同じものを使う
import claude_roundups as cr

ROUNDUPS = os.path.join(ROOT, "site", "src", "data", "roundups.json")
try:
    with open(ROUNDUPS, encoding="utf-8") as f:
        rounds = json.load(f)
except (OSError, json.JSONDecodeError) as e:
    print(f"  ❌ roundups.json を読めません: {e}")
    sys.exit(1)

check("roundups.json は配列で、すべて項目(辞書)になっている", isinstance(rounds, list) and all(isinstance(r, dict) for r in rounds))
rounds = [r for r in rounds if isinstance(r, dict)] if isinstance(rounds, list) else []
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
starts = [r.get("week_start") for r in rounds]
check("週の始まり(week_start)がすべて月曜日の日付", all(isinstance(w, str) and DAY.match(w) and cr.week_start_of(w) == w for w in starts), starts[:5])
check("同じ週の記事が重複していない", len(set(starts)) == len(starts))
check("新しい週が先頭に並んでいる", starts == sorted(starts, reverse=True))
check("公開日(written)がすべてあり、その週が終わったあとの日付", all(
    isinstance(r.get("written"), str) and DAY.match(r["written"]) and isinstance(r.get("week_start"), str) and DAY.match(r["week_start"])
    and r["written"] > cr.add_days(r["week_start"], 6) for r in rounds))
check("公開日が未来の日付になっていない", all(str(r.get("written", "")) <= jst_tomorrow for r in rounds))
check("導入文(lead)の文字数・使えない言葉などの点検に通る", all(
    isinstance(r.get("lead"), str) and not cc.text_problems(r["lead"].strip(), cr.LEAD_MIN, cr.LEAD_MAX) for r in rounds),
    [(r.get("week_start"), cc.text_problems(str(r.get("lead", "")).strip(), cr.LEAD_MIN, cr.LEAD_MAX)) for r in rounds][:2])
check("この週の傾向(trend)がすべての記事にあり、文字数・使えない言葉・確かめられない評価などの点検に通る（2026-10-07 から）", all(
    isinstance(r.get("trend"), str) and not cr.trend_text_problems(r["trend"].strip(), str(r.get("lead", "")).strip()) for r in rounds),
    [(r.get("week_start"), cr.trend_text_problems(str(r.get("trend", "")).strip(), str(r.get("lead", "")).strip())) for r in rounds][:2])


def _count_ok(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _facts_ok(f):
    return (isinstance(f, dict) and set(f) == {"total", "prev_total", "vr", "prev_vr", "debut", "genres", "popular"}
            and all(_count_ok(f[k]) for k in ("total", "prev_total", "vr", "prev_vr", "debut"))
            and isinstance(f["genres"], list) and len(f["genres"]) <= cr.TREND_GENRES
            and all(isinstance(g, dict) and set(g) == {"name", "count", "prev"} and g["name"] in cr.CONTENT_GENRES and _count_ok(g["count"]) and _count_ok(g["prev"]) for g in f["genres"])
            and isinstance(f["popular"], list) and len(f["popular"]) <= cr.FACTS_POPULAR
            and all(isinstance(p, dict) and set(p) == {"cid", "best", "days10"} and isinstance(p["cid"], str) and p["cid"]
                    and _count_ok(p["best"]) and p["best"] >= 1 and _count_ok(p["days10"]) for p in f["popular"])
            and [p["best"] for p in f["popular"]] == sorted(p["best"] for p in f["popular"]))


check("書いたときの傾向の数字(facts)が決まった形（本数・前の週・VR・デビュー作・ジャンル6つまで・人気の作品5本まで・順位の順）",
      all(_facts_ok(r.get("facts")) for r in rounds), [r.get("week_start") for r in rounds if not _facts_ok(r.get("facts"))][:3])
by_cid_date = {str(x.get("cid", "")).strip(): str(x.get("date", ""))[:10] for x in items}
picks_ok = all(
    isinstance(r.get("picks"), list) and cr.PICKS_MIN <= len(r["picks"]) <= cr.PICKS_MAX
    and all(isinstance(q, dict) and isinstance(q.get("cid"), str) and isinstance(q.get("note"), str) for q in r["picks"])
    for r in rounds)
check("注目の作品(picks)が3〜6件で、cid と note がある", picks_ok)
if picks_ok:
    check("注目の作品がすべて、その週に発売の、データにある作品", all(
        by_cid_date.get(q["cid"], "") >= r["week_start"] and by_cid_date.get(q["cid"], "") <= cr.add_days(r["week_start"], 6)
        for r in rounds for q in r["picks"]), [(r["week_start"], q["cid"]) for r in rounds for q in r["picks"] if q["cid"] not in by_cid_date][:3])
    check("ひとことの文字数・使えない言葉などの点検に通る", all(
        not cc.text_problems(q["note"].strip(), cr.NOTE_MIN, cr.NOTE_MAX) for r in rounds for q in r["picks"]))
    check("注目の作品に同じ作品が2回入っていない", all(len({q["cid"] for q in r["picks"]}) == len(r["picks"]) for r in rounds))
rtext = open(ROUNDUPS, encoding="utf-8").read()
check("roundups.json にAPIキーらしき文字列が入っていない", not re.search(r"AIza[0-9A-Za-z_\-]{20,}", rtext))

# ---- 月のまとめ記事（monthly.json。2026-10-07 から）。Claude が毎月1日に書き足すので、壊れていないかを見張る ----
print("\n■ 月のまとめ記事（monthly.json）")
import claude_monthly as cm

MONTHLY = os.path.join(ROOT, "site", "src", "data", "monthly.json")
try:
    with open(MONTHLY, encoding="utf-8") as f:
        months = json.load(f)
except (OSError, json.JSONDecodeError) as e:
    print(f"  ❌ monthly.json を読めません: {e}")
    sys.exit(1)
check("monthly.json は配列で、すべて項目(辞書)になっている", isinstance(months, list) and all(isinstance(r, dict) for r in months))
months = [r for r in months if isinstance(r, dict)] if isinstance(months, list) else []
mkeys = [r.get("month") for r in months]
check("月(month)がすべて YYYY-MM", all(isinstance(m, str) and cm.MONTH_RE.match(m) for m in mkeys), mkeys[:5])
check("同じ月の記事が重複していない", len(set(mkeys)) == len(mkeys))
check("新しい月が先頭に並んでいる", mkeys == sorted(mkeys, reverse=True))
check("公開日(written)がすべてあり、その月が終わったあと・未来でない日付", all(
    isinstance(r.get("written"), str) and DAY.match(r["written"]) and isinstance(r.get("month"), str) and cm.MONTH_RE.match(r["month"])
    and cm.month_last(r["month"]) < r["written"] <= jst_tomorrow for r in months))
check("導入文・傾向が点検に通る", all(
    isinstance(r.get("lead"), str) and not cc.text_problems(r["lead"].strip(), cm.LEAD_MIN, cm.LEAD_MAX)
    and isinstance(r.get("trend"), str) and not cr.trend_text_problems(r["trend"].strip(), r["lead"].strip()) for r in months))
check("書いたときの傾向の数字(facts)が、週のまとめと同じ決まった形", all(_facts_ok(r.get("facts")) for r in months))
mpicks_ok = all(isinstance(r.get("picks"), list) and cm.PICKS_MIN <= len(r["picks"]) <= cm.PICKS_MAX
                and all(isinstance(q, dict) and isinstance(q.get("cid"), str) and isinstance(q.get("note"), str) for q in r["picks"]) for r in months)
check("注目の作品(picks)が4〜8件で、cid と note がある", mpicks_ok)
if mpicks_ok:
    check("注目の作品がすべて、その月に発売の、データにある作品（重複なし）", all(
        by_cid_date.get(q["cid"], "")[:7] == r["month"] for r in months for q in r["picks"]) and all(len({q["cid"] for q in r["picks"]}) == len(r["picks"]) for r in months))
    check("ひとことが点検に通る", all(not cc.text_problems(q["note"].strip(), cm.NOTE_MIN, cm.NOTE_MAX) for r in months for q in r["picks"]))
check("monthly.json にAPIキーらしき文字列が入っていない", not re.search(r"AIza[0-9A-Za-z_\-]{20,}", open(MONTHLY, encoding="utf-8").read()))

print("\n■ FANZA同人・FANZAゲーム（site/src/data/doujin.json・game.json。2026-10-09 から。まだ無ければ見ない）")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import floor_data as FD  # noqa: E402
floor_counts = {}
for key in FD.FLOORS:
    fpath = os.path.join(ROOT, "site", "src", "data", FD.FLOORS[key]["file"])
    if not os.path.exists(fpath):
        print(f"  （{FD.FLOORS[key]['label']}のデータはまだありません）")
        continue
    label = FD.FLOORS[key]["label"]
    try:
        fdata = FD.load_floor(fpath)
    except ValueError as e:
        check(f"{label}: 読める", False, e)
        continue
    ftext = open(fpath, encoding="utf-8").read()
    raw_rows = json.loads(ftext)["items"]
    floor_counts[key] = len(fdata["items"])
    check(f"{label}: 読める・決まった項目だけ・書き方がそろっている（読んで書き直しても同じ）", len(raw_rows) == len(fdata["items"]) and FD.dump_floor(fdata) == ftext)
    fitems = list(fdata["items"].values())
    check(f"{label}: URL はアフィリエイトの FANZA の https・画像は DMM の https", all(
        re.match(r"^https://al\.fanza\.co\.jp/", x["url"]) and (not x["image_url"] or re.match(r"^https://[a-z0-9.-]+\.dmm\.co\.jp/", x["image_url"])) for x in fitems))
    check(f"{label}: 未成年を連想させる作品が入っていない（タイトル・ジャンル・シリーズ・サークル/ブランド・作家）", not any(
        cc.title_block_reason({"title": t}) == "minor" for x in fitems for t in [x["title"], *x["genres"], *x["formats"], *x["sales"], x["series"], x["maker"], *x["authors"]] if t),
        [x["cid"] for x in fitems if cc.title_block_reason(x) == "minor"][:5])
    check(f"{label}: Claude のコメントは点検に通る", all(not cc.text_problems(x["comment"], cc.MIN_LEN_SPARSE, cc.MAX_LEN) for x in fitems if x["comment_kind"] == "claude"),
          [x["cid"] for x in fitems if x["comment_kind"] == "claude" and cc.text_problems(x["comment"], cc.MIN_LEN_SPARSE, cc.MAX_LEN)][:5])
    check(f"{label}: 本数が決めた数の範囲（コメントのある作品と予約の分だけ、多くてもよい）", len(fitems) <= FD.FLOORS[key]["target"] + FD.FLOORS[key]["upcoming"] + sum(1 for x in fitems if x["comment_kind"] == "claude"), len(fitems))
    check(f"{label}: APIキーらしき文字列が入っていない", not re.search(r"AIza[0-9A-Za-z_\-]{20,}|api_id=", ftext))
    check(f"{label}: 画像は pics.dmm.co.jp から（doujin-assets はページの中で出ないことがあるため。2026-10-09）", "doujin-assets.dmm.co.jp" not in ftext)

# ---- FANZAのレビューの評価（reviews.json。get_new_releases.py が毎日ためる。2026-10-10 から） ----
print("\n■ レビューの評価（reviews.json）")
REVIEWS = os.path.join(ROOT, "site", "src", "data", "reviews.json")
if not os.path.exists(REVIEWS):
    print("  （reviews.json はまだありません。毎日の更新で作られます）")
else:
    try:
        rvtext = open(REVIEWS, encoding="utf-8").read()
        rv = json.loads(rvtext)
    except (OSError, json.JSONDecodeError) as e:
        rv = None
        check("reviews.json を読める", False, str(e))
    if rv is not None:
        check("reviews.json: 更新日・続きの場所・作品ごとの [平均×100, 件数] だけ（1作品1行）",
              isinstance(rv, dict) and set(rv) == {"updated", "cursor", "items"} and isinstance(rv["items"], dict)
              and all(re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", c) and isinstance(v, list) and len(v) == 2 and all(isinstance(n, int) for n in v) and 100 <= v[0] <= 500 and v[1] >= 1 for c, v in rv["items"].items())
              and (not rv["items"] or rvtext.count("\n") == len(rv["items"]) + 3))

# ---- 読みがな（readings.json。scripts/readings.py が週1回。2026-10-10 から） ----
print("\n■ 読みがな（readings.json）")
READINGS = os.path.join(ROOT, "site", "src", "data", "readings.json")
if not os.path.exists(READINGS):
    print("  （readings.json はまだありません。毎日の更新で作られます）")
else:
    try:
        rdtext = open(READINGS, encoding="utf-8").read()
        rd = json.loads(rdtext)
    except (OSError, ValueError) as e:
        rd = None
        check("readings.json を読める", False, str(e))
    if rd is not None:
        _kinds = {"genre", "maker", "series", "author"}
        _floors = [k for k in rd if k not in ("updated", "next")]
        check("readings.json: 更新日・続きの場所と、売り場ごとの {種類: {キー: 読み}} だけ（1つの読みを1行に）",
              isinstance(rd, dict) and "video" in _floors and isinstance(rd.get("next"), dict)
              and all(isinstance(rd[k], dict) and set(rd[k]) == _kinds and all(isinstance(m, dict) and all(isinstance(a, str) and isinstance(b, str) and 0 < len(b) <= 60 for a, b in m.items()) for m in rd[k].values()) for k in _floors)
              and rdtext.count("\n") >= sum(len(m) for k in _floors for m in rd[k].values()))

# ---- ジャンルの「FANZA全体で人気の作品」（genre_tops.json。scripts/genre_tops.py が毎日。2026-10-10 から） ----
print("\n■ ジャンルの「FANZA全体で人気の作品」（genre_tops.json）")
GENRE_TOPS = os.path.join(ROOT, "site", "src", "data", "genre_tops.json")
if not os.path.exists(GENRE_TOPS):
    print("  （genre_tops.json はまだありません。毎日の更新で作られます）")
else:
    try:
        gttext = open(GENRE_TOPS, encoding="utf-8").read()
        gt = json.loads(gttext)
    except (OSError, ValueError) as e:
        gt = None
        check("genre_tops.json を読める", False, str(e))
    if gt is not None:
        _gt_rows = [r for g in gt.get("genres", {}).values() for r in g.get("items", [])] if isinstance(gt, dict) and isinstance(gt.get("genres"), dict) else None
        check("genre_tops.json: ジャンルごとに id・集めた日・作品（20本まで・c t d a m i u）だけ（1作品1行）",
              _gt_rows is not None and set(gt) == {"updated", "genres"}
              and all(set(g) == {"id", "date", "items"} and isinstance(g["id"], int) and re.match(r"^\d{4}-\d{2}-\d{2}$", g["date"]) and len(g["items"]) <= 20 for g in gt["genres"].values())
              and all({"c", "t", "d", "a", "m", "i", "u"} <= set(r) and set(r) <= {"c", "t", "d", "a", "m", "i", "u", "v"} for r in _gt_rows)
              and (not _gt_rows or gttext.count("\n") == len(_gt_rows) + 2 + 2 * len(gt["genres"])))
        check("genre_tops.json: 未成年を連想させるタイトルの作品は無い", _gt_rows is not None and not [r["t"] for r in _gt_rows if cc.title_block_reason({"title": r["t"]}) == "minor"])

# ---- 10円セール（ten_yen.json。scripts/ten_yen.py が毎日と、開催中は1日に数回。2026-10-09 から） ----
print("\n■ 10円セール（ten_yen.json）")
import ten_yen as TY  # noqa: E402
TEN = os.path.join(ROOT, "site", "src", "data", "ten_yen.json")
if not os.path.exists(TEN):
    print("  （ten_yen.json はまだありません。毎日の更新で作られます）")
else:
    try:
        ten = TY.load(TEN)
        ten_text = open(TEN, encoding="utf-8").read()
    except ValueError as e:
        ten = None
        check("ten_yen.json を読める", False, str(e))
    if ten is not None:
        raw_ten = json.loads(ten_text)
        check("ten_yen.json: 確かめた日時・売り場ごとの10円の作品・開催の記録だけ（書き直しても1文字も変わらない）",
              set(raw_ten) == {"checked", *TY.FLOOR_KEYS, "runs"} and (raw_ten["checked"] == "" or re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", raw_ten["checked"]))
              and TY.dump(ten) == ten_text and len(ten["runs"]) == len(raw_ten["runs"]))
        ten_items = [(k, x) for k in TY.FLOOR_KEYS for x in raw_ten[k]]
        check("ten_yen.json: どの作品も10円・FANZAのURL・決まった項目（動画は作品データと同じ名前・同人とゲームは doujin.json と同じ名前）",
              all(x.get("price") == TY.PRICE and re.match(r"^https://al\.fanza\.co\.jp/", str(x.get("url") or ""))
                  and set(x) == ({*TY.VIDEO_KEYS, "price", "list_price", "sale_title", "sale_end"} if k == "video" else {*TY.FLOOR_ITEM_KEYS, "price", "list_price", "sale_title", "sale_end", "rank"})
                  for k, x in ten_items), [x.get("cid") for _, x in ten_items][:5])
        check("ten_yen.json: 未成年を連想させる作品が入っていない", not any(
            cc.title_block_reason({"title": t}) == "minor" for _, x in ten_items for t in [x["title"], *x.get("genres", []), x.get("series") or "", x.get("maker") or "", *x.get("authors", [])] if t))
        check("ten_yen.json: APIキーらしき文字列が入っていない", not re.search(r"AIza[0-9A-Za-z_\-]{20,}|api_id=", ten_text))

print(f"\n  （{len(items)}件の作品データ・{len(rounds)}本の週のまとめ記事・{len(months)}本の月のまとめ記事・同人{floor_counts.get('doujin', 0)}本・ゲーム{floor_counts.get('game', 0)}本を確認）")
if problems:
    print("失敗:", problems)
    sys.exit(1)
print("=== データ形式 OK ===")
