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
  row.title === '作品の題名' && row.href === '/doujin/w/d9/' && row.img === 'https://example.com/d9.jpg' && row.line === 'サークルA｜作家1、作家2' && row.meta === '同人・1,320円（30%OFF）' && !JSON.stringify(row).includes('熟女'), JSON.stringify(row));
// コメントのある作品は /<売り場>/item/、無い作品は /<売り場>/w/（2026-11-10。案A）
const rowC = T.floorPickRow({ floor: 'doujin', label: '同人', item: f('doujin', 'd8', { comment: 'ひとこと。' }) });
check('リンク先: コメントのある作品は /doujin/item/・無い作品は /doujin/w/', rowC.href === '/doujin/item/d8/' && row.href === '/doujin/w/d9/', rowC.href);
const crowd = T.floorPickRow({ floor: 'anime', label: 'アニメ', item: f('anime', 'n9', { actress: ['あ', 'い', 'う', 'え'], upcoming: true }) });
check('作家・出演者は3人まで（多いときは「ほか」）・予約は売り場の名前のあと・値段が無ければ出さない・作り手が無くても止まらない',
  crowd.line === 'あ、い、うほか' && crowd.meta === 'アニメ・予約' && crowd.upcoming === false && T.FLOOR_PICK_NAMES === 3, JSON.stringify(crowd));

console.log('■ 沼を深くする（人気の順に・次に見る女優。2026-11-12 案B）');
{
  const day = '2026-11-12';
  const p = (cid, dateKey, actress, popAll, extra = {}) => w(cid, dateKey, actress, { popAll, popNew: null, ...extra });
  // 女優Aの作品: 人気の順は a2(3位) → a1(10位) → a4(20位。新着の順位のほうが上なら、そちら) → 順位なしは新しい順 a3 → a5。a6 は発売前・a7 は未成年を連想させるタイトル
  const A = [
    p('a1', '2026-10-01', ['女優A'], 10),
    p('a2', '2026-09-01', ['女優A'], 3),
    p('a3', '2026-11-01', ['女優A'], null),
    w('a4', '2026-08-01', ['女優A', '女優B'], { popAll: 50, popNew: 20 }),
    p('a5', '2026-07-01', ['女優A'], null),
    p('a6', '2026-12-01', ['女優A'], null),
    p('a7', '2026-06-01', ['女優A'], 1, { title: '女子校生の作品' }),
    p('a8', '2026-05-01', ['女優A', 'x1', 'x2', 'x3', 'x4'], 2),
  ];
  const B = [A[3], p('b1', '2026-10-05', ['女優B'], 5, { maker: 'メーカーB' }), p('b2', '2026-10-06', ['女優B'], 40, { maker: 'メーカーB' })];
  const C = [p('c1', '2026-10-01', ['女優C'], 7), p('c2', '2026-10-02', ['女優C'], 8, { comment: 'ひとこと。' })];
  const D = [p('d1', '2026-10-01', ['女優D'], 2, { maker: 'メーカーB' }), p('d2', '2026-10-02', ['女優D'], 9, { maker: 'メーカーB' })];
  const groups = [
    { name: '女優A', path: '/actress/a/', items: A },
    { name: '女優B', path: '/actress/b/', items: B },
    { name: '女優C', path: '/actress/c/', items: C },
    { name: '女優D', path: '/actress/d/', items: D },
  ];
  const byName = new Map(groups.map((g) => [g.name, g]));
  const order = T.walkList(A[0], A, day).map((x) => x.cid).join(',');
  check('人気の順: 順位の小さい順（全体と新着の上のほう）→ 順位なしは新しい順・発売前・未成年を連想させるタイトル・総集編（出演者5人以上）は入れない', order === 'a2,a1,a4,a3,a5', order);
  check('発売前の作品のページでは、その作品だけ入れて位置を出す', T.walkList(A[5], A, day).some((x) => x.cid === 'a6'));
  const mid = T.castWalksOf(A[0], byName, day)[0];
  check('前の作品・次の作品・何本めか', mid.name === '女優A' && mid.at === 2 && mid.total === 5 && mid.prev.cid === 'a2' && mid.next.cid === 'a4' && mid.nextName === '' && mid.path === '/actress/a/', JSON.stringify({ at: mid.at, total: mid.total }));
  const first = T.castWalksOf(A[1], byName, day)[0];
  check('いちばん人気の作品は、前の作品なし', first.at === 1 && first.prev === null && first.next.cid === 'a1');
  const two = T.castWalksOf(A[3], byName, day);
  check('出演者が2人なら2人ぶん（出演者の並び順）', two.length === 2 && two[0].name === '女優A' && two[1].name === '女優B' && two[1].at === 2 && two[1].prev.cid === 'b1' && two[1].next.cid === 'b2');
  check('出演者が多すぎる作品・作品が1本だけの人には出さない',
    T.castWalksOf(w('z1', '2026-10-01', ['女優A', 'x', 'y', 'z', 'v']), byName, day).length === 0 &&
    T.castWalksOf(w('z2', '2026-10-01', ['ひとり']), new Map([['ひとり', { name: 'ひとり', path: '/actress/h/', items: [w('z2', '2026-10-01', ['ひとり'])] }]]), day).length === 0);

  // 次に見る女優: 女優Aの共演は女優B（1本）。同じメーカー（メーカーA）は女優C。検索に出せるページ（コメントのある作品がある）の人が先
  const idx = T.actressLinkIndex(groups, (g) => g.items.some((x) => String(x.comment ?? '').trim()));
  const nextA = T.nextActressesOf('女優A', idx);
  check('検索に出せる人が先 → 共演 → 同じメーカー・自分は入れない', nextA.map((r) => r.name).join(',') === '女優C,女優B' && nextA[0].kind === 'maker' && nextA[1].kind === 'costar' && nextA[1].count === 1, JSON.stringify(nextA));
  check('顔の下の文は「共演○本」と「同じメーカー」', T.nextActressNote(nextA[1]) === '共演1本' && T.nextActressNote(nextA[0]) === '同じメーカー');
  const idx2 = T.actressLinkIndex(groups);
  check('検索に出せる人がいなければ、共演が先', T.nextActressesOf('女優A', idx2).map((r) => r.name).join(',') === '女優B,女優C');
  check('同じメーカーは、その人にいちばん多いメーカーの人が先（女優BはメーカーBの女優D → メーカーAの女優C）', T.nextActressesOf('女優B', idx2).map((r) => r.name).join(',') === '女優A,女優D,女優C', JSON.stringify(T.nextActressesOf('女優B', idx2)));
  check('人数は NEXT_ACTRESS_SHOWN まで', T.NEXT_ACTRESS_SHOWN === 6 && T.nextActressesOf('女優A', idx2, 1).length === 1);
  // 最後の作品では、次に見る女優のいちばん人気の作品へ（前の作品と同じ作品は選ばない）
  const last = T.castWalksOf(A[4], byName, day, { nextActress: (name) => T.nextActressWork(name, idx, day, A[4].cid) })[0];
  check('いちばん最後の作品では、次に見る女優のいちばん人気の作品へ', last.at === 5 && last.prev.cid === 'a3' && last.next.cid === 'c1' && last.nextName === '女優C', JSON.stringify({ next: last.next?.cid, name: last.nextName }));
  check('次に見る女優の作品が無いときは、次の作品なし', T.castWalksOf(A[4], byName, day, { nextActress: () => null })[0].next === null);
}

