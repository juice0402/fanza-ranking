#!/usr/bin/env python3
"""Claude が「読み物」（/yomimono/）の記事を書くための道具（Python標準ライブラリだけ）

読み物は、ジャンル・テーマごとの、ブログのような記事です（導入文・見出しのある節・最初に見る5本）。
本数・年ごとの本数・メーカー・評価などの数字は、この道具がサイトの全作品から数えます。
Claude は数字を「話を支える材料」として使い、文章を書きます。手順と書き方は docs/claude-yomimono.md を見てください。

  python3 scripts/claude_yomimono.py themes [--today YYYY-MM-DD]
      （別名 candidates）書き直す記事（確かめた日 checked から90日をすぎたもの）と、まだ書いていないテーマの候補を出す
  python3 scripts/claude_yomimono.py list --slug ai-remaster [--today YYYY-MM-DD]
  python3 scripts/claude_yomimono.py list --slug jukujo --genres 熟女 [--keywords 語,語]
      テーマの数字（facts）と、選べる作品（candidates。作品タイトルは出さない）を出す
  python3 scripts/claude_yomimono.py apply 記事.json [--dry-run] [--today YYYY-MM-DD]
      {"<slug>": {title, description, lead, sections, picks_h?, picks, theme?}} を点検して、
      問題が無ければ site/src/data/yomimono.json に書き込む（1件でも問題があれば何も書き込まない）

テーマ: {"genres": [...], "keywords": [...]}。作品のジャンルにテーマのジャンルが1つでもあるか、
作品の題にキーワードが1つでも入っていれば、そのテーマの作品（サイトの lib/yomimono.js も同じ決まり）。
外す作品: 未成年を連想させる題（claude_comments.py の title_block_reason が "minor"）と、
site/src/lib/yomimono-exclude.json の title_words のどれかが題に入っている作品。数（facts）には入れてよいが、
選べる作品（candidates）と最初に見る5本（picks）には入れない。

保存先: site/src/data/yomimono.json（環境変数 YOMIMONO_PATH で変えられる。作品データは DATA_PATH・CATALOG_DIR、
人気の順位は POPULARITY_PATH・CATALOG_RANK_PATH、レビューは REVIEWS_PATH、セールは SALE_PATH、外す言葉は YOMIMONO_EXCLUDE_PATH）
"""
import argparse
import json
import math
import os
import re
import statistics
import sys
import unicodedata
from collections import Counter
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claude_comments as cc  # noqa: E402  禁止語・未成年を連想させる題の見方・文章の共通の点検
import claude_roundups as cr  # noqa: E402  作品データ（毎日の更新＋過去作品）の読み込み・確かめられない評価の言葉

ROOT = cr.ROOT
DATA_DIR = os.path.dirname(cr.DATA_PATH)
YOMIMONO_PATH = os.environ.get("YOMIMONO_PATH", os.path.join(ROOT, "site", "src", "data", "yomimono.json"))
EXCLUDE_PATH = os.environ.get("YOMIMONO_EXCLUDE_PATH", os.path.join(ROOT, "site", "src", "lib", "yomimono-exclude.json"))
REVIEWS_PATH = os.environ.get("REVIEWS_PATH", os.path.join(DATA_DIR, "reviews.json"))
SALE_PATH = os.environ.get("SALE_PATH", os.path.join(DATA_DIR, "sale.json"))

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DAY_TIME = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_MAX = 40

# はじめの4本のテーマ（yomimono.json にまだ無いときに使う）
BUILTIN_THEMES = {
    "hard": {"genres": ["淫乱・ハード系"], "keywords": []},
    "gensaku": {"genres": ["原作コラボ"], "keywords": ["実写"]},
    "ai-remaster": {"genres": [], "keywords": ["AIリマスター"]},
    "vr": {"genres": ["VR専用"], "keywords": []},
}

PICKS = 5                    # 最初に見る作品の数（ちょうど5本）
CANDIDATES_MAX = 30          # list に出す、選べる作品の数
CANDIDATES_PER_MAKER = 3     # 同じメーカーは3本まで（選ぶ作品がかたよらないように）
MONTHS = 12                  # 月ごとの本数を出す月の数（今日の月まで）
TOP_MAKERS = 5
TOP_ACTRESSES = 5            # 2本以上に出た人だけ
TOP_GENRES = 8               # いっしょに付いているジャンル
LONG_MIN = 240               # 「4時間以上」の分
BEST_GENRES = ("ベスト・総集編", "女優ベスト・総集編")  # 総集編のジャンルは2つある（両方を数える）
CLASSIC_GENRES = ("クラシック", "復刻")
REVIEW_PRIOR = 10            # 並べるときに平均にならす件数（lib/reviews.js の REVIEW_PRIOR と同じ）
REVIEW_MIN_SCORE = 5         # 評価を並べ順に使うレビューの件数
UNKNOWN_RANK = 50000         # 順位の「まだ分からない」（lib/popularity.js と同じ）
REWRITE_DAYS = 90            # 確かめた日（checked）からこの日数をすぎた記事は書き直す
THEME_MIN_WORKS = 100        # 新しいテーマの候補にする、作品の数
THEME_MIN_PICKABLE = 20      # 新しいテーマの候補にする、選べる作品の数
THEMES_SHOWN = 12
THEME_OVERLAP = 0.8          # すでにあるテーマの作品と、この割合以上が重なるジャンルは、新しいテーマの候補にしない（8KVR と VR など）

TITLE_MIN, TITLE_MAX = 8, 40
DESC_MIN, DESC_MAX = 80, 120
HEAD_MIN, HEAD_MAX = 2, 30
PARA_MIN, PARA_MAX = 30, 600
BODY_MIN, BODY_MAX = 2000, 3000   # 導入文と節の本文の合計（改行は数えない）
SECTIONS_MIN, SECTIONS_MAX = 4, 6
PARAS_MAX = 3                # 1つの節の段落の数（1〜3）
WHY_MIN, WHY_MAX = 40, 80
NUMBERS_PER_PARA = 3         # 1段落の数字（日付と「1」は数えない）。数字のレポートにしないため
DEFAULT_PICKS_H = "最初に見るならこの5本"

