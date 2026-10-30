# CLAUDE.md — このリポジトリで開発するときの案内

FANZAの新作・予約作品を毎日自動で集め、ひとことコメントを添えて公開するアフィリエイトブログ。
公開先: https://av-sale-guide.com/ （リポジトリは **public**）

運営者はコードに詳しくない。説明は専門用語を避けた平易な日本語で、手順は1手ずつ示す。
開発は「Claude に頼む → ブランチ+プルリクエスト → CI（check。ビルドと全ページの点検）で確認 → 運営者が Merge」の1本道（ターミナル操作は不要）。

**くわしい説明は `docs/architecture.md`**（データの流れの全体・ファイルごとの役割と決まり・経緯・運営者の希望）。**全部は読まない**: 変えるファイル・機能の名前で検索して（`grep -n "floor_sales" docs/architecture.md`）、その節だけ Read の offset/limit で読む。**変える前に、そのファイルの節は必ず読む。** 新しい機能を足したら、くわしい説明はそこの節に書き、このファイルには1行だけ足す。
くわしいことは docs/ の `shikumi.md`（公開・毎日の仕組みの表・ページ・コマンドの補足）・`kimari.md`（守ることのくわしいこと）・`design.md`（デザインの決まり）・`architecture.md`（ファイルごと）（全部は読まず、さわる所の節・行だけ読む）。
CLAUDE.md は1万字以内に保つ。経緯・くわしいことは docs/ へ書く。

## トークンの節約（運営者の希望「クロードのトークンをできるだけ節約したい。サイトが確実に運用されることが優先」。2026-10-13）

- このファイルは、毎回の会話で自動で読み込まれる（読み直さない）。**短く保つ**（くわしいことは docs/architecture.md へ）
- テストは `bash scripts/check.sh`（成功は1行ずつ・失敗したテストだけ ❌ の行と出力の後ろ。全部見たいときだけ `--verbose`。CI では全部出る）
- GitHub の実行（毎日の更新・CI・公開）を待つときは、何度も見に行かずに `python3 scripts/wait_run.py update|ci <sha>|deploy <sha>` を1回（Bash の timeout は 600000。中で30秒ごとに見て、終わったら1行で返す。3 が返ったら同じコマンドをもう一度）
- 大きなファイル（docs/design-notes.md・docs/architecture.md・データの JSON・ビルドのログ）は、全部を読まずに検索して必要な所だけ。`gh api` は `--jq` で要る所だけ出す（PR を作った答えの全体は数万文字ある）
- 点検（テスト・CI・公開前の全ページの点検）は減らさない

## 公開

**公開は GitHub Actions が行う**（`deploy.yml`: ビルド → 全ページの点検 `tests/verify_dist.py` → Cloudflare Workers に直接アップロード）。Cloudflare のビルド（月500回を「あそびトーク」と共有）は使わない。
- main に入ると本番に公開される。毎日の更新・取り直しは、データを保存したあとに `deploy.yml` を動かす（ワークフローが保存したコミットでは、ほかのワークフローが自動では動かないため）。点検に落ちたら公開しない（前の公開のまま）。
- コード・デザインを変えるPR（`site/` の中。データは除く）は、CI がプレビュー（`<ブランチ名>-av-sale-guide.juice-juice-0402.workers.dev`。URL は check の注釈）を作る。
- 独自ドメインは `https://av-sale-guide.com`（`site/src/config.js` の `SITE_URL` 1か所で、URL・canonical・sitemap・robots.txt・RSS・構造化データ・IndexNow が切りかわる）。旧 fanza-ranking.pages.dev は Bulk Redirects で 301。くわしくは docs/shikumi.md の「公開（くわしく）」
- 本番の公開のたびに `deploy.yml` が `scripts/indexnow.py` で、新しいページ・変わったページを IndexNow で知らせる（Google は sitemap と Search Console）。くわしくは docs/shikumi.md
- 本番もプレビューも Cloudflare Workers（`workers/wrangler.jsonc`・`scripts/deploy_workers.sh`・Secrets の `CLOUDFLARE_WORKERS_TOKEN`）。Pages には出さない。ファイル数の上限 `FILE_BUDGET` は4万。戻し方は docs/architecture.md の「Workers への引っ越し」
- Cloudflare 側の自動ビルドは止めてある（2026-10-09。ダッシュボードの「ブランチコントロール」。戻すときはそこをオンに）。コミット・Merge のメッセージに `[CI Skip]` は要らない（入れても何も変わらない）。

