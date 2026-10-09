"""get_new_releases.py のテスト（本物のAPIは使わず、偽の応答で動かす）

実行: python3 tests/test_script.py   （どこから実行してもOK）
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import subprocess
import tempfile
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "get_new_releases.py")
# 毎日変わる本番データではなく、固定した20件で試す（テストの結果がぶれないように）
SAVED_DATA = os.path.join(ROOT, "tests", "fixtures", "archive_20items.json")
JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ✅ " if cond else "  ❌ ") + name + (f"  → {detail}" if (detail and not cond) else ""))


class FakeResponse:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


ACTRESS_NAMES = {}  # 出演者の id（文字列）→ 名前（偽のAPIが、出演者の検索に答えるために使う）


def fake_actress_id(name):
    """名前から作る、決まった出演者の id（本物のAPIも、出演者ごとに別の id を返す）"""
    return 100000 + int(hashlib.sha1(name.encode("utf-8")).hexdigest(), 16) % 800000


def make_movie(cid, pc=1, sp=1):
    base = f"https://www.dmm.co.jp/litevideo/-/part/=/cid={cid}"
    return {f"size_{w}_{h}": f"{base}/size={w}_{h}/affi_id=x-990/" for w, h in ((476, 306), (560, 360), (644, 414), (720, 480))} | {"pc_flag": pc, "sp_flag": sp}


def make_api_item(cid, days_from_today, actress=("テスト花子",), maker="テストメーカー", title=None, movie=True, genres=("テストジャンル",)):
    d = (TODAY + timedelta(days=days_from_today)).strftime("%Y-%m-%d 00:00:00")
    for n in actress:
        ACTRESS_NAMES[str(fake_actress_id(n))] = n
    item = {
        "content_id": cid,
        "product_id": cid,
        "title": title or f"【VR】【8K】テスト作品 {cid}",
        "date": d,
        "affiliateURL": f"https://al.fanza.co.jp/?lurl=https%3A%2F%2Fvideo.dmm.co.jp%2Fav%2Fcontent%2F%3Fid%3D{cid}&af_id=x-990",
        "imageURL": {"large": f"https://pics.dmm.co.jp/digital/video/{cid}/{cid}pl.jpg"},
        "sampleImageURL": {"sample_l": {"image": [f"https://pics.dmm.co.jp/digital/video/{cid}/{cid}jp-{i}.jpg" for i in range(1, 4)]}},
        "volume": "120",
        "iteminfo": {
            "maker": [{"id": 1, "name": maker}],
            "actress": [{"id": fake_actress_id(n), "name": n, "ruby": "てすと"} for n in actress],
            "genre": [{"id": 1, "name": g} for g in genres],
        },
    }
    if movie:
        item["sampleMovieURL"] = make_movie(cid)
    return item


# 本物のGeminiが返す形に似せた、利用上限(429)の応答
BODY_QUOTA_DAILY = json.dumps({"error": {
    "code": 429, "status": "RESOURCE_EXHAUSTED",
    "message": "You exceeded your current quota, please check your plan and billing details. "
               "* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash",
    "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "27s"},
    ]}}).encode("utf-8")


def _per_minute_body(delay):
    return json.dumps({"error": {
        "code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Resource has been exhausted (e.g. check quota).",
        "details": [
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
             "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay},
        ]}}).encode("utf-8")


QUOTA_BODIES = {
    "quota_daily": BODY_QUOTA_DAILY,
    "per_minute": _per_minute_body("7s"),
    "wait_too_long": _per_minute_body("3600s"),
}


class Env:
    """偽のネットワーク。シナリオごとに挙動を切り替える"""

    def __init__(self):
        self.gemini_calls = 0
        self.gemini_mode = "mixed"      # mixed / always_error / always_ok
        self.dmm_mode = "ok"            # ok / fail / status400
        self.first_429_done = False
        self.prompts = []
        self.dmm_calls = 0              # FANZA APIを呼んだ回数
        self.queries = []               # FANZA APIを呼んだ内容 [(エンドポイント, {項目: 値})]
        self.by_cid = {}                # 品番を指定した取り直しに答える作品（cid → APIの1件）
        self.actress_rows = {}          # 出演者の検索に答える内容（id → 1件）。無ければ、名前から作った標準の内容
        self.cid_mode = "ok"            # 品番指定の取り直し: ok / fail
        self.actress_mode = "ok"        # 出演者の検索: ok / fail
        self.rank_mode = "ok"           # 売れ筋ランキング: ok / fail
        self.rank_items = None          # 売れ筋ランキングの応答（None なら標準の6本。2位はジャンルがVR・3位は題名がVR・ほかはVRでない）
        self.actress_total_extra = 0    # 名前での出演者検索に「該当は全部で、返した一覧よりこれだけ多い」と答える（一覧が途中で切れた場合）
        self.directory_counts = {"gte_bust": 250, "gte_height": 120, "gte_birthday": 30}  # 一覧（名簿）の、絞り込みごとの人数
        self.directory_fail = False     # 一覧の取得を失敗させる
        self.catalog_total = 250        # 過去作品（人気順の一覧）の本数
        self.catalog_fail = False       # 過去作品の一覧の取得を失敗させる
        self.catalog_overrides = {}     # 過去作品の一覧の n 本目を、この作品に差し替える（n → APIの1件）
        self.new_total = 150            # 新着の人気順（最近30日の発売）の本数
        self.new_overrides = {}         # 新着の人気順の n 本目を差し替える
        self.count_fail = False         # 本数の問い合わせを失敗させる
        self.upcoming_rank_ids = None   # 予約の人気順に答える作品ID（None なら soon001〜soon040）

    def urlopen(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        if "api.dmm.com" in url:
            return self._dmm(url)
        if "generativelanguage.googleapis.com" in url:
            return self._gemini(req)
        raise AssertionError("想定外のURL: " + url)

    def _actress_row(self, aid, name):
        return {"id": str(aid), "name": name, "ruby": "てすと", "bust": "86", "cup": "F", "waist": "57", "hip": "87", "height": "158",
                "birthday": "1999-03-04", "blood_type": "A", "hobby": "散歩", "prefectures": "東京都",
                "imageURL": {"small": f"http://pics.dmm.co.jp/mono/actjpgs/thumbnail/a{aid}.jpg", "large": f"http://pics.dmm.co.jp/mono/actjpgs/a{aid}.jpg"},
                "listURL": {"digital": f"https://al.fanza.co.jp/?lurl=https%3A%2F%2Fvideo.dmm.co.jp%2Fav%2Flist%2F%3Factress%3D{aid}&af_id=x-990"}}

    def _dmm(self, url):
        self.dmm_calls += 1
        parsed = urllib.parse.urlparse(url)
        endpoint = parsed.path.rsplit("/", 1)[-1]
        q = urllib.parse.parse_qs(parsed.query)
        self.queries.append((endpoint, {k: v[0] for k, v in q.items() if k != "api_id"}))
        if self.dmm_mode == "fail":
            raise urllib.error.URLError("network down")
        if self.dmm_mode == "status400":
            return FakeResponse({"result": {"status": 400, "message": "invalid parameter"}})
        if endpoint == "ActressSearch":
            if self.actress_mode == "fail":
                raise urllib.error.URLError("actress api down")
            if "offset" in q:  # 女優検索の名簿のための一覧（絞り込み・id の順・100人ずつ）
                if self.directory_fail:
                    raise urllib.error.URLError("directory api down")
                key = next(k for k in self.directory_counts if k in q)
                total = self.directory_counts[key]
                base_id = {"gte_bust": 100000, "gte_height": 100200, "gte_birthday": 100000}[key]  # 生年月日の一覧は、バストの一覧と同じ人（重なり）
                start = int(q["offset"][0])
                rows = []
                for n in range(start, min(total, start + int(q["hits"][0]) - 1) + 1):
                    aid = base_id + n
                    row = self._actress_row(aid, f"名簿{aid}")
                    if n % 10 == 0:  # 10人に1人は、体型・身長・生年月日が無い（名簿に入れない）
                        row.update(bust=None, waist=None, hip=None, height=None, birthday=None, cup=None)
                    rows.append(row)
                return FakeResponse({"result": {"status": 200, "actress": rows, "total_count": str(total), "result_count": len(rows)}})
            if "actress_id" in q:
                aid = q["actress_id"][0]
                row = self.actress_rows.get(aid) or (self._actress_row(aid, ACTRESS_NAMES[aid]) if aid in ACTRESS_NAMES else None)
                return FakeResponse({"result": {"status": 200, "actress": [row] if row else []}})
            name = q["keyword"][0]
            if name.startswith("不明人"):
                rows = []
            elif name.startswith("同名"):
                rows = [self._actress_row(fake_actress_id(name) + k, name) for k in (0, 1)]
            else:
                rows = [self._actress_row(fake_actress_id(name), name), self._actress_row(fake_actress_id(name + "別人"), name + "別人")]
            result = {"status": 200, "actress": rows}
            if self.actress_total_extra:
                result["total_count"] = len(rows) + self.actress_total_extra
            return FakeResponse({"result": result})
        if q.get("cid"):
            if self.cid_mode == "fail":
                raise urllib.error.URLError("cid api down")
            item = self.by_cid.get(q["cid"][0])
            return FakeResponse({"result": {"status": 200, "items": [item] if item else []}})
        if q.get("hits") == ["1"] and "gte_date" in q and "lte_date" in q and "cid" not in q:  # きょうの数字: その日の発売本数
            if self.count_fail:
                raise urllib.error.URLError("count api down")
            day_ = q["gte_date"][0][:10]
            return FakeResponse({"result": {"status": 200, "items": [], "total_count": str(100 + int(day_[8:10])), "result_count": 0}})
        if q.get("sort", [""])[0] == "rank" and "gte_date" in q and "offset" not in q and q["gte_date"][0][:10] > TODAY.strftime("%Y-%m-%d"):  # 予約の人気順
            ids = self.upcoming_rank_ids or [f"soon{n:03d}" for n in range(1, 41)]
            rows = [make_api_item(c, 2 + n % 20, actress=(f"予約の人{n % 4}",), title=("【VR】" if n == 3 else "") + f"予約の人気作 {n}") for n, c in enumerate(ids, 1)]
            return FakeResponse({"result": {"status": 200, "items": rows[: int(q["hits"][0])], "total_count": "4321"}})
        if q.get("sort", [""])[0] == "rank" and "offset" in q:  # 過去作品（人気順の一覧。発売済みだけ・100本ずつ）
            if self.catalog_fail:
                raise urllib.error.URLError("catalog api down")
            assert q.get("lte_date", [""])[0][:10] == TODAY.strftime("%Y-%m-%d"), "過去作品は、発売済みだけ（lte_date が今日）"
            start = int(q["offset"][0])
            if "gte_date" in q:  # 新着の人気順（最近30日の発売）: 新作 new0001〜（new_total 本）。self.new_overrides で差し替え
                assert q["gte_date"][0][:10] == (TODAY - timedelta(days=7)).strftime("%Y-%m-%d"), "新着の人気順は、最近1週間の発売"
                rows = [self.new_overrides.get(n) or make_api_item(f"new{n:04d}", -(n % 25), actress=(f"新しい人{n % 5}",), title=f"人気の新作 {n}")
                        for n in range(start, min(self.new_total, start + int(q["hits"][0]) - 1) + 1)]
                return FakeResponse({"result": {"status": 200, "items": rows}})
            rows = []
            for n in range(start, min(self.catalog_total, start + int(q["hits"][0]) - 1) + 1):
                rows.append(self.catalog_overrides.get(n) or make_api_item(
                    f"cat{n:05d}", -(40 + n * 3), actress=(f"昔の人{n % 7}",), maker=f"昔のメーカー{n % 3}", title=f"過去作品 {n}",
                    movie=(n % 2 == 0)))
            return FakeResponse({"result": {"status": 200, "items": rows, "total_count": str(self.catalog_total)}})
        if q.get("sort", [""])[0] == "rank":
            if self.rank_mode == "fail":
                raise urllib.error.URLError("rank api down")
            rows = self.rank_items if self.rank_items is not None else [
                make_api_item(f"rank{i}", -5, actress=(f"ランク花子{i}",),
                              title=("【VR】売れ筋" if i == 3 else f"売れ筋 {i}"),
                              genres=(("ハイクオリティVR",) if i == 2 else ("テストジャンル",)))
                for i in range(1, 7)
            ]
            return FakeResponse({"result": {"status": 200, "items": rows[: int(q["hits"][0])]}})
        gte = q.get("gte_date", [""])[0]
        if gte and gte[:10] > TODAY.strftime("%Y-%m-%d"):  # 予約の取得
            items = [make_api_item(f"up{i:03d}", 3 + i) for i in range(8)]
            return FakeResponse({"result": {"status": 200, "items": items[: int(q["hits"][0])]}})
        items = []
        for i in range(30):  # 発売済み。新しい順
            kw = {}
            if i % 3 == 0:
                kw["actress"] = ("ブロック太郎",)  # このプロンプトはブロックされる
            if i == 4:
                kw["actress"] = ()
            items.append(make_api_item(f"rel{i:03d}", -(i // 4), **kw))
        # 既に保存済みの作品（保存データにある cid）も混ぜる → 重複しないことの確認用
        items.insert(2, make_api_item("bibivr00176", -1, actress=("蓮実クレア",), maker="KMPVR-bibi-", movie=False))
        return FakeResponse({"result": {"status": 200, "items": items[: int(q["hits"][0])]}})

    def _gemini(self, req):
        self.gemini_calls += 1
        body = json.loads(req.data.decode("utf-8"))
        prompt = body["contents"][0]["parts"][0]["text"]
        self.prompts.append(prompt)
        assert req.headers.get("X-goog-api-key") or req.headers.get("x-goog-api-key"), "APIキーがヘッダーに無い"
        assert "key=" not in req.full_url, "APIキーがURLに入っている"
        if self.gemini_mode == "always_blocked":
            return FakeResponse({"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}})
        if self.gemini_mode in QUOTA_BODIES and not (self.gemini_mode == "per_minute" and self.gemini_calls > 1):
            raise urllib.error.HTTPError(req.full_url, 429, "rate", {}, io.BytesIO(QUOTA_BODIES[self.gemini_mode]))
        if self.gemini_mode == "always_error":
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b"{}"))
        if self.gemini_mode == "mixed" and not self.first_429_done:
            self.first_429_done = True
            raise urllib.error.HTTPError(req.full_url, 429, "rate", {}, io.BytesIO(b"{}"))
        if self.gemini_mode == "hype":  # 確かめられない評価が入った答え（採用されないはず）
            return FakeResponse({"candidates": [{"content": {"parts": [{"text": "待望の新作が登場。熱い視線が集まる注目の一本です。ぜひご覧ください。"}]}}]})
        if "ブロック太郎" in prompt and self.gemini_mode == "mixed":
            return FakeResponse({"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}})
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "「テスト用のAIコメントです。**上品**に紹介します。」\n"}]}}]})


def load_module(data_path, api_id="fake", gemini="fake", max_calls=None, directory_calls=0, catalog_calls=0, catalog_top=0, catalog_limit=None, new_rank=0, today_stats=False):
    os.environ["DIRECTORY_CALLS"] = str(directory_calls)  # 女優検索の名簿の一覧取得（ふだんのシナリオでは呼ばない。専用のシナリオで試す）
    os.environ["CATALOG_CALLS"] = str(catalog_calls)  # 過去作品の一覧取得（上位より下を続きから。同じく、専用のシナリオで試す）
    os.environ["CATALOG_TOP_CALLS"] = str(catalog_top)  # 過去作品: その日の人気順の上位を取り直す回数
    os.environ["NEW_RANK_CALLS"] = str(new_rank)  # 新着の人気順を取る回数
    os.environ["TODAY_STATS"] = "1" if today_stats else "0"  # きょうの数字（専用のシナリオで試す）
    os.environ["REVIEW_REFETCH_PER_RUN"] = "0"  # レビューの評価の取り直し（品番で取り直す回数に数えないよう、ふだんのシナリオでは呼ばない。tests/test_reviews.py で試す）
    if catalog_limit is None:
        os.environ.pop("CATALOG_LIMIT", None)  # 集める深さ（既定の3万本）
    else:
        os.environ["CATALOG_LIMIT"] = str(catalog_limit)
    os.environ["API_ID"] = api_id
    os.environ["GEMINI_API_KEY"] = gemini
    os.environ["DATA_PATH"] = data_path
    os.environ["GEMINI_INTERVAL_SEC"] = "0"
    os.environ["DMM_INTERVAL_SEC"] = "0"
    if max_calls is None:
        os.environ.pop("GEMINI_MAX_CALLS", None)  # 設定の既定値を使う
    else:
        os.environ["GEMINI_MAX_CALLS"] = str(max_calls)
    spec = importlib.util.spec_from_file_location("grn_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.sleeps = []                      # 待った秒数の記録（本当には待たない）
    mod.time.sleep = lambda s: mod.sleeps.append(s)
    return mod


def run_main(mod, env):
    mod.urllib.request.urlopen = env.urlopen
    try:
        mod.main()
        return 0
    except SystemExit as e:
        return e.code


def run_main_capture(mod, env):
    """run_main と同じ。画面に出た文字も一緒に返す"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = run_main(mod, env)
    return code, buf.getvalue()


tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "new_releases.json")