# いっしょに付いているジャンル・新しいテーマの候補から外す、作品の中身を表さないジャンル
META_GENRES = ["ハイビジョン", "単体作品", "独占配信", "4K", "セット商品", "デジモ", "妄想族", "その他フェチ", "ギリモザ"]
# テーマにしない言葉（未成年を連想させる言葉 MINOR_WORDS と、外す題の言葉 title_words に足すもの）:
# 学校・子どもを思わせる服や体つき、同意の無い場面・嫌がらせ・薬を思わせるジャンル
THEME_NG_EXTRA = ["セーラー服", "スクール水着", "小柄", "ミニ系", "童貞", "教師", "辱め", "ドラッグ", "イタズラ", "近親相姦", "寝取",
                  "母", "緊縛", "縛り", "SM", "M女", "羞恥", "セクハラ", "無理"]
# list に出す・新しいテーマの候補にするジャンル（決めた一覧だけ）: コメントの手がかりのジャンル（サイトのジャンルのページ＋舞台・関係・形式の
# おだやかなもの）に、読み物で使う作品の成り立ちのジャンルを足したもの。行為そのもの・未成年を連想させる・同意の無い場面のジャンルは入れない
YOMI_GENRES = list(dict.fromkeys(cc.safe_genres_from_config() + cc.COMMENT_EXTRA_GENRES + cc.FLOOR_COMMENT_GENRES + [
    "原作コラボ", "クラシック", "復刻", "ベスト・総集編", "女優ベスト・総集編", "16時間以上作品", "イメージビデオ", "特撮", "カップル",
    "和服・浴衣", "女上司", "女戦士", "セクシー"]))

# 記事に使わない言い方（コメント・まとめ記事の点検に足すもの）
FIRST_PERSON_WORDS = ["私", "僕", "ぼく", "わたし", "俺", "筆者", "編集部", "管理人", "当ブログ", "見てみた", "見てみま", "観てみ",
                      "使ってみ", "試してみ", "実際に見", "個人的", "感じました", "思いました", "思います", "ありませんか"]
# 画面に出さない「AI」の言い回し（tests/verify_dist.py の AI_PHRASES と同じ。AIリマスターのような作品の言葉はよい）
AI_SCREEN_PHRASES = ["AIのひとこと", "AIがひとこと", "AIが出演者", "AIが作品情報", "AIが自動", "AIが書", "AIによる"]
ARROW_CHARS = "→›»"
SUIT_RE = re.compile(r"向いて|向き|人に|方に|人へ|方へ|人なら|方なら")
# 確かめられない評価・大げさな言い方（週のまとめの傾向と同じ。「原作のファンの人に」のように書けるよう「ファンの」だけはよい）
HYPE_WORDS = [w for w in cr.TREND_HYPE_WORDS if w != "ファンの"]


# ------------------------------------------------------------------
# 日付
# ------------------------------------------------------------------
def to_date(day):
    return date(int(day[:4]), int(day[5:7]), int(day[8:10]))


def day_of(item):
    return str(item.get("date") or "")[:10]


def month_list(today, n=MONTHS):
    """今日の月までの n か月の "YYYY-MM"（古い順）"""
    y, m = int(today[:4]), int(today[5:7])
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def half_up(x):
    """四捨五入（JS の Math.round と同じ。Python の round は偶数への丸め）"""
    return int(math.floor(x + 0.5))


# ------------------------------------------------------------------
# データの読み込み（書くのは yomimono.json だけ）
# ------------------------------------------------------------------
def load_works():
    """サイトの全作品（毎日の更新の作品＋過去作品。同じ作品は毎日の更新のほう。FANZAのURLが無い過去作品は入れない＝lib/data.js の all と同じ）"""
    out, seen = [], set()
    for x in cr.load_items():
        if x["cid"] not in seen:
            seen.add(x["cid"])
            out.append(x)
    for x in cr.load_catalog_items():
        if x["cid"] not in seen and x.get("url"):
            seen.add(x["cid"])
            out.append(x)
    return out


def valid_rank(v):
    return isinstance(v, int) and not isinstance(v, bool) and 1 <= v < UNKNOWN_RANK


def load_ranks():
    """人気の順位 {cid: 順位}: 全体の人気順（popularity.json の all・catalog_rank.json）と新着の人気順の、上のほう"""
    ranks = cc.load_catalog_ranks()
    allr = cc._read_dict(cc.POPULARITY_PATH).get("all")
    for c, v in (allr.items() if isinstance(allr, dict) else []):
        if valid_rank(v):
            ranks[c] = min(v, ranks.get(c, v))
    return ranks


def load_reviews():
    """FANZAのレビュー {cid: (平均, 件数)}（lib/reviews.js の reviewOf と同じ読み方）"""
    items = cc._read_dict(REVIEWS_PATH).get("items")
    out = {}
    for c, v in (items.items() if isinstance(items, dict) else []):
        if (isinstance(v, list) and len(v) == 2 and all(isinstance(n, int) and not isinstance(n, bool) for n in v)
                and 100 <= v[0] <= 500 and v[1] >= 1):
            out[c] = (v[0] / 100, v[1])
    return out


def load_sale(today):
    """いまセール中の作品 {cid: {"off": 割引の%（分からなければ None）, "end": 終わる日時}}（今日が期間に入っているキャンペーンだけ。lib/sale.js と同じ）"""
    raw = cc._read_dict(SALE_PATH)
    camps = raw.get("campaigns") if isinstance(raw.get("campaigns"), list) else []
    out = {}
    for r in raw.get("items") if isinstance(raw.get("items"), list) else []:
        if not isinstance(r, dict) or not isinstance(r.get("c"), str) or not isinstance(r.get("k"), int) or not (0 <= r["k"] < len(camps)):
            continue
        camp = camps[r["k"]] if isinstance(camps[r["k"]], dict) else {}
        end = str(camp.get("end") or "")
        if not str(camp.get("title") or "").strip() or not DAY_TIME.match(end) or end[:10] < today:
            continue
        p, lp = r.get("p"), r.get("l")
        priced = isinstance(p, int) and isinstance(lp, int) and 0 < p < lp
        out[r["c"]] = {"off": min(99, half_up((1 - p / lp) * 100)) if priced else None, "end": end[:16]}
    return out


