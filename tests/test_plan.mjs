// サイトのファイル数の計画（site/src/lib/plan.js）のテスト。実行: node tests/test_plan.mjs
// 過去作品（カタログ）が増えても、Cloudflare Pages の無料プランの上限（2万ファイル）をこえないように、
// 作品ページを優先順に、残りの枠の数だけ作る。あふれた作品は、FANZAへ直接リンクする。
import * as P from '../site/src/lib/plan.js';
import { ARCHIVE_PAGE_SIZE, FILE_BUDGET, FIXED_FILES, ENTITY_LIST_LIMIT, INDEX_LIST_LIMIT } from '../site/src/config.js';
import { itemPath, actressSummary, makerSummary } from '../site/src/lib/items.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

const it = (cid, dateKey, extra = {}) => ({ cid, dateKey, comment: '', url: `https://www.dmm.co.jp/digital/videoa/-/detail/=/cid=${cid}/`, actress: [], maker: 'M', ...extra });

console.log('■ 設定');
check('上限は Cloudflare Pages の無料プランの2万ファイルより少ない（余裕を残す）', FILE_BUDGET > 0 && FILE_BUDGET < 20000, String(FILE_BUDGET));
check('固定のファイルの見積もり・一覧の上限が正の数', FIXED_FILES > 0 && ENTITY_LIST_LIMIT > 0 && INDEX_LIST_LIMIT > 0);

console.log('\n■ 作品ページ以外のファイルの数');
check('何も無いときは、固定分＋過去の作品の1ページ目', P.nonItemFileCount({}) === FIXED_FILES + 1);
check('出演者・メーカー・月・ジャンル・まとめ記事・カレンダーのページと、過去の作品のページ数を足す',
  P.nonItemFileCount({ actress: 10, maker: 5, month: 2, tag: 3, weekly: 1, ics: 7, archiveItems: ARCHIVE_PAGE_SIZE * 2 + 1 }) === FIXED_FILES + 10 + 5 + 2 + 3 + 1 + 7 + 3);

console.log('\n■ 作品ページの優先順');
const curatedNew = it('new01', '2026-10-05', { comment: 'こめんと' });
const curatedOld = it('cur01', '2026-09-01', { comment: 'こめんと' });
const curatedBare = it('cur02', '2026-08-01'); // 毎日の更新で載せた作品は、コメントが空でも最優先
const catCommented = it('cat01', '2020-01-01', { catalog: true, comment: 'こめんと' });
const catNew = it('cat02', '2026-07-01', { catalog: true });
const catOld = it('cat03', '2019-01-01', { catalog: true });
check('順位: 毎日の更新で載せた作品 0 → コメントのある過去作品 1 → そのほか 2',
  P.pagePriority(curatedNew) === 0 && P.pagePriority(curatedBare) === 0 && P.pagePriority(catCommented) === 1 && P.pagePriority(catNew) === 2);
const items = [catOld, catNew, catCommented, curatedBare, curatedOld, curatedNew];
const set3 = P.pagedCids(items, 3);
check('枠が3なら、毎日の更新で載せた作品の3本', [...set3].sort().join() === 'cur01,cur02,new01', [...set3].join());
const set4 = P.pagedCids(items, 4);
check('枠が4なら、次はコメントのある過去作品（発売が古くても、コメントの無い新しい過去作品より先）', set4.has('cat01') && !set4.has('cat02'), [...set4].join());
const set5 = P.pagedCids(items, 5);
check('同じ順位の中では、発売日の新しい順（人気順の順位が分からないとき）', set5.has('cat02') && !set5.has('cat03'), [...set5].join());
const ranked = [it('r1', '2015-01-01', { catalog: true, rank: 3 }), it('r2', '2026-09-01', { catalog: true, rank: 900 }), it('r3', '2026-09-02', { catalog: true }), it('r4', '2010-01-01', { catalog: true, rank: 1 })];
check('過去作品は、人気順の順位が上の作品から（発売日が古くても）。順位が分からない作品は、そのあと', [...P.pagedCids(ranked, 3)].sort().join() === 'r1,r2,r4' && P.pagedCids(ranked, 1).has('r4'), [...P.pagedCids(ranked, 3)].join());
check('コメントのある過去作品は、順位が低くても、コメントの無い作品より先', P.pagedCids([...ranked, it('r5', '2012-01-01', { catalog: true, rank: 29000, comment: 'こめんと' })], 1).has('r5'));
check('枠が作品数より多くても、全部（重複なし）', P.pagedCids(items, 100).size === items.length);
check('枠が0・負・小数でも落ちない', P.pagedCids(items, 0).size === 0 && P.pagedCids(items, -5).size === 0 && P.pagedCids(items, 2.7).size === 2);
check('元の並びは変えない', items[0] === catOld && items[5] === curatedNew);

