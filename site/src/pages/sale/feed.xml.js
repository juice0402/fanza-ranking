// 新しく始まったセールの RSS（/sale/feed.xml。issue #239）。いま開いているセールを、始まりの新しい順に（lib/feed.js の saleFeedItems）
import { saleCalendarSources, today } from '../../lib/data.js';
import { jstNow, saleEvents } from '../../lib/calendar.js';
import { SALE_FEED_PATH, SALE_FEED_TITLE, rssXml, saleFeedItems } from '../../lib/feed.js';

export function GET() {
  const now = jstNow();
  const xml = rssXml({
    title: SALE_FEED_TITLE,
    path: SALE_FEED_PATH,
    description: 'FANZAの動画・売り場で新しく始まったセールを、終わりの日時と一緒にお知らせします。',
    items: saleFeedItems(saleEvents(saleCalendarSources, now, Infinity), now),
    updated: today,
  });
  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } });
}
