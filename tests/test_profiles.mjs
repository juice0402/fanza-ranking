// 出演者プロフィール・売れ筋ランキングの部品（site/src/lib/profiles.js）と、
// 出演者検索の絞り込み（site/public/actress-search.js）のテスト。実行: node tests/test_profiles.mjs
// （ブラウザでの見た目・タップの動きは、PRごとの確認で見る。ここでは、値の整え方・絞り込みの正しさ・個人情報が出ないことを見る）
import fs from 'node:fs';
import vm from 'node:vm';
import * as P from '../site/src/lib/profiles.js';
import { normalizeItems } from '../site/src/lib/items.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

const source = fs.readFileSync(new URL('../site/public/actress-search.js', import.meta.url), 'utf-8');
const sandbox = { module: { exports: {} } };
vm.runInNewContext(source, sandbox); // document が無い環境（node）では、部品だけを出して終わる
const S = sandbox.module.exports;
const plain = (v) => JSON.parse(JSON.stringify(v));

const today = '2026-10-03';

console.log('■ 年齢（生年月日から計算。範囲外・あり得ない日付は出さない）');
check('誕生日の前は1つ若い・当日から上がる', P.ageFromBirthday('1999-10-04', today) === 26 && P.ageFromBirthday('1999-10-03', today) === 27 && P.ageFromBirthday('1999-10-02', today) === 27);
check('年またぎ・月の前後', P.ageFromBirthday('2000-01-01', '2026-12-31') === 26 && P.ageFromBirthday('2000-12-31', '2026-01-01') === 25);
check('うるう日の生まれ（2/29）は、平年の2/28 ではまだ誕生日前・3/1 で上がる', P.ageFromBirthday('2000-02-29', '2026-02-28') === 25 && P.ageFromBirthday('2000-02-29', '2026-03-01') === 26);
check('18歳ちょうどは出す・18歳未満は null', P.ageFromBirthday('2008-10-03', today) === 18 && P.ageFromBirthday('2008-10-04', today) === null && P.ageFromBirthday('2015-01-01', today) === null);
check('80歳まで出す・81歳以上は null', P.ageFromBirthday('1946-10-03', today) === 80 && P.ageFromBirthday('1945-10-03', today) === null);
check('実在しない日付・形が違う値・文字列でない値は null', ['2000-02-30', '2000-13-01', '2000/01/01', '', null, undefined, 19990101, 'abc'].every((v) => P.ageFromBirthday(v, today) === null));

