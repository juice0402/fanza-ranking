// 検索エンジンに教えるための地図（/sitemap.xml）を、ビルド時に自動で作ります。
// lastmod（最後に変わった日）は、データにある updated（コメントを変えた日）から付けます。分からないページには付けません。
import { all, released, today, upcoming, actressGroups, makerGroups, roundups, monthGroups, tagGroups } from '../lib/data.js';
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
  const archive = Array.from({ length: archivePageCount(released.length) }, (_, i) => ({
    path: `/archive/${i + 1}/`,
    lastmod: listLastmod(released.slice(i * ARCHIVE_PAGE_SIZE, (i + 1) * ARCHIVE_PAGE_SIZE), today),
  }));
  const groupPages = (groups) => groups.map((g) => ({ path: g.path, lastmod: listLastmod(g.items, today) }));
  const entries = [
    { path: '/', lastmod: listLastmod(home, today) },
    ...archive,
    { path: ACTRESS_INDEX_PATH, lastmod: listLastmod(actressGroups.flatMap((g) => g.items), today) },
    ...groupPages(actressGroups),
    { path: MAKER_INDEX_PATH, lastmod: listLastmod(makerGroups.flatMap((g) => g.items), today) },
    ...groupPages(makerGroups),
    // 月ごと・ジャンルごとのまとめページ（1つも無いあいだは、一覧ページも地図に入れない）
    ...(monthGroups.length > 0 ? [{ path: MONTH_INDEX_PATH, lastmod: listLastmod(monthGroups.flatMap((g) => g.items), today) }, ...groupPages(monthGroups)] : []),
    ...(tagGroups.length > 0 ? [{ path: TAG_INDEX_PATH, lastmod: listLastmod(tagGroups.flatMap((g) => g.items), today) }, ...groupPages(tagGroups)] : []),
    ...all.map((item) => ({ path: itemPath(item.cid), lastmod: item.updated })),
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
