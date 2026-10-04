// サンプル動画の枠（site/public/movie.js）の、画面に依存しない部分のテスト。実行: node tests/test_movie.mjs
// （枠の中の見え方は、PRごとのプレビューで見る。ここでは、倍率の計算だけを見る）
import fs from 'node:fs';
import vm from 'node:vm';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

const source = fs.readFileSync(new URL('../site/public/movie.js', import.meta.url), 'utf-8');
const sandbox = { module: { exports: {} } };
vm.runInNewContext(source, sandbox); // document が無い環境（node）では、部品だけを出して終わる
const { scaleFor, sizeFromQuery, SIZES, WIDTH } = sandbox.module.exports;

console.log('■ 枠の幅 → 倍率');
check('FANZAの再生ページの幅は476px', WIDTH === 476);
check('枠が476pxなら等倍', scaleFor(476) === 1);
check('スマホ（343px）では縮小', Math.abs(scaleFor(343) - 343 / 476) < 1e-9 && scaleFor(343) < 1);
check('広い画面（640px）では拡大', Math.abs(scaleFor(640) - 640 / 476) < 1e-9 && scaleFor(640) > 1);
check('幅が分からない（0・負・数字でない・NaN・Infinity）ときは等倍', [0, -5, '300', null, undefined, NaN, Infinity].every((v) => scaleFor(v) === 1));

check('再生ページの幅を渡すと、その幅で割る（720pxの再生ページを、枠360pxに入れるなら 0.5倍）', scaleFor(360, 720) === 0.5 && scaleFor(476, 476) === 1);
check('再生ページの幅が分からない・不正なら、476で割る', scaleFor(238, 0) === 0.5 && scaleFor(238, 'x') === 0.5 && scaleFor(238) === 0.5);

console.log('\n■ ?msize=（画質のためしがけ）');
check('許す大きさは4つだけ（476_306 / 560_360 / 644_414 / 720_480）', Object.keys(SIZES).sort().join() === '476_306,560_360,644_414,720_480');
check('?msize=560_360 などを読める（ほかの条件と一緒でも）', sizeFromQuery('?msize=560_360') === '560_360' && sizeFromQuery('?a=1&msize=720_480&b=2') === '720_480' && sizeFromQuery('?msize=644_414') === '644_414');
check('許していない値・つくりが違う値・無いときは、空（なにもしない）', ['?msize=999_999', '?msize=560', '?msize=560_360x', '?msize=<script>', '?msize=', '?msize=__proto__', '?msize=constructor', '', null, undefined, '?xmsize=560_360'].every((v) => sizeFromQuery(v) === ''), JSON.stringify(['?msize=__proto__'].map(sizeFromQuery)));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
