#!/usr/bin/env python3
"""Claude が「女優の歩み」の紹介文を書くための道具（Python標準ライブラリだけ。運営者の希望「紹介文いいじゃん」。2026-10-27）

女優のページの「歩み」（年表）のいちばん上に出す、2〜3文の紹介文を、Claude が数字だけを使って書きます。
数字は scripts/actress_history.py が FANZA公式のAPIで数えたもの（actress_history.json）。手順と書き方は docs/claude-history.md。

  python3 scripts/claude_history.py list [--limit 5] [--today YYYY-MM-DD]
      まだ紹介文の無い人（このサイトの本数が多い順）→ 書いてから数字が集め直された人（90日より前に書いた人）を、
      書いてよい数字（facts）と一緒に表示する。作品のタイトルは出さない
  python3 scripts/claude_history.py apply 紹介文.json [--dry-run] [--today YYYY-MM-DD]
      [{"name": "...", "text": "..."}] を点検して、問題が無ければ site/src/data/actress_stories.json に書き込む
      （1件でも問題があれば何も書き込まない）

点検: 文字数（STORY_MIN〜STORY_MAX）・コメントと同じ禁止語や記号（claude_comments.text_problems）・あおり言葉・
facts に無い数字・「デビュー」と言い切る言い方・私生活や確かめられないこと（結婚・引退・本名・出身・うわさ など）・
ほかの人の紹介文と同じ書き出し。

保存先: site/src/data/actress_stories.json（環境変数 ACTRESS_STORIES_PATH で変えられる）
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claude_comments as cc  # noqa: E402  禁止語・文字の点検（コメントと同じルール）を使い回す

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "site", "src", "data")
HISTORY_PATH = os.environ.get("ACTRESS_HISTORY_PATH", os.path.join(DATA_DIR, "actress_history.json"))
STORIES_PATH = os.environ.get("ACTRESS_STORIES_PATH", os.path.join(DATA_DIR, "actress_stories.json"))
JST = timezone(timedelta(hours=9))
STORY_MIN = 90
STORY_MAX = 200
REWRITE_DAYS = 90  # この日数より前に書いた紹介文は、数字が集め直されていれば書き直す
DEFAULT_LIMIT = 5  # 1日に書く人数（運営者と決めた。2026-10-27）
OPENING_LEN = 8  # 書き出しのこの文字数が、ほかの人の紹介文と同じなら断る（似た文章の量産にしない）
# 書かないこと（FANZAの数字では確かめられない・私生活にかかわる）。「デビュー」は「FANZAでいちばん古い作品」と書く（配信より前の作品があるため）
NOT_FACT_WORDS = ["デビュー", "引退", "卒業", "休業", "活動休止", "復帰", "結婚", "妊娠", "出産", "本名", "出身", "年齢", "歳", "噂", "うわさ", "私生活",
                  "事務所", "移籍", "専属", "女優になる前", "No.1", "ナンバーワン", "トップ女優", "人気女優", "看板", "代表作", "伝説", "レジェンド"]


def jst_today():
    return datetime.now(JST).strftime("%Y-%m-%d")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def history_rows():
    rows = (load_json(HISTORY_PATH, {}) or {}).get("actresses") or {}
    return {r["name"]: r for r in rows.values() if isinstance(r, dict) and r.get("name") and int(r.get("total") or 0) > 0 and isinstance(r.get("first"), dict)}


def load_stories():
    return (load_json(STORIES_PATH, {}) or {}).get("stories") or {}


def facts_of(r):
    """書いてよい事実（タイトルは入れない。メーカー・共演者の名前と数字だけ）"""
    first, latest = r.get("first") or {}, r.get("latest") or {}
    return {
        "name": r["name"],
        "checked": r.get("checked"),
        "total": r.get("total"),
        "upcoming": r.get("upcoming", 0),
        "first": {"date": first.get("d"), "maker": first.get("m")},
        "latest": {"date": latest.get("d"), "maker": latest.get("m")},
        "years": {y: {"n": v.get("n"), "makers": v.get("m") or []} for y, v in (r.get("years") or {}).items()},
        "makers": [{"maker": m.get("m"), "n": m.get("n"), "first": m.get("f")} for m in r.get("makers") or []],
        "milestones": [{"n": m.get("n"), "date": m.get("d"), "maker": m.get("m")} for m in r.get("milestones") or []],
        "vr": {"n": r["vr"]["n"], "first_date": (r["vr"].get("first") or {}).get("d")} if r.get("vr") else None,
        "best": r.get("best", 0),
        "solo": r.get("solo", 0),
        "costars": r.get("costars") or [],
        "genres": r.get("genres") or [],
    }


def site_counts():
    """このサイトの作品の、出演者ごとの本数（書く順番に使う）"""
    counts = Counter()
    paths = [os.path.join(DATA_DIR, "new_releases.json")]
    cat = os.path.join(DATA_DIR, "catalog")
    if os.path.isdir(cat):
        paths += [os.path.join(cat, n) for n in sorted(os.listdir(cat)) if n.endswith(".json")]
    for p in paths:
        raw = load_json(p, [])
        for it in raw if isinstance(raw, list) else raw.get("items") or []:
            for name in set(it.get("actress") or []):
                counts[name] += 1
    return counts


def pick(rows, stories, today, limit=DEFAULT_LIMIT, counts=None):
    """まだ紹介文の無い人（このサイトの本数が多い順）→ 90日より前に書いて、そのあと数字が集め直された人（書いた日が古い順）"""
    counts = counts if counts is not None else site_counts()
    old = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=REWRITE_DAYS)).strftime("%Y-%m-%d")
    fresh = sorted((n for n in rows if n not in stories), key=lambda n: (-counts.get(n, 0), n))
    stale = sorted((n for n, s in stories.items() if n in rows and str(s.get("written") or "") < old and str(rows[n].get("checked") or "") > str(s.get("written") or "")),
                   key=lambda n: (stories[n].get("written") or "", n))
    return (fresh + stale)[:limit]


def allowed_numbers(f):
    """紹介文に出てきてよい数字: 本数・年・月・日（事実の日付から）・何本目・メーカーごとの本数・共演の本数・ジャンルの本数、
    数えた年の数（「8年」など）、1〜3（「1本」「2社」「3人」などの自然な言い方）"""
    allowed = {1, 2, 3}
    for v in (f["total"], f["upcoming"], f["best"], f["solo"]):
        if isinstance(v, int):
            allowed.add(v)
    dates = [f["first"]["date"], f["latest"]["date"]] + [m["first"] for m in f["makers"]] + [m["date"] for m in f["milestones"]]
    if f["vr"]:
        allowed.add(f["vr"]["n"])
        dates.append(f["vr"]["first_date"])
    for d in dates:
        if d and re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            allowed.update({int(d[:4]), int(d[5:7]), int(d[8:10])})
    years = sorted(int(y) for y in f["years"])
    for y, v in f["years"].items():
        allowed.update({int(y), v["n"]})
        allowed.update(n for _, n in v["makers"])
    if years:
        allowed.update({years[-1] - years[0] + 1, years[-1] - years[0], len(years)})
    allowed.update(m["n"] for m in f["makers"])
    allowed.update(m["n"] for m in f["milestones"])
    allowed.update(n for _, n in f["costars"])
    allowed.update(n for _, n in f["genres"])
    allowed.add(len(f["makers"]))
    return allowed


def numbers_in(text, names):
    """文章の中の数字（名前の中の数字・VR や 8K のような英数字のかたまりは除く。「1,234本」のかんまは外す）"""
    for n in sorted(names, key=len, reverse=True):
        if n:
            text = text.replace(n, " ")
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    return {int(m) for m in re.findall(r"(?<![0-9A-Za-z])\d+(?![0-9A-Za-z])", text)}


def story_problems(name, text, rows, stories):
    """1人分の紹介文の問題点（なければ空）"""
    if name not in rows:
        return [f"{name}: 歩みのデータがありません（list に出た名前で書いてください）"]
    if not isinstance(text, str):
        return [f"{name}: text が文字列ではありません"]
    problems = [f"{name}: {why}" for why in cc.text_problems(text, STORY_MIN, STORY_MAX)]
    hype = [w for w in cc.HYPE_WORDS if w in text]
    if hype:
        problems.append(f"{name}: あおる言葉があります（数字で書いてください）: " + "、".join(hype))
    nf = [w for w in NOT_FACT_WORDS if w in text]
    if nf:
        problems.append(f"{name}: FANZAの数字で確かめられない・私生活にかかわる言葉があります（「デビュー」は「FANZAでいちばん古い作品」と書く）: " + "、".join(nf))
    f = facts_of(rows[name])
    short = re.sub(r"（[^）]*）", "", name).strip() or name  # 「河北彩花（河北彩伽）」は「河北彩花」と書いてよい
    names = [name, short] + [m["maker"] for m in f["makers"] if m["maker"]] + [c for c, _ in f["costars"]] + [g for g, _ in f["genres"]]
    names += [m for v in f["years"].values() for m, _ in v["makers"]]
    extra = sorted(numbers_in(text, names) - allowed_numbers(f))
    if extra:
        problems.append(f"{name}: list の facts に無い数字があります: {extra}")
    if short not in text:
        problems.append(f"{name}: 紹介文に名前を入れてください（「{short}さん」）")
    opening = text[:OPENING_LEN]
    same = [n for n, s in stories.items() if n != name and str(s.get("text") or "")[:OPENING_LEN].replace(n, name) == opening]
    if same:
        problems.append(f"{name}: 書き出しが、ほかの人の紹介文と同じです（{same[0]}）。書き出しを変えてください")
    return problems


def cmd_list(args):
    today = args.today or jst_today()
    rows, stories = history_rows(), load_stories()
    names = pick(rows, stories, today, args.limit)
    out = {"today": today, "count": len(names), "length": [STORY_MIN, STORY_MAX], "actresses": [facts_of(rows[n]) for n in names]}
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_apply(args):
    today = args.today or jst_today()
    try:
        items = json.load(open(args.file, encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"❌ 読めません: {e}")
    if not isinstance(items, list) or not items:
        sys.exit("❌ [{\"name\": \"...\", \"text\": \"...\"}] の形にしてください")
    rows, stories = history_rows(), load_stories()
    problems, seen = [], set()
    pending = dict(stories)
    for it in items:
        name = (it or {}).get("name") if isinstance(it, dict) else None
        if not name or name in seen:
            problems.append(f"名前が無い・同じ名前が2回あります: {name}")
            continue
        seen.add(name)
        text = str(it.get("text") or "").strip()
        problems += story_problems(name, text, rows, pending)
        pending[name] = {"text": text, "written": today, "checked": rows.get(name, {}).get("checked", "")}
    if problems:
        print("❌ 書き込みませんでした:")
        for p in problems:
            print("  - " + p)
        sys.exit(1)
    if args.dry_run:
        print(f"✅ 問題ありません（{len(items)}人。--dry-run のため書き込んでいません）")
        return
    data = load_json(STORIES_PATH, {}) or {}
    data["stories"] = pending
    data["updated"] = today
    save_json(STORIES_PATH, data)
    print(f"✅ {len(items)}人の紹介文を書き込みました（全部で {len(pending)}人）")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.add_argument("--today")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("apply")
    p.add_argument("file")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--today")
    p.set_defaults(func=cmd_apply)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
