#!/usr/bin/env bash
# 今日（日本時間）の「データ更新」が、もう記録（コミット）に入っているかを調べる。
#   入っていれば 0、まだなら 1 で終わる（画面に、どちらかを日本語で出す）。
#
# 使う所:
#   (1) 毎日の更新（.github/workflows/update.yml）の定時実行。GitHub の定時実行は、混んでいると数時間遅れることがある
#       （2026-10-04 は 0:05 の予定が 3:58 に動いた）。その間に Claude の予約タスクが更新を動かしていたら、
#       遅れて来た定時実行は何もしない（Gemini の無料枠を二重に使わないため）
#   (2) Claude の予約タスク（毎日 0:20。docs/claude-comments.md）が、更新が済んでいるかを確かめる
#
# 使い方: bash scripts/already_updated.sh [調べる記録。省略すると HEAD]   例: bash scripts/already_updated.sh origin/main
# 最近50件の記録だけを見る。TODAY=YYYY-MM-DD で「今日」を変えられる（テスト用）
set -u
today="${TODAY:-$(TZ=Asia/Tokyo date +%Y-%m-%d)}"
ref="${1:-HEAD}"
if ! subjects=$(git log -n 50 --format=%s "$ref" 2>/dev/null); then
  echo "記録（${ref}）を読めませんでした。まだ済んでいないものとして扱います"
  exit 1
fi
if printf '%s\n' "$subjects" | grep -qxF "データ更新: ${today}"; then
  echo "今日（${today}）のデータ更新は済んでいます"
  exit 0
fi
echo "今日（${today}）のデータ更新は、まだです"
exit 1