console.log('\n■ サイト全体の計画');
const plan = P.planPages(items, { actress: 2, archiveItems: 6 }, FIXED_FILES + 1 + 2 + 4);
check('全体の上限から作品ページ以外を引いた数だけ、作品ページを作る', plan.itemBudget === 4 && plan.paged.size === 4 && plan.nonItem === FIXED_FILES + 1 + 2, JSON.stringify({ b: plan.itemBudget, n: plan.nonItem }));
const tight = P.planPages(items, { actress: 50000 });
check('作品ページ以外だけで上限をこえても、枠は0（負にならない）', tight.itemBudget === 0 && tight.paged.size === 0);
// 大きな数でも、作品ページ＋それ以外が上限に収まる
const many = Array.from({ length: 30000 }, (_, i) => it(`c${String(i).padStart(6, '0')}`, `20${String(10 + (i % 16)).padStart(2, '0')}-01-01`, { catalog: i >= 500 }));
const counts = { actress: 3000, maker: 600, month: 3, tag: 20, weekly: 2, ics: 400, archiveItems: 30000 };
const big = P.planPages(many, counts);
check('3万本・出演者3000人でも、作品ページ＋それ以外のファイルが上限以内', big.paged.size + big.nonItem <= FILE_BUDGET && big.paged.size > 10000, JSON.stringify({ paged: big.paged.size, nonItem: big.nonItem }));
check('毎日の更新で載せた作品は、全部ページがある', many.filter((i) => !i.catalog).every((i) => big.paged.has(i.cid)));

console.log('\n■ 作品へのリンク');
const paged = new Set(['new01']);
check('作品ページがあれば作品ページ（サイトの中）', JSON.stringify(P.itemHref(curatedNew, paged)) === JSON.stringify({ href: itemPath('new01'), external: false }));
const out = P.itemHref(catOld, paged);
check('作品ページが無ければ、FANZAの作品ページ（外へのリンク）', out.href === catOld.url && out.external === true);
check('FANZAのURLも無い作品は、作品ページのURLのまま（外へのリンクにしない）', P.itemHref({ ...catOld, url: '' }, paged).external === false);
check('外へのリンクの属性は、サイトのほかの「FANZAで見る」と同じ', P.OUTBOUND_ATTRS.target === '_blank' && P.OUTBOUND_ATTRS.rel === 'sponsored nofollow noopener noreferrer');

console.log('\n■ 検索エンジンに出すか（noindex・sitemap）');
check('コメントのある作品が1本でもある一覧は出す・過去作品だけ（コメント無し）の一覧は出さない',
  P.listIndexable([catOld, catCommented]) && !P.listIndexable([catOld, catNew]) && !P.listIndexable([it('x', '2020-01-01', { comment: '   ' })]));
check('作品がまだ1本も無い一覧（最初の状態）は、これまでどおり出す', P.listIndexable([]));
check('作品ページは、ページがあり、コメントがあるときだけ出す',
  P.itemIndexable(curatedNew, paged) && !P.itemIndexable(catCommented, paged) && !P.itemIndexable(curatedBare, new Set(['cur02'])));

console.log('\n■ 発売日カレンダー・出演者/メーカーのページ');
check('新作・予約が載っている人だけカレンダーを作る（過去作品だけの人は作らない）',
  P.hasCalendar({ items: [catOld, curatedOld] }) && !P.hasCalendar({ items: [catOld, catNew] }));
const listing = P.entityListing(items, 4);
check('ページに並べるのは先頭から limit 本まで。並べきれない本数も分かる', listing.shown.length === 4 && listing.hidden === 2 && listing.shown[0] === items[0]);
check('limit より少なければ全部・0や負でも落ちない', P.entityListing(items, 100).hidden === 0 && P.entityListing(items, 0).shown.length === 0 && P.entityListing(items, -1).hidden === items.length);

console.log('\n■ 紹介文（過去作品を含むときの言い方）');
const g = (list) => ({ name: '花子', items: list.map((i) => ({ ...i, formats: [], actress: ['花子'] })) });
check('新作・予約だけなら、これまでどおり', actressSummary(g([curatedNew, curatedOld])).startsWith('FANZAの新作・予約として掲載している花子さん'));
check('過去作品を含むなら「新作・予約と過去の作品として」', actressSummary(g([curatedNew, catOld])).startsWith('FANZAの新作・予約と過去の作品として掲載している花子さん') && makerSummary(g([catOld, catNew])).startsWith('FANZAの新作・予約と過去の作品として掲載している花子の'));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
