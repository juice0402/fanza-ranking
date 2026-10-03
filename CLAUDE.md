# CLAUDE.md — このリポジトリで開発するときの案内

FANZAの新作・予約作品を毎日自動で集め、AIのひとことコメントを添えて公開するアフィリエイトブログ。
公開先: https://fanza-ranking.pages.dev/ （リポジトリは **public**）

運営者はコードに詳しくない。説明は専門用語を避けた平易な日本語で、手順は1手ずつ示す。
開発は「Claude に頼む → ブランチ+プルリクエスト → Cloudflareのプレビューで確認 → 運営者が Merge」の1本道（ターミナル操作は不要）。

## 仕組み（データの流れ）

```
GitHub Actions（毎日 0:05 JST。日付が変わった直後）
  → get_new_releases.py
      FANZA(DMM) アフィリエイトAPI から「発売済み」「予約」を別々に取得
      Gemini でひとことコメント作成（ブロック時は代替文 → 次回再挑戦）
      → site/src/data/new_releases.json に作品IDごとにためていく
  → main に commit → Cloudflare Pages が自動ビルド（Astro, 静的サイト）→ 公開

Claude の予約タスク（毎日 0:20 JST。手順は docs/claude-comments.md）
  → Gemini が書けず定型文のままの作品に、Claude がコメントを書く（scripts/claude_comments.py）
  → ブランチ+PR → CIが緑ならMerge → 公開

Claude の予約タスク（毎週月曜 0:50 JST。手順は docs/claude-roundups.md）
  → 前の週（月〜日）に発売された作品の「週のまとめ記事」を Claude が書く（scripts/claude_roundups.py）
  → site/src/data/roundups.json に追加 → ブランチ+PR → CIが緑ならMerge → /weekly/ に公開
```

## フォルダ

| 場所 | 役割 |
|---|---|
| `get_new_releases.py` | 毎日の更新スクリプト。Python標準ライブラリだけ（pip不要） |
| `scripts/claude_comments.py` | Claude がコメントを書くための道具（`list` で対象を出し、`apply` で点検して書き込む）。標準ライブラリだけ |
| `scripts/claude_roundups.py` | Claude が週のまとめ記事を書くための道具（`list` で週の作品データを出し、`apply` で点検して `roundups.json` に書き込む）。標準ライブラリだけ |
| `site/` | サイト本体（Astro 7 / 静的出力）。Cloudflare Pages のビルド対象 |
| `site/src/config.js` | **サイト名・URL・表示件数の設定はここだけ**（独自ドメイン化もここ） |
| `site/src/lib/items.js` | 並べ替え・日付・sitemap/robots・出演者/メーカーのまとめ・構造化データ（JSON-LD）など、テストできる部品（画面に依存しない） |
| `site/src/lib/roundups.js` | 週のまとめ記事の部品（週の計算・集計・読み込み・Article構造化データ。画面に依存しない）。集計は `claude_roundups.py` の `week_stats` と同じ数え方（`tests/test_roundups.mjs` で突き合わせている） |
| `site/src/lib/data.js` | JSON読み込み。`released`/`upcoming`/`all`/`roundups` を各ページに渡す |
| `site/src/pages/` | トップ、`item/[cid]`（作品）、`archive/[page]`（過去作品）、`actress/`（出演者別。2本以上の人だけ）、`maker/`（メーカー別。2本以上だけ）、`weekly/`（週のまとめ記事。1本も無いあいだは一覧が noindex・sitemap にも入らず、リンクも出さない）、404、`sitemap.xml.js`、`robots.txt.js` |
| `site/src/data/new_releases.json` | **自動更新のデータ。手で編集しない**（作品IDごとに蓄積。`updated` は、その作品のコメントを最後に変えた日で、sitemap の `lastmod` に使う） |
| `site/src/data/roundups.json` | **Claude が毎週書き足す記事のデータ。手で編集しない**（`claude_roundups.py apply` だけが書く。新しい週が先頭） |
| `tests/` | テスト一式。`fixtures/` は固定データ（本番データには依存しない） |
| `scripts/check.sh` | テストをまとめて実行（`--build` でビルドと点検まで） |
| `.github/workflows/` | `update.yml`（毎日の更新）、`ci.yml`（PRごとの自動確認） |
| `docs/claude-comments.md` | 毎日の予約タスク（Claude がコメントを書く）の手順書と書き方のルール |
| `docs/claude-roundups.md` | 毎週月曜の予約タスク（Claude が週のまとめ記事を書く）の手順書と書き方のルール |
| `docs/design-notes.md` | デザインの考え方、API/Geminiで学んだ注意点、今後やりたいこと |

