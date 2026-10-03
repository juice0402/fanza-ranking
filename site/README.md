# site（サイト本体）

Astro 7 で作った静的サイトです。Cloudflare Pages がこのフォルダをビルドして公開します。

- 設定（サイト名・URL・表示件数）: `src/config.js`
- ページ: `src/pages/`　部品: `src/components/`　共通の枠: `src/layouts/Base.astro`　見た目: `src/styles/site.css`
- データ（自動更新・手で編集しない）: `src/data/new_releases.json`

全体の説明・コマンド・守ること → リポジトリ直下の [README.md](../README.md) と [CLAUDE.md](../CLAUDE.md)

```sh
npm ci          # 初回だけ
npm run dev     # 画面を見ながら開発
npm run build   # 公開用に作る（dist/ に出力）
```