console.log('\n■ プロフィールの整え方');
const rawProfiles = {
  actresses: [
    { id: '1001', name: 'テスト花子', ruby: 'てすとはなこ', image_small: 'https://pics.dmm.co.jp/mono/actjpgs/thumbnail/a.jpg', image_large: 'http://pics.dmm.co.jp/mono/actjpgs/a.jpg', bust: 86, cup: 'F', waist: 57, hip: 87, height: 158, birthday: '1999-03-04', list_url: 'https://al.fanza.co.jp/?lurl=x', fetched: '2026-10-03' },
    { id: '1002', name: '数字なし子', ruby: '', image_small: '', image_large: '', bust: null, cup: '', waist: null, hip: null, height: null, birthday: '', list_url: 'https://al.fanza.co.jp/?lurl=y', fetched: '2026-10-03' },
    { id: '1003', name: '悪い値の人', ruby: 'x', image_small: 'https://evil.example/a.jpg', image_large: 'javascript:alert(1)', bust: 999, cup: 'f', waist: '57', hip: -3, height: 5, birthday: '2015-01-01', list_url: 'https://evil.example/list', fetched: '昨日' },
    { id: 'abc', name: 'idが数字でない', fetched: '2026-10-03' },
    { id: '1005', name: '  ' },
    { id: '1001', name: 'テスト花子', bust: 70 }, // 同じ名前（先のものを使う）
    null, 'x', 5,
  ],
};
const profiles = P.normalizeProfiles(rawProfiles, today);
const by = P.profileByName(profiles);
check('使えない項目（idが数字でない・名前が空・同じ名前・形が違う行）は捨てる', profiles.map((p) => p.name).join() === 'テスト花子,数字なし子,悪い値の人', profiles.map((p) => p.name).join());
const hanako = by.get('テスト花子');
check('正しい値はそのまま・年齢は生年月日から', hanako.bust === 86 && hanako.cup === 'F' && hanako.waist === 57 && hanako.hip === 87 && hanako.height === 158 && hanako.age === 27);
check('画像は http でも https に直る', hanako.imageLarge === 'https://pics.dmm.co.jp/mono/actjpgs/a.jpg' && hanako.imageSmall.startsWith('https://pics.dmm.co.jp/'));
const bad = by.get('悪い値の人');
check('範囲外・数字でない値・小文字のカップは空にする', bad.bust === null && bad.cup === '' && bad.waist === null && bad.hip === null && bad.height === null, JSON.stringify(bad));
check('未成年になる生年月日は年齢にしない・外部の画像/リンク・javascript: は空', bad.age === null && bad.imageSmall === '' && bad.imageLarge === '' && bad.listUrl === '');
check('日付でない取得日は空', bad.fetched === '' && hanako.fetched === '2026-10-03');
check('生年月日は、ここから先に持ち出さない（項目にも、JSONの文字にも無い）', !('birthday' in hanako) && !JSON.stringify(profiles).includes('1999-03-04') && !JSON.stringify(profiles).includes('2015-01-01'));
const namesake = P.normalizeProfiles({ actresses: [
  { id: '2001', name: 'あおい', fetched: '2026-10-03', bust: 80 },
  { id: '2002', name: 'あおい', fetched: '', bust: 90 },
  { id: '2003', name: 'ゆうな', fetched: '2026-10-03' },
  { id: '2003', name: 'ゆうな', fetched: '2026-10-03' }, // 同じ id の重なり（1人）
] }, today);
check('同じ名前の人が別々の id で2人以上いるときは、どちらも使わない（人違いを出さない）。同じ id の重なりは1人', namesake.map((x) => x.name).join() === 'ゆうな', namesake.map((x) => x.id + x.name).join());
check('ファイルが無い・形が違うときは空', [null, undefined, {}, [], 'x', { actresses: 'x' }].every((v) => P.normalizeProfiles(v, today).length === 0));
check('顔写真: 小さい版→大きい版の順に代わりを探す・どちらも無ければ空', P.faceUrl(hanako) === hanako.imageSmall && P.faceUrl(hanako, true) === hanako.imageLarge && P.faceUrl({ imageSmall: '', imageLarge: 'https://pics.dmm.co.jp/l.jpg' }) === 'https://pics.dmm.co.jp/l.jpg' && P.faceUrl(by.get('数字なし子')) === '' && P.faceUrl(undefined) === '');

console.log('\n■ プロフィールの文');
check('項目の表: 載っている項目だけ・順番は 年齢・身長・バスト・ウエスト・ヒップ', JSON.stringify(P.profileFacts(hanako)) === JSON.stringify([['年齢', '27歳'], ['身長', '158cm'], ['バスト', '86cm（Fカップ）'], ['ウエスト', '57cm'], ['ヒップ', '87cm']]), JSON.stringify(P.profileFacts(hanako)));
check('項目の表: 何も載っていなければ空・プロフィールが無くても落ちない', P.profileFacts(by.get('数字なし子')).length === 0 && P.profileFacts(undefined).length === 0);
check('項目の表: カップだけ載っているときは「カップ」', JSON.stringify(P.profileFacts({ age: null, height: null, bust: null, cup: 'G', waist: null, hip: null })) === JSON.stringify([['カップ', 'Gカップ']]));
check('短い体型の文', P.compactSpec(hanako) === '27歳・158cm・B86(F) W57 H87', P.compactSpec(hanako));
check('短い体型の文: 一部だけ・何も無いとき', P.compactSpec({ age: 30 }) === '30歳' && P.compactSpec({ height: 160, waist: 58 }) === '160cm・W58' && P.compactSpec({ cup: 'E' }) === 'Eカップ' && P.compactSpec({}) === '' && P.compactSpec() === '');