def load_exclude_words():
    """外す題の言葉（site/src/lib/yomimono-exclude.json の title_words。一覧はそのファイルだけに置く）。読めなければ止める"""
    try:
        with open(EXCLUDE_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"❌ 外す題の言葉のファイルを読めませんでした（{e}）")
    words = raw.get("title_words") if isinstance(raw, dict) else None
    if not isinstance(words, list) or not words or not all(isinstance(w, str) and w for w in words):
        sys.exit("❌ 外す題の言葉のファイルの形が違います（title_words が文字列のリストではありません）")
    return words


def load_yomimono():
    if not os.path.exists(YOMIMONO_PATH):
        return {"updated": None, "articles": {}}
    try:
        with open(YOMIMONO_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"❌ 読み物のデータを読めませんでした（{e}）")
    if not isinstance(raw, dict) or not isinstance(raw.get("articles"), dict) or not all(isinstance(a, dict) for a in raw["articles"].values()):
        sys.exit("❌ 読み物のデータの形が違います（{updated, articles: {slug: 記事}} ではありません）")
    return raw


def save_yomimono(data):
    """インデント1・日本語そのまま・末尾に改行（ほかの記事のデータと同じ書き方）。記事は slug の順"""
    out = {"updated": data.get("updated"), "articles": {k: data["articles"][k] for k in sorted(data["articles"])}}
    tmp_path = YOMIMONO_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp_path, YOMIMONO_PATH)  # 書き込み途中で止まってもデータが壊れないように
    return out


# ------------------------------------------------------------------
# テーマと、外す作品
# ------------------------------------------------------------------
def is_excluded(item, words):
    """読み物の候補から外す作品か（未成年を連想させる題・外す題の言葉が入った題）"""
    title = str(item.get("title") or "")
    return cc.title_block_reason(item) == "minor" or any(w in title for w in words)


def normalize_theme(raw):
    """{"genres": [...], "keywords": [...]} にそろえる（形が違えば None）"""
    if not isinstance(raw, dict):
        return None
    out = {}
    for key in ("genres", "keywords"):
        vals = raw.get(key) or []
        if not isinstance(vals, list) or not all(isinstance(v, str) for v in vals):
            return None
        out[key] = list(dict.fromkeys(v.strip() for v in vals if v.strip()))
    return out if (out["genres"] or out["keywords"]) else None


def theme_problems(theme, words):
    """テーマにしてはいけない言葉（未成年を連想させる・無理やりや犯罪を思わせる）が入っていれば、その言葉"""
    ng = cc.MINOR_WORDS + words + THEME_NG_EXTRA
    return sorted({w for v in theme["genres"] + theme["keywords"] for w in ng if w.lower() in unicodedata.normalize("NFKC", v).lower()})


def matches(item, theme):
    """テーマの作品か: テーマのジャンルが1つでも付いているか、題にキーワードが1つでも入っている（lib/yomimono.js と同じ決まり）"""
    genres = item.get("genres") or []
    title = str(item.get("title") or "")
    return any(g in genres for g in theme["genres"]) or any(k in title for k in theme["keywords"])


def safe_name(name, words):
    """list に出してよい名前（シリーズ・レーベル・ジャンル）か。直接的な言葉・未成年を連想させる言葉・外す題の言葉が入っていない"""
    low = unicodedata.normalize("NFKC", str(name or "")).lower()
    return bool(low) and not any(w.lower() in low for w in cc.EXPLICIT_WORDS + cc.MINOR_WORDS + cc.FICTION_THEME_WORDS + words)


def shown_genre(g, words):
    """list に出してよいジャンルか（決めた一覧 YOMI_GENRES にあり、中身を表さないジャンルではなく、使えない言葉が入っていない）"""
    return g in YOMI_GENRES and g not in META_GENRES and safe_name(g, words)


# ------------------------------------------------------------------
# 数字（facts）と、選べる作品（candidates）
# ------------------------------------------------------------------
def build_ctx(today):
    works = load_works()
    reviews = load_reviews()
    site_reviews = [reviews[x["cid"]][0] for x in works if x["cid"] in reviews]
    return {
        "today": today, "works": works, "words": load_exclude_words(), "ranks": load_ranks(), "reviews": reviews,
        "sale": load_sale(today), "site_avg": round(statistics.mean(site_reviews), 2) if site_reviews else None,
        "site_total": len(works), "month_all": Counter(day_of(x)[:7] for x in works),
    }


def top_named(values, words, n=1):
    """いちばん多い名前（list に出してよいものだけ）{"name", "n"}"""
    c = Counter(v for v in values if v and safe_name(v, words))
    rows = sorted(c.items(), key=lambda p: (-p[1], p[0]))[:n]
    return [{"name": k, "n": v} for k, v in rows]


def minutes_of(x):
    d = x.get("duration_min")
    return d if isinstance(d, int) and not isinstance(d, bool) and d > 0 else None