## コマンド

```sh
bash scripts/check.sh            # テスト一式（数秒）。変更したら必ず実行
bash scripts/check.sh --build    # + ビルドして全ページを点検（Node 22.12+ が必要。CIでも実行される）
cd site && npm ci && npm run dev # 画面を見ながら開発（ローカル）
```

- `get_new_releases.py` を本物のAPIで動かすのは、運営者に頼まれたときだけ（`API_ID`/`GEMINI_API_KEY` が要る。`DATA_PATH` で書き込み先を変えられる）。
- 本番サイトを WebFetch で確認するときは、URLの末尾に `?cb=日時` を付ける（付けないと、前に取得した古い内容が返ってきて、更新されていないように見えることがある。2026-10-03 の仮運転で確認）。
- Claude のクラウド環境では npm が使えない/ビルドが動かないことがある。その場合は `bash scripts/check.sh`（ビルドなし）で確認し、**PRのCIとCloudflareのプレビューが最初の本番ビルド**になる。見ていないものを「確認した」と書かない。

## 守ること

1. **main へ直接 push しない。** ブランチ（`claude/...`）→ PR。PRの作成は `gh api repos/juice0402/fanza-ranking/pulls`（REST）を使う（Claude Code環境では GraphQL が使えず `gh pr create` は失敗する）。毎日更新の GitHub Actions（`update.yml`）だけは、データファイルだけを main に直接 commit する。
   - 例外の許可: 予約タスクの**コメント更新PR（`new_releases.json` だけを変えるもの）は、CIが緑なら Claude 自身が Merge してよい**（運営者の許可済み）。同じく、**週のまとめ記事のPR（`roundups.json` だけを変えるもの）も、CIが緑なら Claude 自身が Merge してよい**（運営者の許可済み）。コード・デザインを変えるPRは、運営者に知らせてからMergeする。
2. **秘密情報をコードやログに書かない。** 使うのは GitHub Secrets の `API_ID` / `AFFILIATE_ID` / `GEMINI_API_KEY` のみ。リポジトリは公開なので、一度でも書くと履歴に残る。Geminiのキーは URL ではなくヘッダ（`x-goog-api-key`）で渡す。
3. **規約の表記を消さない。** 全ページに「広告（アフィリエイト）表記」「18歳確認」「RTAラベル」「Powered by FANZA Webサービス」。AIコメントの注記も残す。`tests/verify_dist.py` が全ページを検査する。
4. **データを壊さない。** 取得に失敗したら `exit 1` で止まり、既存データは上書きしない（テスト済み）。保存データの形式を変えるときは、`normalize_loaded`（Python）と `normalizeItems`（JS）の両方を直し、**データ本体も新しい形式に移行してから**（`tests/test_data.py` が通ること）、古い形式の読み込み処理は残さない。
5. **変更にはテストを足す。** 挙動を変えたら `tests/` を更新し、`bash scripts/check.sh` を通してから PR にする。
6. Pythonは標準ライブラリのみ（Actionsは Python 3.12）。コードのコメントと画面の文言は日本語。
7. 作品タイトルを Gemini に渡さない（セーフティフィルターでブロックされやすくなるため。出演者・メーカー・形式タグだけ渡す）。Claude がコメントや週のまとめ記事を書くときも同じで、`scripts/claude_comments.py list` と `scripts/claude_roundups.py list` はタイトルを出さない。
8. **Gemini無料枠は1日20回ほど。** 1回の実行は 新規12＋予約4＋再挑戦4＝20回に収めてある。件数を増やすなら、先に運営者へ「有料枠にするか」を確認する。`get_new_releases.py` の手動実行は1日1回まで（上限に当たると、その日はAIコメントが付かない）。詳細は `docs/design-notes.md`。

## 変更のしかた（例）

- 表示件数・サイト名・URL → `site/src/config.js`
- デザイン → `site/src/styles/site.css`、部品は `site/src/components/`、全ページ共通部分は `site/src/layouts/Base.astro`
- コメントの文体・代替文 → `get_new_releases.py`（`ANGLES`、`template_comment`、`build_prompt`）。Claude が書くコメントの書き方・手順 → `docs/claude-comments.md`。週のまとめ記事の書き方・手順 → `docs/claude-roundups.md`
- 取得する件数・日数 → `get_new_releases.py` 冒頭の定数（`NEW_ITEMS_PER_RUN` など。Geminiの回数上限とセットで考える → 守ること8）

背景や今後の予定は `docs/design-notes.md` を見ること。
