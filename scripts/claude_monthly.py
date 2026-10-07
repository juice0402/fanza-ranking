#!/usr/bin/env python3
"""Claude が「月のまとめ記事」を書くための道具（Python標準ライブラリだけ。2026-10-07 から）

毎月1日に、前の月に発売された作品（毎日の更新で、このサイトに載せた作品）のまとめ記事を、Claude が書きます。
記事は、月のページ（/month/YYYY-MM/）のいちばん上に出ます。
記事の本体は「導入文（lead）」「この月の傾向（trend）」と「注目の作品（picks）とそのひとこと」です。
週のまとめ記事（claude_roundups.py）と同じ点検・同じ傾向の数字を使います。手順と書き方は docs/claude-monthly.md を見てください。

  python3 scripts/claude_monthly.py list [--month YYYY-MM] [--today YYYY-MM-DD]
      書く対象の月と、その月の作品データ（出演者・メーカー・形式・発売日・収録時間・ジャンル・デビュー作か・最高順位。作品タイトルは出さない）と、
      傾向の数字（前の月との比べ・ジャンル・新着の人気順で上位に入った作品）を表示する
  python3 scripts/claude_monthly.py apply 記事.json [--dry-run] [--today YYYY-MM-DD]
      {"month": "YYYY-MM", "lead": "...", "trend": "...", "picks": [{"cid": "...", "note": "..."}]} を点検して、
      問題が無ければ site/src/data/monthly.json に追加する（1件でも問題があれば何も書き込まない）

保存先: site/src/data/monthly.json（環境変数 MONTHLY_PATH で変えられる。作品データは DATA_PATH）
"""
import argparse
import calendar
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claude_comments as cc  # 禁止語・文字の点検（コメントと同じルール）
import claude_roundups as cr  # 日付・作品データの読み込み・傾向の数字（週のまとめと同じ）

MONTHLY_PATH = os.environ.get("MONTHLY_PATH", os.path.join(cr.ROOT, "site", "src", "data", "monthly.json"))

MIN_MONTH_ITEMS = 30         # この月の作品がこれより少ないときは、記事を作らない（内容が薄くなるため）
LEAD_MIN, LEAD_MAX = 100, 360
TREND_MIN, TREND_MAX = cr.TREND_MIN, cr.TREND_MAX
NOTE_MIN, NOTE_MAX = cr.NOTE_MIN, cr.NOTE_MAX
PICKS_MIN, PICKS_MAX = 4, 8
TOP_MAKERS = 5
TOP_ACTRESSES = 5            # 2本以上に出た人だけ
BUSY_DAYS = 3                # 掲載の多かった日を、多い順にいくつ出すか
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# ------------------------------------------------------------------
# 月の日付
# ------------------------------------------------------------------
def month_first(month):
    return f"{month}-01"


def month_last(month):
    y, m = int(month[:4]), int(month[5:7])
    return f"{month}-{calendar.monthrange(y, m)[1]:02d}"


