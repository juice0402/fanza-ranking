// 人気順（site/src/lib/popularity.js。「新着の人気順」と「全体の人気順」）のテスト。実行: node tests/test_popularity.mjs
import * as P from '../site/src/lib/popularity.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

console.log('■ 順位のファイルの読み方');
const pop = P.normalizePopularity({ date: '2026-10-05', new: { n1: 1, n2: 2, bad: 0, odd: 'x', far: 50000 }, all: { c1: 7 }, prev_date: '2026-10-04', prev: { n2: 9 } });
check('popularity.json: 日付・新着の人気順・全体の人気順・前の日の新着の人気順（変な値は捨てる）', pop.date === '2026-10-05' && pop.newRank.get('n1') === 1 && pop.newRank.size === 2 && pop.allRank.get('c1') === 7 && pop.prevDate === '2026-10-04' && pop.prevRank.get('n2') === 9, [...pop.newRank].join());
check('無い・形が違うときは空', [null, undefined, [], 'x', { date: 'あした', new: [], all: null }].every((v) => { const p = P.normalizePopularity(v); return p.date === '' && p.newRank.size === 0 && p.allRank.size === 0; }));
check('catalog_rank.json の順位: [順位, 一回り] の順位。「まだ分からない」（50000）・形が違えば null', P.catalogAllRank({ a: [12, 3], b: [50000, 2], c: 'x' }, 'a') === 12 && P.catalogAllRank({ b: [50000, 2] }, 'b') === null && P.catalogAllRank({ c: 'x' }, 'c') === null && P.catalogAllRank(null, 'a') === null && P.catalogAllRank({}, 'constructor') === null);
check('2つの順位の上のほう（どちらか無ければ、ある方）', P.bestRank(5, 3) === 3 && P.bestRank(null, 4) === 4 && P.bestRank(9, null) === 9 && P.bestRank(null, null) === null);

console.log('\n■ ランキング');
const it = (cid, dateKey, popAll = null, popNew = null) => ({ cid, dateKey, popAll, popNew });
const items = [
  it('old', '2020-01-01', 1, null), it('new1', '2026-10-01', 40, 2), it('new2', '2026-09-20', null, 1), it('wait', '2026-10-20', 2, 3),
  it('past31', '2026-09-03', 5, 4), it('new3', '2026-10-04', 9, null),
];
const today = '2026-10-04';
check('新着の人気順: 最近1週間に発売された作品（予約・8日より前は除く）を、新着の順位の順に', P.newRanking(items, today).map((i) => i.cid).join() === 'new1', P.newRanking(items, today).map((i) => i.cid).join());
check('期間を変えれば、その期間で（30日）', P.newRanking(items, today, 100, 30).map((i) => i.cid).join() === 'new2,new1');
check('全体の人気順: 発売済みの作品を、全体の順位の順に（予約は除く）', P.allRanking(items, today).map((i) => i.cid).join() === 'old,past31,new3,new1', P.allRanking(items, today).map((i) => i.cid).join());
check('本数の上限', P.allRanking(items, today, 2).length === 2 && P.newRanking(items, today, 1, 30).map((i) => i.cid).join() === 'new2');
check('同じ順位なら、新しい作品から（並びがぶれない）', P.allRanking([it('x', '2026-01-01', 3), it('y', '2026-02-01', 3)], today).map((i) => i.cid).join() === 'y,x');
check('元の並びは変えない・空でも落ちない', items[0].cid === 'old' && P.newRanking([], today).length === 0 && P.allRanking([], today).length === 0);
check('ページの場所・新着は1週間', P.RANKING_PATH === '/ranking/' && P.RANKING_ALL_PATH === '/ranking/all/' && P.RANKING_LIMIT === 100 && P.NEW_RANK_DAYS === 7);

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
