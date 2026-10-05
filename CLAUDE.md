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
      保存済み作品の「空だった出演者・ジャンル・サンプル画像・収録時間」「未取得のサンプル動画」を補い、発売日の変更（延期）を反映する（今回の取得に出ていれば refresh_from_fetched、
        出ていなければ品番を指定して取り直し refetch_by_cid。1回20件まで。出演者は発売30日後まで、動画は3回まで。
        ジャンルは、予約の作品にあとから載るので、今回の取得か、出演者・動画の取り直しのついでに入る）
      Gemini でひとことコメントの「下書き」を作成（comment_kind: ai。ブロック時は代替文 template → 次回再挑戦）
      → site/src/data/new_releases.json に作品IDごとにためていく
      出演者のプロフィール（顔写真・体型・生年月日・FANZAの全作品リンク）を女優検索APIで取得（1回30人まで）
      → site/src/data/actresses.json（Geminiは使わない）
      女優検索の名簿（FANZA公式の出演者検索の一覧。体型・身長・生年月日が載っている人。毎日40回×100人ずつ続きから、約5日で一回り）
      → site/src/data/actress_directory.json（Geminiは使わない）
      売れ筋ランキング（FANZAの人気順の上位6本。トップのTOP3は新着の人気順で出し、これは新着の人気順がまだ無いときの代わり）→ site/src/data/ranking.json
      過去作品（FANZAの人気順の上位1.5万本の、発売済みの作品。毎日、その日の上位1,000本を取り直して順位を入れ替え、その下を30回×100本ずつ続きから（約5日で一回り）。
        新着の人気順（最近1週間の発売の、その日の上位500本）も取り、持っていない作品は過去作品に足す。
        2回続けて一回りで見かけなかった作品（人気の上位から外れた作品）は外す。Claude がコメントを書いた作品は残す。new_releases.json にある作品は入れない）
      → site/src/data/catalog/YYYY-MM.json（発売月ごと・1作品1行。Geminiは使わない。コメントは無し）・順位は catalog_rank.json・続きの場所は catalog_state.json
      → site/src/data/popularity.json（新着の人気順・前の日の新着の人気順・毎日の更新の作品の全体の人気順の順位）・sale.json（その日に見かけたセール・キャンペーン中の作品）
      予約の人気順の上位30本（きょうの話題に使う）と、FANZA動画の日ごとの発売本数7日分・予約受付中の本数（いまは画面に出していない）→ site/src/data/today.json（Geminiは使わない）
  → scripts/agency_links.py --update（週1回。前に集めてから7日たった日だけ。失敗しても更新は止めない）
      所属事務所とSNS（13の事務所の公式サイトの、所属女優の一覧とプロフィールのページ。robots.txt を守り、同じサイトへは2秒ずつ間をあける。事務所どうしは同時に読む）
      → site/src/data/agencies.json（FANZAの名前と完全に同じ1人に結びついた人だけ。Geminiは使わない）
  → main に commit → Cloudflare Pages が自動ビルド（Astro, 静的サイト）→ 公開

Claude の予約タスク（毎日 0:20 JST。手順は docs/claude-comments.md）
  → まず、今日の更新が済んでいるかを確かめる（scripts/already_updated.sh。GitHubの定時実行は数時間遅れることがある。
    まだなら、更新を手動実行で動かして待つ。遅れて来た定時実行は、済んでいるのを見て何もしない＝Geminiを二重に使わない）
  → Gemini の下書き・定型文のままの作品と、発売日をすぎたのに「予約」「発売されます」などの言い方が残る作品と、仕上げたあとに出演者・収録時間・ジャンルが増えた作品（info_added）を、Claude が読み直して完成した文章（2〜3文・100〜160文字。内容にさらっと触れる）に書き上げる。
    枠（1日40件）が余ったら、コメントがまだ無い過去作品（catalog/）を、人気順の順位が上の作品から書く（コメントが付くと、その作品ページが検索エンジンに出る）
    （comment_kind: claude。scripts/claude_comments.py。1回40件まで）
  → ブランチ+PR → CIが緑ならMerge → 公開

Claude の予約タスク（毎週月曜 0:50 JST。手順は docs/claude-roundups.md）
  → 前の週（月〜日）に発売された作品の「週のまとめ記事」を Claude が書く（scripts/claude_roundups.py）
  → site/src/data/roundups.json に追加 → ブランチ+PR → CIが緑ならMerge → /weekly/ に公開
