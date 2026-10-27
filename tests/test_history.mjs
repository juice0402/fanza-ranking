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

console.log('■ 女優の年表の一覧（/actress/nenpyo/）');
check('一覧の1行の短い数字（年の幅と本数）', H.historyBrief(h) === '2018〜2026年・120本' && H.historyBrief(null) === '', H.historyBrief(h));
const one = { ...h, total: 1234, first: { ...h.first, d: '2026-01-01' }, latest: null, years: [{ year: 2026, n: 1234, makers: [] }] };
check('同じ年だけの人は「2026年・1,234本」', H.historyBrief(one) === '2026年・1,234本', H.historyBrief(one));
const idx = H.nenpyoIndex([
  { name: '佐藤', path: '/actress/a/#hist-title', history: h, reading: 'さとう' },
  { name: '阿部', path: '/actress/b/#hist-title', history: h, reading: 'アベ' },
  { name: '伊藤', path: '/actress/c/#hist-title', history: h, reading: 'いとう' },
  { name: '草野', path: '/actress/d/#hist-title', history: h, reading: 'ぐさの' },
  { name: 'Mia', path: '/actress/e/#hist-title', history: h, reading: 'mia' },
  { name: '読めない', path: '/actress/f/#hist-title', history: h, reading: '' },
  { name: 'データなし', path: '/actress/g/#hist-title', history: null, reading: 'でーた' },
]);
check('50音の行の順・最後に「その他」（読みがなの無い人）', idx.map((r) => r.head).join(',') === 'あ,か,さ,英数,その他', idx.map((r) => r.head).join(','));
check('行の中は読みの順（カタカナもひらがなで比べる・濁音はもとの行）', idx[0].entries.map((e) => e.name).join(',') === '阿部,伊藤' && idx[1].entries[0].name === '草野', JSON.stringify(idx.map((r) => r.entries.map((e) => e.name))));
check('年表のデータが無い人は入れない・飛び先と短い数字', !idx.some((r) => r.entries.some((e) => e.name === 'データなし')) && idx[0].entries[0].path === '/actress/b/#hist-title' && idx[0].entries[0].brief === '2018〜2026年・120本' && idx[0].id === 'nenpyo-a');
console.log('\n■ 人気作ベスト・評価の高い作品（FANZA全体。topWorks）');
const own = { cid: 'own1', title: 'このサイトの作品', review: null };
const tw = H.topWorks([
  { c: 'own1', t: 'x', d: '2024-01-01', rv: [450, 9] },
  { c: 'f1', t: 'FANZAだけ', d: '2024-02-01', m: 'メーカー', i: 'https://pics.dmm.co.jp/f1.jpg', u: 'https://al.dmm.co.jp/?lurl=f1', rv: [420, 3] },
  { c: 'f2', t: '少女の作品', d: '2024-02-01', i: 'https://pics.dmm.co.jp/f2.jpg', u: 'https://al.dmm.co.jp/?lurl=f2' },
  { c: 'f3', t: 'よそのURL', d: '2024-02-01', i: 'https://pics.dmm.co.jp/f3.jpg', u: 'https://evil.example/f3' },
  { c: 'f1', t: '重なり', d: '2024-02-01', i: 'https://pics.dmm.co.jp/f1.jpg', u: 'https://al.dmm.co.jp/?lurl=f1' },
], new Map([['own1', own]]), (t) => t.includes('少女'));
check('このサイトの作品はそのまま（評価が無ければ保存した★）・ほかはFANZAへ・未成年を連想させる・よそのURL・重なりは入れない', tw.length === 2 && tw[0].cid === 'own1' && tw[0].review.avg === 4.5 && tw[1].cid === 'f1' && tw[1].url.startsWith('https://al.dmm.co.jp/') && tw[1].review.count === 3, JSON.stringify(tw.map((w) => w.cid)));
const hm = H.normalizeHistory({ actresses: { 9: { ...Object.values(raw.actresses)[0], popular: [{ c: 'f1', t: 'A', d: '2024-02-01', i: 'https://pics.dmm.co.jp/a.jpg', u: 'https://al.dmm.co.jp/a' }], rated: [{ c: 'f2', t: 'B', d: '2024-02-01', i: 'https://pics.dmm.co.jp/b.jpg', u: 'https://al.dmm.co.jp/b' }] } } });
const h1 = [...hm.values()][0];
check('年表の1人分に popular・rated（評価のほうは★のある作品だけ）', h1 && h1.popular.length === 1 && h1.rated.length === 0, JSON.stringify(h1 && [h1.popular.length, h1.rated.length]));
check('0人でもこわれない', Array.isArray(H.nenpyoIndex([])) && H.nenpyoIndex([]).length === 0);

