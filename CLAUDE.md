# CLAUDE.md — このリポジトリで開発するときの案内

FANZAの新作・予約作品を毎日自動で集め、ひとことコメントを添えて公開するアフィリエイトブログ。
公開先: https://av-sale-guide.com/ （リポジトリは **public**）

運営者はコードに詳しくない。説明は専門用語を避けた平易な日本語で、手順は1手ずつ示す。
開発は「Claude に頼む → ブランチ+プルリクエスト → CI（check。ビルドと全ページの点検）で確認 → 運営者が Merge」の1本道（ターミナル操作は不要）。

**くわしい説明は `docs/architecture.md`**（データの流れの全体・ファイルごとの役割と決まり・経緯・運営者の希望）。**全部は読まない**: 変えるファイル・機能の名前で検索して（`grep -n "floor_sales" docs/architecture.md`）、その節だけ Read の offset/limit で読む。**変える前に、そのファイルの節は必ず読む。** 新しい機能を足したら、くわしい説明はそこの節に書き、このファイルには1行だけ足す。

## トークンの節約（運営者の希望「クロードのトークンをできるだけ節約したい。サイトが確実に運用されることが優先」。2026-10-13）

- このファイルは、毎回の会話で自動で読み込まれる（読み直さない）。**短く保つ**（くわしいことは docs/architecture.md へ）
- テストは `bash scripts/check.sh`（成功は1行ずつ・失敗したテストだけ ❌ の行と出力の後ろ。全部見たいときだけ `--verbose`。CI では全部出る）
- GitHub の実行（毎日の更新・CI・公開）を待つときは、何度も見に行かずに `python3 scripts/wait_run.py update|ci <sha>|deploy <sha>` を1回（Bash の timeout は 600000。中で30秒ごとに見て、終わったら1行で返す。3 が返ったら同じコマンドをもう一度）
- 大きなファイル（docs/design-notes.md・docs/architecture.md・データの JSON・ビルドのログ）は、全部を読まずに検索して必要な所だけ。`gh api` は `--jq` で要る所だけ出す（PR を作った答えの全体は数万文字ある）
- 点検（テスト・CI・公開前の全ページの点検）は減らさない

## 公開

**公開は GitHub Actions が行う**（`deploy.yml`。ビルド → 全ページの点検 `tests/verify_dist.py` → Cloudflare Pages に直接アップロード＝Direct Upload。Cloudflare のビルド（月500回を「あそびトーク」と共有）は使わない。2026-10-09 から）。
- main に入ると本番に公開される。毎日の更新・取り直しは、データを保存したあとに `deploy.yml` を動かす（ワークフローが保存したコミットでは、ほかのワークフローが自動では動かないため）。点検に落ちたら公開しない（前の公開のまま）。
- コード・デザインを変えるPR（`site/` の中。データ `site/src/data/` は除く）は、CI が**プレビュー**（`<ブランチ名>.fanza-ranking.pages.dev`。URL は check の注釈と要約）を作る。データだけ・手順書やテストだけのPRには作らない。
- **独自ドメイン**（2026-10-22 取得。Cloudflare Registrar・1年・自動更新）: サイト名も「FANZA新作情報」から **FANZAセール情報** に（`config.js` の `SITE_NAME`）。本番は `https://av-sale-guide.com`（`site/src/config.js` の `SITE_URL` 1か所で、URL・canonical・sitemap・robots.txt・RSS・構造化データ・IndexNow が切りかわる）。旧 `https://fanza-ranking.pages.dev` は Cloudflare の Bulk Redirects で同じパスへ 301（プレビューの `<ブランチ名>.fanza-ranking.pages.dev` は転送しない＝サブドメインを含めない）。Search Console は新ドメインのドメインプロパティ＋旧プロパティからアドレス変更。DMM は新しいサイトとして追加（リンクは API 用の `juice0402-990` のまま）
- **検索エンジンへのお知らせ（IndexNow。2026-10-17）**: 本番の公開のたびに `deploy.yml` が `scripts/indexnow.py` で、新しいページ・コメントや記事が入ったページ（一覧・ランキングなどは7日に1回まで）を Bing などへ知らせる（1万件ずつ。前回の記録は本番の `/indexnow-pages.json`。受け付けてもらえなかったページは Actions の置き場（cache）にとっておき、次の公開で送り直す。main にはコミットしない。鍵は `site/public/<鍵>.txt`。Google は sitemap と Search Console のまま。くわしくは docs/architecture.md の「公開」）
- Cloudflare 側の自動ビルドは止めてある（2026-10-09。ダッシュボードの「ブランチコントロール」。戻すときはそこをオンに）。コミット・Merge のメッセージに `[CI Skip]` は要らない（入れても何も変わらない）。