```

## フォルダ

| 場所 | 役割 |
|---|---|
| `get_new_releases.py` | 毎日の更新スクリプト。Python標準ライブラリだけ（pip不要） |
| `scripts/claude_comments.py` | Claude がコメントを書き上げるための道具（`list` で対象と下書き・使える事実を出し、`apply` で点検して書き込む。書いたものは `comment_kind: "claude"`。確かめられない評価・古くなる言い方・下書きと同じ文は断る）。毎日の更新の作品を先に、枠（1日40件）が余ったら、コメントがまだ無い過去作品（`catalog/`）を人気順の順位が上の作品から出し（順位そのものは出さない）、そのファイルに書き込む。標準ライブラリだけ |
| `scripts/agency_links.py` | **所属事務所とSNS**（運営者の希望。2026-10-05）。13の事務所（ティーパワーズ・マインズ・バンビプロモーション・SO MODELAGENT・プロダクションALIVE・エスフラート・カプセルエージェンシー・C-more ENTERTAINMENT・LIGHT promotion・ライフプロモーション・LINX・NAX・Duo Entertainment）の公式サイト（robots.txt で止められていない・所属女優の一覧がある所。`SITES`。日本プロダクション協会の加盟社などから下調べ）から、所属女優の名前・X・Instagram を集める（SNS が無い人も所属は付ける）。事務所の側の名前は、一覧のリンクの文字（ローマ字は外す）・決まった形の文字（`label_name`）・決まった見出し（`name_prefix`）・決まった形のページのタイトル（`title_name`）のどれか1つ。プロフィールの横に全員が並ぶ事務所は `via_profile`。**事務所の側の名前（プロフィール1つにつき1つ）の全体が、FANZA の名前（かっこの前）と完全に同じで、FANZA に同じ名前が1人だけのときだけ**結びつける（名前の一部・前の名前・ページの中のほかの見出しでは合わせない。日本語で2文字まで・ローマ字だけで4文字までの短い名前は結びつけない）。事務所のアカウント・2人以上のページに出るSNSは外す。読めない・前の半分も読めない事務所は前の情報を残し（30日まで）、読めた事務所の一覧から消えた人は消す。毎日の更新から `--update`（7日ごと）、「Refresh FANZA Data」の「所属事務所」を 1 にすると `--force`。標準ライブラリだけ。`tests/test_agencies.py` |
| `scripts/already_updated.sh` | 今日（日本時間）の「データ更新」が、もう記録に入っているかを調べる（済んでいれば 0）。毎日の更新の定時実行（遅れて来たときに二重に動かない）と、0:20 の予約タスク（更新が遅れていたら先に動かす）が使う |
| `scripts/claude_roundups.py` | Claude が週のまとめ記事を書くための道具（`list` で週の作品データを出し、`apply` で点検して `roundups.json` に書き込む）。標準ライブラリだけ |
| `site/` | サイト本体（Astro 7 / 静的出力）。Cloudflare Pages のビルド対象 |
| `site/src/config.js` | **サイト名・URL・表示件数の設定はここだけ**（独自ドメイン化もここ）。月・ジャンルのページの最低本数と、ページを作るジャンルの一覧（`TAG_PAGE_GENRES`）もここ。サイト全体のファイル数の上限（`FILE_BUDGET`。Cloudflare Pages の無料プランは2万ファイルまで）と、出演者・メーカーのページ・一覧に並べる最大数（`ENTITY_LIST_LIMIT`・`INDEX_LIST_LIMIT`。女優検索の、JavaScriptが使えないとき用の一覧は `ACTRESS_FALLBACK_LIMIT`＝150人。ふだんは隠れるので少なめ）もここ。一覧のカードに出す出演者は3名まで（`CAST_LIMIT`。オムニバスなどは「ほか○名」。`items.js` の `castLine`。作品検索・お気に入りの画面も同じ3名） |
| `site/src/lib/plan.js` | **サイトのファイル数の計画**（画面に依存しない。`tests/test_plan.mjs`）。過去作品（カタログ）が増えても2万ファイルをこえないよう、作品ページは「①毎日の更新で載せた作品 ②コメントのある過去作品 ③そのほかの過去作品、同じ中では、過去作品は人気順の順位が上の作品から（`catalog_rank.json`。順位が分からなければ新しい順）」に、残りの枠の数だけ作る（`planPages`）。**作品ページの無い作品は、一覧からFANZAへ直接リンクする**（`itemHref`）。コメントの無い作品ページ・コメントのある作品が1本も無い一覧は noindex で sitemap にも入れない（`itemIndexable`・`listIndexable`。FANZAの情報を並べただけのページを検索エンジンに出さないため）。出演者・メーカーの発売日カレンダー（.ics）は、新作・予約が載っている人だけ（`hasCalendar`） |
| `site/src/lib/popularity.js` / `site/src/pages/ranking/` | **人気ランキング**（画面に依存しない部品は `tests/test_popularity.mjs`）。`/ranking/`＝新着の人気順（最近1週間に発売された作品を、その日の人気順に100本）、`/ranking/all/`＝全体の人気順（発売済みの作品を、その日の人気順に100本）。順位は、過去作品は `catalog_rank.json`、毎日の更新の作品は `popularity.json`（`popAll`・`popNew`）。作品検索（`/search/`）でも「人気順（新着）」「人気順（全体）」で並べ替えられる（索引の `r`・`n`。索引には全体の人気順の上位1,000本を先に入れる）。FANZAの「デイリーランキング」のページそのものはAPIに無く、自動で読むのも禁止なので使わない。トップのTOP3は、新着の人気順の先頭（下の `topics.js`） |
| `site/src/lib/topics.js` / `site/src/components/TopThree.astro`・`HotActresses.astro`・`HotGenres.astro`・`TopicList.astro`・`PickCorner.astro` | **トップの「きょうの〜」**（運営者の希望「訪れるたびに新しい情報を」。2026-10-04 夜。画面に依存しない部品は `tests/test_topics.mjs`）。トップは「きょうのFANZA新作」の見出し（更新した日付）→ **きょうの新着人気TOP3**（`topEntries`＝新着の人気順の先頭6本。画面に出すのは3本。🥇🥈🥉のメダルで、スマホでも横に3本。**メダルは小さく、表紙の左下のふちに半分かける**（顔を隠さない。2026-10-05）。発売日はメダルの横、前の日からの順位の動き `rankMove`＝▲3・▼1・→・初登場は、表紙の右上のふちの小さな札。新着の人気順がまだ無いあいだは `ranking.json` の売れ筋で代わりにする）→ **いま人気の女優**（`hotActresses`。この1週間の発売で新着の人気順100位までの作品（出演者4人までの作品だけ）に「101−順位」の点を足した上位3人。**顔写真がある人だけ**（順位は繰り上がる）。顔写真の丸と名前だけで、選んだ理由（本数・順位）は書かない（運営者の希望）。「顔」という言葉は運営者の希望で使わない。VR作品を隠すときは、VR作品を数えない並びに入れかえる。2026-10-05）→ **人気のジャンル**（`hotGenres`。いま人気の女優と同じ点を、ジャンルごとに足して上から3つ。数えるのは `TAG_PAGE_GENRES`（ベスト・総集編は除く）のジャンルだけ。表紙を四角く切り出した札・順位・名前。タップでジャンルのページ。運営者の希望。2026-10-05）→ **きょうの話題**（`buildTopics`。急上昇・きょう発売・予約で人気・予約に初登場・週のまとめ・セール開始（きのう・きょう始まった特集で、このサイトの作品が3本以上）・もうすぐ終わるセール。セールの話題は `/sale/#sale-番号`（その特集の見出し）へ。最大8件。画像は表紙か出演者の顔。文はデータで決まった形だけで、評価の言葉は書かない。TOP3の作品は出さない。**話題の作品がVR作品なら、同じ種類のVRでない次の作品（`alt`→`.topic-alt`）も入れておき、「VR作品を隠す」のときはそれに繰り上げる**）→ 作品を探す → セール中の特集 → 発売中（**いちばん新しい日付のすぐ下に、おすすめのコーナー**＝`PickCorner.astro`: 運命の作品 → 今週のデビュー作（`weekDebuts`。7日間の「デビュー作品」を人気順に3本。VR・単体の絞り込みで差し替え）→ 誕生日の近い女優（`birthdaySoon`。このサイトに作品があり、顔写真と誕生日が分かる人で、14日のうちに誕生日が来る人を近い順に3人。月日だけ出す））→ 予約。**パソコン（960px〜）は2列**（運営者の希望「右のカラム（きょうの話題）の下に全て並べる」「作品を探すも右のカラムの上に」「週のまとめは概要だけ・月のまとめはバックナンバー形式で」。2026-10-05）: 見出しは横いっぱい、左に「TOP3 → セール中の特集 → 発売中 → 予約」、右の欄（`.home-side`）に「作品を探す → きょうの話題 → いま人気の女優 → 人気のジャンル → **週のまとめ**（`SideWeekly.astro`。いちばん新しい週の、はじめの1文 `roundupSummary` と注目の作品の表紙3枚 `roundupCovers`（VRでない作品）だけ。くわしくは記事のページ。前の3週はリンク）→ 運命の作品 → 今週のデビュー作 → 誕生日の近い女優 → **月のまとめ**（`SideMonths.astro`。きょうの月までの月のページを、新しい月から12か月のバックナンバー）」。週のまとめ・月のまとめの欄（`.side-only`）はパソコンだけで、スマホは「作品を探す」の「週のまとめ」「月ごと」のリンク（`.only-narrow`。パソコンでは隠す）。きょうの話題の「週のまとめ」も、パソコンでは隠す（専用の欄があるため）。右の欄の3つ並びは、どれも同じ3列で縦の線がそろう（欄の間は細い線。点線の囲みは、スマホのときだけ）。右の欄は、左の欄の行をまたいで伸ばす（`.home` の `--side-span`＝左の欄の欄の数。`index.astro` が数える）。**おすすめのコーナー（`#pick-corner`）は、HTMLではスマホの場所（発売中のいちばん新しい日付の下。`#corner-home`）にあり、パソコンのときだけ、すぐ後ろの小さなスクリプト（`CORNER_MOVE_JS`）が右の欄の `#side-corner` へ移す**（読みながら動かすので表示がずれない。幅が変われば戻す）。スマホの並びは前と同じ（右の欄の中の並びは CSS の `order`）。左の欄の棚は3列（1100px〜は4列）。「きょうの数字」（発売本数の欄）は、運営者の判断で外した（2026-10-05。`today.json` の本数は集め続けているが、画面には出さない） |
| `site/src/lib/gacha.js` / `site/public/gacha.js` | **運命の作品**（トップの、発売中の新作の、いちばん新しい日付のすぐ下。運営者の希望「上から見ていって、作品が決まらなかった人にオススメしたい」「スロットマシンみたいに3本」。2026-10-05。部品は `tests/test_gacha.mjs`）。候補は、ひとことコメントと作品ページのある発売済みの作品を、人気の高い順に80本（`gachaPool`。ページの中の `#gacha-data` に小さなJSONで入れる）。「まわす」で3つの窓の表紙が回り、左から順に止まって3本が決まる（動きを減らす設定なら、すぐ出す）。直前の9本は続けて出さない。「VR作品を隠す」のときはVR作品を、「単体作品のみ表示」のときは単体でない作品を外す。**未成年を連想させるタイトルの作品は候補に入れない**（こちらから勧める欄のため。判定は `claude_comments.py` の `title_block_reason` と同じ言葉の一覧で、テストで突き合わせている）。JavaScript が使えないときは欄ごと出さない |
| `site/src/lib/sale.js` / `site/src/pages/sale/` / `site/public/sale.js` | **セール・キャンペーン**（部品は `tests/test_sale.mjs`）。`/sale/`＝はじめに特集（キャンペーン）への目次、特集ごとに、終わりが近い順、**このサイトの作品から数えた「おもなメーカー・よく出ている女優（出演者4人までの作品で2本以上）・多いジャンル（`contentGenres`＝`TAG_PAGE_GENRES` からベスト・総集編を除いたもの）」**（`campaignSummary`。運営者の希望「何の特集で、どういう関連作品がセールなのか知りたい」。2026-10-05）と、人気の高い作品から12本（札は「○%OFF」、価格は「1,884円〜（通常2,692円〜）」）。見出しの id は `sale-キャンペーンの番号`（`saleAnchor`）。トップの「作品を探す」の下に**「セール中の特集」**（`SaleCampaigns.astro`。特集ごとのカード＝名前・いつまで（きょう・あすなら札）・本数・おもなメーカー・人気作品の表紙を3枚重ねた束・名前にある「○%OFF」の赤札。先頭4枚を見せ、終わった特集が隠れたら次が繰り上がる＝`data-sale-show`・`sale-more`）、フッターにリンク。データは `sale.json`（その日の 0:05 ごろの情報なので、「○日の時点」「くわしくはFANZAの作品ページで」を必ず添える）。終わりの時刻（`data-sale-end`）をすぎたキャンペーンは、ブラウザで隠す（`public/sale.js`。ビルドは1日1回のため）。FANZAのAPIが教えてくれるのは特集の名前・期間・価格だけで、特集の説明文やニュース（新人・専属・引退など）は無い（ページの自動取得も禁止）ので載せない |
| `site/src/lib/agencies.js` | 所属事務所とSNSの部品（画面に依存しない。`tests/test_agencies.mjs`）。事務所の名前・公式サイトは `AGENCIES` だけ（`agency_links.py` の `SITES` とテストで突き合わせ）。`normalizeAgencies`（出どころが事務所の公式サイトでない行・アカウント名の形が違うSNSは捨てる。同じ名前が2行なら使わない）、`withAgencies`（女優検索の索引の `g`・`agencies`）。出演者のページに「所属」（事務所のページへのリンク）と「SNS」（`x.com/…`・`instagram.com/…/` の「X（公式）」「Instagram（公式）」。`rel="nofollow noopener noreferrer"`）と、出どころの注記（「○月○日時点」）。女優検索に「所属事務所」の絞り込みと、結果の「所属：○○」 |
| `site/src/lib/items.js` / `site/src/lib/assets.js` | 並べ替え・日付・sitemap/robots・出演者/メーカーのまとめ・構造化データ（JSON-LD）など、テストできる部品（画面に依存しない）。**小さな表紙** `smallImage`（FANZAの …pl.jpg → 表紙だけの …ps.jpg。きょうの話題・セール中の特集・今週のデビュー作・運命の作品・作品検索の結果に使う。無ければ `SMALL_IMG_ONERROR` でパッケージ画像に戻す。大きなカード・TOP3・作品ページはパッケージ画像のまま）。`assets.js` の `assetUrl` は、`public/` のスクリプトのURLに中身から作った印（`/vr-filter.js?v=1a2b3c4d`）を付ける（`_headers` で1年キャッシュにするため。スクリプトを読むときは必ずこれを通す。`tests/verify_dist.py` が全ページで印と中身を突き合わせる） |
| `site/src/lib/roundups.js` | 週のまとめ記事の部品（週の計算・集計・読み込み・Article構造化データ・トップの右の欄の概要 `roundupSummary`・表紙 `roundupCovers`・短い期間 `weekRangeShort`。画面に依存しない）。記事のページ（`weekly/[week].astro`）の注目の作品は、横長のカード（`.pick-card`。小さな表紙・タイトル・出演者/メーカー/発売日・ひとこと・FANZAへ。運営者の指摘「とても読みづらい」。2026-10-05）、その週の全作品は作品検索の結果と同じ行（`.ws-row`）。集計は `claude_roundups.py` の `week_stats` と同じ数え方（`tests/test_roundups.mjs` で突き合わせている） |
| `site/src/lib/favorites.js` / `site/src/lib/calendar.js` | お気に入りの索引（`/data/favorites-index.json`）と、発売日カレンダー（`.ics`）の部品（画面に依存しない。`tests/test_calendar.mjs`）。カレンダーの予定の**題名に作品タイトルを入れない**（「【発売】○○の新作」。タイトル・品番・リンクは説明に入れる）。`escapeIcsText` は `;` `,` `\` 改行を書き換える |
| `site/public/favorites.js` / `site/public/lightbox.js` | ブラウザで動く小さなスクリプト（ビルドを通さずそのまま配信）。`lightbox.js` はサンプル画像・パッケージ写真の拡大表示（前・次のボタンと枚数は、画像に重ならないよう、画像の下の帯 `.lightbox-bar` に。運営者の希望。2026-10-05）。`favorites.js` は ☆ の付け外しと「お気に入り」ページ・トップのお知らせ（**保存先は端末の localStorage だけ。サーバーには送らない**）。部品は node でテストできる（`tests/test_favorites.mjs`）。DOM は `textContent` で作り、保存データの HTML は実行しない |
| `site/src/lib/search.js` / `site/public/search.js` | 作品検索（`/search/`）。`search.js`（lib）は索引 `/data/items-index.json`（キー: c 作品ID / p 品番（例 DLDSS-566。作れないときは無い）/ t タイトル（文節の区切り U+200B 入り）/ d 発売日 / a 出演者 / m メーカー / g ジャンルの番号 / v VRなら1 / i 画像（決まった形 `digital/video/作品ID/作品IDpl.jpg` なら項目ごと省く。ブラウザの `rowImage` が戻す。索引を軽くするため）。新しい順に最大3000本）を作る。`public/search.js` は、キーワード（タイトル・出演者・メーカー・品番（「-」の有無は問わない）・ジャンル）・ジャンル（タグ。複数はAND。足すと0本になるものは押せない）・発売の状態で端末の中で絞り込み、条件を URL（`?q=&tag=&st=&sort=`）にも書く（トップの検索欄は `?q=` を送るふつうのフォーム）。ジャンル・発売・並び順は `details` にたたむ（スマホでは閉じる）。結果は、小さな表紙＋タイトル・出演者・発売日の行（`.ws-row`。スマホ1列・640px〜2列）。パソコン（960px〜）は、左に条件（画面に固定 `.search-side`）・右に結果（`.search-layout`。女優検索も同じ）。説明は1文だけ（運営者の希望「スマホで説明・情報が多すぎる」。2026-10-05）。`noindex`・sitemap なし。DOM は `textContent` で作る。部品は `tests/test_search.mjs` |
| `site/public/vr-filter.js` / `site/src/components/VrToggle.astro` | 「VR作品を隠す」「単体作品のみ表示」スイッチ（2つ並べる。単体作品のみは運営者の希望。2026-10-05。単体作品＝ジャンル「単体作品」、ジャンルがまだ無い作品は出演者1人。`items.js` の `isSoloWork`。一覧のマスに `data-solo`（`filterAttrs`）、`html.only-solo` のとき `data-solo` の無いマスを隠す。状態は localStorage（`only-solo`）。作品検索は索引の `o:1`。きょうの話題・いま人気の女優には効かない）。**スイッチの文字は、押しても変えない**（「VR作品を隠す」「単体作品のみ」のまま。押した状態は黄色い枠と印。文字が変わって幅が変わり、急に改行したため。運営者の指摘。2026-10-05）。以下は「VR作品を隠す」の説明（単体作品のみも同じ仕組みで、TOP3・今週のデビュー作の差し替え・日付ごとの本数「（単体作品のみ）」にも効く）。一覧の1マス（`li.shelf-cell`）の `data-vr`（`filterAttrs(item)`）を、`html.hide-vr` のとき CSS で隠す。状態は localStorage（`hide-vr`）だけ。`Base.astro` の `<head>` で先に印を付けてチラつきを防ぐ。VR判定は `items.js` の `isVrWork`（タイトルの【VR】・形式タグ・ジャンルの「VR」のどれか）。トップ・過去の作品・出演者/メーカー・検索にスイッチがある。VR作品のページ（`/tag/`）では隠さない（`DaySection` の `keepVr`）。全部がVRになりうるまとまり（作品ページの「同じ出演者・メーカーの作品」など）には `data-vr-group` を付け、全部隠れたら見出しごと隠す。トップのTOP3は、データに6本あり、画面に出すのは先頭の3本（`config.js` の `RANKING_SHOWN`。残りは `rank-off` で隠してある）。隠すときは `rankLayout` が、VRを除いた先頭3本に差し替える（順位の数字も1・2・3にふり直し、見出しに「VRを除く」と出す）。`.rank-podium` の `data-visible`（見えている本数）と、メダルの色の `data-place`（見えている中で1 金・2 銀・3 銅）も付け直す（`tests/test_search.mjs`）。きょうの話題は、VR作品の話題が隠れ、すぐ後ろの繰り上げ（`.topic-alt`。ふだんは隠れている）が出る |
| `site/src/lib/profiles.js` | 出演者のプロフィール（顔写真・年齢・体型・誕生日の月日 `birthMD`）・女優検索の索引（`/data/actresses-index.json`。名簿＋このサイトの出演者。`{generated, img, list, actresses:[{n,r,id,s,k,i,a,h,b,c,wa,hi,l}]}`、空の値は書かない）・売れ筋ランキングの表示用の整え方（画面に依存しない。`tests/test_profiles.mjs`）。生年月日は年齢と誕生日の月日にだけ変えて、生まれた年は持ち出さない。URLは FANZA(DMM) の https だけ通す |
| `site/src/lib/phrase.js` / `site/src/integrations/phrase-breaks.js` / `site/src/lib/budoux-ja.js` | **日本語の文章を文節で改行させる**仕組み（運営者が見つけた「あ／り」のような語の途中の改行を、全ページ・全箇所で防ぐ）。iPhone/iPadのSafari系には、CSSの `word-break: auto-phrase` が無い（2026-10に確認）ため、**ビルドの最後に（Astro の拡張 `phraseBreaks`、`astro:build:done`）、できあがった全HTMLの日本語の文章へ、文節の区切り `<wbr>` を足し、`<span class="ph">` で包む**。CSS（`site.css` の `.ph`）が `word-break: keep-all`・`line-break: strict`・`overflow-wrap: anywhere`。文節はBudouX（Google・Apache-2.0。モデルは `budoux-ja.js`、ライセンスは `budoux-LICENSE.txt`）で決め、禁則・英数字・中黒・かっこ・長すぎる文節（8文字超は分ける）を足してある。script・style・title・textarea・button・pre・code・noscript・svg・select は触らない。**ページに手で印を付ける必要は無い**（コメントなど、あとから増える文章も自動）。**出演者名・メーカー名（作品データ・過去作品から集める。数万あっても速いよう、`namesPattern` は先頭2文字と長さで引く表）の途中には区切りを入れず、10文字までの名前は `<span class="nb">`（nowrap）で包む。伏せ字（○●）・数字と単位も離さず、「～」は前の1文字と一緒に包む。** ブラウザで作る文章（検索結果・お気に入り）は、索引のタイトルに U+200B（区切り）・U+2060/U+00A0（「～」の前の改行止め）を入れて `.ph-js` で表示（`phraseZwsp`）。出演者検索の結果は対象外。開発サーバー（`npm run dev`）では動かない（ビルドしたときだけ）。`tests/test_phrase.mjs`、`tests/verify_dist.py`（`read()` は区切りを外して読み、区切りそのものは専用の検査）。画面に出る文字は変えない |
| `site/public/actress-search.js` / `site/public/movie.js` | ブラウザで動く小さなスクリプト。`actress-search.js` は `/actress/` の「条件で探す」（名前・年齢・身長を下限〜上限の数字で・**スリーサイズは幅（〜79・80〜84 など。`profiles.js` の `SIZE_BUCKETS`）をタップで、いくつでも**（運営者の希望「何センチと言われてもサイズ感が分からない」。2026-10-05。見出しの下に、いちばん人数の多い幅を目安として出す）・カップは複数選択・所属事務所（`ag`）・作品がある人/顔写真がある人だけ・並び順11通り。索引を読んで、端末の中で絞り込み、条件を URL にも書く）。`movie.js` は作品ページのサンプル動画の枠の拡大・縮小（FANZAの再生ページの iframe を、ページを開いたときから入れておく。「押してから読み込む」形は、iPhone で2回押しになったのでやめた。画質は変えられない → `docs/design-notes.md`）。部品は node でテストできる（`tests/test_profiles.mjs` / `tests/test_movie.mjs`）。DOM は `textContent` で作る |
| `site/public/_headers` / アイコン | Cloudflare Pages の応答ヘッダー（nosniff・フレームへの埋め込み禁止など。CSP は最小限。`/_astro/*` と `/*.js`（`assetUrl` で中身の印 `?v=` を付けて読む）は1年キャッシュ、アイコンは1週間）と、サイトのアイコン（`favicon.svg` / `favicon.ico` / `apple-touch-icon.png`）。`tests/verify_dist.py` が、全ページの `<head>`・ヘッダーの広告ラベル（`pr-chip`）とフッターの広告文・18歳確認・クレジット・FANZAへのリンクの属性と一緒に検査する |
| `site/src/components/` | 画面の部品。`Face`（出演者の顔の丸。写真が無い・読み込めないときは頭文字）、`SampleMovie`（FANZAのサンプル動画の枠）、`TopThree`（トップのメダルのTOP3）など |
| `site/src/lib/facts.js` / `site/src/lib/collections.js` | SEOのための部品（画面に依存しない。`tests/test_seo.mjs`）。`facts.js` は作品ページの「この作品のデータ」欄（掲載データを数えた事実だけ。評価の言葉は書かない。収録時間の長さくらべは、運営者の判断で出さない。収録時間そのものは作品ページの基本情報に出す）と、作品IDから作る**品番**（`productCode`。形がはっきりしたものだけ。作れないときは出さない）。`collections.js` は月ごとのページ（`/month/YYYY-MM/`。5本以上の月）とジャンルのページ（`/tag/<ハッシュ>/`。3本以上。**作るのは `config.js` の `TAG_PAGE_GENRES` にあるジャンルと「VR作品」だけ**。過激・未成年を連想させる名前は入れない） |
| `site/src/lib/data.js` | JSON読み込み。`curated`（毎日の更新で載せた作品）/`catalog`（過去作品）/`all`（両方）/`released`/`upcoming`（curated だけ）/`allReleased`/`paged`（作品ページを作る作品）/`roundups`/`ranking`/`profilesByName`/`actressSearchIndex` などを各ページに渡す。トップ・月/ジャンルのページ・お気に入り・まとめ記事は curated だけ、過去の作品の一覧・出演者/メーカーのページ・「この作品のデータ」欄は all を使う。`actresses.json`・`ranking.json`・`actress_directory.json` は、まだ無くてもビルドが止まらない（`import.meta.glob` で任意に読む） |
| `site/src/pages/` | トップ、`item/[cid]`（作品）、`archive/[page]`（過去作品）、`actress/`（出演者別。2本以上の人だけ）、`maker/`（メーカー別。2本以上だけ）、`month/`（月ごと）、`tag/`（ジャンルごと）、`weekly/`（週のまとめ記事。1本も無いあいだは一覧が noindex・sitemap にも入らず、リンクも出さない）、`favorites`（お気に入り。noindex）、`calendar/`（使い方のページ＋購読用の `.ics`。使い方は noindex）、`data/favorites-index.json.js`、`data/actresses-index.json.js`（出演者検索の索引）、404、`sitemap.xml.js`、`robots.txt.js` |
| `site/src/data/new_releases.json` | **自動更新のデータ。手で編集しない**（作品IDごとに蓄積。`updated` は、その作品のコメントを最後に変えた日で、sitemap の `lastmod` に使う） |
| `site/src/data/actresses.json` | **自動更新のデータ。手で編集しない**（出演者のプロフィール。`{actresses:[…], unmatched:{名前:探した日}}`。体型は数字・生年月日は年齢と誕生日の月日の計算用で、画面に出すのは**年齢と、トップの「誕生日の近い女優」の月日だけ**。血液型・趣味・出身地は**保存しない**。名前の完全一致が1人だけのときだけ採用し、推測で選ばない） |
| `site/src/data/agencies.json` | **自動更新のデータ。手で編集しない**（`scripts/agency_links.py --update` だけが書く。`{updated, sites:[{key, checked, profiles}], rows:[{name: FANZAの名前, id, agency, x, instagram, source: 出どころのページ, seen}]}`・1人1行。事務所のページにある生年月日・出身地・画像・文章は保存しない） |
| `site/src/data/actress_directory.json` | **自動更新のデータ。手で編集しない**（女優検索の名簿。FANZA公式の出演者検索の一覧から、`{cursor, cycle_done, cycle_start, prev_cycle_start, rows:[…]}`。1人1行・id の順。持つのは id・名前・読み・顔写真のファイル名・体型・身長・生年月日・最後に見かけた日（seen）だけ。約5日の一回りを2回続けて見かけなかった人（FANZAから消えた・数字が消された人）は外す。体型も身長も生年月日も無い人は入れない。18歳未満・80歳をこえる生年月日は捨てる） |
| `site/src/data/catalog/YYYY-MM.json` | **過去作品（カタログ）。自動更新のデータ。手で編集しない**（`get_new_releases.py` の `update_catalog`。発売月ごとのファイル・1作品1行。作品の形は `new_releases.json` と同じで、コメントは無し（`comment_kind: "none"`・空）か、あとから Claude が書いたもの（`"claude"`）だけ。サンプル画像は8枚まで。まだ無くてもビルドは止まらない。同じ作品が `new_releases.json` にあれば、そちらを使う（毎日の更新が、過去作品から外す）。続きの場所は `catalog_state.json`（`{cursor, cycle, cycle_done, limit, items}`）。作品ごとの人気順の順位は `catalog_rank.json`（`{cid: [順位, 最後に見かけた一回りの番号]}`・1作品1行。毎日書きかわるのは、こちらの小さな行だけ）） |
| `site/src/data/popularity.json` / `site/src/data/sale.json` | **自動更新のデータ。手で編集しない**。`popularity.json`＝`{date, new: {cid: 新着の人気順の順位}, all: {毎日の更新の作品の cid: 全体の人気順の順位}, prev_date, prev: {前の日の新着の人気順（上位200本）}}`（1作品1行。取れなかった日は前の日のまま）。`today.json`＝`{date, daily: [{d, n: その日の発売本数}×7], upcoming_total, upcoming: [{c, t, d, a, m, i, u, r, v}×30（予約の人気順）], prev_upcoming: [前の日の予約の人気順の作品ID]}`。`sale.json`＝`{date, campaigns: [{title, begin, end}], items: [{c, k: キャンペーンの番号, p: 価格, l: 定価}]}`（FANZA公式のAPIの `campaign`・`prices` から、その日に見かけたセール中の作品。今日が期間に入っているキャンペーンだけ。値引きが確かめられないときは価格を入れない） |
| `site/src/data/ranking.json` | **自動更新のデータ。手で編集しない**（売れ筋ランキング上位6本。トップのTOP3は、新着の人気順がまだ無いときだけ、これで代わりにする。各行の `vr` は、取得のときにジャンルなどから判定した「VR作品か」。取得に失敗したら前回のものを残す） |
| `site/src/data/roundups.json` | **Claude が毎週書き足す記事のデータ。手で編集しない**（`claude_roundups.py apply` だけが書く。新しい週が先頭） |
| `tests/` | テスト一式。`fixtures/` は固定データ（本番データには依存しない） |
| `scripts/check.sh` | テストをまとめて実行（`--build` でビルドと点検まで） |
| `.github/workflows/` | `update.yml`（毎日の更新）、`ci.yml`（PRごとの自動確認）、`refresh-data.yml`（取り直しだけを手動で動かす。Geminiは使わない。ブランチを選んで実行すると、本物のAPIでの確認に使える。「名簿の一覧を取る回数」を増やすと、女優検索の名簿を、「過去作品の一覧を取る回数」（上位1,000本より下を取る回数。最大500。1.5万本なら140回で一回り）を増やすと、過去作品を一気に集められる）、`probe-api.yml`（APIの応答の形を調べる道具。`scripts/probe_api.py`。結果は個人情報を伏せて注釈に出す） |
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
  - **Geminiを使わずに、取り直しだけ**したいときは `python get_new_releases.py --refresh-only`（Actions では「Refresh FANZA Data」）。新しい作品の追加もAIコメントもしないので、Geminiの無料枠を使わない。`ACTRESSES_PATH` / `RANKING_PATH` で出演者データ・ランキングの書き込み先も変えられる。
- 本番サイトを WebFetch で確認するときは、URLの末尾に `?cb=日時` を付ける（付けないと、前に取得した古い内容が返ってきて、更新されていないように見えることがある。2026-10-03 の仮運転で確認）。
- Claude のクラウド環境では npm が使えない/ビルドが動かないことがある。その場合は `bash scripts/check.sh`（ビルドなし）で確認し、**PRのCIとCloudflareのプレビューが最初の本番ビルド**になる。見ていないものを「確認した」と書かない。

## 守ること

1. **main へ直接 push しない。** ブランチ（`claude/...`）→ PR。PRの作成は `gh api repos/juice0402/fanza-ranking/pulls`（REST）を使う（Claude Code環境では GraphQL が使えず `gh pr create` は失敗する）。毎日更新の GitHub Actions（`update.yml`）だけは、データファイルだけを main に直接 commit する。
   - 例外の許可: 予約タスクの**コメント更新PR（`new_releases.json` と、過去作品の `site/src/data/catalog/` の中のファイルだけを変えるもの）は、CIが緑なら Claude 自身が Merge してよい**（運営者の許可済み。過去作品のコメントは、2026-10-04 夜に、運営者の「5万件くらい網羅したい」に合わせて加え、報告した）。同じく、**週のまとめ記事のPR（`roundups.json` だけを変えるもの）も、CIが緑なら Claude 自身が Merge してよい**（運営者の「そっち側でできることは極力やっていい」という包括的な許可にもとづき、2026-10-03 に追加して運営者へ報告した。やめてほしいと言われたら、この文を消す）。コード・デザインを変えるPRは、運営者に知らせてからMergeする。
2. **秘密情報をコードやログに書かない。** 使うのは GitHub Secrets の `API_ID` / `AFFILIATE_ID` / `GEMINI_API_KEY` のみ。リポジトリは公開なので、一度でも書くと履歴に残る。Geminiのキーは URL ではなくヘッダ（`x-goog-api-key`）で渡す。
3. **規約の表記を消さない。** 全ページに「広告（アフィリエイト）表記」「18歳確認」「RTAラベル」「Powered by FANZA Webサービス」。AIコメントの注記も残す。`tests/verify_dist.py` が全ページを検査する。
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

## 変更のしかた（例）

- 表示件数・サイト名・URL・ページを作るジャンル → `site/src/config.js`
- デザイン → `site/src/styles/site.css`、部品は `site/src/components/`、全ページ共通部分は `site/src/layouts/Base.astro`
- コメントの文体・代替文 → `get_new_releases.py`（`ANGLES`/`OPENINGS`/`CLOSINGS`、`HYPE_WORDS`、`template_comment`、`build_prompt`。**切り口・書き出し・結びを作品ごとに変えて、似た文章の量産にならないようにしている**。確かめられない評価が入った答えは採用しない）。Claude が書くコメントの書き方・手順 → `docs/claude-comments.md`。週のまとめ記事の書き方・手順 → `docs/claude-roundups.md`
- 取得する件数・日数 → `get_new_releases.py` 冒頭の定数（`NEW_ITEMS_PER_RUN` など。Geminiの回数上限とセットで考える → 守ること8）

背景や今後の予定は `docs/design-notes.md` を見ること。
