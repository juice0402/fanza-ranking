// 独自の価値を足す部品（site/src/lib/insights.js）のテスト。実行: node tests/test_insights.mjs
// 人気の動きのグラフ・ランキングの1行・シリーズ/レーベルのまとまり・同じジャンルで人気・関連するジャンル・週のまとめへのリンク
import * as I from '../site/src/lib/insights.js';
import { normalizeItems } from '../site/src/lib/items.js';
import { normalizeRankHistory } from '../site/src/lib/popularity.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

console.log('■ 人気の動きのグラフ（作品ページ）');
const RH = normalizeRankHistory({ items: {
  a: { d: '2026-10-05', n: [120, 12, 3, 0, null, 8], a: [0, 0, 640] },
  one: { d: '2026-10-05', n: [5], a: [] },
  out: { d: '2026-10-05', n: [0, 0], a: [] },
} });
const ch = I.trendChart(RH.get('a'));
check('順位のある日は点・圏外の日は印・取れなかった日は何も描かない', ch && ch.points.map((p) => p.rank).join() === '120,12,3,8' && ch.outs.length === 1 && ch.outs[0].date === '2026-10-08', JSON.stringify(ch?.points));
check('線は続いている日だけつなぐ（圏外・取れなかった日で切る）', ch.path.startsWith('M') && (ch.path.match(/M/g) || []).length === 2 && (ch.path.match(/L/g) || []).length === 2, ch.path);
check('いちばん上の順位の点・日付のラベル（10/5 の形）', ch.best.rank === 3 && ch.best.label === '10/7' && ch.days.length === 6 && ch.days[0].label === '10/5');
check('縦の目盛りは対数（1位が上・500位が下・10位と100位は等間隔）', I.rankY(1) < I.rankY(10) && I.rankY(10) < I.rankY(100) && Math.abs((I.rankY(10) - I.rankY(1)) - (I.rankY(100) - I.rankY(10))) < 0.2 && I.rankY(9999) === I.rankY(500));
check('記録が1日だけ・一度も入っていない・記録が無いときはグラフを出さない', I.trendChart(RH.get('one')) === null && I.trendChart(RH.get('out')) === null && I.trendChart(undefined) === null);
check('文: 最高の順位と日付・500位以内の日数。全体の人気順に入っていれば、その最高', JSON.stringify(I.trendLines(RH.get('a'))) === JSON.stringify(['新着の人気順で最高3位（10月7日）・500位以内に4日', '全体の人気順（上位1,000本）でも最高640位（10月7日）']), JSON.stringify(I.trendLines(RH.get('a'))));
check('文: 一度も入っていなければ出さない', I.trendLines(RH.get('out')).length === 0 && I.trendLines(null).length === 0);

console.log('\n■ 新着の人気ランキングのカードの下の1行');
const prev = new Map([['x', 8], ['y', 2]]);
check('前日からの上がり下がり・最高順位（いまより上だったとき）', I.rankNote({ cid: 'x', popNew: 5 }, prev, { bestNew: { rank: 2 }, daysIn: 3 }) === '前日から▲3｜最高2位'
  && I.rankNote({ cid: 'y', popNew: 4 }, prev, { bestNew: { rank: 2 }, daysIn: 3 }) === '前日から▼2｜最高2位');
check('初登場・いまが最高位（前より上がったときだけ。1位は書かない）・何も分からなければ空', I.rankNote({ cid: 'z', popNew: 7 }, prev, { bestNew: { rank: 7 }, daysIn: 2, n: [20, 7] }) === '初登場｜いまが最高位'
  && I.rankNote({ cid: 'z', popNew: 7 }, prev, { bestNew: { rank: 7 }, daysIn: 2, n: [7, 7] }) === '初登場' && I.rankNote({ cid: 'y', popNew: 1 }, prev, { bestNew: { rank: 1 }, daysIn: 2, n: [3, 1] }) === '前日から▲1'
  && I.rankNote({ cid: 'z', popNew: 7 }, new Map(), null) === '');