## 仕組み（時刻は日本時間。くわしくは docs/architecture.md の「データの流れ」）

| いつ | 何が動く | おもに書くデータ（`site/src/data/`） |
|---|---|---|
| 毎日 0:05 | `update.yml`: `get_new_releases.py`（動画の新作・予約・Gemini の下書き・出演者・名簿・売れ筋・過去作品（人気の上位1万本）・人気の順位・セール・レビュー）→ 所属事務所（週1）・イベント・売り場（同人・ゲーム・アニメ・素人・成人映画・コミック・写真集・VR見放題）・読みがな（週1）・ジャンルの人気TOP20・10円セール → main に commit → `deploy.yml` | `new_releases.json`・`catalog/`・`popularity.json`・`sale.json`・`reviews.json`・`actresses.json`・`doujin.json` などの売り場・`ten_yen.json` ほか |
| 毎日 0:20 | Claude の予約タスク: コメントを仕上げる（1日40件。手順は `docs/claude-comments.md`）＋女優の歩みの紹介文を5人（`docs/claude-history.md`。2026-10-27〜） | `new_releases.json`・`catalog/`・売り場のファイル・`actress_stories.json` |
| 毎日 0:35・10:17 | `sale-refresh.yml`: 動画のセールの読み直し（はじめは上位1万本だけ）・10:17 は売り場の集め直し・0:35 は素人/アニメ/成人映画のキャンペーンごと | `sale.json`・`sale_history.json`・`floor_sale.json` |
| 毎日 10:12・12:12・16:12・20:12 | `ten-yen.yml`: 10円セールが変わったときだけ保存して公開 | `ten_yen.json` |
| 毎日 4:23 | `actress-history.yml`: 女優の歩み（出演者ごとの全作品を数える。`scripts/actress_history.py`。1回600回まで。公開はしない） | `actress_history.json` |
| 毎週月曜 0:01 | `health.yml`: 見張り番（この7日の更新・公開・コメント・過去作品の数・リポジトリの大きさ。Claude を使わない。おかしいときだけ ⚠️ と GitHub の知らせ） | なし（読むだけ） |
| 毎週月曜 0:50 | Claude の予約タスク: 週のまとめ記事（`docs/claude-roundups.md`）。月が変わって最初の月曜は、月のまとめ記事（`docs/claude-monthly.md`）も同じPRで。見張り番の結果も報告 | `roundups.json`・`monthly.json` |

週1回の仕事は、日曜から月曜に日付が変わったあとにそろえる（運営者の希望。2026-10-13）: 所属事務所・読みがなも、月曜 0:05 の毎日の更新で集める（月曜に集められなかったときは7日たった日）。

Gemini を使うのは `get_new_releases.py` のコメントの下書きだけ（守ること8）。ほかの道具・取り直し（`refresh-data.yml`）は使わない。

## どこに何があるか（くわしくは docs/architecture.md の、そのファイルの節）