def theme_facts(ctx, theme):
    """テーマの数字（作品タイトルは入れない）"""
    today, words, ranks, reviews, sale = ctx["today"], ctx["words"], ctx["ranks"], ctx["reviews"], ctx["sale"]
    rows = [x for x in ctx["works"] if matches(x, theme)]
    released = [x for x in rows if day_of(x) <= today]
    total = len(rows)

    # 年ごと・月ごとの本数は、予約（発売日が今日より後）も入れて数える（年ごとの本数の合計＝total）
    by_year = Counter(int(day_of(x)[:4]) for x in rows)
    years = [{"y": y, "n": by_year.get(y, 0)} for y in range(min(by_year), max(by_year) + 1)] if by_year else []
    by_month = Counter(day_of(x)[:7] for x in rows)
    months = []
    for m in month_list(today):
        n, all_n = by_month.get(m, 0), ctx["month_all"].get(m, 0)
        one_in = half_up(all_n / n) if n else None
        months.append({"m": m, "n": n, "all": all_n, "pct": round(n / all_n * 100, 1) if all_n else 0.0,
                       "one_in": one_in, "phrase": f"{one_in}本に1本" if one_in else None})
    share_in = half_up(ctx["site_total"] / total) if total else None
    share = {"pct": round(total / ctx["site_total"] * 100, 1) if ctx["site_total"] else 0.0, "one_in": share_in,
             "phrase": f"{share_in}本に1本" if share_in else None}

    maker_rows = {}
    for x in rows:
        mk = x.get("maker")
        if mk and mk != "不明":
            maker_rows.setdefault(mk, []).append(x)
    makers = []
    for mk, xs in sorted(maker_rows.items(), key=lambda p: (-len(p[1]), p[0]))[:TOP_MAKERS]:
        series = top_named((x.get("series") for x in xs), words)
        label = top_named((x.get("label") for x in xs), words)
        makers.append({"name": mk, "n": len(xs), "months": len({day_of(x)[:7] for x in xs}),
                       "series": series[0] if series else None, "label": label[0] if label else None})
    act = Counter(a for x in rows for a in dict.fromkeys(x.get("actress") or []) if a)
    actresses = [{"name": a, "n": n} for a, n in sorted(act.items(), key=lambda p: (-p[1], p[0])) if n >= 2][:TOP_ACTRESSES]

    durs = [minutes_of(x) for x in rows if minutes_of(x)]
    has_best = lambda x: any(g in (x.get("genres") or []) for g in BEST_GENRES)  # noqa: E731
    minutes = {
        "known": len(durs),
        "median": half_up(statistics.median(durs)) if durs else None,
        "long": sum(1 for d in durs if d >= LONG_MIN),
        "long_best": sum(1 for x in rows if (minutes_of(x) or 0) >= LONG_MIN and has_best(x)),
        "best": sum(1 for x in rows if has_best(x)),
        "best_general": sum(1 for x in rows if BEST_GENRES[0] in (x.get("genres") or [])),
        "best_actress": sum(1 for x in rows if BEST_GENRES[1] in (x.get("genres") or [])),
    }

    revs = [reviews[x["cid"]] for x in rows if x["cid"] in reviews]
    count = sum(r[1] for r in revs)
    review = {"reviewed": len(revs), "avg": round(statistics.mean(r[0] for r in revs), 2) if revs else None,
              "site_avg": ctx["site_avg"], "count": count, "per_work": round(count / len(revs), 1) if revs else None}
    on_sale = [sale[x["cid"]] for x in released if x["cid"] in sale]
    offs = [s["off"] for s in on_sale if s["off"]]
    rk = [ranks[x["cid"]] for x in rows if x["cid"] in ranks]

    co = Counter(g for x in rows for g in dict.fromkeys(x.get("genres") or []) if g not in theme["genres"] and shown_genre(g, words))
    genres = [{"name": g, "n": n} for g, n in sorted(co.items(), key=lambda p: (-p[1], p[0]))[:TOP_GENRES]]

    return {
        "today": today,
        "total": total,
        "released": len(released),
        "upcoming": total - len(released),
        "excluded": sum(1 for x in rows if is_excluded(x, words)),
        "site_total": ctx["site_total"],
        "share": share,
        "years": years,
        "months": months,
        "makers": makers,
        "actresses": actresses,
        "minutes": minutes,
        "single": sum(1 for x in rows if len(dict.fromkeys(a for a in x.get("actress") or [] if a)) == 1),
        "no_actress": sum(1 for x in rows if not any(x.get("actress") or [])),
        "reviews": review,
        "sale": {"now": len(on_sale), "max_off": max(offs) if offs else None},
        "rank": {"best": min(rk) if rk else None, "top100": sum(1 for r in rk if r <= 100), "top1000": sum(1 for r in rk if r <= 1000), "ranked": len(rk)},
        "genres": genres,
        "cid_ai": sum(1 for x in rows if x["cid"].endswith("ai")),
        "classic": sum(1 for x in rows if any(g in (x.get("genres") or []) for g in CLASSIC_GENRES)),
    }


def candidate_score(x, ctx):
    """選べる作品の並べ順の点: 人気の順位（上ほど高い）＋評価（件数でならした平均と、サイト全体の平均の差）＋セール中"""
    s = 0.0
    r = ctx["ranks"].get(x["cid"])
    if r:
        s += 3 * max(0.0, 1 - math.log10(r) / math.log10(UNKNOWN_RANK))
    rv = ctx["reviews"].get(x["cid"])
    mean = ctx["site_avg"] or 0
    if rv and rv[1] >= REVIEW_MIN_SCORE:
        s += 5 * ((rv[1] * rv[0] + REVIEW_PRIOR * mean) / (rv[1] + REVIEW_PRIOR) - mean)
    if x["cid"] in ctx["sale"]:
        s += 0.3
    return s


def pickable_pool(ctx, theme):
    """最初に見る5本に選べる作品（テーマの作品のうち、発売済みで、外す作品ではないもの）"""
    return [x for x in ctx["works"] if matches(x, theme) and day_of(x) <= ctx["today"] and not is_excluded(x, ctx["words"])]


def theme_candidates(ctx, theme):
    """最初に見る5本の候補（pickable_pool）を、人気・評価・セールの点の高い順に、同じメーカーは3本まで。作品タイトルは出さない"""
    words = ctx["words"]
    pool = pickable_pool(ctx, theme)
    scored = sorted(pool, key=lambda x: (-candidate_score(x, ctx), ctx["ranks"].get(x["cid"], UNKNOWN_RANK), x["cid"]))
    out, per_maker = [], Counter()
    for x in scored:
        mk = x.get("maker") if x.get("maker") and x.get("maker") != "不明" else None
        if mk and per_maker[mk] >= CANDIDATES_PER_MAKER:
            continue
        per_maker[mk] += 1
        rv = ctx["reviews"].get(x["cid"])
        sale = ctx["sale"].get(x["cid"])
        out.append({
            "cid": x["cid"],
            "date": day_of(x),
            "maker": mk,
            "actress": [a for a in (x.get("actress") or []) if a][:4],
            "minutes": minutes_of(x),
            "genres": [g for g in dict.fromkeys(x.get("genres") or []) if shown_genre(g, words)][:8],
            "series": x["series"] if x.get("series") and safe_name(x["series"], words) else None,
            "rank": ctx["ranks"].get(x["cid"]),
            "stars": rv[0] if rv else None,
            "reviews": rv[1] if rv else None,
            "sale": sale,
        })
        if len(out) >= CANDIDATES_MAX:
            break
    return out


