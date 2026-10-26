#!/usr/bin/env bash
# まとめて確認するコマンド（どこから実行してもOK）
#
#   bash scripts/check.sh             テストだけ（数秒。パソコン/タブレットで手軽に）
#   bash scripts/check.sh --build     テスト + サイトを実際にビルドして点検（Node.js が必要）
#   bash scripts/check.sh --verbose   テストの出力を全部出す（ふだんは、成功は1行ずつ・失敗だけくわしく。scripts/quiet_step.sh）
#
# GitHub Actions（CI）では、記録を残すため、いつも全部出す。
# 1つでも失敗すると、最後に「失敗」と出て終了コード 1 になります。

cd "$(dirname "$0")/.." || exit 1
failed=0
build=0
verbose=0
for arg in "$@"; do
  case "$arg" in
    --build) build=1 ;;
    --verbose|-v) verbose=1 ;;
  esac
done
[ -n "${CI:-}" ] && verbose=1
. scripts/quiet_step.sh

run "毎日の更新スクリプト (Python)" python3 tests/test_script.py

run "Claudeのコメント差し替えの道具 (Python)" python3 tests/test_claude_comments.py

run "Claudeの週のまとめ記事の道具 (Python)" python3 tests/test_claude_roundups.py

run "Claudeの月のまとめ記事の道具 (Python)" python3 tests/test_claude_monthly.py

run "FANZA同人・FANZAゲームを集める道具 (Python)" python3 tests/test_doujin_game.py

run "売り場のセール（キャンペーンごと）を集める道具 (Python)" python3 tests/test_floor_sales.py

run "10円セールを集める道具 (Python)" python3 tests/test_ten_yen.py
run "女優の歩みを集める道具 (Python)" python3 tests/test_actress_history.py

run "FANZAのレビューの評価を集める道具 (Python)" python3 tests/test_reviews.py

run "読みがな（ジャンル・メーカー・シリーズ・作家）を集める道具 (Python)" python3 tests/test_readings.py

run "ジャンルの「FANZA全体で人気の作品」を集める道具 (Python)" python3 tests/test_genre_tops.py

run "公開のしくみ（Cloudflare Pages への直接アップロード）" python3 tests/test_deploy.py

run "検索エンジンへのお知らせ（IndexNow） (Python)" python3 tests/test_indexnow.py

run "AIっぽさゼロの点検（サイトの作りに、AIによく出る絵文字・矢印・言い方が無いか） (Python)" python3 tests/test_ai_style.py

run "保存データの形式" python3 tests/test_data.py

run "トークンを節約する道具（待つ道具・テストの出力・一覧の出力） (Python)" python3 tests/test_tools.py

run "週1回の見張り番 (Python)" python3 tests/test_health.py

run "サイトの部品 (Node.js)" node tests/test_items.mjs

run "品番・作品ページの情報欄・月ごと/ジャンルごとのページの部品 (Node.js)" node tests/test_seo.mjs

run "検索結果に出る説明文（ページごとの数字入り）の部品 (Node.js)" node tests/test_describe.mjs

run "作品ページの「次に見るもの」の部品 (Node.js)" node tests/test_stay.mjs

run "RSS（新着のお知らせの配信）の部品 (Node.js)" node tests/test_feed.mjs

run "人気の動き・シリーズ/レーベル・内部リンクの部品 (Node.js)" node tests/test_insights.mjs

run "週のまとめ記事の部品 (Node.js + Pythonとの突き合わせ)" node tests/test_roundups.mjs

run "月のまとめ記事の部品 (Node.js + Pythonとの突き合わせ)" node tests/test_monthly.mjs

run "サンプル画像の拡大表示 (Node.js)" node tests/test_lightbox.mjs

run "発売日カレンダー (.ics) の部品 (Node.js)" node tests/test_calendar.mjs

run "お気に入りの部品 (Node.js)" node tests/test_favorites.mjs

run "所属事務所・SNSの道具 (Python)" python3 tests/test_agencies.py

run "所属事務所・SNSの部品 (Node.js)" node tests/test_agencies.mjs

run "女優のイベント情報の道具 (Python)" python3 tests/test_events.py
run "女優のイベント情報の部品 (Node.js)" node tests/test_events.mjs

run "出演者プロフィール・売れ筋・出演者検索の部品 (Node.js)" node tests/test_profiles.mjs

run "サンプル動画の枠の部品 (Node.js)" node tests/test_movie.mjs

run "作品検索・「VR作品を隠す」の部品 (Node.js)" node tests/test_search.mjs

run "日本語の文節改行の部品 (Node.js)" node tests/test_phrase.mjs

run "サイトのファイル数の計画（過去作品が増えても2万ファイル以内） (Node.js)" node tests/test_plan.mjs

run "人気順（新着の人気順・全体の人気順）の部品 (Node.js)" node tests/test_popularity.mjs

run "FANZA同人・FANZAゲームのページの部品 (Node.js)" node tests/test_floors.mjs

run "セール・キャンペーンの部品 (Node.js)" node tests/test_sale.mjs

run "10円セールの部品 (Node.js + Pythonとの突き合わせ)" node tests/test_ten_yen.mjs

run "レビューの評価・高評価ランキングの部品 (Node.js + Pythonとの突き合わせ)" node tests/test_reviews.mjs

run "読みがな・50音で探す・ひらがなの作品検索の部品 (Node.js)" node tests/test_kana.mjs
run "トップの「きょうの〜」の部品 (Node.js)" node tests/test_topics.mjs
run "運命の作品の部品 (Node.js)" node tests/test_gacha.mjs

if [ "$build" = 1 ]; then
  if run "サイトのビルド" bash -c 'cd site && npm ci --no-audit --no-fund && npm run build'; then
    run "ビルド結果の点検" python3 tests/verify_dist.py
  fi
fi

find . -name __pycache__ -type d -not -path "./site/node_modules/*" -prune -exec rm -rf {} + 2>/dev/null
rm -rf "$QUIET_LOG_DIR"

echo
if [ "$failed" -eq 0 ]; then
  echo "✅ ぜんぶ成功"
else
  if [ "$verbose" = 1 ]; then
    echo "❌ 失敗があります（上のログを確認）"
  else
    echo "❌ 失敗があります（上の ❌ の行。全部の出力は bash scripts/check.sh --verbose）"
  fi
  exit 1
fi