- `get_new_releases.py` — 毎日の更新（動画の新作・予約・過去作品・人気・セール・レビュー）。Python の標準ライブラリだけ
- `scripts/claude_comments.py`・`claude_roundups.py`・`claude_monthly.py`・`claude_history.py` — Claude がコメント・週/月のまとめ・女優の歩みの紹介文を書く道具（`list` → 書く → `apply` が点検して書き込む）
- `scripts/doujin_game.py`・`floor_data.py`・`floor_history.py`・`floor_sales.py` — 売り場（同人・ゲーム・アニメ・素人・成人映画・コミック・写真集・VR見放題）を集める・人気の動き・セールの記録・キャンペーンごと
- `scripts/ten_yen.py` — 10円セール ／ `scripts/readings.py` — 読みがな ／ `scripts/genre_tops.py` — ジャンルの人気TOP20
- `/sale/ending/`（今週終わるセール）・`/hinban/`（品番の見方。`lib/hinban.js`）— 2026-10-27。くわしくは docs/architecture.md の「セール・キャンペーン」の下
- `scripts/agency_links.py`・`agency_events.py` — 所属事務所とSNS・女優のイベント情報（事務所の公式サイトから。守ること9）
- `scripts/indexnow.py` — 検索エンジンへのお知らせ（IndexNow。本番の公開のときだけ）
- `scripts/check.sh`（`quiet_step.sh`）— テスト一式 ／ `scripts/wait_run.py` — GitHub の実行を待つ ／ `scripts/already_updated.sh` — 今日の更新が済んだか
- `scripts/health.py`（`health.yml`）— 週1回の見張り番（毎週月曜 0:01。Claude を使わない。`--last` で結果を1行ずつ）
- `scripts/screens.mjs`（`screens.yml`）— 画面の写真と形のくずれの点検（GitHub の上で撮る）／ `scripts/probe_api.py`（`probe-api.yml`）— API の応答の形を調べる
- `.github/workflows/` — update・sale-refresh・ten-yen・ci・deploy（`scripts/deploy_pages.sh`）・health（見張り番）・refresh-data（取り直しだけ。手動）・probe-api・screens
- `site/` — サイト本体（Astro 7・静的出力）。`src/config.js` がサイト名・URL・件数・ファイル数の上限（`FILE_BUDGET`。Cloudflare Pages の無料プランは2万ファイルまで）の設定
- `site/src/lib/` — 画面に依存しない部品（テストは `tests/test_*.mjs`）。`data.js`（読み込み）・`items.js`（並べ替え・構造化データ・規約の表記）・`plan.js`（ファイル数の計画）・`floors.js`（売り場）・`sale.js`・`ten-yen.js`・`topics.js`（トップ）・`search.js`・`profiles.js`・`insights.js`・`reviews.js`・`kana.js`・`phrase.js`（文節の改行）・`describe.js`（検索結果の説明文。ページのデータの数字から80〜120文字）など
- `site/src/pages/`・`components/`・`layouts/Base.astro`・`styles/site.css` — ページ・部品・全ページ共通の部分・デザイン
- `site/public/` — ブラウザで動く小さなスクリプト（作品検索・女優検索・売り場の検索・VR/単体の絞り込み・お気に入り・運命の作品・セール・拡大表示・サンプル動画）と `_headers`・`_redirects`
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
  - **Geminiを使わずに、取り直しだけ**したいときは `python get_new_releases.py --refresh-only`（Actions では「Refresh FANZA Data」）。新しい作品の追加もAIコメントもしないので、Geminiの無料枠を使わない。`ACTRESSES_PATH` / `RANKING_PATH` で出演者データ・ランキングの書き込み先も変えられる。
- 本番サイトを WebFetch で確認するときは、URLの末尾に `?cb=日時` を付ける（付けないと、前に取得した古い内容が返ってきて、更新されていないように見えることがある。2026-10-03 の仮運転で確認）。
- Claude のクラウド環境では npm が使えない/ビルドが動かないことがある。その場合は `bash scripts/check.sh`（ビルドなし）で確認し、**PRのCIが最初のビルド**になる。コード・デザインのPRなら、CI がプレビュー（`<ブランチ名>.fanza-ranking.pages.dev`）も作るので、運営者にスマホで見てもらえる（URL は check の注釈。クラウド環境からは pages.dev が見えない）。見ていないものを「確認した」と書かない。
- 本番に公開されたかは `python3 scripts/wait_run.py deploy <Merge のコミット>`（`deploy.yml` の実行を見る。ビルドと点検とアップロードで10〜15分。`cancelled` は、あとの Merge の公開に含まれたということで、そちらの結果を返す）

