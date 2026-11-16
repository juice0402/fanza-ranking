# 地図（コードを直す前にここから）

使い方: この地図 → `grep -n` で関数名や文字を検索 → 見つかった所の前後だけ Read（offset/limit）→ Edit で変わる所だけ直す（claude/code-rules.md）。ファイルごとの決まりは docs/architecture.md の、そのファイルの節。行の目安は 2026-11-16 のもの（大きくずれたら直す）。

## フォルダ

- `get_new_releases.py` — 毎日の更新の本体（FANZA API・Gemini の下書き・出演者・過去作品・人気・セール・レビュー）
- `scripts/` — Claude が書く道具 `claude_*.py`（`list` → 書く → `apply`）、売り場 `doujin_game.py`・`floor_*.py`、`ten_yen.py`・`readings.py`・`genre_tops.py`・`agency_*.py`・`actress_history.py`、見張り `health.py`・`mihari.py`、マージの印 `merge_ok.py`、公開 `deploy_workers.sh`・`indexnow.py`、待つ `wait_run.py`、テスト一式 `check.sh`
- `site/` — Astro のサイト。`src/config.js`（設定）・`src/lib/`（画面に依存しない部品）・`src/pages/`・`src/components/`・`src/layouts/Base.astro`・`src/styles/site.css`・`public/`（ブラウザの小さなスクリプト）
- `tests/` — `test_*.py`・`test_*.mjs`・`verify_dist.py`（ビルド後の全ページ点検）・`fixtures/`
- `.github/workflows/` — update・sale-refresh・ten-yen・actress-history・ci・deploy・health・mihari・merge-ok・refresh-data・probe-api・screens
- `workers/wrangler.jsonc` — Cloudflare Workers の設定
- `docs/` — 予約タスクの手順書 `claude-*.md`・`architecture.md`・`shikumi.md`・`kimari.md`・`design.md`・`design-notes.md`（どれも大きいので検索して節だけ）

## 大きいファイル（300行より大きいもの。見出しと行の目安）

- `get_new_releases.py`（約2,600行）: 秘密の値 45・名簿 79・`build_prompt` 285・`ask_gemini` 382・`call_api` 600・`parse_api_item` 776・`refetch_by_cid` 912・出演者 `collect_actresses` 1067・`update_directory` 1258・セール `sale_active` 1366〜`merge_price_history` 1784・`run_sales_only` 1658・順位 `save_rank_history` 2035・`save_today` 2294・`main` 2362
- `tests/verify_dist.py`（約3,900行）: ページごとの点検の関数がならぶ。点検の言葉で検索する
- `site/src/styles/site.css`（約7,200行）: `/* ` のコメントが節の見出し。部品のクラス名で検索する
- `site/src/lib/floors.js`（約1,200行）: `FLOORS` 19・`normalizeFloor` 109・`FLOOR_THEMES` 441・`normalizeFloorSale` 796・`floorSearchIndex` 1139
- `site/src/lib/items.js`（約770行）: パス 69〜81・表紙 157〜245・`splitByRelease` 308・`buildRobots` 423・`itemPageDescription` 498・メーカー 537〜664・`DMM_CREDIT_HTML` 543
- `scripts/claude_comments.py`（約900行）: `cmd_list` 456・`cmd_apply` 747・`main` 881
- `scripts/claude_yomimono.py`（約1,000行）: `cmd_list` 476・`cmd_themes` 508・`cmd_apply` 943
- そのほか 300〜1,000行: `scripts/probe_api.py`・`claude_roundups.py`・`agency_links.py`・`agency_events.py`・`ten_yen.py`・`site/public/search.js`・`actress-search.js`・`favorites.js`・`site/src/lib/sale.js`・`profiles.js`・`components/ItemPage.astro`。テストの `tests/test_script.py`・`test_data.py`・`test_claude_comments.py` も大きい

## データの場所

- `site/src/data/` — 自動で作るデータ（読まない・手で直さない。書く道具が決まっている）: 作品 `new_releases.json`・過去作品 `catalog/`・売り場 `doujin.json` など・セール `sale.json`・人気 `popularity.json`・出演者 `actresses.json`・まとめ `roundups.json`・`monthly.json`・読み物 `yomimono.json` ほか。形は docs/architecture.md の、そのファイルの節
- 作品の件数・サイト名・URL・ファイル数の上限は `site/src/config.js`、取得の件数は `get_new_releases.py` 冒頭の定数

## ビルド・テスト・公開

- テスト: `bash scripts/check.sh`。ビルドと全ページ点検: `bash scripts/check.sh --build`
- 公開: main に入ると `deploy.yml`（ビルド → `tests/verify_dist.py` → Workers）。待つのは `python3 scripts/wait_run.py`

## 自動で作るもの（読まない・手で直さない）

- `site/src/data/` の全部・`site/dist/`・`site/package-lock.json`・`site/src/lib/budoux-ja.js`（外の部品）
