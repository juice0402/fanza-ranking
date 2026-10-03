#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FANZAの新作を取得し、AIコメントを付けて、過去分と一緒に貯めていくスクリプト。

GitHub Actions から毎日自動で実行されます。
手元で試すとき（API_ID は DMM アフィリエイトの管理画面で確認できます）:

    API_ID=xxxx GEMINI_API_KEY=xxxx python3 get_new_releases.py

保存先: site/src/data/new_releases.json
  - 作品ごとに1件。cid（作品ID）で重複を防ぎ、毎回「追記」します。
  - comment_kind が "ai" ならAIが書いたコメント、"template" なら作品情報から作った代わりの文。
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

# ---- 秘密の値は環境変数（GitHub Secrets）から受け取ります。コードには書きません ----
API_ID = os.environ.get("API_ID", "")
AFFILIATE_ID = os.environ.get("AFFILIATE_ID", "juice0402-990")  # リンクに公開される値なのでOK
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

# ---- 調整できる設定 ----
DATA_PATH = os.environ.get("DATA_PATH", os.path.join("site", "src", "data", "new_releases.json"))
NEW_ITEMS_PER_RUN = 20      # 1回の実行で新しく追加する「発売済み」作品の最大数
UPCOMING_ITEMS = 12         # 「予約受付中」として追加する作品の最大数
LOOKBACK_DAYS = 14          # 何日前までの発売作品を探すか
UPCOMING_DAYS = 14          # 何日先までの予約作品を探すか
RETRY_PER_RUN = 6           # 代わりの文のままの作品に、AIコメントを再挑戦する最大数
MAX_COMMENT_TRIES = 3       # 1作品あたりのAI再挑戦の上限（ブロックされ続けるのを防ぐ）
GEMINI_INTERVAL_SEC = float(os.environ.get("GEMINI_INTERVAL_SEC", "5"))  # API制限対策の待ち時間
MAX_AI_FAILS_IN_ROW = 3     # 連続で失敗したら、その回はAI呼び出しをやめる

# 昔のバージョンで使っていた定型文（見つけたら新しい代わりの文に置き換える）
OLD_GENERIC_COMMENTS = {
    "注目の新作登場！要チェックです！",
    "話題の最新作！キャストの美しさと魅力がギュッと詰まった必見の一作です✨",
    "注目の新着タイトル！期待を裏切らない見ごたえ十分のストーリー展開🔥",
    "いま一番チェックしたい注目作品！圧倒的な世界観と映像美を楽しめます💖",
    "ファン必見の最新リリース！見どころ満載で満足度の高い仕上がりです🌟",
}

ANGLES = [
    "出演者の魅力",
    "新作として発売されるタイミングの注目度",
    "作品の形式や雰囲気（わかる範囲で）",
]


# ------------------------------------------------------------------
# 小さな道具
# ------------------------------------------------------------------
def stable_number(*parts):
    """同じ入力なら必ず同じ数になる（毎回ランダムに変わらないようにするため）"""
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.sha1(raw).hexdigest(), 16)


def format_date_jp(date_str):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str or "")
    if not m:
        return ""
    return f"{int(m.group(1))}年{int(m.group(2))}月{int(m.group(3))}日"


def title_tags(title):
    """タイトルの【VR】【8K】のような括弧書きを取り出す"""
    return [t.strip() for t in re.findall(r"【([^】]{1,10})】", title or "")][:4]


def cid_from_old_item(item):
    """古い形式のデータには cid が無いので、URLから作品IDを取り出す"""
    for key in ("url", "image_url"):
        value = urllib.parse.unquote(item.get(key) or "")
        m = re.search(r"[?&]id=([A-Za-z0-9_]+)", value)
        if m:
            return m.group(1)
        m = re.search(r"/video/([A-Za-z0-9_]+)/", value)
        if m:
            return m.group(1)
    return None


