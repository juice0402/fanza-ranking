// 週のまとめ記事の RSS（/weekly/feed.xml。lib/feed.js）。記事が無いあいだは、中身の無い配信
import { roundups } from '../../lib/data.js';
import { SITE_URL } from '../../lib/items.js';
import { WEEKLY_FEED_PATH, WEEKLY_FEED_TITLE, rssDate, rssXml } from '../../lib/feed.js';
import { weeklyPath, weekRangeShort } from '../../lib/roundups.js';

export function GET() {
  const xml = rssXml({
    title: WEEKLY_FEED_TITLE,
    path: WEEKLY_FEED_PATH,
    description: 'FANZAの1週間の新作をまとめた記事を、毎週月曜にお知らせします。',
    items: roundups.map((r) => ({
      title: `${weekRangeShort(r.week_start, r.week_end)}の新作まとめ`,
      link: SITE_URL + weeklyPath(r.week_start),
      pubDate: rssDate(r.written),
      description: String(r.lead ?? '').trim(),
    })),
    updated: roundups.map((r) => r.written).sort().at(-1) ?? '',
  });
  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } });
}