# ------------------------------------------------------------------
# list
# ------------------------------------------------------------------
def split_arg(value):
    return [v.strip() for v in re.split(r"[,、]", value or "") if v.strip()]


def check_today(today):
    if not DAY_RE.match(today or ""):
        sys.exit("❌ --today は YYYY-MM-DD の形で指定してください")
    return today


def resolve_theme(slug, existing, genres=None, keywords=None):
    if genres or keywords:
        return normalize_theme({"genres": genres or [], "keywords": keywords or []})
    if existing and normalize_theme(existing.get("theme")):
        return normalize_theme(existing["theme"])
    return normalize_theme(BUILTIN_THEMES.get(slug))


def cmd_list(args):
    today = check_today(args.today or cc.jst_today())
    slug = args.slug
    if not SLUG_RE.match(slug) or len(slug) > SLUG_MAX:
        sys.exit(f"❌ --slug は英小文字・数字・ハイフンで{SLUG_MAX}文字まで（例: ai-remaster）")
    existing = load_yomimono()["articles"].get(slug)
    theme = resolve_theme(slug, existing, split_arg(args.genres), split_arg(args.keywords))
    if theme is None:
        sys.exit("❌ 新しいテーマは --genres（ジャンル）か --keywords（題に入る言葉）を指定してください")
    ctx = build_ctx(today)
    ng = theme_problems(theme, ctx["words"])
    if ng:
        sys.exit("❌ このテーマは読み物にしません（未成年を連想させる・無理やりや犯罪を思わせる言葉）: " + "、".join(ng))
    facts = theme_facts(ctx, theme)
    cands = theme_candidates(ctx, theme)
    out = {"today": today, "slug": slug, "status": "rewrite" if existing else "new", "theme": theme}
    if existing:
        out["previous"] = {"title": existing.get("title"), "written": existing.get("written"), "checked": existing.get("checked")}
    if len(cands) < PICKS:
        out["status"] = "too_few"
        out["message"] = f"選べる作品が{PICKS}本に満たないため、この記事は書けません。ほかのテーマにしてください"
    else:
        out["message"] = (f"facts の数字だけで書き、candidates の cid から{PICKS}本を選んでください（作品タイトルは出していません）。"
                          "書いたら apply で点検して書き込みます")
    out["facts"] = facts
    out["candidates"] = cands
    print(cc.dumps_lines(out))  # 1行に1件（Claude が読む量を減らす）


# ------------------------------------------------------------------
# themes（毎週の予約タスク用: 書き直す記事と、新しいテーマの候補）
# ------------------------------------------------------------------
def cmd_themes(args):
    today = check_today(args.today or cc.jst_today())
    articles = load_yomimono()["articles"]
    ctx = build_ctx(today)
    words = ctx["words"]
    limit = (to_date(today) - timedelta(days=REWRITE_DAYS)).isoformat()
    rewrite = sorted(({"slug": s, "title": a.get("title"), "checked": a.get("checked"), "days": (to_date(today) - to_date(a["checked"])).days}
                      for s, a in articles.items() if DAY_RE.match(str(a.get("checked") or "")) and a["checked"] < limit),
                     key=lambda r: (r["checked"], r["slug"]))
    builtin = []
    for slug, theme in BUILTIN_THEMES.items():
        if slug not in articles:
            builtin.append({"slug": slug, "theme": theme, "total": sum(1 for x in ctx["works"] if matches(x, theme)),
                            "pickable": len(pickable_pool(ctx, theme))})
    themes_now = [t for t in (normalize_theme(a.get("theme")) for a in articles.values()) if t] + list(BUILTIN_THEMES.values())
    used = {g for t in themes_now for g in t["genres"]}
    theme_sets = [{x["cid"] for x in ctx["works"] if matches(x, t)} for t in themes_now]
    total = Counter(g for x in ctx["works"] for g in dict.fromkeys(x.get("genres") or []))
    pickable = Counter(g for x in ctx["works"] if day_of(x) <= today and not is_excluded(x, words) for g in dict.fromkeys(x.get("genres") or []))
    proposals = []
    for g, n in sorted(total.items(), key=lambda p: (-p[1], p[0])):
        if (n < THEME_MIN_WORKS or g in used or not shown_genre(g, words) or pickable[g] < THEME_MIN_PICKABLE
                or theme_problems({"genres": [g], "keywords": []}, words)):
            continue
        cids = {x["cid"] for x in ctx["works"] if g in (x.get("genres") or [])}
        if any(len(cids & ts) >= THEME_OVERLAP * len(cids) for ts in theme_sets):
            continue
        proposals.append({"genres": [g], "keywords": [], "total": n, "pickable": pickable[g]})
        if len(proposals) >= THEMES_SHOWN:
            break
    out = {"today": today, "rewrite": rewrite, "builtin": builtin, "new": proposals,
           "message": ("rewrite があれば、先頭の1本を書き直す。無ければ builtin の先頭、それも無ければ new から1つを選んで新しく書く"
                       "（slug は英小文字・数字・ハイフンの短いローマ字。list --slug <slug> --genres <ジャンル>）")}
    print(cc.dumps_lines(out))


# ------------------------------------------------------------------
# apply
# ------------------------------------------------------------------
NUM_RE = re.compile(r"(?<![0-9A-Za-z.,])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![0-9A-Za-z])")


ABOUT_RE = re.compile(r"(約|およそ|おおよそ|ほぼ|ざっと)$")


def number_tokens(text, names):
    """文章の中の数字 [(数字の文字（カンマなし）, うしろの文字, 前に「約」などがあるか)]。名前（メーカー・出演者・ジャンルなど）の中の数字と、
    VR・8K のような英数字のかたまりは除く。1,234 と 4.52 は1つの数字として読む"""
    for n in sorted(names, key=len, reverse=True):
        if n:
            text = text.replace(n, " ")
    text = unicodedata.normalize("NFKC", text)
    return [(m.group(1).replace(",", ""), text[m.end():m.end() + 1], bool(ABOUT_RE.search(text[max(0, m.start() - 4):m.start()])))
            for m in NUM_RE.finditer(text)]


