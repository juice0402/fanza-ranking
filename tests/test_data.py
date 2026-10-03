"""保存データ（site/src/data/new_releases.json）が壊れていないかのチェック

毎日の自動更新や手作業の編集で、サイトが落ちるようなデータが入っていないかを確かめます。
実行: python3 tests/test_data.py
"""
import json
import os
import re
import sys

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
check("アフィリエイトのURLは https", all(str(x.get("url", "")).startswith("https://") for x in items if x.get("url")))
check("cid はURLに使える文字だけ", all(re.match(r"^[A-Za-z0-9_\-]+$", c) for c in cids), [c for c in cids if not re.match(r"^[A-Za-z0-9_\-]+$", c)][:5])

text = open(DATA, encoding="utf-8").read()
check("APIキーらしき文字列が入っていない", not re.search(r"AIza[0-9A-Za-z_\-]{20,}", text))

print(f"\n  （{len(items)}件のデータを確認）")
if problems:
    print("失敗:", problems)
    sys.exit(1)
print("=== データ形式 OK ===")
