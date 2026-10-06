// 新作の RSS（/feed.xml）。最近7日に発売された新作（ひとことコメントと作品ページのある作品）を、新しい順に50本まで（lib/feed.js）
import { curated, paged, today } from '../lib/data.js';
import { FEED_PATH, FEED_TITLE, newReleaseFeedItems, rssXml } from '../lib/feed.js';

export function GET() {
  const xml = rssXml({
    title: FEED_TITLE,
    path: FEED_PATH,
    description: 'FANZAの新作を、ひとことコメントと一緒に毎日お知らせします。',
    items: newReleaseFeedItems(curated, paged, today),
    updated: today,
  });
  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } });
}