# ------------------------------------------------------------------
# コメント作り
# ------------------------------------------------------------------
def template_comment(item):
    """AIが使えないときの代わりの文。作品情報だけで作るので、事実と食い違いません"""
    actress = item.get("actress") or []
    maker = item.get("maker") or ""
    has_maker = bool(maker) and maker != "不明"
    date_jp = format_date_jp(item.get("date"))
    tags = item.get("tags") or []
    n = stable_number(item.get("cid"), "template")

    if actress:
        who = actress[0] + ("ほか" if len(actress) > 1 else "")
        if has_maker:
            choices = [
                f"{who}が出演する、{maker}の作品です。発売日は{date_jp}。",
                f"{maker}の{who}出演作。発売日は{date_jp}です。",
                f"発売日は{date_jp}。{maker}が届ける、{who}出演の一本です。",
            ]
        else:
            choices = [
                f"{who}が出演する作品です。発売日は{date_jp}。",
                f"発売日は{date_jp}。{who}出演の一本です。",
            ]
    else:
        if has_maker:
            choices = [
                f"{maker}の作品です。発売日は{date_jp}。",
                f"発売日は{date_jp}。{maker}の一本です。",
            ]
        else:
            choices = [f"発売日は{date_jp}の作品です。"]

    text = choices[n % len(choices)]
    if tags:
        text += f"（{'・'.join(tags[:3])}）"
    return text


def build_prompt(item, tries):
    """AIに渡す文章。タイトルは渡しません（過激な言葉でブロックされやすいため）"""
    actress = item.get("actress") or []
    tags = item.get("tags") or []
    angle = ANGLES[stable_number(item.get("cid"), tries) % len(ANGLES)]
    return (
        "映像作品の紹介サイトに載せる、60〜90文字の短い紹介コメントを日本語で1つだけ書いてください。\n\n"
        "【書き方のルール】\n"
        "- 上品で、読んだ人が気になる前向きなトーンにする\n"
        "- 過激・直接的な表現や、性的な描写は使わない\n"
        "- 作品の中身（ストーリーなど）を断定しない。分からないことは書かない\n"
        "- 出演者名は入れてよい（1回まで）\n"
        "- 挨拶・前置き・絵文字・飾りの記号は入れず、コメント本文だけを出力する\n"
        f"- 今回は「{angle}」を中心に書く\n\n"
        "【作品情報】\n"
        f"出演: {', '.join(actress) if actress else '記載なし'}\n"
        f"メーカー: {item.get('maker') or '記載なし'}\n"
        f"形式: {' / '.join(tags) if tags else '記載なし'}\n"
        f"発売日: {format_date_jp(item.get('date'))}"
    )


def clean_comment(text):
    text = re.sub(r"[\r\n]+", " ", text or "").strip()
    text = text.strip("「」\"' ")
    text = re.sub(r"\*+", "", text)  # マークダウンの強調記号を除く
    if len(text) > 140:
        text = text[:139] + "…"
    return text


