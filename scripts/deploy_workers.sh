#!/usr/bin/env bash
# 本番とプレビューを Cloudflare Workers（静的ファイルだけ）に出す（連絡 C-012・issue #188。2026-10-28。設定は workers/wrangler.jsonc）。
#   bash scripts/deploy_workers.sh production
#       本番（main）へ。`wrangler deploy`。https://av-sale-guide.com/ は routes で Workers から出る
#   bash scripts/deploy_workers.sh preview <ブランチ名> [比べる元]
#       PR のプレビューへ（`wrangler versions upload --preview-alias`。本番は変わらない）。
#       URL は https://<ブランチ名を英数字とハイフンにしたもの>-av-sale-guide.juice-juice-0402.workers.dev（注釈と要約に出す）。
#       比べる元（例 HEAD^1）を渡すと、サイトの作り（site/ の中。データ site/src/data/ は除く）が変わっていないときは作らない
# ・Pages は2万ファイルまで。Workers は有料プランで10万まで。2026-10-28（issue #188）から、本番もプレビューも Workers だけに出す
#   （Pages のプロジェクト fanza-ranking は、fanza-ranking.pages.dev → av-sale-guide.com の転送のために残す。戻し方は docs/architecture.md）。
# ・鍵は GitHub の Secrets の CLOUDFLARE_WORKERS_TOKEN（deploy.yml・ci.yml が CLOUDFLARE_API_TOKEN として渡す）。
# ・本番は、出したら workers.dev と本番の URL の __served-by.txt（どこから出ているかの印）で、中身が新しくなったかを確かめる。
#   workers/wrangler.jsonc に routes があるとき（本番が Workers のとき）の失敗は「公開の失敗」。routes が無いあいだの失敗は注意だけ。
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

mode="${1:-}"
branch="${2:-}"
base="${3:-}"
case "$mode" in
  production) ;;
  preview)
    if [ -z "$branch" ]; then echo "プレビューには、ブランチの名前が要ります"; exit 2; fi
    if [ "$branch" = "main" ]; then echo "main はプレビューにできません（本番は production で）"; exit 2; fi
    ;;
  *) echo "使い方: bash scripts/deploy_workers.sh production | preview <ブランチ名> [比べる元]"; exit 2 ;;
esac

# プレビューの名前（alias）: 英小文字・数字・ハイフンだけ（/ や _ などは -）、英字ではじめる、長いときは短くする
# （<alias>-av-sale-guide が URL の1つの区切り＝63文字までに入るように、40文字まで）
preview_alias() {
  local a
  a="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
  case "$a" in [a-z]*) ;; *) a="b-$a" ;; esac
  a="$(printf '%s' "$a" | cut -c1-40 | sed -E 's/-+$//')"
  printf '%s' "$a"
}

if [ "$mode" = "preview" ]; then
  # サイトの作り（site/ の中。データは除く）が変わっていないPRには、プレビューを作らない（本番と同じ見た目になるため）
  if [ -n "$base" ]; then
    if ! changed="$(git diff --name-only "$base" HEAD 2>/dev/null)"; then
      echo "::warning title=プレビュー::変わったファイルを調べられなかったので、プレビューを作ります（比べる元: $base）"
      changed="site/(unknown)"
    fi
    if ! printf '%s\n' "$changed" | grep '^site/' | grep -qv '^site/src/data/'; then
      if [ -n "$changed" ] && ! printf '%s\n' "$changed" | grep -qv '^site/src/data/'; then
        say "### ⏭ データだけの変更なので、プレビューは作りません"
      else
        say "### ⏭ サイトの作り（site/）が変わっていないので、プレビューは作りません"
      fi
      exit 0
    fi
  fi
  if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
    say "### ⏭ Workers の鍵が無いので、プレビューは作りません"
    exit 0
  fi
  if [ ! -f "$DIST/index.html" ]; then
    echo "::warning title=プレビューを作れませんでした::$DIST/index.html がありません（先にビルドしてください）"
    exit 1
  fi
  alias="$(preview_alias "$branch")"
  sha="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  printf '%s\n' "preview ${sha:0:12} ${GITHUB_RUN_ID:-local}" > "$DIST/__served-by.txt"
  files="$(find "$DIST" -type f | wc -l | tr -d ' ')"
  echo "アップロード: $DIST（${files}ファイル）→ Workers のプレビュー（$alias）"
  log="$(mktemp)"
  # shellcheck disable=SC2086  # WRANGLER はコマンドと引数を空白で区切って持つ
  $WRANGLER versions upload --config "$CONFIG" --preview-alias "$alias" --message "preview ${sha:0:7} run ${GITHUB_RUN_ID:-local}" 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  if [ "$rc" -ne 0 ]; then
    reason="$(grep -E 'ERROR|✘|Error' "$log" | head -5 | tr '\n' ' ' | cut -c1-500)"
    rm -f "$log"
    echo "::warning title=プレビューを作れませんでした::${reason:-ログを見てください}"
    exit 1
  fi
  # 名前（alias）つきの URL を先に、そのあとに版ごとの URL
  urls="$(grep -Eo "https://${alias}-[a-z0-9.-]+\.workers\.dev" "$log" | sort -u; grep -Eo 'https://[a-z0-9.-]+\.workers\.dev' "$log" | grep -v "^https://${alias}-" | sort -u)"
  rm -f "$log"
  if [ -z "$urls" ]; then
    echo "::warning title=プレビュー::アップロードはできましたが、URL が出ませんでした（Workers の設定 preview_urls を確かめてください）"
    exit 0
  fi
  say "### 👀 プレビューを作りました（本番は変わりません。${files}ファイル）"
  for u in $urls; do
    say "- $u"
    echo "::notice title=プレビュー::$u"
  done
  exit 0
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
  say "### ⏭ Workers の鍵（CLOUDFLARE_WORKERS_TOKEN）が無いので、Workers には出しません"
  exit 0
fi
if [ ! -f "$DIST/index.html" ]; then
  echo "::error title=公開できません::$DIST/index.html がありません（先にビルドしてください）"
  exit 1
fi

sha="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
mark="workers ${sha:0:12} ${GITHUB_RUN_ID:-local}"
# どこから出ているかの印（本番の URL が Workers から出ているかを、外から確かめるため）
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
# アップロード済みの印（IndexNow で検索エンジンに知らせてよい。scripts/indexnow.py send。下の確認の途中で止められても知らせられるよう、ここで付ける）
if [ -n "${UPLOADED_MARK:-}" ]; then : > "$UPLOADED_MARK"; fi

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
