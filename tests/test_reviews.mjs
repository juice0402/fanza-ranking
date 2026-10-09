// FANZAのレビューの評価・高評価ランキングの部品（site/src/lib/reviews.js）のテスト。実行: node tests/test_reviews.mjs
import { execFileSync } from 'node:child_process';
import * as R from '../site/src/lib/reviews.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

console.log('■ 読み方');
check('[平均×100, 件数] → { avg, count }（範囲の外・形が違えば null）', JSON.stringify(R.reviewOf([471, 31])) === '{"avg":4.71,"count":31}'
  && [null, [99, 3], [501, 3], [400, 0], [4.5, 3], 'x', [400]].every((v) => R.reviewOf(v) === null));
const n = R.normalizeReviews({ updated: '2026-10-10', items: { a: [450, 10], 'b c': [400, 2], d: [300, 0] } });
check('reviews.json → 日付と cid ごとの評価（形の違う行は捨てる）・無い・壊れていても空', n.updated === '2026-10-10' && [...n.byCid.keys()].join() === 'a'
  && [null, [], 'x', { items: [] }].every((v) => R.normalizeReviews(v).byCid.size === 0));
check('表示の文字', R.reviewLabel({ avg: 4.7, count: 1234 }) === '★4.70（1,234件）' && R.reviewLabel(null) === '');

console.log('\n■ 高評価ランキング');
const it = (cid, avg, count, dateKey = '2026-09-01', title = 't') => ({ cid, dateKey, title, review: avg ? { avg, count } : null });
const items = [it('few', 5, 3), it('many', 4.6, 300), it('mid', 4.8, 20), it('low', 3.0, 100), it('none', 0, 0), it('future', 5, 50, '2026-12-01'), it('tie', 4.6, 300)];
const top = R.topRated(items, '2026-10-10', { min: 10 });
check('レビューが決めた件数以上の発売済みの作品を、件数でならした評価の高い順（同じ点なら件数の多い順・品番の順）', top.map((i) => i.cid).join() === 'mid,many,tie,low', top.map((i) => i.cid).join());
check('件数でならす: 3件の満点は、20件の4.8・300件の4.6より下（全体の平均に引き寄せる）', R.topRated(items, '2026-10-10', { min: 1 }).map((i) => i.cid).indexOf('few') > 2
  && R.reviewScore({ avg: 5, count: 3 }, 4.2) < R.reviewScore({ avg: 4.6, count: 300 }, 4.2));
const skipped = R.topRated(items, '2026-10-10', { min: 10, limit: 2, skip: (i) => i.cid === 'mid' }).map((i) => i.cid).join();
check('入れない作品（skip）・本数の上限', skipped === 'many,tie', skipped);
const recent = R.recentTopRated([it('r1', 4.9, 5, '2026-10-01'), it('r2', 4.0, 3, '2026-09-20'), it('old', 5, 99, '2026-08-01'), it('r3', 5, 2, '2026-10-05')], '2026-10-10');
check('最近30日の発売で評価が高い作品（3件以上）', recent.map((i) => i.cid).join() === 'r1,r2', recent.map((i) => i.cid).join());
check('評価の高い作品の棚: 3本に満たなければ空', R.ratedShelf(items.slice(0, 2), '2026-10-10').length === 0 && R.ratedShelf(items, '2026-10-10').length >= 3);
check('ページのURL', R.REVIEW_RANKING_PATH === '/ranking/review/' && R.floorReviewRankingPath('doujin') === '/doujin/ranking/review/');

console.log('\n■ 集める道具（get_new_releases.py）との突き合わせ');
const py = JSON.parse(execFileSync('python3', ['-c', 'import sys,json; sys.path.insert(0,"."); import get_new_releases as G; print(json.dumps(G.parse_review({"review": {"count": 31, "average": "4.71"}})))'], { encoding: 'utf-8' }));
check('APIの review を同じ形（[平均×100, 件数]）で保存し、同じ形で読む', JSON.stringify(R.reviewOf(py)) === '{"avg":4.71,"count":31}');

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
