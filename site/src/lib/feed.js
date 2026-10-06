// RSS（新着のお知らせの配信。運営者の希望「リピーターをつけたい」。2026-10-06。画面に依存しない。tests/test_feed.mjs）。
// /feed.xml: 最近7日に発売された新作（ひとことコメントと作品ページのある作品だけ。新しい順に50本まで）
// /weekly/feed.xml: 週のまとめ記事
// こちらから配る案内なので、未成年を連想させるタイトルの作品は入れない。説明は文字だけ（HTMLは入れない）
import { addDays, castLine, isDay, itemPath, SITE_NAME, SITE_URL, truncate } from './items.js';
import { isMinorTitle } from './gacha.js';

export const FEED_PATH = '/feed.xml';
export const WEEKLY_FEED_PATH = '/weekly/feed.xml';
export const FEED_DAYS = 7;
export const FEED_LIMIT = 50;

const escapeXml = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' })[c]).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '');

const WEEK = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "2026-10-06" → "Tue, 06 Oct 2026 00:00:00 +0900"（RSS の日付の形。日本時間のその日の0時） */
export function rssDate(day) {
  if (!isDay(day)) return '';
  const d = new Date(Date.UTC(+day.slice(0, 4), +day.slice(5, 7) - 1, +day.slice(8, 10)));
  return `${WEEK[d.getUTCDay()]}, ${day.slice(8, 10)} ${MONTHS[d.getUTCMonth()]} ${day.slice(0, 4)} 00:00:00 +0900`;
}

/** 新作の配信に入れる作品: 最近 days 日（きょうまで）に発売・ひとことコメントと作品ページがある・未成年を連想させるタイトルでない。新しい順に limit 本 */
export function newReleaseFeedItems(items, paged, today, { days = FEED_DAYS, limit = FEED_LIMIT } = {}) {
  const from = addDays(today, -(days - 1));
  return items
    .filter((i) => i.dateKey >= from && i.dateKey <= today && paged.has(i.cid) && String(i.comment ?? '').trim() && !isMinorTitle(i.title))
    .sort((a, b) => b.dateKey.localeCompare(a.dateKey) || (a.popNew ?? Infinity) - (b.popNew ?? Infinity) || a.cid.localeCompare(b.cid))
    .slice(0, limit)
    .map((i) => ({
      title: truncate(i.title, 80),
      link: SITE_URL + itemPath(i.cid),
      pubDate: rssDate(i.dateKey),
      description: [String(i.comment).trim(), `出演: ${castLine(i.actress, 3, '記載なし')}`, i.maker !== '不明' ? `メーカー: ${i.maker}` : ''].filter(Boolean).join(' ／ '),
    }));
}

/** RSS 2.0 の文字列 */
export function rssXml({ title, path, description, items, updated = '' }) {
  const rows = items
    .map((x) => `    <item>\n      <title>${escapeXml(x.title)}</title>\n      <link>${escapeXml(x.link)}</link>\n      <guid isPermaLink="true">${escapeXml(x.link)}</guid>\n${x.pubDate ? `      <pubDate>${x.pubDate}</pubDate>\n` : ''}      <description>${escapeXml(x.description)}</description>\n    </item>`)
    .join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>${escapeXml(title)}</title>
    <link>${escapeXml(SITE_URL + '/')}</link>
    <atom:link href="${escapeXml(SITE_URL + path)}" rel="self" type="application/rss+xml" />
    <description>${escapeXml(description)}</description>
    <language>ja</language>
${isDay(updated) ? `    <lastBuildDate>${rssDate(updated)}</lastBuildDate>\n` : ''}${rows}
  </channel>
</rss>
`;
}

export const FEED_TITLE = `${SITE_NAME}（新作）`;
export const WEEKLY_FEED_TITLE = `${SITE_NAME}（週のまとめ）`;
