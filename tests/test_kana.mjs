// 読みがな・50音の並びの部品（site/src/lib/kana.js）と、作品検索の読みがなのテスト。実行: node tests/test_kana.mjs
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import * as K from '../site/src/lib/kana.js';
import { buildItemsIndex } from '../site/src/lib/search.js';
import { floorSearchIndex } from '../site/src/lib/floors.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

console.log('■ 50音の行');
check('カタカナ・半角もひらがなに', K.toHiragana('ムーディーズ') === 'むーでぃーず' && K.toHiragana('ｴｽﾜﾝ') === 'えすわん');
check('行: 濁音・半濁音・小さい字はもとの行、ひらがなでない字は「英数」',
  K.kanaRow('がくえん').head === 'か' && K.kanaRow('ぱんだ').head === 'は' && K.kanaRow('ゔぃーなす').head === 'あ' && K.kanaRow('ヤマト').head === 'や'
  && K.kanaRow('をとめ').head === 'わ' && K.kanaRow('s1').head === '英数' && K.kanaRow('').head === '英数');

console.log('\n■ readings.json');
const R = K.normalizeReadings({ updated: '2026-10-10', next: { 'video.series': 3 }, video: { maker: { ムーディーズ: 'むーでぃーず', 空: '', 長い: 'あ'.repeat(61) }, series: { 12: 'シリーズ' } }, doujin: { maker: { 500: 'さーくる' } }, game: 'x' });
check('売り場・種類・キーで引ける（カタカナはひらがなに。空・長すぎる読みは捨てる）',
  R.updated === '2026-10-10' && R.of('video', 'maker', 'ムーディーズ') === 'むーでぃーず' && R.of('video', 'series', 12) === 'しりーず'
  && R.of('doujin', 'maker', '500') === 'さーくる' && R.of('video', 'maker', '空') === '' && R.of('video', 'maker', '長い') === '' && R.of('game', 'maker', '1') === '');
check('無い・壊れていても空', [null, 'x', [], {}].every((v) => K.normalizeReadings(v).of('video', 'maker', 'a') === ''));
check('漢字の入った読み（FANZAの一覧に、名前がそのまま入っているもの）は使わない', K.normalizeReadings({ video: { maker: { 桃: '桃太郎映像', S: 'えすわん' } } }).of('video', 'maker', '桃') === ''
  && K.readingLine('桃太郎映像', '桃太郎映像') === '' && K.readingLine('名前', '名まえ') === '');
check('見出しの下の読み: 名前と同じ読み（ひらがなの名前・カタカナの名前）は出さない',
  K.readingLine('三上悠亜', 'みかみゆあ') === 'みかみゆあ' && K.readingLine('あやみ旬果', 'あやみしゅんか') === 'あやみしゅんか'
  && K.readingLine('つぼみ', 'つぼみ') === '' && K.readingLine('ムーディーズ', 'むーでぃーず') === '' && K.readingLine('名前', '') === '');

console.log('\n■ 50音で探す');
const e = (name, count, reading = '') => ({ name, path: `/m/${name}/`, count, reading });
const many = Array.from({ length: 30 }, (_, n) => e(`名${n}`, 100 - n, ['かきく', 'あいう', 'さしす', 'ばびぶ', 'わをん'][n % 5] + n));
const idx = K.kanaIndex([...many, e('Zeta', 1), e('読み無し', 2)], { top: 5, prefix: 'mk' });
check('読みの分かる名前が多ければ出す・上に作品数の多い順のタイル（決めた数）', idx.show && idx.top.length === 5 && idx.top[0].name === '名0');
check('行は50音の順（無い行は飛ばす）・読みの分からない名前は「英数」の行に、名前で並べる',
  idx.rows.map((r) => r.head).join() === 'あ,か,さ,は,わ,英数' && idx.rows.at(-1).entries.map((x) => x.name).join() === 'Zeta,読み無し' && idx.rows[0].id === 'mk-a');
