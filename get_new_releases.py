#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FANZAの新作を取得し、AIコメントを付けて、過去分と一緒に貯めていくスクリプト。

GitHub Actions から毎日自動で実行されます。
手元で試すとき（API_ID は DMM アフィリエイトの管理画面で確認できます）:

    API_ID=xxxx GEMINI_API_KEY=xxxx python3 get_new_releases.py

保存先: site/src/data/new_releases.json
  - 作品ごとに1件。cid（作品ID）で重複を防ぎ、毎回「追記」します。
  - comment_kind が "ai" なら Gemini が書いたコメント（下書き）、"claude" なら Claude が読み直して仕上げたコメント、
    "template" なら作品情報から作った代わりの文。下書きと定型文は、毎日 0:20 の Claude の予約タスクが仕上げる（docs/claude-comments.md）。
  - updated は、その作品のデータ（コメント）を最後に変えた日（日本時間 YYYY-MM-DD）。sitemap の lastmod に使います。
  - sample_movie は、FANZAのサンプル動画のURL（無ければ空）。movie_tries は、品番で取り直しても見つからなかった回数。
保存先（出演者）: site/src/data/actresses.json … 出演者ごとの顔写真・体型・年齢の元データ・FANZAの全作品リンク（FANZA公式のデータ）
保存先（売れ筋）: site/src/data/ranking.json … FANZAの人気順（売れ筋）の上位6本（画面に出すのは先頭の3本。「VR作品を隠す」ときは、VRを除いて、次の順位から差し替える）

  python3 get_new_releases.py --refresh-only
      新しい作品の追加とAIコメントはせず、保存済みデータの取り直し（出演者・サンプル動画・プロフィール・ランキング）だけをする（Geminiは使わない）
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
# --- 件数の目安: Geminiの無料枠は「1日20回ほど」。新規(12+4)＋再挑戦(4)＝20回に収めています。---
# 有料枠にしたときは、この3つと GEMINI_MAX_CALLS を増やしてOK（例: 20 / 12 / 6 / 40）
NEW_ITEMS_PER_RUN = 12      # 1回の実行で新しく追加する「発売済み」作品の最大数
UPCOMING_ITEMS = 4          # 「予約受付中」として追加する作品の最大数
RETRY_PER_RUN = 4           # 代わりの文のままの作品に、AIコメントを再挑戦する最大数
GEMINI_MAX_CALLS = int(os.environ.get("GEMINI_MAX_CALLS", "20"))  # 1回の実行でGeminiに頼む最大回数
LOOKBACK_DAYS = 14          # 何日前までの発売作品を探すか
UPCOMING_DAYS = 14          # 何日先までの予約作品を探すか
MAX_COMMENT_TRIES = 3       # 1作品あたりのAI再挑戦の上限（ブロックされ続けるのを防ぐ）
GEMINI_INTERVAL_SEC = float(os.environ.get("GEMINI_INTERVAL_SEC", "5"))  # API制限対策の待ち時間
MAX_AI_FAILS_IN_ROW = 3     # 連続で失敗したら、その回はAI呼び出しをやめる
MAX_RETRY_WAIT_SEC = 60     # 「混雑中」で待つ最大秒数。これより長く待てと言われたら、その回はあきらめる

# --- FANZAのAPI（Geminiとは別。回数の上限は気にしなくてよいが、続けて呼ぶときは少し待つ）---
DMM_INTERVAL_SEC = float(os.environ.get("DMM_INTERVAL_SEC", "0.5"))  # APIを続けて呼ぶときの待ち時間
REFRESH_PER_RUN = 20        # 保存済みの作品を品番で取り直す最大数（出演者が空・サンプル動画が未取得）
REFRESH_WINDOW_DAYS = 30    # 出演者が空の作品を取り直す期間（発売日の何日後まで。それ以降は、載らないものとしてあきらめる）
MAX_MOVIE_TRIES = 3         # サンプル動画を品番で取り直す回数の上限（動画が無い作品を毎日探し続けないため）
PROFILE_PER_RUN = 30        # 出演者のプロフィールを取りに行く最大数
PROFILE_RECHECK_DAYS = 30   # 取得済みのプロフィールを、取り直すまでの日数（体型などはあとから載ることがある）
MAX_API_FAILS_IN_ROW = 3    # 取り直し・プロフィールの取得で、連続で失敗したら、その回はやめる
RANKING_ITEMS = 6           # 売れ筋ランキングの本数（画面に出すのは先頭3本。VR作品を隠したとき、次の順位から差し替えるために、多めに取っておく）
ACTRESSES_PATH = os.environ.get("ACTRESSES_PATH", os.path.join(os.path.dirname(DATA_PATH), "actresses.json"))
RANKING_PATH = os.environ.get("RANKING_PATH", os.path.join(os.path.dirname(DATA_PATH), "ranking.json"))

