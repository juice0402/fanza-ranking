#!/usr/bin/env python3
"""Claude がコメントを書く・仕上げるための道具（Python標準ライブラリだけ）

毎日の更新（get_new_releases.py）では、Gemini がコメントの「下書き」（comment_kind: ai）を書きます。
Gemini が書けなかった作品は、定型文（comment_kind: template）のまま保存されます。
そのどちらも、Claude が読み直して書き上げた文章（comment_kind: claude）に置き換えるときに使います。
手順は docs/claude-comments.md を見てください。

  python3 scripts/claude_comments.py list [--limit 30]
      書く対象の作品を、コメント作りに必要な情報だけで表示する（作品タイトルは出さない）。対象は次の3つ
        ・定型文のままの作品（reason: 定型文）
        ・Gemini の下書きのままの作品（reason: 下書きを仕上げる。draft に下書きが入る）
        ・発売日をすぎたのに、コメントに「予約」「発売予定」「発売前」などの言い方が残っている作品（reason: 予約の言い方が残っている）
  python3 scripts/claude_comments.py apply コメント.json [--dry-run]
      {"cid": "コメント", ...} を点検して、問題が無ければ new_releases.json に書き込む
      （1件でも問題があれば何も書き込まない）

書き込んだコメントは comment_kind を "claude" にし、その作品の updated（更新日）を今日（日本時間）にします
（サイトのフッターの「ひとことコメントは…自動で作成」の注記の対象。sitemap の lastmod にも使われます）。
Claude が仕上げたコメント（"claude"）は上書きしません（発売日をすぎて、予約の言い方が残っているものだけは書き直します）。
直す必要が見つかったときだけ、apply --rewrite で書き直せます（毎日の予約タスクでは使わない）。
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.environ.get("DATA_PATH", os.path.join(ROOT, "site", "src", "data", "new_releases.json"))
JST = timezone(timedelta(hours=9))

MIN_LEN = 100           # コメントの文字数の下限（目安は100〜160文字。2〜3文。運営者の希望で、2026-10-04 に長くした。試運転で90字前後が多かったので、下限を100に）
MIN_LEN_SPARSE = 80     # 書ける事実が少ない作品（タイトルを見せない・収録時間もジャンルもまだ無い予約）の下限。100文字に届かせるための水増しをさせないため
MAX_LEN = 200           # 上限
DEFAULT_LIMIT = 30      # list で一度に出す件数
DAILY_LIMIT = 40        # 1日に仕上げる件数の上限（試運転で、1回の予約タスクが40件を2回続けて書いたため。--rewrite は数えない）

# コメントに書けない言葉: 行為・体の部位の言葉、性的暴行・連れ去り・拷問・人をモノ扱いする言葉。
# 痴漢・催眠・寝取り・セクハラ・拘束などは、フィクションの「設定」を伝える言葉として書いてよい（運営者の希望。2026-10-04）
EXPLICIT_WORDS = ["中出", "射精", "精液", "挿入", "フェラ", "レイプ", "強姦", "凌辱", "陵辱", "輪姦", "セックス", "SEX", "性交", "膣", "精子", "ザーメン", "絶頂",
                  "潮吹", "乳首", "巨根", "デカチン", "チンポ", "ちんぽ", "マンコ", "まんこ", "手コキ", "パイズリ", "クンニ", "アナル", "淫語", "淫乱", "ハメ", "オナニー",
                  "イラマ", "顔射", "ぶっかけ", "ごっくん", "放尿", "失禁", "犯さ", "犯す", "便器", "奴隷", "鬼畜", "エロ", "●", "拉致", "拷問"]
MINOR_WORDS = ["未成年", "少女", "ロリ", "児童", "幼", "女子高生", "女子校生", "女子中", "中学生", "高校生", "小学生",
               "JK", "JC", "JS", "制服", "校生", "学生", "生徒", "教え子", "園児", "子供", "子ども", "妹", "娘", "童顔", "貧乳",
               "つるぺた", "パイパン", "処女",
               # 学校・子どもの生活を連想させる場面の言葉（2026-10-04 の試運転で、「職業体験」「学園」「家庭教師」に触れたコメントがあったため）
               "学園", "職業体験", "家庭教師", "放課後", "部活", "修学旅行", "体操着", "ブルマ", "スク水", "ランドセル", "保健室", "通学", "登校", "下校", "塾", "女の子", "いじめっ子", "J系"]
FORBIDDEN_CHARS = "<>*#"
# コメントは保存したままずっと表示されるので、日がたつと古くなる言い方は使わない（日付で書く）
RELATIVE_TIME_WORDS = ["今日", "本日", "明日", "昨日", "今週", "来週", "先週", "今夜", "今朝", "今月", "来月"]

# 確かめられない評価（人気・期待度・評判）や大げさな言い方。get_new_releases.py の HYPE_WORDS と同じ一覧（tests/test_script.py が同じかを調べる）
HYPE_WORDS = ["待望", "話題", "熱い視線", "高い関心", "期待が高まる", "期待が膨らむ", "期待作", "期待の", "大人気", "人気の", "ファンの", "ファンから",
              "おなじみ", "必見", "間違いなし", "至高", "極上", "圧倒的", "注目の", "見逃せない", "目が離せない", "心を奪", "豪華な"]
# 使いすぎると、どのコメントも同じ結びになる言い回し（get_new_releases.py の AVOID_PHRASES と同じ一覧）。まとめて書くときに、多すぎたら知らせるだけ
AVOID_PHRASES = ["気になる方は", "チェック", "ぜひ", "いまのうちに", "お早めに", "お見逃しなく", "おすすめ"]
# まとめて書くときに、3本に1本より多く使うと断る言い回し（どのコメントも「サンプル動画と12枚の画像で雰囲気を確かめられます」で終わる、
# 型どおりの文章になってしまうため。2026-10-04 の試運転で、40本ほぼすべてがこの結びだった）。6本以上まとめて書くときだけ数える
REPEAT_LIMIT_PHRASES = ["サンプル", "雰囲気を確かめ", "雰囲気をつかめ", "雰囲気を見られ", "様子を確かめ", "様子を見られ", "公開されています", "用意されています",
                        # 2回目の試運転で、文字数を満たすための決まり文句になっていたもの（40本中14本が「名前から…探せます」）
                        "名前から", "向いています"]
SAME_SENTENCE_RUN = 10  # 1つのコメントの中で、2つの文がこの文字数以上つづけて同じなら、同じことの言い直し（水増し）として断る（「確かめられます。」のような短い語尾の一致は数えない）
# 発売日をすぎると古くなる言い方（予約中の作品に書いたコメントが、発売後も「予約受付中」のまま残らないように探す）
STALE_STATUS = re.compile(r"予約|発売予定|発売前|発売を前に|発売に向けて|発売日を待|発売まで|リリース前|リリースを前に|リリースへ向け|待ちきれ|まもなく|近日")

# 同意の無い場面・薬・嫌がらせなどの設定を表す言葉。タイトルにあっても見せる（フィクションの設定として、落ち着いた言葉で内容を書く。
# list で fiction_theme: true を付ける）。2026-10-04 夕方まではタイトルごと見せていなかったが、運営者の希望で内容を書くようにした
FICTION_THEME_WORDS = ["レイプ", "強姦", "凌辱", "陵辱", "輪姦", "痴漢", "盗撮", "催眠", "媚薬", "薬", "泥酔", "睡眠", "昏睡", "監禁",
                             "拘束", "調教", "奴隷", "鬼畜", "無理やり", "無理矢理", "強制", "脅", "犯", "洗脳", "便器", "姪",
                             # 全作品の点検（2026-10-04 夕方）で見つかった、同意の無い場面・嫌がらせ・制裁を表す言葉
                             "セクハラ", "制裁", "拉致", "連れ去", "連れ込", "騙", "嫌なのに", "復讐", "いいなり", "言いなり", "寝取",
                             "理解らせ", "わからせ", "夜這", "人質", "拷問", "朦朧", "酩酊"]
# タイトルを Claude に見せない作品（内容に触れない）は、未成年を連想させるものだけ。ただし、大人どうしの言葉の一部として
# よく使われるもの（幼なじみ・姉妹・母娘・男の娘・看板娘 など）は数えない。「女の子」「処女」も、タイトルでは大人の女性を指すので数えない
# （コメントには、どれも書かない。「女性」と書く）。筆おろし・いじめっ子は、未成年を連想させる場面として数える
MINOR_TITLE_OK = ["幼なじみ", "幼馴染", "姉妹", "母娘", "男の娘", "看板娘", "肛門娘", "女の子", "処女"]
MINOR_TITLE_WORDS = [w for w in MINOR_WORDS if w not in MINOR_TITLE_OK] + ["筆おろし"]
TITLE_BLOCK = MINOR_TITLE_WORDS + FICTION_THEME_WORDS  # ジャンルの手がかりから外す言葉（comment_genres）
# 伏せ字（中●し・チ○ポ・レ●プ など）。タイトルは見せる（コメントには伏せ字も行為の言葉も書けない）。
# 伏せた言葉が未成年（J● 女子○生 ●学生 など）のときは、タイトルごと見せない（MINOR_CENSORED）。同意の無い行為（レ●プ 痴● など）は fiction_theme。
# 「×」は「A×B」の区切りにも使うので、伏せ字としては「J×」のような危ない形のときだけ数える（2026-10-04 夕方まで、×・伏せ字があるだけで隠していた）
CENSOR_CHARS = "●○◯〇＊*×"
_C = "[●○◯〇＊*×]"
MINOR_CENSORED = re.compile(rf"[JＪjｊ]{_C}|女子{_C}{{1,2}}生|{_C}{{1,2}}[学校]生|[中小高]{_C}生|ロ{_C}")
RISKY_CENSORED = re.compile(rf"[JＪjｊ]{_C}|女子{_C}{{1,2}}生|{_C}{{1,2}}[学校]生|[中小高]{_C}生|ロ{_C}|レ{_C}|強{_C}|痴{_C}|輪{_C}|犯{_C}|"
                            rf"催{_C}|睡{_C}|盗{_C}|媚{_C}|拉{_C}|監{_C}|凌{_C}|陵{_C}|鬼{_C}|{_C}{{3,}}")
# コメントの手がかりに出すジャンル（決めた一覧だけ）: サイトの「ジャンルのページ」の一覧（config.js の TAG_PAGE_GENRES）と、ここに足した、
# 作品の舞台・関係・形式を表す、おだやかなもの。過激な行為・未成年を連想させるもの（学校・体操着・小柄など）・同意の無い行為・薬は入れない
COMMENT_EXTRA_GENRES = ["ドラマ", "企画", "ドキュメンタリー", "恋愛", "デート", "不倫", "未亡人", "看護婦・ナース", "職業色々", "部下・同僚",
                        "ビジネススーツ", "めがね", "お風呂", "温泉", "旅行", "エステ", "マッサージ・リフレ", "主観", "ナンパ", "レズビアン",
                        "ニューハーフ", "キス・接吻", "美脚", "長身", "スポーツ", "アイドル・芸能人", "キャバ嬢・風俗嬢", "メイド", "OL",
                        "VR専用", "ハイクオリティVR", "8KVR", "4K", "ハイビジョン", "独占配信", "単体作品", "4時間以上作品", "複数話"]
COPY_RUN = 10           # タイトルの文字を、これより長く続けて写したら断る（タイトルは手がかり。文章は自分の言葉で）

# コメントの種類（get_new_releases.py と同じ）: template＝定型文、ai＝Gemini の下書き、claude＝Claude が仕上げたもの
FINAL_KIND = "claude"
DRAFT_KIND = "ai"
CONFIG_JS = os.path.join(ROOT, "site", "src", "config.js")

# list に出す形式タグは、VR / 8K のような英数字だけのものに絞る。
# タグは作品タイトルの【…】から取っているため、日本語のタグには作品の内容を表す言葉が混ざることがある。
FORMAT_TAG = re.compile(r"^[0-9A-Za-z]{1,6}$")


def jst_today():
    return datetime.now(JST).strftime("%Y-%m-%d")


# 作品の形式を表すジャンル（場面・関係を表さないもの）。未成年を連想させるタイトルの作品では、これ以外のジャンルにも触れない
FORMAT_GENRES = ["VR専用", "ハイクオリティVR", "8KVR", "4K", "ハイビジョン", "独占配信", "単体作品", "4時間以上作品", "複数話", "ベスト・総集編"]


def title_block_reason(item):
    """タイトルの見方: "minor"（未成年を連想させる。タイトルを見せない）・"theme"（同意の無い場面などのフィクションの設定。見せる）・""（ふつう）。
    全角の英数字（ＪＫ など）も半角にそろえてから調べる"""
    title = str(item.get("title") or "").strip()
    norm = unicodedata.normalize("NFKC", title)
    low = norm.lower()
    for ok in MINOR_TITLE_OK:
        low = low.replace(ok.lower(), "\u0000")
    if any(w.lower() in low for w in MINOR_TITLE_WORDS) or MINOR_CENSORED.search(norm) or MINOR_CENSORED.search(title):
        return "minor"
    if any(w.lower() in low for w in FICTION_THEME_WORDS) or RISKY_CENSORED.search(norm) or RISKY_CENSORED.search(title):
        return "theme"
    return ""


def safe_title(item):
    """Claude に見せてよいタイトル（見せないときは ""）。未成年を連想させるタイトルだけ見せない"""
    title = str(item.get("title") or "").strip()
    return title if title and title_block_reason(item) != "minor" else ""


def genres_for_comment(item, allowed=None):
    """コメントに使ってよいジャンル。未成年を連想させるタイトルの作品は、形式のジャンル（FORMAT_GENRES）だけ"""
    genres = comment_genres(item, allowed)
    return [g for g in genres if g in FORMAT_GENRES] if title_block_reason(item) == "minor" else genres


def comment_genres(item, allowed=None):
    """コメントの手がかりに出すジャンル（決めた一覧にあるものだけ。並びはデータのまま）"""
    allowed = allowed if allowed is not None else set(safe_genres_from_config()) | set(COMMENT_EXTRA_GENRES)
    out = []
    for g in item.get("genres") or []:
        if isinstance(g, str) and g in allowed and g not in out and not any(w.lower() in g.lower() for w in EXPLICIT_WORDS + TITLE_BLOCK):
            out.append(g)
    return out


def copied_from_title(text, title, names=()):
    """コメントの中に、タイトルから COPY_RUN 文字以上そのまま写した所があれば、その文字（なければ ""）。出演者名・メーカー名は除いて調べる"""
    if not title:
        return ""
    for n in sorted((n for n in names if n), key=len, reverse=True):
        title = title.replace(n, "\u0000")
        text = text.replace(n, "\u0001")
    for i in range(0, max(0, len(text) - COPY_RUN + 1)):
        piece = text[i:i + COPY_RUN]
        if "\u0001" not in piece and piece in title:
            return piece
    return ""


def safe_genres_from_config(path=CONFIG_JS):
    """コメントに使ってよいジャンル。サイトの「ジャンルのページ」を作るジャンルの一覧（config.js の TAG_PAGE_GENRES）と同じ。
    過激な言葉・未成年を連想させる言葉は、その一覧に入れていない。読めなければ空（ジャンルを出さないだけ）"""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    m = re.search(r"TAG_PAGE_GENRES\s*=\s*\[(.*?)\]", text, re.S)
    if not m:
        return []
    names = re.findall(r"'([^']+)'|\"([^\"]+)\"", m.group(1))
    words = [a or b for a, b in names]
    return [w for w in words if not any(x.lower() in w.lower() for x in EXPLICIT_WORDS + MINOR_WORDS)]


# ------------------------------------------------------------------
# データの読み書き
# ------------------------------------------------------------------
def load_raw():
    """保存データを、そのままの並びで読む（書き戻すときに余計な差分が出ないように）"""
    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"❌ 保存データを読めませんでした（{e}）")
    if not isinstance(raw, list) or not all(isinstance(x, dict) and x.get("cid") for x in raw):
        sys.exit("❌ 保存データの形が違います（cid のある作品のリストではありません）")
    return raw


def save_raw(items):
    """get_new_releases.py の save_archive と同じ書き方（インデント1・日本語そのまま）"""
    tmp_path = DATA_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp_path, DATA_PATH)  # 書き込み途中で止まってもデータが壊れないように


# ------------------------------------------------------------------
# list: コメントを書く対象を出す
# ------------------------------------------------------------------
def stale_status_word(item, today):
    """発売日をすぎた作品のコメントに「予約」「発売予定」などが残っていれば、その言葉（なければ空）。予約中の作品・定型文は対象外"""
    if item.get("comment_kind") not in (DRAFT_KIND, FINAL_KIND):
        return ""
    day = str(item.get("date") or "")[:10]
    if not day or day > today:
        return ""
    m = STALE_STATUS.search(item.get("comment") or "")
    return m.group(0) if m else ""


def pending_items(items, today=None):
    """書く対象の作品: Claude がまだ仕上げていないもの（定型文・Gemini の下書き）と、
    発売日をすぎたのに予約の言い方が残っているもの"""
    today = today or jst_today()
    return [x for x in items if x.get("comment_kind") != FINAL_KIND or stale_status_word(x, today)]


def pending_reason(item, today):
    if stale_status_word(item, today):
        return "予約の言い方が残っている"
    if item.get("comment_kind") == DRAFT_KIND:
        return "下書きを仕上げる"
    return "定型文"


def cmd_list(args):
    items = load_raw()
    today = args.today or jst_today()
    todo = pending_items(items, today)
    # 先に、急ぐもの（予約の言い方が残っている・定型文）、そのあとに Gemini の下書き。
    # それぞれの中は、発売済みを新しい順に、そのあとに予約を発売日の近い順に
    def ordered(rows):
        released = sorted((x for x in rows if (x.get("date") or "")[:10] <= today),
                          key=lambda x: (x.get("date") or "", x["cid"]), reverse=True)
        upcoming = sorted((x for x in rows if (x.get("date") or "")[:10] > today),
                          key=lambda x: (x.get("date") or "", x["cid"]))
        return released + upcoming
    urgent = [x for x in todo if pending_reason(x, today) != "下書きを仕上げる"]
    drafts = [x for x in todo if pending_reason(x, today) == "下書きを仕上げる"]
    shown = (ordered(urgent) + ordered(drafts))[: max(args.limit, 0)]

    allowed = set(safe_genres_from_config()) | set(COMMENT_EXTRA_GENRES)
    rows = []
    for x in shown:
        maker = x.get("maker")
        minutes = x.get("duration_min")
        reason = pending_reason(x, today)
        row = {
            "cid": x["cid"],
            "reason": reason,
            "status": "発売済み" if (x.get("date") or "")[:10] <= today else "予約",
            "date": (x.get("date") or "")[:10],
            "actress": x.get("actress") or [],
            "maker": None if (not maker or maker == "不明") else maker,
            "tags": [t for t in (x.get("tags") or []) if isinstance(t, str) and FORMAT_TAG.match(t)],
            "duration_min": minutes if isinstance(minutes, int) and not isinstance(minutes, bool) and minutes > 0 else None,
            # ジャンルは、決めた一覧（ジャンルのページの一覧＋COMMENT_EXTRA_GENRES）にあるものだけ
            "genres": genres_for_comment(x, allowed),
            "sample_movie": bool(x.get("sample_movie")),
            "sample_images": len(x.get("sample_images") or []),
        }
        # タイトル: 内容にさらっと触れるための手がかり（安全チェックを通ったものだけ。通らなければ title_hidden: true で、内容には触れない）
        title = safe_title(x)
        row["min_len"] = min_length_for(x)  # この作品のコメントの文字数の下限（書ける事実が少ない作品は80）
        if title:
            row["title"] = title
            if title_block_reason(x) == "theme":
                row["fiction_theme"] = True  # 同意の無い場面などを含むフィクションの設定。設定として、落ち着いた言葉で内容を書く（行為・体の言葉・暴行の言葉は書かない）
        else:
            row["title_hidden"] = True
            if title_block_reason(x) == "minor":
                row["content_off"] = True  # 未成年を連想させるタイトル: 内容にも場面のジャンルにも触れず、出演者・メーカー・形式・日付・収録時間だけで書く
        if x.get("comment_kind") in (DRAFT_KIND, FINAL_KIND):
            row["draft"] = x.get("comment") or ""  # 仕上げる前の文（Gemini の下書きなど）。そのまま使わず、書き直す
        rows.append(row)
    print(json.dumps({"today": today, "total_pending": len(todo), "shown": len(rows), "items": rows},
                     ensure_ascii=False, indent=1))


# ------------------------------------------------------------------
# apply: コメントを点検して書き込む
# ------------------------------------------------------------------
def text_problems(text, min_len, max_len, allow_newlines=False):
    """文章の共通の点検（文字数・URL・記号・絵文字・古くなる言い方・使えない言葉）。問題点のリスト（なければ空）。
    週のまとめ記事の道具（claude_roundups.py）でも同じ点検を使う"""
    problems = []
    if not allow_newlines and ("\n" in text or "\r" in text):
        problems.append("改行が入っています")
    if not (min_len <= len(text) <= max_len):
        problems.append(f"文字数が {len(text)} 文字です（{min_len}〜{max_len}文字にしてください）")
    if "http" in text.lower():
        problems.append("URLが入っています")
    bad_chars = sorted({c for c in text if c in FORBIDDEN_CHARS})
    if bad_chars:
        problems.append("使えない記号があります: " + " ".join(bad_chars))
    if any(unicodedata.category(c) in ("So", "Cc", "Cf", "Cs", "Co") for c in text):
        problems.append("絵文字や飾りの記号が入っています")
    stale = [w for w in RELATIVE_TIME_WORDS if w in text]
    if stale:
        problems.append("日がたつと古くなる言い方があります（日付で書いてください）: " + "、".join(stale))
    low = unicodedata.normalize("NFKC", text).lower()  # 全角の英数字（ＪＫ など）も半角にそろえて調べる
    hit = [w for w in EXPLICIT_WORDS + MINOR_WORDS if w.lower() in low]
    if hit:
        problems.append("使えない言葉があります: " + "、".join(hit))
    return problems


def is_sparse(item):
    """書ける事実が少ない作品か: 収録時間もジャンルもまだ無い（予約）、または、タイトルを見せないうえに収録時間かジャンルが無い"""
    has_minutes, has_genres = bool(item.get("duration_min")), bool(comment_genres(item))
    if safe_title(item):
        return not (has_minutes or has_genres)
    return not (has_minutes and has_genres)


def min_length_for(item):
    """その作品のコメントの文字数の下限（未成年を連想させるタイトルの作品は、書ける事実が少ないので80）"""
    return MIN_LEN_SPARSE if is_sparse(item) or title_block_reason(item) == "minor" else MIN_LEN


def comment_problems(comment, item):
    """コメント1件の問題点（なければ空のリスト）"""
    if not isinstance(comment, str):
        return ["文字列ではありません"]
    text = comment.strip()
    problems = text_problems(text, min_length_for(item), MAX_LEN)
    hype = [w for w in HYPE_WORDS if w in text]
    if hype:
        problems.append("確かめられない評価・大げさな言い方があります（事実だけで書いてください）: " + "、".join(hype))
    stale = [w for w in sorted(set(STALE_STATUS.findall(text)))]
    if stale:
        problems.append("発売日をすぎると古くなる言い方があります（日付で書いてください。例: 「11月1日発売」）: " + "、".join(stale))
    for name in item.get("actress") or []:
        if name and text.count(name) > 1:
            problems.append(f"出演者名「{name}」が2回以上入っています（1回まで）")
    copied = copied_from_title(text, str(item.get("title") or ""), [*(item.get("actress") or []), item.get("maker") or ""])
    if copied:
        problems.append(f"タイトルの言葉をそのまま写しています（「{copied}」。内容は、自分の言葉で、やわらかく言いかえてください）")
    if text == (item.get("comment") or "").strip():
        problems.append("いまのコメントと同じです")
    if title_block_reason(item) == "minor":
        scenes = [g for g in comment_genres(item) if g not in FORMAT_GENRES and g in text]
        if scenes:
            problems.append("未成年を連想させるタイトルの作品なので、場面・関係のジャンルにも触れないでください（出演者・メーカー・形式・日付・収録時間だけで書く）: " + "、".join(scenes))
    repeated = repeated_sentence(text)
    if repeated:
        problems.append(f"同じ内容の文が2回入っています（「{repeated}」）。言い直して文字数を増やさず、事実（ジャンル・形式・発売日・収録時間など）を1つ足してください")
    return problems


def repeated_sentence(text, run=SAME_SENTENCE_RUN):
    """1つのコメントの中で、2つの文に run 文字以上つづけて同じところがあれば、その部分を返す（なければ ""）。
    2回目の試運転で「長めの作品を探す方に向いています。長めの作品を探す方にも向いています。」のような水増しがあったため"""
    sentences = [x for x in re.split(r"(?<=[。！？])", text) if x.strip()]
    for a in range(len(sentences)):
        for b in range(a + 1, len(sentences)):
            x, y = sentences[a], sentences[b]
            for i in range(len(x) - run + 1):
                if x[i:i + run] in y:
                    j = i + run
                    while j < len(x) and x[i:j + 1] in y:
                        j += 1
                    return x[i:j]
    return ""


def read_comments_file(path):
    """{"cid": "コメント"} または [{"cid":..., "comment":...}] を {cid: コメント} にする"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"❌ コメントのファイルを読めませんでした（{e}）")
    if isinstance(data, list):
        mapping = {}
        for row in data:
            if not isinstance(row, dict) or "cid" not in row or "comment" not in row:
                sys.exit('❌ リストの各項目は {"cid": ..., "comment": ...} の形にしてください')
            if row["cid"] in mapping:
                sys.exit(f"❌ cid が重複しています: {row['cid']}")
            mapping[row["cid"]] = row["comment"]
        return mapping
    if isinstance(data, dict):
        return data
    sys.exit('❌ コメントのファイルは {"cid": "コメント"} の形にしてください')


