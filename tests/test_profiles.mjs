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
const sandbox = { module: { exports: {} }, URLSearchParams };
vm.runInNewContext(source, sandbox); // document が無い環境（node）では、部品だけを出して終わる
const S = sandbox.module.exports;
const plain = (v) => JSON.parse(JSON.stringify(v));

const today = '2026-10-03';

console.log('■ 年齢（生年月日から計算。範囲外・あり得ない日付は出さない）');
check('誕生日の前は1つ若い・当日から上がる', P.ageFromBirthday('1999-10-04', today) === 26 && P.ageFromBirthday('1999-10-03', today) === 27 && P.ageFromBirthday('1999-10-02', today) === 27);
check('年またぎ・月の前後', P.ageFromBirthday('2000-01-01', '2026-12-31') === 26 && P.ageFromBirthday('2000-12-31', '2026-01-01') === 25);
check('うるう日の生まれ（2/29）は、平年の2/28 ではまだ誕生日前・3/1 で上がる', P.ageFromBirthday('2000-02-29', '2026-02-28') === 25 && P.ageFromBirthday('2000-02-29', '2026-03-01') === 26);
check('誕生日の月日（「誕生日の近い女優」用。年は持ち出さない）: 年齢が出せるときだけ "MM-DD"', P.birthMonthDay('1999-10-07', today) === '10-07' && P.birthMonthDay('2015-10-07', today) === '' && P.birthMonthDay('x', today) === '');
check('プロフィール・名簿を読むとき、誕生日の月日も入る（生年月日そのものは入らない）', P.normalizeProfiles({ actresses: [{ id: '1', name: '花子', birthday: '1999-10-07' }] }, today)[0].birthMD === '10-07' && !('birthday' in P.normalizeProfiles({ actresses: [{ id: '1', name: '花子', birthday: '1999-10-07' }] }, today)[0]) && P.normalizeDirectory({ rows: [{ id: '2', name: '月子', birthday: '2000-01-02' }] }, today)[0].birthMD === '01-02');
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
const ALLOWED = new Set(['n', 'r', 'id', 's', 'k', 'i', 'a', 'h', 'b', 'c', 'wa', 'hi', 'l']);
check('索引: 日付・顔写真の置き場所・取得済みの人だけ（取得日が空の人は入れない）・作品の多い順', idx.generated === today && idx.img === P.ACTRESS_IMAGE_BASE && idx.actresses.map((r) => r.n).join() === 'テスト花子,数字なし子', idx.actresses.map((r) => r.n).join());
check('索引: 項目は決まった短い名前だけ（生年月日は入れない）・値が無い項目は入れない', idx.actresses.every((r) => Object.keys(r).every((k) => ALLOWED.has(k))) && !('a' in idx.actresses[1]) && !('s' in idx.actresses[1]), JSON.stringify(idx.actresses));
const r0 = idx.actresses[0];
check('索引: 値が正しく入る', r0.s === 'abcdef0123' && r0.k === 3 && r0.a === 27 && r0.h === 158 && r0.b === 86 && r0.c === 'F' && r0.wa === 57 && r0.hi === 87 && r0.id === hanako.id, JSON.stringify(r0));
check('索引: JSONに生年月日が出ない', !JSON.stringify(idx).includes('1999') && !/birthday/.test(JSON.stringify(idx)));
check('顔写真のファイル名: FANZAの決まった形のURLから取り出す・それ以外は空', P.imageKeyOf('https://pics.dmm.co.jp/mono/actjpgs/thumbnail/hasumi_kurea.jpg') === 'hasumi_kurea' && P.imageKeyOf('https://pics.dmm.co.jp/mono/actjpgs/hasumi_kurea.jpg') === 'hasumi_kurea' && ['https://evil.example/mono/actjpgs/x.jpg', 'https://pics.dmm.co.jp/other/x.jpg', '', null].every((u) => P.imageKeyOf(u) === ''));
check('全作品のURLの形: id の所を {ID} にした形を作る。作れなければ空', P.listTemplateOf([{ id: '123', listUrl: 'https://al.fanza.co.jp/?lurl=x%3D123%2F&af_id=a' }]) === 'https://al.fanza.co.jp/?lurl=x%3D{ID}%2F&af_id=a' && P.listTemplateOf([{ id: '1', listUrl: 'https://al.fanza.co.jp/?a=1&b=1' }]) === '' && P.listTemplateOf([]) === '');
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
check('索引: そうした人は、数字・顔写真・リンクが無い・読みは分かれば入る・作品数は正しい', JSON.stringify(rowOf('新人さん')) === JSON.stringify({ n: '新人さん', s: '0123456789', k: 2, r: 'しんじん' }), JSON.stringify(rowOf('新人さん')));
check('索引: 取得済みの人は重複して入らない・ページが無くて未取得の人は入らない', idx2.actresses.filter((r) => r.n === 'テスト花子').length === 1 && !rowOf('ページの無い未取得の人'), idx2.actresses.map((r) => r.n).join());

