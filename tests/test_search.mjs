// 作品検索（site/src/lib/search.js の索引づくり・site/public/search.js の絞り込み）と、
// 「VR作品を隠す」スイッチ（site/public/vr-filter.js）の、画面に依存しない部分のテスト。実行: node tests/test_search.mjs
// （ブラウザでの見た目・タップの動きは、PRごとの確認で見る。ここでは、索引の形・絞り込みの正しさ・URLの読み書き・安全な値だけを通すことを見る）
import fs from 'node:fs';
import vm from 'node:vm';
import * as L from '../site/src/lib/search.js';
import { normalizeItems, RANKING_SHOWN, CAST_LIMIT, castLine, castParts } from '../site/src/lib/items.js';

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
check('個人情報や長い文（コメント・URL）は索引に入れない（短い名前 c,p,t,d,a,m,g,i,v だけ）', idx.items.every((r) => Object.keys(r).every((k) => 'cptdamgiv'.includes(k))) && !JSON.stringify(idx).includes('al.fanza.co.jp'));
const coded = L.buildItemsIndex(normalizeItems([{ cid: '1dldss00566', title: '品番のある作品です。長めの題名にしておきます', date: '2026-10-01', maker: 'DAHLIA', actress: ['青坂あおい'] }, { cid: 'a001', title: 'x', date: '2026-10-01' }]), today);
check('品番を作れる作品には p（例 DLDSS-566）が入る。作れない作品には無い', coded.items.find((r) => r.c === '1dldss00566').p === 'DLDSS-566' && !('p' in coded.items.find((r) => r.c === 'a001')));
const ct = coded.items.find((r) => r.c === '1dldss00566').t;
check('タイトルには、文節の区切りに幅のない空白（U+200B）が入る。取り除くと元のタイトルに戻る', ct.includes('\u200b') && ct.replace(/\u200b/g, '') === '品番のある作品です。長めの題名にしておきます', JSON.stringify(ct));
const named = L.buildItemsIndex(normalizeItems([{ cid: 'n1', title: '出演は青坂あおいさんの作品', date: '2026-10-01', actress: ['青坂あおい'] }]), today).items[0].t;
check('タイトルの中の出演者名の途中には、区切りを入れない', named.includes('青坂あおいさん') || named.includes('青坂あおい'), JSON.stringify(named));
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
{
  // 人気順（索引の r: 全体の人気順・n: 新着の人気順）。順位の無い作品は、そのあとに新しい順
  const pr = plain(L.buildItemsIndex(items.map((i) => ({ ...i, popAll: { a004: 3, a002: 10 }[i.cid] ?? null, popNew: { a001: 1, a005: 2 }[i.cid] ?? null })), today).items).map((r) => ({ ...r }));
  S.prepare(pr, idx.genres);
  const by = (sort) => S.filterRows(pr, { terms: [], tags: [], status: '', sort }, { today, hideVr: false }).map((r) => r.c).join();
  check('索引に、全体の人気順（r）・新着の人気順（n）が入る（分からなければ無い）', pr.find((r) => r.c === 'a004').r === 3 && pr.find((r) => r.c === 'a001').n === 1 && !('r' in pr.find((r) => r.c === 'a003')) && !('n' in pr.find((r) => r.c === 'a004')));
  check('人気順（全体）: 順位の上から・順位の無い作品はそのあと新しい順', by('pop') === 'a004,a002,a003,a001,a005', by('pop'));
  check('人気順（新着）: 新着の順位の上から・順位の無い作品はそのあと新しい順', by('popnew') === 'a001,a005,a003,a002,a004', by('popnew'));
  const popIdx = L.buildItemsIndex(items.map((i) => ({ ...i, popAll: i.cid === 'a004' ? 1 : null })), today, 2, 1);
  check('索引に入れる作品: 全体の人気順の上位は、古くても先に入れる（残りは新しい順）。並びは発売日の新しい順', popIdx.items.map((r) => r.c).join() === 'a003,a004', popIdx.items.map((r) => r.c).join());
}
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
check('読む・書く: 人気順（新着・全体）も URL に入る', plain(S.parseQuery('?sort=popnew', genres)).sort === 'popnew' && plain(S.parseQuery('?sort=pop', genres)).sort === 'pop' && S.buildQuery({ sort: 'pop' }, genres) === '?sort=pop' && S.buildQuery({ sort: 'popnew' }, genres) === '?sort=popnew' && S.buildQuery({ sort: 'toString' }, genres) === '' && plain(S.parseQuery('?sort=constructor', genres)).sort === 'new');
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
check('検索用の文字: 品番の「-」と、文節の区切り（U+200B）も無視する', S.normalizeText('DLDSS-566') === 'dldss566' && S.normalizeText('ＤＬＤＳＳ－５６６') === 'dldss566' && S.normalizeText('作品\u200bです') === 'さくひんです'.replace('さくひん', '作品'));
const crow = plain(coded.items).map((r) => ({ ...r }));
S.prepare(crow, coded.genres);
const byCode = (q) => S.filterRows(crow, { terms: S.splitTerms(q), tags: [], status: '', sort: 'new' }, { today, hideVr: false }).map((r) => r.c).join();
check('品番で探せる（DLDSS-566・dldss566・dldss-566・DLDSS566・作品IDの dldss00566）', ['DLDSS-566', 'dldss566', 'dldss-566', 'DLDSS566', 'dldss00566'].every((q) => byCode(q) === '1dldss00566'), ['DLDSS-566', 'dldss566'].map(byCode).join('/'));
check('タイトルの言葉で探すとき、文節の区切りがあっても見つかる（「作品です」）', byCode('作品です') === '1dldss00566');

