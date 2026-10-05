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


console.log('\n■ 特集の最大の割引（saleGroups の maxOff）');
const gs = S.saleGroups(items, sale, '2026-10-05', 12);
check('値引きの分かる作品の、いちばん大きい割引・分からなければ null', gs.find((g) => g.title === 'メーカーA30％OFF').maxOff === 30 && gs.find((g) => g.title === '日替わりセール★').maxOff === 51, gs.map((g) => `${g.title}:${g.maxOff}`).join());

console.log('\n■ セールの履歴（sale_history.json）');
const hraw = {
  updated: '2026-10-06',
  campaigns: [
    { title: 'メーカーA30％OFF', begin: '2026-10-03 10:00', end: '2026-10-06 09:59', first: '2026-10-05', last: '2026-10-06', count: 2, max_off: 30 },
    { title: 'メーカーA30％OFF', begin: '2026-09-20 10:00', end: '2026-09-22 09:59', first: '2026-09-20', last: '2026-09-22', count: 5 },
    { title: '日替わりセール★', begin: '2026-10-05 00:00', end: '2026-10-05 23:59', first: '2026-10-05', last: '2026-10-05', count: 1, max_off: 51 },
    { title: '昔のセール', begin: '2026-05-01 00:00', end: '2026-05-03 23:59', first: '2026-05-01', last: '2026-05-03', count: 4 },
    { title: '女子校生セール', begin: '2026-10-01 00:00', end: '2026-10-07 23:59', first: '2026-10-05', last: '2026-10-06', count: 9 },
    { title: '', begin: 'x', end: 'y' }, { title: 'ok', begin: '', end: '2026-10-08', first: '2026-10-06', last: '2026-10-06', count: -3, max_off: 100 }, 'x',
  ],
};
const hist = S.normalizeSaleHistory(hraw);
check('履歴の読み方: 形の違う行は捨てる・本数が変なら0・割引は1〜99%だけ・新しい順', hist.updated === '2026-10-06' && hist.rows.length === 6
  && hist.rows.find((r) => r.title === 'ok').count === 0 && hist.rows.find((r) => r.title === 'ok').maxOff === null && hist.rows.at(-1).title === '昔のセール', hist.rows.map((r) => r.title).join());
check('無い・形が違うときは空', [null, [], { campaigns: 'x' }].every((v) => S.normalizeSaleHistory(v).rows.length === 0));
check('特集のページの印: 名前ごと・全角/半角と空白の違いは同じ・10文字', S.campaignSlug('メーカーA30％OFF') === S.campaignSlug('メーカーＡ30%OFF') && S.campaignSlug('日替わり セール') === S.campaignSlug('日替わりセール')
  && /^[0-9a-f]{10}$/.test(S.campaignSlug('x')) && S.campaignPath('x') === `/sale/${S.campaignSlug('x')}/` && S.campaignSlug('a') !== S.campaignSlug('b'));
check('開催の日数・期間の文', S.runDays(hist.rows[0]) === 3 && S.runDays({ begin: '', first: '2026-10-06', end: '2026-10-08' }) === 3
  && S.runRange({ begin: '2026-10-03 10:00', end: '2026-10-06 09:59' }) === '10月3日〜10月6日 9:59' && S.runRange({ begin: '', end: '2026-10-08' }) === '〜10月8日' && S.mdOf('x') === '');

console.log('\n■ 特集ごとのページ（campaignPages）');
const pages = S.campaignPages(items, sale, hist, '2026-10-05');
const pOf = (t) => pages.find((p) => p.title === t);
check('開催中の特集（終わりが近い順）→ 終わった特集（最後に見かけた日が新しい順）・名前ごとに1ページ',
  pages.map((p) => p.title).join() === '日替わりセール★,メーカーA30％OFF,ok', pages.map((p) => p.title).join());
check('開催中の特集には、まとまり（作品・いつまで・最大の割引）と、これまでの開催（同じ名前の全部の回）', pOf('メーカーA30％OFF').active.total === 2 && pOf('メーカーA30％OFF').runs.length === 2 && pOf('メーカーA30％OFF').path === S.campaignPath('メーカーA30％OFF'));
check('開催していない特集は、まとまりが無い（これまでの開催だけ）', pOf('ok').active === null && pOf('ok').runs.length === 1);
check('最後に見かけてから90日をすぎた特集・未成年を連想させる名前の特集は、ページを作らない', !pOf('昔のセール') && !pOf('女子校生セール'));
check('作品の本数の上限（perGroup）', S.campaignPages(items, sale, hist, '2026-10-05', { perGroup: 1 }).find((p) => p.title === 'メーカーA30％OFF').active.items.length === 1);