print("\n■ 1回目: 保存済みの20件に追記する")
shutil.copy(SAVED_DATA, path)
env = Env()
mod = load_module(path)
code = run_main(mod, env)
data = json.load(open(path, encoding="utf-8"))
by_cid = {d["cid"]: d for d in data}
check("正常終了(0)", code == 0, code)
check("cid が全件ある", all(d.get("cid") for d in data))
check("cid の重複なし", len(by_cid) == len(data))
check("保存済みの20件が残っている", "bibivr00176" in by_cid and "1dldss00538" in by_cid)
old_ai = by_cid["bibivr00176"]
check("保存済みのAIコメントはそのまま保持", old_ai["comment_kind"] == "ai" and "蓮実クレア" in old_ai["comment"], old_ai["comment"])
check("新しい発売済みが追加された(上限=NEW_ITEMS_PER_RUN)", len([d for d in data if d["cid"].startswith("rel")]) == mod.NEW_ITEMS_PER_RUN,
      len([d for d in data if d["cid"].startswith("rel")]))
check("予約が追加された(上限=UPCOMING_ITEMS)", len([d for d in data if d["cid"].startswith("up")]) == mod.UPCOMING_ITEMS)
check("1回に頼むAIの回数が無料枠(1日20回)に収まる設定", mod.NEW_ITEMS_PER_RUN + mod.UPCOMING_ITEMS + mod.RETRY_PER_RUN <= mod.GEMINI_MAX_CALLS <= 20,
      (mod.NEW_ITEMS_PER_RUN, mod.UPCOMING_ITEMS, mod.RETRY_PER_RUN, mod.GEMINI_MAX_CALLS))
check("日付の新しい順に並ぶ", [d["date"] for d in data] == sorted([d["date"] for d in data], reverse=True))
ai_new = [d for d in data if d["cid"].startswith(("rel", "up")) and d["comment_kind"] == "ai"]
tp_new = [d for d in data if d["cid"].startswith(("rel", "up")) and d["comment_kind"] == "template"]
check("AI成功とブロックの両方が混在", len(ai_new) > 0 and len(tp_new) > 0, (len(ai_new), len(tp_new)))
check("AIコメントの整形(括弧・改行・**を除去)", all("**" not in d["comment"] and "\n" not in d["comment"] and not d["comment"].startswith("「") for d in ai_new),
      ai_new[0]["comment"] if ai_new else "")
check("代わりの文に作品名やジャンルを含まない", all("テスト作品" not in d["comment"] for d in tp_new))
check("代わりの文が全部同じにならない（出演者・メーカー入り）", len({d["comment"] for d in tp_new}) > 1)
check("AIに作品タイトルを渡していない", all("テスト作品" not in p and "【VR】【8K】テスト" not in p for p in env.prompts))
check("プロンプトに形式タグ(VR / 8K)を渡す", any("VR / 8K" in p for p in env.prompts))
check("429のあと再挑戦して成功した", env.gemini_calls > 1)
sample = by_cid["rel001"]
check("サンプル画像・ジャンル・収録時間を保存", len(sample["sample_images"]) == 3 and sample["genres"] == ["テストジャンル"] and sample["duration_min"] == 120)
check("出演者なしの作品も保存できる", by_cid["rel004"]["actress"] == [])
check("タグ抽出", sample["tags"] == ["VR", "8K"], sample["tags"])
check("APIキーなどの秘密情報が保存データに入っていない", "fake" not in open(path, encoding="utf-8").read().lower().replace("fake_", ""))
TODAY_STR = TODAY.strftime("%Y-%m-%d")
saved = {x["cid"]: x for x in json.load(open(SAVED_DATA, encoding="utf-8"))}
new_items = [d for d in data if d["cid"] in set(by_cid) - set(saved)]
check("更新日(updated): 新しく追加した作品は今日（日本時間）", len(new_items) > 0 and all(d["updated"] == TODAY_STR for d in new_items), {d["updated"] for d in new_items})
check("更新日(updated): コメントも空の項目の補いも無かった保存済みの作品は、そのまま", all(by_cid[c]["updated"] == saved[c]["updated"] for c in saved if by_cid[c]["comment"] == saved[c]["comment"] and by_cid[c]["genres"] == saved[c]["genres"]))
check("更新日(updated): ジャンルが空だったので補った保存済みの作品は、今日になる（補ったことが sitemap にも伝わる）", all(by_cid[c]["updated"] == TODAY_STR for c in saved if not saved[c]["genres"] and by_cid[c]["genres"]) and any(not saved[c]["genres"] and by_cid[c]["genres"] for c in saved))
check("更新日(updated): 再挑戦でコメントが変わった保存済みの作品は、今日になる",
      all(by_cid[c]["updated"] == TODAY_STR for c in saved if by_cid[c]["comment"] != saved[c]["comment"]))
check("更新日(updated): すべて YYYY-MM-DD", all(re.match(r"^\d{4}-\d{2}-\d{2}$", d["updated"]) for d in data))

print("\n■ 2回目: 同じ作品は増えず、ブロックされた作品は別の切り口で再挑戦")
# 前の日に保存したことにする（今日の日付が入るのは、このあと変わった作品だけのはず）
for d in data:
    d["updated"] = "2000-01-01"
json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
before = {d["cid"]: d for d in data}
env2 = Env()
env2.first_429_done = True
mod2 = load_module(path)
code = run_main(mod2, env2)
data2 = json.load(open(path, encoding="utf-8"))
after = {d["cid"]: d for d in data2}
check("正常終了(0)", code == 0)
check("2回目は件数が増えすぎない(発売済みの追加分だけ)", len(data2) <= len(data) + mod2.NEW_ITEMS_PER_RUN, (len(data), len(data2)))
check("既存のAIコメントは書き換わらない", all(after[c]["comment"] == before[c]["comment"] for c in before if before[c]["comment_kind"] == "ai"))
retried = [c for c in before if before[c]["comment_kind"] == "template" and after[c]["comment_tries"] > before[c]["comment_tries"]]
check("テンプレのままの作品に再挑戦した", len(retried) > 0)
check("再挑戦は1回の実行で上限(6件)以内", len(retried) <= mod2.RETRY_PER_RUN, len(retried))
check("更新日(updated): 2回目は、コメントが変わった作品だけ今日になり、変わらない作品は動かない",
      all(after[c]["updated"] == (TODAY_STR if after[c]["comment"] != before[c]["comment"] else "2000-01-01") for c in before)
      and any(after[c]["comment"] != before[c]["comment"] for c in before) and any(after[c]["comment"] == before[c]["comment"] for c in before))
check("更新日(updated): 2回目に新しく入った作品は今日", all(after[c]["updated"] == TODAY_STR for c in after if c not in before))

print("\n■ 3回目以降: 再挑戦の回数に上限がある")
for _ in range(4):
    e = Env()
    e.first_429_done = True
    m = load_module(path)
    run_main(m, e)
data4 = json.load(open(path, encoding="utf-8"))
check("再挑戦の上限(3回)を超えない", max(d["comment_tries"] for d in data4) <= 3, max(d["comment_tries"] for d in data4))

print("\n■ 更新日: コメントが変わらなかった作品は、更新日を動かさない")
path_u = os.path.join(tmp, "u.json")
d0 = json.load(open(SAVED_DATA, encoding="utf-8"))
for x in d0:
    x["updated"] = "2000-01-01"
