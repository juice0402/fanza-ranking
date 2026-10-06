// RSS（site/src/lib/feed.js）のテスト。実行: node tests/test_feed.mjs
import * as F from '../site/src/lib/feed.js';
import { SITE_URL } from '../site/src/lib/items.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};
const w = (cid, dateKey, extra = {}) => ({ cid, dateKey, title: `作品${cid}`, comment: `${cid}のひとこと`, actress: ['花子'], maker: 'メーカーA', popNew: null, ...extra });

console.log('■ 日付の形');
check('RSSの日付（日本時間の0時・曜日と月は英語の短い形）', F.rssDate('2026-10-06') === 'Tue, 06 Oct 2026 00:00:00 +0900' && F.rssDate('x') === '');

console.log('\n■ 新作の配信に入れる作品');
const items = [
  w('a', '2026-10-06'), w('b', '2026-10-05', { popNew: 1 }), w('c', '2026-10-05', { popNew: 5 }), w('d', '2026-09-29'), w('e', '2026-09-30'),
  w('f', '2026-10-07'), w('g', '2026-10-04', { comment: '' }), w('h', '2026-10-04', { title: '女子校生の放課後' }), w('nopage', '2026-10-04'),
];
const paged = new Set(items.map((i) => i.cid).filter((c) => c !== 'nopage'));
const got = F.newReleaseFeedItems(items, paged, '2026-10-06');
check('最近7日（きょうまで）・コメントと作品ページがある・未成年を連想させるタイトルでない作品を、新しい順（同じ日は人気順）に',
  got.map((x) => x.link.split('/').at(-2)).join() === 'a,b,c,e', got.map((x) => x.link).join());
check('作品ページへのリンク・ひとことと出演者・メーカーの説明', got[0].link === `${SITE_URL}/item/a/` && got[0].description === 'aのひとこと ／ 出演: 花子 ／ メーカー: メーカーA' && got[0].pubDate.startsWith('Tue, 06 Oct 2026'));
check('本数の上限', F.newReleaseFeedItems(items, paged, '2026-10-06', { limit: 2 }).length === 2);

console.log('\n■ RSS の文字列');
const xml = F.rssXml({ title: 'T&<>', path: F.FEED_PATH, description: 'D', items: [{ title: '<b>"A"&B</b>', link: 'https://x/a/', pubDate: F.rssDate('2026-10-06'), description: '説明\u0001' }], updated: '2026-10-06' });
check('RSS 2.0 の形・自分の場所（atom:link）・記号は書きかえる・使えない文字は消す', xml.startsWith('<?xml version="1.0" encoding="UTF-8"?>') && xml.includes('<rss version="2.0"') && xml.includes(`<atom:link href="${SITE_URL}/feed.xml" rel="self"`)
  && xml.includes('<title>T&amp;&lt;&gt;</title>') && xml.includes('<title>&lt;b&gt;&quot;A&quot;&amp;B&lt;/b&gt;</title>') && !xml.includes('\u0001') && xml.includes('<lastBuildDate>Tue, 06 Oct 2026'));
check('記事が無くても、中身の無い配信として壊れない', F.rssXml({ title: 'T', path: F.WEEKLY_FEED_PATH, description: 'D', items: [] }).includes('</channel>'));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
