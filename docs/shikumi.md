# 公開・毎日の仕組み・ページのくわしいこと

CLAUDE.md の「公開」「仕組み」「どこに何があるか」「コマンド」から移したもの（2026-10-30。CLAUDE.md を1万字以内にするため）。
**全部は読まない。** さわる所の節だけ読む。

## 公開（くわしく）

**公開は GitHub Actions が行う**（`deploy.yml`。ビルド → 全ページの点検 `tests/verify_dist.py` → Cloudflare Workers に直接アップロード（2026-10-28 から。前は Pages）。Cloudflare のビルド（月500回を「あそびトーク」と共有）は使わない。2026-10-09 から）。

- **独自ドメイン**（2026-10-22 取得。Cloudflare Registrar・1年・自動更新）: サイト名も「FANZA新作情報」から **FANZAセール情報** に（`config.js` の `SITE_NAME`）。本番は `https://av-sale-guide.com`（`site/src/config.js` の `SITE_URL` 1か所で、URL・canonical・sitemap・robots.txt・RSS・構造化データ・IndexNow が切りかわる）。旧 `https://fanza-ranking.pages.dev` は Cloudflare の Bulk Redirects で同じパスへ 301（プレビューの `<ブランチ名>.fanza-ranking.pages.dev` は転送しない＝サブドメインを含めない）。Search Console は新ドメインのドメインプロパティ＋旧プロパティからアドレス変更。DMM は新しいサイトとして追加（リンクは API 用の `juice0402-990` のまま）
- **検索エンジンへのお知らせ（IndexNow。2026-10-17）**: 本番の公開のたびに `deploy.yml` が `scripts/indexnow.py` で、新しいページ・コメントや記事が入ったページ（一覧・ランキングなどは7日に1回まで）を Bing などへ知らせる（1万件ずつ。前回の記録は本番の `/indexnow-pages.json`。受け付けてもらえなかったページは Actions の置き場（cache）にとっておき、次の公開で送り直す。main にはコミットしない。鍵は `site/public/<鍵>.txt`。Google は sitemap と Search Console のまま。くわしくは docs/architecture.md の「公開」）
- **Workers への引っ越し（連絡 C-012。2026-10-28）**: Pages は有料プランでも2万ファイルまで（本物で確かめた）。本番もプレビューも Workers（静的ファイル10万まで）に出す（`workers/wrangler.jsonc` の `routes` で av-sale-guide.com が Workers から出る・`scripts/deploy_workers.sh`・鍵は Secrets の `CLOUDFLARE_WORKERS_TOKEN`）。Pages には出さない（プロジェクトは pages.dev の転送のために残す）。`FILE_BUDGET` は4万（#188。次に上げるかは11/10 の見直しで）。戻し方は docs/architecture.md の「Workers への引っ越し」

## 毎日・毎週の仕組み（くわしい表）

| いつ | 何が動く | おもに書くデータ（`site/src/data/`） |
|---|---|---|
| 毎日 0:05 | `update.yml`: `get_new_releases.py`（動画の新作・予約（人気順に1日12本・30日先まで）・Gemini の下書き・出演者・名簿・売れ筋・過去作品（人気の上位1万本）・人気の順位・セール・レビュー）→ 所属事務所（週1）・イベント・売り場（同人・ゲーム・アニメ・素人・成人映画・コミック・写真集・VR見放題）・読みがな（週1）・ジャンルの人気TOP20・10円セール → main に commit → `deploy.yml` | `new_releases.json`・`catalog/`・`popularity.json`・`sale.json`・`price_history.json`・`reviews.json`・`actresses.json`・`doujin.json` などの売り場・`ten_yen.json` ほか |
| 毎日 0:20 | Claude の予約タスク: コメントを仕上げる（1日40件。手順は `docs/claude-comments.md`）＋女優の歩みの紹介文を5人（`docs/claude-history.md`。2026-10-27〜） | `new_releases.json`・`catalog/`・売り場のファイル・`actress_stories.json` |
| 毎日 0:35・10:17 | `sale-refresh.yml`: 動画のセールの読み直し（はじめは上位1万本だけ）・10:17 は売り場の集め直し・0:35 は素人/アニメ/成人映画のキャンペーンごと | `sale.json`・`sale_history.json`・`price_history.json`・`floor_sale.json` |
| 毎日 10:12・12:12・16:12・20:12 | `ten-yen.yml`: 10円セールが変わったときだけ保存して公開 | `ten_yen.json` |
| 毎日 4:23 | `actress-history.yml`: 女優の歩み（出演者ごとの全作品を数える。`scripts/actress_history.py`。1回600回まで。公開はしない） | `actress_history.json` |
| 毎週月曜 0:01 | `health.yml`: 見張り番（この7日の更新・公開・コメント・過去作品の数・リポジトリの大きさ。Claude を使わない。おかしいときだけ ⚠️ と GitHub の知らせ） | なし（読むだけ） |
| 毎週月曜 0:50 | Claude の予約タスク: 週のまとめ記事（`docs/claude-roundups.md`）。月が変わって最初の月曜は、月のまとめ記事（`docs/claude-monthly.md`）も同じPRで。読み物を1本（新しいテーマか90日をこえた書き直し。`docs/claude-yomimono.md`）。見張り番の結果も報告 | `roundups.json`・`monthly.json`・`yomimono.json` |