console.log('\n■ 出演者検索の索引');
const items = normalizeItems([
  { cid: 'a1', title: 't', date: '2026-10-01', actress: ['テスト花子', '数字なし子'], maker: 'M' },
  { cid: 'a2', title: 't', date: '2026-10-02', actress: ['テスト花子', 'テスト花子'], maker: 'M' },
  { cid: 'a3', title: 't', date: '2026-10-02', actress: ['テスト花子'], maker: 'M' },
]);
check('作品の本数: 1作品に同じ名前が2回あっても1本', P.countWorksByName(items).get('テスト花子') === 3 && P.countWorksByName(items).get('数字なし子') === 1);
const idx = P.buildActressSearchIndex(profiles, items, new Map([['テスト花子', { slug: 'abcdef0123' }]]), today);
check('索引: 日付・取得済みの人だけ（取得日が空の人は入れない）・作品の多い順', idx.generated === today && idx.actresses.map((r) => r.n).join() === 'テスト花子,数字なし子', idx.actresses.map((r) => r.n).join());
check('索引: 項目は決まった短い名前だけ（生年月日・id は入れない）', idx.actresses.every((r) => Object.keys(r).sort().join() === 'a,b,c,h,hi,i,k,l,n,r,s,wa'), Object.keys(idx.actresses[0]).join());
const r0 = idx.actresses[0];
check('索引: 値が正しく入る', r0.s === 'abcdef0123' && r0.k === 3 && r0.a === 27 && r0.h === 158 && r0.b === 86 && r0.c === 'F' && r0.wa === 57 && r0.hi === 87 && r0.l.startsWith('https://al.fanza.co.jp/'));
check('索引: ページが無い人は s が空・載っていない数字は null', idx.actresses[1].s === '' && idx.actresses[1].a === null && idx.actresses[1].h === null && idx.actresses[1].b === null && idx.actresses[1].c === '');
check('索引: JSONに生年月日が出ない', !JSON.stringify(idx).includes('1999') && !/birthday/.test(JSON.stringify(idx)));
// 専用ページがあるのに、プロフィールをまだ取れていない人（検索の部品が出ると、最初からある一覧は隠れるので、索引に入れないと消えてしまう）
const items2 = normalizeItems([
  { cid: 'b1', title: 't', date: '2026-10-01', actress: ['新人さん', 'テスト花子', 'あおい'], maker: 'M' },
  { cid: 'b2', title: 't', date: '2026-10-02', actress: ['新人さん', 'あおい'], maker: 'M' },
]);
const groups2 = new Map([['テスト花子', { slug: 'abcdef0123', items: [1, 2] }], ['新人さん', { slug: '0123456789', items: [1, 2] }], ['あおい', { slug: 'fedcba9876', items: [1, 2] }]]);
const unfetched = (id, name, ruby) => ({ id, name, ruby, imageSmall: '', imageLarge: '', bust: null, cup: '', waist: null, hip: null, height: null, age: null, listUrl: '', fetched: '' });
const idx2 = P.buildActressSearchIndex([...profiles, unfetched('3001', '新人さん', 'しんじん'), unfetched('3002', 'ページの無い未取得の人', 'x')], items2, groups2, today);
const rowOf = (n) => idx2.actresses.find((r) => r.n === n);
check('索引: 専用ページがあれば、プロフィール未取得（fetched が空）・プロフィールが無い（同名で使えない）人も入る', idx2.actresses.length === 4 && rowOf('新人さん') && rowOf('あおい') && rowOf('新人さん').s === '0123456789' && rowOf('あおい').s === 'fedcba9876', idx2.actresses.map((r) => r.n).join());
check('索引: そうした人の数字は null・読みは分かれば入る・顔写真・リンクは空・作品数は正しい', ['a', 'h', 'b', 'wa', 'hi'].every((k) => rowOf('新人さん')[k] === null) && rowOf('新人さん').c === '' && rowOf('新人さん').r === 'しんじん' && rowOf('新人さん').i === '' && rowOf('新人さん').l === '' && rowOf('新人さん').k === 2 && rowOf('あおい').r === '', JSON.stringify(rowOf('新人さん')));
check('索引: 取得済みの人は重複して入らない・ページが無くて未取得の人は入らない', idx2.actresses.filter((r) => r.n === 'テスト花子').length === 1 && !rowOf('ページの無い未取得の人'), idx2.actresses.map((r) => r.n).join());
const cov = P.profileCoverage(profiles);
check('データのある人数: 取得済み2人のうち 顔1・年齢1・身長1・スリーサイズ1', cov.total === 2 && cov.withFace === 1 && cov.withAge === 1 && cov.withHeight === 1 && cov.withSize === 1, JSON.stringify(cov));

