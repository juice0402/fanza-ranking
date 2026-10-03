#!/usr/bin/env python3
"""Claude がAIコメントを書くための道具（Python標準ライブラリだけ）

毎日の更新（get_new_releases.py）で Gemini がコメントを付けられなかった作品は、
定型文（comment_kind: template）のまま保存されます。その定型文を、Claude が書いた
コメントに置き換えるときに使います。手順は docs/claude-comments.md を見てください。

  python3 scripts/claude_comments.py list [--limit 30]
      定型文のままの作品を、コメント作りに必要な情報だけで表示する（作品タイトルは出さない）
  python3 scripts/claude_comments.py apply コメント.json [--dry-run]
      {"cid": "コメント", ...} を点検して、問題が無ければ new_releases.json に書き込む
      （1件でも問題があれば何も書き込まない）

書き込んだコメントは comment_kind を "ai" にし、その作品の updated（更新日）を今日（日本時間）にします
（サイトの注記「AIが自動で作成」の対象。sitemap の lastmod にも使われます）。
Gemini が作ったコメント（すでに "ai"）は上書きしません。
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

MIN_LEN = 40            # コメントの文字数の下限（目安は60〜90文字）
MAX_LEN = 120           # 上限
DEFAULT_LIMIT = 30      # list で一度に出す件数

# 出してはいけない言葉。コメントは出演者・メーカー・形式・発売日だけから書くので、
# 本来は出てこないはずの言葉。うっかり入ったときの安全網です。
EXPLICIT_WORDS = ["中出", "射精", "精液", "挿入", "フェラ", "レイプ", "強姦", "凌辱", "陵辱", "輪姦", "痴漢", "盗撮", "調教"]
MINOR_WORDS = ["未成年", "少女", "ロリ", "児童", "幼", "女子高生", "女子校生", "女子中", "中学生", "高校生", "小学生",
               "JK", "JC", "JS", "制服"]
FORBIDDEN_CHARS = "<>*#"
# コメントは保存したままずっと表示されるので、日がたつと古くなる言い方は使わない（日付で書く）
RELATIVE_TIME_WORDS = ["今日", "本日", "明日", "昨日", "今週", "来週", "先週", "今夜", "今朝", "今月", "来月"]

# list に出す形式タグは、VR / 8K のような英数字だけのものに絞る。
# タグは作品タイトルの【…】から取っているため、日本語のタグには作品の内容を表す言葉が混ざることがある。
FORMAT_TAG = re.compile(r"^[0-9A-Za-z]{1,6}$")


def jst_today():
    return datetime.now(JST).strftime("%Y-%m-%d")


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
def pending_items(items):
    """定型文のままの作品（Gemini が書いたコメントは対象外）"""
    return [x for x in items if x.get("comment_kind") != "ai"]


def cmd_list(args):
    items = load_raw()
    today = args.today or jst_today()
    todo = pending_items(items)
    # 発売済みを新しい順に、そのあとに予約を発売日の近い順に
    released = sorted((x for x in todo if (x.get("date") or "")[:10] <= today),
                      key=lambda x: (x.get("date") or "", x["cid"]), reverse=True)
    upcoming = sorted((x for x in todo if (x.get("date") or "")[:10] > today),
                      key=lambda x: (x.get("date") or "", x["cid"]))
    shown = (released + upcoming)[: max(args.limit, 0)]

    rows = []
    for x in shown:
        maker = x.get("maker")
        minutes = x.get("duration_min")
        rows.append({
            "cid": x["cid"],
            "status": "発売済み" if (x.get("date") or "")[:10] <= today else "予約",
            "date": (x.get("date") or "")[:10],
            "actress": x.get("actress") or [],
            "maker": None if (not maker or maker == "不明") else maker,
            "tags": [t for t in (x.get("tags") or []) if isinstance(t, str) and FORMAT_TAG.match(t)],
            "duration_min": minutes if isinstance(minutes, int) and not isinstance(minutes, bool) and minutes > 0 else None,
        })
    print(json.dumps({"today": today, "total_pending": len(todo), "shown": len(rows), "items": rows},
                     ensure_ascii=False, indent=1))


# ------------------------------------------------------------------
# apply: コメントを点検して書き込む
# ------------------------------------------------------------------
def comment_problems(comment, item):
    """コメント1件の問題点（なければ空のリスト）"""
    if not isinstance(comment, str):
        return ["文字列ではありません"]
    text = comment.strip()
    problems = []
    if "\n" in text or "\r" in text:
        problems.append("改行が入っています")
    if not (MIN_LEN <= len(text) <= MAX_LEN):
        problems.append(f"文字数が {len(text)} 文字です（{MIN_LEN}〜{MAX_LEN}文字にしてください）")
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
    hit = [w for w in EXPLICIT_WORDS + MINOR_WORDS if w.lower() in text.lower()]
    if hit:
        problems.append("使えない言葉があります: " + "、".join(hit))
    for name in item.get("actress") or []:
        if name and text.count(name) > 1:
            problems.append(f"出演者名「{name}」が2回以上入っています（1回まで）")
    if text == (item.get("comment") or "").strip():
        problems.append("いまのコメントと同じです")
    return problems


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
        if item.get("comment_kind") == "ai":
            errors.append((cid, ["すでにAIコメントが付いています（上書きしません）"]))
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

    if args.dry_run:
        print(f"✅ {len(texts)}件、問題ありません（--dry-run のため書き込んでいません）")
        return

    for cid, text in texts.items():
        by_cid[cid]["comment"] = text
        by_cid[cid]["comment_kind"] = "ai"
        by_cid[cid]["updated"] = stamp  # コメントを変えた日（sitemap の lastmod に使う）
    save_raw(items)
    # 書いたものを読み直して確かめる
    check = load_raw()
    ok = len(check) == len(items) and all(x["cid"] == y["cid"] for x, y in zip(check, items))
    if not ok:
        sys.exit("❌ 書き込み後の確認に失敗しました。git で変更を取り消してください")
    left = len(pending_items(check))
    print(f"✅ {len(texts)}件のコメントを書き込みました（定型文のままの作品: 残り{left}件）")


def main():
    parser = argparse.ArgumentParser(description="Claude がAIコメントを書くための道具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="定型文のままの作品を出す")
    p_list.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"出す件数（既定 {DEFAULT_LIMIT}）")
    p_list.add_argument("--today", help="今日の日付 YYYY-MM-DD（テスト用。省略すると日本時間の今日）")
    p_list.set_defaults(func=cmd_list)

    p_apply = sub.add_parser("apply", help="コメントを点検して書き込む")
    p_apply.add_argument("file", help='{"cid": "コメント"} の形のJSONファイル')
    p_apply.add_argument("--dry-run", action="store_true", help="点検だけして書き込まない")
    p_apply.add_argument("--today", help="更新日に入れる日付 YYYY-MM-DD（テスト用。省略すると日本時間の今日）")
    p_apply.set_defaults(func=cmd_apply)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