def ask_gemini(prompt):
    """戻り値: (本文 or None, 状態)  状態は "ok" / "blocked" / "error" """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9},
    }).encode("utf-8")

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as res:
                data = json.loads(res.read().decode("utf-8"))

            if (data.get("promptFeedback") or {}).get("blockReason"):
                return None, "blocked"
            candidates = data.get("candidates") or []
            if not candidates:
                return None, "blocked"
            cand = candidates[0]
            parts = (cand.get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
            if text:
                return text, "ok"
            if cand.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"):
                return None, "blocked"
            return None, "error"

        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                wait = 10 * (attempt + 1)
                print(f"   ⏳ 混雑中(HTTP {e.code})。{wait}秒待ってもう一度… ({attempt + 1}/3)")
                time.sleep(wait)
                continue
            print(f"   ⚠️ Gemini APIエラー HTTP {e.code}（設定やキーを確認してね）")
            return None, "error"
        except Exception as e:  # 通信エラーなど
            print(f"   ⚠️ Gemini呼び出しに失敗: {type(e).__name__}")
            time.sleep(2)
    return None, "error"


class CommentMaker:
    def __init__(self):
        self.ai_enabled = bool(GEMINI_API_KEY)
        self.fails_in_row = 0
        self.ai_ok = 0
        self.blocked = 0

    def apply(self, item):
        """item に comment / comment_kind / comment_tries を書き込む"""
        tries = int(item.get("comment_tries") or 0)

        if self.ai_enabled:
            text, status = ask_gemini(build_prompt(item, tries))
            time.sleep(GEMINI_INTERVAL_SEC)
            if status == "ok":
                comment = clean_comment(text)
                if comment:
                    item["comment"] = comment
                    item["comment_kind"] = "ai"
                    item["comment_tries"] = tries + 1
                    self.fails_in_row = 0
                    self.ai_ok += 1
                    return
            if status == "blocked":
                self.blocked += 1
                self.fails_in_row = 0
                item["comment_tries"] = tries + 1  # ブロックは数える（次は別の切り口で再挑戦）
            else:
                self.fails_in_row += 1  # 通信の失敗は数えない（あとで再挑戦できる）
                if self.fails_in_row >= MAX_AI_FAILS_IN_ROW:
                    print("   ⚠️ 連続で失敗したので、今回はAIコメントをお休みします")
                    self.ai_enabled = False

        if item.get("comment_kind") != "ai":
            item["comment"] = template_comment(item)
            item["comment_kind"] = "template"
            item.setdefault("comment_tries", tries)


# ------------------------------------------------------------------
# データの読み書き
# ------------------------------------------------------------------
def normalize_loaded(item):
    """保存済みデータを今の形に揃える（古い形式のデータも読めるようにする）"""
    cid = item.get("cid") or cid_from_old_item(item)
    title = (item.get("title") or "").strip()
    if not cid or not title:
        return None
    actress = [a for a in (item.get("actress") or []) if a]
    out = {
        "cid": cid,
        "title": title,
        "url": item.get("url") or "",
        "image_url": item.get("image_url") or "",
        "sample_images": item.get("sample_images") or [],
        "date": item.get("date") or "",
        "maker": item.get("maker") or "不明",
        "actress": actress,
        "genres": item.get("genres") or [],
        "tags": item.get("tags") or title_tags(title),
        "duration_min": item.get("duration_min"),
        "comment": item.get("comment") or "",
        "comment_kind": item.get("comment_kind") or "",
        "comment_tries": int(item.get("comment_tries") or 0),
    }
    if not out["comment_kind"]:
        generic = (not out["comment"]) or out["comment"] in OLD_GENERIC_COMMENTS
        out["comment_kind"] = "template" if generic else "ai"
    if out["comment_kind"] == "template" and (not out["comment"] or out["comment"] in OLD_GENERIC_COMMENTS):
        out["comment"] = template_comment(out)
    return out


def load_archive():
    if not os.path.exists(DATA_PATH):
        return {}
    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"❌ 保存済みデータを読めませんでした（{e}）。上書きを防ぐため中止します")
        sys.exit(1)
    archive = {}
    for item in raw if isinstance(raw, list) else []:
        norm = normalize_loaded(item)
        if norm:
            archive.setdefault(norm["cid"], norm)
    return archive


def save_archive(archive):
    items = sorted(archive.values(), key=lambda x: (x.get("date") or "", x["cid"]), reverse=True)
    folder = os.path.dirname(DATA_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp_path = DATA_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp_path, DATA_PATH)  # 書き込み途中で止まってもデータが壊れないように


# ------------------------------------------------------------------
# FANZA（DMM）APIから取得
# ------------------------------------------------------------------
def call_item_list(extra_params):
    params = {
        "api_id": API_ID,
        "affiliate_id": AFFILIATE_ID,
        "site": "FANZA",
        "service": "digital",
        "floor": "videoa",
        "sort": "date",
        "output": "json",
    }
    params.update(extra_params)
    url = "https://api.dmm.com/affiliate/v3/ItemList?" + urllib.parse.urlencode(params)

    last_error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as res:
                data = json.loads(res.read().decode("utf-8"))
            result = data.get("result") or {}
            status = result.get("status")
            if status is not None and str(status) != "200":
                raise RuntimeError(f"APIがエラーを返しました: status={status} message={result.get('message')}")
            return result.get("items") or []
        except Exception as e:
            last_error = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"FANZA APIから取得できませんでした: {last_error}")