console.log('\n■ 「FANZAのセールはいつ？」の材料（saleHistoryFacts）');
const facts = S.saleHistoryFacts(hist, new Map(pages.map((p) => [p.slug, p])));
check('未成年を連想させる名前の回は入れない・始まった月ごと（新しい月から）', facts.runs.length === 5 && facts.byMonth.map((m) => `${m.ym}:${m.runs.length}`).join() === '2026-10:3,2026-09:1,2026-05:1', facts.byMonth.map((m) => `${m.ym}:${m.runs.length}`).join());
check('2回以上開かれた特集（ページがあればリンク先も）', facts.repeats.length === 1 && facts.repeats[0].title === 'メーカーA30％OFF' && facts.repeats[0].runs.length === 2 && facts.repeats[0].path === S.campaignPath('メーカーA30％OFF'));
check('期間の日数（いちばん短い・長い・平均）・記録の始まり', facts.minDays === 1 && facts.maxDays === 4 && facts.avgDays === 2.8 && facts.since === '2026-05-01', JSON.stringify([facts.minDays, facts.maxDays, facts.avgDays, facts.since]));

console.log('\n■ 出演者のページの「セール中の作品」（onSaleItems）');
const os = S.onSaleItems([...items, it('f', '2026-12-01', 1)], sale, '2026-10-05');
check('いまセール中の発売済みの作品だけ・人気の高い順・キャンペーンの終わりと名前つき', os.map((i) => i.cid).join() === 'c,b,a' && os[2].sale.price === 1884 && os[2].sale.end === '2026-10-06 09:59' && os[2].sale.title === 'メーカーA30％OFF', os.map((i) => i.cid).join());
check('終わったキャンペーンの作品は入れない', S.onSaleItems(items, sale, '2026-10-07').length === 0);

console.log('\n■ 出演者・メーカーのページの「入っているセール」（saleCampaignsOf）');
const sc = S.saleCampaignsOf([
  { sale: { title: 'B', k: 1, end: '2026-10-09 23:59' } }, { sale: { title: 'A', k: 0, end: '2026-10-07 23:59' } },
  { sale: { title: 'B', k: 1, end: '2026-10-09 23:59' } }, { sale: { title: 'C', k: 2, end: '2026-10-06 23:59' } }, {},
]);
check('本数の多い順・同じなら早く終わる順・名前ごとに1つ', sc.map((c) => `${c.title}${c.count}`).join() === 'B2,C1,A1' && sc[0].k === 1, sc.map((c) => `${c.title}${c.count}`).join());

console.log('\n■ セールの帯のグラフ（「FANZAのセールはいつ？」）');
check('帯のマス: 窓の中の位置・窓の前/後ろへ続く印・重ならなければ null',
  JSON.stringify(S.barSpan('2026-10-03', '2026-10-05', '2026-10-01', '2026-10-31')) === '{"s":2,"e":5,"cutL":false,"cutR":false}'
  && JSON.stringify(S.barSpan('2026-09-30', '2026-11-02', '2026-10-01', '2026-10-31')) === '{"s":0,"e":31,"cutL":true,"cutR":true}'
  && S.barSpan('2026-09-01', '2026-09-30', '2026-10-01', '2026-10-31') === null && S.barSpan('2026-10-05', '2026-10-04', '2026-10-01', '2026-10-31') === null
  && S.barSpan('x', '2026-10-04', '2026-10-01', '2026-10-31') === null);
const sp = { s: 2, e: 8, cutL: true, cutR: false };
const parts = S.splitAtToday(sp, 4);
check('きょうで分ける: きょうまで（開いていた日）とあしたから（これから）。前後へ続く印は、はしの帯にだけ',
  parts.length === 2 && parts[0].s === 2 && parts[0].e === 5 && !parts[0].future && parts[0].cutL && parts[0].joinR && parts[1].s === 5 && parts[1].e === 8 && parts[1].future && !parts[1].cutL && parts[1].joinL
  && S.splitAtToday(sp, 1)[0].future === true && S.splitAtToday(sp, 7)[0].future === false && S.splitAtToday(sp, 9).length === 1 && S.splitAtToday(null, 3).length === 0);
const tk = (a) => a.map((x) => `${x.i}:${x.label}${x.today ? '*' : ''}${x.edge}`).join(' ');
check('月の目もり: 1・5・10…とはじめのマス・きょう（きょうのすぐ近くの数字は外す）・はしの印',
  tk(S.dayTicks('2026-10-01', 31, '2026-10-06', { fixed: [1, 5, 10, 15, 20, 25, 30] })) === '0:1l 5:6* 9:10 14:15 19:20 24:25 29:30'
  && tk(S.dayTicks('2026-10-01', 31, '2026-10-02', { fixed: [1, 5, 10, 15, 20, 25, 30] })) === '1:2* 4:5 9:10 14:15 19:20 24:25 29:30', tk(S.dayTicks('2026-10-01', 31, '2026-10-06', { fixed: [1, 5, 10, 15, 20, 25, 30] })));