console.log('\n■ シリーズ・レーベルのページ');
const items = normalizeItems([
  { cid: 's1', title: 'A', date: '2026-10-01', maker: 'M1', actress: ['花子'], series_id: 10, series: 'シリーズX', label_id: 20, label: 'レーベルY' },
  { cid: 's2', title: 'B', date: '2026-10-03', maker: 'M1', actress: ['花子', '月子'], series_id: 10, series: 'シリーズX', label_id: 20, label: 'レーベルY' },
  { cid: 's3', title: 'C', date: '2026-09-01', maker: 'M1', actress: ['月子'], series_id: 10, series: 'シリーズX（旧）', label_id: 20, label: 'レーベルY' },
  { cid: 's4', title: 'D', date: '2026-10-02', maker: 'M1', series_id: 10, series: 'シリーズX', label_id: 30, label: 'M1' },
  { cid: 't1', title: 'E', date: '2026-10-02', maker: 'M2', series_id: 11, series: '少女たち', label_id: 30, label: 'M1' },
  { cid: 't2', title: 'F', date: '2026-10-02', maker: 'M2', series_id: 11, series: '少女たち', label_id: 30, label: 'M1' },
  { cid: 't3', title: 'G', date: '2026-10-02', maker: 'M2', series_id: 11, series: '少女たち', label_id: 31, label: 'M2' },
  { cid: 't4', title: 'H', date: '2026-10-02', maker: 'M2', label_id: 31, label: 'M2' },
  { cid: 't5', title: 'I', date: '2026-10-02', maker: 'M2', label_id: 31, label: 'M2' },
]);
const series = I.groupByEntry(items, 'series');
check('シリーズは id でまとめる・名前はいちばん多い名前・新しい順・3本以上', series.length === 1 && series[0].id === 10 && series[0].name === 'シリーズX' && series[0].items.map((i) => i.cid).join() === 's2,s4,s1,s3' && series[0].path === '/series/10/', JSON.stringify(series.map((g) => [g.id, g.name])));
check('未成年を連想させる名前のシリーズは作らない', !series.some((g) => g.id === 11));
const labels = I.groupByEntry(items, 'label');
check('レーベルは、メーカーと同じ名前（いちばん多いメーカー）なら作らない・違う名前なら作る', labels.map((g) => g.id).sort().join() === '20,30' && labels.find((g) => g.id === 30).makers.join() === 'M2,M1' && labels.find((g) => g.id === 20).path === '/label/20/', JSON.stringify(labels.map((g) => [g.id, g.name, g.makers])));
check('最大の数（作品数の多い順）・最小の本数', I.groupByEntry(items, 'label', { max: 1 }).length === 1 && I.groupByEntry(items, 'series', { minItems: 5 }).length === 0);
check('タイトル・紹介文（作品データだけから）', I.entryPageTitle(series[0], '2026-10-07') === 'シリーズX（シリーズ）の新作・作品一覧【2026年10月】（4本）｜FANZA新作情報'
  && I.entrySummary(series[0]).startsWith('FANZAの「シリーズX」（シリーズ）の作品を4本掲載しています。発売日は2026年9月1日から2026年10月3日です。メーカーはM1です。出演は花子、月子です。'), I.entrySummary(series[0]));
const near = I.sameSeries(items[1], series[0], 2);
check('同じシリーズの作品: その作品を除いて、発売日の近い順', near.map((i) => i.cid).join() === 's4,s1', near.map((i) => i.cid).join());
const byId = new Map(labels.map((g) => [g.id, g]));
check('メーカーのページのチップ: ページのあるものだけ・本数の多い順', JSON.stringify(I.entryChips(items, byId, 'label')) === JSON.stringify([{ name: 'レーベルY', path: '/label/20/', count: 3 }, { name: 'M1', path: '/label/30/', count: 3 }]), JSON.stringify(I.entryChips(items, byId, 'label')));

