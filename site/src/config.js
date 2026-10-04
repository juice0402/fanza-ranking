// サイト全体の設定です。独自ドメインにしたり、表示する件数を変えたいときは、ここだけ書き換えます。
// （astro.config.mjs・robots.txt・sitemap・各ページの canonical は、ここの SITE_URL を自動で使います）

export const SITE_NAME = 'FANZA新作情報';
export const SITE_URL = 'https://fanza-ranking.pages.dev'; // 末尾にスラッシュは付けない

// Google Search Console の所有権の確認用コード（<meta> の content の値）。公開されても問題のないコードです。空にすると出力しません
export const GOOGLE_SITE_VERIFICATION = 'Sr-kZdXB7gQmvK32Zc6vaSY6Gqdn0m_BI2pCHN3RMPk';

export const HOME_RELEASED_LIMIT = 36; // トップに並べる「発売中」の最大数
export const HOME_UPCOMING_LIMIT = 60; // トップに並べる「予約」の最大数（予約は毎回4本まで・14日先までなので、最大でも56本ほど。全部が載る数にしてある。予約の一覧ページは無いため、これを減らすと、載らない作品が出る）
export const ARCHIVE_PAGE_SIZE = 30;   // 過去の作品の1ページあたりの件数
export const RANKING_SHOWN = 3;        // トップの「売れ筋」に出す本数（データには、VR作品を隠したときの差し替え用に、もっと多く入れてある。profiles.js の RANKING_MAX）
export const NEW_BADGE_DAYS = 6;       // 発売から何日間「新作」シールを付けるか
export const ENTITY_MIN_ITEMS = 2;     // 出演者・メーカーのページを作る最小の作品数（1本だけだと内容が薄いので作らない）
