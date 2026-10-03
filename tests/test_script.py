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


def make_api_item(cid, days_from_today, actress=("テスト花子",), maker="テストメーカー", title=None, movie=True):
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
            "genre": [{"id": 1, "name": "テストジャンル"}],
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
        self.rank_items = None          # 売れ筋ランキングの応答（None なら標準の3本）
        self.actress_total_extra = 0    # 名前での出演者検索に「該当は全部で、返した一覧よりこれだけ多い」と答える（一覧が途中で切れた場合）

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
        if q.get("sort", [""])[0] == "rank":
            if self.rank_mode == "fail":
                raise urllib.error.URLError("rank api down")
            rows = self.rank_items if self.rank_items is not None else [make_api_item(f"rank{i}", -5, actress=(f"ランク花子{i}",)) for i in range(1, 4)]
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
        if "ブロック太郎" in prompt and self.gemini_mode == "mixed":
            return FakeResponse({"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}})
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "「テスト用のAIコメントです。**上品**に紹介します。」\n"}]}}]})


def load_module(data_path, api_id="fake", gemini="fake", max_calls=None):
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
check("更新日(updated): コメントが変わらなかった保存済みの作品は、そのまま", all(by_cid[c]["updated"] == saved[c]["updated"] for c in saved if by_cid[c]["comment"] == saved[c]["comment"]))
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


def seeded(cid, days, actress, kind="ai"):
    """保存済みの作品（APIの偽の応答にも出てくる cid を使う）。更新日は昔の日付にしておく"""
    api = make_api_item(cid, days, actress=tuple(actress))
    return {"cid": cid, "title": api["title"], "url": api["affiliateURL"], "image_url": api["imageURL"]["large"],
            "sample_images": [], "date": api["date"], "maker": "テストメーカー", "actress": list(actress), "genres": [],
            "tags": ["VR", "8K"], "duration_min": 120, "sample_movie": make_movie(cid)["size_476_306"], "movie_tries": 0,
            "comment": "保存済みのコメントです。" * 5, "comment_kind": kind,
            "comment_tries": 0, "updated": "2000-01-01"}


seed += [
    seeded("rel001", -0, []),                 # 発売済み・空 → 今回の取得にテスト花子が載っている → 補う
    seeded("up000", 3, []),                   # 予約・空 → 今回の取得にテスト花子が載っている → 補う
    seeded("rel002", -0, ["既存の人"]),       # すでに出演者がある → 今回の取得が違っても書き換えない
    seeded("rel004", -1, []),                 # 空 → 今回の取得も空 → 空のまま・更新日も動かない
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


def run_with(path_, env_, *args):
    """スクリプトを、指定の引数（--refresh-only など）で動かす。(モジュール, 終了コード, 画面の出力) を返す"""
    m_ = load_module(path_)
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
frag = m_p.normalize_loaded({"cid": "b", "title": "【ケツずり】テスト", "tags": ["ケツずり", "8K"], "actress": ["花子"], "maker": "M", "date": "2026-10-01"})
check("AIへの依頼にも、定型文にも、タイトルの断片は入らない", "ケツずり" not in m_p.build_prompt(frag, 0) and "ケツずり" not in m_p.template_comment(frag) and "8K" in m_p.build_prompt(frag, 0))
H = ("dmm.co.jp",)
check("URL: DMMのhttpsだけ通す（httpはhttpsに直す）", m_p.safe_https_url("http://pics.dmm.co.jp/a.jpg", H) == "https://pics.dmm.co.jp/a.jpg" and m_p.safe_https_url("https://evil.example/dmm.co.jp", H) == "")
check("URL: ブラウザと解釈がずれるもの（バックスラッシュ・@つき・空白）は通さない", all(m_p.safe_https_url(u, H) == "" for u in ["https://evil.com\\@dmm.co.jp/x", "https://dmm.co.jp:x@evil.com/", "https://u:p@pics.dmm.co.jp/a", "https://pics.dmm.co.jp/a b.jpg", "javascript:alert(1)"]))
check("生年月日: 実在しない日付（2月30日・13月）は使わない", m_p.valid_birthday("1999-02-30", TODAY_STR) == "" and m_p.valid_birthday("1999-13-45", TODAY_STR) == "" and m_p.valid_birthday("1999-02-28", TODAY_STR) == "1999-02-28")

print("\n■ 売れ筋ランキング（FANZAの人気順の上位3本）")
folder = scenario_dir("ranking")
path_k = write_archive(folder, [seed_item("x", -2, ["A"])])
env_k = Env()
m_k, code_k, out_k = run_with(path_k, env_k, "--refresh-only")
rank_path = os.path.join(folder, "ranking.json")
rank = json.load(open(rank_path, encoding="utf-8"))
check("正常終了(0)・ranking.json が保存される", code_k == 0 and os.path.exists(rank_path), out_k[-300:])
check("日付と3本が入り、順位は 1・2・3", rank["date"] == TODAY_STR and [x["rank"] for x in rank["items"]] == [1, 2, 3], rank)
check("1本ごとに、品番・題名・アフィリエイトのURL・画像・発売日・メーカー・出演者がある", all(set(x) == {"rank", "cid", "title", "url", "image_url", "date", "maker", "actress"} and x["url"].startswith("https://al.fanza.co.jp/") and re.match(r"^\d{4}-\d{2}-\d{2}$", x["date"]) for x in rank["items"]), rank["items"][0])
rank_calls = [q for ep, q in env_k.queries if ep == "ItemList" and q.get("sort") == "rank"]
check("人気順（sort=rank）で3本だけ頼む（日付の絞り込みなし）", len(rank_calls) == 1 and rank_calls[0].get("hits") == "3" and "gte_date" not in rank_calls[0], rank_calls)
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
