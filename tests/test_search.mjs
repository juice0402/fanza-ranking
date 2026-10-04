// 作品検索（site/src/lib/search.js の索引づくり・site/public/search.js の絞り込み）と、
// 「VR作品を隠す」スイッチ（site/public/vr-filter.js）の、画面に依存しない部分のテスト。実行: node tests/test_search.mjs
// （ブラウザでの見た目・タップの動きは、PRごとの確認で見る。ここでは、索引の形・絞り込みの正しさ・URLの読み書き・安全な値だけを通すことを見る）
import fs from 'node:fs';
import vm from 'node:vm';
import * as L from '../site/src/lib/search.js';
import { normalizeItems, rankHasHero } from '../site/src/lib/items.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};
const load = (file, extra = {}) => {
  const source = fs.readFileSync(new URL(`../site/public/${file}`, import.meta.url), 'utf-8');
  const sandbox = { module: { exports: {} }, ...extra };
  vm.runInNewContext(source, sandbox); // document が無い環境（node）では、部品だけを出して終わる
  return sandbox.module.exports;
};
const S = load('search.js', { URLSearchParams });
const V = load('vr-filter.js');
const plain = (v) => JSON.parse(JSON.stringify(v)); // vm の中で作られたオブジェクトを、普通のオブジェクトにする

const items = normalizeItems([
  { cid: 'a001', title: '【VR】新人VR 桜ゆの', date: '2026-10-03', maker: 'Vメーカー', actress: ['桜ゆの'], genres: ['VR専用', '巨乳'], tags: ['VR'], image_url: 'https://pics.dmm.co.jp/digital/video/a001/a001pl.jpg' },
  { cid: 'a002', title: '人妻の休日', date: '2026-10-02', maker: 'テストメーカー', actress: ['テスト花子', '桜ゆの'], genres: ['巨乳', '人妻', '中出し'], image_url: 'https://pics.dmm.co.jp/digital/video/a002/a002pl.jpg' },
  { cid: 'a003', title: '予約の作品', date: '2026-11-01', maker: '不明', actress: [], genres: [], image_url: 'https://pics.dmm.co.jp/digital/video/a003/a003pl.jpg' },
  { cid: 'a004', title: 'ふつうの作品', date: '2026-09-20', maker: 'テストメーカー', actress: ['テスト花子'], genres: ['人妻', '4K'], image_url: 'https://example.net/img.jpg' },
  { cid: 'a005', title: 'ジャンル重複', date: '2026-10-02', maker: 'テストメーカー', actress: [], genres: ['人妻', '人妻'], image_url: '' },
]);
const today = '2026-10-03';

console.log('■ 検索の索引（/data/items-index.json）');
const idx = L.buildItemsIndex(items, today);
check('generated・newDays・genres・items がある', idx.generated === today && typeof idx.newDays === 'number' && Array.isArray(idx.genres) && Array.isArray(idx.items));
check('作品は発売日の新しい順（同じ日は品番順）', idx.items.map((r) => r.c).join() === 'a003,a001,a002,a005,a004', idx.items.map((r) => r.c).join());
check('ジャンルは、作品の多い順（同数は名前順）・重複なし', idx.genres.join() === '人妻,巨乳,4K,VR専用,中出し', idx.genres.join());
const nameOf = (r) => r.g.map((n) => idx.genres[n]);
check('作品のジャンルの番号が、元のジャンルに戻る（重複は1つにまとめる）', nameOf(idx.items.find((r) => r.c === 'a002')).sort().join() === ['人妻', '巨乳', '中出し'].sort().join() && nameOf(idx.items.find((r) => r.c === 'a005')).join() === '人妻');
check('VR作品だけ v:1 が付く（それ以外は項目ごと無い）', idx.items.filter((r) => r.v === 1).map((r) => r.c).join() === 'a001' && idx.items.every((r) => r.v === undefined || r.v === 1));
check('メーカーが「不明」のときは空・出演者が空でも配列', idx.items.find((r) => r.c === 'a003').m === '' && Array.isArray(idx.items.find((r) => r.c === 'a003').a));
check('画像: DMMのURLの先頭を省く（DMM以外のホストの画像は、作品データの時点で外れて空になる）', idx.items.find((r) => r.c === 'a001').i === 'digital/video/a001/a001pl.jpg' && idx.items.find((r) => r.c === 'a004').i === '' && idx.items.find((r) => r.c === 'a005').i === '');
check('画像: ブラウザ側で付け直すと、もとの画像URLに戻る（DMMのもの）', idx.items.filter((r) => r.i.startsWith('digital/')).every((r) => S.imageUrl(r.i) === 'https://pics.dmm.co.jp/' + r.i && items.find((i) => i.cid === r.c).image_url === S.imageUrl(r.i)));
check('画像: DMM以外のホスト・ホスト名を似せたURL・空・数字は、ブラウザ側で使わない', ['https://example.net/img.jpg', 'https://dmm.co.jp.evil.example/a.jpg', 'https://evildmm.co.jp/a.jpg', '', null, 5].every((u) => S.imageUrl(u) === ''));
check('画像: ホストを偽る形（https://dmm.co.jp:@evil…）も通さない', S.imageUrl('https://evil.example/x.jpg') === '' && S.imageUrl('https://pics.dmm.co.jp:@evil.example/x.jpg') === '' && S.imageUrl('') === '');
check('個人情報や長い文（コメント・URL）は索引に入れない（短い名前 c,t,d,a,m,g,i,v だけ）', idx.items.every((r) => Object.keys(r).every((k) => 'ctdamgiv'.includes(k))) && !JSON.stringify(idx).includes('al.fanza.co.jp'));
const limited = L.buildItemsIndex(items, today, 2);
check('作品の数に上限がある（新しい順に残す）・ジャンル一覧は残した作品のものだけ', limited.items.map((r) => r.c).join() === 'a003,a001' && [...limited.genres].sort().join() === ['VR専用', '巨乳'].sort().join(), limited.genres.join());
check('空の入力でも落ちない', L.buildItemsIndex([], today).items.length === 0);
check('検索ページへのリンク: ジャンル名は URL 用に変える・空なら /search/', L.searchPath('巨乳') === '/search/?tag=%E5%B7%A8%E4%B9%B3' && L.searchPath('A&B=C') === '/search/?tag=A%26B%3DC' && L.searchPath() === '/search/' && L.searchPath('') === '/search/');