json.dump(d0, open(path_u, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
tries0 = {x["cid"]: x["comment_tries"] for x in d0}
e = Env()
e.gemini_mode = "always_blocked"
run_main(load_module(path_u), e)
du = json.load(open(path_u, encoding="utf-8"))
retried_u = [x for x in du if x["cid"] in tries0 and x["comment_tries"] > tries0[x["cid"]]]
check("ブロックされて再挑戦したが、コメントが変わらなかった作品がある", len(retried_u) > 0, len(retried_u))
check("そうした作品の更新日は動かない", all(x["updated"] == "2000-01-01" for x in retried_u), {x["updated"] for x in retried_u})
check("新しく入った作品は今日の日付", all(x["updated"] == TODAY_STR for x in du if x["cid"] not in tries0))

print("\n■ コメントの書き分け（切り口・書き出し・結び）と、確かめられない評価の除外")
m_v = load_module(os.path.join(tmp, "v.json"))
base_item = {"cid": "x00001", "actress": ["花子"], "maker": "メーカーA", "tags": ["VR"], "duration_min": 92, "date": "2026-11-22"}
prompts_v = {m_v.build_prompt(dict(base_item, cid=f"x{i:05d}"), 0, today="2026-10-04") for i in range(300)}
check("切り口が6種類・書き出しが4種類・結びが4種類ある", len(m_v.ANGLES) == 6 and len(m_v.OPENINGS) == 4 and len(m_v.CLOSINGS) == 4, (len(m_v.ANGLES), len(m_v.OPENINGS), len(m_v.CLOSINGS)))
check("作品ごとに、いろいろな組み合わせの依頼が作られる（300作品で、少なくとも60通り）", len(prompts_v) >= 60, len(prompts_v))
check("同じ作品・同じ回数なら、いつも同じ依頼になる", m_v.build_prompt(base_item, 0, today="2026-10-04") == m_v.build_prompt(dict(base_item), 0, today="2026-10-04"))
check("再挑戦（回数が増える）では、別の組み合わせになる作品がある", sum(m_v.build_prompt(dict(base_item, cid=f"x{i:05d}"), 0, today="2026-10-04") != m_v.build_prompt(dict(base_item, cid=f"x{i:05d}"), 1, today="2026-10-04") for i in range(50)) >= 40)
p_up = m_v.build_prompt(base_item, 0, today="2026-10-04")
p_rel = m_v.build_prompt(base_item, 0, today="2026-12-01")
check("発売前の作品には「予約受付中」「発売予定」など古くなる言い方を使わないよう頼み、日付で書かせる", "古くなる言い方は使わず" in p_up and "「○月○日発売」" in p_up and "この作品は発売済み" not in p_up)
check("発売済みの作品には「発売されました」と書いてよいと伝える", "この作品は発売済み" in p_rel and "古くなる" not in p_rel)
check("使いすぎる言い回し（気になる方は・チェック・ぜひ…）は使わないよう頼む", all(w in p_up for w in m_v.AVOID_PHRASES))
check("収録時間（事実）を渡す。無いときは「記載なし」", "収録時間: 約92分" in p_up and "収録時間: 記載なし" in m_v.build_prompt(dict(base_item, duration_min=None), 0, today="2026-10-04") and "収録時間: 記載なし" in m_v.build_prompt(dict(base_item, duration_min=True), 0, today="2026-10-04"))
check("人気・期待度・評判は書かないよう頼む。「前向きなトーン」とは頼まない", "人気" in p_up and "期待度" in p_up and "前向き" not in p_up)
check("依頼にタイトルは入らない（従来どおり）", "title" not in p_up and "タイトル" not in p_up)

check("確かめられない評価の言葉を見つけられる", m_v.rejected_words("待望の新作で、ファンの期待が高い注目の一本") == ["待望", "ファンの", "注目の"], m_v.rejected_words("待望の新作で、ファンの期待が高い注目の一本"))
check("過激な言葉・未成年を連想させる言葉も見つけられる", "中出" in m_v.rejected_words("中出しの") and "少女" in m_v.rejected_words("少女のような") and "JK" in m_v.rejected_words("jkの"))
check("ふつうのコメントは、見つからない", m_v.rejected_words("花子さん出演の、メーカーAの新作です。発売は11月22日、収録時間は約92分です。") == [])

# 言葉の一覧が、Claude の道具（scripts/claude_comments.py）と同じ
spec_cc = importlib.util.spec_from_file_location("cc_test", os.path.join(ROOT, "scripts", "claude_comments.py"))
cc = importlib.util.module_from_spec(spec_cc)
spec_cc.loader.exec_module(cc)
check("確かめられない評価・過激な言葉・結びの言い回しの一覧が、Claude の道具と同じ（片方だけ直し忘れない）",
      m_v.HYPE_WORDS == cc.HYPE_WORDS and m_v.EXPLICIT_WORDS == cc.EXPLICIT_WORDS and m_v.MINOR_WORDS == cc.MINOR_WORDS and m_v.AVOID_PHRASES == cc.AVOID_PHRASES)

path_h = os.path.join(tmp, "hype.json")
shutil.copy(SAVED_DATA, path_h)
d_before = json.load(open(path_h, encoding="utf-8"))
tries_h0 = {x["cid"]: x["comment_tries"] for x in d_before}
e = Env()
e.gemini_mode = "hype"
m_h = load_module(path_h)
code_h, out_h = run_main_capture(m_h, e)
d_h = json.load(open(path_h, encoding="utf-8"))
new_h = [x for x in d_h if x["cid"] not in tries_h0]
check("確かめられない評価が入った答えは、採用されない（新しい作品は、すべて定型文）", code_h == 0 and new_h and all(x["comment_kind"] == "template" and "待望" not in x["comment"] and "熱い視線" not in x["comment"] for x in new_h), [(x["cid"], x["comment_kind"]) for x in new_h][:3])
check("採用しなかった作品は、再挑戦の回数が1増える（上限まで続けば、Claude が書き直す）", all(x["comment_tries"] == 1 for x in new_h), {x["comment_tries"] for x in new_h})
check("採用しなかった数が、画面とカウンターに出る（連続失敗のお休みにはならない）", m_h.CommentMaker is not None and "採用せず" in out_h and e.gemini_calls > 4, e.gemini_calls)
check("定型文に入るのは作品情報だけ（確かめられない評価は入らない）", all(not m_h.rejected_words(x["comment"]) for x in new_h))

print("\n■ Geminiが使えない/APIキー無しでも止まらない")
path_b = os.path.join(tmp, "b.json")
shutil.copy(SAVED_DATA, path_b)
e = Env()
m = load_module(path_b, gemini="")
code = run_main(m, e)
d = json.load(open(path_b, encoding="utf-8"))
check("キー無し: 正常終了", code == 0)
check("キー無し: Geminiを1回も呼ばない", e.gemini_calls == 0)
check("キー無し: 全件にコメントがある", all(x["comment"] for x in d))

path_c = os.path.join(tmp, "c.json")
shutil.copy(SAVED_DATA, path_c)
e = Env()
e.gemini_mode = "always_error"
m = load_module(path_c)
code = run_main(m, e)
d = json.load(open(path_c, encoding="utf-8"))
check("Gemini全滅: 正常終了してデータは保存される", code == 0 and len(d) > 20)
check("Gemini全滅: 連続失敗でお休み（呼び出しが少ない）", e.gemini_calls <= 4, e.gemini_calls)
check("Gemini全滅: 失敗は再挑戦回数に数えない", all(x["comment_tries"] == 0 for x in d if x["cid"].startswith(("rel", "up"))))

print("\n■ 失敗のときは、既存データを壊さない")
print("  （この下に出る ❌ で始まるエラー文は、わざと失敗させたときの正しいメッセージです）")
path_d = os.path.join(tmp, "d.json")
shutil.copy(SAVED_DATA, path_d)
orig = open(path_d, "rb").read()
e = Env()
e.dmm_mode = "fail"
m = load_module(path_d)
code = run_main(m, e)
check("FANZA取得失敗: 終了コード1（Actionsで気づける）", code == 1, code)
check("FANZA取得失敗: データは変更されない", open(path_d, "rb").read() == orig)
e = Env()
e.dmm_mode = "status400"
m = load_module(path_d)
code = run_main(m, e)
check("APIがstatus 400: 終了コード1", code == 1, code)
check("APIがstatus 400: データは変更されない", open(path_d, "rb").read() == orig)

path_e = os.path.join(tmp, "e.json")
open(path_e, "w").write("{壊れたJSON")
m = load_module(path_e)
code = run_main(m, Env())
check("保存データが壊れていたら上書きせず中止", code == 1 and open(path_e).read() == "{壊れたJSON")

path_g = os.path.join(tmp, "g.json")
good = json.load(open(SAVED_DATA, encoding="utf-8"))
broken = good + [{"title": "cid の無い作品", "date": "2026-10-01 00:00:00"}]  # 1件だけ読めない
json.dump(broken, open(path_g, "w", encoding="utf-8"), ensure_ascii=False)
before_g = open(path_g, "rb").read()
code, out = run_main_capture(load_module(path_g), Env())
check("読めない作品が1件でもあれば、作品が消えないよう中止(1)", code == 1 and open(path_g, "rb").read() == before_g and "読めない作品が1件" in out, (code, out[-120:]))

path_h = os.path.join(tmp, "h.json")
open(path_h, "w", encoding="utf-8").write('{"items": []}')
code, out = run_main_capture(load_module(path_h), Env())
check("データが作品のリストでなければ、上書きせず中止(1)", code == 1 and open(path_h, encoding="utf-8").read() == '{"items": []}', code)

path_i = os.path.join(tmp, "i.json")
partial = [{k: v for k, v in good[0].items() if k not in ("comment_kind", "tags", "comment_tries", "sample_images", "genres", "updated")}]
json.dump(partial, open(path_i, "w", encoding="utf-8"), ensure_ascii=False)
mi = load_module(path_i)
norm = mi.load_archive()[good[0]["cid"]]
check("項目が足りなくても読める（既定値で補う）", norm["comment_kind"] == "template" and norm["comment_tries"] == 0 and norm["sample_images"] == [] and isinstance(norm["tags"], list), norm)
check("更新日が無い・壊れているときは空にする（日付を作り出さない）", norm["updated"] == "" and mi.day_key("昨日") == "" and mi.day_key(None) == ""
      and mi.day_key("2026-10-03") == "2026-10-03" and mi.day_key("2026-10-03 00:00:00") == "2026-10-03" and mi.day_key("2026-10-3") == "")

m = load_module(os.path.join(tmp, "f.json"), api_id="")
code = run_main(m, Env())
check("API_ID未設定: 分かりやすく中止(1)", code == 1)

print("\n■ Geminiの利用上限（429）への対応")
info_day = mod.gemini_error_info(BODY_QUOTA_DAILY.decode("utf-8"))
check("エラー本文の読み取り: 1日の上限・理由・待ち秒数", info_day[1] is True and "limit: 20" in info_day[0] and info_day[2] == 27.0, info_day)
info_min = mod.gemini_error_info(QUOTA_BODIES["per_minute"].decode("utf-8"))
check("エラー本文の読み取り: 1分あたりの上限は『1日』と判定しない", info_min[1] is False and info_min[2] == 7.0, info_min)
check("エラー本文の読み取り: 壊れた本文でも落ちない", mod.gemini_error_info("<html>oops") == ("", False, None) and mod.gemini_error_info(None) == ("", False, None))

path_q = os.path.join(tmp, "q.json")
shutil.copy(SAVED_DATA, path_q)
e = Env()
e.gemini_mode = "quota_daily"
m = load_module(path_q)
code, out = run_main_capture(m, e)
dq = json.load(open(path_q, encoding="utf-8"))
newq = [x for x in dq if x["cid"].startswith(("rel", "up"))]
check("1日の上限: 正常終了してデータは保存される", code == 0 and len(newq) == m.NEW_ITEMS_PER_RUN + m.UPCOMING_ITEMS, (code, len(newq)))
check("1日の上限: 1回で見切りをつける（Geminiを呼ぶのは1回だけ）", e.gemini_calls == 1, e.gemini_calls)
check("1日の上限: 長く待たない（待ち時間なし）", max(m.sleeps or [0]) < 10, m.sleeps)
check("1日の上限: 新しい作品も代わりの文で載る", all(x["comment_kind"] == "template" and x["comment"] for x in newq))
check("1日の上限: 再挑戦の回数に数えない", all(x["comment_tries"] == 0 for x in newq))
check("1日の上限: ログに理由が出る", "利用上限" in out and "limit: 20" in out)
check("1日の上限: Actionsの警告表示(::warning)を出す", "::warning title=" in out)

path_m = os.path.join(tmp, "m.json")
shutil.copy(SAVED_DATA, path_m)
e = Env()
e.gemini_mode = "per_minute"
m = load_module(path_m)
code, out = run_main_capture(m, e)
dm = json.load(open(path_m, encoding="utf-8"))
check("1分あたりの上限: 言われた秒数(7秒)+1秒だけ待つ", 8.0 in m.sleeps, m.sleeps)
check("1分あたりの上限: 待ったあとは成功してAIコメントが付く", code == 0 and any(x["comment_kind"] == "ai" for x in dm if x["cid"].startswith(("rel", "up"))))
check("1分あたりの上限: そのあとは止まらずに続ける", e.gemini_calls > 3, e.gemini_calls)

path_w = os.path.join(tmp, "w.json")
shutil.copy(SAVED_DATA, path_w)
e = Env()
e.gemini_mode = "wait_too_long"
m = load_module(path_w)
code, out = run_main_capture(m, e)
check("待ち時間が長すぎる(3600秒): すぐあきらめて、長く待たない", code == 0 and e.gemini_calls == 1 and max(m.sleeps or [0]) < 10, (code, e.gemini_calls, m.sleeps))

print("\n■ 1回の実行でGeminiに頼む回数の上限")
path_c5 = os.path.join(tmp, "c5.json")
shutil.copy(SAVED_DATA, path_c5)
e = Env()
e.first_429_done = True  # このテストでは429は出さない
m = load_module(path_c5, max_calls=5)
code, out = run_main_capture(m, e)
d5 = json.load(open(path_c5, encoding="utf-8"))
ai5 = [x for x in d5 if x["cid"].startswith(("rel", "up")) and x["comment_kind"] == "ai"]
check("回数上限(GEMINI_MAX_CALLS=5): Geminiに頼むのは5回まで", e.gemini_calls <= 5, e.gemini_calls)
check("回数上限: 残りは代わりの文で載る（作品は減らない）", code == 0 and len([x for x in d5 if x["cid"].startswith(("rel", "up"))]) == m.NEW_ITEMS_PER_RUN + m.UPCOMING_ITEMS)
check("回数上限: ログに理由が出る", "上限(5回)" in out)

print("\n■ 出演者が空の作品を、あとから載った出演者で補う")
path_c = os.path.join(tmp, "cast.json")
seed = json.load(open(SAVED_DATA, encoding="utf-8"))


def seeded(cid, days, actress, kind="ai", genres=("保存済みのジャンル",)):
    """保存済みの作品（APIの偽の応答にも出てくる cid を使う）。更新日は昔の日付にしておく"""
    api = make_api_item(cid, days, actress=tuple(actress))
    return {"cid": cid, "title": api["title"], "url": api["affiliateURL"], "image_url": api["imageURL"]["large"],
            "sample_images": [f"https://pics.dmm.co.jp/digital/video/{cid}/{cid}jp-{i}.jpg" for i in (1, 2, 3)],
            "date": api["date"], "maker": "テストメーカー", "actress": list(actress), "genres": list(genres),
            "tags": ["VR", "8K"], "duration_min": 120, "sample_movie": make_movie(cid)["size_476_306"], "movie_tries": 0,
            "comment": "保存済みのコメントです。" * 5, "comment_kind": kind,
            "comment_tries": 0, "updated": "2000-01-01"}


seed += [
    seeded("rel001", -0, []),                 # 発売済み・空 → 今回の取得にテスト花子が載っている → 補う
    seeded("up000", 3, []),                   # 予約・空 → 今回の取得にテスト花子が載っている → 補う
    seeded("rel002", -0, ["既存の人"]),       # すでに出演者がある → 今回の取得が違っても書き換えない
    seeded("rel004", -1, []),                 # 空 → 今回の取得も空 → 空のまま・更新日も動かない
    seeded("rel005", -0, ["既存の人"], genres=()),  # ジャンルだけ空 → 今回の取得にジャンルがある → ジャンルだけ補う
]
json.dump(seed, open(path_c, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
e = Env()
e.first_429_done = True
m = load_module(path_c)
code, out = run_main_capture(m, e)
got = {d["cid"]: d for d in json.load(open(path_c, encoding="utf-8"))}
check("正常終了(0)", code == 0)
check("空だった発売済みの作品に、出演者が入る", got["rel001"]["actress"] == ["テスト花子"], got["rel001"]["actress"])
check("空だった予約の作品にも、出演者が入る", got["up000"]["actress"] == ["テスト花子"], got["up000"]["actress"])
check("補った作品は、更新日が今日になる（sitemap の lastmod に使う）", got["rel001"]["updated"] == TODAY_STR and got["up000"]["updated"] == TODAY_STR)
check("補っても、コメントや種類は書き換えない", got["rel001"]["comment"] == "保存済みのコメントです。" * 5 and got["rel001"]["comment_kind"] == "ai")
check("すでに出演者がある作品は、書き換えない（更新日も動かない）", got["rel002"]["actress"] == ["既存の人"] and got["rel002"]["updated"] == "2000-01-01", got["rel002"])
check("今回の取得も空の作品は、空のまま（更新日も動かない）", got["rel004"]["actress"] == [] and got["rel004"]["updated"] == "2000-01-01", got["rel004"])
check("ログに補った件数が出る（2件）", "補いました: 2件" in out, out[-300:])
check("ジャンルが空だった作品に、ジャンル（商品タグ）が入る・出演者は書き換えない・更新日が今日になる", got["rel005"]["genres"] == ["テストジャンル"] and got["rel005"]["actress"] == ["既存の人"] and got["rel005"]["updated"] == TODAY_STR, got["rel005"])
check("すでにジャンルがある作品は、書き換えない", got["rel001"]["genres"] == ["保存済みのジャンル"] and got["rel002"]["genres"] == ["保存済みのジャンル"], (got["rel001"]["genres"], got["rel002"]["genres"]))
check("ログに、ジャンルを補った件数が出る（rel005 と、取り直された保存済みの1件で、2件）", "ジャンルを補いました: 2件" in out, [l for l in out.splitlines() if "ジャンル" in l])

print("\n■ 予約の作品に、あとから載ったサンプル画像・収録時間・発売日の変更を反映する（apply_fresh）")
af = mod.apply_fresh
base_item = {"cid": "x1", "date": "2026-11-01 10:00:00", "sample_images": [], "duration_min": None, "image_url": "",
             "actress": ["花子"], "genres": ["巨乳"], "sample_movie": "", "comment": "花子さん出演、11月1日発売の新作です。メーカーの一本として紹介します。",
             "comment_kind": "claude", "updated": "2000-01-01", "title": "t", "maker": "m", "tags": []}
fresh_item = {"cid": "x1", "date": "2026-11-01 10:00:00", "sample_images": ["https://pics.dmm.co.jp/a/x1jp-1.jpg"], "duration_min": 150,
              "image_url": "https://pics.dmm.co.jp/a/x1pl.jpg", "actress": ["別の人"], "genres": ["別"], "sample_movie": ""}
it = json.loads(json.dumps(base_item))
ch = af(it, dict(fresh_item), TODAY_STR)
check("空だったサンプル画像・収録時間・パッケージ画像が入る（入っている出演者・ジャンルは書き換えない）",
      it["sample_images"] == fresh_item["sample_images"] and it["duration_min"] == 150 and it["image_url"] == fresh_item["image_url"]
      and it["actress"] == ["花子"] and it["genres"] == ["巨乳"] and sorted(ch) == ["duration_min", "image_url", "sample_images"], (ch, it))
check("補ったら更新日が今日になる", it["updated"] == TODAY_STR)
it2 = json.loads(json.dumps(base_item))
it2["sample_images"] = ["https://pics.dmm.co.jp/a/old.jpg"]
af(it2, dict(fresh_item, sample_images=["https://pics.dmm.co.jp/a/new.jpg"]), TODAY_STR)
check("すでに入っているサンプル画像は書き換えない", it2["sample_images"] == ["https://pics.dmm.co.jp/a/old.jpg"])
it3 = json.loads(json.dumps(base_item))
ch3 = af(it3, dict(fresh_item, date="2026-11-21 10:00:00", sample_images=[], duration_min=None, image_url=""), TODAY_STR)
check("発売日が延期されたら、発売日を直す", it3["date"] == "2026-11-21 10:00:00" and "date" in ch3, (ch3, it3["date"]))
check("コメントに古い発売日（11月1日）が書いてあれば、定型文に戻す（Claude が書き直す）", it3["comment_kind"] == "template" and "11月1日" not in it3["comment"] and "comment" in ch3, it3["comment"])
it4 = json.loads(json.dumps(base_item))
it4["comment"] = "花子さん出演の、メーカーの新作です。サンプル画像で雰囲気を確かめられます。"
ch4 = af(it4, dict(fresh_item, date="2026-11-21 10:00:00", sample_images=[], duration_min=None, image_url=""), TODAY_STR)
check("コメントに日付が書いてなければ、コメントはそのまま", it4["comment_kind"] == "claude" and ch4 == ["date"], ch4)
it5 = json.loads(json.dumps(base_item))
check("同じ日（時刻だけ違う）なら、発売日は変えない", af(it5, dict(fresh_item, date="2026-11-01 00:00:00", sample_images=[], duration_min=None, image_url=""), TODAY_STR) == [] and it5["updated"] == "2000-01-01")
check("取り直しの発売日が空・変な形なら、発売日は変えない", af(json.loads(json.dumps(base_item)), dict(fresh_item, date="", sample_images=[], duration_min=None, image_url=""), TODAY_STR) == [])

it6 = json.loads(json.dumps(base_item))
it6["comment_kind"] = "template"
it6["comment"] = mod.template_comment(it6)
af(it6, dict(fresh_item, date="2026-11-21 10:00:00", sample_images=[], duration_min=None, image_url=""), TODAY_STR)
check("定型文のコメントは、新しい発売日で作り直す（古い日付が残らない）", it6["comment"] == mod.template_comment(it6) and "11月21日" in it6["comment"] and "11月1日" not in it6["comment"], it6["comment"])
it7 = json.loads(json.dumps(base_item))
it7["date"] = "2026-01-01 10:00:00"
it7["comment"] = "花子さん出演、11月1日に発売された一本です。メーカーの新作として紹介します。"
af(it7, dict(fresh_item, date="2026-01-08 10:00:00", sample_images=[], duration_min=None, image_url=""), TODAY_STR)
check("古い日付の照らし合わせは、日付の区切りを見る（「11月1日」の中の「1月1日」は、別の日）", it7["comment_kind"] == "claude", it7["comment_kind"])

print("\n■ シリーズ・レーベル（APIの iteminfo.series・label。2026-10-07 から保存）")
raw_s = make_api_item("srs00001", -3)
raw_s["iteminfo"]["series"] = [{"id": 223790, "name": " unfinished  VR "}]
raw_s["iteminfo"]["label"] = [{"id": 25739, "name": "SODVR"}]
ps_ = mod.parse_api_item(raw_s)
check("シリーズ・レーベルの id と名前を取る（名前の空白は1つにそろえる）", (ps_["series_id"], ps_["series"], ps_["label_id"], ps_["label"]) == (223790, "unfinished VR", 25739, "SODVR"), ps_)
raw_n = make_api_item("srs00002", -3)
raw_n["iteminfo"]["label"] = [{"id": 99999, "name": "----"}]
pn_ = mod.parse_api_item(raw_n)
check("シリーズが無い・レーベルが「----」（id 99999）なら、無し（0 と空）", (pn_["series_id"], pn_["series"], pn_["label_id"], pn_["label"]) == (0, "", 0, ""), pn_)
check("読めない id・名前は無し（id が0以下・数字でない・名前が空）", mod.clean_entry("x", "名前") == (0, "") and mod.clean_entry(0, "名前") == (0, "") and mod.clean_entry(5, "  ") == (0, "") and mod.clean_entry("12", "名前") == (12, "名前"))
nl_ = mod.normalize_loaded({"cid": "a", "title": "t", "date": "2026-10-01"})
check("保存済みの作品にシリーズ・レーベルが無くても読める（無し＝0 と空）", (nl_["series_id"], nl_["series"], nl_["label_id"], nl_["label"]) == (0, "", 0, ""), nl_)
nl2_ = mod.normalize_loaded({"cid": "a", "title": "t", "date": "2026-10-01", "series_id": 7, "series": "S", "label_id": 99999, "label": "----"})
check("保存済みのシリーズは残し、無しの印のレーベルは空にする", (nl2_["series_id"], nl2_["series"], nl2_["label_id"], nl2_["label"]) == (7, "S", 0, ""), nl2_)
it_s = json.loads(json.dumps(base_item))
it_s.update(series_id=0, series="", label_id=0, label="")
ch_s = af(it_s, dict(fresh_item, sample_images=[], duration_min=None, image_url="", series_id=5, series="シリーズA", label_id=6, label="レーベルB"), TODAY_STR)
check("空だったシリーズ・レーベルを、取り直しで補う（id も一緒に）", (it_s["series_id"], it_s["series"], it_s["label_id"], it_s["label"]) == (5, "シリーズA", 6, "レーベルB") and sorted(ch_s) == ["label", "series"], (ch_s, it_s))
it_s2 = json.loads(json.dumps(it_s))
check("入っているシリーズ・レーベルは書き換えない", af(it_s2, dict(fresh_item, sample_images=[], duration_min=None, image_url="", series_id=9, series="別", label_id=9, label="別"), TODAY_STR) == [] and it_s2["series"] == "シリーズA")

print("\n■ コメントの囲み記号の外し方（clean_comment）")
cc = mod.clean_comment
check("全体を囲む「」は外す", cc("「花子さん出演の新作です。」") == "花子さん出演の新作です。")
check("文の頭の「新作」の「」は残す（片方だけ外して、とじかっこだけが残らない）", cc("「新作」として届いた一本です。") == "「新作」として届いた一本です。", cc("「新作」として届いた一本です。"))
check("文の終わりの「」も残す", cc("出演は花子さん、作品名は「秘密」") == "出演は花子さん、作品名は「秘密」")
check("全体を囲む \"…\" も外す", cc('"花子さん出演の新作です。"') == "花子さん出演の新作です。")
check("片方だけのかっこ（はじめの「・終わりの」）も外す", cc("「花子さん出演の新作です。") == "花子さん出演の新作です。" and cc("花子さん出演の新作です。」") == "花子さん出演の新作です。")

print("\n■ サンプル動画のURLの選び方")
tm = mod  # 1回目に読み込んだスクリプト
good = make_movie("abc")
check("パソコン・スマホの両方で見られる動画だけ使う（476x306）", tm.pick_sample_movie({"sampleMovieURL": good}) == good["size_476_306"])
check("スマホ非対応（sp_flag=0）の動画は使わない", tm.pick_sample_movie({"sampleMovieURL": make_movie("abc", sp=0)}) == "")
check("パソコン非対応（pc_flag=0）の動画は使わない", tm.pick_sample_movie({"sampleMovieURL": make_movie("abc", pc=0)}) == "")
check("フラグが文字列の '1' でも読める", tm.pick_sample_movie({"sampleMovieURL": dict(good, pc_flag="1", sp_flag="1")}) == good["size_476_306"])
check("http のURLは https に直す", tm.pick_sample_movie({"sampleMovieURL": dict(good, size_476_306="http://www.dmm.co.jp/litevideo/x/")}) == "https://www.dmm.co.jp/litevideo/x/")
check("FANZA(DMM)以外のホスト・javascript: のURLは使わない", all(tm.pick_sample_movie({"sampleMovieURL": dict(good, size_476_306=u)}) == "" for u in ("https://evil.example/x", "javascript:alert(1)", "https://dmm.co.jp.evil.example/x", "//www.dmm.co.jp/x", "")))
check("動画の項目が無い・形が違っても落ちない", tm.pick_sample_movie({}) == "" and tm.pick_sample_movie({"sampleMovieURL": "x"}) == "" and tm.pick_sample_movie({"sampleMovieURL": None}) == "")
check("新しく追加した作品に、動画のURLが入る", by_cid["rel001"]["sample_movie"] == make_movie("rel001")["size_476_306"] and by_cid["rel001"]["movie_tries"] == 0, by_cid["rel001"].get("sample_movie"))
check("保存した動画のURLに、取得時のアフィリエイトIDが含まれる（APIが返した値をそのまま）", "affi_id=" in by_cid["rel001"]["sample_movie"])


def scenario_dir(name):
    folder = os.path.join(tmp, name)
    os.makedirs(folder, exist_ok=True)
    return folder


def write_archive(folder, items):
    path_ = os.path.join(folder, "new_releases.json")
    json.dump(items, open(path_, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return path_


def run_with(path_, env_, *args, **module_kw):
    """スクリプトを、指定の引数（--refresh-only など）で動かす。(モジュール, 終了コード, 画面の出力) を返す"""
    m_ = load_module(path_, **module_kw)
    saved_argv = sys.argv
    sys.argv = ["get_new_releases.py", *args]
    try:
        code_, out_ = run_main_capture(m_, env_)
    finally:
        sys.argv = saved_argv
    return m_, code_, out_


def seed_item(cid, days, actress=(), movie=True, tries=0):
    item = seeded(cid, days, list(actress))
    item["sample_movie"] = make_movie(cid)["size_476_306"] if movie else ""
    item["movie_tries"] = tries
    return item


def cid_queries(env_):
    return [q["cid"] for ep, q in env_.queries if ep == "ItemList" and "cid" in q]


print("\n■ 保存済みの作品の取り直し（品番を指定。--refresh-only）")
folder = scenario_dir("refetch")
path_r = write_archive(folder, [
    seed_item("mvok", -2, ["元の人"], movie=False),        # 発売済み・動画なし → 動画が取れる
    seed_item("mvnone", -3, ["B"], movie=False),           # 発売済み・動画なし → APIにも無い
    seed_item("castfill", 5, [], movie=False),             # 予約・出演者なし → 出演者が載っていた
    seed_item("castwin", -10, [], movie=False),            # 発売済み・出演者なし（30日以内）→ 出演者も動画も載っていた
    seed_item("castmid", -10, [], movie=True),             # 発売から10日・出演者なし（動画は揃っている）→ 30日以内なので取り直す
    seed_item("castold", -60, [], movie=True),             # 発売から60日・出演者なし → もう取り直さない
    seed_item("complete", -4, ["完全な人"], movie=True),   # すべて揃っている → 取り直さない
])
env_r = Env()
env_r.by_cid = {
    "mvok": make_api_item("mvok", -2, actress=("甲",)),
    "castfill": make_api_item("castfill", 5, actress=("追加花子",), movie=False),
    "castwin": make_api_item("castwin", -10, actress=("窓花子",)),
    "castmid": make_api_item("castmid", -10, actress=("中花子",)),
}
before_r = open(path_r, "rb").read()
m_r, code_r, out_r = run_with(path_r, env_r, "--refresh-only")
got_r = {d["cid"]: d for d in json.load(open(path_r, encoding="utf-8"))}
check("正常終了(0)", code_r == 0, out_r[-300:])
check("--refresh-only: Geminiを一度も呼ばない", env_r.gemini_calls == 0)
check("--refresh-only: 新しい作品を追加しない（7件のまま）", len(got_r) == 7, sorted(got_r))
check("発売済みで動画が無かった作品に、動画が入る（更新日が今日になる）", got_r["mvok"]["sample_movie"] == make_movie("mvok")["size_476_306"] and got_r["mvok"]["updated"] == TODAY_STR)
check("すでにある出演者は書き換えない（動画だけ補う）", got_r["mvok"]["actress"] == ["元の人"])
check("APIにも動画が無い作品は、取り直しの回数が1回増える", got_r["mvnone"]["sample_movie"] == "" and got_r["mvnone"]["movie_tries"] == 1 and got_r["mvnone"]["updated"] == "2000-01-01")
check("予約で出演者が空だった作品に、出演者が入る（予約なので動画の回数は増えない）", got_r["castfill"]["actress"] == ["追加花子"] and got_r["castfill"]["movie_tries"] == 0 and got_r["castfill"]["updated"] == TODAY_STR)
check("発売済みで出演者が空だった作品に、出演者と動画の両方が入る", got_r["castwin"]["actress"] == ["窓花子"] and got_r["castwin"]["sample_movie"] != "")
check("発売から30日より前で出演者が空の作品・すべて揃っている作品は、取り直さない", not ({"castold", "complete"} & set(cid_queries(env_r))), cid_queries(env_r))
check("発売から10日で出演者が空の作品（動画は揃っている）は、30日の範囲内なので取り直して補う", got_r["castmid"]["actress"] == ["中花子"] and got_r["castmid"]["sample_movie"] != "")
check("取り直したのは、必要な5件だけ", sorted(cid_queries(env_r)) == ["castfill", "castmid", "castwin", "mvnone", "mvok"], cid_queries(env_r))
check("ログに補った件数が出る（出演者3件・動画2件）", "出演者を補いました: 3件" in out_r and "動画を補いました: 2件" in out_r, out_r[-500:])

# 動画が無い作品は、3回で取り直しをやめる
for n in (2, 3):
    m_x, c_x, o_x = run_with(path_r, Env(), "--refresh-only")
env_r4 = Env()
run_with(path_r, env_r4, "--refresh-only")
got_r4 = {d["cid"]: d for d in json.load(open(path_r, encoding="utf-8"))}
check(f"動画が無い作品の取り直しは {m_r.MAX_MOVIE_TRIES} 回まで（4回目は品番を指定しない）", got_r4["mvnone"]["movie_tries"] == m_r.MAX_MOVIE_TRIES and "mvnone" not in cid_queries(env_r4), (got_r4["mvnone"]["movie_tries"], cid_queries(env_r4)))

# 1回の取り直しの件数の上限・出演者が空の作品が先
folder = scenario_dir("refetch_cap")
many = [seed_item(f"m{i:02d}", -2 - i, ["動画なし"], movie=False) for i in range(25)] + [seed_item(f"c{i}", -1, [], movie=True) for i in range(5)]
path_cap = write_archive(folder, many)
env_cap = Env()
run_with(path_cap, env_cap, "--refresh-only")
asked = cid_queries(env_cap)
check(f"1回の取り直しは {m_r.REFRESH_PER_RUN} 件まで", len(asked) == m_r.REFRESH_PER_RUN, len(asked))
check("出演者が空の作品（5件）を、動画の取り直しより先にする", all(f"c{i}" in asked for i in range(5)), asked[:8])

# APIが続けて失敗しても、止めずに保存する
folder = scenario_dir("refetch_fail")
path_f = write_archive(folder, [seed_item(f"f{i}", -2, ["A"], movie=False) for i in range(8)])
env_f = Env()
env_f.cid_mode = "fail"
m_f, code_f, out_f = run_with(path_f, env_f, "--refresh-only")
check("品番の取り直しが続けて失敗しても、正常終了する（データは壊れない）", code_f == 0 and len(json.load(open(path_f, encoding="utf-8"))) == 8, out_f[-300:])
# 1件ごとに、通信の再試行（3回）があるので、数えるのは「何件目まで試したか」
check(f"続けて {m_f.MAX_API_FAILS_IN_ROW} 件失敗したら、その回の取り直しをやめる（8件あっても3件で止まる）", len(set(cid_queries(env_f))) == m_f.MAX_API_FAILS_IN_ROW, sorted(set(cid_queries(env_f))))

print("\n■ 出演者のプロフィール（顔写真・体型・FANZAの全作品リンク）")
folder = scenario_dir("profiles")
path_p = write_archive(folder, [seed_item("known", -2, ["既知の人"]), seed_item("dup", -2, ["同名の人"]), seed_item("nobody", -2, ["不明人A"])])
env_p = Env()
m_p, code_p, out_p = run_with(path_p, env_p, "--refresh-only")
act_path = os.path.join(folder, "actresses.json")
act = json.load(open(act_path, encoding="utf-8"))
by_name = {a["name"]: a for a in act["actresses"]}
check("正常終了(0)・出演者データが保存される", code_p == 0 and os.path.exists(act_path), out_p[-300:])
hanako = by_name.get("テスト花子", {})
check("今回の取得に出た出演者が、idつきで保存される", hanako.get("id") == str(fake_actress_id("テスト花子")) and "ブロック太郎" in by_name and "蓮実クレア" in by_name and "ランク花子1" in by_name, sorted(by_name)[:8])
check("体型は数字として保存される（バスト86・カップF・ウエスト57・ヒップ87・身長158）", (hanako.get("bust"), hanako.get("cup"), hanako.get("waist"), hanako.get("hip"), hanako.get("height")) == (86, "F", 57, 87, 158), hanako)
check("生年月日は、年齢の計算のために保存する（YYYY-MM-DD）", hanako.get("birthday") == "1999-03-04")
check("顔写真のURLは https に直る", hanako.get("image_small", "").startswith("https://pics.dmm.co.jp/mono/actjpgs/thumbnail/") and hanako.get("image_large", "").startswith("https://pics.dmm.co.jp/"), hanako)
check("FANZAの全作品リンク（アフィリエイトURL）が入る", hanako.get("list_url", "").startswith("https://al.fanza.co.jp/?lurl="), hanako.get("list_url"))
check("取得日が入る", hanako.get("fetched") == TODAY_STR)
raw_text = open(act_path, encoding="utf-8").read()
check("血液型・趣味・出身地は保存しない（必要ないため）", "散歩" not in raw_text and "東京都" not in raw_text and "blood" not in raw_text and "hobby" not in raw_text and "prefectures" not in raw_text)
check("保存済みの作品にいるのに id が分からない名前は、名前の完全一致が1人だけのとき採用する", "既知の人" in by_name and by_name["既知の人"]["id"] == str(fake_actress_id("既知の人")), sorted(by_name))
check("同じ名前が2人以上・見つからない名前は、推測で選ばず「見つからなかった」として覚える", "同名の人" not in by_name and "不明人A" not in by_name and act["unmatched"] == {"不明人A": TODAY_STR, "同名の人": TODAY_STR}, act["unmatched"])
check("ログに件数が出る", "出演者プロフィール" in out_p, out_p[-400:])

env_p2 = Env()
run_with(path_p, env_p2, "--refresh-only")
check("2回目（同じ日）は、取得済み・見つからなかった名前を、もう一度探さない", sum(1 for ep, q in env_p2.queries if ep == "ActressSearch") == 0, [q for ep, q in env_p2.queries if ep == "ActressSearch"][:3])

# 30日たったら取り直す（体型などは、あとから載ることがある）
old_day = (TODAY - timedelta(days=40)).strftime("%Y-%m-%d")
recent_day = (TODAY - timedelta(days=10)).strftime("%Y-%m-%d")
act["actresses"] = [dict(a, fetched=old_day) if a["name"] == "テスト花子" else dict(a, fetched=recent_day) if a["name"] == "ブロック太郎" else a for a in act["actresses"]]
act["unmatched"]["不明人A"] = old_day
act["unmatched"]["同名の人"] = recent_day
json.dump(act, open(act_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
env_p3 = Env()
run_with(path_p, env_p3, "--refresh-only")
asked_p3 = [(q.get("actress_id") or q.get("keyword")) for ep, q in env_p3.queries if ep == "ActressSearch"]
check("30日たった出演者と、30日たった「見つからなかった名前」だけを、取り直す（10日前に取った人・10日前に探した名前は、まだ）", sorted(asked_p3) == sorted([str(fake_actress_id("テスト花子")), "不明人A"]), asked_p3)
act3 = json.load(open(act_path, encoding="utf-8"))
check("取り直すと、取得日が今日になる", {a["name"]: a for a in act3["actresses"]}["テスト花子"]["fetched"] == TODAY_STR)

# 危ない値・あり得ない値は使わない
folder = scenario_dir("profiles_bad")
path_b = write_archive(folder, [seed_item("x", -2, ["悪い値の人"])])
env_b = Env()
bad_id = str(fake_actress_id("悪い値の人"))
ACTRESS_NAMES[bad_id] = "悪い値の人"
env_b.actress_rows[bad_id] = {"id": bad_id, "name": "悪い値の人", "ruby": "x", "bust": "999", "cup": "ff", "waist": "-5", "hip": "abc", "height": "5",
                              "birthday": (TODAY - timedelta(days=365 * 10)).strftime("%Y-%m-%d"),
                              "imageURL": {"small": "javascript:alert(1)", "large": "https://evil.example/a.jpg"},
                              "listURL": {"digital": "https://evil.example/list"}}
env_b.by_cid = {}
run_with(path_b, env_b, "--refresh-only")
# 作品の取得に出ていない出演者なので、名前で探して採用する
env_b2 = Env()
env_b2.actress_rows = {}
json.dump({"actresses": [{"id": bad_id, "name": "悪い値の人", "fetched": ""}], "unmatched": {}}, open(os.path.join(folder, "actresses.json"), "w", encoding="utf-8"))
env_b2.actress_rows[bad_id] = env_b.actress_rows[bad_id]
run_with(path_b, env_b2, "--refresh-only")
bad = {a["name"]: a for a in json.load(open(os.path.join(folder, "actresses.json"), encoding="utf-8"))["actresses"]}["悪い値の人"]
check("範囲外・数字でない体型は空にする（バスト999・ウエスト-5・ヒップabc・身長5）", (bad["bust"], bad["waist"], bad["hip"], bad["height"]) == (None, None, None, None), bad)
check("カップは英字1文字だけ（ff は空）", bad["cup"] == "")
check("年齢が18歳未満になる生年月日は使わない", bad["birthday"] == "", bad["birthday"])
check("javascript: や FANZA以外のURL（画像・リンク）は使わない", bad["image_small"] == "" and bad["image_large"] == "" and bad["list_url"] == "", bad)

# 取得の上限・失敗しても止めない・壊れたデータは上書きしない
folder = scenario_dir("profiles_cap")
path_c = write_archive(folder, [seed_item(f"n{i:02d}", -2, [f"名前{i:02d}"]) for i in range(40)])
env_c = Env()
run_with(path_c, env_c, "--refresh-only")
check(f"1回に出演者を取りに行くのは {m_p.PROFILE_PER_RUN} 回まで", sum(1 for ep, q in env_c.queries if ep == "ActressSearch") == m_p.PROFILE_PER_RUN, sum(1 for ep, q in env_c.queries if ep == "ActressSearch"))
check("取りに行く順番: まだ取っていない出演者（今回の取得に出た人）が先", sum(1 for ep, q in env_c.queries if ep == "ActressSearch" and "actress_id" in q) >= 6)
folder = scenario_dir("profiles_fail")
path_pf = write_archive(folder, [seed_item("x", -2, ["A"])])
env_pf = Env()
env_pf.actress_mode = "fail"
m_pf, code_pf, out_pf = run_with(path_pf, env_pf, "--refresh-only")
check("出演者の検索が失敗しても、正常終了する（作品データは保存される）", code_pf == 0 and len(json.load(open(path_pf, encoding="utf-8"))) == 1, out_pf[-300:])
asked_pf = {(q.get("actress_id") or q.get("keyword")) for ep, q in env_pf.queries if ep == "ActressSearch"}
check(f"続けて {m_pf.MAX_API_FAILS_IN_ROW} 人失敗したら、その回はやめる", len(asked_pf) == m_pf.MAX_API_FAILS_IN_ROW, sorted(asked_pf))
check("失敗しても、見つけた出演者（id・名前）は保存する（次回に取りに行く）", all(a["fetched"] == "" for a in json.load(open(os.path.join(folder, "actresses.json"), encoding="utf-8"))["actresses"]))
folder = scenario_dir("profiles_corrupt")
path_pc = write_archive(folder, [seed_item("x", -2, ["A"])])
open(os.path.join(folder, "actresses.json"), "w", encoding="utf-8").write("{oops")
before_pc = open(path_pc, "rb").read()
env_pc = Env()
m_pc, code_pc, out_pc = run_with(path_pc, env_pc, "--refresh-only")
act_file_pc = os.path.join(folder, "actresses.json")
check("出演者データが壊れていても、作品の更新は止めない（正常終了）。出演者データは上書きせず、出演者の検索もしない", code_pc == 0 and open(act_file_pc, encoding="utf-8").read() == "{oops" and not any(ep == "ActressSearch" for ep, q in env_pc.queries) and len(json.load(open(path_pc, encoding="utf-8"))) == 1, out_pc[-300:])
check("そのことが、警告として出力に出る", "出演者データを読めませんでした" in out_pc and "::warning" in out_pc, out_pc[-300:])
check("売れ筋ランキングは、出演者データが壊れていても保存される", os.path.exists(os.path.join(folder, "ranking.json")))
open(act_file_pc, "w", encoding="utf-8").write('{"actresses": "x"}')
code_pc2 = run_with(path_pc, Env(), "--refresh-only")[1]
check("出演者データの形が違っても、同じように止めず、上書きしない", code_pc2 == 0 and open(act_file_pc, encoding="utf-8").read() == '{"actresses": "x"}')

print("\n■ 出演者プロフィールの取り違えを防ぐ")
# 名前での検索が途中で切れているとき（該当が一覧より多い）は、完全一致が1人でも採用しない
folder = scenario_dir("profiles_cut")
path_cut = write_archive(folder, [seed_item("x", -2, ["既知の人"])])
env_cut = Env()
env_cut.actress_total_extra = 15
run_with(path_cut, env_cut, "--refresh-only")
act_cut = json.load(open(os.path.join(folder, "actresses.json"), encoding="utf-8"))
check("一覧が途中で切れているとき（該当が一覧より多い）は、完全一致が1人でも採用しない（同じ名前の人が、一覧の外にいるかもしれない）", "既知の人" not in {a["name"] for a in act_cut["actresses"]} and act_cut["unmatched"].get("既知の人") == TODAY_STR, act_cut["unmatched"])
kw_cut = [q for ep, q in env_cut.queries if ep == "ActressSearch" and "keyword" in q]
check("名前での検索は100件まで頼む（切れにくくする）", kw_cut and all(q["hits"] == "100" for q in kw_cut), kw_cut)

# 中身の無い応答で、保存済みの顔写真・体型を消さない
folder = scenario_dir("profiles_bare")
path_bare = write_archive(folder, [seed_item("x", -2, ["保存済みの人"])])
sid = str(fake_actress_id("保存済みの人"))
ACTRESS_NAMES[sid] = "保存済みの人"
good = {"id": sid, "name": "保存済みの人", "ruby": "ほぞん", "image_small": "https://pics.dmm.co.jp/mono/actjpgs/thumbnail/a1.jpg",
        "image_large": "https://pics.dmm.co.jp/mono/actjpgs/a1.jpg", "bust": 86, "cup": "F", "waist": 57, "hip": 87, "height": 158,
        "birthday": "1999-03-04", "list_url": "https://al.fanza.co.jp/?lurl=x&af_id=y-990", "fetched": old_day}
act_file_bare = os.path.join(folder, "actresses.json")
json.dump({"actresses": [good], "unmatched": {}}, open(act_file_bare, "w", encoding="utf-8"))
env_bare = Env()
env_bare.actress_rows[sid] = {"id": sid, "name": "保存済みの人"}  # 中身の無い応答（一時的な不具合を想定）
run_with(path_bare, env_bare, "--refresh-only")
got_bare = {x["name"]: x for x in json.load(open(act_file_bare, encoding="utf-8"))["actresses"]}["保存済みの人"]
check("中身の無い応答では、保存済みの顔写真・体型・生年月日・リンクを消さない（取得日だけ進める）", (got_bare["bust"], got_bare["image_small"] != "", got_bare["birthday"], got_bare["list_url"] != "", got_bare["fetched"]) == (86, True, "1999-03-04", True, TODAY_STR), got_bare)
json.dump({"actresses": [good], "unmatched": {}}, open(act_file_bare, "w", encoding="utf-8"))
env_bare2 = Env()
env_bare2.actress_rows[sid] = {"id": sid, "name": "保存済みの人", "bust": "90"}  # 新しい中身がある応答
run_with(path_bare, env_bare2, "--refresh-only")
got_bare2 = {x["name"]: x for x in json.load(open(act_file_bare, encoding="utf-8"))["actresses"]}["保存済みの人"]
check("新しい中身がある応答なら、新しい内容に置き換える", got_bare2["bust"] == 90 and got_bare2["fetched"] == TODAY_STR, got_bare2)

# 品番で取り直して分かった出演者の id も、プロフィール取得に使う（同じ名前の人が複数いても、取り違えずに済む）
folder = scenario_dir("profiles_refetched")
path_rf = write_archive(folder, [seed_item("emptycast", 3, [], movie=True)])
env_rf = Env()
env_rf.by_cid = {"emptycast": make_api_item("emptycast", 3, actress=("同名さん",))}
run_with(path_rf, env_rf, "--refresh-only")
act_rf = json.load(open(os.path.join(folder, "actresses.json"), encoding="utf-8"))
by_rf = {a["name"]: a for a in act_rf["actresses"]}
check("品番の取り直しで分かった出演者の id を使う（名前で探すと同名が2人いて決められない人も、id で取れる）", by_rf.get("同名さん", {}).get("id") == str(fake_actress_id("同名さん")) and by_rf["同名さん"]["fetched"] == TODAY_STR and "同名さん" not in act_rf["unmatched"], (by_rf.get("同名さん"), act_rf["unmatched"]))

print("\n■ 取り直しの枠（出演者が空の作品が多くても、動画の取り直しが後回しにならない）")
folder = scenario_dir("refetch_fair")
fair_items = [seed_item(f"far{i:02d}", 20 + i, [], movie=False) for i in range(25)] + [seed_item(f"rel{i}", -2 - i, ["動画なし"], movie=False) for i in range(3)]
path_fair = write_archive(folder, fair_items)
env_fair = Env()
run_with(path_fair, env_fair, "--refresh-only")
asked_fair = cid_queries(env_fair)
check(f"出演者が空の作品が25件あっても、発売済みの動画なしの3件も取り直す（合計 {m_p.REFRESH_PER_RUN} 件）", len(asked_fair) == m_p.REFRESH_PER_RUN and all(f"rel{i}" in asked_fair for i in range(3)), asked_fair)
check("出演者が空の作品は、発売日が今日に近いものから", all(f"far{i:02d}" in asked_fair for i in range(17)) and "far17" not in asked_fair, asked_fair)
folder = scenario_dir("refetch_fair2")
fair2 = [seed_item(f"c{i}", 3 + i, [], movie=True) for i in range(3)] + [seed_item(f"m{i:02d}", -2 - i, ["動画なし"], movie=False) for i in range(25)]
env_fair2 = Env()
run_with(write_archive(folder, fair2), env_fair2, "--refresh-only")
asked_fair2 = cid_queries(env_fair2)
check("動画なしが25件あっても、出演者が空の3件はすべて取り直す（合計 20 件）", len(asked_fair2) == m_p.REFRESH_PER_RUN and all(f"c{i}" in asked_fair2 for i in range(3)), asked_fair2)

print("\n■ 形式タグ・URL・生年月日の検査")
tags_item = m_p.parse_api_item(make_api_item("tag001", -1, title="【VR】【痴●団地】【8K】【ケツずり】【4K60fps】テスト作品"))
check("形式タグは英数字6文字までだけ（日本語の括弧書き・長すぎるものはタイトルの断片なので除く）", tags_item["tags"] == ["VR", "8K"], tags_item["tags"])
check("保存済みのタグも、形式タグだけに直す（日本語の断片は消える）", m_p.normalize_loaded({"cid": "a", "title": "テスト", "tags": ["ケツずり", "VR", "VR"]})["tags"] == ["VR"] and m_p.normalize_loaded({"cid": "a", "title": "【痴●団地】テスト", "tags": ["痴●団地"]})["tags"] == [])
nl = lambda kind: m_p.normalize_loaded({"cid": "a", "title": "テスト", "comment": "文章のコメントです。", "comment_kind": kind})["comment_kind"]
check("コメントの種類 ai（Geminiの下書き）・claude（Claudeが仕上げ）・template は、そのまま読む。知らない種類は template", [nl(k) for k in ("ai", "claude", "template", "xx")] == ["ai", "claude", "template", "template"])
frag = m_p.normalize_loaded({"cid": "b", "title": "【ケツずり】テスト", "tags": ["ケツずり", "8K"], "actress": ["花子"], "maker": "M", "date": "2026-10-01"})
check("AIへの依頼にも、定型文にも、タイトルの断片は入らない", "ケツずり" not in m_p.build_prompt(frag, 0) and "ケツずり" not in m_p.template_comment(frag) and "8K" in m_p.build_prompt(frag, 0))
H = ("dmm.co.jp",)
check("URL: DMMのhttpsだけ通す（httpはhttpsに直す）", m_p.safe_https_url("http://pics.dmm.co.jp/a.jpg", H) == "https://pics.dmm.co.jp/a.jpg" and m_p.safe_https_url("https://evil.example/dmm.co.jp", H) == "")
check("URL: ブラウザと解釈がずれるもの（バックスラッシュ・@つき・空白）は通さない", all(m_p.safe_https_url(u, H) == "" for u in ["https://evil.com\\@dmm.co.jp/x", "https://dmm.co.jp:x@evil.com/", "https://u:p@pics.dmm.co.jp/a", "https://pics.dmm.co.jp/a b.jpg", "javascript:alert(1)"]))
check("生年月日: 実在しない日付（2月30日・13月）は使わない", m_p.valid_birthday("1999-02-30", TODAY_STR) == "" and m_p.valid_birthday("1999-13-45", TODAY_STR) == "" and m_p.valid_birthday("1999-02-28", TODAY_STR) == "1999-02-28")

print("\n■ 売れ筋ランキング（FANZAの人気順の上位6本。画面に出すのは先頭3本で、VR作品を隠すときの差し替え用に多めに取る）")
folder = scenario_dir("ranking")
path_k = write_archive(folder, [seed_item("x", -2, ["A"])])
env_k = Env()
m_k, code_k, out_k = run_with(path_k, env_k, "--refresh-only")
rank_path = os.path.join(folder, "ranking.json")
rank = json.load(open(rank_path, encoding="utf-8"))
check("正常終了(0)・ranking.json が保存される", code_k == 0 and os.path.exists(rank_path), out_k[-300:])
check("日付と6本が入り、順位は 1〜6", rank["date"] == TODAY_STR and [x["rank"] for x in rank["items"]] == [1, 2, 3, 4, 5, 6], rank)
check("VR作品には vr=true（2位はジャンルがVR・3位は題名がVR）、それ以外は false", [x["vr"] for x in rank["items"]] == [False, True, True, False, False, False], [x["vr"] for x in rank["items"]])
check("VR判定（is_vr_item）: 題名の【…VR…】・形式タグ・ジャンル（VR専用・ハイクオリティVR・8KVR）のどれか1つでもあればVR。題名に VR の文字があるだけ（括弧なし）では、VRにしない",
      m_k.is_vr_item({"title": "【VR】作品"}) and m_k.is_vr_item({"title": "【8KVR】作品"}) and m_k.is_vr_item({"title": "作品", "tags": ["VR"]})
      and m_k.is_vr_item({"title": "作品", "genres": ["VR専用"]}) and m_k.is_vr_item({"title": "作品", "genres": ["ハイクオリティVR"]}) and m_k.is_vr_item({"title": "作品", "genres": ["8KVR"]})
      and not m_k.is_vr_item({"title": "作品", "genres": ["巨乳"], "tags": ["8K"]}) and not m_k.is_vr_item({"title": "VRの話をする作品"}) and not m_k.is_vr_item({}))
check("1本ごとに、品番・題名・アフィリエイトのURL・画像・発売日・メーカー・出演者がある", all(set(x) == {"rank", "cid", "title", "url", "image_url", "date", "maker", "actress", "vr"} and x["url"].startswith("https://al.fanza.co.jp/") and re.match(r"^\d{4}-\d{2}-\d{2}$", x["date"]) for x in rank["items"]), rank["items"][0])
rank_calls = [q for ep, q in env_k.queries if ep == "ItemList" and q.get("sort") == "rank"]
check("人気順（sort=rank）で6本だけ頼む（日付の絞り込みなし）", len(rank_calls) == 1 and rank_calls[0].get("hits") == "6" and "gte_date" not in rank_calls[0], rank_calls)
check("ランキングに出た出演者も、出演者データに入る", "ランク花子1" in {a["name"] for a in json.load(open(os.path.join(folder, "actresses.json"), encoding="utf-8"))["actresses"]})
for mode, label in (("fail", "取得に失敗"), ("empty", "空の応答")):
    prev = open(rank_path, "rb").read()
    env_k2 = Env()
    if mode == "fail":
        env_k2.rank_mode = "fail"
    else:
        env_k2.rank_items = []
    m_k2, code_k2, out_k2 = run_with(path_k, env_k2, "--refresh-only")
    check(f"ランキングの{label}でも、正常終了し、前回のランキングをそのまま残す", code_k2 == 0 and open(rank_path, "rb").read() == prev and "売れ筋ランキングの取得に失敗" in out_k2, out_k2[-300:])

print("\n■ 通常の実行にも、取り直し・プロフィール・ランキングが入る")
folder = scenario_dir("normal")
path_n = write_archive(folder, [seed_item("castfill", 5, [], movie=False)])
env_n = Env()
env_n.first_429_done = True
env_n.by_cid = {"castfill": make_api_item("castfill", 5, actress=("追加花子",), movie=False)}
m_n, code_n, out_n = run_with(path_n, env_n)
got_n = {d["cid"]: d for d in json.load(open(path_n, encoding="utf-8"))}
check("通常の実行: 新しい作品も追加され、Geminiも呼ばれる", code_n == 0 and len(got_n) > 1 and env_n.gemini_calls > 0)
check("通常の実行: 保存済みの空の出演者も補われ、プロフィールとランキングも保存される", got_n["castfill"]["actress"] == ["追加花子"] and os.path.exists(os.path.join(folder, "actresses.json")) and os.path.exists(os.path.join(folder, "ranking.json")))
check("通常の実行: Geminiの回数は、取り直し・プロフィールで増えない（上限以内）", env_n.gemini_calls <= m_n.GEMINI_MAX_CALLS, env_n.gemini_calls)

print("\n■ 毎日の更新が、新しいデータファイルも保存する")
yml_update = open(os.path.join(ROOT, ".github", "workflows", "update.yml"), encoding="utf-8").read()
add_lines = [ln.strip() for ln in yml_update.splitlines() if ln.strip().startswith("git add")]
check("update.yml の git add は1行だけ", len(add_lines) == 1, add_lines)


def stage_in_temp_repo(files):
    """update.yml の git add の行を、本物の git で動かす。(終了コード, 保存対象になったファイル) を返す"""
    repo = tempfile.mkdtemp(dir=tmp)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    os.makedirs(os.path.join(repo, "site", "src", "data"))
    os.makedirs(os.path.join(repo, "site", "src", "pages"))
    for name in files:
        open(os.path.join(repo, name), "w").write("{}")
    open(os.path.join(repo, "site", "src", "pages", "index.astro"), "w").write("x")  # データ以外が紛れ込まないことの確認用
    r = subprocess.run(add_lines[0], shell=True, cwd=repo, capture_output=True, text=True)
    staged = subprocess.run(["git", "diff", "--staged", "--name-only"], cwd=repo, capture_output=True, text=True).stdout.split()
    return r.returncode, sorted(staged)


data_dir = "site/src/data/"
rc1, st1 = stage_in_temp_repo([data_dir + "new_releases.json"])
check("最初の実行（出演者データ・ランキングがまだ無い）でも、git add が失敗せず、作品データを保存する", rc1 == 0 and st1 == [data_dir + "new_releases.json"], (rc1, st1))
rc2, st2 = stage_in_temp_repo([data_dir + "new_releases.json", data_dir + "actresses.json", data_dir + "ranking.json"])
check("3つのデータファイルがそろっていれば、3つとも保存する・データ以外（ページなど）は保存しない", rc2 == 0 and st2 == sorted([data_dir + n for n in ("new_releases.json", "actresses.json", "ranking.json")]), (rc2, st2))
print("\n■ 定時実行が遅れたときに、二重に動かない（scripts/already_updated.sh）")
GUARD = os.path.join(ROOT, "scripts", "already_updated.sh")


def guard_in_temp_repo(subjects, today, ref=None):
    """記録（コミットの件名）を並べた git の置き場で already_updated.sh を動かし、終了コードを返す"""
    repo = tempfile.mkdtemp(dir=tmp)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    for i, subject in enumerate(subjects):
        open(os.path.join(repo, "f.txt"), "w").write(str(i))
        subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", subject], cwd=repo, check=True)
    r = subprocess.run(["bash", GUARD] + ([ref] if ref else []), cwd=repo, capture_output=True, text=True, env=dict(os.environ, TODAY=today))
    return r.returncode


check("今日の「データ更新」があれば、済んでいる（0）", guard_in_temp_repo(["データ更新: 2026-10-03", "データ更新: 2026-10-04", "コメントの仕上げ（Claude）: 40件"], "2026-10-04") == 0)
check("前の日の更新・取り直し・似た件名だけなら、まだ（1）",
      guard_in_temp_repo(["データ更新: 2026-10-03", "データの取り直し: 2026-10-04", "データ更新: 2026-10-04（テスト）"], "2026-10-04") == 1)
check("記録を読めないとき（無い名前）は、まだとして扱う（1）", guard_in_temp_repo(["データ更新: 2026-10-04"], "2026-10-04", ref="no-such-ref") == 1)
check("update.yml: 定時実行のときだけ調べ、済んでいたら更新と保存をしない（Python の準備・更新・所属事務所・イベント・同人とゲーム・読みがな・10円セール・保存の8つ）",
      "if: github.event_name == 'schedule'" in yml_update and "already_updated.sh FETCH_HEAD" in yml_update
      and yml_update.count("if: steps.guard.outputs.skip != '1'") == 8 and 'git commit -m "データ更新: $(TZ=Asia/Tokyo date +%Y-%m-%d)"' in yml_update)
check("update.yml: 読みがなは、週1回（--update は7日ごと）・同人とゲームのあと・失敗しても更新を止めない・保存の前",
      "python scripts/readings.py --update\n" in yml_update and yml_update.index("doujin_game.py") < yml_update.index("readings.py") < yml_update.index("git add -A -- site/src/data"))
check("update.yml: 所属事務所は、週1回（--update は7日ごと）・失敗しても更新を止めない・保存の前",
      "python scripts/agency_links.py --update" in yml_update and "--force" not in yml_update and "continue-on-error: true" in yml_update
      and yml_update.index("agency_links.py") < yml_update.index("git add -A -- site/src/data"))

check("update.yml: イベント情報は毎日・所属事務所のあと（所属の名前を使う）・失敗しても更新を止めない・保存の前",
      "python scripts/agency_events.py --update" in yml_update
      and yml_update.index("python scripts/agency_links.py") < yml_update.index("python scripts/agency_events.py") < yml_update.index("git add -A -- site/src/data")
      and "continue-on-error: true" in yml_update[yml_update.index("Update events"):yml_update.index("python scripts/agency_events.py")])

yml_refresh = open(os.path.join(ROOT, ".github", "workflows", "refresh-data.yml"), encoding="utf-8").read() if os.path.exists(os.path.join(ROOT, ".github", "workflows", "refresh-data.yml")) else ""
check("refresh-data.yml は --refresh-only で動かし、Gemini のキーを渡さない", "--refresh-only" in yml_refresh and "GEMINI_API_KEY" not in yml_refresh)

print("\n■ 実行結果の要約（GitHub Actionsの画面に出る）")
summary_path = os.path.join(tmp, "summary.md")
os.environ["GITHUB_STEP_SUMMARY"] = summary_path
path_s = os.path.join(tmp, "s.json")
shutil.copy(SAVED_DATA, path_s)
e = Env()
e.first_429_done = True
m = load_module(path_s)
run_main(m, e)
sm = open(summary_path, encoding="utf-8").read() if os.path.exists(summary_path) else ""
check("要約: 取得件数・追加件数・AIの成功数が書かれる", "FANZA更新の結果" in sm and "新しく追加" in sm and "成功" in sm, sm[:200])
check("要約: 出演者を補った件数が書かれる", "出演者が空だった作品に補った" in sm, sm[:300])
os.remove(summary_path)
e = Env()
e.dmm_mode = "fail"
m = load_module(path_s)
run_main(m, e)
sm = open(summary_path, encoding="utf-8").read() if os.path.exists(summary_path) else ""
check("要約: 取得に失敗したときも理由が書かれる", "取得に失敗" in sm, sm[:200])
del os.environ["GITHUB_STEP_SUMMARY"]
m = load_module(path_s)
code = run_main(m, Env())
check("要約: GITHUB_STEP_SUMMARY が無くても落ちない（手元の実行）", code == 0)

print("\n■ 女優検索の名簿（FANZA公式の出演者検索の一覧から、体型・身長・生年月日がある人を集める）")
d_dir = scenario_dir("directory")
d_path = write_archive(d_dir, json.load(open(SAVED_DATA, encoding="utf-8")))
dir_file = os.path.join(d_dir, "actress_directory.json")
env_d = Env()
m_d = load_module(d_path, directory_calls=3)
code_d, out_d = run_main_capture(m_d, env_d)
listing = [q for ep, q in env_d.queries if ep == "ActressSearch" and "offset" in q]
check("正常終了(0)・一覧は、決めた回数（3回）だけ取りに行く", code_d == 0 and len(listing) == 3, (code_d, len(listing)))
check("1回目の一覧: バストありで、id の順・100人ずつ、1人目・101人目・201人目から", [(q.get("gte_bust"), q.get("sort"), q.get("hits"), q.get("offset")) for q in listing] == [("1", "id", "100", "1"), ("1", "id", "100", "101"), ("1", "id", "100", "201")], listing)
dj = json.load(open(dir_file, encoding="utf-8"))
ids = [r["id"] for r in dj["rows"]]
check("名簿に入るのは、体型・身長・生年月日のどれかがある人だけ（250人のうち225人）", len(ids) == 225 and all(r["bust"] or r["height"] or r["birthday"] for r in dj["rows"]), len(ids))
check("名簿の1行: 決めた項目だけ（id・名前・読み・顔写真のファイル名・体型・身長・生年月日・最後に見かけた日）。血液型・趣味・出身地・URLは保存しない",
      all(set(r) == {"id", "name", "ruby", "img", "bust", "cup", "waist", "hip", "height", "birthday", "seen"} and r["seen"] == TODAY_STR for r in dj["rows"]) and "散歩" not in open(dir_file, encoding="utf-8").read()
      and "東京都" not in open(dir_file, encoding="utf-8").read() and "http" not in open(dir_file, encoding="utf-8").read())
check("顔写真は、FANZAの画像のファイル名だけ（a100001 など）", dj["rows"][0]["img"] == "a" + dj["rows"][0]["id"], dj["rows"][0])
check("バストの一覧を最後まで取ったら、次の絞り込み（身長あり）の1人目へ進む", dj["cursor"] == {"filter": 1, "offset": 1} and dj["cycle_done"] == "", dj["cursor"])
check("名簿のファイルは、1人1行（毎日の差分が、変わった人だけになるように）", open(dir_file, encoding="utf-8").read().count("\n") == len(ids) + 2)
env_d2 = Env()
m_d2 = load_module(d_path, directory_calls=5)
run_main_capture(m_d2, env_d2)
dj2 = json.load(open(dir_file, encoding="utf-8"))
listing2 = [q for ep, q in env_d2.queries if ep == "ActressSearch" and "offset" in q]
check("2回目は続きから（身長あり 1・101人目 → 生年月日あり 1人目 → 一回りしてバストあり 1・101人目）", [(next(k for k in ("gte_bust", "gte_height", "gte_birthday") if k in q), q["offset"]) for q in listing2] == [("gte_height", "1"), ("gte_height", "101"), ("gte_birthday", "1"), ("gte_bust", "1"), ("gte_bust", "101")], listing2)
expect_ids = {str(b + n) for b, total in ((100000, 250), (100200, 120), (100000, 30)) for n in range(1, total + 1) if n % 10}
check("一回りしたら、その日を cycle_done に。重なる人（バストと身長・生年月日の両方の一覧に出る人）は1人として数える", dj2["cycle_done"] == TODAY_STR and {r["id"] for r in dj2["rows"]} == expect_ids and len(dj2["rows"]) == len(expect_ids), (dj2["cycle_done"], len(dj2["rows"]), len(expect_ids)))
open(dir_file, "w", encoding="utf-8").write("{broken")
env_d3 = Env()
m_d3 = load_module(d_path, directory_calls=3)
code_d3, out_d3 = run_main_capture(m_d3, env_d3)
check("名簿が壊れていたら、名簿の更新だけやめる（ほかの更新は続ける・ファイルは上書きしない・一覧も取りに行かない）", code_d3 == 0 and open(dir_file, encoding="utf-8").read() == "{broken" and not any(ep == "ActressSearch" and "offset" in q for ep, q in env_d3.queries), out_d3[-200:])
os.remove(dir_file)
env_d4 = Env()
env_d4.directory_fail = True
m_d4 = load_module(d_path, directory_calls=10)
code_d4, out_d4 = run_main_capture(m_d4, env_d4)
check("一覧の取得が続けて失敗したら、その回はやめる（3回まで。1回につき3回まで試すので、問い合わせは9回）・ほかの更新は続ける・続きの位置は進めない", code_d4 == 0 and sum(1 for ep, q in env_d4.queries if ep == "ActressSearch" and "offset" in q) == 9 and json.load(open(dir_file, encoding="utf-8"))["cursor"] == {"filter": 0, "offset": 1}, out_d4[-300:])
row_ok = m_d4.directory_row({"id": "123", "name": "テスト", "ruby": "てすと", "bust": "86", "height": "abc", "birthday": "1700-01-01", "blood_type": "A", "imageURL": {"small": "http://pics.dmm.co.jp/mono/actjpgs/thumbnail/test_a.jpg"}}, TODAY_STR)
check("名簿の1行: 変な値（数字でない身長・ありえない生年月日）は捨てる。http の画像も、ファイル名だけ取り出す", row_ok == {"id": "123", "name": "テスト", "ruby": "てすと", "img": "test_a", "bust": 86, "cup": "", "waist": None, "hip": None, "height": None, "birthday": ""}, row_ok)
check("名簿の1行: 体型・身長・生年月日がどれも無い人・id が数字でない人は入れない", m_d4.directory_row({"id": "5", "name": "x", "imageURL": {"small": "http://pics.dmm.co.jp/mono/actjpgs/thumbnail/x.jpg"}}, TODAY_STR) is None and m_d4.directory_row({"id": "abc", "name": "x", "bust": "80"}, TODAY_STR) is None)
check("名簿の1行: FANZAの画像でないURLは使わない", m_d4.directory_row({"id": "7", "name": "x", "bust": "80", "imageURL": {"small": "https://evil.example/mono/actjpgs/thumbnail/x.jpg"}}, TODAY_STR)["img"] == "")

print("\n■ 女優検索の名簿: FANZAから消えた人・数字が消された人を外す（2回続けて一回りで見かけなかった人）")
check("名簿のファイルに、一回りを始めた日（cycle_start・prev_cycle_start）が入る", "cycle_start" in dj2 and "prev_cycle_start" in dj2, {k: dj2.get(k) for k in ("cycle_start", "prev_cycle_start", "cycle_done")})
row_a = dict(row_ok, id="1", seen="2026-10-05")
row_b = dict(row_ok, id="2", seen="2026-10-10")
st = {"cursor": {"filter": 0, "offset": 1}, "cycle_done": "", "cycle_start": "2026-10-09", "prev_cycle_start": "", "rows": {"1": dict(row_a), "2": dict(row_b)}}
n0 = m_d4.prune_directory(st, "2026-10-14")
check("ひとつ前の一回りの始まりが分からないうちは、誰も外さない（古い形のファイルから読んだ直後）", n0 == 0 and len(st["rows"]) == 2 and st["prev_cycle_start"] == "2026-10-09" and st["cycle_start"] == "2026-10-14", st)
n1 = m_d4.prune_directory(st, "2026-10-19")
check("2回続けて一回りで見かけなかった人（ひとつ前の一回りの始まり 10/9 より前に見たきり）だけ外す", n1 == 1 and set(st["rows"]) == {"2"} and st["prev_cycle_start"] == "2026-10-14", st)
old_form = os.path.join(d_dir, "old_dir.json")
json.dump({"cursor": {"filter": 1, "offset": 101}, "cycle_done": "2026-10-04", "rows": [{k: v for k, v in row_ok.items()}]}, open(old_form, "w", encoding="utf-8"), ensure_ascii=False)
m_d4.DIRECTORY_PATH = old_form
st_old = m_d4.load_directory(TODAY_STR)
check("古い形のファイル（最後に見かけた日・一回りの始まりが無い）も読める（今日見かけたことにして、まだ誰も外さない）",
      st_old["rows"]["123"]["seen"] == TODAY_STR and st_old["cycle_start"] == TODAY_STR and st_old["prev_cycle_start"] == "" and st_old["cursor"] == {"filter": 1, "offset": 101}, st_old)

print("\n■ 過去作品（FANZAの人気順の上位を集める。毎日その日の上位を取り直す。Gemini は使わない）")
c_dir = scenario_dir("catalog")
c_seed = json.load(open(SAVED_DATA, encoding="utf-8"))
c_path = write_archive(c_dir, c_seed)
cat_dir = os.path.join(c_dir, "catalog")
cat_state = os.path.join(c_dir, "catalog_state.json")
cat_rank = os.path.join(c_dir, "catalog_rank.json")


def catalog_rows():
    rows_ = {}
    for name_ in sorted(os.listdir(cat_dir)):
        for r_ in json.load(open(os.path.join(cat_dir, name_), encoding="utf-8")):
            rows_[r_["cid"]] = (name_, r_)
    return rows_


def cat_offsets(env_):
    return [q["offset"] for ep, q in env_.queries if ep == "ItemList" and q.get("sort") == "rank" and "offset" in q]


def past_item(n, **kw):
    return make_api_item(f"cat{n:05d}", -(40 + n * 3), actress=(f"昔の人{n % 7}",), maker=f"昔のメーカー{n % 3}", title=f"過去作品 {n}", **kw)


env_c = Env()
env_c.catalog_overrides = {5: make_api_item("bibivr00176", -1, actress=("蓮実クレア",), maker="KMPVR-bibi-")}  # 毎日の更新で載せた作品と同じ作品
m_c = load_module(c_path, catalog_calls=1, catalog_top=1)
code_c, out_c = run_main_capture(m_c, env_c)
cat_q = [q for ep, q in env_c.queries if ep == "ItemList" and q.get("sort") == "rank" and "offset" in q]
check("正常終了(0)・まずその日の人気順の上位（1本目から）、次にその下を続きから（101本目から）。人気順・100本ずつ・発売済みだけ",
      code_c == 0 and [(q["hits"], q["offset"]) for q in cat_q] == [("100", "1"), ("100", "101")], (code_c, cat_q[:2]))
crow = catalog_rows()
check("過去作品: 200本のうち、毎日の更新で載せた作品と同じ1本を除いた199本", len(crow) == 199 and "bibivr00176" not in crow, len(crow))
check("過去作品は、発売月ごとのファイル（YYYY-MM.json）に入る", all(name_ == r_["date"][:7] + ".json" for name_, r_ in crow.values()) and len(os.listdir(cat_dir)) > 3, sorted(os.listdir(cat_dir))[:3])
check("過去作品の形: コメントは無し（comment_kind: none）・更新日は今日・サンプル画像は8枚まで",
      all(r_["comment"] == "" and r_["comment_kind"] == "none" and r_["updated"] == TODAY_STR and len(r_["sample_images"]) <= 8 for _, r_ in crow.values()))
same_keys = set(m_c.normalize_loaded(c_seed[0]))
check("過去作品の作品の形（項目）は、毎日の更新の作品と同じ（順位は作品に入れず、別のファイルに）", all(set(r_) == same_keys for _, r_ in crow.values()), sorted(set(next(iter(crow.values()))[1]) ^ same_keys))
some_file = os.path.join(cat_dir, sorted(os.listdir(cat_dir))[0])
check("ファイルは1作品1行（毎日の差分が、変わった作品の行だけになるように）", open(some_file, encoding="utf-8").read().count("\n") == len(json.load(open(some_file, encoding="utf-8"))) + 2)
rk = json.load(open(cat_rank, encoding="utf-8"))
check("順位（catalog_rank.json）: 作品ごとに [人気順の順位, 見かけた一回りの番号]。1作品1行・cid の順",
      len(rk) == 199 and rk["cat00010"] == [10, 1] and rk["cat00150"] == [150, 1] and list(rk) == sorted(rk) and open(cat_rank, encoding="utf-8").read().count("\n") == 201, (len(rk), rk.get("cat00010")))
st_c = json.load(open(cat_state, encoding="utf-8"))
check("続きの場所（catalog_state.json）: 次は201本目から・一回り目・まだ一回りしていない・集める深さ・本数", st_c == {"cursor": 201, "cycle": 1, "cycle_done": "", "limit": 10000, "items": 199}, st_c)
check("毎日の更新のデータ（new_releases.json）には、過去作品を入れない", all(not d["cid"].startswith("cat") for d in json.load(open(c_path, encoding="utf-8"))))
check("画面に結果が出る", "過去作品: 一覧を2回取得" in out_c and "うち新しく199本" in out_c and "上位10000本まで" in out_c, out_c[-300:])
pop1 = json.load(open(os.path.join(c_dir, "popularity.json"), encoding="utf-8"))
check("毎日の更新の作品が全体の人気順に出てきたら、その順位を popularity.json の all に（5本目）", pop1["all"] == {"bibivr00176": 5} and pop1["new"] == {}, pop1)

# 2回目: その日の人気順で、上位が入れ替わる（150本目だった作品が1位に・1位だった作品が150本目に）。続きは201本目から → 250本目で終わり → 一回り
first_name, first_row = crow["cat00010"]
first_rows = json.load(open(os.path.join(cat_dir, first_name), encoding="utf-8"))
for r_ in first_rows:
    if r_["cid"] == "cat00010":
        r_["comment"] = "Claudeが書いた、過去作品のコメントです。" * 4
        r_["comment_kind"] = "claude"
    if r_["cid"] == "cat00012":
        r_["comment"] = "定型文のコメント"
        r_["comment_kind"] = "template"
json.dump(first_rows, open(os.path.join(cat_dir, first_name), "w", encoding="utf-8"), ensure_ascii=False)
moved = make_api_item("cat00220", -(40 + 220 * 3) + 400, actress=("昔の人3",), title="過去作品 220")  # 発売日が変わった（別の月へ）
env_c2 = Env()
env_c2.catalog_overrides = {1: past_item(150), 150: past_item(1), 220: moved}
c_seed2 = c_seed + [dict(c_seed[0], cid="cat00011", title="毎日の更新に入った過去作品")]
write_archive(c_dir, c_seed2)
m_c2 = load_module(c_path, catalog_calls=2, catalog_top=1, catalog_limit=250)  # 集める深さを250本にして、一回りを試す
code_c2, out_c2 = run_main_capture(m_c2, env_c2)
st_c2 = json.load(open(cat_state, encoding="utf-8"))
crow2 = catalog_rows()
rk2 = json.load(open(cat_rank, encoding="utf-8"))
check("2回目: 上位（1本目から）→ 続き（201本目から）→ 250本目で終わり、一回りして上位の下（101本目）へ。一回りした日・一回りの番号が進む",
      cat_offsets(env_c2) == ["1", "201", "101"] and st_c2["cursor"] == 201 and st_c2["cycle"] == 2 and st_c2["cycle_done"] == TODAY_STR and st_c2["limit"] == 250, (cat_offsets(env_c2), st_c2))
check("その日の人気順で、順位が入れ替わる（150本目だった作品が1位・1位だった作品が150本目）",
      rk2["cat00150"][0] == 1 and rk2["cat00001"][0] == 150, (rk2.get("cat00150"), rk2.get("cat00001")))
check("Claude が書いたコメントは残す・定型文などは空に戻す", crow2["cat00010"][1]["comment_kind"] == "claude" and crow2["cat00012"][1]["comment"] == "" and crow2["cat00012"][1]["comment_kind"] == "none")
# 1回目の199本 ＋ 201〜250本目の50本 ＋ 5本目（1回目は毎日の更新の作品に差し替えていた）の1本 − 毎日の更新に入った1本 = 249本
check("毎日の更新に入った作品は、過去作品から外す（順位からも外す）", "cat00011" not in crow2 and "cat00011" not in rk2 and "cat00005" in crow2 and len(crow2) == 249 and len(rk2) == 249, len(crow2))
check("発売日が変わった作品は、新しい発売月のファイルへ移る（前の月のファイルからは消える）",
      crow2["cat00220"][0] == moved["date"][:7] + ".json" and crow2["cat00220"][1]["date"] == moved["date"] and crow2["cat00220"][1]["updated"] == TODAY_STR, crow2["cat00220"][0])
check("作品が無くなった月のファイルは消す（空のファイルを残さない）", all(json.load(open(os.path.join(cat_dir, n_), encoding="utf-8")) for n_ in os.listdir(cat_dir)))

# 人気の上位から外れた作品を外す（2回続けて一回りで見かけなかった作品。Claude がコメントを書いた作品は残す）
base_p = {f"cat{n:05d}": dict(crow2[f"cat{n:05d}"][1]) for n in range(20, 40)}  # いまの一回りで見かけた作品（外さない）
st_p = {"items": {**base_p, **{c: dict(crow2[c][1]) for c in ("cat00002", "cat00003", "cat00010")}},
        "ranks": {**{c: [50, 3] for c in base_p}, "cat00002": [2, 1], "cat00003": [3, 2], "cat00010": [10, 1]}, "cursor": 101, "cycle": 3, "cycle_done": ""}
n_p = m_c2.prune_catalog(st_p)
check("一回りが終わったとき、2回続けて見かけなかった作品だけ外す（1回だけ見かけなかった作品・Claude がコメントを書いた作品は残す）",
      n_p == 1 and "cat00002" not in st_p["items"] and "cat00002" not in st_p["ranks"] and {"cat00003", "cat00010"} <= set(st_p["items"]) and len(st_p["items"]) == 22, (n_p, len(st_p["items"])))
st_mass = {"items": {c: dict(crow2[c][1]) for c in list(crow2)[:30]}, "ranks": {c: [1, 1] for c in list(crow2)[:30]}, "cursor": 101, "cycle": 3, "cycle_done": ""}
for c in list(st_mass["items"])[:5]:
    st_mass["items"][c]["comment_kind"] = "none"
buf_m = io.StringIO()
with contextlib.redirect_stdout(buf_m):
    n_mass = m_c2.prune_catalog(st_mass)
check("一度に外れる作品が多すぎる（2割をこえる）ときは、APIの答えがおかしかったものとして、外さない", n_mass == 0 and len(st_mass["items"]) == 30 and "多すぎます" in buf_m.getvalue(), (n_mass, buf_m.getvalue()[-120:]))
# 集める深さを浅くしたあと（2026-10-09 に1.5万本→1万本）: 最後に見かけた順位が深さより下の作品は、多くても外す（深さを変えたせいで見かけなくなっただけ）
saved_limit = m_c2.CATALOG_LIMIT
m_c2.CATALOG_LIMIT = 100
st_shrink = {"items": {c: dict(crow2[c][1]) for c in list(crow2)[:30]}, "ranks": {}, "cursor": 51, "cycle": 3, "cycle_done": ""}
for i, c in enumerate(st_shrink["items"]):
    st_shrink["items"][c]["comment_kind"] = "none"
    st_shrink["ranks"][c] = [10 + i, 3] if i < 18 else [150 + i, 1]  # 18本はいまの深さの中・12本は深さより下（前の一回りで見かけたきり）
buf_s = io.StringIO()
with contextlib.redirect_stdout(buf_s):
    n_shrink = m_c2.prune_catalog(st_shrink)
check("深さを浅くしたあとは、深さより下の作品を、2割をこえても外す（深さの中の作品は残す）", n_shrink == 12 and len(st_shrink["items"]) == 18 and "多すぎます" not in buf_s.getvalue(), (n_shrink, buf_s.getvalue()[-120:]))
st_shrink2 = {"items": {c: dict(crow2[c][1]) for c in list(crow2)[:30]}, "ranks": {}, "cursor": 51, "cycle": 3, "cycle_done": ""}
for i, c in enumerate(st_shrink2["items"]):
    st_shrink2["items"][c]["comment_kind"] = "none"
    st_shrink2["ranks"][c] = [10 + i, 3] if i < 18 else [20 + i, 1]  # 深さの中なのに12本を見かけなかった（APIの答えがおかしい）
with contextlib.redirect_stdout(io.StringIO()):
    n_shrink2 = m_c2.prune_catalog(st_shrink2)
check("深さの中の作品がたくさん見えなくなったときは、これまでどおり外さない", n_shrink2 == 0 and len(st_shrink2["items"]) == 30, n_shrink2)
m_c2.CATALOG_LIMIT = saved_limit

# 失敗のとき
broken_name = sorted(os.listdir(cat_dir))[0]
open(os.path.join(cat_dir, broken_name), "w", encoding="utf-8").write("[{broken")
snapshot = {n_: open(os.path.join(cat_dir, n_), encoding="utf-8").read() for n_ in os.listdir(cat_dir)}
env_c3 = Env()
m_c3 = load_module(c_path, catalog_calls=2, catalog_top=1)
code_c3, out_c3 = run_main_capture(m_c3, env_c3)
check("過去作品のファイルが壊れていたら、過去作品の更新だけやめる（ほかの更新は続ける・ファイルは上書きしない・一覧も取りに行かない）",
      code_c3 == 0 and {n_: open(os.path.join(cat_dir, n_), encoding="utf-8").read() for n_ in os.listdir(cat_dir)} == snapshot
      and not cat_offsets(env_c3), out_c3[-200:])
os.remove(os.path.join(cat_dir, broken_name))
rank_text = open(cat_rank, encoding="utf-8").read()
open(cat_rank, "w", encoding="utf-8").write("{broken")
env_c3b = Env()
m_c3b = load_module(c_path, catalog_calls=2, catalog_top=1)
code_c3b, out_c3b = run_main_capture(m_c3b, env_c3b)
check("順位のファイルが壊れていても、過去作品の更新だけやめる（上書きしない）", code_c3b == 0 and open(cat_rank, encoding="utf-8").read() == "{broken" and not cat_offsets(env_c3b), out_c3b[-200:])
open(cat_rank, "w", encoding="utf-8").write(rank_text)
# 一覧が、決めた深さ（既定の3万本）より手前で終わった（250本しか無い）: 一回りに数えず、続きの場所も進めない
st_before_short = json.load(open(cat_state, encoding="utf-8"))
env_cs = Env()
m_cs = load_module(c_path, catalog_calls=2, catalog_top=1)
code_cs, out_cs = run_main_capture(m_cs, env_cs)
st_after_short = json.load(open(cat_state, encoding="utf-8"))
check("一覧が決めた深さより手前で終わったら（APIの答えがおかしい）、一回りに数えず・外さず・続きの場所も進めない（次の日にもう一度）",
      code_cs == 0 and cat_offsets(env_cs) == ["1", "201"] and st_after_short["cursor"] == 201 and st_after_short["cycle"] == st_before_short["cycle"] and "手前で終わりました" in out_cs,
      (cat_offsets(env_cs), st_after_short))
cursor_before = json.load(open(cat_state, encoding="utf-8"))["cursor"]
env_c4 = Env()
env_c4.catalog_fail = True
m_c4 = load_module(c_path, catalog_calls=10, catalog_top=1)
code_c4, out_c4 = run_main_capture(m_c4, env_c4)
check("一覧の取得が続けて失敗したら、その回はやめる（3回まで。1回につき3回まで試すので、問い合わせは9回）・続きの場所は進めない・ほかの更新は続ける",
      code_c4 == 0 and len(cat_offsets(env_c4)) == 9 and json.load(open(cat_state, encoding="utf-8"))["cursor"] == cursor_before, out_c4[-300:])
env_c5 = Env()
m_c5, code_c5, out_c5 = run_with(c_path, env_c5, "--refresh-only", catalog_calls=1, catalog_top=1)
check("取り直しだけ（--refresh-only）のときも、過去作品を集める（Gemini は使わない）",
      code_c5 == 0 and env_c5.gemini_calls == 0 and "過去作品: 一覧を" in out_c5, out_c5[-300:])
# 集める深さ（CATALOG_LIMIT）と、APIの上限（offset は50000まで）
st_end = {"items": {}, "ranks": {}, "cursor": 201, "cycle": 1, "cycle_done": ""}
env_c6 = Env()
env_c6.catalog_total = 60000
m_c6 = load_module(c_path)
m_c6.urllib.request.urlopen = env_c6.urlopen
m_c6.CATALOG_LIMIT = 300
m_c6.update_catalog(st_end, {}, TODAY, top_calls=1, calls=2)
check("集める深さ（上位300本まで）で一回りして、上位の下（101本目）へ戻る", cat_offsets(env_c6) == ["1", "201", "101"] and st_end["cursor"] == 201 and st_end["cycle"] == 2 and len(st_end["items"]) == 300, (cat_offsets(env_c6), st_end["cursor"], len(st_end["items"])))
st_max = {"items": {}, "ranks": {}, "cursor": 49901, "cycle": 1, "cycle_done": ""}
env_c7 = Env()
env_c7.catalog_total = 60000
m_c6.urllib.request.urlopen = env_c7.urlopen
m_c6.CATALOG_LIMIT = 50000
m_c6.update_catalog(st_max, {}, TODAY, top_calls=0, calls=2)
check("人気順の5万本目まで行ったら（offset は50000まで）、一回りして1本目へ", cat_offsets(env_c7) == ["49901", "1"] and st_max["cursor"] == 101 and st_max["cycle_done"] == TODAY_STR, (cat_offsets(env_c7), st_max["cursor"]))
check("集める深さの既定は1万本（2026-10-09 に1.5万本から。同人・ゲームのページの分を空ける）・APIの上限をこえない", m_c4.CATALOG_LIMIT == 10000 and m_c4.CATALOG_MAX_OFFSET == 50000)

print("\n■ セール・キャンペーン（FANZA公式のAPIの campaign・prices。その日に見かけたものだけ）")
s_dir = scenario_dir("sale")
s_path = write_archive(s_dir, c_seed)
day = lambda d: (TODAY + timedelta(days=d)).strftime("%Y-%m-%d")


def on_sale(n, camps, price="1884~", list_price="2692~"):
    it_ = past_item(n)
    it_["campaign"] = camps
    it_["prices"] = {"price": price, "list_price": list_price, "deliveries": {"delivery": []}}
    return it_


camp_a = {"date_begin": day(-2) + " 10:00:00", "date_end": day(1) + " 09:59:59", "title": "メーカーA30％OFF"}
camp_b = {"date_begin": day(-1) + " 00:10:00", "date_end": day(3) + " 23:59:59", "title": "日替わりセール★"}
env_s = Env()
env_s.catalog_overrides = {
    3: on_sale(3, [camp_a]),
    4: on_sale(4, [{"date_begin": day(-9) + " 00:00:00", "date_end": day(-1) + " 23:59:59", "title": "終わったセール"}]),  # 昨日で終わった
    6: on_sale(6, [camp_b, camp_a]),  # 2つ重なっている → 早く終わるほう
    7: on_sale(7, [camp_b], price="2180~", list_price="2180~"),  # 値引きが確かめられない → 価格は出さない
    8: on_sale(8, [{"date_begin": day(2) + " 00:00:00", "date_end": day(5) + " 23:59:59", "title": "まだ始まっていないセール"}]),
}
m_s = load_module(s_path, catalog_calls=0, catalog_top=1)
code_s, out_s = run_main_capture(m_s, env_s)
sale = json.load(open(os.path.join(s_dir, "sale.json"), encoding="utf-8"))
by_c = {r["c"]: r for r in sale["items"]}
camp_of = lambda c: sale["campaigns"][by_c[c]["k"]]
check("sale.json: 日付と、セール中の作品（今日が期間に入っているキャンペーンだけ）", code_s == 0 and sale["date"] == TODAY_STR and set(by_c) == {"cat00003", "cat00006", "cat00007"}, sorted(by_c))
check("キャンペーンは名前・始まり・終わり（分まで）。重なっていたら、早く終わるほう", camp_of("cat00003") == {"title": "メーカーA30％OFF", "begin": day(-2) + " 10:00", "end": day(1) + " 09:59"} and camp_of("cat00006")["title"] == "メーカーA30％OFF", camp_of("cat00006"))
check("価格は「〜円から」の数字（値引きが確かめられるときだけ）", by_c["cat00003"].get("p") == 1884 and by_c["cat00003"].get("l") == 2692 and "p" not in by_c["cat00007"], by_c["cat00007"])
check("同じキャンペーンは1つにまとめる", len(sale["campaigns"]) == 2, sale["campaigns"])
check("価格の読み方: 「1,884~」→ 1884・読めなければ None", m_s.parse_yen("1,884~") == 1884 and m_s.parse_yen("2180") == 2180 and m_s.parse_yen("") is None and m_s.parse_yen(None) is None and m_s.parse_yen("abc") is None)
env_s2 = Env()
env_s2.catalog_fail = True
before_sale = open(os.path.join(s_dir, "sale.json"), encoding="utf-8").read()
m_s2 = load_module(s_path, catalog_calls=0, catalog_top=1)
run_main_capture(m_s2, env_s2)
check("一覧が取れなかった日は、セールの情報を書きかえない（前の日のまま）", open(os.path.join(s_dir, "sale.json"), encoding="utf-8").read() == before_sale)

print("\n■ セールの履歴（「FANZAのセールはいつ？」・特集ごとのページに使う。毎日足していく）")
hist = json.load(open(os.path.join(s_dir, "sale_history.json"), encoding="utf-8"))
hrow = {r["title"]: r for r in hist["campaigns"]}
check("sale_history.json: 今日見かけたキャンペーンの名前・始まり・終わり・見かけた日・このサイトの作品の本数・最大の割引",
      hist["updated"] == TODAY_STR and set(hrow) == {"メーカーA30％OFF", "日替わりセール★"}
      and hrow["メーカーA30％OFF"] == {"title": "メーカーA30％OFF", "begin": day(-2) + " 10:00", "end": day(1) + " 09:59", "first": TODAY_STR, "last": TODAY_STR, "count": 2, "max_off": 30}
      and "max_off" not in hrow["日替わりセール★"] and hrow["日替わりセール★"]["count"] == 1, hist)
check("一覧が取れなかった日は、セールの履歴も書きかえない", json.load(open(os.path.join(s_dir, "sale_history.json"), encoding="utf-8")) == hist)
prev_h = {"updated": "2026-01-01", "campaigns": [
    {"title": "週末セール", "begin": "2026-01-01 00:00", "end": "2026-01-03 23:59", "first": "2026-01-01", "last": "2026-01-02", "count": 5, "max_off": 50},
    {"title": "とても古いセール", "begin": "2020-01-01 00:00", "end": "2020-01-03 23:59", "first": "2020-01-01", "last": "2020-01-02", "count": 1},
    {"title": "", "begin": "x", "end": "y"}, "壊れた行"]}
camp_w = {"title": "週末セール", "begin": "2026-01-01 00:00", "end": "2026-01-04 23:59"}
camp_d = {"title": "日替わり", "begin": "2026-01-03 00:00", "end": "2026-01-03 23:59"}
merged = m_s.merge_sale_history(prev_h, {"a": (camp_w, 700, 1000), "b": (camp_w, None, None), "c": (camp_d, 500, 1000)}, "2026-01-03")
mrow = {(r["title"], r["begin"]): r for r in merged["campaigns"]}
check("名前と始まりが同じなら同じキャンペーン（終わりが延びたら新しくする・本数と割引は大きいほう・最初に見かけた日はそのまま）",
      mrow[("週末セール", "2026-01-01 00:00")] == {"title": "週末セール", "begin": "2026-01-01 00:00", "end": "2026-01-04 23:59", "first": "2026-01-01", "last": "2026-01-03", "count": 5, "max_off": 50}, mrow)
check("同じ名前でも、始まりがちがえば別の回（毎日の「日替わり」など）・400日より前に最後に見かけたもの・形の違う行は消す・新しい順",
      ("日替わり", "2026-01-03 00:00") in mrow and not any(t == "とても古いセール" for t, _ in mrow) and len(merged["campaigns"]) == 2
      and merged["campaigns"][0]["title"] == "日替わり" and mrow[("日替わり", "2026-01-03 00:00")]["max_off"] == 50)
check("割引の割合は四捨五入（サイトの offPercent と同じ）", m_s.off_percent(1884, 2692) == 30 and m_s.off_percent(675, 1350) == 50 and m_s.off_percent(1, 3) == 67 and m_s.off_percent(None, 100) == 0 and m_s.off_percent(100, 100) == 0)
with tempfile.TemporaryDirectory() as tmp_h:
    bad_h = os.path.join(tmp_h, "sale_history.json")
    open(bad_h, "w").write("{壊れている")
    with contextlib.redirect_stdout(io.StringIO()):
        res_h = m_s.save_sale_history({"a": (camp_w, 700, 1000)}, "2026-01-03", bad_h)
    check("前の履歴が壊れていたら、上書きしない（毎日の更新は止めない）", res_h is None and open(bad_h).read() == "{壊れている")
    ok_h = os.path.join(tmp_h, "ok.json")
    m_s.save_sale_history({"a": (camp_w, 700, 1000)}, "2026-01-03", ok_h)
    text_h = open(ok_h, encoding="utf-8").read()
    check("保存は1行に1つ・読み直せる", json.loads(text_h)["campaigns"][0]["title"] == "週末セール" and text_h.count("\n") == 4, text_h)

print("\n■ きょうの数字（FANZA動画の日ごとの発売本数・予約受付中の本数）と、予約の人気順")
t_dir = scenario_dir("today")
t_path = write_archive(t_dir, c_seed)
env_t = Env()
m_t = load_module(t_path, today_stats=True)
code_t, out_t = run_main_capture(m_t, env_t)
tj = json.load(open(os.path.join(t_dir, "today.json"), encoding="utf-8"))
days7 = [(TODAY - timedelta(days=k)).strftime("%Y-%m-%d") for k in range(6, -1, -1)]
check("today.json: 日付・きょうを含む7日分の発売本数（古い日から）", code_t == 0 and tj["date"] == TODAY_STR and [d["d"] for d in tj["daily"]] == days7 and all(d["n"] == 100 + int(d["d"][8:10]) for d in tj["daily"]), tj.get("daily"))
check("予約受付中の本数・予約の人気順の上位30本（順位・発売日・出演者・画像・リンク。VRには印）", tj["upcoming_total"] == 4321 and len(tj["upcoming"]) == 30 and tj["upcoming"][0]["c"] == "soon001" and tj["upcoming"][0]["r"] == 1
      and tj["upcoming"][0]["d"] > TODAY_STR and tj["upcoming"][0]["a"] == ["予約の人1"] and tj["upcoming"][0]["i"].startswith("https://pics.dmm.co.jp/") and tj["upcoming"][0]["u"].startswith("https://al.fanza.co.jp/")
      and tj["upcoming"][2].get("v") == 1 and "v" not in tj["upcoming"][0], tj["upcoming"][:1])
check("最初の日は、前の日の予約の人気順が無い（空）・画面に結果が出る", tj["prev_upcoming"] == [] and "きょうの数字: きょうの発売" in out_t, out_t[-200:])
check("予約の人気順は1本1行", open(os.path.join(t_dir, "today.json"), encoding="utf-8").read().count("\n") >= 30 + 5)
# 次の日（日付を1日前にずらしたファイルで試す）: 前の日の予約の人気順を prev_upcoming に
tj_old = dict(tj, date=(TODAY - timedelta(days=1)).strftime("%Y-%m-%d"))
json.dump(tj_old, open(os.path.join(t_dir, "today.json"), "w", encoding="utf-8"), ensure_ascii=False)
env_t2 = Env()
env_t2.upcoming_rank_ids = ["soonNEW"] + [f"soon{n:03d}" for n in range(1, 40)]
m_t2 = load_module(t_path, today_stats=True)
run_main_capture(m_t2, env_t2)
tj2 = json.load(open(os.path.join(t_dir, "today.json"), encoding="utf-8"))
check("次の日: 前の日の予約の人気順の作品IDが prev_upcoming に（新しく入った作品が分かる）", tj2["prev_upcoming"] == [r["c"] for r in tj["upcoming"]] and tj2["upcoming"][0]["c"] == "soonNEW", tj2["prev_upcoming"][:3])
m_t3 = load_module(t_path, today_stats=True)
run_main_capture(m_t3, Env())
check("同じ日に2回動いても、前の日の予約の人気順はそのまま", json.load(open(os.path.join(t_dir, "today.json"), encoding="utf-8"))["prev_upcoming"] == tj2["prev_upcoming"])
before_t = open(os.path.join(t_dir, "today.json"), encoding="utf-8").read()
env_t4 = Env()
env_t4.count_fail = True
m_t4 = load_module(t_path, today_stats=True)
code_t4, out_t4 = run_main_capture(m_t4, env_t4)
check("本数が取れなかったら、きょうの数字だけやめる（ほかの更新は続ける・ファイルは前のまま）", code_t4 == 0 and open(os.path.join(t_dir, "today.json"), encoding="utf-8").read() == before_t and "きょうの数字の取得に失敗" in out_t4, out_t4[-200:])

print("\n■ 新着の人気順（最近1週間の発売の、その日の人気順）")
n_dir = scenario_dir("newrank")
n_path = write_archive(n_dir, c_seed)
env_n = Env()
env_n.new_overrides = {2: make_api_item("bibivr00176", -1, actress=("蓮実クレア",), maker="KMPVR-bibi-")}  # 毎日の更新の作品も、新着の人気順に出る
m_n = load_module(n_path, catalog_calls=0, catalog_top=1, new_rank=2)
code_n, out_n = run_main_capture(m_n, env_n)
new_q = [(q["offset"], q.get("gte_date", "")[:10]) for ep, q in env_n.queries if ep == "ItemList" and q.get("sort") == "rank" and "gte_date" in q and "offset" in q]
pop = json.load(open(os.path.join(n_dir, "popularity.json"), encoding="utf-8"))
check("新着の人気順: 最近30日の発売を、人気順に100本ずつ（決めた回数）取る", code_n == 0 and [o for o, _ in new_q] == ["1", "101"], new_q)
check("popularity.json: 日付・新着の人気順（150本。毎日の更新の作品も含む）", pop["date"] == TODAY_STR and len(pop["new"]) == 150 and pop["new"]["bibivr00176"] == 2 and pop["new"]["new0001"] == 1 and pop["new"]["new0150"] == 150, (pop["date"], len(pop["new"])))
ncat = {}
for name_ in os.listdir(os.path.join(n_dir, "catalog")):
    for r_ in json.load(open(os.path.join(n_dir, "catalog", name_), encoding="utf-8")):
        ncat[r_["cid"]] = r_
nrank = json.load(open(os.path.join(n_dir, "catalog_rank.json"), encoding="utf-8"))
check("新着の人気順に出た作品で、まだ持っていないものは過去作品に足す（毎日の更新の作品は足さない）", all(f"new{n:04d}" in ncat for n in range(1, 151) if n != 2) and "bibivr00176" not in ncat, len(ncat))
check("新着の人気順だけで見つけた作品の全体の順位は、まだ分からない（後ろに回す）。全体の人気順にも出た作品は、その順位", nrank["new0010"] == [50000, 1] and nrank["cat00010"] == [10, 1], (nrank.get("new0010"), nrank.get("cat00010")))
check("popularity.json は1作品1行（順位の順）", open(os.path.join(n_dir, "popularity.json"), encoding="utf-8").read().count("\n") >= 150 + 4)
check("最初の日は、前の日の新着の人気順（prev）が空", pop["prev"] == {} and pop["prev_date"] == "", (pop.get("prev_date"), len(pop.get("prev", {}))))
pop_y = dict(pop, date=(TODAY - timedelta(days=1)).strftime("%Y-%m-%d"))
open(os.path.join(n_dir, "popularity.json"), "w", encoding="utf-8").write(json.dumps(pop_y, ensure_ascii=False))
m_ny = load_module(n_path, catalog_calls=0, catalog_top=1, new_rank=2)
run_main_capture(m_ny, Env())
pop2 = json.load(open(os.path.join(n_dir, "popularity.json"), encoding="utf-8"))
check("次の日: 前の日の新着の人気順が prev に（上位200本まで。「急上昇」を見つける用）・その日付", pop2["prev_date"] == pop_y["date"] and pop2["prev"] == dict(sorted(pop["new"].items(), key=lambda kv: kv[1])[:200]), (pop2.get("prev_date"), len(pop2.get("prev", {}))))
m_ny2 = load_module(n_path, catalog_calls=0, catalog_top=1, new_rank=2)
run_main_capture(m_ny2, Env())
check("同じ日に2回動いても、前の日の新着の人気順はそのまま", json.load(open(os.path.join(n_dir, "popularity.json"), encoding="utf-8"))["prev"] == pop2["prev"])
check("画面に結果が出る", "新着の人気順: 150本" in out_n, out_n[-200:])
env_n2 = Env()
env_n2.catalog_fail = True
before_pop = open(os.path.join(n_dir, "popularity.json"), encoding="utf-8").read()
m_n2 = load_module(n_path, catalog_calls=0, catalog_top=0, new_rank=2)
code_n2, out_n2 = run_main_capture(m_n2, env_n2)
check("新着の人気順が取れなかった日は、前の日のまま（popularity.json を書きかえない）", code_n2 == 0 and open(os.path.join(n_dir, "popularity.json"), encoding="utf-8").read() == before_pop, out_n2[-200:])
check("過去作品の1件: 発売日（YYYY-MM-DD）が無い・タイトルが無い作品は入れない", m_c6.catalog_item(dict(c_seed[0], date="")) is None and m_c6.catalog_item(dict(c_seed[0], title="")) is None and m_c6.catalog_item("x") is None)
check("過去作品の1件: Gemini の下書き（ai）も、空にする（過去作品のコメントは Claude が書いたものだけ）", m_c6.catalog_item(dict(c_seed[0], comment_kind="ai", comment="下書き"))["comment_kind"] == "none")
check("過去作品を取りに行かない設定（回数が0）なら、過去作品には触らない（ファイルも作らない）", not os.path.exists(os.path.join(scenario_dir("refetch"), "catalog")) and not os.path.exists(os.path.join(scenario_dir("refetch"), "catalog_rank.json")))

print("\n■ 人気の動き（rank_history.json。新着の人気順に出てきた作品の、毎日の順位）")
rh_path = os.path.join(n_dir, "rank_history.json")
rh = json.load(open(rh_path, encoding="utf-8"))
# （この時点で、上の新着の人気順の試しが4回動いている。2回目からは2本目が new0002 になるので、記録は151本。同じ日に動き直したら、その日の順位は新しいほうにする）
check("新着の人気順に出てきた作品の記録を始める・始めた日・その日の順位（毎日の更新の作品も記録する）", rh["updated"] == TODAY_STR and len(rh["items"]) == 151
      and rh["items"]["new0001"] == {"d": TODAY_STR, "n": [1], "a": []} and rh["items"]["bibivr00176"]["d"] == TODAY_STR and rh["items"]["new0002"]["n"] == [2], (rh.get("updated"), len(rh.get("items", {})), rh["items"].get("new0001")))
rh_text = open(rh_path, encoding="utf-8").read()
check("1作品1行（毎日の差分が、記録中の作品の行だけになるように）", rh_text.count("\n") == len(rh["items"]) + 3, rh_text.count("\n"))
yday = (TODAY - timedelta(days=1)).strftime("%Y-%m-%d")
two = (TODAY - timedelta(days=2)).strftime("%Y-%m-%d")
rh_y = {"updated": yday, "items": {c: dict(r, d=yday) for c, r in rh["items"].items()}}
rh_y["items"]["gone0001"] = {"d": (TODAY - timedelta(days=40)).strftime("%Y-%m-%d"), "n": [3], "a": []}  # データから消えた・記録を終えた作品
open(rh_path, "w", encoding="utf-8").write(json.dumps(rh_y))
m_r1 = load_module(n_path, catalog_calls=0, catalog_top=1, new_rank=2)
run_main_capture(m_r1, Env())
rh2 = json.load(open(rh_path, encoding="utf-8"))
check("次の日: 前の日の順位のあとに、その日の順位を足す（同じ並びで2日分）", rh2["items"]["new0001"]["n"] == [1, 1] and rh2["items"]["new0001"]["d"] == yday, rh2["items"]["new0001"])
check("毎日の更新・過去作品のどちらにも無く、記録を終えた作品は消す", "gone0001" not in rh2["items"])
m_r2 = load_module(n_path, catalog_calls=0, catalog_top=1, new_rank=2)
run_main_capture(m_r2, Env())
check("同じ日に2回動いても、並びは増えない", json.load(open(rh_path, encoding="utf-8"))["items"]["new0001"]["n"] == [1, 1])
rh3 = json.load(open(rh_path, encoding="utf-8"))
rh3["items"] = {c: dict(r, d=two) for c, r in rh3["items"].items()}
open(rh_path, "w", encoding="utf-8").write(json.dumps(rh3))
env_rf = Env()
env_rf.catalog_fail = True
m_r3 = load_module(n_path, catalog_calls=0, catalog_top=1, new_rank=2)
run_main_capture(m_r3, env_rf)
check("人気順を取れなかった日は「分からない」（null）にする（圏外の 0 にしない）", json.load(open(rh_path, encoding="utf-8"))["items"]["new0001"]["n"] == [1, 1, None])
mr = m_n
h_ = {"updated": "", "items": {}}
mr.merge_rank_history(h_, "2026-10-01", {"a1": 3, "a2": 10}, {"a1": 50, "z9": 7}, {"a1", "a2"})
mr.merge_rank_history(h_, "2026-10-02", {"a1": 1}, {}, {"a1", "a2"})
mr.merge_rank_history(h_, "2026-10-04", {"a2": 4, "b1": 9}, None, {"a1", "a2", "b1"})
check("記録: 出てこなかった日は 0・動かなかった日は null で埋める・全体の人気順は記録中の作品だけ",
      h_["items"]["a1"] == {"d": "2026-10-01", "n": [3, 1, None, 0], "a": [50, 0, None, None]} and h_["items"]["a2"]["n"] == [10, 0, None, 4] and "z9" not in h_["items"] and h_["items"]["b1"] == {"d": "2026-10-04", "n": [9], "a": [None]}, h_["items"])
for k in range(5, 40):
    mr.merge_rank_history(h_, f"2026-10-{k:02d}" if k <= 31 else f"2026-11-{k - 31:02d}", {}, {"a1": 20}, {"a1", "a2", "b1"})
check("新着の人気順は8日分・全体の人気順は30日分まで記録する", len(h_["items"]["a1"]["n"]) == mr.RANK_NEW_DAYS == 8 and len(h_["items"]["a1"]["a"]) == mr.RANK_ALL_DAYS == 30, (len(h_["items"]["a1"]["n"]), len(h_["items"]["a1"]["a"])))
mr.merge_rank_history(h_, "2026-11-20", {}, {}, {"a1"})
check("どちらのデータにも無くなった作品は、全体の人気順を記録し終えたら消す（ある作品は残す）", "a2" not in h_["items"] and "a1" in h_["items"], sorted(h_["items"]))
mr.merge_rank_history(h_, "2027-11-20", {}, {}, {"a1"})
check("400日をすぎた記録は消す", h_["items"] == {}, h_["items"])
bad_dir = scenario_dir("rankbad")
open(os.path.join(bad_dir, "rank_history.json"), "w", encoding="utf-8").write("{壊れた")
mr.RANK_HISTORY_PATH = os.path.join(bad_dir, "rank_history.json")
with contextlib.redirect_stdout(io.StringIO()):
    lb_ = mr.load_rank_history()
check("壊れたファイルは、空から記録し直す（止まらない）", lb_ == {"updated": "", "items": {}}, lb_)
check("読むときに、変な順位（文字・負の数・5万より大きい）を null に、9日目より先の新着の順位を捨てる",
      mr.clean_rank_list([1, "x", -1, 50001, None, 0, 2, 3, 4, 5], 8) == [1, None, None, None, None, 0, 2, 3])

print("\n■ ソースの安全チェック")
src = open(SCRIPT, encoding="utf-8").read()
check("API_IDがコードに直書きされていない", not re.search(r'API_ID\s*=\s*os\.environ\.get\("API_ID",\s*"[^"]+"', src))
check("Geminiキーを?key=でURLに付けていない", "?key=" not in src)

shutil.rmtree(tmp)
failed = [n for n, ok in results if not ok]
print(f"\n=== {len(results) - len(failed)}/{len(results)} 合格 ===")
if failed:
    print("失敗:", failed)
    sys.exit(1)
