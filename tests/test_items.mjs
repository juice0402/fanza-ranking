// サイトの部品（site/src/lib/items.js）のテスト。実行: node tests/test_items.mjs
import * as L from '../site/src/lib/items.js';
import fs from 'node:fs';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

console.log('■ 日付');
// UTC 2026-10-01 15:30 = 日本時間 2026-10-02 00:30
check('日本時間の日付またぎ(UTC 15:30 → 翌日)', L.jstToday(Date.UTC(2026, 9, 1, 15, 30)) === '2026-10-02', L.jstToday(Date.UTC(2026, 9, 1, 15, 30)));
check('UTC 14:59 はまだ前日', L.jstToday(Date.UTC(2026, 9, 1, 14, 59)) === '2026-10-01');
check('曜日: 2026-10-02 は金', L.dateParts('2026-10-02').wd === '金', L.dateParts('2026-10-02').wd);
check('曜日: 2026-11-22 は日', L.dateParts('2026-11-22').wd === '日', L.dateParts('2026-11-22').wd);
check('曜日: 2026-01-01 は木', L.dateParts('2026-01-01').wd === '木');
check('日付の日本語表記', L.formatDateJp('2026-11-02') === '2026年11月2日');
check('日数の差(月またぎ)', L.daysBetween('2026-10-02', '2026-09-30') === 2);
check('日数の差(年またぎ)', L.daysBetween('2027-01-01', '2026-12-31') === 1);

console.log('\n■ 整形・分類');
const raw = JSON.parse(fs.readFileSync(new URL('./fixtures/items.json', import.meta.url), 'utf-8'));
const items = L.normalizeItems(raw);
check('壊れたデータ(cid無し/日付不正/タイトル無し/重複)を除外', items.length === raw.length - 4, `${items.length} / ${raw.length}`);
check('配列でない入力でも落ちない', L.normalizeItems(null).length === 0 && L.normalizeItems({}).length === 0);
check('足りない項目に既定値', items.every((i) => Array.isArray(i.actress) && Array.isArray(i.sample_images) && typeof i.comment === 'string'));
check('AI判定(comment_kind)', items.some((i) => i.isAi) && items.some((i) => !i.isAi));

const today = '2026-10-02';
const { released, upcoming } = L.splitByRelease(items, today);
check('発売済み: 新しい順', released.every((x, i, a) => i === 0 || a[i - 1].dateKey >= x.dateKey));
check('予約: 近い順', upcoming.every((x, i, a) => i === 0 || a[i - 1].dateKey <= x.dateKey));
check('当日発売は「発売済み」', released.some((i) => i.dateKey === today));
check('翌日発売は「予約」', upcoming.some((i) => i.dateKey === '2026-10-03'));
check('発売済み+予約=全件', released.length + upcoming.length === items.length);

const groups = L.groupByDate(released);
check('日付ごとのまとめ: 日付が重複しない', new Set(groups.map((g) => g.dateKey)).size === groups.length);
check('日付ごとのまとめ: 件数の合計が一致', groups.reduce((n, g) => n + g.items.length, 0) === released.length);
check('空でも落ちない', L.groupByDate([]).length === 0);

check('シール: 当日=new', L.statusOf({ dateKey: '2026-10-02' }, today) === 'new');
check('シール: 6日前=new', L.statusOf({ dateKey: '2026-09-26' }, today) === 'new');
check('シール: 7日前=なし', L.statusOf({ dateKey: '2026-09-25' }, today) === '');
check('シール: 翌日=wait', L.statusOf({ dateKey: '2026-10-03' }, today) === 'wait');

console.log('\n■ 関連作品・ページ送り');
const base = items.find((i) => i.actress.length && i.actress[0] === '佐藤みお');
const rel = L.relatedItems(base, items, 8);
check('関連: 自分自身を含まない', !rel.some((r) => r.cid === base.cid));
check('関連: 重複なし', new Set(rel.map((r) => r.cid)).size === rel.length);
check('関連: 同じ出演者が先頭', rel.length > 0 && rel[0].actress.includes('佐藤みお'));
check('関連: 上限を守る', L.relatedItems(base, items, 2).length <= 2);
check('関連: メーカー不明どうしを関連にしない', L.relatedItems({ cid: 'x', actress: [], maker: '不明' }, items, 8).length === 0);
check('ページ数: 0件でも1ページ', L.archivePageCount(0) === 1);
check('ページ数: 30件=1, 31件=2', L.archivePageCount(30) === 1 && L.archivePageCount(31) === 2);
check('ページ番号の窓', JSON.stringify(L.pageWindow(10, 20)) === JSON.stringify([1, '…', 8, 9, 10, 11, 12, '…', 20]), JSON.stringify(L.pageWindow(10, 20)));
check('ページ番号: 全部表示できる少なさ', JSON.stringify(L.pageWindow(1, 3)) === JSON.stringify([1, 2, 3]));

console.log('\n■ sitemap / メタ情報');
const xml = L.buildSitemap(['/', '/item/a&b/']);
check('sitemap: XMLの記号をエスケープ', xml.includes('/item/a&amp;b/') && !xml.includes('a&b'));
check('sitemap: 絶対URL', xml.includes('<loc>https://fanza-ranking.pages.dev/</loc>'));
check('sitemap: 宣言とurlset', xml.startsWith('<?xml version="1.0"') && xml.includes('<urlset'));
const robotsTxt = L.buildRobots();
check('robots.txt: 全体を許可し、sitemapの場所を案内', robotsTxt.includes('User-agent: *') && robotsTxt.includes('Allow: /') && robotsTxt.includes('Sitemap: https://fanza-ranking.pages.dev/sitemap.xml'), robotsTxt);
check('robots.txt: 指定したURLを使う', L.buildRobots('https://example.com').includes('Sitemap: https://example.com/sitemap.xml'));
const long = { ...base, title: 'あ'.repeat(200) };
check('タイトルを切り詰める', L.itemPageTitle(long).length < 80, L.itemPageTitle(long).length);
check('説明文は120字以内', L.itemPageDescription({ ...base, comment: 'い'.repeat(300) }).length <= 120);
check('作品パス', L.itemPath('abc123') === '/item/abc123/' && L.archivePath(3) === '/archive/3/');

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
