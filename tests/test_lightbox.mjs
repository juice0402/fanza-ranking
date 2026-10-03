// サンプル画像の拡大表示（site/public/lightbox.js）の、画面に依存しない部分のテスト。実行: node tests/test_lightbox.mjs
// （ブラウザでの実際の動きは、PRごとの確認で見る。ここでは、送り方・スワイプの判定だけを見る）
import fs from 'node:fs';
import vm from 'node:vm';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

const source = fs.readFileSync(new URL('../site/public/lightbox.js', import.meta.url), 'utf-8');
const sandbox = { module: { exports: {} } };
vm.runInNewContext(source, sandbox); // document が無い環境（node）では、部品だけを出して終わる
const { step, swipeDelta } = sandbox.module.exports;

console.log('■ 前後に送る');
check('次へ: 1 → 2', step(1, 1, 8) === 2);
check('前へ: 3 → 2', step(3, -1, 8) === 2);
check('最後の次は、最初へ回る', step(7, 1, 8) === 0);
check('最初の前は、最後へ回る', step(0, -1, 8) === 7);
check('動かさない（0）はそのまま', step(5, 0, 8) === 5);
check('1枚だけでも落ちない', step(0, 1, 1) === 0 && step(0, -1, 1) === 0);
check('0枚でも落ちない', step(0, 1, 0) === 0);
check('範囲を超えた位置も、範囲内に直る', step(9, 0, 8) === 1 && step(-1, 0, 8) === 7);

console.log('\n■ スワイプの判定');
check('左へ大きく動かす → 次', swipeDelta(-120, 10) === 1);
check('右へ大きく動かす → 前', swipeDelta(120, -10) === -1);
check('少ししか動かない（タップ）→ 何もしない', swipeDelta(10, 2) === 0 && swipeDelta(-49, 0) === 0);
check('ちょうど50pxは、スワイプ', swipeDelta(-50, 0) === 1 && swipeDelta(50, 0) === -1);
check('縦のほうが大きい動き（スクロール）→ 何もしない', swipeDelta(-80, 120) === 0 && swipeDelta(60, -200) === 0);
check('斜めでも、横が十分大きければスワイプ', swipeDelta(-100, 60) === 1);

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