# --- コメントの書き分け ---
# 作品ごとに「切り口」「書き出し」「結び」の組み合わせを決めてAIに頼む（同じ作品・同じ回数なら、いつも同じ組み合わせ）。
# 全部のコメントが「出演者＋メーカー＋日付＋『ぜひチェック』」の同じ型にならないようにするため（検索エンジンに、似た文章の量産と見られないように）。
# どれも「作品情報にある事実」だけを材料にする（雰囲気・人気・期待度など、確かめられないことは書かせない）。
ANGLES = [
    "出演者の名前を主役にして、メーカーと発売日を添える（出演者が記載なしなら、メーカーを主役にする）",
    "メーカーのラインナップの一本として、メーカー名を主役にする",
    "発売日（何月何日か）を主役にする",
    "形式（VR・8Kなど）を主役にする（形式が記載なしなら、メーカーを主役にする）",
    "収録時間を主役にして、事実だけを淡々と伝える（収録時間が記載なしなら、発売日を主役にする）",
    "出演者の顔ぶれを主役にする（複数人なら人数や「ほか○名」。記載なしなら、メーカーを主役にする）",
]
OPENINGS = [
    "出演者名から書き出す（記載なしのときは、メーカー名から）",
    "メーカー名から書き出す",
    "発売日（○月○日）から書き出す",
    "「新作」「新着」「一本」などの言葉から書き出す",
]
CLOSINGS = [
    "呼びかけは入れず、事実を言い切って終える",
    "最後に、くわしい情報はFANZAのページで確認できる、と添える",
    "最後に、発売日をもう一度、さらりと添える",
    "最後に、収録時間（記載なしなら、メーカー名）を添える",
]
# 使いすぎて、どのコメントも同じ結びになってしまう言い回し（AIへの依頼で、使わないよう頼む。採用の可否には使わない）
AVOID_PHRASES = ["気になる方は", "チェック", "ぜひ", "いまのうちに", "お早めに", "お見逃しなく", "おすすめ"]
# 確かめられない評価（人気・期待度・評判）や、大げさな言い方。入っていたら採用せず、定型文にして、Claude の書き直しに回す
# （docs/claude-comments.md の「人気・知名度の評価は書かない」と同じ考え方。scripts/claude_comments.py にも同じ一覧がある。tests/test_script.py が、2つが同じかを調べる）
HYPE_WORDS = ["待望", "話題", "熱い視線", "高い関心", "期待が高まる", "期待が膨らむ", "期待作", "期待の", "大人気", "人気の", "ファンの", "ファンから",
              "おなじみ", "必見", "間違いなし", "至高", "極上", "圧倒的", "注目の", "見逃せない", "目が離せない", "心を奪", "豪華な"]
# 出してはいけない言葉（過激な表現・未成年を連想させる言葉）。scripts/claude_comments.py と同じ一覧
EXPLICIT_WORDS = ["中出", "射精", "精液", "挿入", "フェラ", "レイプ", "強姦", "凌辱", "陵辱", "輪姦", "痴漢", "盗撮", "調教"]
MINOR_WORDS = ["未成年", "少女", "ロリ", "児童", "幼", "女子高生", "女子校生", "女子中", "中学生", "高校生", "小学生",
               "JK", "JC", "JS", "制服"]


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


def day_key(value):
    """日付の文字列から "YYYY-MM-DD" を取り出す（形が違えば空文字）"""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:$|[ T])", str(value or ""))
    return m.group(1) if m else ""


FORMAT_TAG = re.compile(r"[0-9A-Za-z]{1,6}")  # 形式タグ（VR・8K など）。日本語の括弧書きはタイトルの一部なので、タグにしない


def clean_tags(tags):
    """形式タグだけを残す（英数字6文字まで。重複なし）。タイトルの断片を、AIへの依頼や定型文に混ぜないため"""
    out = []
    for t in tags or []:
        t = t.strip() if isinstance(t, str) else ""
        if FORMAT_TAG.fullmatch(t) and t not in out:
            out.append(t)
    return out[:4]


def title_tags(title):
    """タイトルの【VR】【8K】のような括弧書きから、形式タグだけを取り出す"""
    return clean_tags(re.findall(r"【([^】]{1,10})】", title or ""))


def is_vr_item(item):
    """VR作品か。タイトルの【…VR…】・形式タグ・ジャンル（VR専用・ハイクオリティVR など）のどれかに VR が入っていれば VR。
    site/src/lib/items.js の isVrWork と同じ決まり（画面の「VR作品を隠す」の判定。売れ筋は、ここで印を付けて保存する）"""
    title = item.get("title") or ""
    if re.search(r"【[^】]*VR[^】]*】", title, re.I):
        return True
    return any("VR" in str(x).upper() for x in (item.get("tags") or []) + (item.get("genres") or []))


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


def rejected_words(text):
    """AIコメントに入っていたら採用しない言葉（確かめられない評価・過激な言葉・未成年を連想させる言葉）のリスト（なければ空）"""
    low = (text or "").lower()
    return [w for w in HYPE_WORDS + EXPLICIT_WORDS + MINOR_WORDS if w.lower() in low]


def build_prompt(item, tries, today=None):
    """AIに渡す文章。タイトルは渡しません（過激な言葉でブロックされやすいため）"""
    actress = item.get("actress") or []
    tags = item.get("tags") or []
    cid = item.get("cid")
    # 切り口・書き出し・結びは、それぞれ別の数から選ぶ（組み合わせがかたよらないように）。再挑戦（tries が増える）のときは、別の組み合わせになる
    angle = ANGLES[stable_number(cid, "angle", tries) % len(ANGLES)]
    opening = OPENINGS[stable_number(cid, "opening", tries) % len(OPENINGS)]
    closing = CLOSINGS[stable_number(cid, "closing", tries) % len(CLOSINGS)]
    minutes = item.get("duration_min")
    minutes_text = f"約{minutes}分" if isinstance(minutes, int) and not isinstance(minutes, bool) and minutes > 0 else "記載なし"
    today = today or datetime.now(JST).strftime("%Y-%m-%d")
    if day_key(item.get("date")) and day_key(item.get("date")) > today:
        status_rule = ("この作品はまだ発売前。ただし「予約受付中」「発売予定」「発売される」「まもなく」「〜を前に」「待ちきれない」のような、"
                       "発売日をすぎると古くなる言い方は使わず、「○月○日発売」と日付だけで伝える")
    else:
        status_rule = "この作品は発売済み。「発売されました」「発売中」などと書いてよい"
    return (
        "映像作品の紹介サイトに載せる、60〜90文字の短い紹介コメントを日本語で1つだけ書いてください。\n\n"
        "【書き方のルール】\n"
        "- 落ち着いた、上品なトーンで、「です・ます」調にする\n"
        "- 使ってよい情報は、下の【作品情報】にあることだけ。作品の中身（ストーリー・雰囲気・演出）、出演者の容姿・経歴・人気、"
        "作品の評判や期待度は書かない。分からないことは書かない\n"
        "- 過激・直接的な表現や、性的な描写は使わない\n"
        "- 出演者名は入れてよい（1回まで。複数人のときは「○○さんほか○名」でもよい）\n"
        f"- 次の言い回しは使わない: {'、'.join(AVOID_PHRASES)}\n"
        f"- {status_rule}\n"
        "- 挨拶・前置き・絵文字・飾りの記号は入れず、コメント本文だけを出力する\n"
        f"- 切り口: {angle}\n"
        f"- 書き出し: {opening}\n"
        f"- 結び: {closing}\n\n"
        "【作品情報】\n"
        f"出演: {', '.join(actress) if actress else '記載なし'}\n"
        f"メーカー: {item.get('maker') or '記載なし'}\n"
        f"形式: {' / '.join(tags) if tags else '記載なし'}\n"
        f"収録時間: {minutes_text}\n"
        f"発売日: {format_date_jp(item.get('date'))}"
    )