def prev_month(month):
    y, m = int(month[:4]), int(month[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def latest_finished_month(today):
    """today より前に終わった、いちばん新しい月（今日が10月1日なら9月）"""
    return prev_month(today[:7])


def month_items(items, month):
    first, last = month_first(month), month_last(month)
    return sorted((x for x in items if first <= cr.day_of(x) <= last), key=lambda x: (cr.day_of(x), x["cid"]))


# ------------------------------------------------------------------
# 読み書き
# ------------------------------------------------------------------
def load_monthly():
    if not os.path.exists(MONTHLY_PATH):
        return []
    try:
        with open(MONTHLY_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"❌ 月のまとめ記事のデータを読めませんでした（{e}）")
    if not isinstance(raw, list) or not all(isinstance(x, dict) and x.get("month") for x in raw):
        sys.exit("❌ 月のまとめ記事のデータの形が違います（month のある記事のリストではありません）")
    return raw


def save_monthly(rows):
    """週のまとめ記事と同じ書き方（インデント1・日本語そのまま・末尾に改行）"""
    tmp_path = MONTHLY_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp_path, MONTHLY_PATH)  # 書き込み途中で止まってもデータが壊れないように


# ------------------------------------------------------------------
# 月の集計と傾向
# ------------------------------------------------------------------
def month_stats(items, month):
    rows = month_items(items, month)
    makers = [x.get("maker") for x in rows if x.get("maker") and x.get("maker") != "不明"]
    actresses = [a for x in rows for a in dict.fromkeys(x.get("actress") or [])]
    formats = [f for x in rows for f in dict.fromkeys(cr.formats_of(x))]
    per_day = cr.count_by(cr.day_of(x) for x in rows)
    return {
        "total": len(rows),
        "per_week": [{"week_start": w, "count": c} for w, c in sorted(cr.count_by(cr.week_start_of(cr.day_of(x)) for x in rows))],
        "busy_days": [{"date": d, "count": c} for d, c in sorted(per_day, key=lambda p: (-p[1], p[0]))[:BUSY_DAYS]],
        "makers": cr.ranked(cr.count_by(makers), 1, TOP_MAKERS),
        "actresses": cr.ranked(cr.count_by(actresses), 2, TOP_ACTRESSES),
        "formats": cr.ranked(cr.count_by(formats), 1),
    }


def month_trend(items, month, hist=None, pool=None):
    hist = cr.load_rank_history() if hist is None else hist
    pool = (items + cr.load_catalog_items()) if pool is None else pool
    seen, merged = set(), []
    for x in pool:
        if x["cid"] not in seen:
            seen.add(x["cid"])
            merged.append(x)
    prev = prev_month(month)
    return cr.period_trend(month_items(items, month), month_items(items, prev), merged, hist, month_first(month), month_last(month)) | {"prev_month": prev}


# ------------------------------------------------------------------
# list
# ------------------------------------------------------------------
def cmd_list(args):
    today = args.today or cr.jst_today()
    month = args.month or latest_finished_month(today)
    if not MONTH_RE.match(month):
        sys.exit("❌ --month は YYYY-MM の形で指定してください")
    out = {"today": today, "month": month, "first": month_first(month), "last": month_last(month)}

    if month_last(month) >= today:
        out["status"] = "not_finished"
        out["message"] = "この月はまだ終わっていません。何もしないで終了してください"
    elif any(r.get("month") == month for r in load_monthly()):
        out["status"] = "already_written"
        out["message"] = "この月のまとめ記事はもうあります。何もしないで終了してください"
    else:
        items = cr.load_items()
        rows = month_items(items, month)
        if len(rows) < MIN_MONTH_ITEMS:
            out["status"] = "too_few_items"
            out["total"] = len(rows)
            out["message"] = f"この月の作品が{MIN_MONTH_ITEMS}本に満たないため、記事は作りません。何もしないで終了してください"
        else:
            hist = cr.load_rank_history()
            out["status"] = "ready"
            out.update(month_stats(items, month))
            out["trend"] = month_trend(items, month, hist=hist)
            out["weekly"] = [r["week_start"] for r in cr.load_roundups() if month_first(month) <= r.get("week_start", "") <= month_last(month)]
            out["items"] = [{
                "cid": x["cid"],
                "date": cr.day_of(x),
                "actress": x.get("actress") or [],
                "maker": None if (not x.get("maker") or x.get("maker") == "不明") else x["maker"],
                "formats": cr.formats_of(x),
                "duration_min": x["duration_min"] if isinstance(x.get("duration_min"), int)
                and not isinstance(x.get("duration_min"), bool) and x["duration_min"] > 0 else None,
                "genres": [g for g in (x.get("genres") or []) if g in cr.CONTENT_GENRES],
                "debut": cr.DEBUT_GENRE in (x.get("genres") or []),
                "best_rank": (cr.rank_stats(hist[x["cid"]]) or [None])[0] if x["cid"] in hist else None,
                "no_pick": cc.title_block_reason(x) == "minor",
            } for x in rows]
    print(json.dumps(out, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------
# apply
# ------------------------------------------------------------------
def allowed_numbers(month, stats, picked_rows, hist):
    """文章に出てきてよい数字: 月の集計の本数、年・月・その月の日、前の月、選んだ作品の収録時間と最高順位など、1・7"""
    y, m = int(month[:4]), int(month[5:7])
    allowed = {1, 7, len(picked_rows), stats["total"], y, m, int(prev_month(month)[5:7]), int(prev_month(month)[:4])}
    allowed.update(range(1, int(month_last(month)[8:10]) + 1))
    allowed.add(len(stats["per_week"]))  # 「5つの週」
    for key in ("per_week", "busy_days", "makers", "actresses", "formats"):
        allowed.update(r["count"] for r in stats[key])
    for x in picked_rows:
        if isinstance(x.get("duration_min"), int):
            allowed.add(x["duration_min"])
        st = cr.rank_stats(hist[x["cid"]]) if x["cid"] in hist else None
        if st:
            allowed.update({st[0], st[2], st[3]})
    return allowed


def article_problems(article, items, monthly, today):
    """記事の問題点 [(場所, 理由)]（なければ空）"""
    problems = []

    def add(where, why):
        problems.append((where, why))

    if not isinstance(article, dict):
        return [("全体", '{"month": ..., "lead": ..., "trend": ..., "picks": [...]} の形にしてください')]
    month = article.get("month")
    if not isinstance(month, str) or not MONTH_RE.match(month):
        return [("month", "YYYY-MM の形にしてください")]
    if month_last(month) >= today:
        return [("month", "この月はまだ終わっていません")]
    if any(r.get("month") == month for r in monthly):
        return [("month", "この月のまとめ記事はもうあります（上書きしません）")]
    rows = month_items(items, month)
    if len(rows) < MIN_MONTH_ITEMS:
        return [("month", f"この月の作品が{MIN_MONTH_ITEMS}本に満たないため、記事は作れません（{len(rows)}本）")]

    by_cid = {x["cid"]: x for x in rows}
    stats = month_stats(items, month)
    hist = cr.load_rank_history()
    trend = month_trend(items, month, hist=hist)
    names = {n for x in rows for n in (x.get("actress") or [])} | {x["maker"] for x in rows if x.get("maker")}
    names |= {n for p in trend["popular"] for n in ([p["maker"]] if p["maker"] else []) + p["actress"]}

    lead = article.get("lead")
    if not isinstance(lead, str):
        add("lead", "文字列ではありません")
        lead = ""
    lead = lead.strip()
    for why in cc.text_problems(lead, LEAD_MIN, LEAD_MAX):
        add("lead", why)
    trend_text = article.get("trend")
    if not isinstance(trend_text, str):
        add("trend", "この月の傾向（trend）を文字列で書いてください")
        trend_text = ""
    trend_text = trend_text.strip()
    for why in cr.trend_text_problems(trend_text, lead):
        add("trend", why)

    picks = article.get("picks")
    if not isinstance(picks, list) or not (PICKS_MIN <= len(picks) <= PICKS_MAX):
        add("picks", f"注目の作品は{PICKS_MIN}〜{PICKS_MAX}件のリストにしてください")
        picks = []
    seen_cids, seen_notes, picked_rows = set(), {}, []
    for i, p in enumerate(picks, 1):
        where = f"picks[{i}]"
        if not isinstance(p, dict) or not isinstance(p.get("cid"), str) or not isinstance(p.get("note"), str):
            add(where, '{"cid": ..., "note": ...} の形（どちらも文字列）にしてください')
            continue
        cid, note = p["cid"], p["note"].strip()
        if cid not in by_cid:
            add(where, f"cid「{cid}」はこの月の作品にありません")
            continue
        if cid in seen_cids:
            add(where, f"cid「{cid}」が重複しています")
        if cc.title_block_reason(by_cid[cid]) == "minor":
            add(where, f"cid「{cid}」は注目の作品に選べません（list の no_pick: true。こちらから勧める欄のため）")
        seen_cids.add(cid)
        picked_rows.append(by_cid[cid])
        for why in cc.text_problems(note, NOTE_MIN, NOTE_MAX):
            add(where, why)
        for name in by_cid[cid].get("actress") or []:
            if name and note.count(name) > 1:
                add(where, f"出演者名「{name}」が2回以上入っています（1回まで）")
        seen_notes.setdefault(note, []).append(where)
    for note, wheres in seen_notes.items():
        if len(wheres) > 1:
            for w in wheres:
                add(w, "同じ文章が他の作品にも使われています")

    allowed = allowed_numbers(month, stats, picked_rows, hist) | cr.trend_numbers(trend)
    for where, text in [("lead", lead), ("trend", trend_text)] + [(f"picks[{i}]", p["note"]) for i, p in enumerate(picks, 1)
                                                                  if isinstance(p, dict) and isinstance(p.get("note"), str)]:
        unknown = sorted(cr.numbers_in(text, names) - allowed)
        if unknown:
            add(where, "一覧にない数字があります（list の数字・日付・収録時間・順位だけを使ってください）: " + "、".join(map(str, unknown)))
    return problems


def cmd_apply(args):
    today = args.today or cr.jst_today()
    if not cr.DAY_RE.match(today):
        sys.exit("❌ --today は YYYY-MM-DD の形で指定してください")
    article = cr.read_article(args.file)
    items = cr.load_items()
    monthly = load_monthly()

    problems = article_problems(article, items, monthly, today)
    if problems:
        print(f"❌ 問題が {len(problems)} 件あります。何も書き込んでいません。直してもう一度実行してください")
        for where, why in problems:
            print(f"  - {where}: {why}")
        sys.exit(1)

    if args.dry_run:
        print("✅ 問題ありません（--dry-run のため書き込んでいません）")
        return

    entry = {
        "month": article["month"],
        "lead": article["lead"].strip(),
        "trend": article["trend"].strip(),
        "picks": [{"cid": p["cid"], "note": p["note"].strip()} for p in article["picks"]],
        "written": today,
        "facts": cr.trend_facts(month_trend(items, article["month"])),
    }
    rows = sorted(monthly + [entry], key=lambda r: r["month"], reverse=True)
    save_monthly(rows)
    check = load_monthly()
    if len(check) != len(rows) or check[[r["month"] for r in rows].index(entry["month"])] != entry:
        sys.exit("❌ 書き込み後の確認に失敗しました。git で変更を取り消してください")
    print(f"✅ {entry['month']} のまとめ記事を書き込みました（記事は全部で{len(check)}本）")


def main():
    parser = argparse.ArgumentParser(description="Claude が月のまとめ記事を書くための道具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="書く対象の月と、その月の作品データ・傾向の数字を出す")
    p_list.add_argument("--month", help="対象の月 YYYY-MM（省略すると、いちばん新しく終わった月）")
    p_list.add_argument("--today", help="今日の日付 YYYY-MM-DD（テスト用。省略すると日本時間の今日）")
    p_list.set_defaults(func=cmd_list)

    p_apply = sub.add_parser("apply", help="記事を点検して書き込む")
    p_apply.add_argument("file", help="記事のJSONファイル")
    p_apply.add_argument("--dry-run", action="store_true", help="点検だけして書き込まない")
    p_apply.add_argument("--today", help="公開日に入れる日付 YYYY-MM-DD（テスト用。省略すると日本時間の今日）")
    p_apply.set_defaults(func=cmd_apply)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