console.log('\n■ 「VR作品を隠す」「単体作品のみ表示」スイッチ（vr-filter.js）');
check('保存のキーと、html に付ける印', V.KEY === 'hide-vr' && V.CLASS === 'hide-vr' && V.SOLO_KEY === 'only-solo' && V.SOLO_CLASS === 'only-solo');
check('本数の注記: VRを隠す・単体作品のみ・両方・どちらも無し', V.filterNote(true, false) === '（VRを除く）' && V.filterNote(false, true) === '（単体作品のみ）' && V.filterNote(true, true) === '（単体作品・VRを除く）' && V.filterNote(false, false) === '');
check('マスが隠れるか: VRを隠すときはVR作品、単体作品のみのときは単体でない作品', V.cellHidden(true, true, true, false) && !V.cellHidden(false, false, true, false) && V.cellHidden(false, false, false, true) && !V.cellHidden(false, true, false, true) && V.cellHidden(true, true, true, true) && !V.cellHidden(true, false, false, false));
check('日付ごとの本数の文字: 絞り込まないとき・隠れる作品が無いときは元のまま', V.dayCountText('5本', 5, 2, '') === '5本' && V.dayCountText('5本', 5, 0, '（VRを除く）') === '5本' && V.dayCountText('3本（全5本）', 3, 0, '（単体作品のみ）') === '3本（全5本）');
check('日付ごとの本数の文字: 絞り込むときは、隠れない本数と注記（「全◯本」は分からないので出さない）', V.dayCountText('5本', 5, 2, '（VRを除く）') === '3本（VRを除く）' && V.dayCountText('3本（全5本）', 3, 1, '（単体作品のみ）') === '2本（単体作品のみ）');
check('全部が隠れる日付だけ、空になる', V.dayIsEmpty(2, 2) && !V.dayIsEmpty(2, 1) && !V.dayIsEmpty(0, 0));

console.log('\n■ トップの新着人気TOP3の出し方（VR作品を隠すときは、VRを除いて次の順位から差し替え）');
const RL = (flags, hide, show = 3) => plain(V.rankLayout(flags, hide, show));
const RLs = (flags, hide, show = 3) => JSON.stringify(RL(flags, hide, show));
check('隠さないとき: 先頭の3本をそのまま（VRが混ざっていても）。4位以降は出さない', RLs([0, 0, 0, 0, 0, 0], false) === '{"shown":[0,1,2],"visible":3}' && RLs([0, 0, 1, 0, 0, 0], false) === '{"shown":[0,1,2],"visible":3}');
check('3位がVRで隠すとき: 4位が繰り上がって、先頭の3本（1・2・4位）', RLs([0, 0, 1, 0, 0, 0], true) === '{"shown":[0,1,3],"visible":3}');
check('1位がVRで隠すとき: 2・3・4位が出る', RLs([1, 0, 0, 0, 0, 0], true) === '{"shown":[1,2,3],"visible":3}');
check('VRが多くて隠すとき: 6本の中から、VRでない先頭3本を拾う', RLs([1, 1, 0, 1, 0, 0], true) === '{"shown":[2,4,5],"visible":3}');
check('VRでない作品が2本・1本しか無いとき: その本数だけ', RLs([1, 1, 0, 1, 1, 0], true) === '{"shown":[2,5],"visible":2}' && RLs([1, 1, 1, 1, 1, 0], true) === '{"shown":[5],"visible":1}');
check('全部がVRで隠すとき: 0本（TOP3の見出しごと隠す）', RLs([1, 1, 1, 1, 1, 1], true) === '{"shown":[],"visible":0}');
check('データが3本だけでも動く（3位がVRなら2本）', RLs([0, 0, 1], true) === '{"shown":[0,1],"visible":2}' && RLs([0, 0, 1], false) === '{"shown":[0,1,2],"visible":3}');
check('作品が無い・2本だけのときも落ちない', RLs([], true) === '{"shown":[],"visible":0}' && RLs([0, 0], false) === '{"shown":[0,1],"visible":2}');
check('出す本数（show）を変えても、その本数までで止まる', RLs([0, 0, 0, 0, 0, 0], false, 2) === '{"shown":[0,1],"visible":2}');
check('出す本数の設定（RANKING_SHOWN）は3', RANKING_SHOWN === 3);

console.log('\n■ 一覧の出演者は3名まで（オムニバスなど、出演者が多い作品で、カードが長くならないように）');
const many34 = Array.from({ length: 34 }, (_, i) => `出演者${i + 1}`);
check('一覧の出演者の人数は3（設定）', CAST_LIMIT === 3);
check('3名まで出して、残りは「ほか○名」', castLine(many34) === '出演者1、出演者2、出演者3 ほか31名' && castParts(many34).more === 31, castLine(many34));
check('3名以下なら全員・「ほか」は付けない・いなければ「出演者の記載なし」', castLine(['花子', '月子']) === '花子、月子' && castLine(['花子', '月子', '星子']) === '花子、月子、星子' && castLine([]) === '出演者の記載なし' && castLine(undefined, 3, '') === '');
check('人数を変えられる（トップのTOP3は2名）', castLine(['花子', '月子', '星子'], 2) === '花子、月子 ほか1名');
check('作品検索の画面（search.js）も、同じ3名まで', S.CAST_LIMIT === CAST_LIMIT && JSON.stringify(plain(S.castShown(many34, S.CAST_LIMIT))) === JSON.stringify({ names: many34.slice(0, 3), more: 31 }) && plain(S.castShown(['花子'], 3)).more === 0);

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