def rounded_forms(allowed):
    """「約1,500本」「1.5万本」のような、facts の数字（100以上）を丸めた数（10・100・1000の位）"""
    out = set()
    for t in allowed:
        if t.isdigit() and int(t) >= 100:
            v = int(t)
            out.update(str(half_up(v / u) * u) for u in (10, 100, 1000) if half_up(v / u))
    return out


def number_ok(tok, nxt, about, ok, rounded, this_year):
    """その数字を書いてよいか: facts の数字・日付・1〜10・「約」のあとの丸めた数・「万」の付いた丸めた数"""
    if tok in ok or is_date_token(tok, nxt, this_year) or (tok.isdigit() and 1 <= int(tok) <= 10):
        return True
    if about and tok in rounded:
        return True
    if nxt == "万":
        return str(half_up(float(tok) * 10000)) in rounded
    return False


def is_date_token(tok, nxt, this_year):
    """「2026年」「10月」「28日」のような日付の数字か"""
    if not tok.isdigit():
        return False
    v = int(tok)
    return (nxt == "年" and 1960 <= v <= this_year + 1) or (nxt == "月" and 1 <= v <= 12) or (nxt == "日" and 1 <= v <= 31)


def float_forms(v):
    """小数の書き方（4.52 → "4.52" "4.5" "5"）"""
    two = f"{v:.2f}"
    return {two, f"{v:.1f}", two.rstrip("0").rstrip("."), f"{v:.1f}".rstrip("0").rstrip("."), str(half_up(v))}


