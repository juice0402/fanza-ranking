# CLAUDE.md — このリポジトリで開発するときの案内

FANZAの新作・予約作品を毎日自動で集め、ひとことコメントを添えて公開するアフィリエイトブログ。
公開先: https://av-sale-guide.com/ （リポジトリは **public**）

コードを直すときは docs/MAP.md → 検索 → その範囲だけ読む → 変わる所だけ直す（claude/code-rules.md）

運営者はコードに詳しくない。説明は専門用語を避けた平易な日本語で、手順は1手ずつ示す。
開発は「Claude に頼む → ブランチ+プルリクエスト → CI（check。ビルドと全ページの点検）で確認 → 運営者が Merge」の1本道（ターミナル操作は不要）。

docs/ は `MAP.md`（地図）・`architecture.md`（ファイルごと。変える前にその節は必ず読む）・`shikumi.md`（公開・仕組み・ページ・コマンド）・`kimari.md`（守ること）・`design.md`・`claude-old.md`（経緯）。全部は読まず、検索してその節だけ。新しい機能のくわしい説明は docs/architecture.md の節に書き、ここには1行だけ。
CLAUDE.md は5,000字くらいに保つ（いまの決まり・作り・やり方だけ）。経緯・くわしいことは docs/ へ書く。

## トークンの節約（点検は減らさない）

- 大きなファイル・データの JSON・ログは検索して必要な所だけ。`gh api` は `--jq` で要る所だけ。くわしくは docs/shikumi.md の「トークンの節約（くわしく）」

## 公開

- 公開は `deploy.yml`（ビルド → 全ページの点検 `tests/verify_dist.py` → Cloudflare Workers）。Cloudflare のビルドは使わない。点検に落ちたら公開しない
- main に入ると本番に公開。毎日の更新・取り直しは、データを保存したあとに `deploy.yml` を動かす（ワークフローが保存したコミットでは、ほかのワークフローが自動では動かないため）
- コード・デザインのPR（`site/` の中。データは除く）は CI がプレビューを作る（URL は check の注釈）
- 本番の URL は `config.js` の `SITE_URL` 1か所。Pages には出さない。`FILE_BUDGET` は4万。`[CI Skip]` は要らない。くわしくは docs/shikumi.md の「公開（くわしく）」

## 仕組み

毎日 0:05 `update.yml`（`get_new_releases.py` など → main に commit → `deploy.yml`）、0:20 Claude のコメント・紹介文、月曜 0:50 Claude のまとめ・読み物（手順は docs/claude-*.md）、ほかにセール・10円セール・見張り `mihari.yml`・マージの印 `merge-ok.yml` など。表は docs/shikumi.md の「毎日・毎週の仕組み（くわしい表）」、見張りとマージの印は同じファイルの「見張り（mihari.yml）」「マージの印（merge-ok.yml）」。
週1回の仕事は、日曜から月曜に日付が変わったあとにそろえる。Gemini を使うのは `get_new_releases.py` のコメントの下書きだけ（守ること8）。ほかの道具・取り直し（`refresh-data.yml`）は使わない。

## コマンド

```sh
bash scripts/check.sh            # テスト一式。変更したら必ず実行。成功は1行ずつ・失敗だけくわしく
bash scripts/check.sh --build    # + ビルドして全ページを点検（Node 22.12+。CIでも実行）
python3 scripts/wait_run.py update|ci <sha>|deploy <sha>   # 1回で待つ（timeout 600000。3 が返ったらもう一度）
```

- `get_new_releases.py` を本物のAPIで動かすのは、運営者に頼まれたときだけ。取り直しだけは `--refresh-only`
- クラウド環境でビルドが動かないときは `bash scripts/check.sh` で確認し、PRのCIが最初のビルド。見ていないものを「確認した」と書かない。本番を WebFetch で見るときは URL の末尾に `?cb=日時`。くわしくは docs/shikumi.md の「コマンドの補足」

## 守ること

1. **main へ直接 push しない。** ブランチ（`claude/...`）→ PR。PRの作成は `gh api repos/juice0402/fanza-ranking/pulls`（REST。`gh pr create` は失敗する）。毎日更新の `update.yml` だけは、データファイルだけを main に直接 commit する。
   - 例外: 予約タスクの PR で、次のファイルだけを変えるものは、**CIが緑なら Claude 自身が Merge してよい**（運営者の許可済み）: コメント（`new_releases.json`・`site/src/data/catalog/`・売り場の `doujin.json`・`game.json`・`anime.json`・`amateur.json`・`cinema.json`・`comic.json`・`photo.json`・`vr.json`）と女優の歩みの紹介文 `actress_stories.json`／週のまとめ `roundups.json`／月のまとめ `monthly.json`（週と月を1つにしたPRも）／読み物 `yomimono.json`（まとめ記事のデータとの組み合わせも）。コード・デザインを変えるPRは、運営者に知らせてからMergeする。くわしくは docs/kimari.md の「1. 予約タスクの PR を Claude が Merge してよいもの（くわしく）」
