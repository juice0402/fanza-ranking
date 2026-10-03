#!/usr/bin/env bash
# まとめて確認するコマンド（どこから実行してもOK）
#
#   bash scripts/check.sh           テストだけ（数秒。パソコン/タブレットで手軽に）
#   bash scripts/check.sh --build   テスト + サイトを実際にビルドして点検（Node.js が必要）
#
# 1つでも失敗すると、最後に「失敗」と出て終了コード 1 になります。

cd "$(dirname "$0")/.." || exit 1
failed=0

step() { echo; echo "━━ $1"; }

step "毎日の更新スクリプト (Python)"
python3 tests/test_script.py || failed=1

step "Claudeのコメント差し替えの道具 (Python)"
python3 tests/test_claude_comments.py || failed=1

step "Claudeの週のまとめ記事の道具 (Python)"
python3 tests/test_claude_roundups.py || failed=1

step "保存データの形式"
python3 tests/test_data.py || failed=1

step "サイトの部品 (Node.js)"
node tests/test_items.mjs || failed=1

step "週のまとめ記事の部品 (Node.js + Pythonとの突き合わせ)"
node tests/test_roundups.mjs || failed=1

step "サンプル画像の拡大表示 (Node.js)"
node tests/test_lightbox.mjs || failed=1

step "発売日カレンダー (.ics) の部品 (Node.js)"
node tests/test_calendar.mjs || failed=1

step "お気に入りの部品 (Node.js)"
node tests/test_favorites.mjs || failed=1

if [ "${1:-}" = "--build" ]; then
  step "サイトのビルド"
  if (cd site && npm ci --no-audit --no-fund && npm run build); then
    step "ビルド結果の点検"
    python3 tests/verify_dist.py || failed=1
  else
    failed=1
  fi
fi

find . -name __pycache__ -type d -not -path "./site/node_modules/*" -prune -exec rm -rf {} + 2>/dev/null

echo
if [ "$failed" -eq 0 ]; then
  echo "✅ ぜんぶ成功"
else
  echo "❌ 失敗があります（上のログを確認）"
  exit 1
fi
