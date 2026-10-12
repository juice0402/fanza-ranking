# scripts/check.sh が読みこむ、テストを1つずつ動かす部品（bash の source 用。単独では動かさない）。
#
# ふだん（静かなとき）は、成功したテストは1行（✅ 名前）だけ、失敗したテストだけ、❌ の行と出力の後ろを出す。
# Claude がテストの全部の出力（25万文字ほど）を毎回読まずに済むように（運営者の希望「クロードのトークンをできるだけ節約したい」。2026-10-13）。
# verbose=1 のとき（--verbose・GitHub Actions）は、前と同じく全部出す。
#
#   run "名前" コマンド 引数…    成功なら 0、失敗なら 1 を返し、failed=1 にする
# テストは tests/test_tools.py

QUIET_LOG_DIR="${QUIET_LOG_DIR:-$(mktemp -d)}"
QUIET_TAIL="${QUIET_TAIL:-25}"
quiet_n=0

run() {
  local title="$1"
  shift
  if [ "${verbose:-0}" = 1 ]; then
    echo
    echo "━━ $title"
    "$@" || { failed=1; return 1; }
    return 0
  fi
  quiet_n=$((quiet_n + 1))
  local log="$QUIET_LOG_DIR/$quiet_n.log"
  if "$@" >"$log" 2>&1; then
    echo "✅ $title"
    return 0
  fi
  failed=1
  echo "❌ $title"
  # 失敗した点検の行（❌）を先に。そのあと、出力の後ろ（エラーの理由が出ることが多い）
  grep -F "❌" "$log" | head -n 20 | sed 's/^/   /'
  echo "   ……（出力の後ろ${QUIET_TAIL}行。全部見るときは --verbose）"
  tail -n "$QUIET_TAIL" "$log" | sed 's/^/   /'
  return 1
}