console.log('\n■ 絞り込み（ブラウザ側 search.js）');
const rows = plain(idx.items).map((r) => ({ ...r }));
S.prepare(rows, idx.genres);
const gn = (name) => idx.genres.indexOf(name);
const find = (state, opts = {}) => S.filterRows(rows, { terms: [], tags: [], status: '', sort: 'new', ...state }, { today, hideVr: false, ...opts }).map((r) => r.c).join();
check('条件なし: 全部・新しい順', find({}) === 'a003,a001,a002,a005,a004');
check('古い順', find({ sort: 'old' }) === 'a004,a002,a005,a001,a003');
check('ジャンル1つ', find({ tags: [gn('人妻')] }) === 'a002,a005,a004');
check('ジャンル2つは、両方を持つ作品だけ（AND）', find({ tags: [gn('人妻'), gn('巨乳')] }) === 'a002' && find({ tags: [gn('4K'), gn('巨乳')] }) === '');
check('発売済みだけ・予約だけ（今日が発売日のものは、発売済み）', find({ status: 'released' }) === 'a001,a002,a005,a004' && find({ status: 'upcoming' }) === 'a003');
check('VRを隠す: VR作品が消える', find({}, { hideVr: true }) === 'a003,a002,a005,a004' && find({ tags: [gn('巨乳')] }, { hideVr: true }) === 'a002');
check('キーワード: タイトル・出演者・メーカー・品番・ジャンルのどれでも当たる', find({ terms: S.splitTerms('人妻の休日') }) === 'a002' && find({ terms: S.splitTerms('桜ゆの') }) === 'a001,a002' && find({ terms: S.splitTerms('vメーカー') }) === 'a001' && find({ terms: S.splitTerms('A004') }) === 'a004' && find({ terms: S.splitTerms('4k') }) === 'a004');
check('キーワード: カタカナ/ひらがな・全角/半角・空白の違いを無視する（漢字と読みの対応は、索引に読みが無いので見ない）', find({ terms: S.splitTerms('ﾃｽﾄ花子') }) === 'a002,a004' && find({ terms: S.splitTerms('てすと　花子') }) === 'a002,a004' && find({ terms: S.splitTerms('ＶＭメーカー') }) === '' && find({ terms: S.splitTerms('ＶＭｅｎ') }) === '');
check('キーワード: 空白で区切った語は、全部を含む作品だけ。項目をまたいで当たらない', find({ terms: S.splitTerms('人妻 桜ゆの') }) === 'a002' && find({ terms: S.splitTerms('休日テスト') }) === '', find({ terms: S.splitTerms('休日テスト') }));
check('条件を全部組み合わせる', find({ terms: S.splitTerms('桜ゆの'), tags: [gn('巨乳')], status: 'released', sort: 'old' }, { hideVr: true }) === 'a002');
check('元の配列は並べ替えない', rows.map((r) => r.c).join() === 'a003,a001,a002,a005,a004');
check('語に分ける: 空・空白だけ・null は語なし', S.splitTerms('').length === 0 && S.splitTerms('  　 ').length === 0 && S.splitTerms(null).length === 0);