def parse_api_item(raw):
    info = raw.get("iteminfo") or {}
    cid = raw.get("content_id") or raw.get("product_id")
    title = (raw.get("title") or "").strip()
    date = raw.get("date") or ""
    if not cid or not title or not date:
        return None

    images = raw.get("imageURL") or {}
    sample = raw.get("sampleImageURL") or {}
    sample_list = ((sample.get("sample_l") or {}).get("image")
                   or (sample.get("sample_s") or {}).get("image") or [])
    makers = info.get("maker") or []
    volume = re.search(r"\d+", str(raw.get("volume") or ""))

    return {
        "cid": cid,
        "title": title,
        "url": raw.get("affiliateURL") or "",
        "image_url": images.get("large") or images.get("list") or images.get("small") or "",
        "sample_images": [u for u in sample_list if u][:12],
        "date": date,
        "maker": (makers[0].get("name") if makers else None) or "不明",
        "actress": [a.get("name") for a in (info.get("actress") or []) if a.get("name")],
        "genres": [g.get("name") for g in (info.get("genre") or []) if g.get("name")],
        "tags": title_tags(title),
        "duration_min": int(volume.group(0)) if volume else None,
        "comment": "",
        "comment_kind": "",
        "comment_tries": 0,
    }


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def main():
    if not API_ID:
        print("❌ API_ID が設定されていません。")
        print("   GitHub の Settings > Secrets に API_ID を登録するか、")
        print("   手元で試すときは  API_ID=xxxx python3 get_new_releases.py  のように実行してね。")
        sys.exit(1)

    today = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    archive = load_archive()
    print(f"📚 保存済みの作品: {len(archive)}件")

    try:
        released_raw = call_item_list({
            "hits": 100,
            "gte_date": iso(today - timedelta(days=LOOKBACK_DAYS)),
            "lte_date": iso(today.replace(hour=23, minute=59, second=59)),
        })
        upcoming_raw = call_item_list({
            "hits": UPCOMING_ITEMS,
            "gte_date": iso(today + timedelta(days=1)),
            "lte_date": iso(today + timedelta(days=UPCOMING_DAYS)),
        })
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)  # 失敗を目立たせる（GitHub Actionsに赤いバツが付く）

    released = [p for p in map(parse_api_item, released_raw) if p]
    upcoming = [p for p in map(parse_api_item, upcoming_raw) if p]
    print(f"🔎 取得: 発売済み{len(released)}件 / 予約{len(upcoming)}件")
    today_str = today.strftime("%Y-%m-%d")
    if released and all(p["date"][:10] > today_str for p in released):
        print("⚠️ 発売済みのはずの取得結果が、すべて未来の日付でした。日付の絞り込みが効いていないかも。")

    newcomers = [p for p in released if p["cid"] not in archive][:NEW_ITEMS_PER_RUN]
    newcomers += [p for p in upcoming if p["cid"] not in archive and p["cid"] not in {n["cid"] for n in newcomers}]
    print(f"🆕 新しく追加: {len(newcomers)}件")

    maker = CommentMaker()
    for i, item in enumerate(newcomers, 1):
        maker.apply(item)
        archive[item["cid"]] = item
        print(f"  [{i}/{len(newcomers)}] {item['comment_kind']:8s} {item['comment'][:24]}")

    retry_targets = [
        it for it in sorted(archive.values(), key=lambda x: x.get("date") or "", reverse=True)
        if it.get("comment_kind") == "template" and int(it.get("comment_tries") or 0) < MAX_COMMENT_TRIES
        and it["cid"] not in {n["cid"] for n in newcomers}
    ][:RETRY_PER_RUN]
    if retry_targets and maker.ai_enabled:
        print(f"🔁 AIコメントに再挑戦: {len(retry_targets)}件")
        for item in retry_targets:
            if not maker.ai_enabled:
                break
            maker.apply(item)
            print(f"  {item['comment_kind']:8s} {item['comment'][:24]}")

    save_archive(archive)
    total_ai = sum(1 for it in archive.values() if it.get("comment_kind") == "ai")
    print(f"\n✨ 保存完了！ 合計{len(archive)}件（AIコメント{total_ai}件 / 代わりの文{len(archive) - total_ai}件）")
    print(f"   今回のAI成功 {maker.ai_ok}件 / ブロック {maker.blocked}件")


if __name__ == "__main__":
    main()