# コメントの種類: template＝定型文、ai＝Gemini の下書き、claude＝Claude が仕上げたもの
COMMENT_KINDS = ("ai", "claude", "template")
WRITTEN_KINDS = ("ai", "claude")  # 文章が書かれている（定型文ではない）もの


def strip_wrapping(text):
    """全体が「…」や "…" で囲まれていれば、その囲みだけを外す（文の途中の「」は残す）。
    対になる相手が無い、はじめの「・終わりの」（片方だけのかっこ）も外す"""
    pairs = (("「", "」"), ("『", "』"), ('"', '"'), ("'", "'"))
    changed = True
    while changed and len(text) >= 2:
        changed = False
        for left, right in pairs:
            inner = text[len(left):-len(right)]
            if text.startswith(left) and text.endswith(right) and left not in inner and right not in inner:
                text = inner.strip()
                changed = True
            elif left != right and text.startswith(left) and right not in text:
                text = text[len(left):].strip()
                changed = True
            elif left != right and text.endswith(right) and left not in text:
                text = text[:-len(right)].strip()
                changed = True
    return text


def clean_comment(text):
    text = re.sub(r"[\r\n]+", " ", text or "").strip()
    text = strip_wrapping(text)
    text = re.sub(r"\*+", "", text)  # マークダウンの強調記号を除く
    if len(text) > 140:
        text = text[:139] + "…"
    return text


def gemini_error_info(body):
    """Geminiのエラー本文から (理由の短い説明, 1日の上限か, 待つように言われた秒数 or None) を取り出す"""
    text = body or ""
    message = ""
    try:
        message = str((json.loads(text).get("error") or {}).get("message", ""))
    except (ValueError, AttributeError):
        pass
    message = re.sub(r"\s+", " ", message).strip()[:240]
    # 例: quotaId が "GenerateRequestsPerDayPerProjectPerModel-FreeTier" → 1日あたりの上限
    daily = bool(re.search(r"per\s*day|daily", text, re.IGNORECASE))
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', text)
    return message, daily, (float(m.group(1)) if m else None)


def read_error_body(err):
    try:
        return err.read().decode("utf-8", "replace")[:4000]
    except Exception:
        return ""


def ask_gemini(prompt):
    """戻り値: (本文 or None, 状態)  状態は "ok" / "blocked" / "error" / "quota"（利用上限）"""
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
                message, daily, retry_after = gemini_error_info(read_error_body(e))
                reason = f" 理由: {message}" if message else ""
                too_long = retry_after is not None and retry_after > MAX_RETRY_WAIT_SEC
                if e.code == 429 and (daily or too_long):
                    # 1日の上限に達している。待っても治らないので、この回はAIをお休みする
                    print(f"   ⛔ Geminiの利用上限に達しました(HTTP 429)。{reason}")
                    return None, "quota"
                if attempt == 2:
                    print(f"   ⚠️ 混雑が続くのであきらめます(HTTP {e.code}){reason}")
                    break
                wait = min(retry_after + 1, MAX_RETRY_WAIT_SEC) if retry_after else 10 * (attempt + 1)
                print(f"   ⏳ 混雑中(HTTP {e.code}){reason} {wait:.0f}秒待ってもう一度… ({attempt + 1}/3)")
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
        self.rejected = 0        # 使わない言い回しが入っていて、採用しなかった数
        self.calls = 0           # Geminiに頼んだ回数
        self.stop_reason = ""    # AIをお休みした理由（なければ空）

    def stop(self, reason):
        self.ai_enabled = False
        self.stop_reason = reason

    def apply(self, item):
        """item に comment / comment_kind / comment_tries を書き込む"""
        tries = int(item.get("comment_tries") or 0)

        if self.ai_enabled and self.calls >= GEMINI_MAX_CALLS:
            print(f"   ⏸ 1回の実行でAIに頼む上限({GEMINI_MAX_CALLS}回)に達したので、残りは代わりの文にします")
            self.stop(f"1回の上限（{GEMINI_MAX_CALLS}回）に達した")

        if self.ai_enabled:
            self.calls += 1
            text, status = ask_gemini(build_prompt(item, tries))
            time.sleep(GEMINI_INTERVAL_SEC)
            bad = []
            if status == "ok":
                comment = clean_comment(text)
                bad = rejected_words(comment)
                if comment and not bad:
                    item["comment"] = comment
                    item["comment_kind"] = "ai"
                    item["comment_tries"] = tries + 1
                    self.fails_in_row = 0
                    self.ai_ok += 1
                    return
            if bad:
                # 確かめられない評価などが入っていた → 採用しない。定型文にして、次は別の切り口で再挑戦（上限まで続けば、Claude が書き直す）
                self.rejected += 1
                self.fails_in_row = 0
                item["comment_tries"] = tries + 1
                print(f"   ⚠️ 使わない言い回し（{'、'.join(bad[:3])}）が入っていたので、採用しませんでした")
            elif status == "quota":
                self.stop("Geminiの利用上限（無料枠は1日20回ほど）に達した")  # 数えない（あとで再挑戦できる）
            elif status == "blocked":
                self.blocked += 1
                self.fails_in_row = 0
                item["comment_tries"] = tries + 1  # ブロックは数える（次は別の切り口で再挑戦）
            else:
                self.fails_in_row += 1  # 通信の失敗は数えない（あとで再挑戦できる）
                if self.fails_in_row >= MAX_AI_FAILS_IN_ROW:
                    print("   ⚠️ 連続で失敗したので、今回はAIコメントをお休みします")
                    self.stop("連続で失敗した（Geminiが混み合っている）")

        if item.get("comment_kind") not in WRITTEN_KINDS:
            item["comment"] = template_comment(item)
            item["comment_kind"] = "template"
            item.setdefault("comment_tries", tries)