## 守ること

1. **main へ直接 push しない。** ブランチ（`claude/...`）→ PR。PRの作成は `gh api repos/juice0402/fanza-ranking/pulls`（REST）を使う（Claude Code環境では GraphQL が使えず `gh pr create` は失敗する）。毎日更新の GitHub Actions（`update.yml`）だけは、データファイルだけを main に直接 commit する。
   - 例外の許可: 予約タスクの**コメント更新PR（`new_releases.json` と、過去作品の `site/src/data/catalog/` の中のファイルと、売り場の `doujin.json`・`game.json`・`anime.json`・`amateur.json`・`cinema.json`・`comic.json`・`photo.json`・`vr.json` と、女優の歩みの紹介文 `actress_stories.json` だけを変えるもの）は、CIが緑なら Claude 自身が Merge してよい**（運営者の許可済み。過去作品のコメントは、2026-10-04 夜に、運営者の「5万件くらい網羅したい」に合わせて加え、報告した。同人・ゲームのコメントは、2026-10-09 に、運営者の「動画35・同人4・ゲーム1の割合で執筆を」に合わせて加えた。新しい売り場のコメントは、2026-10-10 に、運営者の「上限は40のまま、1件ずつ」に合わせて加えた）。同じく、**週のまとめ記事のPR（`roundups.json` だけを変えるもの）も、CIが緑なら Claude 自身が Merge してよい**（運営者の「そっち側でできることは極力やっていい」という包括的な許可にもとづき、2026-10-03 に追加して運営者へ報告した。やめてほしいと言われたら、この文を消す）。**月のまとめ記事のPR（`monthly.json` だけを変えるもの）と、週と月のまとめを1つにしたPR（`roundups.json`・`monthly.json` だけを変えるもの）も同じ**（運営者の希望「月のまとめ記事＋予約タスク」にもとづき、2026-10-07 に追加して運営者へ報告した。2026-10-13 から、月のまとめは毎週月曜の予約タスクが同じPRで書く）。コード・デザインを変えるPRは、運営者に知らせてからMergeする。
2. **秘密情報をコードやログに書かない。** 使うのは GitHub Secrets の `API_ID` / `AFFILIATE_ID` / `GEMINI_API_KEY` と、公開用の `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID`（`deploy.yml` と CI のプレビューだけに渡す）のみ。リポジトリは公開なので、一度でも書くと履歴に残る。Geminiのキーは URL ではなくヘッダ（`x-goog-api-key`）で渡す。
3. **規約の表記を消さない。** 全ページに「広告（アフィリエイト）表記」「18歳確認」「RTAラベル」「Powered by FANZA Webサービス」。AIコメントの注記も残す。`tests/verify_dist.py` が全ページを検査する。
   - **FANZA のクレジットは、DMMの規定のHTMLを1文字も変えない**（DMMアフィリエイト公式の「クレジット表示」の FANZA クレジット・テキスト形式 `Powered by <a href="https://affiliate.dmm.com/api/">FANZA Webサービス</a>`。改変すると API の利用を止められることがある。運営者が公式のページで確かめた。2026-10-07）。`items.js` の `DMM_CREDIT_HTML` を、フッターの `<p class="foot-credit">` に `set:html` でそのまま入れる。class・target・rel を足さない。文節の区切りも入れない（`lib/phrase.js` が `foot-credit` の中を飛ばす）。見た目は CSS の `.foot-credit a` で整える。`tests/verify_dist.py` が全ページで1文字ずつ突き合わせる
   - 「広告」のラベルは、**最初に見える画面（ヘッダーの `pr-chip`）に残す**。くわしい文はフッター。フッターだけにしない（ASPの案内で「ファーストビューに表示」「下部やフッターだけは不適切」とされているため。ステマ規制への対応）。
   - 個々のリンク（出演者検索の「FANZAで全作品を見る」など）や、ボタンの下の「広告｜リンク先は…」の行には、広告の文字を付けない（運営者の希望。見づらくなるため。`tests/verify_dist.py` が、この行が出ていないことを検査）。広告であることは、全ページの**ヘッダーの `pr-chip` とフッター**で示している。これは消さない。
   - 画面に「AI」という表示・言葉は、運営者の希望で出していない（コメントの横のチップ・「AIのひとこと」・トップの「AIがひとこと添えます」など。`tests/verify_dist.py` が検査）。**ただし、コメントが自動で作成されていて正確さは保証できない、という注記は、フッターに必ず残す**（「AI」という言葉は使わず「自動で作成」と書く。読者への正直さのため。「人が書いた」と受け取れる言い方・名前・肩書きは付けない）。
   - 18歳確認（`.gate`）は、**真っ黒ではなく、強いぼかし（曇りガラス）**で後ろを隠す（運営者の希望。2026-10-04）。画面に固定し、開いている間は後ろのページをスクロールさせない（`html.gate-open`・`touch-action: none`）。ぼかしは **18px ほど**にしてある（強くしすぎると、Chromiumで画面のふちの文字がかえって読めてしまう）。ふちを暗くする覆い（`.gate::before`）と、ふだんは「ほぼ真っ黒」にしておき `@supports (backdrop-filter: blur(1px))` の中だけ曇りガラスにする作り（ビルドの道具が `-webkit-` を消すことがあり、古いSafariで薄い色だけが残らないように）・「透明さを減らす」設定のときのほぼ真っ黒も、消さない。`tests/verify_dist.py` が、ビルド後のCSS（色が `#rrggbbaa` に縮められても読める）で検査する。
