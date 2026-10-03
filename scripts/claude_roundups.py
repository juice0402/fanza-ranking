#!/usr/bin/env python3
"""Claude が「週のまとめ記事」を書くための道具（Python標準ライブラリだけ）

毎週月曜に、いちばん新しく終わった週（月曜〜日曜）のまとめ記事を、Claude が書きます。
記事の本体は「導入文（lead）」と「注目の作品（picks）とそのひとこと」です。
本数・メーカー別・出演者別などの数字は、サイトが作品データから自動で作ります。
手順と書き方は docs/claude-roundups.md を見てください。

  python3 scripts/claude_roundups.py list [--week-start YYYY-MM-DD] [--today YYYY-MM-DD]
      書く対象の週と、その週の作品データ（出演者・メーカー・形式・発売日・収録時間。作品タイトルは出さない）を表示する
  python3 scripts/claude_roundups.py apply 記事.json [--dry-run] [--today YYYY-MM-DD]
      {"week_start": "...", "lead": "...", "picks": [{"cid": "...", "note": "..."}]} を点検して、
      問題が無ければ site/src/data/roundups.json に追加する（1件でも問題があれば何も書き込まない）

保存先: site/src/data/roundups.json（環境変数 ROUNDUPS_PATH で変えられる。作品データは DATA_PATH）
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claude_comments as cc  # 禁止語・文字の点検（コメントと同じルール）を使い回す

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.environ.get("DATA_PATH", os.path.join(ROOT, "site", "src", "data", "new_releases.json"))
ROUNDUPS_PATH = os.environ.get("ROUNDUPS_PATH", os.path.join(ROOT, "site", "src", "data", "roundups.json"))
JST = timezone(timedelta(hours=9))

MIN_WEEK_ITEMS = 10          # この週の作品がこれより少ないときは、記事を作らない（内容が薄くなるため）
LEAD_MIN, LEAD_MAX = 80, 300
NOTE_MIN, NOTE_MAX = 40, 120
PICKS_MIN, PICKS_MAX = 3, 6
TOP_MAKERS = 5
TOP_ACTRESSES = 5            # 2本以上に出た人だけ
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ------------------------------------------------------------------
# 日付（日本時間の月曜〜日曜）
# ------------------------------------------------------------------
def to_date(day):
    return date(int(day[:4]), int(day[5:7]), int(day[8:10]))


def week_start_of(day):
    """その日を含む週の月曜日 "YYYY-MM-DD" """
    d = to_date(day)
    return (d - timedelta(days=d.weekday())).isoformat()  # 月曜=0


def add_days(day, n):
    return (to_date(day) + timedelta(days=n)).isoformat()


def jst_today():
    return datetime.now(JST).strftime("%Y-%m-%d")


def latest_finished_week(today):
    """today より前に終わった、いちばん新しい週の月曜日（今日が月曜なら、昨日の日曜で終わった週）"""
    return add_days(week_start_of(today), -7)


# ------------------------------------------------------------------
# データの読み書き
# ------------------------------------------------------------------
def load_items():
    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"❌ 作品データを読めませんでした（{e}）")
    if not isinstance(raw, list):
        sys.exit("❌ 作品データの形が違います（作品のリストではありません）")
    return [x for x in raw if isinstance(x, dict) and x.get("cid") and DAY_RE.match(str(x.get("date") or "")[:10])]


def load_roundups():
    if not os.path.exists(ROUNDUPS_PATH):
        return []
    try:
        with open(ROUNDUPS_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"❌ まとめ記事のデータを読めませんでした（{e}）")
    if not isinstance(raw, list) or not all(isinstance(x, dict) and x.get("week_start") for x in raw):
        sys.exit("❌ まとめ記事のデータの形が違います（week_start のある記事のリストではありません）")
    return raw


def save_roundups(rows):
    """get_new_releases.py の save_archive と同じ書き方（インデント1・日本語そのまま・末尾に改行）"""
    tmp_path = ROUNDUPS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp_path, ROUNDUPS_PATH)  # 書き込み途中で止まってもデータが壊れないように


# ------------------------------------------------------------------
# 週の集計（サイトの lib/roundups.js の weekStats と同じ数え方。tests/test_roundups.mjs で突き合わせている）
# ------------------------------------------------------------------
def day_of(item):
    return str(item.get("date") or "")[:10]


def week_items(items, start):
    end = add_days(start, 6)
    return sorted((x for x in items if start <= day_of(x) <= end), key=lambda x: (day_of(x), x["cid"]))


def formats_of(item):
    return [t for t in (item.get("tags") or []) if isinstance(t, str) and cc.FORMAT_TAG.match(t)]


def ranked(counter_pairs, minimum=1, limit=None):
    """[(名前, 本数)] を、本数の多い順（同数なら名前順）にして、{"name","count"} のリストにする"""
    rows = sorted(((n, c) for n, c in counter_pairs if c >= minimum), key=lambda p: (-p[1], p[0]))
    rows = [{"name": n, "count": c} for n, c in rows]
    return rows[:limit] if limit else rows


def count_by(values):
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return counts.items()


def week_stats(items, start):
    rows = week_items(items, start)
    makers = [x.get("maker") for x in rows if x.get("maker") and x.get("maker") != "不明"]
    actresses = [a for x in rows for a in dict.fromkeys(x.get("actress") or [])]
    formats = [f for x in rows for f in dict.fromkeys(formats_of(x))]
    return {
        "total": len(rows),
        "per_day": [{"date": d, "count": c} for d, c in sorted(count_by(day_of(x) for x in rows))],
        "makers": ranked(count_by(makers), 1, TOP_MAKERS),
        "actresses": ranked(count_by(actresses), 2, TOP_ACTRESSES),
        "formats": ranked(count_by(formats), 1),
    }


# ------------------------------------------------------------------
# list
# ------------------------------------------------------------------
def cmd_list(args):
    today = args.today or jst_today()
    start = args.week_start or latest_finished_week(today)
    if not DAY_RE.match(start) or week_start_of(start) != start:
        sys.exit("❌ --week-start は月曜日の日付（YYYY-MM-DD）にしてください")
    end = add_days(start, 6)
    out = {"today": today, "week_start": start, "week_end": end}

    if end >= today:
        out["status"] = "not_finished"
        out["message"] = "この週はまだ終わっていません。何もしないで終了してください"
    elif any(r.get("week_start") == start for r in load_roundups()):
        out["status"] = "already_written"
        out["message"] = "この週のまとめ記事はもうあります。何もしないで終了してください"
    else:
        items = load_items()
        rows = week_items(items, start)
        if len(rows) < MIN_WEEK_ITEMS:
            out["status"] = "too_few_items"
            out["total"] = len(rows)
            out["message"] = f"この週の作品が{MIN_WEEK_ITEMS}本に満たないため、記事は作りません。何もしないで終了してください"
        else:
            out["status"] = "ready"
            out.update(week_stats(items, start))
            out["items"] = [{
                "cid": x["cid"],
                "date": day_of(x),
                "actress": x.get("actress") or [],
                "maker": None if (not x.get("maker") or x.get("maker") == "不明") else x["maker"],
                "formats": formats_of(x),
                "duration_min": x["duration_min"] if isinstance(x.get("duration_min"), int)
                and not isinstance(x.get("duration_min"), bool) and x["duration_min"] > 0 else None,
            } for x in rows]
    print(json.dumps(out, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------
# apply
# ------------------------------------------------------------------
def numbers_in(text, names):
    """文章の中の数字（"10月5日" の 10 と 5、"120分" の 120 など）。VR・8K のような英数字のかたまりや、出演者・メーカー名の中の数字は除く"""
    for n in sorted(names, key=len, reverse=True):
        if n:
            text = text.replace(n, " ")
    text = unicodedata.normalize("NFKC", text)
    return {int(m) for m in re.findall(r"(?<![0-9A-Za-z])\d+(?![0-9A-Za-z])", text)}


def allowed_numbers(start, stats, rows, picked_rows):
    """文章に出てきてよい数字: 週の集計の本数、この週の日付（年・月・日）、選んだ作品の収録時間、
    1（「1週間」「1本」などの自然な言い方）、7（7日間）"""
    allowed = {1, 7, len(picked_rows), stats["total"]}
    for key in ("per_day", "makers", "actresses", "formats"):
        allowed.update(r["count"] for r in stats[key])
    for i in range(7):
        d = to_date(add_days(start, i))
        allowed.update({d.year, d.month, d.day})
    for x in rows:
        d = to_date(day_of(x))
        allowed.update({d.year, d.month, d.day})
    for x in picked_rows:
        if isinstance(x.get("duration_min"), int):
            allowed.add(x["duration_min"])
    return allowed


def article_problems(article, items, roundups, today):
    """記事の問題点 [(場所, 理由)]（なければ空）"""
    problems = []

    def add(where, why):
        problems.append((where, why))

    if not isinstance(article, dict):
        return [("全体", '{"week_start": ..., "lead": ..., "picks": [...]} の形にしてください')]
    start = article.get("week_start")
    if not isinstance(start, str) or not DAY_RE.match(start) or week_start_of(start) != start:
        return [("week_start", "月曜日の日付（YYYY-MM-DD）にしてください")]
    if add_days(start, 6) >= today:
        return [("week_start", "この週はまだ終わっていません")]
    if any(r.get("week_start") == start for r in roundups):
        return [("week_start", "この週のまとめ記事はもうあります（上書きしません）")]
    rows = week_items(items, start)
    if len(rows) < MIN_WEEK_ITEMS:
        return [("week_start", f"この週の作品が{MIN_WEEK_ITEMS}本に満たないため、記事は作れません（{len(rows)}本）")]

    by_cid = {x["cid"]: x for x in rows}
    stats = week_stats(items, start)
    names = {n for x in rows for n in (x.get("actress") or [])} | {x["maker"] for x in rows if x.get("maker")}

    lead = article.get("lead")
    if not isinstance(lead, str):
        add("lead", "文字列ではありません")
        lead = ""
    lead = lead.strip()
    for why in cc.text_problems(lead, LEAD_MIN, LEAD_MAX):
        add("lead", why)

    picks = article.get("picks")
    if not isinstance(picks, list) or not (PICKS_MIN <= len(picks) <= PICKS_MAX):
        add("picks", f"注目の作品は{PICKS_MIN}〜{PICKS_MAX}件のリストにしてください")
        picks = []
    seen_cids, seen_notes = set(), {}
    picked_rows = []
    for i, p in enumerate(picks, 1):
        where = f"picks[{i}]"
        if not isinstance(p, dict) or not isinstance(p.get("cid"), str) or not isinstance(p.get("note"), str):
            add(where, '{"cid": ..., "note": ...} の形（どちらも文字列）にしてください')
            continue
        cid, note = p["cid"], p["note"].strip()
        if cid not in by_cid:
            add(where, f"cid「{cid}」はこの週の作品にありません")
            continue
        if cid in seen_cids:
            add(where, f"cid「{cid}」が重複しています")
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

    allowed = allowed_numbers(start, stats, rows, picked_rows)
    for where, text in [("lead", lead)] + [(f"picks[{i}]", p["note"]) for i, p in enumerate(picks, 1)
                                          if isinstance(p, dict) and isinstance(p.get("note"), str)]:
        unknown = sorted(numbers_in(text, names) - allowed)
        if unknown:
            add(where, "一覧にない数字があります（list の数字・日付・収録時間だけを使ってください）: " + "、".join(map(str, unknown)))
    return problems


def read_article(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"❌ 記事のファイルを読めませんでした（{e}）")


def cmd_apply(args):
    today = args.today or jst_today()
    if not DAY_RE.match(today):
        sys.exit("❌ --today は YYYY-MM-DD の形で指定してください")
    article = read_article(args.file)
    items = load_items()
    roundups = load_roundups()

    problems = article_problems(article, items, roundups, today)
    if problems:
        print(f"❌ 問題が {len(problems)} 件あります。何も書き込んでいません。直してもう一度実行してください")
        for where, why in problems:
            print(f"  - {where}: {why}")
        sys.exit(1)

    if args.dry_run:
        print("✅ 問題ありません（--dry-run のため書き込んでいません）")
        return

    entry = {
        "week_start": article["week_start"],
        "lead": article["lead"].strip(),
        "picks": [{"cid": p["cid"], "note": p["note"].strip()} for p in article["picks"]],
        "written": today,
    }
    rows = sorted(roundups + [entry], key=lambda r: r["week_start"], reverse=True)
    save_roundups(rows)
    check = load_roundups()
    if len(check) != len(rows) or check[[r["week_start"] for r in rows].index(entry["week_start"])] != entry:
        sys.exit("❌ 書き込み後の確認に失敗しました。git で変更を取り消してください")
    print(f"✅ {entry['week_start']} 〜 {add_days(entry['week_start'], 6)} のまとめ記事を書き込みました（記事は全部で{len(check)}本）")


def main():
    parser = argparse.ArgumentParser(description="Claude が週のまとめ記事を書くための道具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="書く対象の週と、その週の作品データを出す")
    p_list.add_argument("--week-start", help="対象の週の月曜日 YYYY-MM-DD（省略すると、いちばん新しく終わった週）")
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
