// サイト全体の設定です。独自ドメインにしたり、表示する件数を変えたいときは、ここだけ書き換えます。
// （astro.config.mjs・robots.txt・sitemap・各ページの canonical は、ここの SITE_URL を自動で使います）

export const SITE_NAME = 'FANZA新作情報';
export const SITE_URL = 'https://fanza-ranking.pages.dev'; // 末尾にスラッシュは付けない

export const HOME_RELEASED_LIMIT = 36; // トップに並べる「発売中」の最大数
export const HOME_UPCOMING_LIMIT = 24; // トップに並べる「予約」の最大数
export const ARCHIVE_PAGE_SIZE = 30;   // 過去の作品の1ページあたりの件数
export const NEW_BADGE_DAYS = 6;       // 発売から何日間「新作」シールを付けるか