console.log('\n■ 同じジャンルで人気・関連するジャンル・週のまとめへのリンク');
const pop = normalizeItems([
  { cid: 'p1', title: '人妻の休日', date: '2026-10-01', genres: ['人妻・主婦', '単体作品'] },
  { cid: 'p2', title: '人妻の旅', date: '2026-10-02', genres: ['人妻・主婦', 'ドラマ'] },
  { cid: 'p3', title: '制服の少女', date: '2026-10-02', genres: ['人妻・主婦'] },
  { cid: 'p4', title: '予約の作品', date: '2026-12-01', genres: ['人妻・主婦'] },
  { cid: 'p5', title: '順位なし', date: '2026-10-01', genres: ['人妻・主婦'] },
  { cid: 'p6', title: 'ドラマ', date: '2026-10-02', genres: ['ドラマ', '人妻・主婦'] },
]).map((i) => ({ ...i, popAll: { p1: 30, p2: 5, p3: 1, p4: 2, p6: 40 }[i.cid] ?? null, popNew: i.cid === 'p6' ? 3 : null }));
const genres = new Set(['人妻・主婦', 'ドラマ']);
const lists = I.genreTopLists(pop, genres, '2026-10-07');
check('ジャンルごとの人気の一覧: 発売済み・順位のある作品だけ・未成年を連想させるタイトルは入れない・全体と新着の上のほうの順位で', lists.get('人妻・主婦').map((i) => i.cid).join() === 'p6,p2,p1' && lists.get('ドラマ').map((i) => i.cid).join() === 'p6,p2', JSON.stringify([...lists].map(([g, l]) => [g, l.map((i) => i.cid)])));
const pig = I.popularInGenre(pop[0], lists, genres, new Set(['p6']));
check('作品ページの「○○で人気の作品」: いちばん目立つジャンル・その作品と、ほかの欄に出した作品を除く', pig.genre === '人妻・主婦' && pig.items.map((i) => i.cid).join() === 'p2', JSON.stringify(pig));
check('中身のジャンルが無い作品は出さない', I.popularInGenre({ ...pop[0], genres: ['単体作品'] }, lists, genres).items.length === 0);
const pages = new Map([['ドラマ', '/tag/d/'], ['人妻・主婦', '/tag/h/']]);
check('関連するジャンル: ページのあるジャンル・2本以上・本数の多い順', JSON.stringify(I.relatedGenres(pop, '人妻・主婦', genres, pages)) === JSON.stringify([{ name: 'ドラマ', path: '/tag/d/', count: 2 }]), JSON.stringify(I.relatedGenres(pop, '人妻・主婦', genres, pages)));
const rus = [{ week_start: '2026-09-28', week_end: '2026-10-04', picks: [{ cid: 'p1' }] }, { week_start: '2026-10-05', week_end: '2026-10-11', picks: [] }];
check('その作品の発売週の週のまとめ・注目の作品として紹介したか', I.roundupFor(pop[0], rus).pick === true && I.roundupFor(pop[0], rus).roundup.week_start === '2026-09-28' && I.roundupFor({ dateKey: '2026-10-20' }, rus) === null);
check('月のページの、その月の週のまとめ（月曜日がその月）', I.roundupsInMonth(rus, '2026-10').map((r) => r.week_start).join() === '2026-10-05' && I.roundupsInMonth(rus, '2026-09').length === 1);

console.log('\n■ ジャンルの「FANZA全体で人気の作品」（genre_tops.json）');
const own = { cid: 'own1', title: 'このサイトの作品', dateKey: '2026-09-01', actress: [], maker: 'M', genres: ['巨乳'], url: 'https://al.fanza.co.jp/x', image_url: 'https://pics.dmm.co.jp/x.jpg' };
const gtRow = (c, extra = {}) => ({ c, t: `作品${c}`, d: '2026-09-02', a: ['女優A', '', 3], m: 'メーカー', i: `https://pics.dmm.co.jp/digital/video/${c}/${c}pl.jpg`, u: `https://al.fanza.co.jp/?id=${c}`, ...extra });
const gt = I.normalizeGenreTops({ genres: {
  巨乳: { id: 2001, date: '2026-10-10', items: [gtRow('own1'), gtRow('f1', { v: 1 }), gtRow('f1'), gtRow('bad', { u: 'https://example.com/' }), gtRow('minor', { t: '女子校生の作品' }), gtRow('noimg', { i: '' }), 'x'] },
  空: { id: 1, date: '2026-10-10', items: [gtRow('x', { u: '' })] },
  日付なし: { id: 2, items: [gtRow('y')] },
} }, new Map([['own1', own]]));
const kyo = gt.get('巨乳');
check('このサイトの作品はそのまま・ほかは保存した形から（作品ページが無いのでFANZAへ）・人気の順', kyo.date === '2026-10-10' && kyo.items.map((i) => i.cid).join() === 'own1,f1'
  && kyo.items[0] === own && kyo.items[1].fanzaOnly && kyo.items[1].vr === true && kyo.items[1].actress.join() === '女優A' && kyo.items[1].genres.join() === '巨乳', kyo.items.map((i) => i.cid).join());
check('FANZA以外のURL・画像の無い行・未成年を連想させるタイトル・同じ作品・日付の無いジャンル・作品の無いジャンルは捨てる', !gt.has('空') && !gt.has('日付なし') && [null, 'x', { genres: [] }].every((v) => I.normalizeGenreTops(v).size === 0));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
