// サイト全体の設定です。独自ドメインにしたり、表示する件数を変えたいときは、ここだけ書き換えます。
// （astro.config.mjs・robots.txt・sitemap・各ページの canonical は、ここの SITE_URL を自動で使います）

export const SITE_NAME = 'FANZAセール情報'; // 2026-10-22 に「FANZA新作情報」から（独自ドメイン av-sale-guide.com への引っ越しといっしょに。見に来る人のお目当てはセール）
// サイト名のほかの呼び方（トップの WebSite の構造化データの alternateName。Google の検索結果のサイト名に使われる。2026-10-26 司令塔の連絡 C-003）。
// ホーム画面に追加したときの短い名前（site.webmanifest の short_name）と、前の名前を入れる
export const SITE_ALT_NAMES = ['FANZAセール', 'FANZA新作情報'];
export const SITE_URL = 'https://av-sale-guide.com'; // 末尾にスラッシュは付けない

// Google Search Console の所有権の確認用コード（<meta> の content の値）。公開されても問題のないコードです。空にすると出力しません
export const GOOGLE_SITE_VERIFICATION = 'Sr-kZdXB7gQmvK32Zc6vaSY6Gqdn0m_BI2pCHN3RMPk';

export const HOME_RELEASED_LIMIT = 36; // トップに並べる「発売中」の最大数
export const HOME_UPCOMING_SHOWN = 12; // トップの「予約受付中」で、はじめに見せる本数（発売日が近い順。残りは「もっと見る」で出す。押すまで残りの画像は読まない。運営者の「下のほうが重い」。2026-10-07）
export const HOME_UPCOMING_LIMIT = 60; // トップに並べる「予約」の最大数（予約は毎回4本まで・14日先までなので、最大でも56本ほど。全部が載る数にしてある。予約の一覧ページは無いため、これを減らすと、載らない作品が出る）
export const ARCHIVE_PAGE_SIZE = 30;   // 過去の作品の1ページあたりの件数
export const CAST_LIMIT = 3;           // 一覧のカードに出す出演者の人数（オムニバスなど出演者が多い作品は「ほか○名」。運営者の希望。2026-10-05）
export const RANKING_SHOWN = 3;        // トップの「きょうの新着人気TOP3」に出す本数（データには、VR作品を隠したときの差し替え用に、もっと多く入れてある。profiles.js の RANKING_MAX）
export const NEW_BADGE_DAYS = 6;       // 発売から何日間「新作」シールを付けるか
export const ENTITY_MIN_ITEMS = 2;     // 出演者・メーカーのページを作る最小の作品数（1本だけだと内容が薄いので作らない）
export const ENTITY_LIST_LIMIT = 120;  // 出演者・メーカーのページに並べる最大数（新しい順。過去作品が増えると、1ページが重くなりすぎるため）
export const INDEX_LIST_LIMIT = 500;   // 「メーカーから探す」に並べる最大数（作品数の多い順）
export const ACTRESS_FALLBACK_LIMIT = 150; // 「女優検索」の、JavaScriptが使えないとき用の一覧の最大数（作品数の多い順。ふだんは条件で探す画面に入れかわって隠れるので、ページを軽くするため少なめ。2026-10-05）

// サイト全体のファイル数の上限。2026-10-28 から本番もプレビューも Cloudflare Workers（静的ファイルは1つのサイトに10万まで。Pages は2万まで）。
// 過去作品が増えても超えないよう、作品ページは、この数から「作品ページ以外のファイル」を引いた数だけ、新しい作品から作る
// （あふれた古い作品は、一覧・出演者/メーカーのページから、FANZAへ直接リンクする。lib/plan.js）。少し余裕を残してある
// 2026-10-12 に 19,000 から 19,500 へ（運営者の判断「素人を1,000本にする分は、余裕の枠を使う」。動画の作品ページを約1万のまま残すため。
// 2026-10-28 に 19,500 から 40,000 へ（issue #188。運営者「ページは徐々に9万まで」。まず4万。次に上げるかは、公開の時間と検索に出ているかを見て決める。
// 上限は tests/verify_dist.py の FILE_LIMIT＝Workers の10万。Pages に戻すときは、2万より下＝19,500 に戻す。docs/architecture.md の「Workers への引っ越し」）
export const FILE_BUDGET = 40000;
export const FIXED_FILES = 150;        // 作品・出演者・メーカー・月・ジャンル・過去の作品・カレンダー・まとめ記事のページ以外のファイル（トップ・検索・画像・スクリプト・CSS など）の見積もり（実際は30ほど）

// 月ごと（/month/2026-11/）・ジャンルごと（/tag/…）のページ。検索エンジンから「11月 新作」「巨乳 新作」のような言葉で来てもらうための、作品のまとめページ
// シリーズ・レーベルのページ（運営者の希望「独自の価値を足す」→ シリーズ・レーベル別のページ。2026-10-07。lib/insights.js の groupByEntry）。
// 作品が MIN 本以上あるものだけ、作品数の多い順に MAX 件まで（サイト全体を FILE_BUDGET 以内に収めるため。足りない分は作品ページの枠から引かれる）
export const SERIES_MIN_ITEMS = 3;
export const SERIES_PAGE_MAX = 800;
export const LABEL_MIN_ITEMS = 3;
export const LABEL_PAGE_MAX = 300;
export const MONTH_MIN_ITEMS = 5;      // 月ごとのページを作る最小の作品数（少ない月は、内容が薄いので作らない）
export const TAG_MIN_ITEMS = 3;        // ジャンルごとのページを作る最小の作品数
export const TAG_PAGE_LIMIT = 90;      // ジャンルのページに並べる最大数（新しい順。それより多い分は、作品検索で探せる）
// ジャンルのページを作るジャンル（FANZAのジャンル名のうち、これに書いたものだけ）。VR作品のページは別に、いつも作る。
// 内容が分からない区分（ハイビジョン・独占配信・4K など）、過激な行為を表す言葉、学生・制服・「少女」を含む言葉など未成年を連想させる言葉は、わざと入れていない（コメントで使わない言葉の一覧 scripts/claude_comments.py の MINOR_WORDS と同じ考え方）。足すときは、ここに書く
export const TAG_PAGE_GENRES = [
  '巨乳', '美乳', '痴女', 'OL', 'お姉さん', 'スレンダー', '巨尻', '素人', 'ギャル', '人妻・主婦', '熟女', 'コスプレ', 'ベスト・総集編', 'ドラマ', 'ハーレム',
];
