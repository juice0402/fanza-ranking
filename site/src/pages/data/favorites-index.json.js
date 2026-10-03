// 「お気に入り」ページ・トップのお知らせが、お気に入りの出演者・メーカーの新作を探すための索引（/data/favorites-index.json）。
// 最近の作品と予約だけを入れた、小さなJSONです（毎日のビルドで作り直します）。
import { all, today, actressGroups, makerGroups } from '../../lib/data.js';
import { buildFavoritesIndex, pageSlugMap, FAVORITES_INDEX_DAYS } from '../../lib/favorites.js';

export function GET() {
  const pages = { actress: pageSlugMap(actressGroups), maker: pageSlugMap(makerGroups) };
  return new Response(JSON.stringify(buildFavoritesIndex(all, today, FAVORITES_INDEX_DAYS, pages)), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}
