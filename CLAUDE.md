# CLAUDE.md — このリポジトリで開発するときの案内

FANZAの新作・予約作品を毎日自動で集め、AIのひとことコメントを添えて公開するアフィリエイトブログ。
公開先: https://fanza-ranking.pages.dev/ （リポジトリは **public**）

運営者はコードに詳しくない。説明は専門用語を避けた平易な日本語で、手順は1手ずつ示す。
開発は「Claude に頼む → ブランチ+プルリクエスト → Cloudflareのプレビューで確認 → 運営者が Merge」の1本道（ターミナル操作は不要）。

## 仕組み（データの流れ）

```
GitHub Actions（毎日 01:00 JST）
  → get_new_releases.py
      FANZA(DMM) アフィリエイトAPI から「発売済み」「予約」を別々に取得
      Gemini でひとことコメント作成（ブロック時は代替文 → 次回再挑戦）
      → site/src/data/new_releases.json に作品IDごとにためていく
  → main に commit → Cloudflare Pages が自動ビルド（Astro, 静的サイト）→ 公開
```

## フォルダ

| 場所 | 役割 |
|---|---|
| `get_new_releases.py` | 毎日の更新スクリプト。Python標準ライブラリだけ（pip不要） |
| `site/` | サイト本体（Astro 7 / 静的出力）。Cloudflare Pages のビルド対象 |
| `site/src/config.js` | **サイト名・URL・表示件数の設定はここだけ**（独自ドメイン化もここ） |
| `site/src/lib/items.js` | 並べ替え・日付・sitemap/robots など、テストできる部品（画面に依存しない） |
| `site/src/lib/data.js` | JSON読み込み。`released`/`upcoming`/`all` を各ページに渡す |
| `site/src/pages/` | トップ、`item/[cid]`（作品）、`archive/[page]`（過去作品）、404、`sitemap.xml.js`、`robots.txt.js` |
| `site/src/data/new_releases.json` | **自動更新のデータ。手で編集しない**（作品IDごとに蓄積） |
| `tests/` | テスト一式。`fixtures/` は固定データ（本番データには依存しない） |
| `scripts/check.sh` | テストをまとめて実行（`--build` でビルドと点検まで） |
| `.github/workflows/` | `update.yml`（毎日の更新）、`ci.yml`（PRごとの自動確認） |
| `docs/design-notes.md` | デザインの考え方、API/Geminiで学んだ注意点、今後やりたいこと |

## コマンド

```sh
bash scripts/check.sh            # テスト一式（数秒）。変更したら必ず実行
bash scripts/check.sh --build    # + ビルドして全ページを点検（Node 22.12+ が必要。CIでも実行される）
cd site && npm ci && npm run dev # 画面を見ながら開発（ローカル）
```

- `get_new_releases.py` を本物のAPIで動かすのは、運営者に頼まれたときだけ（`API_ID`/`GEMINI_API_KEY` が要る。`DATA_PATH` で書き込み先を変えられる）。
- Claude のクラウド環境では npm が使えない/ビルドが動かないことがある。その場合は `bash scripts/check.sh`（ビルドなし）で確認し、**PRのCIとCloudflareのプレビューが最初の本番ビルド**になる。見ていないものを「確認した」と書かない。

## 守ること

1. **main へ直接 push しない。** ブランチ（`claude/...`）→ PR。PRの作成は `gh api repos/juice0402/fanza-ranking/pulls`（REST）を使う（Claude Code環境では GraphQL が使えず `gh pr create` は失敗する）。
2. **秘密情報をコードやログに書かない。** 使うのは GitHub Secrets の `API_ID` / `AFFILIATE_ID` / `GEMINI_API_KEY` のみ。リポジトリは公開なので、一度でも書くと履歴に残る。Geminiのキーは URL ではなくヘッダ（`x-goog-api-key`）で渡す。
3. **規約の表記を消さない。** 全ページに「広告（アフィリエイト）表記」「18歳確認」「RTAラベル」「Powered by FANZA Webサービス」。AIコメントの注記も残す。`tests/verify_dist.py` が全ページを検査する。
4. **データを壊さない。** 取得に失敗したら `exit 1` で止まり、既存データは上書きしない（テスト済み）。データの形式を変えるときは `normalize_loaded`（Python）と `normalizeItems`（JS）の両方を直し、古い形式も読めるようにする。
5. **変更にはテストを足す。** 挙動を変えたら `tests/` を更新し、`bash scripts/check.sh` を通してから PR にする。
6. Pythonは標準ライブラリのみ（Actionsは Python 3.12）。コードのコメントと画面の文言は日本語。
7. 作品タイトルを Gemini に渡さない（セーフティフィルターでブロックされやすくなるため。出演者・メーカー・形式タグだけ渡す）。

## 変更のしかた（例）

- 表示件数・サイト名・URL → `site/src/config.js`
- デザイン → `site/src/styles/site.css`、部品は `site/src/components/`、全ページ共通部分は `site/src/layouts/Base.astro`
- コメントの文体・代替文 → `get_new_releases.py`（`ANGLES`、`template_comment`、`build_prompt`）
- 取得する件数・日数 → `get_new_releases.py` 冒頭の定数（`NEW_ITEMS_PER_RUN` など）

背景や今後の予定は `docs/design-notes.md` を見ること。