# ------------------------------------------------------------------
# データの読み書き
# ------------------------------------------------------------------
def normalize_loaded(item):
    """保存済みデータの1件を今の形に揃える（足りない項目は既定値で補う）。読めない場合は None"""
    cid = str(item.get("cid") or "").strip()
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
        "tags": clean_tags(item.get("tags")) or title_tags(title),  # 保存済みのタグも、形式タグだけに直す
        "duration_min": item.get("duration_min"),
        "sample_movie": safe_https_url(item.get("sample_movie"), MOVIE_HOSTS),
        "movie_tries": int(item.get("movie_tries") or 0),
        "comment": item.get("comment") or "",
        "comment_kind": item.get("comment_kind") if item.get("comment_kind") in COMMENT_KINDS else "template",
        "comment_tries": int(item.get("comment_tries") or 0),
        "updated": day_key(item.get("updated")),
    }
    if out["comment_kind"] == "template" and not out["comment"]:
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
    if not isinstance(raw, list):
        print("❌ 保存済みデータの形が違います（作品のリストではありません）。上書きを防ぐため中止します")
        sys.exit(1)
    archive = {}
    unreadable = 0
    for item in raw:
        norm = normalize_loaded(item) if isinstance(item, dict) else None
        if norm:
            archive.setdefault(norm["cid"], norm)
        else:
            unreadable += 1
    if unreadable:
        # 黙って捨てると、保存のときに作品が消えてしまう。止めて気づけるようにする
        print(f"❌ 保存済みデータに、読めない作品が{unreadable}件あります（cid かタイトルが無い）。消えてしまうのを防ぐため中止します")
        sys.exit(1)
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
def call_api(endpoint, params):
    """FANZA(DMM)アフィリエイトAPIを呼んで、応答の result（辞書）を返す。失敗したら RuntimeError"""
    query = {"api_id": API_ID, "affiliate_id": AFFILIATE_ID, "output": "json"}
    query.update(params)
    url = f"https://api.dmm.com/affiliate/v3/{endpoint}?" + urllib.parse.urlencode(query)

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
            return result
        except Exception as e:
            last_error = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"FANZA APIから取得できませんでした: {last_error}")


def call_item_list(extra_params):
    params = {"site": "FANZA", "service": "digital", "floor": "videoa", "sort": "date"}
    params.update(extra_params)
    return call_api("ItemList", params).get("items") or []


def call_actress_search(params):
    """出演者検索の応答から (出演者の一覧, 該当した全人数 or None) を返す。全人数が一覧より多ければ、一覧は途中までということ"""
    result = call_api("ActressSearch", params)
    try:
        total = int(result.get("total_count"))
    except (TypeError, ValueError):
        total = None
    return result.get("actress") or [], total


def safe_https_url(url, host_suffixes):
    """https のURLだけを通す（http は https に直す）。ホストが host_suffixes のどれかでなければ空文字"""
    if not isinstance(url, str):
        return ""
    url = url.strip()
    if re.search(r"[\\\x00-\x20\x7f]", url):  # バックスラッシュ・空白・制御文字は、ブラウザと解釈がずれるため通さない
        return ""
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or "@" in parsed.netloc or not any(host == suffix or host.endswith("." + suffix) for suffix in host_suffixes):
        return ""
    return url


MOVIE_HOSTS = ("dmm.co.jp",)
IMAGE_HOSTS = ("dmm.co.jp",)
LIST_HOSTS = ("fanza.co.jp", "dmm.co.jp")


def pick_sample_movie(raw):
    """サンプル動画のURL（476x306）。パソコンとスマホの両方で見られるものだけ。無ければ空文字"""
    movie = raw.get("sampleMovieURL")
    if not isinstance(movie, dict):
        return ""
    if str(movie.get("pc_flag")) != "1" or str(movie.get("sp_flag")) != "1":
        return ""
    return safe_https_url(movie.get("size_476_306"), MOVIE_HOSTS)


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
        "sample_movie": pick_sample_movie(raw),
        "movie_tries": 0,
        "comment": "",
        "comment_kind": "",
        "comment_tries": 0,
        "updated": "",  # 保存するときに main() が今日の日付を入れる
    }