4. **データを壊さない。** 取得に失敗したら `exit 1` で止まり、既存データは上書きしない（テスト済み）。保存データの形式を変えるときは、`normalize_loaded`（Python）と `normalizeItems`（JS）の両方を直し、**データ本体も新しい形式に移行してから**（`tests/test_data.py` が通ること）、古い形式の読み込み処理は残さない。
5. **変更にはテストを足す。** 挙動を変えたら `tests/` を更新し、`bash scripts/check.sh` を通してから PR にする。
6. Pythonは標準ライブラリのみ（Actionsは Python 3.12）。コードのコメントと画面の文言は日本語。
7. 作品タイトルを Gemini に渡さない（セーフティフィルターでブロックされやすくなるため。出演者・メーカー・形式タグだけ渡す）。週のまとめ記事（`scripts/claude_roundups.py list`）もタイトルを出さない。
   - 例外: **Claude がコメントを書き上げるときだけ**、内容に「さらっと」触れるため、`scripts/claude_comments.py list` が**安全チェックを通ったタイトル**を `title` で出す（運営者の希望。2026-10-04）。**書ける範囲で、できるだけ的確に内容を伝える**（運営者の希望。見に来る人は作品がフィクション・演技だと分かっている）。セクハラ・寝取り・催眠・痴漢・拘束などの同意の無い場面を含む設定も、タイトルを見せて（`fiction_theme: true`）、設定として落ち着いた言葉で書く。**タイトルを出さないのは未成年を連想させる作品だけ**（`title_hidden: true`・`content_off: true`。出演者・メーカー・形式・日付・収録時間だけで書く。フィクションであっても、Claude は未成年の設定を性的な作品として紹介する文を書けないため。運営者に伝え済み。2026-10-04）。幼なじみ・姉妹・母娘・男の娘・女の子・処女のような大人どうしの言葉では未成年あつかいしない。コメントには、行為・体の部位を直接さす言葉・性的暴行や連れ去りの言葉・未成年を連想させる言葉を書かない（`EXPLICIT_WORDS`・`MINOR_WORDS`。`apply` が断る。「女の子」は「女性」と書く）。タイトルの言葉を10文字以上そのまま写すのも断る。FANZAの「商品紹介」の文は、APIに無く（2026-10-04 に本物のAPIで確認）、作品ページの自動取得は robots.txt で禁止されているので使わない
