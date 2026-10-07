// お気に入り（site/public/favorites.js）の、画面に依存しない部分のテスト。実行: node tests/test_favorites.mjs
// （ブラウザでの☆ボタン・ページの動きは、PRごとの確認で見る。ここでは、保存データの読み書きと新作の見つけ方を見る）
import fs from 'node:fs';
import vm from 'node:vm';
import { smallImage, tinyImage, THUMB_MEDIA } from '../site/src/lib/items.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

const source = fs.readFileSync(new URL('../site/public/favorites.js', import.meta.url), 'utf-8');
const sandbox = { module: { exports: {} } };
vm.runInNewContext(source, sandbox); // document が無い環境（node）では、部品だけを出して終わる
const F = sandbox.module.exports;
const plain = (v) => JSON.parse(JSON.stringify(v));

console.log('■ 作品の行のサムネ（表紙だけの軽い画像。スマホは、いちばん小さい版）');
const urls = ['https://pics.dmm.co.jp/digital/video/a/apl.jpg', 'https://pics.dmm.co.jp/digital/video/a/aps.jpg', 'https://example.net/apl.jpg', ''];
check('サイト側の smallImage・tinyImage・THUMB_MEDIA と同じ', F.THUMB_MEDIA === THUMB_MEDIA && urls.every((u) => F.smallImageUrl(u) === smallImage(u) && F.tinyImageUrl(u) === tinyImage(u)));
check('読めなければ pt → ps → pl の順に戻し、それも読めなければ隠す・印 is-small（まん中で切る）', source.includes("img.src = img.src.replace(/pt\\.jpg$/, 'ps.jpg');") && source.includes("img.src = img.src.replace(/ps\\.jpg$/, 'pl.jpg');") && source.includes("img.classList.add('is-small')") && source.includes('window.matchMedia(THUMB_MEDIA).matches ? tinyImageUrl(small) : small'));
 // vm の中で作られたオブジェクトを、普通のオブジェクトにする

const work = { t: 'タイトル', i: 'https://pics.example/x.jpg', d: '2026-10-17', a: ['花子'], m: 'メーカーA' };

console.log('■ 読み込み（壊れた保存データでも落ちない）');
check('空の保存データ', JSON.stringify(plain(F.parseStore(null))) === JSON.stringify({ v: 1, work: {}, actress: {}, maker: {} }));
check('壊れたJSON・配列・数字・null は空になる', ['{oops', '[]', '123', 'null', '"x"', ''].every((t) => F.hasPeople(F.parseStore(t)) === false && Object.keys(F.parseStore(t).work).length === 0));
const messy = F.parseStore(JSON.stringify({
  work: { ok1: { t: 'A', d: '2026-10-01', i: 'https://x/y.jpg', a: ['花子', 5, ''], m: 'M', at: 5 }, 'bad key!': { t: 'B' }, notitle: { t: '' }, evil: { t: 'C', i: 'javascript:alert(1)', d: '昨日' } },
  actress: { 花子: { slug: 'abcdef0123', at: 1 }, 'ng': { slug: '<script>' }, '': { slug: 'abcdef0123' } },
  maker: [1, 2],
}));
check('作品: 正しいものは残り、キーに使えない文字・タイトル無しは捨てる', Object.keys(messy.work).sort().join() === 'evil,ok1', Object.keys(messy.work).join());
check('作品: 出演者は文字列だけ・画像は https だけ・日付は YYYY-MM-DD だけ', plain(messy.work.ok1.a).join() === '花子' && messy.work.evil.i === '' && messy.work.evil.d === '');
check('出演者: slug は10桁の英数字だけ（それ以外は空にする）・名前が空のものは捨てる', messy.actress['花子'].slug === 'abcdef0123' && messy.actress['ng'].slug === '' && !('' in messy.actress));
check('メーカーが配列などで壊れていても空として読める', Object.keys(messy.maker).length === 0);
const huge = { work: Object.fromEntries(Array.from({ length: F.LIMIT + 50 }, (_, i) => [`c${i}`, { t: 't' }])) };
check(`多すぎる保存データは ${F.LIMIT}件までに切る`, Object.keys(F.parseStore(JSON.stringify(huge)).work).length === F.LIMIT);