def fact_numbers(facts):
    """文章に出てきてよい数字（文字）: facts の数字すべて・となりの年/月の差・評価の平均とサイト全体の平均の差・年の幅・決まった数"""
    out = set()

    def walk(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, int):
            out.add(str(v))
        elif isinstance(v, float):
            out.update(float_forms(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(facts)
    ys = facts["years"]
    out.update(str(abs(b["n"] - a["n"])) for a, b in zip(ys, ys[1:]))
    if ys:
        out.update({str(len(ys)), str(ys[-1]["y"] - ys[0]["y"])})
    ms = facts["months"]
    out.update(str(abs(b[k] - a[k])) for a, b in zip(ms, ms[1:]) for k in ("n", "all"))
    rv = facts["reviews"]
    if rv["avg"] is not None and rv["site_avg"] is not None:
        out.update(float_forms(abs(rv["avg"] - rv["site_avg"])))
    out.update({str(LONG_MIN), "4", "100", "1000", str(MONTHS), str(PICKS)})
    return out


def candidate_numbers(c):
    out = {str(c[k]) for k in ("minutes", "rank", "reviews") if isinstance(c.get(k), int)}
    if isinstance(c.get("stars"), float):
        out |= float_forms(c["stars"])
    if c.get("sale") and c["sale"].get("off"):
        out.add(str(c["sale"]["off"]))
    out.add(str(len(c["actress"])))
    return out


def title_grams(works):
    """全作品の題の、cc.COPY_RUN 文字ずつのかたまり（題の写しを探すため）"""
    n = cc.COPY_RUN
    grams = set()
    for x in works:
        t = str(x.get("title") or "")
        grams.update(t[i:i + n] for i in range(len(t) - n + 1))
    return grams


def copied_piece(text, grams, masks):
    """文章の中に、どれかの作品の題から cc.COPY_RUN 文字以上そのまま写した所があれば、その文字（名前・ジャンル・キーワードは除いて調べる）"""
    for m in sorted((m for m in masks if m), key=len, reverse=True):
        text = text.replace(m, "\u0001")
    n = cc.COPY_RUN
    for i in range(len(text) - n + 1):
        piece = text[i:i + n]
        if "\u0001" not in piece and piece in grams:
            return piece
    return ""


def common_problems(text, lo, hi):
    """共通の点検（cc.text_problems）。FANZAのレビューの「★」だけは記号として使ってよい（作品カードの表示と同じ）"""
    return cc.text_problems(text.replace("★", "星"), lo, hi) + style_problems(text)


def style_problems(text):
    """記事だけの点検（共通の点検 cc.text_problems に足すもの）"""
    problems = []
    hype = [w for w in HYPE_WORDS if w in text]
    if hype:
        problems.append("確かめられない評価・大げさな言い方があります（数字で書いてください）: " + "、".join(hype))
    first = [w for w in FIRST_PERSON_WORDS if w in text]
    if first:
        problems.append("自分の体験・感想・決まり文句の問いかけのような言い方があります（事実だけで書いてください）: " + "、".join(first))
    ai = [w for w in AI_SCREEN_PHRASES if w in text]
    if ai:
        problems.append("画面に出さない「AI」の言い回しがあります: " + "、".join(ai))
    arrows = sorted({c for c in text if c in ARROW_CHARS})
    if arrows:
        problems.append("矢印の記号は使いません: " + " ".join(arrows))
    return problems


def paragraphs_of(text):
    return [p.strip() for p in text.split("\n")]


def check_article(slug, art, ctx, existing, grams):
    """記事1本の問題点 [(場所, 理由)] と、書き込む形（問題があれば None）"""
    problems = []

    def add(where, why):
        problems.append((f"{slug} の {where}", why))

    if not SLUG_RE.match(slug) or len(slug) > SLUG_MAX:
        return [(slug, f"slug は英小文字・数字・ハイフンで{SLUG_MAX}文字まで（例: ai-remaster）")], None
    if not isinstance(art, dict):
        return [(slug, "記事は {title, description, lead, sections, picks} の形にしてください")], None
    unknown = sorted(set(art) - {"title", "description", "lead", "sections", "picks_h", "picks", "theme"})
    if unknown:
        add("全体", "知らない項目があります: " + "、".join(unknown))
    if "theme" in art:
        theme = normalize_theme(art["theme"])
        if theme is None:
            return problems + [(f"{slug} の theme", '{"genres": [...], "keywords": [...]}（どちらかに1つ以上）の形にしてください')], None
    else:
        theme = resolve_theme(slug, existing)
        if theme is None:
            return problems + [(f"{slug} の theme", "新しいテーマは theme を入れてください（list に出た theme）")], None
    ng = theme_problems(theme, ctx["words"])
    if ng:
        return problems + [(f"{slug} の theme", "このテーマは読み物にしません: " + "、".join(ng))], None

    facts = theme_facts(ctx, theme)
    cands = {c["cid"]: c for c in theme_candidates(ctx, theme)}
    if len(cands) < PICKS:
        return problems + [(f"{slug} の theme", f"選べる作品が{PICKS}本に満たないため、この記事は書けません")], None

    texts = []      # (場所, 文, 段落か) 数字・題の写しを調べる文
    strings = {}
    for key, lo, hi in (("title", TITLE_MIN, TITLE_MAX), ("description", DESC_MIN, DESC_MAX)):
        v = art.get(key)
        if not isinstance(v, str):
            add(key, "文字列で書いてください")
            continue
        v = v.strip()
        strings[key] = v
        for why in common_problems(v, lo, hi):
            add(key, why)
        texts.append((key, v, False))

    body_len = 0
    seen_paras = {}
    lead = art.get("lead")
    lead_paras = []
    if not isinstance(lead, str):
        add("lead", "文字列で書いてください（2つの段落を改行 \\n で区切る）")
    else:
        lead_paras = paragraphs_of(lead.strip())
        if len(lead_paras) != 2 or not all(lead_paras):
            add("lead", f"導入文は2つの段落にしてください（いま{len([p for p in lead_paras if p])}段落。段落の区切りは改行1つ）")
        for i, p in enumerate(lead_paras, 1):
            if not p:
                continue
            for why in common_problems(p, PARA_MIN, PARA_MAX):
                add(f"lead の{i}段落め", why)
            texts.append((f"lead の{i}段落め", p, True))
            body_len += len(p)
            seen_paras.setdefault(p, []).append(f"lead の{i}段落め")

    sections = art.get("sections")
    clean_sections = []
    if not isinstance(sections, list) or not (SECTIONS_MIN <= len(sections) <= SECTIONS_MAX):
        add("sections", f"節は{SECTIONS_MIN}〜{SECTIONS_MAX}個のリストにしてください")
        sections = sections if isinstance(sections, list) else []
    charts = 0
    for i, s in enumerate(sections, 1):
        where = f"sections[{i}]"
        if not isinstance(s, dict) or not isinstance(s.get("h"), str) or not isinstance(s.get("text"), str):
            add(where, '{"h": 見出し, "text": 本文} の形（どちらも文字列）にしてください')
            continue
        extra = sorted(set(s) - {"h", "text", "chart"})
        if extra:
            add(where, "知らない項目があります: " + "、".join(extra))
        h = s["h"].strip()
        for why in common_problems(h, HEAD_MIN, HEAD_MAX):
            add(f"{where} の見出し", why)
        texts.append((f"{where} の見出し", h, False))
        paras = paragraphs_of(s["text"].strip())
        if not (1 <= len(paras) <= PARAS_MAX) or not all(paras):
            add(where, f"本文は1〜{PARAS_MAX}段落にしてください（段落の区切りは改行1つ。空の段落は入れない）")
        for j, p in enumerate(paras, 1):
            if not p:
                continue
            for why in common_problems(p, PARA_MIN, PARA_MAX):
                add(f"{where} の{j}段落め", why)
            texts.append((f"{where} の{j}段落め", p, True))
            body_len += len(p)
            seen_paras.setdefault(p, []).append(f"{where} の{j}段落め")
        entry = {"h": h, "text": "\n".join(paras)}
        if "chart" in s:
            if s["chart"] != "years":
                add(where, 'chart は "years"（年ごとの本数のグラフ）だけです')
            else:
                charts += 1
                entry["chart"] = "years"
        clean_sections.append(entry)
    if charts > 1:
        add("sections", 'chart: "years" は1つの節だけにしてください')
    if charts and not facts["years"]:
        add("sections", "年ごとの本数が無いので、グラフは付けられません")
    if not (BODY_MIN <= body_len <= BODY_MAX):
        add("本文", f"導入文と節の本文の合計が {body_len} 文字です（{BODY_MIN}〜{BODY_MAX}文字にしてください。改行は数えない）")
    for p, wheres in seen_paras.items():
        if len(wheres) > 1:
            add("、".join(wheres), "同じ段落が2回あります")

    picks_h = art.get("picks_h", DEFAULT_PICKS_H)
    if not isinstance(picks_h, str):
        add("picks_h", "文字列で書いてください")
        picks_h = DEFAULT_PICKS_H
    picks_h = picks_h.strip()
    for why in common_problems(picks_h, HEAD_MIN, HEAD_MAX):
        add("picks_h", why)
    texts.append(("picks_h", picks_h, False))

    picks = art.get("picks")
    clean_picks, picked = [], []
    if not isinstance(picks, list) or len(picks) != PICKS:
        add("picks", f"最初に見る作品は、ちょうど{PICKS}本のリストにしてください")
        picks = picks if isinstance(picks, list) else []
    seen_cids, seen_whys = set(), {}
    for i, p in enumerate(picks, 1):
        where = f"picks[{i}]"
        if not isinstance(p, dict) or not isinstance(p.get("cid"), str) or not isinstance(p.get("why"), str) or set(p) - {"cid", "why"}:
            add(where, '{"cid": ..., "why": ...} の形（どちらも文字列）にしてください')
            continue
        cid, why = p["cid"], p["why"].strip()
        if cid not in cands:
            work = next((x for x in ctx["works"] if x["cid"] == cid), None)
            if work is not None and is_excluded(work, ctx["words"]):
                add(where, f"cid「{cid}」は読み物では選べない作品です（外す作品）")
            else:
                add(where, f"cid「{cid}」は list の candidates にありません（candidates の cid から選んでください）")
            continue
        if cid in seen_cids:
            add(where, f"cid「{cid}」が重複しています")
        seen_cids.add(cid)
        picked.append(cands[cid])
        for w in common_problems(why, WHY_MIN, WHY_MAX):
            add(where, w)
        if not SUIT_RE.search(why):
            add(where, "どんな人に向くかの1文を入れてください（例: 「長めの作品を通して見たい人に向いています」）")
        for name in cands[cid]["actress"]:
            if name and why.count(name) > 1:
                add(where, f"出演者名「{name}」が2回以上入っています（1回まで）")
        seen_whys.setdefault(why, []).append(where)
        texts.append((where, why, False, cid))
        clean_picks.append({"cid": cid, "why": why})
    for why, wheres in seen_whys.items():
        if len(wheres) > 1:
            for w in wheres:
                add(w, "同じ文章が他の作品にも使われています")

    # 名前（数字・題の写しを調べるときは除く）: facts と候補の名前・テーマの作品のジャンル・テーマの言葉
    rows = [x for x in ctx["works"] if matches(x, theme)]
    names = set(theme["genres"]) | set(theme["keywords"]) | set(BEST_GENRES) | set(CLASSIC_GENRES)
    names |= {g for x in rows for g in (x.get("genres") or []) if isinstance(g, str)}
    for m in facts["makers"]:
        names.add(m["name"])
        names |= {d["name"] for d in (m["series"], m["label"]) if d}
    names |= {a["name"] for a in facts["actresses"]} | {g["name"] for g in facts["genres"]}
    for c in cands.values():
        names |= set(c["actress"]) | set(c["genres"]) | {v for v in (c["maker"], c["series"]) if v}

    allowed = fact_numbers(facts)
    body_allowed = allowed | {n for c in picked for n in candidate_numbers(c)}
    this_year = int(ctx["today"][:4])
    for where, text, is_para, *pick in texts:
        # 選んだ作品の理由は、facts とその作品の数字だけ。本文は、facts と選んだ5本の数字
        ok = allowed | candidate_numbers(cands[pick[0]]) if pick else body_allowed
        toks = number_tokens(text, names)
        rounded = rounded_forms(ok)
        bad = sorted({t for t, nxt, about in toks if not number_ok(t, nxt, about, ok, rounded, this_year)}, key=float)
        if bad:
            add(where, "facts にない数字があります（list の facts・candidates の数字と、日付・1〜10の小さな数だけを使ってください）: " + "、".join(bad))
        if is_para:
            # 日付と、1〜10の小さな数（「5本」「4時間」など）は数えない
            counted = [t for t, nxt, _ in toks if not is_date_token(t, nxt, this_year) and not (t.isdigit() and int(t) <= 10)]
            if len(counted) > NUMBERS_PER_PARA:
                add(where, f"数字が{len(counted)}つあります（1段落に{NUMBERS_PER_PARA}つまで。数字は話を支える材料として、しぼって使ってください）")
        piece = copied_piece(text, grams, names)
        if piece:
            add(where, f"作品の題の言葉をそのまま写しています（「{piece}」。題は本文に書きません）")

    if problems:
        return problems, None
    entry = {
        "theme": theme,
        "title": strings["title"],
        "description": strings["description"],
        "lead": "\n".join(lead_paras),
        "sections": clean_sections,
        "picks_h": picks_h,
        "picks": clean_picks,
    }
    if charts:
        entry["years"] = facts["years"]
    entry["total"] = facts["total"]
    entry["written"] = existing.get("written") if existing and DAY_RE.match(str(existing.get("written") or "")) else ctx["today"]
    entry["checked"] = ctx["today"]
    return [], entry


def cmd_apply(args):
    today = check_today(args.today or cc.jst_today())
    raw = cr.read_article(args.file)
    if not isinstance(raw, dict) or not raw:
        sys.exit('❌ {"<slug>": {title, description, lead, sections, picks}} の形にしてください')
    data = load_yomimono()
    ctx = build_ctx(today)
    grams = title_grams(ctx["works"])
    problems, entries = [], {}
    for slug, art in raw.items():
        probs, entry = check_article(slug, art, ctx, data["articles"].get(slug), grams)
        problems += probs
        if entry:
            entries[slug] = entry
    if problems:
        print(f"❌ 問題が {len(problems)} 件あります。何も書き込んでいません。直してもう一度実行してください")
        for where, why in problems:
            print(f"  - {where}: {why}")
        sys.exit(1)
    if args.dry_run:
        print("✅ 問題ありません（--dry-run のため書き込んでいません）")
        return
    rewritten = [s for s in entries if s in data["articles"]]
    data["articles"].update(entries)
    data["updated"] = today
    saved = save_yomimono(data)
    if load_yomimono() != saved:
        sys.exit("❌ 書き込み後の確認に失敗しました。git で変更を取り消してください")
    for slug, e in entries.items():
        print(f"✅ {slug}「{e['title']}」を{'書き直しました' if slug in rewritten else '書き込みました'}（{e['total']}本のテーマ。記事は全部で{len(saved['articles'])}本）")


def main():
    parser = argparse.ArgumentParser(description="Claude が読み物（/yomimono/）の記事を書くための道具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_themes = sub.add_parser("themes", aliases=["candidates"], help="書き直す記事と、新しいテーマの候補を出す（毎週の予約タスク用）")
    p_themes.add_argument("--today", help="今日の日付 YYYY-MM-DD（テスト用。省略すると日本時間の今日）")
    p_themes.set_defaults(func=cmd_themes)

    p_list = sub.add_parser("list", help="テーマの数字（facts）と、選べる作品（candidates）を出す")
    p_list.add_argument("--slug", required=True, help="記事の slug（例: ai-remaster）")
    p_list.add_argument("--genres", help="新しいテーマのジャンル（カンマ区切り）")
    p_list.add_argument("--keywords", help="新しいテーマの、題に入る言葉（カンマ区切り）")
    p_list.add_argument("--today", help="今日の日付 YYYY-MM-DD（テスト用。省略すると日本時間の今日）")
    p_list.set_defaults(func=cmd_list)

    p_apply = sub.add_parser("apply", help="記事を点検して書き込む")
    p_apply.add_argument("file", help='{"<slug>": {記事}} のJSONファイル')
    p_apply.add_argument("--dry-run", action="store_true", help="点検だけして書き込まない")
    p_apply.add_argument("--today", help="書いた日・確かめた日に入れる日付 YYYY-MM-DD（テスト用。省略すると日本時間の今日）")
    p_apply.set_defaults(func=cmd_apply)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
