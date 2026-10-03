"""get_new_releases.py のテスト（本物のAPIは使わず、偽の応答で動かす）

実行: python3 tests/test_script.py   （どこから実行してもOK）
"""
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "get_new_releases.py")
# 毎日変わる本番データではなく、固定した20件で試す（テストの結果がぶれないように）
OLD_DATA = os.path.join(ROOT, "tests", "fixtures", "archive_20items.json")
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


def make_api_item(cid, days_from_today, actress=("テスト花子",), maker="テストメーカー", title=None):
    d = (TODAY + timedelta(days=days_from_today)).strftime("%Y-%m-%d 00:00:00")
    return {
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
            "actress": [{"id": i, "name": n} for i, n in enumerate(actress, 1)],
            "genre": [{"id": 1, "name": "テストジャンル"}],
        },
    }


class Env:
    """偽のネットワーク。シナリオごとに挙動を切り替える"""

    def __init__(self):
        self.gemini_calls = 0
        self.gemini_mode = "mixed"      # mixed / always_error / always_ok
        self.dmm_mode = "ok"            # ok / fail / status400
        self.first_429_done = False
        self.prompts = []

    def urlopen(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        if "api.dmm.com" in url:
            return self._dmm(url)
        if "generativelanguage.googleapis.com" in url:
            return self._gemini(req)
        raise AssertionError("想定外のURL: " + url)

    def _dmm(self, url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if self.dmm_mode == "fail":
            raise urllib.error.URLError("network down")
        if self.dmm_mode == "status400":
            return FakeResponse({"result": {"status": 400, "message": "invalid parameter"}})
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
        # 既に保存済みの作品（古いデータにある cid）も混ぜる → 重複しないことの確認用
        items.insert(2, make_api_item("bibivr00176", -1, actress=("蓮実クレア",), maker="KMPVR-bibi-"))
        return FakeResponse({"result": {"status": 200, "items": items[: int(q["hits"][0])]}})

    def _gemini(self, req):
        self.gemini_calls += 1
        body = json.loads(req.data.decode("utf-8"))
        prompt = body["contents"][0]["parts"][0]["text"]
        self.prompts.append(prompt)
        assert req.headers.get("X-goog-api-key") or req.headers.get("x-goog-api-key"), "APIキーがヘッダーに無い"
        assert "key=" not in req.full_url, "APIキーがURLに入っている"
        if self.gemini_mode == "always_error":
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b"{}"))
        if self.gemini_mode == "mixed" and not self.first_429_done:
            self.first_429_done = True
            raise urllib.error.HTTPError(req.full_url, 429, "rate", {}, io.BytesIO(b"{}"))
        if "ブロック太郎" in prompt and self.gemini_mode == "mixed":
            return FakeResponse({"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}})
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "「テスト用のAIコメントです。**上品**に紹介します。」\n"}]}}]})


def load_module(data_path, api_id="fake", gemini="fake"):
    os.environ["API_ID"] = api_id
    os.environ["GEMINI_API_KEY"] = gemini
    os.environ["DATA_PATH"] = data_path
    os.environ["GEMINI_INTERVAL_SEC"] = "0"
    spec = importlib.util.spec_from_file_location("grn_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.time.sleep = lambda s: None
    return mod


def run_main(mod, env):
    mod.urllib.request.urlopen = env.urlopen
    try:
        mod.main()
        return 0
    except SystemExit as e:
        return e.code


tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "new_releases.json")

print("\n■ 1回目: 古い形式の20件に追記する")
shutil.copy(OLD_DATA, path)
env = Env()
mod = load_module(path)
code = run_main(mod, env)
data = json.load(open(path, encoding="utf-8"))
by_cid = {d["cid"]: d for d in data}
check("正常終了(0)", code == 0, code)
check("cid が全件ある", all(d.get("cid") for d in data))
check("cid の重複なし", len(by_cid) == len(data))
check("古い20件が残っている", "bibivr00176" in by_cid and "1dldss00538" in by_cid)
old_ai = by_cid["bibivr00176"]
check("古いAIコメントはそのまま保持", old_ai["comment_kind"] == "ai" and "蓮実クレア" in old_ai["comment"], old_ai["comment"])
old_generic = [d for d in data if d["cid"] == "vrkm01942"][0]
check("古い定型文は新しい代わりの文に置換", "注目の新作登場" not in old_generic["comment"], old_generic["comment"])
check("新しい発売済みが追加された(上限20)", len([d for d in data if d["cid"].startswith("rel")]) == 20,
      len([d for d in data if d["cid"].startswith("rel")]))
check("予約が追加された", len([d for d in data if d["cid"].startswith("up")]) == 8)
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

print("\n■ 2回目: 同じ作品は増えず、ブロックされた作品は別の切り口で再挑戦")
before = {d["cid"]: d for d in data}
env2 = Env()
env2.first_429_done = True
mod2 = load_module(path)
code = run_main(mod2, env2)
data2 = json.load(open(path, encoding="utf-8"))
after = {d["cid"]: d for d in data2}
check("正常終了(0)", code == 0)
check("2回目は件数が増えすぎない(残りの発売済みだけ追加)", len(data2) <= len(data) + 11, (len(data), len(data2)))
check("既存のAIコメントは書き換わらない", all(after[c]["comment"] == before[c]["comment"] for c in before if before[c]["comment_kind"] == "ai"))
retried = [c for c in before if before[c]["comment_kind"] == "template" and after[c]["comment_tries"] > before[c]["comment_tries"]]
check("テンプレのままの作品に再挑戦した", len(retried) > 0)
check("再挑戦は1回の実行で上限(6件)以内", len(retried) <= mod2.RETRY_PER_RUN, len(retried))

print("\n■ 3回目以降: 再挑戦の回数に上限がある")
for _ in range(4):
    e = Env()
    e.first_429_done = True
    m = load_module(path)
    run_main(m, e)
data4 = json.load(open(path, encoding="utf-8"))
check("再挑戦の上限(3回)を超えない", max(d["comment_tries"] for d in data4) <= 3, max(d["comment_tries"] for d in data4))

print("\n■ Geminiが使えない/APIキー無しでも止まらない")
path_b = os.path.join(tmp, "b.json")
shutil.copy(OLD_DATA, path_b)
e = Env()
m = load_module(path_b, gemini="")
code = run_main(m, e)
d = json.load(open(path_b, encoding="utf-8"))
check("キー無し: 正常終了", code == 0)
check("キー無し: Geminiを1回も呼ばない", e.gemini_calls == 0)
check("キー無し: 全件にコメントがある", all(x["comment"] for x in d))

path_c = os.path.join(tmp, "c.json")
shutil.copy(OLD_DATA, path_c)
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
shutil.copy(OLD_DATA, path_d)
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

m = load_module(os.path.join(tmp, "f.json"), api_id="")
code = run_main(m, Env())
check("API_ID未設定: 分かりやすく中止(1)", code == 1)

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
