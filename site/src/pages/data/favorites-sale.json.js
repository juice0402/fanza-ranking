// 「推しの棚」（トップ）が、お気に入りの出演者・メーカーのセール中の作品を探すための索引（/data/favorites-sale.json）。
// セール中で、作品ページがある作品だけを、人気の順に入れる（毎日のビルドで作り直します）。
import { all, paged, sale, today } from '../../lib/data.js';
import { onSaleItems, offPercent } from '../../lib/sale.js';
import { isMinorTitle } from '../../lib/gacha.js';
import { buildFavoritesSale } from '../../lib/favorites.js';

export function GET() {
  const items = onSaleItems(all.filter((i) => paged.has(i.cid) && !isMinorTitle(i.title)), sale, today);
  return new Response(JSON.stringify(buildFavoritesSale(items, today, offPercent)), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}