def cmd_apply(args):
    stamp = args.today or jst_today()  # 更新日に入れる日付
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", stamp):
        sys.exit("❌ --today は YYYY-MM-DD の形で指定してください")
    mapping = read_comments_file(args.file)
    if not mapping:
        print("書き換えるコメントがありません。何も変更しませんでした")
        return

    items = load_raw()
    by_cid = {x["cid"]: x for x in items}
    errors = []
    texts = {}
    for cid, comment in mapping.items():
        item = by_cid.get(cid)
        if item is None:
            errors.append((cid, ["保存データにない cid です"]))
            continue
        if item.get("comment_kind") == FINAL_KIND and not stale_status_word(item, stamp) and not args.rewrite:
            errors.append((cid, ["Claude が仕上げたコメントが、すでに付いています（上書きしません。書き直せるのは、定型文・Gemini の下書き・発売日をすぎて予約の言い方が残っているものだけ）"]))
            continue
        problems = comment_problems(comment, item)
        if problems:
            errors.append((cid, problems))
        else:
            texts[cid] = comment.strip()

    # 同じ文章を複数の作品に使い回していないか
    seen = {}
    for cid, text in texts.items():
        seen.setdefault(text, []).append(cid)
    for text, cids in seen.items():
        if len(cids) > 1:
            for cid in cids:
                errors.append((cid, ["同じ文章が他の作品にも使われています: " + "、".join(c for c in cids if c != cid)]))

    # 1日に仕上げるのは DAILY_LIMIT 件まで（急いで大量に書くと、型どおりの文になりやすい。残りは次の日に回す）
    if not args.rewrite and not args.no_daily_limit:
        done_today = sum(1 for x in items if x.get("comment_kind") == FINAL_KIND and x.get("updated") == stamp and x["cid"] not in texts)
        if done_today + len(texts) > DAILY_LIMIT:
            errors.append(("(まとめて)", [f"今日（{stamp}）はもう {done_today} 件を仕上げています。1日に仕上げるのは {DAILY_LIMIT} 件までです"
                                          f"（今回は {max(0, DAILY_LIMIT - done_today)} 件まで。残りは次の日に回してください）"]))

    # 同じ型の結びが多すぎるときは断る（どれが多いかを出して、書き分けてもらう）
    if len(texts) >= 6:
        for phrase in REPEAT_LIMIT_PHRASES:
            used = [cid for cid, t in texts.items() if phrase in t]
            if len(used) * 3 > len(texts):
                errors.append(("(まとめて)", [f"「{phrase}」を使ったコメントが {len(used)}/{len(texts)} 件あります。3本に1本までにして、"
                                              "結びを書き分けてください（言い切る・発売日を添える・出演者やメーカーの別の作品にふれる など）: " + "、".join(used[:12])]))

    if errors:
        print(f"❌ 問題のあるコメントが {len(errors)} 件あります。何も書き込んでいません。直してもう一度実行してください")
        for cid, problems in errors:
            print(f"  - {cid}: " + " / ".join(problems))
        sys.exit(1)

    # 書き出しがそろいすぎると単調なので、気づけるように警告だけ出す
    if len(texts) >= 8:
        openings = {}
        for text in texts.values():
            openings[text[:6]] = openings.get(text[:6], 0) + 1
        top, count = max(openings.items(), key=lambda kv: kv[1])
        if count * 4 > len(texts):
            print(f"⚠️ 書き出しが「{top}」の コメントが {count}/{len(texts)} 件あります。変化をつけると読みやすくなります")

    # 同じ結びの言い回しが多すぎると、どのコメントも同じ型に見えるので、気づけるように警告だけ出す
    if len(texts) >= 6:
        for phrase in AVOID_PHRASES:
            count = sum(1 for t in texts.values() if phrase in t)
            if count * 3 > len(texts):
                print(f"⚠️ 「{phrase}」を使ったコメントが {count}/{len(texts)} 件あります。言い回しを変えると、読みやすくなります")

    if args.dry_run:
        print(f"✅ {len(texts)}件、問題ありません（--dry-run のため書き込んでいません）")
        return

    for cid, text in texts.items():
        by_cid[cid]["comment"] = text
        by_cid[cid]["comment_kind"] = FINAL_KIND
        by_cid[cid]["updated"] = stamp  # コメントを変えた日（sitemap の lastmod に使う）
    save_raw(items)
    # 書いたものを読み直して確かめる
    check = load_raw()
    ok = len(check) == len(items) and all(x["cid"] == y["cid"] for x, y in zip(check, items))
    if not ok:
        sys.exit("❌ 書き込み後の確認に失敗しました。git で変更を取り消してください")
    left = len(pending_items(check, stamp))
    kinds = [x.get("comment_kind") for x in pending_items(check, stamp)]
    print(f"✅ {len(texts)}件のコメントを書き込みました（まだ仕上げていない作品: 残り{left}件。"
          f"うち定型文 {kinds.count('template')}件・Gemini の下書き {kinds.count(DRAFT_KIND)}件）")


