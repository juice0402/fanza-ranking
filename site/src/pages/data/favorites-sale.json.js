// トップの「推しの棚」が、お気に入りの出演者・メーカーのセール中の作品を探すための索引（/data/favorites-sale.json。2026-10-31）。
// セール中で、作品ページがある作品だけ。☆を付けられる出演者・メーカー（専用ページがある人）の名前から引けるようにする。
// 形は lib/favorites.js の buildFavoritesSale。毎日のビルドで作り直します。
import { actressGroups, all, makerGroups, paged, sale, today } from '../../lib/data.js';
import { onSaleItems, offPercent } from '../../lib/sale.js';
import { isMinorTitle } from '../../lib/gacha.js';
import { buildFavoritesSale } from '../../lib/favorites.js';

export function GET() {
  const items = onSaleItems(all.filter((i) => paged.has(i.cid) && !isMinorTitle(i.title)), sale, today);
  const names = { actress: new Set(actressGroups.map((g) => g.name)), maker: new Set(makerGroups.map((g) => g.name)) };
  return new Response(JSON.stringify(buildFavoritesSale(items, today, offPercent, names)), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}
