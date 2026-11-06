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

console.log('\n■ ほかの売り場から（floorPicksFor）');
const f = (floor, cid, extra = {}) => ({ floor, cid, title: `作品${cid}`, actress: [], genres: [], ...extra });
const floors = {
  // 売り場の作品は人気の高い順に並んでいる（lib/floors.js の byRank）
  photo: { items: [f('photo', 'p1', { actress: ['月子'] }), f('photo', 'p2', { actress: ['花子'] }), f('photo', 'p3', { actress: ['花子'] })] },
  vr: { items: [f('vr', 'v1', { actress: ['花子'], title: '女子校生の作品' }), f('vr', 'v2', { actress: ['花子'] })] },
  cinema: { items: [] },
  doujin: { items: [f('doujin', 'd1', { genres: ['中出し', '人妻・主婦'] }), f('doujin', 'd2', { genres: ['熟女'] })] },
  comic: { items: [f('comic', 'c1', { genres: ['熟女'] })] },
  anime: { items: [f('anime', 'n1', { genres: ['人妻・主婦'] })] },
};
const v = w('x1', '2026-10-01', ['花子'], { genres: ['ハイビジョン', '中出し', '熟女', '人妻・主婦'] });
const picks = T.floorPicksFor(v, floors);
check('出演者の売り場（写真集・VR見放題）が先に、同じ出演者のいちばん人気の1本（未成年を連想させるタイトルは入れない）',
  picks.slice(0, 2).map((p) => `${p.floor}:${p.item.cid}:${p.reason}`).join() === 'photo:p2:花子の写真集,vr:v2:花子のVR', JSON.stringify(picks.slice(0, 2).map((p) => [p.floor, p.item.cid, p.reason])));
check('出演者のいない売り場は、作品のジャンルの順に、おだやかなジャンル名だけで選ぶ（「中出し」では選ばない）',
  picks.slice(2).map((p) => `${p.floor}:${p.item.cid}:${p.reason}`).join() === 'doujin:d2:「熟女」で人気,comic:c1:「熟女」で人気', JSON.stringify(picks.slice(2).map((p) => [p.floor, p.item.cid, p.reason])));
check('全部で4本まで・売り場の短い名前', picks.length === 4 && T.FLOOR_PICKS_SHOWN === 4 && picks[0].label === '写真集' && picks[1].label === 'VR見放題', picks.map((p) => p.label).join());
const many = w('x2', '2026-10-01', ['花子', 'あ', 'い', 'う', 'え'], { genres: ['人妻・主婦'] });
const pm = T.floorPicksFor(many, floors);
check('出演者が多い作品（総集編など）は、出演者では選ばない（ジャンルだけ）', pm.every((p) => T.FLOOR_PICKS_BY_GENRE.includes(p.floor)) && pm.map((p) => p.item.cid).join() === 'd1,n1', pm.map((p) => p.item.cid).join());
check('当てはまるものが無ければ空・売り場のデータが無くても止まらない', T.floorPicksFor(w('x3', '2026-10-01', [], { genres: [] }), floors).length === 0 && T.floorPicksFor(v, {}).length === 0);

console.log('\n■ ほかの売り場からの1行（floorPickRow）');
const row = T.floorPickRow({ floor: 'doujin', label: '同人', reason: '「熟女」で人気', item: f('doujin', 'd9', { title: '作品の題名', image_url: 'https://example.com/d9.jpg', maker: { name: 'サークルA' }, authors: ['作家1', '作家2'], price: 1320, off: 30 }) });
check('題名・作り手・売り場と値段を出し、選んだ理由は出さない（売り場の作品検索と同じ横長の行の形）',
  row.title === '作品の題名' && row.href === '/doujin/item/d9/' && row.img === 'https://example.com/d9.jpg' && row.line === 'サークルA｜作家1、作家2' && row.meta === '同人・1,320円（30%OFF）' && !JSON.stringify(row).includes('熟女'), JSON.stringify(row));
const crowd = T.floorPickRow({ floor: 'anime', label: 'アニメ', item: f('anime', 'n9', { actress: ['あ', 'い', 'う', 'え'], upcoming: true }) });
check('作家・出演者は3人まで（多いときは「ほか」）・予約は売り場の名前のあと・値段が無ければ出さない・作り手が無くても止まらない',
  crowd.line === 'あ、い、うほか' && crowd.meta === 'アニメ・予約' && crowd.upcoming === false && T.FLOOR_PICK_NAMES === 3, JSON.stringify(crowd));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
