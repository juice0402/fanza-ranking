#!/usr/bin/env bash
# できあがったサイト（site/dist）を、Cloudflare Pages に直接アップロードする（Direct Upload。2026-10-09 から）。
# Cloudflare 側のビルド（月500回を「あそびトーク」と共有）を使わないため。ビルドと全ページの点検は GitHub Actions で済ませておく。
#
#   bash scripts/deploy_pages.sh production
#       本番（main）へ。https://fanza-ranking.pages.dev/ が新しくなる
#   bash scripts/deploy_pages.sh preview <ブランチ名> [比べる元]
#       プレビューへ（<ブランチ名>.fanza-ranking.pages.dev。本番は変わらない）。
#       比べる元（例 HEAD^1）を渡すと、サイトの作り（site/ の中。データ site/src/data/ は除く）が変わっていないときは作らない
#       （毎日のコメント・まとめ記事のPR・手順書やテストだけのPR。本番と同じ見た目になるため）
#
# 鍵は GitHub の Secrets（CLOUDFLARE_API_TOKEN・CLOUDFLARE_ACCOUNT_ID）から環境変数で受け取る。ログには出さない。
# 鍵は「Cloudflare Pages の編集」だけの権限（運営者が作った。docs/design-notes.md）。

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

PROJECT="${PAGES_PROJECT:-fanza-ranking}"            # Cloudflare Pages のプロジェクトの名前（URL の fanza-ranking.pages.dev）
DIST="${DIST_DIR:-site/dist}"
WRANGLER="${WRANGLER:-npx --yes wrangler@4}"          # テストでは、にせものに差しかえる
LIVE_URL="${LIVE_URL-https://fanza-ranking.pages.dev}"  # 本番で、公開されたかを確かめる先（空なら確かめない）
CHECK_TRIES="${CHECK_TRIES:-10}"
CHECK_WAIT="${CHECK_WAIT:-15}"
export WRANGLER_SEND_METRICS=false

mode="${1:-}"
branch="${2:-}"
base="${3:-}"

say() {
  echo "$1"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then echo "$1" >> "$GITHUB_STEP_SUMMARY"; fi
}

case "$mode" in
  production) branch="main" ;;
  preview)
    if [ -z "$branch" ]; then echo "プレビューには、ブランチの名前が要ります"; exit 2; fi
    if [ "$branch" = "main" ]; then echo "main はプレビューにできません（本番は production で）"; exit 2; fi
    ;;
  *) echo "使い方: bash scripts/deploy_pages.sh production | preview <ブランチ名> [比べる元]"; exit 2 ;;
esac

# サイトの作り（site/ の中。データは除く）が変わっていないPRには、プレビューを作らない（本番と同じ見た目になるため）
if [ "$mode" = "preview" ] && [ -n "$base" ]; then
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
  if [ "$mode" = "production" ]; then
    echo "::error title=公開できません::GitHub の Secrets に CLOUDFLARE_API_TOKEN と CLOUDFLARE_ACCOUNT_ID がありません"
    exit 1
  fi
  say "### ⏭ Cloudflare の鍵が無いので、プレビューは作りません"
  exit 0
fi

if [ ! -f "$DIST/index.html" ]; then
  echo "::error title=公開できません::$DIST/index.html がありません（先にビルドしてください）"
  exit 1
fi

sha="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
# 説明は英数字だけにする（日本語・記号の入った説明を、Cloudflare が受け付けないことがあるため）
message="${mode} ${sha:0:7} ${GITHUB_EVENT_NAME:-manual} run ${GITHUB_RUN_ID:-local}"
files="$(find "$DIST" -type f | wc -l | tr -d ' ')"
echo "アップロード: $DIST（${files}ファイル）→ $PROJECT（ブランチ $branch）"

log="$(mktemp)"
# shellcheck disable=SC2086  # WRANGLER はコマンドと引数を空白で区切って持つ
$WRANGLER pages deploy "$DIST" --project-name="$PROJECT" --branch="$branch" \
  --commit-hash="$sha" --commit-message="$message" --commit-dirty=true 2>&1 | tee "$log"
rc=${PIPESTATUS[0]}
if [ "$rc" -ne 0 ]; then
  level="error"; title="公開に失敗しました（前の公開のままです）"
  if [ "$mode" = "preview" ]; then level="warning"; title="プレビューを作れませんでした"; fi
  reason="$(grep -E 'ERROR|✘|Error' "$log" | head -5 | tr '\n' ' ' | cut -c1-500)"
  echo "::${level} title=${title}::${reason:-ログを見てください}"
  rm -f "$log"
  exit 1
fi

urls="$(grep -Eo "https://[a-z0-9.-]+\.${PROJECT}\.pages\.dev" "$log" | sort -u)"
rm -f "$log"

if [ "$mode" = "preview" ]; then
  say "### 👀 プレビューを作りました（本番は変わりません）"
  for u in $urls; do
    say "- $u"
    echo "::notice title=プレビュー::$u"
  done
  exit 0
fi

say "### ✅ 本番に公開しました（${files}ファイル）"

# 本当に新しくなったかを確かめる（sitemap.xml が、いま作ったものと同じになるまで待つ）。
# 同じにならなくても失敗にはしない（Cloudflare の側で少し遅れることがあるため）。注意書きだけ出す
if [ -n "$LIVE_URL" ] && [ -f "$DIST/sitemap.xml" ]; then
  want="$(sha256sum "$DIST/sitemap.xml" | cut -d' ' -f1)"
  for i in $(seq 1 "$CHECK_TRIES"); do
    got="$(curl -fsS --max-time 20 "${LIVE_URL}/sitemap.xml?cb=$(date +%s)" 2>/dev/null | sha256sum | cut -d' ' -f1)"
    if [ "$got" = "$want" ]; then
      say "- ${LIVE_URL}/ で、新しい中身になったのを確かめました"
      exit 0
    fi
    [ "$i" -lt "$CHECK_TRIES" ] && sleep "$CHECK_WAIT"
  done
  echo "::warning title=公開の確認::${LIVE_URL}/sitemap.xml が、まだ新しい中身になっていません（しばらくして見てください）"
  say "- ⚠️ ${LIVE_URL}/ が、まだ新しい中身になっていません"
fi
exit 0