console.log('\n■ 売れ筋ランキングの表示');
const rankRaw = {
  date: '2026-10-03',
  items: [
    { rank: 1, cid: 'ipzz00977', title: '一位', url: 'https://al.fanza.co.jp/?lurl=a', image_url: 'https://pics.dmm.co.jp/a.jpg', date: '2026-10-02 00:00:00', maker: 'M', actress: ['花子', '', 5] },
    { rank: 2, cid: 'bad cid!', title: '壊れた品番', url: 'https://al.fanza.co.jp/?lurl=b' },
    { rank: 3, cid: 'evil1', title: '外部リンク', url: 'https://evil.example/' },
    { rank: 4, cid: 'mida00812', title: '二位になる', url: 'https://al.fanza.co.jp/?lurl=c', image_url: 'javascript:alert(1)', actress: [] },
    { rank: 5, cid: 'juvr00281', title: '三位になる', url: 'https://al.fanza.co.jp/?lurl=d' },
    { rank: 6, cid: 'extra1', title: '4本目（出さない）', url: 'https://al.fanza.co.jp/?lurl=e' },
  ],
};
const rk = P.rankingForDisplay(rankRaw, today);
check('使えない行（品番が壊れている・外部リンク）は飛ばし、3本まで・順位は 1,2,3 にそろえる', rk && rk.items.map((x) => `${x.rank}:${x.cid}`).join() === '1:ipzz00977,2:mida00812,3:juvr00281', rk && rk.items.map((x) => `${x.rank}:${x.cid}`).join());
check('日付・出演者（文字列だけ）・外部の画像は空', rk.items[0].date === '2026-10-02' && rk.items[0].actress.join() === '花子' && rk.items[1].image_url === '' && rk.date === '2026-10-03');
check('古いランキング: 7日前までは出し、8日前からは出さない', P.rankingForDisplay({ ...rankRaw, date: '2026-09-26' }, today) !== null && P.rankingForDisplay({ ...rankRaw, date: '2026-09-25' }, today) === null);
check('無い・壊れている・日付が変・使える行が0本のときは null', [null, undefined, {}, [], 'x', { date: '2026-10-03' }, { date: '昨日', items: [] }, { date: '2026-10-03', items: [] }, { date: '2026-10-03', items: [{ cid: 'x', title: 't', url: 'https://evil.example/' }] }].every((v) => P.rankingForDisplay(v, today) === null));

console.log('\n■ 出演者検索の絞り込み（ブラウザ側）');
check('名前の照らし合わせ: カタカナ/ひらがな・全角/半角・空白や中点を区別しない', S.normalizeText('テスト はなこ') === S.normalizeText('てすと・ハナコ') && S.normalizeText('テスト はなこ') === 'てすとはなこ' && S.normalizeText('ＡＢＣ') === 'abc' && S.normalizeText(null) === '');
check('範囲の読み取り', JSON.stringify(plain(S.parseRange('20-24'))) === JSON.stringify({ min: 20, max: 24 }) && JSON.stringify(plain(S.parseRange('-19'))) === JSON.stringify({ min: null, max: 19 }) && JSON.stringify(plain(S.parseRange('40-'))) === JSON.stringify({ min: 40, max: null }));
check('範囲: 空・形が違う値は絞り込まない（null）', ['', '-', '20', 'abc', '20-24-30', null, undefined].every((v) => S.parseRange(v) === null));
check('カップの読み取り: D・K+', JSON.stringify(plain(S.parseCup('D'))) === JSON.stringify({ min: 'D', max: 'D' }) && JSON.stringify(plain(S.parseCup('K+'))) === JSON.stringify({ min: 'K', max: null }) && S.parseCup('') === null && S.parseCup('d') === null && S.parseCup('DD') === null);

const rows = [
  { n: 'テスト花子', r: 'てすとはなこ', s: 'abcdef0123', k: 5, i: '', a: 27, h: 158, b: 86, c: 'F', wa: 57, hi: 87, l: '' },
  { n: '桜ゆの', r: 'さくらゆの', s: '', k: 3, i: '', a: 22, h: 150, b: 80, c: 'C', wa: 56, hi: 82, l: 'https://al.fanza.co.jp/?lurl=1' },
  { n: '数字なし子', r: 'すうじなしこ', s: '', k: 3, i: '', a: null, h: null, b: null, c: '', wa: null, hi: null, l: 'https://al.fanza.co.jp/?lurl=2' },
  { n: '大人の人', r: 'おとなのひと', s: '', k: 1, i: '', a: 45, h: 165, b: 95, c: 'H', wa: 62, hi: 92, l: 'https://al.fanza.co.jp/?lurl=3' },
  { n: 'あいう', r: '', s: '', k: 9, i: '', a: 30, h: 170, b: 100, c: 'K', wa: 66, hi: 98, l: 'https://al.fanza.co.jp/?lurl=4' },
];
const names = (q) => S.filterRows(rows, q).map((r) => r.n).join();
check('条件なし: 全員・作品の多い順（同数は名前順）', names({}) === 'あいう,テスト花子,数字なし子,桜ゆの,大人の人', names({}));
check('名前: ひらがなでもカタカナでも・読みでも一致', names({ text: 'てすと' }) === 'テスト花子' && names({ text: 'テスト' }) === 'テスト花子' && names({ text: 'さくら' }) === '桜ゆの' && names({ text: '桜' }) === '桜ゆの' && names({ text: 'ゆの' }) === '桜ゆの');
check('名前: 一致しなければ0人', names({ text: 'いない人' }) === '');
check('年齢: 20〜24', names({ age: '20-24' }) === '桜ゆの');
check('年齢: 30以上・29まで（載っていない人は、絞り込むと外れる）', names({ age: '30-' }) === 'あいう,大人の人' && names({ age: '-29' }) === 'テスト花子,桜ゆの');
check('身長: 155〜159・165以上', names({ height: '155-159' }) === 'テスト花子' && names({ height: '165-' }) === 'あいう,大人の人');
check('バスト: 85〜89・100以上', names({ bust: '85-89' }) === 'テスト花子' && names({ bust: '100-' }) === 'あいう');
check('ウエスト・ヒップ', names({ waist: '-56' }) === '桜ゆの' && names({ hip: '90-' }) === 'あいう,大人の人');
check('カップ: Fだけ・H以上（載っていない人は外れる）', names({ cup: 'F' }) === 'テスト花子' && names({ cup: 'H+' }) === 'あいう,大人の人');
check('条件を組み合わせる（すべてに合う人だけ）', names({ age: '20-29', cup: 'C', waist: '-57' }) === '桜ゆの' && names({ age: '20-29', cup: 'H+' }) === '');
check('並び順: 名前順は「読み」の順（読みが無い人は名前で）', names({ sort: 'name' }) === 'あいう,おとなのひと'.replace('おとなのひと', '大人の人') + ',桜ゆの,数字なし子,テスト花子', names({ sort: 'name' }));
check('元の配列は並べ替えない・条件が無い値（undefined）でも落ちない', rows[0].n === 'テスト花子' && S.filterRows(rows, undefined).length === 5 && S.filterRows([], {}).length === 0);
check('数字の条件を指定しているかの判定', S.hasNumericFilter({ age: '20-24' }) && S.hasNumericFilter({ cup: 'D' }) && !S.hasNumericFilter({ text: 'x', sort: 'name' }) && !S.hasNumericFilter({ age: '' }) && !S.hasNumericFilter(undefined));

