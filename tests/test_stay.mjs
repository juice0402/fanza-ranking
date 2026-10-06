// 作品ページの「次に見るもの」（site/src/lib/stay.js）のテスト。実行: node tests/test_stay.mjs
import * as T from '../site/src/lib/stay.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};
const w = (cid, dateKey, actress, extra = {}) => ({ cid, dateKey, actress, maker: 'メーカーA', title: `作品${cid}`, genres: [], formats: [], ...extra });

console.log('■ 次の新作（nextWorksOf）');
const today = '2026-10-06';
const a1 = w('a1', '2026-10-01', ['花子']);
const works = {
  花子: [w('a2', '2026-10-20', ['花子']), w('a3', '2026-10-10', ['花子', '月子']), w('a4', '2026-09-01', ['花子']), w('a5', '2026-10-12', ['花子'], { title: '女子校生の放課後' }), a1],
  月子: [w('a3', '2026-10-10', ['花子', '月子']), w('b1', '2026-10-08', ['月子'])],
};
const byName = new Map(Object.entries(works).map(([n, items]) => [n, { items }]));
const n1 = T.nextWorksOf(a1, byName, today);
check('出演者の予約受付中の作品を、発売日が近い順に（この作品・発売済み・未成年を連想させるタイトルは入れない）', n1.items.map((i) => i.cid).join() === 'a3,a2' && n1.names.join() === '花子', JSON.stringify(n1));
const two = w('c1', '2026-10-01', ['花子', '月子']);
const n2 = T.nextWorksOf(two, byName, today);
check('出演者が2人なら、2人の次の新作を合わせて近い順・同じ作品は1回だけ・本数の上限', n2.items.map((i) => i.cid).join() === 'b1,a3,a2' && n2.names.join() === '花子,月子' && T.nextWorksOf(two, byName, today, { limit: 2 }).items.length === 2, JSON.stringify(n2.items.map((i) => i.cid)));
check('出演者が多い作品（オムニバスなど）・出演者のいない作品には出さない', T.nextWorksOf(w('d', '2026-10-01', ['花子', 'b', 'c', 'd', 'e']), byName, today).items.length === 0 && T.nextWorksOf(w('e', '2026-10-01', []), byName, today).items.length === 0);

console.log('\n■ 同じ出演者・メーカーの作品（relatedForPage）');
const all = [a1, ...works.花子.filter((x) => x.cid !== 'a1'), w('m1', '2026-09-01', ['別人']), w('m2', '2026-09-02', ['別人'], { title: 'ロリ系の作品' })];
const rel = T.relatedForPage(a1, all, 4);
check('同じ出演者 → 同じメーカーの順・この作品は入れない・未成年を連想させるタイトルは入れない・本数の上限', rel.map((i) => i.cid).join() === 'a2,a3,a4,m1' && !rel.some((i) => i.cid === 'a1' || i.cid === 'a5' || i.cid === 'm2'), rel.map((i) => i.cid).join());
check('決まった本数（スマホで3列×2段）', T.RELATED_SHOWN === 6 && T.NEXT_WORKS_SHOWN === 3);

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
