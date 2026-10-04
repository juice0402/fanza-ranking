// サイト全体の設定です。独自ドメインにしたり、表示する件数を変えたいときは、ここだけ書き換えます。
// （astro.config.mjs・robots.txt・sitemap・各ページの canonical は、ここの SITE_URL を自動で使います）

export const SITE_NAME = 'FANZA新作情報';
export const SITE_URL = 'https://fanza-ranking.pages.dev'; // 末尾にスラッシュは付けない

// Google Search Console の所有権の確認用コード（<meta> の content の値）。公開されても問題のないコードです。空にすると出力しません
export const GOOGLE_SITE_VERIFICATION = 'Sr-kZdXB7gQmvK32Zc6vaSY6Gqdn0m_BI2pCHN3RMPk';

export const HOME_RELEASED_LIMIT = 36; // トップに並べる「発売中」の最大数
export const HOME_UPCOMING_LIMIT = 60; // トップに並べる「予約」の最大数（予約は毎回4本まで・14日先までなので、最大でも56本ほど。全部が載る数にしてある。予約の一覧ページは無いため、これを減らすと、載らない作品が出る）
export const ARCHIVE_PAGE_SIZE = 30;   // 過去の作品の1ページあたりの件数
export const NEW_BADGE_DAYS = 6;       // 発売から何日間「新作」シールを付けるか
export const ENTITY_MIN_ITEMS = 2;     // 出演者・メーカーのページを作る最小の作品数（1本だけだと内容が薄いので作らない）

// 月ごと（/month/2026-11/）・ジャンルごと（/tag/…）のページ。検索エンジンから「11月 新作」「巨乳 新作」のような言葉で来てもらうための、作品のまとめページ
export const MONTH_MIN_ITEMS = 5;      // 月ごとのページを作る最小の作品数（少ない月は、内容が薄いので作らない）
export const TAG_MIN_ITEMS = 3;        // ジャンルごとのページを作る最小の作品数
export const TAG_PAGE_LIMIT = 90;      // ジャンルのページに並べる最大数（新しい順。それより多い分は、作品検索で探せる）
// ジャンルのページを作るジャンル（FANZAのジャンル名のうち、これに書いたものだけ）。VR作品のページは別に、いつも作る。
// 内容が分からない区分（ハイビジョン・独占配信・4K など）、過激な行為を表す言葉、学生・制服・「少女」を含む言葉など未成年を連想させる言葉は、わざと入れていない（コメントで使わない言葉の一覧 scripts/claude_comments.py の MINOR_WORDS と同じ考え方）。足すときは、ここに書く
export const TAG_PAGE_GENRES = [
  '巨乳', '美乳', '痴女', 'OL', 'お姉さん', 'スレンダー', '巨尻', '素人', 'ギャル', '人妻・主婦', '熟女', 'コスプレ', 'ベスト・総集編', 'ドラマ', 'ハーレム',
];
