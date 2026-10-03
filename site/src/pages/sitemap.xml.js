// 検索エンジンに教えるための地図（/sitemap.xml）を、ビルド時に自動で作ります。
// lastmod（最後に変わった日）は、データにある updated（コメントを変えた日）から付けます。分からないページには付けません。
import { all, released, today, upcoming } from '../lib/data.js';
import {
  HOME_RELEASED_LIMIT,
  HOME_UPCOMING_LIMIT,
  archivePageCount,
  buildSitemap,
  itemPath,
  listLastmod,
} from '../lib/items.js';
import { ARCHIVE_PAGE_SIZE } from '../config.js';

export function GET() {
  const home = [...released.slice(0, HOME_RELEASED_LIMIT), ...upcoming.slice(0, HOME_UPCOMING_LIMIT)];
  const archive = Array.from({ length: archivePageCount(released.length) }, (_, i) => ({
    path: `/archive/${i + 1}/`,
    lastmod: listLastmod(released.slice(i * ARCHIVE_PAGE_SIZE, (i + 1) * ARCHIVE_PAGE_SIZE), today),
  }));
  const entries = [
    { path: '/', lastmod: listLastmod(home, today) },
    ...archive,
    ...all.map((item) => ({ path: itemPath(item.cid), lastmod: item.updated })),
  ];

  return new Response(buildSitemap(entries), {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
}