8. **Gemini無料枠は1日20回ほど。** 1回の実行は 新規12＋予約4＋再挑戦4＝20回に収めてある。件数を増やすなら、先に運営者へ「有料枠にするか」を確認する。`get_new_releases.py` の手動実行は1日1回まで（上限に当たると、その日はAIコメントが付かない）。詳細は `docs/design-notes.md`。
   - 品番の取り直し・出演者プロフィール・売れ筋ランキングはFANZA(DMM)のAPIを使い、**Geminiは使わない**ので、この回数に入らない（DMMのAPIには、続けて呼ぶときの待ち時間 `DMM_INTERVAL_SEC` と、連続失敗で中断する決まりを入れてある）。
9. **出演者の個人情報は最小限。** `actresses.json` に保存するのは、FANZA公式のAPIが返す出演者データのうち、表示に使うものだけ。生年月日は年齢の計算のために保存するが、**画面に出すのは年齢と、トップの「誕生日の近い女優」の誕生日の月日だけ**（生まれた年は出さない。月日は運営者の希望で2026-10-05に追加。18〜80歳の範囲外になる値は捨てる）。女優検索の名簿（`actress_directory.json`）も、FANZA公式の出演者検索の一覧だけから作る（運営者の「どこかから情報をとって来れないか」に対し、ほかのサイトの数字は使わないと決めた。2026-10-04）。名前がFANZAに載っていない作品の出演者を、他のサイトや推測で補わない（人違い・特定のおそれがあるため。運営者にも伝えて、この方針にした。FANZAが後から載せたときだけ、自動で入る）。
   - 例外（運営者の判断。2026-10-05）: **所属事務所とSNS（X・Instagram）だけ**は、所属事務所の公式サイトの所属女優のページに載っているものを使う（`agencies.json`。見本を運営者が確かめてから採用）。FANZA の名前と完全に同じ1人に結びつくときだけで、推測はしない。事務所のページにある生年月日・出身地などは保存しない。事務所を足すときは、robots.txt と利用規約を確かめてから（`SITES` と `AGENCIES` の両方に足す）
   - 例外（運営者の希望「イベント情報を、本番に作る」。2026-10-05）: **女優のイベント情報**（事務所が公開しているイベントの予定。日付・時刻・種類・短い見出し・会場の名前）も、所属事務所の公式サイトのイベントの一覧から使う（`events.json`）。出る人の結びつけ方は上と同じく完全一致だけ（見出しの中の名前は、その事務所の所属の人だけ）。住所・電話・料金・画像・本文は保存しない。イベントの一覧を足すときも、robots.txt を確かめてから（`agency_events.py` の `SOURCES`。事務所は `SITES` にある所だけ）

## 変更のしかた（例）