check('いま開催中の目もり: きょうから2日ごと・月が変わる日は「10/1」・重なる数字は外す',
  tk(S.dayTicks('2026-09-30', 21, '2026-10-06', { step: 2, anchor: '2026-10-06' })) === '1:10/1 4:4 6:6* 8:8 10:10 12:12 14:14 16:16 18:18 20:20r', tk(S.dayTicks('2026-09-30', 21, '2026-10-06', { step: 2, anchor: '2026-10-06' })));
const pg = (title, begin, end) => ({ title, path: `/sale/${title}/`, active: { title, begin, end, maxOff: 30 } });
const nc = S.nowChart([pg('A', '2026-10-05 10:00', '2026-10-07 23:59'), pg('B', '2026-09-20 00:00', '2026-10-31 23:59'), { title: 'C', active: null }], '2026-10-06');
check('いま開催中の帯: 6日前〜（長くても）20日後・きょうのマス・あと何日・開催していない特集は入れない',
  nc.from === '2026-09-30' && nc.to === '2026-10-26' && nc.days === 27 && nc.t === 6 && nc.rows.length === 2 && nc.rows[0].left === 1 && nc.rows[1].left === 25
  && nc.rows[1].parts[0].cutL && nc.rows[1].parts.at(-1).cutR && nc.rows[0].parts.map((p) => `${p.s}-${p.e}${p.future ? 'f' : ''}`).join() === '5-7,7-8f', JSON.stringify([nc.from, nc.to, nc.rows[0].parts]));
const nc2 = S.nowChart([pg('A', '2026-10-06 00:00', '2026-10-06 23:59')], '2026-10-06');
check('いま開催中の帯: 始まりが新しければ、そこから・終わりが近くても6日後まで見せる・開催中が無ければ null',
  nc2.from === '2026-10-06' && nc2.to === '2026-10-12' && nc2.t === 0 && nc2.rows[0].left === 0 && S.nowChart([], '2026-10-06') === null);
const runs = [
  { title: '日替わり', begin: '2026-10-06 00:00', end: '2026-10-06 23:59', first: '2026-10-06', last: '2026-10-06', maxOff: 70 },
  { title: '日替わり', begin: '2026-10-05 00:00', end: '2026-10-05 23:59', first: '2026-10-05', last: '2026-10-05', maxOff: 50 },
  { title: 'メーカーA', begin: '2026-09-30 10:00', end: '2026-10-08 09:59', first: '2026-10-05', last: '2026-10-06', maxOff: null },
  { title: 'メーカーB', begin: '2026-11-01 00:00', end: '2026-11-03 23:59', first: '2026-11-01', last: '2026-11-01', maxOff: null },
];
check('帯を作る月: 記録を始めた月から、きょうの月まで・開催のあった月だけ・新しい月から',
  S.historyMonths(runs, '2026-11-02').join() === '2026-11,2026-10' && S.historyMonths(runs, '2026-10-06').join() === '2026-10' && S.historyMonths([], '2026-10-06').length === 0);
const mc = S.monthChart(runs, '2026-10', '2026-10-06', new Map([[S.campaignSlug('日替わり'), { path: '/sale/x/' }]]));
check('月ごとの帯: 同じ名前は1行（回ごとに帯）・その月に早く始まった順・月の前から続く帯・いちばん大きい割引・日数・特集のページ',
  mc.days === 31 && mc.t === 5 && mc.rows.map((r) => r.title).join() === 'メーカーA,日替わり' && mc.rows[1].runs.length === 2 && mc.rows[1].path === '/sale/x/' && mc.rows[1].maxOff === 70
  && mc.rows[1].minDays === 1 && mc.rows[1].maxDays === 1 && mc.rows[0].parts[0].cutL && mc.rows[0].parts.map((p) => `${p.s}-${p.e}${p.future ? 'f' : ''}`).join() === '0-6,6-8f'
  && mc.rows[1].runs[0].begin.startsWith('2026-10-05'), JSON.stringify(mc.rows.map((r) => r.parts)));
check('前の月の帯: きょうは窓の後ろ（全部、開いていた日）', S.monthChart(runs, '2026-10', '2026-11-02').t === 31 && S.monthChart(runs, '2026-10', '2026-11-02').rows.every((r) => r.parts.every((p) => !p.future)));
check('短い期間の文字', S.shortRange(runs[2]) === '9/30〜10/8' && S.shortRange(runs[0]) === '10/6' && S.shortRange({ begin: '', first: '2026-10-05', end: '2026-10-07 10:00' }) === '10/5〜10/7');
console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