console.log('\n■ 女優検索の名簿（FANZA公式の出演者検索の一覧。actress_directory.json）');
const dirRaw = { cursor: { filter: 0, offset: 1 }, rows: [
  { id: '9001', name: '名簿花子', ruby: 'めいぼはなこ', img: 'meibo_hanako', bust: 90, cup: 'G', waist: 58, hip: 88, height: 160, birthday: '2000-01-01' },
  { id: '9002', name: '名簿月子', ruby: '', img: '../x', bust: 300, cup: 'gg', waist: null, hip: null, height: 150, birthday: '2015-01-01' },
  { id: '9001', name: '重なり', ruby: '', img: '', bust: 80 },
  { id: 'abc', name: '壊れた id', bust: 80 },
  { id: hanako.id, name: 'テスト花子', ruby: 'てすとはなこ', img: 'test_hanako', bust: 99, cup: 'K', waist: 60, hip: 90, height: 170, birthday: '1990-01-01' },
  { id: '9100', name: 'テスト花子', ruby: '', img: '', bust: 70, height: 150 },
] };
const dir = P.normalizeDirectory(dirRaw, today);
check('名簿: 壊れた id・重なった id は捨てる・あり得ない値・変な画像のファイル名は空・生年月日は年齢にだけ（18歳未満は出さない）',
  dir.length === 4 && dir[0].age === 26 && !('birthday' in dir[0]) && dir[1].bust === null && dir[1].cup === '' && dir[1].img === '' && dir[1].age === null && dir[0].img === 'meibo_hanako', JSON.stringify(dir));