- 表示件数・サイト名・URL・ページを作るジャンル → `site/src/config.js`
- デザイン → `site/src/styles/site.css`、部品は `site/src/components/`、全ページ共通部分は `site/src/layouts/Base.astro`
  - **押せるもの（ボタン・チップ・切り替え・入力欄）の枠と地は `--edge`・`--fill`**（運営者の指摘「黒いボタン系が背景と同化して見づらい」。2026-10-06。枠は背景との明るさの差3:1以上）。パネル・表の罫線は `--line` のまま。新しいボタンを足すときも、この2つを使う
  - **説明文は短く**（運営者の希望「長すぎる説明文は誰も読まないし、サイトを圧迫する」。2026-10-06）: 見出しの下の説明は1文まで。出演者・メーカー・月・ジャンルのページの長い紹介文は画面に出さず（説明文 description にだけ使う）、「48本（2025年5月〜2026年10月発売）」「116本・10月3日〜10月20日発売」の1行（`items.js` の `shortSpan`）。規約・正直さのための注記（○日の時点・自動で作成・公式サイトで確かめて など）は短くしても消さない
  - **あとから出てきて画面がずれる作りにしない**（運営者の「ほかのページでも同じ現象を直して」。2026-10-07）: JavaScript が使えるときだけの部品は、`hidden` にしてスクリプトが出すのではなく、はじめから出しておき、使えないときだけ CSS（`html:not(.js) …`。`js` の印は `Base.astro` の `<head>` が付ける）で隠す（VR・単体のスイッチ・お気に入りのボタン・運命の作品（候補がそろうまで「まわす」は押せない）・予約の「もっと見る」・作品検索・女優検索）。スイッチの押した見た目は `html.hide-vr`・`html.only-solo` でもすぐに出す。データを読んでから出す一覧は、ページを作るときに「はじめの一覧」を入れておく。トップのお気に入りのお知らせは、お気に入りの出演者・メーカーがある人（`html.has-favs`）にだけ、はじめから場所を出す（「★ お気に入りの新作・予約を見る」→ 本数があれば書きかえる）。「お気に入り」ページの「まだお気に入りがありません」も、無い人（`html.fav-none`）には、はじめから出す。**セールの「終わったら隠す」（`public/sale.js`）は、ページの先頭にそのまま入れて（`assets.js` の `inlineScript`。`<script id="sale-early">`）、中身が読み込まれるそばから印を付ける**（前は読み込みのあとで隠していたので、その日に終わった特集・作品が、いちど見えてから消えて下がずれた）
  - **AIっぽさゼロ**（運営者の「サイト作りの原則」。プロジェクトの `claude/site-principles.md`。2026-10-18）: 絵文字（✨✅🚀 など）・右はしの「›」「→」・「おすすめ・ぜひ・便利・簡単・安心・コツ・しましょう・——」は使わない（`tests/test_ai_style.py`・コメントと記事は `text_problems` が断る）。2026-10-22 から、左はしの色の帯・えらんだものだけ色をぬる四角いボタンの切りかえ（→ 申込用紙の「○」「□」と文字）・行の右はしの小さな「見る」・「新作」「NEW」などのシールや札（→ 文字だけ）も使わない。説明の行は1行（見出しの下は全角24字・小さな注記は28字）まで、出どころ・時点・「FANZAで確かめて」の注記（class `note-source`）は2行まで（`verify_dist.py` が注意を出す）
  - **一覧のカードは低く**（2026-10-06）: タイトル2行・ひとこと2行（全文は作品ページ）・FANZAのボタンはカードのいちばん下にそろえる
  - **どんな画面の大きさにも**（運営者の希望。2026-10-05）: 3つ並び（TOP3・いま人気の女優・人気のジャンル・運命の作品・今週のデビュー作・誕生日の近い女優）は、どれも「3等分の列」（`--trio-gap`・`--trio-max`）で、中身は列の幅に合わせて大きさが変わる（丸は列の74%、四角・表紙は列いっぱい。順位の数字・名前は `cqi` で少し大きく）。作品の棚・作品検索の結果・週のまとめの注目の作品は、**置かれた場所の幅で列の数を決める**（コンテナクエリ。`site.css` のいちばん下。使えない古いブラウザには画面の幅の予備）。新しい3つ並びや棚を足すときも、この決まりに合わせる。ページの幅は 1180px（1440px〜は1320px、1760px〜は1440px）、パソコンのトップの右の欄は `clamp(300px, 30%, 380px)`
- コメントの文体・代替文 → `get_new_releases.py`（`ANGLES`/`OPENINGS`/`CLOSINGS`、`HYPE_WORDS`、`template_comment`、`build_prompt`。**切り口・書き出し・結びを作品ごとに変えて、似た文章の量産にならないようにしている**。確かめられない評価が入った答えは採用しない）。Claude が書くコメントの書き方・手順 → `docs/claude-comments.md`。週のまとめ記事の書き方・手順 → `docs/claude-roundups.md`。月のまとめ記事 → `docs/claude-monthly.md`
- 取得する件数・日数 → `get_new_releases.py` 冒頭の定数（`NEW_ITEMS_PER_RUN` など。Geminiの回数上限とセットで考える → 守ること8）

背景・デザインの経緯・API と Gemini で学んだ注意点・今後の予定は `docs/design-notes.md`（大きいので、全部は読まずに検索して、必要な所だけ）。