console.log('\n■ 検索結果の文・URLの安全確認（ブラウザ側と、サーバー側の突き合わせ）');
const specCases = [
  { age: 27, height: 158, bust: 86, cup: 'F', waist: 57, hip: 87 }, { age: 30 }, { height: 160, waist: 58 }, { cup: 'E' }, {}, { bust: 80, hip: 85 }, { age: 22, cup: 'C' },
];
check('検索結果の文は、サーバー側の compactSpec と同じ', specCases.every((c) => {
  const row = { a: c.age ?? null, h: c.height ?? null, b: c.bust ?? null, c: c.cup ?? '', wa: c.waist ?? null, hi: c.hip ?? null };
  return S.specText(row) === P.compactSpec(c);
}));
check('画像・リンクは FANZA(DMM) の https だけ', S.safeUrl('https://pics.dmm.co.jp/a.jpg', ['dmm.co.jp']) !== '' && S.safeUrl('https://al.fanza.co.jp/?x=1', ['fanza.co.jp', 'dmm.co.jp']) !== '' && ['http://pics.dmm.co.jp/a.jpg', 'https://evil.example/a.jpg', 'javascript:alert(1)', 'https://dmm.co.jp.evil.example/a', 'https://evildmm.co.jp/a', '', null, 5].every((u) => S.safeUrl(u, ['dmm.co.jp']) === ''));
check('見せかけのURL（ユーザー名の欄にFANZAのホストを入れる・バックスラッシュ・空白）は通さない', ['https://dmm.co.jp:@evil.example/a.jpg', 'https://pics.dmm.co.jp:80@evil.example/a.jpg', 'https://pics.dmm.co.jp@evil.example/a.jpg', 'https://pics.dmm.co.jp\\@evil.example/a.jpg', 'https://pics.dmm.co.jp/a b.jpg', 'https://pics.dmm.co.jp/a\nb.jpg', 'https://pics.dmm.co.jp:x/a.jpg'].every((u) => S.safeUrl(u, ['dmm.co.jp']) === ''));
check('ポート番号つき・?だけ・#だけ・ホストだけのFANZAのURLは通す', ['https://pics.dmm.co.jp:443/a.jpg', 'https://pics.dmm.co.jp?x=1', 'https://pics.dmm.co.jp#top', 'https://pics.dmm.co.jp'].every((u) => S.safeUrl(u, ['dmm.co.jp']) === u));
check('出演者ページの短い名前: 10桁の英数字（小文字）だけ', S.pagePath('abcdef0123') === '/actress/abcdef0123/' && ['', 'ABCDEF0123', 'abcdef012', '../../etc/x', 'abcdef01234', null].every((s) => S.pagePath(s) === ''));
check('1回に出す人数', S.PAGE_SIZE === 60);

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