check('名簿: ファイルが無い・形が違うときは空', [null, undefined, {}, [], 'x', { rows: 'x' }].every((v) => P.normalizeDirectory(v, today).length === 0));
const idx3 = P.buildActressSearchIndex(profiles, items, new Map([['テスト花子', { slug: 'abcdef0123' }]]), today, dir);
const byIdx3 = (id) => idx3.actresses.find((r) => r.id === id);
check('名簿の人も索引に入る（このサイトの作品が無くても、体型などで探せる）', byIdx3('9001') && byIdx3('9001').n === '名簿花子' && byIdx3('9001').b === 90 && byIdx3('9001').i === 'meibo_hanako' && !('s' in byIdx3('9001')) && !('k' in byIdx3('9001')), JSON.stringify(byIdx3('9001')));
check('名簿とプロフィールの両方にいる人は1行。値は、プロフィール（このサイトの作品の出演者）のほうで上書き・専用ページと作品数が付く', idx3.actresses.filter((r) => r.id === hanako.id).length === 1 && byIdx3(hanako.id).b === 86 && byIdx3(hanako.id).s === 'abcdef0123' && byIdx3(hanako.id).k === 3, JSON.stringify(byIdx3(hanako.id)));
check('同じ名前の別人（id が違う）は別の行。専用ページ・作品数は、作品の出演者と同じ人（プロフィールの id）の行にだけ付く', byIdx3('9100') && !('s' in byIdx3('9100')) && !('k' in byIdx3('9100')), JSON.stringify(byIdx3('9100')));
const cov3 = P.indexCoverage(idx3);
check('探せる人数・年齢などが分かる人数を数える', cov3.total === idx3.actresses.length && cov3.withAge >= 1 && cov3.withCup >= 2, JSON.stringify(cov3));
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
check('使えない行（品番が壊れている・外部リンク）は飛ばし、順位は 1,2,3… にそろえる（VR作品を隠したときの差し替え用に、3本より多く持つ）', rk && rk.items.map((x) => `${x.rank}:${x.cid}`).join() === '1:ipzz00977,2:mida00812,3:juvr00281,4:extra1', rk && rk.items.map((x) => `${x.rank}:${x.cid}`).join());
const manyRows = Array.from({ length: 9 }, (_, i) => ({ cid: `m${i + 1}`, title: `作品${i + 1}`, url: 'https://al.fanza.co.jp/?x=' + i }));
check(`持つのは最大 ${P.RANKING_MAX} 本まで`, P.RANKING_MAX === 6 && P.rankingForDisplay({ date: '2026-10-03', items: manyRows }, today).items.length === 6);
check('日付・出演者（文字列だけ）・外部の画像は空', rk.items[0].date === '2026-10-02' && rk.items[0].actress.join() === '花子' && rk.items[1].image_url === '' && rk.date === '2026-10-03');
const vrRank = P.rankingForDisplay({ date: '2026-10-03', items: [
  { cid: 'a1', title: '【VR】ふつうのVR', url: 'https://al.fanza.co.jp/?x=1' },
  { cid: 'a2', title: 'ふつうの作品', url: 'https://al.fanza.co.jp/?x=2' },
  { cid: 'a3', title: 'タイトルにVRが無い作品', url: 'https://al.fanza.co.jp/?x=3' },
] }, today, new Set(['a3']));
check('売れ筋: VR作品に vr=true（題名の【VR】、または、当サイトの作品のジャンルから分かった品番）。それ以外は false。品番の集まりを渡さなくても動く', vrRank.items.map((i) => i.vr).join() === 'true,false,true' && P.rankingForDisplay({ date: '2026-10-03', items: [{ cid: 'a1', title: '【VR】x', url: 'https://al.fanza.co.jp/?x=1' }] }, today).items[0].vr === true);
check('売れ筋: データの vr が true なら、題名やジャンルが分からなくても VR（取得のときに、ジャンルなどから判定して保存したもの）。true 以外（文字列 "true" など）は信じない', (() => {
  const r = P.rankingForDisplay({ date: '2026-10-03', items: [
    { cid: 'b1', title: '題名に印が無いVR', url: 'https://al.fanza.co.jp/?x=1', vr: true },
    { cid: 'b2', title: 'ふつう', url: 'https://al.fanza.co.jp/?x=2', vr: false },
    { cid: 'b3', title: 'ふつう2', url: 'https://al.fanza.co.jp/?x=3', vr: 'true' },
  ] }, today);
  return r.items.map((i) => i.vr).join() === 'true,false,false';
})());
check('古いランキング: 7日前までは出し、8日前からは出さない', P.rankingForDisplay({ ...rankRaw, date: '2026-09-26' }, today) !== null && P.rankingForDisplay({ ...rankRaw, date: '2026-09-25' }, today) === null);
check('無い・壊れている・日付が変・使える行が0本のときは null', [null, undefined, {}, [], 'x', { date: '2026-10-03' }, { date: '昨日', items: [] }, { date: '2026-10-03', items: [] }, { date: '2026-10-03', items: [{ cid: 'x', title: 't', url: 'https://evil.example/' }] }].every((v) => P.rankingForDisplay(v, today) === null));

console.log('\n■ 女優検索の絞り込み（ブラウザ側）');
check('名前の照らし合わせ: カタカナ/ひらがな・全角/半角・空白や中点を区別しない', S.normalizeText('テスト はなこ') === S.normalizeText('てすと・ハナコ') && S.normalizeText('テスト はなこ') === 'てすとはなこ' && S.normalizeText('ＡＢＣ') === 'abc' && S.normalizeText(null) === '');
check('範囲の読み取り（下限〜上限・どちらかだけ・逆なら入れ替え）', JSON.stringify(plain(S.parseRange('20-24'))) === JSON.stringify({ min: 20, max: 24 }) && JSON.stringify(plain(S.parseRange('-19'))) === JSON.stringify({ min: null, max: 19 }) && JSON.stringify(plain(S.parseRange('40-'))) === JSON.stringify({ min: 40, max: null }) && JSON.stringify(plain(S.parseRange('90-80'))) === JSON.stringify({ min: 80, max: 90 }));
check('範囲: 空・形が違う・範囲外の値は絞り込まない（null）', ['', '-', '20', 'abc', '20-24-30', null, undefined].every((v) => S.parseRange(v) === null) && S.parseRange('5-9', 18, 80) === null);
check('カップの読み取り: いくつでも・L以上・知らない値は捨てる', S.parseCups('E,F,L+').join() === 'E,F,L+' && S.parseCups('e, f').join() === 'E,F' && S.parseCups('Z,DD,').join() === '' && S.parseCups(null).length === 0);

