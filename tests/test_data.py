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
              and all(isinstance(popj.get(k), dict) and all(_rank_ok(v) for v in popj[k].values()) for k in ("new", "all")), str(popj)[:80])
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

print(f"\n  （{len(items)}件の作品データ・{len(rounds)}本のまとめ記事を確認）")
if problems:
    print("失敗:", problems)
    sys.exit(1)
print("=== データ形式 OK ===")
