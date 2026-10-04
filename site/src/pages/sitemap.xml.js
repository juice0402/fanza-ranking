// 検索エンジンに教えるための地図（/sitemap.xml）を、ビルド時に自動で作ります。
// lastmod（最後に変わった日）は、データにある updated（コメントを変えた日）から付けます。分からないページには付けません。
// 検索エンジンに出さない（noindex の）ページ（コメントの無い作品ページ・過去作品だけの一覧）は、地図にも入れません。
import { all, allReleased, paged, popularity, sale, released, today, upcoming, actressGroups, makerGroups, roundups, monthGroups, tagGroups } from '../lib/data.js';
import { itemIndexable, listIndexable } from '../lib/plan.js';
import { RANKING_ALL_PATH, RANKING_PATH, allRanking, newRanking } from '../lib/popularity.js';
import { SALE_PATH, saleGroups } from '../lib/sale.js';
import { MONTH_INDEX_PATH, TAG_INDEX_PATH } from '../lib/collections.js';
import {
  ACTRESS_INDEX_PATH,
  ARCHIVE_PAGE_SIZE,
  HOME_RELEASED_LIMIT,
  HOME_UPCOMING_LIMIT,
  MAKER_INDEX_PATH,
  archivePageCount,
  buildSitemap,
  itemPath,
  listLastmod,
} from '../lib/items.js';
import { WEEKLY_INDEX_PATH, weeklyPath } from '../lib/roundups.js';

export function GET() {
  const home = [...released.slice(0, HOME_RELEASED_LIMIT), ...upcoming.slice(0, HOME_UPCOMING_LIMIT)];
  const archive = Array.from({ length: archivePageCount(allReleased.length) }, (_, i) => allReleased.slice(i * ARCHIVE_PAGE_SIZE, (i + 1) * ARCHIVE_PAGE_SIZE))
    .map((items, i) => ({ path: `/archive/${i + 1}/`, items }))
    .filter((p) => listIndexable(p.items))
    .map((p) => ({ path: p.path, lastmod: listLastmod(p.items, today) }));
  // 人気ランキング（作品が無い・コメントのある作品が1本も無いあいだは、ページが noindex なので入れない）
  const rankingPages = [
    [RANKING_PATH, newRanking(all, today)],
    [RANKING_ALL_PATH, allRanking(all, today)],
  ].filter(([, list]) => list.length > 0 && listIndexable(list)).map(([path]) => ({ path, lastmod: popularity.date || today }));
  // セール・キャンペーン（作品が無い・コメントのある作品が1本も無いあいだは、ページが noindex なので入れない）
  const saleItems = saleGroups(all, sale, today).flatMap((g) => g.items);
  if (saleItems.length > 0 && listIndexable(saleItems)) rankingPages.push({ path: SALE_PATH, lastmod: sale.date || today });
  const groupPages = (groups) => groups.filter((g) => listIndexable(g.items)).map((g) => ({ path: g.path, lastmod: listLastmod(g.items, today) }));
  const entries = [
    { path: '/', lastmod: listLastmod(home, today) },
    ...rankingPages,
    ...archive,
    { path: ACTRESS_INDEX_PATH, lastmod: listLastmod(actressGroups.flatMap((g) => g.items), today) },
    ...groupPages(actressGroups),
    { path: MAKER_INDEX_PATH, lastmod: listLastmod(makerGroups.flatMap((g) => g.items), today) },
    ...groupPages(makerGroups),
    // 月ごと・ジャンルごとのまとめページ（1つも無いあいだは、一覧ページも地図に入れない）
    ...(monthGroups.length > 0 ? [{ path: MONTH_INDEX_PATH, lastmod: listLastmod(monthGroups.flatMap((g) => g.items), today) }, ...groupPages(monthGroups)] : []),
    ...(tagGroups.length > 0 ? [{ path: TAG_INDEX_PATH, lastmod: listLastmod(tagGroups.flatMap((g) => g.items), today) }, ...groupPages(tagGroups)] : []),
    ...all.filter((item) => itemIndexable(item, paged)).map((item) => ({ path: itemPath(item.cid), lastmod: item.updated })),
    // 週のまとめ記事（1本も無いあいだは、一覧ページも地図に入れない）
    ...(roundups.length > 0
      ? [
          { path: WEEKLY_INDEX_PATH, lastmod: roundups.map((r) => r.written).sort().at(-1) },
          ...roundups.map((r) => ({ path: weeklyPath(r.week_start), lastmod: r.written })),
        ]
      : []),
  ];

  return new Response(buildSitemap(entries), {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
}