def apply_fresh(old, fresh, today_str):
    """保存済みの作品 old に、取り直した fresh から、空だった項目（出演者・ジャンル・サンプル動画・サンプル画像・
    収録時間・パッケージ画像）を補い、発売日が変わっていれば直す。

    ・すでに入っている項目は書き換えない（空欄を埋めるだけ）。発売日だけは、FANZAで延期・前倒しされたら合わせる
    ・補ったら更新日（updated）を進める（sitemap の lastmod に使う）
    ・ジャンル（商品タグ）・サンプル画像・収録時間は、予約の作品には、発売が近づいてからFANZAに載ることが多い
    補った項目名のリスト（"actress" / "genres" / "sample_movie" / "sample_images" / "duration_min" / "image_url" / "date"）を返す
    """
    changed = []
    fresh_day = day_key(fresh.get("date"))
    old_day = day_key(old.get("date"))
    if fresh_day and fresh_day != old_day:
        old["date"] = fresh["date"]  # 発売日の延期・前倒し（トップの「発売中/予約」・カレンダー・月のページに使う）
        changed.append("date")
        # コメントに古い発売日（例: 11月1日。「11月1日」の中の「1月1日」は別の日として扱う）が書いてあれば、間違いになる。
        # 文章のコメントは定型文に戻し（その日のうちに Claude が書き直す）、定型文は新しい発売日で作り直す
        old_date_re = re.compile(rf"(?<![0-9０-９]){int(old_day[5:7])}月{int(old_day[8:10])}日") if old_day else None
        if old.get("comment_kind") == "template":
            old["comment"] = template_comment(old)
            changed.append("comment")
        elif old_date_re and old.get("comment_kind") in WRITTEN_KINDS and old_date_re.search(old.get("comment") or ""):
            old["comment"] = template_comment(old)
            old["comment_kind"] = "template"
            changed.append("comment")
    if not old.get("sample_images") and fresh.get("sample_images"):
        old["sample_images"] = list(fresh["sample_images"])
        changed.append("sample_images")
    if not old.get("duration_min") and fresh.get("duration_min"):
        old["duration_min"] = fresh["duration_min"]
        changed.append("duration_min")
    if not old.get("image_url") and fresh.get("image_url"):
        old["image_url"] = fresh["image_url"]
        changed.append("image_url")
    if not old.get("actress") and fresh.get("actress"):
        old["actress"] = list(fresh["actress"])
        changed.append("actress")
    if not old.get("genres") and fresh.get("genres"):
        old["genres"] = list(fresh["genres"])
        changed.append("genres")
    if not old.get("sample_movie") and fresh.get("sample_movie"):
        old["sample_movie"] = fresh["sample_movie"]
        changed.append("sample_movie")
    if changed:
        old["updated"] = today_str
    return changed


def refresh_from_fetched(archive, fetched, today_str):
    """今回の取得（発売済み・予約）にもう一度出てきた保存済みの作品に、空だった項目を補う（APIの追加呼び出しなし）。
    FANZAは、予約の作品に出演者・サンプル動画をあとから載せることがある。{cid: [補った項目名]} を返す"""
    filled = {}
    for fresh in fetched:
        old = archive.get(fresh["cid"])
        if old is None:
            continue
        changed = apply_fresh(old, fresh, today_str)
        if changed:
            filled[old["cid"]] = changed
    return filled


def refetch_targets(archive, today_str, skip):
    """品番で取り直す保存済みの作品（最大 REFRESH_PER_RUN 件）。
    ・出演者が空の作品（発売日の REFRESH_WINDOW_DAYS 日後まで。予約も含む）を先に
    ・次に、発売済みでサンプル動画がまだ無い作品（取り直しは MAX_MOVIE_TRIES 回まで）
    skip は、今回すでに取得できた作品の cid"""
    window_start = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=REFRESH_WINDOW_DAYS)).strftime("%Y-%m-%d")
    today_day = datetime.strptime(today_str, "%Y-%m-%d")
    cast, movie = [], []
    for item in archive.values():
        if item["cid"] in skip:
            continue
        day = day_key(item.get("date"))
        if not item.get("actress") and day >= window_start:
            cast.append(item)
        elif not item.get("sample_movie") and day and day <= today_str and int(item.get("movie_tries") or 0) < MAX_MOVIE_TRIES:
            movie.append(item)
    # 出演者は、発売日が今日に近い作品から（出演者は発売の前後に載ることが多い）。動画は、新しい作品から
    closest_first = lambda x: (abs((datetime.strptime(day_key(x.get("date")), "%Y-%m-%d") - today_day).days), x["cid"])
    cast.sort(key=closest_first)
    movie.sort(key=lambda x: (x.get("date") or "", x["cid"]), reverse=True)
    # 枠は出演者を先に使うが、動画にも最低でも半分（REFRESH_PER_RUN の半分）は残す。どちらかが余れば、もう一方が使う
    cast_part = cast[: max(REFRESH_PER_RUN // 2, REFRESH_PER_RUN - len(movie))]
    return cast_part + movie[: REFRESH_PER_RUN - len(cast_part)]


def refetch_by_cid(archive, today_str, skip, raw_sink=None):
    """出演者が空・サンプル動画が未取得の保存済みの作品を、品番（cid）を指定して取り直す。
    {cid: [補った項目名]} と、取り直した件数を返す。APIが続けて失敗したら、その回はやめる。
    raw_sink（リスト）を渡すと、取り直した作品の生データを入れる（出演者の id を、プロフィール取得で使うため）"""
    filled = {}
    done = 0
    fails = 0
    for item in refetch_targets(archive, today_str, skip):
        try:
            rows = call_item_list({"cid": item["cid"], "hits": 1})
            fails = 0
        except RuntimeError as e:
            fails += 1
            print(f"  ⚠️ {item['cid']} を取り直せませんでした: {e}")
            if fails >= MAX_API_FAILS_IN_ROW:
                print("  ⏸ 続けて失敗したので、今回の取り直しはやめます")
                break
            continue
        time.sleep(DMM_INTERVAL_SEC)
        done += 1
        if raw_sink is not None:
            raw_sink.extend(rows)
        fresh = next((p for p in map(parse_api_item, rows) if p and p["cid"] == item["cid"]), None)
        if fresh is not None:
            changed = apply_fresh(item, fresh, today_str)
            if changed:
                filled[item["cid"]] = changed
        if not item.get("sample_movie") and day_key(item.get("date")) <= today_str:
            item["movie_tries"] = int(item.get("movie_tries") or 0) + 1  # 発売後なのに動画が無い（あきらめるまでの回数）
    return filled, done


# ------------------------------------------------------------------
# 出演者のプロフィール（FANZA公式の出演者データ。顔写真・体型・FANZAの全作品リンク）
# ------------------------------------------------------------------
def parse_measure(value, low, high):
    """体型の数字（"86" のような文字列でも、86 でもよい）。範囲外・数字でなければ None"""
    m = re.fullmatch(r"\s*(\d{1,3})\s*", str(value if value is not None else ""))
    n = int(m.group(1)) if m else None
    return n if n is not None and low <= n <= high else None


def valid_birthday(value, today_str):
    """生年月日（YYYY-MM-DD）。年齢が 18〜80 歳の範囲でなければ空文字（あり得ない値は使わない）"""
    day = day_key(value)
    if not day:
        return ""
    y, m, d = int(day[:4]), int(day[5:7]), int(day[8:10])
    try:
        datetime(y, m, d)  # 1999-02-30 のような、無い日付は使わない
    except ValueError:
        return ""
    ty, tm, td = int(today_str[:4]), int(today_str[5:7]), int(today_str[8:10])
    age = ty - y - ((tm, td) < (m, d))
    return day if 18 <= age <= 80 else ""


def clean_actress_entry(raw, today_str):
    """出演者データ（APIの応答 または 保存済みの1件）を、保存する形に整える。使えなければ None"""
    if not isinstance(raw, dict):
        return None
    aid = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or "").strip()
    if not re.fullmatch(r"\d{1,12}", aid) or not name:
        return None
    images = raw.get("imageURL") if isinstance(raw.get("imageURL"), dict) else {}
    small = raw.get("image_small") or images.get("small")
    large = raw.get("image_large") or images.get("large")
    cup = str(raw.get("cup") or "").strip().upper()
    list_url = raw.get("list_url")
    if list_url is None and isinstance(raw.get("listURL"), dict):
        list_url = raw["listURL"].get("digital")
    return {
        "id": aid,
        "name": name[:100],
        "ruby": str(raw.get("ruby") or "").strip()[:100],
        "image_small": safe_https_url(small, IMAGE_HOSTS),
        "image_large": safe_https_url(large, IMAGE_HOSTS),
        "bust": parse_measure(raw.get("bust"), 50, 160),
        "cup": cup if re.fullmatch(r"[A-Z]", cup) else "",
        "waist": parse_measure(raw.get("waist"), 40, 130),
        "hip": parse_measure(raw.get("hip"), 50, 160),
        "height": parse_measure(raw.get("height"), 120, 210),
        "birthday": valid_birthday(raw.get("birthday"), today_str),
        "list_url": safe_https_url(list_url, LIST_HOSTS),
        "fetched": day_key(raw.get("fetched")),
    }


PROFILE_DETAIL_KEYS = ("image_small", "image_large", "bust", "cup", "waist", "hip", "height", "birthday", "list_url")


def has_profile_details(entry):
    """顔写真・体型・生年月日・FANZAの全作品リンクの、どれか1つでも入っているか"""
    return any(entry.get(k) not in (None, "") for k in PROFILE_DETAIL_KEYS)


def load_actress_state(today_str):
    """保存済みの出演者データ {"actresses": {id: 1件}, "unmatched": {名前: 探した日}} を読む。
    壊れていて読めないときは None を返す（呼び出し側は、出演者プロフィールの更新だけをやめて、ファイルは上書きしない。
    新しい作品の追加やコメントは、出演者データの不具合では止めないため）"""
    state = {"actresses": {}, "unmatched": {}}
    if not os.path.exists(ACTRESSES_PATH):
        return state
    try:
        with open(ACTRESSES_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ 出演者データを読めませんでした（{e}）。上書きを防ぐため、出演者プロフィールの更新はやめます")
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("actresses"), list):
        print("⚠️ 出演者データの形が違います。上書きを防ぐため、出演者プロフィールの更新はやめます")
        return None
    for row in raw["actresses"]:
        entry = clean_actress_entry(row, today_str)
        if entry:
            state["actresses"].setdefault(entry["id"], entry)
    if isinstance(raw.get("unmatched"), dict):
        state["unmatched"] = {str(k): day_key(v) for k, v in raw["unmatched"].items() if k and day_key(v)}
    return state


def save_actress_state(state):
    rows = sorted(state["actresses"].values(), key=lambda e: int(e["id"]))
    folder = os.path.dirname(ACTRESSES_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp_path = ACTRESSES_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"actresses": rows, "unmatched": dict(sorted(state["unmatched"].items()))}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp_path, ACTRESSES_PATH)


