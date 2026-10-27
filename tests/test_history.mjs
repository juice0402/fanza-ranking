// 女優の歩み（site/src/lib/history.js）のテスト。実行: node tests/test_history.mjs
import * as H from '../site/src/lib/history.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

const raw = {
  updated: '2026-10-27',
  actresses: {
    1: {
      name: '花子', checked: '2026-10-27', total: 120, upcoming: 2,
      first: { c: 'abc00001', d: '2018-04-14', m: 'メーカーA', t: '作品のタイトル1' },
      latest: { c: 'abc00200', d: '2026-10-23', m: 'メーカーA', t: '作品のタイトル200' },
      years: { 2018: { n: 6, m: [['メーカーA', 6]] }, 2021: { n: 50, m: [['メーカーA', 40], ['メーカーB', 10]] }, 2026: { n: 64, m: [['メーカーA', 64]] }, 2030: { n: 0 }, xx: { n: 3 } },
      makers: [{ m: 'メーカーA', n: 110, f: '2018-04-14', c: 'abc00001' }, { m: 'メーカーB', n: 10, f: '2021-03-01', c: 'bbb00001' }, { m: 'メーカーC', n: 2, f: '2022-01-01', c: 'ccc00001' }],
      milestones: [{ c: 'abc00100', d: '2024-01-05', m: 'メーカーA', t: '節目の作品', n: 100 }],
      vr: { n: 4, first: { c: 'vvv00001', d: '2021-11-25', m: 'メーカーA', t: '【VR】作品' } },
      best: 30, solo: 80, costars: [['月子', 3], ['', 2], ['星子', 0]], genres: [['ハイビジョン', 100], ['美少女', 40], ['巨乳', 20]],
    },
    2: { name: '読めない人', checked: '2026-10-27', total: 0, first: null },
    3: { name: '', checked: '2026-10-27', total: 3, first: { c: 'x00001', d: '2020-01-01' } },
  },
};
const map = H.normalizeHistory(raw);
const h = map.get('花子');
check('読める人だけ（本数0・名前なし・いちばん古い作品なしは入れない）', map.size === 1 && h && h.total === 120 && h.upcoming === 2);
check('年は数字の年だけ・0本の年は入れない・古い順', h.years.map((y) => y.year).join(',') === '2018,2021,2026', JSON.stringify(h.years.map((y) => y.year)));
check('共演は名前と1本以上だけ', h.costars.length === 1 && h.costars[0].name === '月子' && h.costars[0].n === 3);
check('空のデータ・形の違うデータでも止まらない', H.normalizeHistory(null).size === 0 && H.normalizeHistory({ actresses: 'x' }).size === 0);

console.log('■ 棒グラフ');
const bars = H.yearBars(h);
check('いちばん古い年から最後の年まで、0本の年も入れる', bars.length === 9 && bars[0].year === 2018 && bars[1].n === 0 && bars[3].n === 50 && bars[8].n === 64, JSON.stringify(bars.map((b) => [b.year, b.n])));
check('年の目盛り: 12年までは全部', H.yearTicks(Array.from({ length: 12 }, (_, i) => ({ year: 2010 + i, n: 1 }))).length === 12);
const long = Array.from({ length: 18 }, (_, i) => ({ year: 2009 + i, n: 1 }));
check('年の目盛り: 多いときは最初・最後と5で割り切れる年（端に近すぎる年は出さない）', H.yearTicks(long).join(',') === '2009,2015,2020,2026', H.yearTicks(long).join(','));
check('いちばん多い年（同じなら新しい年）', H.peakYear(h).year === 2026 && H.peakYear(null) === null);

console.log('■ 年譜');
const tl = H.historyTimeline(h);
check('古い順・FANZAでいちばん古い作品が先頭', tl[0].label === 'FANZAでいちばん古い作品' && tl[0].when === '2018年4月', JSON.stringify(tl.map((r) => r.label)));
check('メーカーは3本以上・最初のメーカーは除く', tl.some((r) => r.label === 'メーカーBでいちばん古い作品') && !tl.some((r) => r.label.startsWith('メーカーC')) && !tl.some((r) => r.label === 'メーカーAでいちばん古い作品'));
check('VR・100本目・いちばん新しい作品', tl.map((r) => r.label).join('|') === 'FANZAでいちばん古い作品|メーカーBでいちばん古い作品|いちばん古いVR作品|100本目|いちばん新しい作品', tl.map((r) => r.label).join('|'));
check('1行と説明文の頭', H.historyLine(h) === 'FANZAの作品120本・2018年から（予約2本）' && H.historyDescriptionHead(h) === 'FANZAの作品は120本（2018年から）。' && H.historyLine(null) === '');
check('ジャンルは許した名前だけ（形式のジャンルは出ない）', H.historyGenres(h, new Set(['美少女', '巨乳'])).map((g) => g.name).join(',') === '美少女,巨乳');

console.log('■ 紹介文');
const st = H.normalizeStories({ stories: { 花子: { text: ' 紹介文です。 ', written: '2026-10-28', checked: '2026-10-27' }, 月子: { text: '', written: '2026-10-28' }, 星子: { text: 'x', written: 'きのう' } } });
check('書いた日のある紹介文だけ（前後の空白は取る）', st.size === 1 && st.get('花子').text === '紹介文です。' && st.get('花子').checked === '2026-10-27');

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