console.log('■ 名簿の人のページ（女優名鑑その3。#173）');
{
  const base = Object.values(raw.actresses)[0];
  const hist = H.normalizeHistory({ actresses: {
    11: { ...base, name: '名簿A', total: 300 }, 12: { ...base, name: '名簿B', total: 49 }, 13: { ...base, name: 'ページあり', total: 500 },
    14: { ...base, name: '別の人', total: 80 }, 15: { ...base, name: '名簿C', total: 60 },
  } });
  const dir = new Map([['名簿A', { id: '11', name: '名簿A', img: 'nameboa', age: 25 }], ['名簿B', { id: '12', name: '名簿B', img: '' }], ['ページあり', { id: '13', name: 'ページあり', img: '' }],
    ['別の人', { id: '99', name: '別の人', img: '' }], ['名簿C', { id: '15', name: '名簿C', img: '' }]]);
  const gs = H.nenkanGroups(hist, dir, { takenNames: new Set(['ページあり']), slugOf: (n) => `s-${n}`, pathOf: (s) => `/actress/${s}/`, template: 'https://al.dmm.co.jp/?id={ID}', imageBase: 'https://pics.dmm.co.jp/x/' });
  check('年表があり50本以上・名簿の id が同じ・ページの無い人だけ（本数の多い順）', JSON.stringify(gs.map((g) => g.name)) === '["名簿A","名簿C"]', JSON.stringify(gs.map((g) => g.name)));
  const a = gs[0];
  check('作品は0本・プロフィールは名簿の値（顔写真と全作品のURL）', a.items.length === 0 && a.nenkan && a.path === '/actress/s-名簿A/' && a.profile.imageLarge === 'https://pics.dmm.co.jp/x/nameboa.jpg' && a.profile.listUrl === 'https://al.dmm.co.jp/?id=11' && a.profile.age === 25, JSON.stringify(a.profile));
  check('画像の無い人・URLの形が分からないときは空', gs[1].profile.imageLarge === '' && H.nenkanGroups(hist, dir, { slugOf: (n) => n, pathOf: (s) => s })[0].profile.listUrl === '');
  check('短い名前が重なる人は作らない', H.nenkanGroups(hist, dir, { takenSlugs: new Set(['s-名簿A']), slugOf: (n) => `s-${n}`, pathOf: (s) => s }).every((g) => g.name !== '名簿A'));
  const h = hist.get('名簿A');
  check('検索エンジンに出すのは、年表と紹介文の両方がある人だけ', H.nenkanIndexable(h, { text: '紹介文' }) && !H.nenkanIndexable(h, null) && !H.nenkanIndexable(null, { text: 'x' }));
  check('タイトル（プロフィールがあれば「プロフィール・」）', H.nenkanPageTitle('名簿A', h, true, 'サイト') === '名簿Aのプロフィール・年表と人気作（FANZA 300本）｜サイト' && H.nenkanPageTitle('名簿A', h, false, 'サイト') === '名簿Aの年表と人気作（FANZA 300本）｜サイト');
  const d1 = H.nenkanDescription('名簿A', h, null);
  const d2 = H.nenkanDescription('名簿A', h, { text: '名簿Aさんの作品は、2026年がいちばん多い64本でした。メーカーはメーカーAが110本で、ほとんどを占めています。FANZAでいちばん古い作品は2018年4月です。' });
  check('説明文は80〜120文字・本数から始まる（紹介文があれば紹介文の文を入れる）', [d1, d2].every((d) => d.length >= 80 && d.length <= 120 && d.startsWith('FANZAの作品は300本（2018年から）。')) && d2.includes('2026年がいちばん多い64本'), JSON.stringify([d1.length, d2.length, d1]));
}

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
