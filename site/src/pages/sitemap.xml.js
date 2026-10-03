// 検索エンジンに教えるための地図（/sitemap.xml）を、ビルド時に自動で作ります。
import { all, released } from '../lib/data.js';
import { archivePageCount, buildSitemap, itemPath } from '../lib/items.js';

export function GET() {
  const archivePages = Array.from({ length: archivePageCount(released.length) }, (_, i) => `/archive/${i + 1}/`);
  const paths = ['/', ...archivePages, ...all.map((item) => itemPath(item.cid))];

  return new Response(buildSitemap(paths), {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
}