def collect_actresses(raw_items):
    """作品の生データから、出演者（id・名前・ふりがな）を集める"""
    found = {}
    for raw in raw_items:
        for a in ((raw.get("iteminfo") or {}).get("actress") or []):
            aid = str(a.get("id") or "").strip()
            name = str(a.get("name") or "").strip()
            if re.fullmatch(r"\d{1,12}", aid) and name:
                found.setdefault(aid, {"id": aid, "name": name, "ruby": str(a.get("ruby") or "").strip()})
    return list(found.values())


def upsert_actresses(state, found, today_str):
    """見つけた出演者を、保存データに足す（すでにあれば、名前とふりがなだけを更新）。新しく足した件数を返す"""
    added = 0
    for a in found:
        entry = state["actresses"].get(a["id"])
        if entry is None:
            state["actresses"][a["id"]] = clean_actress_entry(a, today_str)
            added += 1
        else:
            entry["name"] = a["name"][:100]
            if a["ruby"]:
                entry["ruby"] = a["ruby"][:100]
    return added


def update_profiles(state, archive, today_str):
    """出演者のプロフィールを、FANZAの出演者検索（ActressSearch）で取る（最大 PROFILE_PER_RUN 回）。
    ① まだ取っていない出演者 → ② 保存済みの作品にいるのに id が分からない名前（名前の完全一致が1人だけのときだけ採用）
    → ③ 取ってから PROFILE_RECHECK_DAYS 日たった出演者（体型などは、あとから載ることがある）の順。
    取れた件数と、名前で見つからなかった件数を返す"""
    entries = state["actresses"]
    recheck_before = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=PROFILE_RECHECK_DAYS)).strftime("%Y-%m-%d")
    new_ids = sorted((e["id"] for e in entries.values() if not e["fetched"]), key=int, reverse=True)
    known_names = {e["name"] for e in entries.values()}
    archive_names = sorted({n for it in archive.values() for n in it.get("actress") or []})
    unknown_names = [n for n in archive_names if n not in known_names and not (state["unmatched"].get(n, "") > recheck_before)]
    stale_ids = sorted((e["id"] for e in entries.values() if e["fetched"] and e["fetched"] <= recheck_before), key=lambda i: (entries[i]["fetched"], int(i)))
    jobs = [("id", i) for i in new_ids] + [("name", n) for n in unknown_names] + [("id", i) for i in stale_ids]

    fetched = unmatched = fails = 0
    for kind, key in jobs[:PROFILE_PER_RUN]:
        try:
            if kind == "id":
                rows, total = call_actress_search({"actress_id": key, "hits": 1})
            else:
                rows, total = call_actress_search({"keyword": key, "hits": 100})
            fails = 0
        except RuntimeError as e:
            fails += 1
            print(f"  ⚠️ 出演者（{key}）を取れませんでした: {e}")
            if fails >= MAX_API_FAILS_IN_ROW:
                print("  ⏸ 続けて失敗したので、今回のプロフィール取得はやめます")
                break
            continue
        time.sleep(DMM_INTERVAL_SEC)
        if kind == "id":
            row = next((r for r in rows if str(r.get("id")) == key), None)
            entry = clean_actress_entry(row, today_str) if row else None
            old = entries[key]
            if entry and not has_profile_details(entry) and has_profile_details(old):
                old["fetched"] = today_str  # 中身の無い応答（一時的な不具合かも）で、保存済みの顔写真・体型を消さない
            elif entry:
                entry["fetched"] = today_str
                entries[key] = entry
                fetched += 1
            else:
                old["fetched"] = today_str  # 見つからなかった。毎日探し続けないよう、取り直しの日まで待つ
        else:
            exact = [r for r in rows if str(r.get("name") or "").strip() == key]
            cut_short = total is not None and total > len(rows)  # 一覧が途中までのとき、同じ名前の人が一覧の外にもいるかもしれない
            entry = clean_actress_entry(exact[0], today_str) if len(exact) == 1 and not cut_short else None
            if entry and entry["id"] not in entries:
                entry["fetched"] = today_str
                entries[entry["id"]] = entry
                fetched += 1
            elif entry:
                entries[entry["id"]]["fetched"] = entries[entry["id"]]["fetched"] or today_str
            else:
                state["unmatched"][key] = today_str  # 0人 または 同じ名前が2人以上。推測では選ばない
                unmatched += 1
    return fetched, unmatched