check('行の中は読みの順・全部の名前がどこかの行にある', idx.rows[0].entries[0].reading <= idx.rows[0].entries[1].reading
  && idx.rows.reduce((n, r) => n + r.entries.length, 0) === 32);
const jumps = K.kanaJumps(idx.rows, 'mk');
check('行へのボタン: 11個・行が無いものは押せない', jumps.length === 11 && jumps.find((j) => j.head === 'な').href === '' && jumps.find((j) => j.head === 'か').href === '#mk-ka');
const few = K.kanaIndex([e('a', 3, 'あ'), e('b', 2)]);
check('読みの分かる名前が少ない・半分に満たないときは出さない（タイルだけ）', !few.show && few.top.length === 2 && few.rows.length === 0
  && !K.kanaIndex([...many.slice(0, 20), ...Array.from({ length: 21 }, (_, n) => e(`x${n}`, 1))]).show);

console.log('\n■ 作品検索で、ひらがなで打っても見つかる');
const item = (cid, actress, maker, genres) => ({ cid, title: `作品${cid}`, dateKey: '2026-10-01', actress, maker, genres, image_url: '', popAll: null, popNew: null });
const index = buildItemsIndex([item('a1', ['三上悠亜'], 'エスワン', ['巨乳']), item('a2', ['つぼみ'], '不明', [])], '2026-10-10', 3000, 1000,
  (name) => ({ 三上悠亜: 'みかみゆあ', エスワン: 'えすわん', 巨乳: 'きょにゅう', つぼみ: 'つぼみ' })[name] ?? '');
check('索引の yomi に、出演者・メーカー・ジャンルの読み（名前と同じ読み＝ひらがな・カタカナの名前は入れない）', JSON.stringify(index.yomi) === JSON.stringify({ 三上悠亜: 'みかみゆあ', 巨乳: 'きょにゅう' }), JSON.stringify(index.yomi));
const sandbox = { module: { exports: {} } };
vm.runInNewContext(readFileSync(new URL('../site/public/search.js', import.meta.url), 'utf8'), sandbox);
const S = sandbox.module.exports;
if (S.prepare) {
  const rows = JSON.parse(JSON.stringify(index.items));
  S.prepare(rows, index.genres, index.yomi);
  const find = (q) => S.filterRows(rows, { terms: S.splitTerms(q), tags: [], status: '', sort: 'new' }, { today: '2026-10-10' }).map((r) => r.c).join();
  check('「みかみ」「ミカミ」「えすわん」「きょにゅう」で見つかる（読みの無い作品には当たらない）', find('みかみ') === 'a1' && find('ミカミ') === 'a1' && find('えすわん') === 'a1' && find('きょにゅう') === 'a1' && find('つぼみ') === 'a2');
} else {
  check('public/search.js の部品が読める', false);
}

const fItem = { cid: 'd1', title: '同人', dateKey: '2026-10-01', maker: { id: 500, name: 'サークルA' }, authors: ['作家B'], genres: ['ファンタジー'], formats: [], sales: [], type: 'comic', image_url: '' };
const fIndex = floorSearchIndex([fItem], 'doujin', {}, (kind, key) => ({ 'maker.500': 'さーくるえー', 'author.作家B': 'さっかびー', 'genre.ファンタジー': 'ふぁんたじー' })[`${kind}.${key}`] ?? '');
check('同人・ゲームの索引の yomi（サークル/ブランドは id、作家・ジャンルは名前で引く）',
  fIndex.yomi['サークルA'] === 'さーくるえー' && fIndex.yomi['作家B'] === 'さっかびー' && fIndex.yomi['ファンタジー'] === 'ふぁんたじー', JSON.stringify(fIndex.yomi));
const fsrc = readFileSync(new URL('../site/public/floor-search.js', import.meta.url), 'utf8');
check('同人・ゲームの作品検索: 読みがなも照らし合わせる・カタカナ/ひらがなをそろえる', /raw\.yomi/.test(fsrc) && /concat\(readings\)/.test(fsrc) && /\[ァ-ヶ\]/.test(fsrc));

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
