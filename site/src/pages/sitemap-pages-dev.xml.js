// 前の住所（fanza-ranking.pages.dev）のサイトマップ（/sitemap-pages-dev.xml）を、ビルド時に自動で作ります（2026-11-02）。
// 中身は /sitemap.xml と同じページ・同じ lastmod で、住所だけ config.js の OLD_SITE_URL にしたもの（items.js の buildOldSitemap）。
// Google の「サイトの移転」の手順の、古い URL のサイトマップ。Search Console に1回送ると、Google が前の住所を読み直して 301 に気づき、
// 検索に出す住所が今の住所に入れかわる。robots.txt には書かない（今の住所のサイトマップではないため）。
// 前の住所が検索から消えたら（数か月）、このファイルと config.js の OLD_SITE_URL を消してよい
import { GET as currentSitemap } from './sitemap.xml.js';
import { buildOldSitemap } from '../lib/items.js';

export async function GET() {
  const xml = await currentSitemap().text();
  return new Response(buildOldSitemap(xml), {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
}
