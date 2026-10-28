#!/usr/bin/env bash
# 本番を Cloudflare Workers（静的ファイルだけ）にも出す（連絡 C-012。2026-10-28。設定は workers/wrangler.jsonc）。
# 使い方: bash scripts/deploy_workers.sh production
# ・Pages（scripts/deploy_pages.sh）は2万ファイルまで。Workers は有料プランで10万まで。引っ越しのあいだは両方に出す。
# ・鍵は GitHub の Secrets の CLOUDFLARE_WORKERS_TOKEN（deploy.yml が CLOUDFLARE_API_TOKEN として渡す）。無ければ何もしない（Pages だけで公開）。
# ・出したら、workers.dev で中身が新しくなったかを確かめる。workers/wrangler.jsonc に routes があるとき（av-sale-guide.com の前に置いたあと）は、
#   本番の URL が Workers から出ているか（__served-by.txt）も確かめ、失敗は「公開の失敗」にする。routes が無いあいだの失敗は注意だけ（本番は Pages のまま）。
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

CONFIG="${WORKERS_CONFIG:-workers/wrangler.jsonc}"
DIST="${DIST_DIR:-site/dist}"
WRANGLER="${WRANGLER:-npx --yes wrangler@4}"         # テストでは、にせものに差しかえる
LIVE_URL="${LIVE_URL-https://av-sale-guide.com}"
CHECK_TRIES="${CHECK_TRIES:-10}"
CHECK_WAIT="${CHECK_WAIT:-15}"
export WRANGLER_SEND_METRICS=false

say() {
  echo "$1"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then echo "$1" >> "$GITHUB_STEP_SUMMARY"; fi
}

if [ "${1:-}" != "production" ]; then
  echo "使い方: bash scripts/deploy_workers.sh production"
  exit 2
fi

# routes があれば、本番の URL はもう Workers から出ている（失敗をそのままにできない）
routed=0
if grep -Eq '^[[:space:]]*"routes"[[:space:]]*:' "$CONFIG"; then routed=1; fi
fail() {
  if [ "$routed" = "1" ]; then
    echo "::error title=Workers への公開に失敗しました（前の公開のままです）::$1"
    exit 1
  fi
  echo "::warning title=Workers への公開（ためし）::$1（本番は Pages のままなので、サイトは止まっていません）"
  exit 0
}

if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  if [ "$routed" = "1" ]; then
    echo "::error title=公開できません::GitHub の Secrets に CLOUDFLARE_WORKERS_TOKEN がありません（本番は Workers から出ています）"
    exit 1
  fi
  say "### ⏭ Workers の鍵（CLOUDFLARE_WORKERS_TOKEN）が無いので、Workers には出しません（本番は Pages）"
  exit 0
fi
if [ ! -f "$DIST/index.html" ]; then
  echo "::error title=公開できません::$DIST/index.html がありません（先にビルドしてください）"
  exit 1
fi

sha="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
mark="workers ${sha:0:12} ${GITHUB_RUN_ID:-local}"
# どこから出ているかの印（本番の URL が Workers に切りかわったかを、外から確かめるため。Pages へのアップロードのあとで作る）
printf '%s\n' "$mark" > "$DIST/__served-by.txt"
files="$(find "$DIST" -type f | wc -l | tr -d ' ')"
echo "アップロード: $DIST（${files}ファイル）→ Workers（$CONFIG）"

log="$(mktemp)"
$WRANGLER deploy --config "$CONFIG" --message "production ${sha:0:7} run ${GITHUB_RUN_ID:-local}" 2>&1 | tee "$log"
rc=${PIPESTATUS[0]}
if [ "$rc" -ne 0 ]; then
  reason="$(grep -E 'ERROR|✘|Error' "$log" | head -5 | tr '\n' ' ' | cut -c1-500)"
  rm -f "$log"
  fail "${reason:-ログを見てください}"
fi
dev_url="$(grep -Eo 'https://[a-z0-9.-]+\.workers\.dev' "$log" | head -1)"
rm -f "$log"
say "### ✅ Workers に出しました（${files}ファイル）"

# workers.dev で、新しい中身になったか（印のファイルと sitemap）
if [ -n "$dev_url" ]; then
  ok=0
  for i in $(seq 1 "$CHECK_TRIES"); do
    got="$(curl -fsS --max-time 20 "${dev_url}/__served-by.txt?cb=$(date +%s)" 2>/dev/null | tr -d '\r\n')"
    if [ "$got" = "$mark" ]; then ok=1; break; fi
    [ "$i" -lt "$CHECK_TRIES" ] && sleep "$CHECK_WAIT"
  done
  if [ "$ok" = "1" ]; then
    say "- ${dev_url}/ で、新しい中身になったのを確かめました"
  else
    fail "${dev_url}/ が、まだ新しい中身になっていません"
  fi
fi

# 本番の URL が Workers から出ているか（routes を足したあとだけ）
if [ "$routed" = "1" ] && [ -n "$LIVE_URL" ]; then
  for i in $(seq 1 "$CHECK_TRIES"); do
    got="$(curl -fsS --max-time 20 "${LIVE_URL}/__served-by.txt?cb=$(date +%s)" 2>/dev/null | tr -d '\r\n')"
    if [ "$got" = "$mark" ]; then
      say "- ${LIVE_URL}/ が Workers から出ているのを確かめました"
      exit 0
    fi
    [ "$i" -lt "$CHECK_TRIES" ] && sleep "$CHECK_WAIT"
  done
  echo "::warning title=公開の確認::${LIVE_URL}/ が、まだ Workers の新しい中身になっていません（しばらくして見てください）"
  say "- ⚠️ ${LIVE_URL}/ が、まだ Workers の新しい中身になっていません"
fi
exit 0
