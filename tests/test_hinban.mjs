// 品番の見方（site/src/lib/hinban.js）のテスト。実行: node tests/test_hinban.mjs
import * as H from '../site/src/lib/hinban.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

console.log('■ 品番の頭の英字・作品IDの先頭');
check('頭の英字: SSIS-818 → SSIS・読めない形は空', H.hinbanPrefix('SSIS-818') === 'SSIS' && H.hinbanPrefix('ABC818') === '' && H.hinbanPrefix('') === '' && H.hinbanPrefix(null) === '');
check('作品IDの先頭: 数字・h_数字・無し', H.cidHead('1start00413') === '1' && H.cidHead('h_086jrze00326') === 'h_086' && H.cidHead('ssis00818') === '' && H.cidHead('h_086jrze00326a') === '');

console.log('■ 記号ごとのまとめ');
const item = (cid, maker, label, day) => ({ cid, maker, label: label ? { id: label.length, name: label } : null, dateKey: day });
const items = [
  item('ssis00001', 'S1', 'S1 NO.1 STYLE', '2026-01-02'),
  item('ssis00002', 'S1', 'S1 NO.1 STYLE', '2026-03-04'),
  item('ssis00003', 'S1', 'S1 NO.1 STYLE', '2026-02-01'),
  item('1mida00001', 'MOODYZ', 'MOODYZ DIVA', '2026-05-01'),
  item('mida00002', 'MOODYZ', 'MOODYZ DIVA', '2026-05-02'),
  item('h_123mida00003', 'ほかの会社', '', '2026-04-01'),
  item('mida00004', '不明', '', '2026-04-02'),
  item('abc00001', 'A社', '', '2026-01-01'),
  item('abc00002a', 'A社', '', '2026-01-01'), // 最後に英字 → 品番を作らない
  item('zz', 'B社', '', '2026-01-01'),
];
const rows = H.hinbanPrefixes(items);
check('3本以上の記号だけ・本数の多い順', rows.map((r) => r.prefix).join(',') === 'MIDA,SSIS', JSON.stringify(rows.map((r) => [r.prefix, r.count])));
const mida = rows[0];
check('メーカーは多い順（「不明」は数えない）', mida.count === 4 && mida.makers.map((m) => m.name).join(',') === 'MOODYZ,ほかの会社' && mida.makers[0].count === 2, JSON.stringify(mida.makers));
check('レーベルは名前と番号つき', mida.labels.length === 1 && mida.labels[0].name === 'MOODYZ DIVA' && mida.labels[0].id === 11);
check('いちばん新しい発売日', rows[1].last === '2026-03-04' && mida.last === '2026-05-02');
check('頭の文字ごと（A〜Z の順）', H.hinbanByLetter(rows).map((l) => l.letter).join('') === 'MS');

console.log('■ 説明の実例');
const ex = H.hinbanExamples(items, rows);
check('いちばん多い記号の、いちばん新しい作品', ex.plain && ex.plain.cid === 'mida00002' && ex.plain.code === 'MIDA-002', JSON.stringify(ex.plain));
check('先頭に数字などが付く作品IDの実例', ex.headed && ex.headed.cid === '1mida00001' && ex.headed.head === '1' && ex.headed.code === 'MIDA-001', JSON.stringify(ex.headed));
check('作品が無いときは空', H.hinbanExamples([], []).plain === null);

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