console.log('\n■ ☆の付け外し');
let store = F.emptyStore();
let r = F.toggle(store, 'work', 'abc123', work, 1000);
check('付ける: on になり、作品の情報が保存される', r.on === true && F.isOn(r.store, 'work', 'abc123') && r.store.work.abc123.t === 'タイトル' && r.store.work.abc123.at === 1000);
check('付けても、元の store は変わらない', !F.isOn(store, 'work', 'abc123'));
store = r.store;
r = F.toggle(store, 'work', 'abc123', work, 2000);
check('もう一度押すと外れる', r.on === false && !F.isOn(r.store, 'work', 'abc123'));
r = F.toggle(F.emptyStore(), 'actress', '花子', { slug: 'abcdef0123' }, 5);
check('出演者を付ける（slug つき）', r.on && r.store.actress['花子'].slug === 'abcdef0123');
r = F.toggle(F.emptyStore(), 'maker', 'メーカーA', { slug: '' }, 5);
check('専用ページが無い（slug なし）出演者・メーカーも付けられる', r.on && r.store.maker['メーカーA'].slug === '');
check('種類が違えば、同じ名前でも別々', (() => { let s = F.toggle(F.emptyStore(), 'actress', 'X', {}, 1).store; s = F.toggle(s, 'maker', 'X', {}, 2).store; return F.isOn(s, 'actress', 'X') && F.isOn(s, 'maker', 'X'); })());
check('知らない種類・使えないキーは追加されない', F.toggle(F.emptyStore(), 'bogus', 'a', {}, 1).on === false && F.toggle(F.emptyStore(), 'work', 'bad key', work, 1).on === false && F.toggle(F.emptyStore(), 'work', 'ok', { t: '' }, 1).on === false);
check('Object のもともとの名前（constructor など）をお気に入りと勘違いしない', F.isOn(F.emptyStore(), 'actress', 'constructor') === false && F.isOn(F.emptyStore(), 'actress', 'toString') === false);
check('外す（remove）', (() => { const s = F.toggle(F.emptyStore(), 'actress', '花子', {}, 1).store; return !F.isOn(F.remove(s, 'actress', '花子'), 'actress', '花子'); })());
let full = F.emptyStore();
for (let i = 0; i < F.LIMIT; i++) full = F.toggle(full, 'actress', `n${i}`, {}, i).store;
const over = F.toggle(full, 'actress', 'one-more', {}, 999);
check(`上限（${F.LIMIT}件）に達したら追加せず、full で知らせる・すでにあるものは外せる`, over.full === true && over.on === false && !F.isOn(over.store, 'actress', 'one-more') && F.toggle(full, 'actress', 'n0', {}, 1).on === false && !F.isOn(F.toggle(full, 'actress', 'n0', {}, 1).store, 'actress', 'n0'));
check('保存 → 読み込みで元に戻る（往復）', (() => { const s = F.toggle(F.toggle(F.emptyStore(), 'work', 'abc123', work, 7).store, 'actress', '花子', { slug: 'abcdef0123' }, 8).store; return JSON.stringify(plain(F.parseStore(JSON.stringify(s)))) === JSON.stringify(plain(s)); })());

console.log('\n■ お気に入りの新作の見つけ方');
const today = '2026-10-03';
const index = [
  { c: 'u1', t: '予約1', d: '2026-10-20', a: ['花子'], m: 'MA', i: '' },
  { c: 'u2', t: '予約2', d: '2026-10-10', a: ['別の人'], m: 'MB', i: '' },
  { c: 'u3', t: '予約3', d: '2026-10-10', a: [], m: 'MA', i: '' },
  { c: 'r1', t: '最近1', d: '2026-10-03', a: ['花子', '葵'], m: '', i: '' },
  { c: 'r2', t: '最近2', d: '2026-09-04', a: ['葵'], m: 'MC', i: '' },
  { c: 'r3', t: '最近3', d: '2026-09-03', a: ['葵'], m: 'MC', i: '' },
  { c: 'x1', t: '無関係', d: '2026-10-05', a: ['他'], m: 'MZ', i: '' },
  { c: 'bad id', t: '壊れた品番', d: '2026-10-05', a: ['花子'], m: '', i: '' },
  { c: 'bad2', t: '壊れた日付', d: '昨日', a: ['花子'], m: '', i: '' },
];
let fav = F.toggle(F.toggle(F.emptyStore(), 'actress', '花子', {}, 1).store, 'maker', 'MA', {}, 2).store;
let found = F.pickNew(fav, index, today, 30);
check('出演者（花子）・メーカー（MA）の作品が見つかる: 予約は発売日の近い順', plain(found.upcoming).map((x) => x.c).join() === 'u3,u1', plain(found.upcoming).map((x) => x.c).join());
check('発売済みは新しい順（当日発売は「発売済み」）', plain(found.recent).map((x) => x.c).join() === 'r1', plain(found.recent).map((x) => x.c).join());
check('関係ない作品・品番や日付が壊れた作品は出ない', !plain(found.upcoming).concat(plain(found.recent)).some((x) => ['x1', 'bad id', 'bad2', 'u2'].includes(x.c)));
fav = F.toggle(fav, 'actress', '葵', {}, 3).store;
found = F.pickNew(fav, index, today, 30);
check('30日前(9/3)までは「最近」に入る（9/3 は入る）', plain(found.recent).map((x) => x.c).join() === 'r1,r2,r3', plain(found.recent).map((x) => x.c).join());
check('日数を短くすると、古いものは外れる（7日）', plain(F.pickNew(fav, index, today, 7).recent).map((x) => x.c).join() === 'r1');
check('お気に入りが無ければ、何も出ない', F.pickNew(F.emptyStore(), index, today, 30).upcoming.length === 0 && F.pickNew(F.emptyStore(), index, today, 30).recent.length === 0);
check('索引が壊れていても落ちない', F.pickNew(fav, null, today, 30).upcoming.length === 0 && F.pickNew(fav, [null, 1, {}], today, 30).recent.length === 0);
check('出演者・メーカーのお気に入りがあるか（作品だけなら false）', F.hasPeople(fav) === true && F.hasPeople(F.toggle(F.emptyStore(), 'work', 'abc', work, 1).store) === false);

