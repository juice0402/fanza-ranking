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
const { scaleFor, WIDTH } = sandbox.module.exports;

console.log('■ 枠の幅 → 倍率');
check('FANZAの再生ページの幅は476px', WIDTH === 476);
check('枠が476pxなら等倍', scaleFor(476) === 1);
check('スマホ（343px）では縮小', Math.abs(scaleFor(343) - 343 / 476) < 1e-9 && scaleFor(343) < 1);
check('広い画面（640px）では拡大', Math.abs(scaleFor(640) - 640 / 476) < 1e-9 && scaleFor(640) > 1);
check('幅が分からない（0・負・数字でない・NaN・Infinity）ときは等倍', [0, -5, '300', null, undefined, NaN, Infinity].every((v) => scaleFor(v) === 1));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
