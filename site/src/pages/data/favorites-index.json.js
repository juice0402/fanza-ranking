// 「お気に入り」ページ・トップのお知らせが、お気に入りの出演者・メーカーの新作を探すための索引（/data/favorites-index.json）。
// 最近の作品と予約だけを入れた、小さなJSONです（毎日のビルドで作り直します）。
import { curated, paged, today, calendarActressGroups, calendarMakerGroups } from '../../lib/data.js';
import { buildFavoritesIndex, pageSlugMap, FAVORITES_INDEX_DAYS } from '../../lib/favorites.js';

export function GET() {
  // pages: 専用ページと発売日カレンダーの両方がある出演者・メーカー（新作・予約が載っている人だけ。過去作品だけの人まで入れると、索引が大きくなるため）。
  // 「お気に入り」ページは、ここにある人だけに、カレンダーのリンクを出す
  const pages = { actress: pageSlugMap(calendarActressGroups), maker: pageSlugMap(calendarMakerGroups) };
  // 作品は、毎日の更新で載せた作品（新作・予約）のうち、作品ページがあるものだけ（お気に入りのページから、作品ページへリンクするため。
  // 過去作品は「お気に入りの新作」ではないので入れない）
  const items = curated.filter((i) => paged.has(i.cid));
  return new Response(JSON.stringify(buildFavoritesIndex(items, today, FAVORITES_INDEX_DAYS, pages)), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}