2. **秘密情報をコードやログに書かない。** 使うのは GitHub Secrets の `API_ID` / `AFFILIATE_ID` / `GEMINI_API_KEY` と、公開用の `CLOUDFLARE_WORKERS_TOKEN` / `CLOUDFLARE_ACCOUNT_ID`（`deploy.yml` と CI のプレビューだけに渡す。Pages 用の `CLOUDFLARE_API_TOKEN` は戻すときのために残す）のみ。リポジトリは公開なので、一度でも書くと履歴に残る。Geminiのキーは URL ではなくヘッダ（`x-goog-api-key`）で渡す。
3. **規約の表記を消さない。** 全ページに「広告（アフィリエイト）表記」「18歳確認」「RTAラベル」「Powered by FANZA Webサービス」。AIコメントの注記も残す。`tests/verify_dist.py` が全ページを検査する。
   - FANZA のクレジットは、DMMの規定のHTML（`items.js` の `DMM_CREDIT_HTML`）を1文字も変えない。フッターの `<p class="foot-credit">` に `set:html` でそのまま入れ、class・target・rel・文節の区切りを足さない
   - 「広告」のラベルは、最初に見える画面（ヘッダーの `pr-chip`）に残す。くわしい文はフッター。フッターだけにしない（ステマ規制への対応）
   - 個々のリンクやボタンの下の行には「広告」の文字を付けない。画面に「AI」という言葉は出さないが、コメントが自動で作成されていて正確さは保証できないという注記はフッターに必ず残す（「自動で作成」と書く）
   - 18歳確認（`.gate`）は真っ黒ではなく強いぼかし（18px ほど）。古いブラウザ・「透明さを減らす」ではほぼ真っ黒
   - くわしくは docs/kimari.md の「3. 規約の表記（くわしく）」
4. **データを壊さない。** 取得に失敗したら `exit 1` で止まり、既存データは上書きしない。保存データの形式を変えるときは、`normalize_loaded`（Python）と `normalizeItems`（JS）の両方を直し、**データ本体も新しい形式に移行してから**（`tests/test_data.py` が通ること）、古い形式の読み込み処理は残さない。`site/src/data/` は自動更新のデータで、手で編集しない。
5. **変更にはテストを足す。** 挙動を変えたら `tests/` を更新し、`bash scripts/check.sh` を通してから PR にする。
6. Pythonは標準ライブラリのみ（Actionsは Python 3.12）。コードのコメントと画面の文言は日本語。
7. 作品タイトルを Gemini に渡さない（出演者・メーカー・形式タグだけ渡す）。週のまとめ記事（`scripts/claude_roundups.py list`）もタイトルを出さない。
   - 例外: Claude がコメントを書き上げるときだけ、`scripts/claude_comments.py list` が安全チェックを通ったタイトルを出す。未成年を連想させる作品はタイトルを出さない（`title_hidden`・`content_off`）。行為・体の部位・性的暴行・未成年を連想させる言葉は書かない（`apply` が断る）。タイトルを10文字以上写さない。くわしくは docs/kimari.md の「7. 作品タイトルとコメント（くわしく）」と `docs/claude-comments.md`
8. **Gemini無料枠は1日20回ほど。** 1回の実行は 新規12＋予約4＋再挑戦4＝20回に収めてある。件数を増やすなら、先に運営者へ「有料枠にするか」を確認する。`get_new_releases.py` の手動実行は1日1回まで。FANZA(DMM)のAPIはこの回数に入らない。くわしくは docs/kimari.md の「8. Gemini の回数（くわしく）」
9. **出演者の個人情報は最小限。** 保存するのは FANZA 公式の API が返す出演者データのうち表示に使うものだけ。生年月日は年齢の計算に使い、画面には年齢と誕生日の月日だけ（生まれた年は出さない）。FANZA 公式のプロフィールの血液型・出身地・趣味は出してよい。FANZA に名前が載っていない出演者を、ほかのサイトや推測で補わない。例外は所属事務所の公式サイトの所属事務所とSNS（`agencies.json`）とイベント情報（`events.json`）だけで、名前の完全一致のときだけ。事務所を足すときは robots.txt と利用規約を確かめる。くわしくは docs/kimari.md の「9. 出演者の個人情報（くわしく）」

## 変更のしかた

- 表示件数・サイト名・URL・ページを作るジャンル → `site/src/config.js`。取得する件数・日数 → `get_new_releases.py` 冒頭の定数（Geminiの回数上限とセットで → 守ること8）
- デザイン → `site/src/styles/site.css`・`components/`・`layouts/Base.astro`。デザインを変える前に docs/design.md を読む。AIっぽさゼロ（絵文字・右はしの「›」「→」・決まりの言葉・左はしの色の帯・色をぬる四角いボタンの切りかえ・小さな「見る」・シールや札を使わない。`tests/test_ai_style.py`）。押せるものの枠と地は `--edge`・`--fill`。説明文は短く（見出しの下は1文まで）。一覧のカードは低く。3つ並びと棚は置かれた場所の幅に合わせる。あとから出てきて画面がずれる作りにしない。くわしくは docs/design.md の「デザイン（`site/src/styles/site.css`・`components/`・`layouts/Base.astro`）」
- コメントの文体 → docs/design.md の「コメントの文体・代替文」