# ------------------------------------------------------------------
# 売れ筋ランキング（FANZAの人気順の上位）
# ------------------------------------------------------------------
def fetch_ranking_from(raw_items):
    """FANZAの人気順（sort=rank）の応答から、上位 RANKING_ITEMS 本の表示用データを作る（vr = VR作品か）。1本も無ければ RuntimeError"""
    rows = [p for p in map(parse_api_item, raw_items) if p][:RANKING_ITEMS]
    if not rows:
        raise RuntimeError("ランキングが空でした")
    return [
        {"rank": i, "cid": p["cid"], "title": p["title"], "url": p["url"], "image_url": p["image_url"], "date": day_key(p["date"]),
         "maker": p["maker"], "actress": p["actress"], "vr": is_vr_item(p)}
        for i, p in enumerate(rows, 1)
    ]


def fetch_ranking_with_raw():
    """(ランキング, 生データ) を返す。生データは、出演者の id を集めるために使う"""
    raw = call_item_list({"hits": RANKING_ITEMS, "sort": "rank"})
    return fetch_ranking_from(raw), raw


def save_ranking(items, today_str):
    folder = os.path.dirname(RANKING_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp_path = RANKING_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"date": today_str, "items": items}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp_path, RANKING_PATH)


def run_stage(name, func):
    """追加の取得（出演者・ランキングなど）が失敗しても、毎日の更新全体は止めない"""
    try:
        return func()
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ {name}に失敗しました（ほかの更新は続けます）: {type(e).__name__}: {e}")
        print(f"::warning title={name}に失敗::{type(e).__name__}: {e}")
        return None


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def write_step_summary(lines):
    """GitHub Actions の実行ページに出る「結果の要約」を書く（ログを開かなくても結果がわかる）"""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass


