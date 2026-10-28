// 作品ごとの値段の記録（site/src/lib/price-history.js）のテスト。実行: node tests/test_price_history.mjs
import * as P from '../site/src/lib/price-history.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

console.log('■ price_history.json の読み方');
const raw = {
  since: '2026-10-29',
  updated: '2026-12-01',
  items: {
    a: [2692, 1884, '2026-11-03', 2, '2026-11-30', '2026-12-01'],
    b: [1980, 980, '2026-10-29', 1, '2026-10-29', '2026-10-30'],
    big: [12800, 10980, '2026-11-03', 12, '2026-11-01', '2026-11-05'],
    zero: [1000, 0, '2026-11-01', 1, '2026-11-01', '2026-11-01'],
    short: [1000, 500, '2026-11-01'],
    badday: [1000, 500, '2026/11/01', 1, '2026-11-01', '2026-11-01'],
    later: [1000, 500, '2026-11-05', 1, '2026-11-01', '2026-11-02'],
    str: 'x',
  },
};
const h = P.normalizePriceHistory(raw);
check('since・更新日・形の正しい作品だけ（値段0・項目の足りない行・日付の形が違う行・いちばん安い日が最後に見かけた日より後の行は捨てる）',
  h.since === '2026-10-29' && h.updated === '2026-12-01' && [...h.items.keys()].join(',') === 'a,b,big'
  && JSON.stringify(h.items.get('a')) === JSON.stringify({ listPrice: 2692, low: 1884, lowDay: '2026-11-03', count: 2, start: '2026-11-30', last: '2026-12-01' }), [...h.items.keys()].join(','));
const empty = P.normalizePriceHistory(null);
check('ファイルがまだ無いとき（null）・形が違うとき（since が無い）は空（ビルドは止めない）',
  empty.since === '' && empty.items.size === 0 && P.normalizePriceHistory({ items: raw.items }).items.size === 0 && P.normalizePriceHistory([1]).items.size === 0);

console.log('\n■ 30日たつまで出さない（ビルドの日で判断）');
check(`記録を始めてから${P.PRICE_RECORD_MIN_DAYS}日たつまでは出さない・たった日から出す（10月29日から → 11月28日から）`,
  P.PRICE_RECORD_MIN_DAYS === 30 && !P.priceRecordShown(h, '2026-10-29') && !P.priceRecordShown(h, '2026-11-27') && P.priceRecordShown(h, '2026-11-28') && P.priceRecordShown(h, '2027-01-01'));
check('記録が無いときは出さない', !P.priceRecordShown(empty, '2027-01-01') && P.priceRecordText('a', empty, '2027-01-01') === '');
check('30日たつ前は、記録のある作品でも文を作らない', P.priceRecordText('a', h, '2026-11-27', { onSale: true }) === '' && P.priceRecordText('a', h, '2026-11-28') !== '');

console.log('\n■ 作品ページの1行');
const t1 = P.priceRecordText('a', h, '2026-12-01', { onSale: true, nowPrice: 1884, saleDate: '2026-12-01' });
check('いまセール中: 「このサイトの記録（○年○月○日から）：いちばん安かったのは○月○日の○円・セールは○回目」', t1 === 'このサイトの記録（2026年10月29日から）：いちばん安かったのは11月3日の1,884円・セールは2回目', t1);
const t2 = P.priceRecordText('b', h, '2026-12-01');
check('いまセール中でなければ「セールは○回」', t2 === 'このサイトの記録（2026年10月29日から）：いちばん安かったのは10月29日の980円・セールは1回', t2);
const t3 = P.priceRecordText('b', h, '2026-12-01', { onSale: true, saleDate: '2026-12-01' });
check('セールの札が出ていても、記録の最後に見かけた日がセールのデータの日と違えば「○回目」にしない（記録が追いついていない）', t3.endsWith('セールは1回'), t3);
check('いまの値段が、記録のいちばん安い値段より安ければ出さない（記録が追いついていない。記録の値段を今の値段に見せない）',
  P.priceRecordText('a', h, '2026-12-01', { onSale: true, nowPrice: 1500 }) === '' && P.priceRecordText('a', h, '2026-12-01', { onSale: true, nowPrice: 1884 }) !== '');
const t4 = P.priceRecordText('big', h, '2027-01-10');
check('値段は3けたごとに「,」・年が変わったら、いちばん安かった日に年も付ける', t4.includes('2026年11月3日の10,980円・セールは12回'), t4);
check('記録の無い作品は出さない', P.priceRecordText('zzz', h, '2026-12-01') === '');
const all = ['a', 'b', 'big'].flatMap((c) => [P.priceRecordText(c, h, '2026-12-01', { onSale: true }), P.priceRecordText(c, h, '2027-02-01')]);
check('使わない言葉（史上最安・過去最安・最安値・底値・今が買い時・今だけ・見逃す）が入らない・かっこは1つ・いつからの記録かを必ず書く',
  all.every((t) => t && !P.PRICE_RECORD_NG.test(t) && (t.match(/（/g) || []).length === 1 && t.startsWith('このサイトの記録（2026年10月29日から）：')), all[0]);
check('使わない言葉の見張り: 史上最安・過去最安・最安値・底値・今が買い時・今だけ・見逃す・見逃さないで を見つける',
  ['史上最安', '過去最安値', '最安値', '底値', '今が買い時', '今だけ', '見逃すな', '見逃さないで'].every((w) => P.PRICE_RECORD_NG.test(w)) && !P.PRICE_RECORD_NG.test('いちばん安かったのは'));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