## 仕組み（時刻は日本時間。くわしくは docs/architecture.md の「データの流れ」）

| いつ | 何が動く（くわしい表は docs/shikumi.md） |
|---|---|
| 毎日 0:05 | `update.yml`: `get_new_releases.py`（新作・予約・Gemini の下書き・出演者・過去作品・人気・セール・レビュー）と売り場など → main に commit → `deploy.yml` |
| 毎日 0:20 | Claude の予約タスク: コメント（1日40件。`docs/claude-comments.md`）＋女優の歩みの紹介文5人（`docs/claude-history.md`） |
| 毎日 0:35・10:17 | `sale-refresh.yml`: セールと売り場の読み直し |
| 毎日 10:12・12:12・16:12・20:12 | `ten-yen.yml`: 10円セールが変わったときだけ保存して公開 |
| 毎日 4:23 | `actress-history.yml`: 女優の歩み（公開はしない） |
| 毎週月曜 0:01 | `health.yml`: 見張り番（Claude を使わない） |
| 毎週月曜 0:50 | Claude の予約タスク: 週のまとめ（`docs/claude-roundups.md`）・月が変わって最初の月曜は月のまとめ（`docs/claude-monthly.md`）・読み物1本（`docs/claude-yomimono.md`）・見張り番の報告 |

週1回の仕事は、日曜から月曜に日付が変わったあとにそろえる（所属事務所・読みがなも月曜 0:05 の更新で集める）。

Gemini を使うのは `get_new_releases.py` のコメントの下書きだけ（守ること8）。ほかの道具・取り直し（`refresh-data.yml`）は使わない。

## どこに何があるか（くわしくは docs/architecture.md の、そのファイルの節）

- `get_new_releases.py` — 毎日の更新（動画の新作・予約・過去作品・人気・セール・レビュー）。Python の標準ライブラリだけ
- Claude が書く道具 `scripts/claude_*.py`（コメント・まとめ・紹介文・読み物。`list` → 書く → `apply` が点検して書き込む）・売り場 `scripts/doujin_game.py`・`floor_*.py`・10円セール `ten_yen.py`・読みがな `readings.py`・所属事務所 `agency_*.py`（守ること9）・見張り番 `health.py`・画面の点検 `screens.mjs`・`.github/workflows/`・`site/public/`（ブラウザの小さなスクリプト）は docs/shikumi.md の「ファイル（くわしく）」
- ページのくわしいこと（読み物 `/yomimono/`・名簿の人の女優のページ・`/sale/ending/`・`/hinban/`・`/actress/nenpyo/`・作品ページの品番と出演者）は docs/shikumi.md の「ページ（くわしく）」
- `scripts/indexnow.py` — 検索エンジンへのお知らせ（IndexNow。本番の公開のときだけ）
- `scripts/check.sh`（`quiet_step.sh`）— テスト一式 ／ `scripts/wait_run.py` — GitHub の実行を待つ ／ `scripts/already_updated.sh` — 今日の更新が済んだか
- `site/` — サイト本体（Astro 7・静的出力）。`src/config.js` がサイト名・URL・件数・ファイル数の上限（`FILE_BUDGET`＝4万。Workers の静的ファイルは10万まで）の設定
- `site/src/lib/` — 画面に依存しない部品（テストは `tests/test_*.mjs`）。`data.js`（読み込み）・`items.js`（並べ替え・構造化データ・規約の表記）など。一覧は docs/shikumi.md の「site/src/lib（くわしく）」
- `site/src/pages/`・`components/`・`layouts/Base.astro`・`styles/site.css` — ページ・部品・全ページ共通の部分・デザイン
- `site/src/data/` — **自動更新のデータ。手で編集しない**（書く道具が決まっている。形は docs/architecture.md の、そのファイルの節）
- `tests/` — テスト一式（`fixtures/` は固定データ）。`tests/verify_dist.py` がビルドした全ページを点検する
- `docs/` — 予約タスクの手順書（`claude-comments.md`・`claude-roundups.md`・`claude-monthly.md`）・`architecture.md`・`design-notes.md`

## コマンド

