// つづきから（site/public/recent.js）の、画面に依存しない部分のテスト。実行: node tests/test_recent.mjs
// （トップの棚の見た目は、PRの写真で見る。ここでは記録の読み書き: 女優6人・作品3本・重ねない・こわれた記録は捨てる）
import fs from 'node:fs';
import vm from 'node:vm';
import { smallImage, tinyImage, THUMB_MEDIA } from '../site/src/lib/items.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

const source = fs.readFileSync(new URL('../site/public/recent.js', import.meta.url), 'utf-8');
const sandbox = { module: { exports: {} } };
vm.runInNewContext(source, sandbox); // document が無い環境（node）では、部品だけを出して終わる
const R = sandbox.module.exports;
const plain = (v) => JSON.parse(JSON.stringify(v));

const actress = (n) => ({ n: `女優${n}`, p: `/actress/a${n}/`, f: `https://pics.example/${n}.jpg` });
const work = (n) => ({ c: `abc${n}`, t: `題${n}`, i: `https://pics.dmm.co.jp/digital/video/abc${n}/abc${n}pl.jpg`, p: `/item/abc${n}/` });

console.log('■ 記録の数と並び');
let s = R.emptyRecent();
for (let n = 1; n <= 8; n++) s = R.remember(s, 'actress', actress(n), 1000 + n);
check('女優は最後に見た6人（新しい順）', s.a.length === 6 && s.a[0].n === '女優8' && s.a[5].n === '女優3', plain(s.a).map((a) => a.n).join(','));
for (let n = 1; n <= 5; n++) s = R.remember(s, 'work', work(n), 2000 + n);
check('作品は最後に見た3本（新しい順）', s.w.length === 3 && s.w[0].c === 'abc5' && s.w[2].c === 'abc3', plain(s.w).map((w) => w.c).join(','));
s = R.remember(s, 'actress', actress(5), 9999);
check('同じ人は先頭に移すだけで重ねない', s.a.length === 6 && s.a[0].n === '女優5' && s.a.filter((a) => a.n === '女優5').length === 1 && s.a[0].at === 9999);
s = R.remember(s, 'work', work(3), 9999);
check('同じ作品は先頭に移すだけで重ねない', s.w.length === 3 && s.w[0].c === 'abc3' && s.w.filter((w) => w.c === 'abc3').length === 1);
check('女優と作品は別々に数える', s.a.length === 6 && s.w.length === 3);
check('記録する中身: 女優＝名前・住所・顔の画像・時刻', JSON.stringify(Object.keys(plain(s.a[0]))) === JSON.stringify(['n', 'p', 'f', 'at']));
check('記録する中身: 作品＝作品ID・題・表紙の画像・住所・時刻', JSON.stringify(Object.keys(plain(s.w[0]))) === JSON.stringify(['c', 't', 'i', 'p', 'at']));

console.log('■ 使えない値は記録しない');
const before = JSON.stringify(plain(s));
const bad = [
  ['actress', { n: '', p: '/actress/x/' }], ['actress', { n: '名前', p: '/item/x/' }], ['actress', { n: '名前', p: 'https://evil.example/' }],
  ['work', { c: 'a b', t: '題', p: '/item/ab/' }], ['work', { c: 'ab', t: '', p: '/item/ab/' }], ['work', { c: 'ab', t: '題', p: '/actress/ab/' }],
  ['work', { c: 'ab', t: '題', p: 'javascript:alert(1)' }], ['other', { c: 'ab', t: '題', p: '/item/ab/' }], ['work', null],
];
check('名前・題・作品ID・住所がおかしいもの・知らない種類は記録しない', bad.every(([type, raw]) => JSON.stringify(plain(R.remember(s, type, raw, 1))) === before));
check('/w/ の作品も記録できる', R.remember(R.emptyRecent(), 'work', { ...work(9), p: '/w/abc9/' }, 1).w[0].p === '/w/abc9/');
const odd = R.remember(R.emptyRecent(), 'actress', { ...actress(1), f: 'http://x/1.jpg' }, 1);
check('画像は https のときだけ（それ以外は空。名前の頭文字の丸になる）', odd.a.length === 1 && odd.a[0].f === '');
const long = R.remember(R.emptyRecent(), 'work', { ...work(1), t: 'あ'.repeat(80) + '​' }, 1);
check(`題は短く切る（${R.TITLE_MAX}文字まで・切ったら「…」）`, Array.from(long.w[0].t).length === R.TITLE_MAX && long.w[0].t.endsWith('…'));

console.log('■ こわれた記録は捨てる（落ちない）');
check('記録なし・壊れたJSON・配列・数字・文字・null は空', [null, '', '{oops', '[]', '123', '"x"', 'null'].every((t) => R.hasRecent(R.parseRecent(t)) === false));
const messy = R.parseRecent(JSON.stringify({
  a: [actress(1), { n: 1 }, null, 'x', actress(1), actress(2), { n: '名前', p: '../../' }],
  w: 'oops',
}));
check('こわれた行・重なった行は捨て、よい行だけ残す', messy.a.length === 2 && messy.a[0].n === '女優1' && messy.a[1].n === '女優2' && messy.w.length === 0);
const many = R.parseRecent(JSON.stringify({ a: Array.from({ length: 20 }, (_, n) => actress(n)), w: Array.from({ length: 20 }, (_, n) => work(n)) }));
check('保存が多すぎても6人・3本まで', many.a.length === 6 && many.w.length === 3);
check('こわれた記録の上にも記録できる', R.remember(R.parseRecent('{oops'), 'work', work(1), 1).w.length === 1);

console.log('■ 表紙のサムネ（お気に入りと同じ）');
const urls = ['https://pics.dmm.co.jp/digital/video/a/apl.jpg', 'https://pics.dmm.co.jp/digital/video/a/aps.jpg', 'https://example.net/apl.jpg', ''];
check('サイト側の smallImage・tinyImage・THUMB_MEDIA と同じ', R.THUMB_MEDIA === THUMB_MEDIA && urls.every((u) => R.smallImageUrl(u) === smallImage(u) && R.tinyImageUrl(u) === tinyImage(u)));
check('縮めた版が読めなければ ps に戻す', R.unresizedUrl(tinyImage(urls[0])) === urls[1]);

console.log('■ 画面の作り（送らない・HTML を実行しない）');
check('保存先は localStorage だけ（fetch・XMLHttpRequest・sendBeacon・cookie を使わない）', source.includes("var KEY = 'fanza-recent-v1'") && !/fetch\(|XMLHttpRequest|sendBeacon|document\.cookie/.test(source));
check('文字は textContent で入れる（innerHTML を使わない）', !source.includes('innerHTML'));
check('読み書きは try/catch', /try \{\s*var next = remember/.test(source) && /try \{\s*return parseRecent/.test(source));
check('「記録を消す」で記録を消して棚を閉じる', source.includes("'記録を消す'") && source.includes('storage.removeItem(KEY)') && source.includes("root.classList.remove('has-recent')"));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