def main():
    if not API_ID:
        print("❌ API_ID が設定されていません。")
        print("   GitHub の Settings > Secrets に API_ID を登録するか、")
        print("   手元で試すときは  API_ID=xxxx python3 get_new_releases.py  のように実行してね。")
        sys.exit(1)

    refresh_only = "--refresh-only" in sys.argv[1:]  # 新しい作品の追加とAIコメントはせず、取り直しだけをする
    today = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = today.strftime("%Y-%m-%d")
    archive = load_archive()
    actress_state = load_actress_state(today_str)  # 壊れていたら None（プロフィールの更新だけをやめる。ほかの更新は続ける）
    if actress_state is None:
        print("::warning title=出演者データを読めませんでした::actresses.json が壊れています。出演者プロフィールの更新はスキップしました（ファイルは変更していません）")
    print(f"📚 保存済みの作品: {len(archive)}件 / 出演者: {len(actress_state['actresses']) if actress_state else '読めず'}人")
    if refresh_only:
        print("🔄 取り直しだけを行います（新しい作品の追加・AIコメントはしません）")

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
        print(f"::error title=FANZAからの取得に失敗::{e}")
        write_step_summary(["### ❌ FANZAからの取得に失敗しました", "", f"{e}", "", "保存済みのデータは変更していません。"])
        sys.exit(1)  # 失敗を目立たせる（GitHub Actionsに赤いバツが付く）

    released = [p for p in map(parse_api_item, released_raw) if p]
    upcoming = [p for p in map(parse_api_item, upcoming_raw) if p]
    print(f"🔎 取得: 発売済み{len(released)}件 / 予約{len(upcoming)}件")
    if released and all(p["date"][:10] > today_str for p in released):
        print("⚠️ 発売済みのはずの取得結果が、すべて未来の日付でした。日付の絞り込みが効いていないかも。")

    # 保存済みで、出演者・サンプル動画が空の作品を補う。まず今回の取得に載っていた分（APIの追加呼び出しなし）、
    # 次に、取得に出てこなかった分を品番で取り直す
    filled = refresh_from_fetched(archive, released + upcoming, today_str)
    refetched_raw = []  # 品番で取り直した作品の生データ（出演者の id を、プロフィール取得で使う）
    refetched = run_stage("保存済み作品の取り直し", lambda: refetch_by_cid(archive, today_str, {p["cid"] for p in released + upcoming}, refetched_raw))
    if refetched:
        filled.update({cid: sorted(set(filled.get(cid, [])) | set(fields)) for cid, fields in refetched[0].items()})
    filled_cast = [c for c, f in filled.items() if "actress" in f]
    filled_movie = [c for c, f in filled.items() if "sample_movie" in f]
    filled_genres = [c for c, f in filled.items() if "genres" in f]
    if filled_genres:
        print(f"🏷️ ジャンルが空だった作品に、ジャンルを補いました: {len(filled_genres)}件")
    if filled_cast:
        print(f"👤 出演者が空だった作品に、出演者を補いました: {len(filled_cast)}件")
    if filled_movie:
        print(f"🎬 サンプル動画が無かった作品に、動画を補いました: {len(filled_movie)}件")
    if refetched:
        print(f"🔁 品番で取り直した作品: {refetched[1]}件")

    newcomers = []
    maker = None
    if not refresh_only:
        newcomers = [p for p in released if p["cid"] not in archive][:NEW_ITEMS_PER_RUN]
        newcomers += [p for p in upcoming if p["cid"] not in archive and p["cid"] not in {n["cid"] for n in newcomers}]
        print(f"🆕 新しく追加: {len(newcomers)}件")

        maker = CommentMaker()
        for i, item in enumerate(newcomers, 1):
            maker.apply(item)
            item["updated"] = today_str
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
                before_comment = item.get("comment")
                maker.apply(item)
                if item.get("comment") != before_comment:
                    item["updated"] = today_str  # コメントが変わったときだけ「更新日」を進める
                print(f"  {item['comment_kind']:8s} {item['comment'][:24]}")

    save_archive(archive)
    kinds = [it.get("comment_kind") for it in archive.values()]
    print(f"\n✨ 保存完了！ 合計{len(archive)}件（Claudeが仕上げ{kinds.count('claude')}件 / Geminiの下書き{kinds.count('ai')}件 / 代わりの文{kinds.count('template')}件）")
    if maker:
        print(f"   今回のAI成功 {maker.ai_ok}件 / ブロック {maker.blocked}件 / 採用せず {maker.rejected}件 / Geminiに頼んだ回数 {maker.calls}回")
        if maker.stop_reason:
            print(f"   ⏸ AIコメントを途中でお休みした理由: {maker.stop_reason}")
            print(f"::warning title=AIコメントを途中でお休みしました::{maker.stop_reason}")

    # ---- 出演者のプロフィール・売れ筋ランキング（作品の保存のあと。失敗しても、ほかの更新は止めない）----
    def profiles_stage():
        raw_all = released_raw + upcoming_raw + refetched_raw + (ranking_raw or [])
        added = upsert_actresses(actress_state, collect_actresses(raw_all), today_str)
        fetched_n, unmatched_n = update_profiles(actress_state, archive, today_str)
        save_actress_state(actress_state)
        return added, fetched_n, unmatched_n

    ranking_raw = []
    ranking = run_stage("売れ筋ランキングの取得", fetch_ranking_with_raw)
    if ranking:
        ranking_raw = ranking[1]
        run_stage("売れ筋ランキングの保存", lambda: save_ranking(ranking[0], today_str))
        print(f"🏆 売れ筋ランキング: {len(ranking[0])}本（1位 {ranking[0][0]['cid']}）")
    profile_result = run_stage("出演者プロフィールの取得", profiles_stage) if actress_state is not None else None
    if profile_result:
        print(f"👤 出演者プロフィール: 新しく見つけた {profile_result[0]}人 / 取得 {profile_result[1]}人 / 名前で見つからなかった {profile_result[2]}人（保存中 {len(actress_state['actresses'])}人）")

    summary = [
        "### ✅ FANZAデータの取り直しの結果" if refresh_only else "### ✅ FANZA更新の結果",
        "",
        f"- 取得: 発売済み {len(released)}件 / 予約 {len(upcoming)}件",
    ]
    if not refresh_only:
        summary.append(f"- 新しく追加: {len(newcomers)}件")
    summary += [
        f"- 出演者が空だった作品に補った: {len(filled_cast)}件",
        f"- サンプル動画を補った: {len(filled_movie)}件" + (f"（品番で取り直した作品 {refetched[1]}件）" if refetched else ""),
        f"- ジャンルを補った: {len(filled_genres)}件",
        "- 合計: {}件（Claudeが仕上げ {}件 / Geminiの下書き {}件 / 代わりの文 {}件。下書きと代わりの文は、0:20 に Claude が仕上げます）".format(
            len(archive), *(sum(1 for it in archive.values() if it.get("comment_kind") == k) for k in ("claude", "ai", "template"))),
    ]
    if maker:
        summary.append(f"- 今回のAIコメント: 成功 {maker.ai_ok}件 / ブロック {maker.blocked}件 / 採用せず（確かめられない言い回しが入っていた）{maker.rejected}件 / Geminiに頼んだ回数 {maker.calls}回")
        if maker.stop_reason:
            summary.append(f"- ⏸ AIコメントを途中でお休み: {maker.stop_reason}（代わりの文の作品は、次回以降に自動で再挑戦します）")
    summary.append(f"- 売れ筋ランキング: {str(len(ranking[0])) + '本' if ranking else '取得できず（前回のまま）'}")
    if profile_result:
        summary.append(f"- 出演者プロフィール: 取得 {profile_result[1]}人 / 名前で見つからなかった {profile_result[2]}人（保存中 {len(actress_state['actresses'])}人）")
    elif actress_state is None:
        summary.append("- 出演者プロフィール: 保存データ（actresses.json）が壊れているため、更新をスキップ（ファイルは変更していません）")
    else:
        summary.append("- 出演者プロフィール: 取得できず（前回のまま）")
    write_step_summary(summary)


if __name__ == "__main__":
    main()