def main():
    parser = argparse.ArgumentParser(description="Claude がコメントを書く・仕上げるための道具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="まだ仕上げていない作品（定型文・Gemini の下書き）を出す")
    p_list.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"出す件数（既定 {DEFAULT_LIMIT}）")
    p_list.add_argument("--today", help="今日の日付 YYYY-MM-DD（テスト用。省略すると日本時間の今日）")
    p_list.set_defaults(func=cmd_list)

    p_apply = sub.add_parser("apply", help="コメントを点検して書き込む")
    p_apply.add_argument("file", help='{"cid": "コメント"} の形のJSONファイル')
    p_apply.add_argument("--dry-run", action="store_true", help="点検だけして書き込まない")
    p_apply.add_argument("--no-daily-limit", action="store_true",
                         help="1日の上限（DAILY_LIMIT）を数えない（運営者に頼まれて、会話の中で1本ずつ書くときだけ。毎日の予約タスクでは使わない）")
    p_apply.add_argument("--rewrite", action="store_true",
                         help="Claude が仕上げたコメントも書き直す（運営者に頼まれたときや、見直しで問題が見つかった文を直すときだけ。毎日の予約タスクでは使わない）")
    p_apply.add_argument("--today", help="更新日に入れる日付 YYYY-MM-DD（テスト用。省略すると日本時間の今日）")
    p_apply.set_defaults(func=cmd_apply)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