console.log('\n■ ジャンルごとの「足したときの数」（足すと0本になるジャンルを押せなくするため）');
const f0 = S.facetCounts(rows, { terms: [], tags: [], status: '', sort: 'new' }, { today, hideVr: false }, idx.genres.length);
check('条件なし: 全作品の数・ジャンルごとの本数', f0.total === 5 && f0.counts[gn('人妻')] === 3 && f0.counts[gn('巨乳')] === 2 && f0.counts[gn('VR専用')] === 1, JSON.stringify(f0));
const f1 = S.facetCounts(rows, { terms: [], tags: [gn('人妻')], status: '', sort: 'new' }, { today, hideVr: false }, idx.genres.length);
check('「人妻」を選ぶと、結果は3本・「巨乳」を足すと1本・「VR専用」を足すと0本・選んだジャンルは結果と同じ数', f1.total === 3 && f1.counts[gn('巨乳')] === 1 && f1.counts[gn('VR専用')] === 0 && f1.counts[gn('人妻')] === 3, JSON.stringify(f1));
const f2 = S.facetCounts(rows, { terms: [], tags: [], status: '', sort: 'new' }, { today, hideVr: true }, idx.genres.length);
check('VRを隠すと、VR作品のジャンル（VR専用）は0本になり、巨乳は1本になる', f2.total === 4 && f2.counts[gn('VR専用')] === 0 && f2.counts[gn('巨乳')] === 1, JSON.stringify(f2));
check('どの作品も持たない番号（範囲外）が混ざっても落ちない', S.facetCounts([{ c: 'z', t: 't', d: '2026-01-01', a: [], g: [99, -1, 0], _h: '' }], { terms: [], tags: [], status: '', sort: 'new' }, { today, hideVr: false }, 2).counts.join() === '1,0');

console.log('\n■ 最初に出すジャンル');
check('選んだものは必ず出す・あとは結果が1本以上あるものを、並びのまま limit 個まで', plain(S.visibleTags([5, 0, 3, 9, 2], [1], 2, false)).join() === '0,1,2' && plain(S.visibleTags([5, 0, 3, 9, 2], [], 10, false)).join() === '0,2,3,4');
check('expanded なら、0本のものも含めて全部', plain(S.visibleTags([5, 0, 3], [], 1, true)).join() === '0,1,2');
check('最初に出す数・1回に出す作品の数', S.TAGS_COLLAPSED === 14 && S.PAGE_SIZE === 24);

console.log('\n■ URL（?q=…&tag=…&st=…&sort=…）');
const genres = ['人妻', '巨乳', 'A&B'];
const q1 = plain(S.parseQuery('?q=%E6%A1%9C&tag=%E5%B7%A8%E4%B9%B3&tag=A%26B&tag=%E5%B7%A8%E4%B9%B3&st=released&sort=old', genres));
check('読む: キーワード・ジャンル（名前→番号。重複は1つ・記号つきも読める）・発売の状態・並び順', q1.q === '桜' && q1.tags.join() === '1,2' && q1.status === 'released' && q1.sort === 'old', JSON.stringify(q1));
const q2 = plain(S.parseQuery('?tag=%E5%AD%98%E5%9C%A8%E3%81%97%E3%81%AA%E3%81%84&st=hack&sort=zzz&q=' + 'あ'.repeat(300), genres));
check('読む: 知らないジャンルは捨てる・変な状態/並び順は既定に戻す・キーワードは100文字まで', q2.tags.length === 0 && q2.status === '' && q2.sort === 'new' && q2.q.length === 100, JSON.stringify(q2).slice(0, 120));
check('読む: 空・null でも落ちない', plain(S.parseQuery('', genres)).tags.length === 0 && plain(S.parseQuery(null, genres)).sort === 'new');
check('書く: 条件が無ければ空文字（URLをきれいに保つ）', S.buildQuery({ q: '', tags: [], status: '', sort: 'new' }, genres) === '' && S.buildQuery({}, genres) === '');
check('書く: ジャンル名・キーワードは URL 用に変える', S.buildQuery({ q: ' 人妻 ', tags: [2, 0], status: 'upcoming', sort: 'old' }, genres) === '?q=%E4%BA%BA%E5%A6%BB&tag=A%26B&tag=%E4%BA%BA%E5%A6%BB&st=upcoming&sort=old', S.buildQuery({ q: ' 人妻 ', tags: [2, 0], status: 'upcoming', sort: 'old' }, genres));
check('書く→読む で、同じ条件に戻る', (() => {
  const state = { q: '桜 ゆの', tags: [0, 2], status: 'released', sort: 'old' };
  const back = plain(S.parseQuery(S.buildQuery(state, genres), genres));
  return back.q === state.q && back.tags.join() === '0,2' && back.status === state.status && back.sort === state.sort;
})());