```sh
bash scripts/check.sh            # テスト一式（30秒ほど）。変更したら必ず実行。成功は1行ずつ・失敗だけくわしく
bash scripts/check.sh --build    # + ビルドして全ページを点検（Node 22.12+ が必要。CIでも実行される）
bash scripts/check.sh --verbose  # テストの出力を全部出す
python3 scripts/wait_run.py ci <sha>      # CI が終わるまで待って1行で（update・deploy <sha> も）
cd site && npm ci && npm run dev # 画面を見ながら開発（ローカル）
```

- `get_new_releases.py` を本物のAPIで動かすのは、運営者に頼まれたときだけ（`API_ID`/`GEMINI_API_KEY` が要る。`DATA_PATH` で書き込み先を変えられる）。
  - Gemini を使わずに取り直しだけしたいときは `python get_new_releases.py --refresh-only`（Actions では「Refresh FANZA Data」）。くわしくは docs/shikumi.md の「コマンドの補足」
- 本番サイトを WebFetch で確認するときは、URLの末尾に `?cb=日時` を付ける（付けないと、前に取得した古い内容が返ってきて、更新されていないように見えることがある。2026-10-03 の仮運転で確認）。
- Claude のクラウド環境では npm が使えない/ビルドが動かないことがある。その場合は `bash scripts/check.sh`（ビルドなし）で確認し、**PRのCIが最初のビルド**になる（プレビューの URL は check の注釈。クラウド環境からは開かない）。見ていないものを「確認した」と書かない。
- 本番に公開されたかは `python3 scripts/wait_run.py deploy <Merge のコミット>`（`deploy.yml` の実行を見る。ビルドと点検とアップロードで10〜15分。`cancelled` は、あとの Merge の公開に含まれたということで、そちらの結果を返す）

## 守ること

1. **main へ直接 push しない。** ブランチ（`claude/...`）→ PR。PRの作成は `gh api repos/juice0402/fanza-ranking/pulls`（REST）を使う（Claude Code環境では GraphQL が使えず `gh pr create` は失敗する）。毎日更新の GitHub Actions（`update.yml`）だけは、データファイルだけを main に直接 commit する。
   - 例外: 予約タスクの PR で、次のファイルだけを変えるものは、**CIが緑なら Claude 自身が Merge してよい**（運営者の許可済み）: コメント（`new_releases.json`・`site/src/data/catalog/`・売り場の `doujin.json`・`game.json`・`anime.json`・`amateur.json`・`cinema.json`・`comic.json`・`photo.json`・`vr.json`）と女優の歩みの紹介文 `actress_stories.json`／週のまとめ `roundups.json`／月のまとめ `monthly.json`（週と月を1つにしたPRも）／読み物 `yomimono.json`（まとめ記事のデータとの組み合わせも）。コード・デザインを変えるPRは、運営者に知らせてからMergeする。くわしい経緯は docs/kimari.md の「1.」
2. **秘密情報をコードやログに書かない。** 使うのは GitHub Secrets の `API_ID` / `AFFILIATE_ID` / `GEMINI_API_KEY` と、公開用の `CLOUDFLARE_WORKERS_TOKEN` / `CLOUDFLARE_ACCOUNT_ID`（`deploy.yml` と CI のプレビューだけに渡す。Pages 用の `CLOUDFLARE_API_TOKEN` は戻すときのために残す）のみ。リポジトリは公開なので、一度でも書くと履歴に残る。Geminiのキーは URL ではなくヘッダ（`x-goog-api-key`）で渡す。
3. **規約の表記を消さない。** 全ページに「広告（アフィリエイト）表記」「18歳確認」「RTAラベル」「Powered by FANZA Webサービス」。AIコメントの注記も残す。`tests/verify_dist.py` が全ページを検査する。
   - FANZA のクレジットは、DMMの規定のHTML（`items.js` の `DMM_CREDIT_HTML`）を1文字も変えない。フッターの `<p class="foot-credit">` に `set:html` でそのまま入れ、class・target・rel・文節の区切りを足さない（`tests/verify_dist.py` が全ページで突き合わせる）
   - 「広告」のラベルは、**最初に見える画面（ヘッダーの `pr-chip`）に残す**。くわしい文はフッター。フッターだけにしない（ASPの案内で「ファーストビューに表示」「下部やフッターだけは不適切」とされているため。ステマ規制への対応）。
   - 個々のリンクやボタンの下の行には「広告」の文字を付けない。画面に「AI」という言葉は出さないが、コメントが自動で作成されていて正確さは保証できないという注記はフッターに必ず残す（「自動で作成」と書く）
   - 18歳確認（`.gate`）は真っ黒ではなく強いぼかし（18px ほど）。古いブラウザ・「透明さを減らす」ではほぼ真っ黒。`tests/verify_dist.py` が検査する
   - くわしくは docs/kimari.md の「3.」