週1回の仕事は、日曜から月曜に日付が変わったあとにそろえる（運営者の希望。2026-10-13）: 所属事務所・読みがなも、月曜 0:05 の毎日の更新で集める（月曜に集められなかったときは7日たった日）。

## ページ（くわしく）

- 読み物 `/yomimono/`（ジャンル・テーマのブログ調の記事＋厳選5本＋自動の棚。`lib/yomimono.js`・データ `yomimono.json`・外す題の言葉は `lib/yomimono-exclude.json` だけ）— 2026-10-28 #181。docs/architecture.md の「読み物」
- 名簿の人の女優のページ（FANZAで50本以上・このサイトに作品が無くても。年表と紹介文がそろうまで noindex）— 2026-10-27 #173。docs/architecture.md の「名簿の人のページ」
- `/sale/ending/`（今週終わるセール）・`/hinban/`（品番の見方。`lib/hinban.js`）— 2026-10-27。くわしくは docs/architecture.md の「セール・キャンペーン」の下
- `/actress/nenpyo/`（女優の年表の一覧。年表のある女優を50音順に・入口は女優検索のページだけ）— 2026-10-27。くわしくは docs/architecture.md の「女優の歩み」
- 作品ページの品番と出演者（説明文の頭・見出しの下の1行・構造化データ Movie・OGP video.movie。出演者がいない作品には何も足さない）— 2026-10-28 #174。docs/architecture.md の `items.js` の節

## site/src/lib（くわしく）

- `site/src/lib/` — 画面に依存しない部品（テストは `tests/test_*.mjs`）。`data.js`（読み込み）・`items.js`（並べ替え・構造化データ・規約の表記）・`plan.js`（ファイル数の計画）・`floors.js`（売り場）・`sale.js`・`ten-yen.js`・`topics.js`（トップ）・`search.js`・`profiles.js`・`insights.js`・`reviews.js`・`kana.js`・`phrase.js`（文節の改行）・`describe.js`（検索結果の説明文。ページのデータの数字から80〜120文字）など

## コマンドの補足

- **Geminiを使わずに、取り直しだけ**したいときは `python get_new_releases.py --refresh-only`（Actions では「Refresh FANZA Data」）。新しい作品の追加もAIコメントもしないので、Geminiの無料枠を使わない。`ACTRESSES_PATH` / `RANKING_PATH` で出演者データ・ランキングの書き込み先も変えられる。
- Claude のクラウド環境では npm が使えない/ビルドが動かないことがある。その場合は `bash scripts/check.sh`（ビルドなし）で確認し、**PRのCIが最初のビルド**になる。コード・デザインのPRなら、CI がプレビュー（`<名前>-av-sale-guide.juice-juice-0402.workers.dev`）も作るので、運営者にスマホで見てもらえる（URL は check の注釈。クラウド環境からは開かない）。見ていないものを「確認した」と書かない。

## ファイル（くわしく）

- `scripts/claude_comments.py`・`claude_roundups.py`・`claude_monthly.py`・`claude_history.py`・`claude_yomimono.py` — Claude がコメント・週/月のまとめ・女優の歩みの紹介文・読み物を書く道具（`list` → 書く → `apply` が点検して書き込む）
- `scripts/doujin_game.py`・`floor_data.py`・`floor_history.py`・`floor_sales.py` — 売り場（同人・ゲーム・アニメ・素人・成人映画・コミック・写真集・VR見放題）を集める・人気の動き・セールの記録・キャンペーンごと
- `scripts/ten_yen.py` — 10円セール ／ `scripts/readings.py` — 読みがな ／ `scripts/genre_tops.py` — ジャンルの人気TOP20
- `scripts/agency_links.py`・`agency_events.py` — 所属事務所とSNS・女優のイベント情報（事務所の公式サイトから。守ること9）
- `scripts/health.py`（`health.yml`）— 週1回の見張り番（毎週月曜 0:01。Claude を使わない。`--last` で結果を1行ずつ）
- `scripts/screens.mjs`（`screens.yml`）— 画面の写真と形のくずれの点検（GitHub の上で撮る）／ `scripts/probe_api.py`（`probe-api.yml`）— API の応答の形を調べる
- `.github/workflows/` — update・sale-refresh・ten-yen・ci・deploy（`scripts/deploy_pages.sh`）・health（見張り番）・refresh-data（取り直しだけ。手動）・probe-api・screens
- `site/public/` — ブラウザで動く小さなスクリプト（作品検索・女優検索・売り場の検索・VR/単体の絞り込み・お気に入り・運命の作品・セール・拡大表示・サンプル動画）と `_headers`・`_redirects`

## コード・デザインのPRのプレビュー

- コード・デザインを変えるPR（`site/` の中。データ `site/src/data/` は除く）は、CI が**プレビュー**（`<ブランチ名を英数字とハイフンにしたもの>-av-sale-guide.juice-juice-0402.workers.dev`。URL は check の注釈と要約）を作る。データだけ・手順書やテストだけのPRには作らない。