console.log('\n■ 作品の1行・日付・安全な値');
check('索引の1行が使える形か（品番は英数字・ハイフン・下線だけ。日付はYYYY-MM-DD。出演者・ジャンルは配列）', S.isRow(rows[0]) && !S.isRow({ ...rows[0], c: '../x' }) && !S.isRow({ ...rows[0], c: 'a b' }) && !S.isRow({ ...rows[0], d: '昨日' }) && !S.isRow({ ...rows[0], a: 'x' }) && !S.isRow({ ...rows[0], g: null }) && !S.isRow({ ...rows[0], t: '' }) && !S.isRow(null) && !S.isRow('x'));
check('「新作」「予約」のシール: 今日以降は予約・6日以内は新作・それより前は無し', S.statusOf('2026-10-04', today, 6) === 'wait' && S.statusOf('2026-10-03', today, 6) === 'new' && S.statusOf('2026-09-27', today, 6) === 'new' && S.statusOf('2026-09-26', today, 6) === '');
check('日本時間の今日（UTC 15:30 → 翌日）', S.jstToday(Date.UTC(2026, 9, 1, 15, 30)) === '2026-10-02' && S.jstToday(Date.UTC(2026, 9, 1, 14, 59)) === '2026-10-01');
check('検索用の文字: 全角/半角・カタカナ/ひらがな・大文字小文字・空白と中点を無視', S.normalizeText('ＡＢｃ　テスト・花子') === 'abcてすと花子' && S.normalizeText(null) === '');

console.log('\n■ 「VR作品を隠す」スイッチ（vr-filter.js）');
check('保存のキーと、html に付ける印', V.KEY === 'hide-vr' && V.CLASS === 'hide-vr');
check('日付ごとの本数の文字: 隠さないとき・VRが無いときは元のまま', V.dayCountText('5本', 5, 2, false) === '5本' && V.dayCountText('5本', 5, 0, true) === '5本' && V.dayCountText('3本（全5本）', 3, 0, true) === '3本（全5本）');
check('日付ごとの本数の文字: 隠すときは、VRを除いた本数（「全◯本」は、VRが分からないので出さない）', V.dayCountText('5本', 5, 2, true) === '3本（VRを除く）' && V.dayCountText('3本（全5本）', 3, 1, true) === '2本（VRを除く）');
check('全部がVRの日付だけ、隠したときに空になる', V.dayIsEmpty(2, 2, true) && !V.dayIsEmpty(2, 1, true) && !V.dayIsEmpty(2, 2, false) && !V.dayIsEmpty(0, 0, true));

console.log('\n■ 売れ筋TOP3の並べ直し（VR作品を隠して本数が減っても、空白を作らない）');
const RL = (flags, hide) => plain(V.rankLayout(flags, hide));
check('隠さないとき: 3本・先頭の1位を大きく（VRが混ざっていても、そのまま）', JSON.stringify(RL([false, false, false], false)) === '{"visible":3,"hero":0}' && JSON.stringify(RL([false, false, true], false)) === '{"visible":3,"hero":0}');
check('3位がVRで隠すとき: 2本・大きく出す1本は無し（同じ大きさで2つ並べる）', JSON.stringify(RL([false, false, true], true)) === '{"visible":2,"hero":-1}');
check('1位がVRで隠すとき: 2本・大きく出す1本は無し', JSON.stringify(RL([true, false, false], true)) === '{"visible":2,"hero":-1}');
check('2つがVRで隠すとき: 残った1本を、横幅いっぱいに大きく出す（何位でも）', JSON.stringify(RL([true, true, false], true)) === '{"visible":1,"hero":2}' && JSON.stringify(RL([false, true, true], true)) === '{"visible":1,"hero":0}' && JSON.stringify(RL([true, false, true], true)) === '{"visible":1,"hero":1}');
check('全部がVRで隠すとき: 0本（売れ筋の見出しごと隠す）', JSON.stringify(RL([true, true, true], true)) === '{"visible":0,"hero":-1}');
check('作品が無い・2本だけのときも落ちない', JSON.stringify(RL([], true)) === '{"visible":0,"hero":-1}' && JSON.stringify(RL([false, false], false)) === '{"visible":2,"hero":-1}');
check('ページを作るときの決め方（rankHasHero）と、ブラウザでの決め方（rankLayout）が、本数ごとに同じ', [0, 1, 2, 3, 4].every((n) => rankHasHero(n) === (RL(Array(n).fill(false), false).hero === 0)));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
