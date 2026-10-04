// セール・キャンペーン（site/src/lib/sale.js・site/public/sale.js）のテスト。実行: node tests/test_sale.mjs
import fs from 'node:fs';
import vm from 'node:vm';
import * as S from '../site/src/lib/sale.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

console.log('■ sale.json の読み方');
const raw = {
  date: '2026-10-05',
  campaigns: [
    { title: 'メーカーA30％OFF', begin: '2026-10-03 10:00', end: '2026-10-06 09:59' },
    { title: '日替わりセール★', begin: '2026-10-05 00:00', end: '2026-10-05 23:59' },
    { title: '昨日で終わったセール', begin: '2026-10-01 00:00', end: '2026-10-04 23:59' },
    { title: '', begin: '', end: '2026-10-09 00:00' },
  ],
  items: [
    { c: 'a', k: 0, p: 1884, l: 2692 }, { c: 'b', k: 0 }, { c: 'c', k: 1, p: 980, l: 1980 }, { c: 'd', k: 2, p: 1, l: 2 },
    { c: 'e', k: 3 }, { c: 'f', k: 9 }, { c: 'g', k: 0, p: 3000, l: 2000 }, 'x', { c: 1, k: 0 },
  ],
};
const sale = S.normalizeSale(raw);
check('日付・キャンペーン・作品（キャンペーンの番号が無い・名前の無いキャンペーンの作品は捨てる）', sale.date === '2026-10-05' && sale.campaigns.length === 4 && [...sale.byCid.keys()].join() === 'a,b,c,d,g', [...sale.byCid.keys()].join());
check('価格は、定価より安いときだけ（高い・無いときは null）', sale.byCid.get('a').price === 1884 && sale.byCid.get('b').price === null && sale.byCid.get('g').price === null && sale.byCid.get('g').listPrice === null);
check('無い・形が違うときは空', [null, undefined, [], 'x', { campaigns: 'x', items: {} }].every((v) => { const s = S.normalizeSale(v); return s.date === '' && s.campaigns.length === 0 && s.byCid.size === 0; }));

console.log('\n■ 表示の文');
check('値引きの割合（四捨五入）・分からなければ null', S.offPercent(1884, 2692) === 30 && S.offPercent(990, 1980) === 50 && S.offPercent(null, 100) === null && S.offPercent(100, 100) === null);
check('札: 「30%OFF」・価格が分からなければ「セール」', S.saleBadge(sale.byCid.get('a')) === '30%OFF' && S.saleBadge(sale.byCid.get('b')) === 'セール' && S.saleBadge(null) === 'セール');
check('価格の文: 「1,884円〜（通常2,692円〜）」・分からなければ空', S.salePriceNote(sale.byCid.get('a')) === '1,884円〜（通常2,692円〜）' && S.salePriceNote(sale.byCid.get('b')) === '' && S.salePriceNote(null) === '');
check('終わりの文: 「10月6日 9:59」・時刻が無ければ日付だけ・読めなければ空', S.endLabel('2026-10-06 09:59') === '10月6日 9:59' && S.endLabel('2026-10-06') === '10月6日' && S.endLabel('あした') === '');
check('終わりの時刻（日本時間・ブラウザで比べる用）', S.endIso('2026-10-06 09:59') === '2026-10-06T09:59:59+09:00' && S.endIso('2026-10-06') === '2026-10-06T23:59:59+09:00' && S.endIso('') === '');

console.log('\n■ キャンペーンごとのまとまり');
const it = (cid, dateKey, popAll = null, popNew = null, extra = {}) => ({ cid, dateKey, popAll, popNew, maker: 'メーカーA', actress: [], genres: [], vr: false, ...extra });
const items = [it('a', '2025-01-01', 50), it('b', '2026-01-01', 3), it('c', '2026-09-01', null, 2), it('d', '2020-01-01', 1), it('z', '2026-01-01', 1)];
const groups = S.saleGroups(items, sale, '2026-10-05');
check('終わりが近い順・今日より前に終わったキャンペーンは入れない・セールでない作品は入れない', groups.map((g) => g.title).join() === '日替わりセール★,メーカーA30％OFF', groups.map((g) => g.title).join());
check('キャンペーンの中は人気の高い順（全体と新着の順位の、上のほう）・本数・作品にセールの情報が付く', groups[1].items.map((i) => i.cid).join() === 'b,a' && groups[1].total === 2 && groups[1].items[1].sale.price === 1884, groups[1].items.map((i) => i.cid).join());
check('キャンペーンの番号（見出しの id・リンク用）', groups[0].k === 1 && groups[1].k === 0 && S.saleAnchor(0) === 'sale-0' && S.saleHref(3) === '/sale/#sale-3');
check('1つのキャンペーンの本数の上限（本数・表紙・まとめは全部の作品から）', S.saleGroups(items, sale, '2026-10-05', 1)[1].items.length === 1 && S.saleGroups(items, sale, '2026-10-05', 1)[1].total === 2 && S.saleGroups(items, sale, '2026-10-05', 1)[1].covers.length === 2);
check('セール中の作品の数（終わったキャンペーンは除く）', S.saleCount(items, sale, '2026-10-05') === 3);
check('空でも落ちない', S.saleGroups([], sale, '2026-10-05').length === 0 && S.saleGroups(items, S.normalizeSale(null), '2026-10-05').length === 0 && S.saleCount(items, S.normalizeSale(null), '2026-10-05') === 0);