console.log('\n■ 身長とカップが近い女優（女優のページ。FANZA公式のプロフィールの数字。2026-11-12）');
{
  const mk = (name, n, noted = false) => ({ name, path: `/actress/${name}/`, items: Array.from({ length: n }, (_, k) => ({ cid: `${name}${k}`, comment: noted && !k ? 'ひとこと' : '' })) });
  const groups = [mk('本人', 5), mk('近い', 3), mk('近い出せる', 2, true), mk('遠い', 9), mk('別カップ', 9), mk('身長なし', 9), mk('ちょうど3cm', 4), mk('次に見る女優の人', 9, true)];
  const prof = { 本人: { height: 158, cup: 'E' }, 近い: { height: 159, cup: 'E' }, 近い出せる: { height: 161, cup: 'E' }, 遠い: { height: 162, cup: 'E' }, 別カップ: { height: 158, cup: 'F' },
    身長なし: { height: null, cup: 'E' }, ちょうど3cm: { height: 155, cup: 'E' }, 次に見る女優の人: { height: 158, cup: 'E' } };
  const idx = T.bodyIndex(groups, (n) => prof[n] ?? null, (g) => g.items.some((i) => i.comment));
  check('索引: 身長とカップがある人だけ・カップごと', idx.get('E').length === 6 && idx.get('F').length === 1 && !idx.get('E').some((r) => r.name === '身長なし'));
  const near = T.bodyNeighborsOf('本人', prof['本人'], idx, { exclude: ['次に見る女優の人'] });
  check('同じカップで身長±3cm・自分と「次に見る女優」の人は除く・検索に出せる人が先 → 身長の近い順',
    near.rows.map((r) => r.name).join() === '近い出せる,近い,ちょうど3cm' && near.min === 155 && near.max === 161 && near.cup === 'E', JSON.stringify(near));
  check('顔の下は「159cm・Eカップ」・女優検索は同じ身長の幅とカップで開く', T.bodyNote(near.rows[1]) === '159cm・Eカップ' && T.bodySearchHref('/actress/', near) === '/actress/?height=155-161&cup=E');
  check('身長かカップが無い人には出さない（null）', T.bodyNeighborsOf('身長なし', prof['身長なし'], idx) === null && T.bodyNeighborsOf('x', null, idx) === null && T.bodyNeighborsOf('x', { height: 300, cup: 'E' }, idx) === null);
  check('6人まで', T.bodyNeighborsOf('本人', prof['本人'], idx, { limit: 2 }).rows.length === 2);
}

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
