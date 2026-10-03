"""保存データ（site/src/data/new_releases.json）が壊れていないかのチェック

毎日の自動更新や手作業の編集で、サイトが落ちるようなデータが入っていないかを確かめます。
実行: python3 tests/test_data.py
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "site", "src", "data", "new_releases.json")

problems = []


def check(name, cond, detail=""):
    print(("  ✅ " if cond else "  ❌ ") + name + (f"  → {detail}" if (detail and not cond) else ""))
    if not cond:
        problems.append(name)


try:
    with open(DATA, encoding="utf-8") as f:
        raw = json.load(f)
except (OSError, json.JSONDecodeError) as e:
    print(f"  ❌ データを読めません: {e}")
    sys.exit(1)

check("全体が配列(リスト)になっている", isinstance(raw, list))
items = [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []
check("すべて項目(辞書)になっている", len(items) == len(raw))

cids = [str(x.get("cid", "")).strip() for x in items]
check("cid がすべてある", all(cids))
check("cid の重複がない", len(set(cids)) == len(cids), [c for c in set(cids) if cids.count(c) > 1][:5])
check("タイトルがすべてある", all(str(x.get("title", "")).strip() for x in items))
check("発売日が YYYY-MM-DD で始まる", all(re.match(r"^\d{4}-\d{2}-\d{2}", str(x.get("date", ""))) for x in items))
check("コメントがすべてある", all(str(x.get("comment", "")).strip() for x in items))
check("comment_kind は ai か template", all(x.get("comment_kind") in ("ai", "template") for x in items),
      {x.get("comment_kind") for x in items})
jst_tomorrow = (datetime.now(timezone(timedelta(hours=9))) + timedelta(days=1)).strftime("%Y-%m-%d")
check("更新日(updated)がすべてある（YYYY-MM-DD）", all(re.match(r"^\d{4}-\d{2}-\d{2}$", str(x.get("updated", ""))) for x in items),
      [x.get("cid") for x in items if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(x.get("updated", "")))][:5])
check("更新日が未来の日付になっていない（sitemapのlastmodに使うため）", all(str(x.get("updated", "")) <= jst_tomorrow for x in items),
      [x.get("cid") for x in items if str(x.get("updated", "")) > jst_tomorrow][:5])
check("アフィリエイトのURLは https", all(str(x.get("url", "")).startswith("https://") for x in items if x.get("url")))
check("cid はURLに使える文字だけ", all(re.match(r"^[A-Za-z0-9_\-]+$", c) for c in cids), [c for c in cids if not re.match(r"^[A-Za-z0-9_\-]+$", c)][:5])

text = open(DATA, encoding="utf-8").read()
check("APIキーらしき文字列が入っていない", not re.search(r"AIza[0-9A-Za-z_\-]{20,}", text))

# ---- 週のまとめ記事（roundups.json）。Claude が毎週書き足すので、壊れていないかを見張る ----
print("\n■ 週のまとめ記事（roundups.json）")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import claude_comments as cc  # 禁止語・文字の点検は、書き込み時と同じものを使う
import claude_roundups as cr

ROUNDUPS = os.path.join(ROOT, "site", "src", "data", "roundups.json")
try:
    with open(ROUNDUPS, encoding="utf-8") as f:
        rounds = json.load(f)
except (OSError, json.JSONDecodeError) as e:
    print(f"  ❌ roundups.json を読めません: {e}")
    sys.exit(1)

check("roundups.json は配列で、すべて項目(辞書)になっている", isinstance(rounds, list) and all(isinstance(r, dict) for r in rounds))
rounds = [r for r in rounds if isinstance(r, dict)] if isinstance(rounds, list) else []
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
starts = [r.get("week_start") for r in rounds]
check("週の始まり(week_start)がすべて月曜日の日付", all(isinstance(w, str) and DAY.match(w) and cr.week_start_of(w) == w for w in starts), starts[:5])
check("同じ週の記事が重複していない", len(set(starts)) == len(starts))
check("新しい週が先頭に並んでいる", starts == sorted(starts, reverse=True))
check("公開日(written)がすべてあり、その週が終わったあとの日付", all(
    isinstance(r.get("written"), str) and DAY.match(r["written"]) and isinstance(r.get("week_start"), str) and DAY.match(r["week_start"])
    and r["written"] > cr.add_days(r["week_start"], 6) for r in rounds))
check("公開日が未来の日付になっていない", all(str(r.get("written", "")) <= jst_tomorrow for r in rounds))
check("導入文(lead)の文字数・使えない言葉などの点検に通る", all(
    isinstance(r.get("lead"), str) and not cc.text_problems(r["lead"].strip(), cr.LEAD_MIN, cr.LEAD_MAX) for r in rounds),
    [(r.get("week_start"), cc.text_problems(str(r.get("lead", "")).strip(), cr.LEAD_MIN, cr.LEAD_MAX)) for r in rounds][:2])
by_cid_date = {str(x.get("cid", "")).strip(): str(x.get("date", ""))[:10] for x in items}
picks_ok = all(
    isinstance(r.get("picks"), list) and cr.PICKS_MIN <= len(r["picks"]) <= cr.PICKS_MAX
    and all(isinstance(q, dict) and isinstance(q.get("cid"), str) and isinstance(q.get("note"), str) for q in r["picks"])
    for r in rounds)
check("注目の作品(picks)が3〜6件で、cid と note がある", picks_ok)
if picks_ok:
    check("注目の作品がすべて、その週に発売の、データにある作品", all(
        by_cid_date.get(q["cid"], "") >= r["week_start"] and by_cid_date.get(q["cid"], "") <= cr.add_days(r["week_start"], 6)
        for r in rounds for q in r["picks"]), [(r["week_start"], q["cid"]) for r in rounds for q in r["picks"] if q["cid"] not in by_cid_date][:3])
    check("ひとことの文字数・使えない言葉などの点検に通る", all(
        not cc.text_problems(q["note"].strip(), cr.NOTE_MIN, cr.NOTE_MAX) for r in rounds for q in r["picks"]))
    check("注目の作品に同じ作品が2回入っていない", all(len({q["cid"] for q in r["picks"]}) == len(r["picks"]) for r in rounds))
rtext = open(ROUNDUPS, encoding="utf-8").read()
check("roundups.json にAPIキーらしき文字列が入っていない", not re.search(r"AIza[0-9A-Za-z_\-]{20,}", rtext))

print(f"\n  （{len(items)}件の作品データ・{len(rounds)}本のまとめ記事を確認）")
if problems:
    print("失敗:", problems)
    sys.exit(1)
print("=== データ形式 OK ===")