4. **データを壊さない。** 取得に失敗したら `exit 1` で止まり、既存データは上書きしない（テスト済み）。保存データの形式を変えるときは、`normalize_loaded`（Python）と `normalizeItems`（JS）の両方を直し、**データ本体も新しい形式に移行してから**（`tests/test_data.py` が通ること）、古い形式の読み込み処理は残さない。
5. **変更にはテストを足す。** 挙動を変えたら `tests/` を更新し、`bash scripts/check.sh` を通してから PR にする。
6. Pythonは標準ライブラリのみ（Actionsは Python 3.12）。コードのコメントと画面の文言は日本語。
7. 作品タイトルを Gemini に渡さない（セーフティフィルターでブロックされやすくなるため。出演者・メーカー・形式タグだけ渡す）。週のまとめ記事（`scripts/claude_roundups.py list`）もタイトルを出さない。
   - 例外: Claude がコメントを書き上げるときだけ、`scripts/claude_comments.py list` が安全チェックを通ったタイトルを出す。未成年を連想させる作品はタイトルを出さない（`title_hidden`・`content_off`）。行為・体の部位・性的暴行・未成年を連想させる言葉は書かない（`apply` が断る）。タイトルを10文字以上写さない。くわしくは docs/kimari.md の「7.」と `docs/claude-comments.md`
8. **Gemini無料枠は1日20回ほど。** 1回の実行は 新規12＋予約4＋再挑戦4＝20回に収めてある。件数を増やすなら、先に運営者へ「有料枠にするか」を確認する。`get_new_releases.py` の手動実行は1日1回まで（上限に当たると、その日はAIコメントが付かない）。詳細は `docs/design-notes.md`。
   - FANZA(DMM)のAPI（品番の取り直し・出演者・売れ筋）は Gemini を使わないので、この回数に入らない。くわしくは docs/kimari.md の「8.」
9. **出演者の個人情報は最小限。** 保存するのは FANZA 公式の API が返す出演者データのうち表示に使うものだけ。生年月日は年齢の計算に使い、画面には年齢と誕生日の月日だけ（生まれた年は出さない）。FANZA 公式のプロフィールの血液型・出身地・趣味は出してよい。FANZA に名前が載っていない出演者を、ほかのサイトや推測で補わない。例外は所属事務所の公式サイトの所属事務所とSNS（`agencies.json`）とイベント情報（`events.json`）だけで、名前の完全一致のときだけ。事務所を足すときは robots.txt と利用規約を確かめる。くわしくは docs/kimari.md の「9.」

## 変更のしかた（例）

- 表示件数・サイト名・URL・ページを作るジャンル → `site/src/config.js`
- デザイン → `site/src/styles/site.css`、部品は `site/src/components/`、全ページ共通部分は `site/src/layouts/Base.astro`
  - 押せるものの枠と地は `--edge`・`--fill`。説明文は短く（見出しの下は1文まで）。あとから出てきて画面がずれる作りにしない。AIっぽさゼロ（絵文字・右はしの「›」「→」・決まりの言葉・左はしの色の帯・色をぬる四角いボタンの切りかえ・小さな「見る」・シールや札を使わない。`tests/test_ai_style.py`）。一覧のカードは低く。3つ並びと棚は置かれた場所の幅に合わせる。くわしくは docs/design.md（デザインを変える前に読む）
- コメントの文体・代替文 → `get_new_releases.py`（`ANGLES`/`OPENINGS`/`CLOSINGS` など。docs/design.md の「コメントの文体・代替文」）。Claude が書くコメント → `docs/claude-comments.md`。週のまとめ → `docs/claude-roundups.md`。月のまとめ → `docs/claude-monthly.md`
- 取得する件数・日数 → `get_new_releases.py` 冒頭の定数（`NEW_ITEMS_PER_RUN` など。Geminiの回数上限とセットで考える → 守ること8）

背景・デザインの経緯・API と Gemini で学んだ注意点・今後の予定は `docs/design-notes.md`（大きいので、全部は読まずに検索して、必要な所だけ）。