console.log('\n■ 専用ページができたとき、☆を付けた人のリンクを補う');
const withNew = plain(F.toggle(F.toggle(F.toggle(F.emptyStore(), 'actress', '新人', { slug: '' }, 1).store, 'actress', '前から', { slug: 'ffffffffff' }, 2).store, 'maker', '小さなメーカー', { slug: '' }, 3).store);
const pagesNow = { actress: { 新人: '0123456789', 前から: 'aaaaaaaaaa' }, maker: { 小さなメーカー: 'abcdef0123' } };
const resolved = F.resolveSlugs(withNew, pagesNow);
check('ページができた出演者・メーカーに、リンク用の短い名前が入る（もともと持っている人は変えない）', resolved.changed && resolved.store.actress['新人'].slug === '0123456789' && resolved.store.actress['前から'].slug === 'ffffffffff' && resolved.store.maker['小さなメーカー'].slug === 'abcdef0123', JSON.stringify(plain(resolved.store)));
check('元の保存データは書き換えない', withNew.actress['新人'].slug === '' && withNew.maker['小さなメーカー'].slug === '');
check('まだページが無い人は、空のまま・変わらなければ changed は false', !F.resolveSlugs(withNew, { actress: {}, maker: {} }).changed && !F.resolveSlugs(resolved.store, pagesNow).changed);
check('形が違う短い名前・索引が壊れているときは、補わない', !F.resolveSlugs(withNew, { actress: { 新人: 'xyz' }, maker: { 小さなメーカー: '<script>' } }).changed && [null, undefined, {}, [], 'x', { actress: null }, { actress: [] }].every((v) => !F.resolveSlugs(withNew, v).changed));
const protoStore = plain(F.toggle(F.emptyStore(), 'actress', 'constructor', { slug: '' }, 1).store);
check('名前が constructor のような特別な名前でも、取り違えない', !F.resolveSlugs(protoStore, { actress: {}, maker: {} }).changed);

console.log('\n■ 発売日カレンダーのリンク（新作・予約が載っている人だけにある）');
check('索引の pages に同じ短い名前で入っている人だけ、カレンダーがある', F.hasCalendar(pagesNow, 'actress', '新人', '0123456789') && F.hasCalendar(pagesNow, 'maker', '小さなメーカー', 'abcdef0123'));
check('過去作品だけの人（pages に無い）・短い名前が違う・空の短い名前は、カレンダーなし', !F.hasCalendar(pagesNow, 'actress', '昔の人', 'bbbbbbbbbb') && !F.hasCalendar(pagesNow, 'actress', '前から', 'ffffffffff') && !F.hasCalendar(pagesNow, 'actress', '新人', ''));
check('索引が壊れていても落ちない・constructor のような名前を取り違えない', [null, undefined, {}, [], 'x', { actress: null }].every((v) => !F.hasCalendar(v, 'actress', '新人', '0123456789')) && !F.hasCalendar({ actress: {}, maker: {} }, 'actress', 'constructor', 'function'));

console.log('\n■ 日付');
check('日本時間の今日（UTC 15:00 → 翌日）', F.jstToday(Date.UTC(2026, 9, 3, 15, 0)) === '2026-10-04' && F.jstToday(Date.UTC(2026, 9, 3, 14, 59)) === '2026-10-03');
check('日数の足し引き（月またぎ・うるう年）', F.addDays('2026-10-01', -1) === '2026-09-30' && F.addDays('2028-02-28', 1) === '2028-02-29');
check('日本語の日付', F.jpDate('2026-10-07') === '2026年10月7日' && F.jpDate('2026-12-31') === '2026年12月31日' && F.jpDate('昨日') === '' && F.jpDate(undefined) === '');

console.log('\n■ お気に入りの一覧の出演者は3名まで');
check('3名まで出して、残りは人数だけ（作品検索・一覧のカードと同じ3名）', F.CAST_LIMIT === 3 && JSON.stringify(plain(F.castShown(['a', 'b', 'c', 'd', 'e'], F.CAST_LIMIT))) === JSON.stringify({ names: ['a', 'b', 'c'], more: 2 }) && plain(F.castShown([], 3)).more === 0);

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