console.log('\n■ 特集の中身（おもなメーカー・よく出ている女優・多いジャンル・表紙）');
const works = [
  it('w1', '2026-01-01', 1, null, { maker: 'S社', actress: ['星子'], genres: ['巨乳', 'ハイビジョン'] }),
  it('w2', '2026-01-01', 2, null, { maker: 'S社', actress: ['星子', '月子'], genres: ['巨乳', '単体作品'], vr: true }),
  it('w3', '2026-01-01', 3, null, { maker: 'N社', actress: ['月子'], genres: ['熟女', '巨乳'] }),
  it('w4', '2026-01-01', 4, null, { maker: '不明', actress: ['花子', '星子', '月子', '雪子', '風子'], genres: ['熟女'] }),
  it('w5', '2026-01-01', 5, null, { maker: 'N社', actress: ['花子'], genres: ['熟女', '熟女'] }),
  it('w6', '2026-01-01', 6, null, { maker: 'S社', actress: [], genres: [] }),
];
const sum = S.campaignSummary(works, { genres: new Set(['巨乳', '熟女']) });
const show = (rows) => rows.map((r) => `${r.name}${r.count}`).join();
check('おもなメーカー: 多い順・「不明」は数えない', show(sum.makers) === 'S社3,N社2', show(sum.makers));
check('よく出ている女優: 出演者が4人までの作品だけ・2本以上の人だけ・同数は名前の順', show(sum.actresses) === '星子2,月子2', show(sum.actresses));
check('多いジャンル: 渡したジャンルだけ（形式のジャンルは数えない）・1作品で同じジャンルは1回', show(sum.genres) === '巨乳3,熟女3', show(sum.genres));
check('数の上限', S.campaignSummary(works, { genres: new Set(['巨乳', '熟女']), limit: 1 }).makers.length === 1 && S.campaignSummary([], {}).makers.length === 0);
check('表紙: VRでない作品を人気の高い順に先に・足りなければVR作品', S.campaignCovers(works).map((w) => w.cid).join() === 'w1,w3,w4' && S.campaignCovers([works[1], works[0]]).map((w) => w.cid).join() === 'w1,w2');
check('終わりの札: きょう・あすだけ（月末・年末もまたぐ）', S.endSoonTag('2026-10-05 09:59', '2026-10-05') === 'きょうまで' && S.endSoonTag('2026-10-06 23:59', '2026-10-05') === 'あすまで' && S.endSoonTag('2026-11-01 23:59', '2026-10-31') === 'あすまで' && S.endSoonTag('2027-01-01', '2026-12-31') === 'あすまで' && S.endSoonTag('2026-10-07 23:59', '2026-10-05') === '' && S.endSoonTag('', '2026-10-05') === '');

console.log('\n■ 終わったキャンペーンを隠す（ブラウザ側 sale.js）');
const sandbox = { module: { exports: {} } };
vm.runInNewContext(fs.readFileSync(new URL('../site/public/sale.js', import.meta.url), 'utf-8'), sandbox);
const now = Date.parse('2026-10-06T10:00:00+09:00');
check('終わりの時刻をすぎたら隠す・まだなら隠さない・読めない値は隠さない', sandbox.module.exports.ended('2026-10-06T09:59:59+09:00', now) && !sandbox.module.exports.ended('2026-10-06T23:59:59+09:00', now) && !sandbox.module.exports.ended('', now) && !sandbox.module.exports.ended('あした', now));
const slots = (flags, n) => sandbox.module.exports.shownSlots(flags, n).map((v) => (v ? 1 : 0)).join('');
check('トップの特集のカード: 終わっていないものを先頭からn個（終わった分は次が繰り上がる）', slots([false, false, false, false, false, false], 4) === '111100' && slots([true, true, false, false, false, false], 4) === '001111' && slots([true, false, true], 4) === '010' && slots([], 4) === '');

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