const rows = [
  { n: 'テスト花子', r: 'てすとはなこ', id: '1001', s: 'abcdef0123', k: 5, i: 'test_hanako', a: 27, h: 158, b: 86, c: 'F', wa: 57, hi: 87 },
  { n: '桜ゆの', r: 'さくらゆの', id: '1002', k: 3, a: 22, h: 150, b: 80, c: 'C', wa: 56, hi: 82 },
  { n: '数字なし子', r: 'すうじなしこ', id: '1003', k: 3 },
  { n: '大人の人', r: 'おとなのひと', id: '1004', k: 1, a: 45, h: 165, b: 95, c: 'H', wa: 62, hi: 92 },
  { n: 'あいう', id: '1005', k: 9, a: 30, h: 170, b: 100, c: 'K', wa: 66, hi: 98, i: 'aiu' },
  { n: '名簿だけの人', r: 'めいぼだけのひと', id: '2001', a: 24, h: 162, b: 92, c: 'M', wa: 58, hi: 90 },
];
const names = (q) => S.filterRows(rows, q).map((r) => r.n).join();
check('条件なし: 全員・このサイトの作品の多い順（同じ本数は読みの順・作品が無い人は後ろ）', names({}) === 'あいう,テスト花子,桜ゆの,数字なし子,大人の人,名簿だけの人', names({}));
check('名前: ひらがなでもカタカナでも・読みでも一致', names({ q: 'てすと' }) === 'テスト花子' && names({ q: 'テスト' }) === 'テスト花子' && names({ q: 'さくら' }) === '桜ゆの' && names({ q: '桜' }) === '桜ゆの' && names({ q: 'ゆの' }) === '桜ゆの');
check('年齢: 20〜24（載っていない人は、絞り込むと外れる）', names({ age: '20-24' }) === '桜ゆの,名簿だけの人');
check('年齢: 30以上・29まで', names({ age: '30-' }) === 'あいう,大人の人' && names({ age: '-29' }) === 'テスト花子,桜ゆの,名簿だけの人');
check('身長・バスト・ウエスト・ヒップを、1cm単位で', names({ height: '158-162' }) === 'テスト花子,名簿だけの人' && names({ bust: '92-95' }) === '大人の人,名簿だけの人' && names({ waist: '-57' }) === 'テスト花子,桜ゆの' && names({ hip: '90-92' }) === '大人の人,名簿だけの人');
check('カップ: いくつでも（どれかに合う人）・L以上', names({ cup: 'F,H' }) === 'テスト花子,大人の人' && names({ cup: 'L+' }) === '名簿だけの人' && names({ cup: 'K,L+' }) === 'あいう,名簿だけの人');
check('このサイトに作品がある人だけ・顔写真がある人だけ', names({ site: '1', age: '20-29' }) === 'テスト花子,桜ゆの' && names({ face: '1' }) === 'あいう,テスト花子');
check('条件を組み合わせる（すべてに合う人だけ）', names({ age: '20-29', cup: 'C', waist: '-57' }) === '桜ゆの' && names({ age: '20-29', cup: 'H' }) === '');
check('並び順: バストの大きい順（載っていない人は後ろ）', names({ sort: 'bust' }) === 'あいう,大人の人,名簿だけの人,テスト花子,桜ゆの,数字なし子', names({ sort: 'bust' }));
check('並び順: カップ・若い順・身長・ウエストの細い順・新しく登録された順', names({ sort: 'cup' }).startsWith('名簿だけの人,あいう,大人の人') && names({ sort: 'young' }).startsWith('桜ゆの,名簿だけの人,テスト花子') && names({ sort: 'tall' }).startsWith('あいう,大人の人,名簿だけの人') && names({ sort: 'waist' }).startsWith('桜ゆの,テスト花子') && names({ sort: 'newest' }).startsWith('名簿だけの人,あいう'), [names({ sort: 'cup' }), names({ sort: 'young' })].join(' / '));
check('並び順: 名前順は「読み」の順（読みが無い人は名前で）・知らない並び順は作品の多い順', names({ sort: 'name' }).startsWith('あいう,大人の人,桜ゆの') && names({ sort: 'xxx' }) === names({}), names({ sort: 'name' }));
check('元の配列は並べ替えない・条件が無い値（undefined）でも落ちない', rows[0].n === 'テスト花子' && S.filterRows(rows, undefined).length === 6 && S.filterRows([], {}).length === 0);
check('数字・カップの条件を指定しているかの判定', S.hasNumericFilter({ age: '20-24' }) && S.hasNumericFilter({ cup: 'D' }) && !S.hasNumericFilter({ q: 'x', sort: 'name' }) && !S.hasNumericFilter({ age: '' }) && !S.hasNumericFilter(undefined));
const pq = plain(S.parseQuery('?q=%E3%81%95%E3%81%8F%E3%82%89&age=20-25&bust=90-&cup=E,F,Z&site=1&sort=bust&evil=1'));
check('URL の読み取り: 知らない項目・知らないカップは捨てる', pq.q === 'さくら' && pq.age === '20-25' && pq.bust === '90-' && pq.cup === 'E,F' && pq.site === '1' && pq.face === '' && pq.sort === 'bust' && !('evil' in pq), JSON.stringify(pq));
check('URL の書き出し: 空の条件は書かない・読み取ると同じ条件に戻る', S.buildQuery(pq) === '?q=%E3%81%95%E3%81%8F%E3%82%89&age=20-25&bust=90-&cup=E%2CF&site=1&sort=bust' && JSON.stringify(plain(S.parseQuery(S.buildQuery(pq)))) === JSON.stringify(pq) && S.buildQuery(plain(S.parseQuery(''))) === '', S.buildQuery(pq));
check('URL の読み取り: 変な並び順・範囲外の値は、指定なしに', plain(S.parseQuery('?sort=evil&age=5-9')).sort === 'works' && plain(S.parseQuery('?sort=evil&age=5-9')).age === '');
check('顔写真のURL: ファイル名なら置き場所とつなぐ・FANZAの https のURLはそのまま・それ以外は空', S.imageUrl('test_hanako', 'https://pics.dmm.co.jp/mono/actjpgs/thumbnail/') === 'https://pics.dmm.co.jp/mono/actjpgs/thumbnail/test_hanako.jpg' && S.imageUrl('https://pics.dmm.co.jp/a.jpg', '') === 'https://pics.dmm.co.jp/a.jpg' && ['../x', 'https://evil.example/a.jpg', '', null].every((i) => S.imageUrl(i, 'https://pics.dmm.co.jp/x/') === '') && S.imageUrl('abc', 'https://evil.example/') === '');
check('全作品のURL: 行の l か、形の {ID} に id を入れる（FANZAの https だけ）', S.listUrl({ id: '1017139' }, 'https://al.fanza.co.jp/?lurl=x%3D{ID}%2F&af_id=a') === 'https://al.fanza.co.jp/?lurl=x%3D1017139%2F&af_id=a' && S.listUrl({ id: '1', l: 'https://al.fanza.co.jp/?x=1' }, '') === 'https://al.fanza.co.jp/?x=1' && S.listUrl({ id: 'x' }, 'https://al.fanza.co.jp/{ID}') === '' && S.listUrl({ id: '1' }, 'https://evil.example/{ID}') === '' && S.listUrl({ id: '1' }, '') === '');

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
check('1回に出す人数・カップの選択肢・並び順・数字の条件', S.PAGE_SIZE === 60 && S.CUPS.join('') === 'ABCDEFGHIJK' && S.SORTS.length === 11 && S.RANGES.join() === 'age,height,bust,waist,hip');
const searchSource = fs.readFileSync(new URL('../site/public/actress-search.js', import.meta.url), 'utf-8');
check('検索結果の「FANZAで全作品を見る」に、（広告）の文字を付けない（広告であることは、全ページのヘッダー・フッターに出している）', searchSource.includes("'FANZAで全作品を見る ›'") && !searchSource.includes('（広告）'));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
