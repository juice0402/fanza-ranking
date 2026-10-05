// トップの「きょうの数字」「きょうの新着人気TOP3」「きょうの話題」の部品（site/src/lib/topics.js）のテスト。実行: node tests/test_topics.mjs
import * as T from '../site/src/lib/topics.js';
import { normalizePopularity } from '../site/src/lib/popularity.js';
import { normalizeSale } from '../site/src/lib/sale.js';
import { normalizeEvents } from '../site/src/lib/events.js';
import { RANKING_SHOWN } from '../site/src/lib/items.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

const TODAY = '2026-10-05';
const it = (cid, dateKey, popNew, extra = {}) => ({
  cid, dateKey, popNew, title: `作品 ${cid}`, image_url: `https://pics.dmm.co.jp/${cid}pl.jpg`, url: `https://video.dmm.co.jp/av/content/?id=${cid}`,
  actress: [], maker: 'M', genres: [], vr: false, comment: '', ...extra,
});
const linkOf = (i) => ({ href: `/item/${i.cid}/`, external: false });

console.log('■ 設定');
check('トップに出すのは3本（設定と同じ）・データは6本（VR作品を隠したときの差し替え用）', T.TOP_SHOWN === RANKING_SHOWN && T.TOP_SHOWN === 3 && T.TOP_DATA === 6);

console.log('\n■ today.json の読み込み（normalizeToday）');
const rawToday = {
  date: TODAY,
  daily: [{ d: '2026-10-04', n: 180 }, { d: TODAY, n: 200 }, { d: 'x', n: 1 }, { d: '2026-10-03', n: -1 }, { d: '2026-10-03', n: 1.5 }],
  upcoming_total: 3402,
  upcoming: [
    { c: 'up1', t: ' 予約の作品 ', d: '2026-10-08', a: ['花子', 3], m: '', i: 'https://pics.dmm.co.jp/up1.jpg', u: 'https://video.dmm.co.jp/av/content/?id=up1', r: 1, v: 1 },
    { c: 'up2', t: '予約2', d: '2026-10-09', a: [], m: 'メーカーB', i: 'http://evil.example/x.jpg', u: 'https://video.dmm.co.jp/av/content/?id=up2', r: 2 },
    { c: 'up3', t: 'リンクの無い作品', d: '2026-10-09', r: 3, u: 'https://evil.example/' },
    { c: 'up4', t: '', d: '2026-10-09', r: 4, u: 'https://video.dmm.co.jp/av/content/?id=up4' },
    { c: 'up5', t: '順位の無い作品', d: '2026-10-09', u: 'https://video.dmm.co.jp/av/content/?id=up5' },
    { c: 'up6', t: '予約6', d: '2026-10-12', a: [], m: 'メーカーC', i: 'https://pics.dmm.co.jp/up6.jpg', u: 'https://video.dmm.co.jp/av/content/?id=up6', r: 3 },
  ],
  prev_upcoming: ['up9', 7],
};
const td = T.normalizeToday(rawToday);
check('日付・本数を読む（形の違う行は捨てる）', td.date === TODAY && td.daily.length === 2 && td.upcomingTotal === 3402, JSON.stringify(td.daily));
check('予約の人気順: タイトル・順位・FANZAのリンクがある作品だけ（リンクはFANZAのhttpsだけ・画像もFANZAだけ）',
  td.upcoming.map((u) => u.cid).join() === 'up1,up2,up6' && td.upcoming[1].image_url === '' && td.upcoming[0].title === '予約の作品', td.upcoming.map((u) => u.cid).join());
check('出演者は文字だけ・メーカーが空なら「不明」・VRの印（v:1）', td.upcoming[0].actress.join() === '花子' && td.upcoming[0].maker === '不明' && td.upcoming[0].vr === true && td.upcoming[1].vr === false);
check('前の日の予約の人気順は、作品IDの文字だけ', td.prevUpcoming.has('up9') && td.prevUpcoming.size === 1);
const empty = T.normalizeToday(null);
check('無い・形が違うときは空（落ちない）', empty.date === '' && empty.daily.length === 0 && empty.upcomingTotal === null && empty.upcoming.length === 0 && T.normalizeToday([1]).date === '');

console.log('\n■ 新着人気TOP3（topEntries）');
const items = [
  it('a', '2026-10-03', 3), it('b', '2026-10-04', 1), it('c', '2026-09-20', 2), // c は1週間より前の発売なので入らない
  it('d', '2026-10-06', 4), // 予約（まだ発売前）は入らない
  it('e', TODAY, 5), it('f', '2026-10-01', null), it('g', '2026-10-02', 8), it('h', '2026-10-02', 9), it('i', '2026-10-02', 10),
];
check('この1週間に発売された作品を、新着の人気順に（予約・古い作品・順位の無い作品は除く）。6本まで', T.topEntries(items, TODAY).map((i) => i.cid).join() === 'b,a,e,g,h,i');
check('新着の人気順がまだ無いときは空', T.topEntries([it('x', TODAY, null)], TODAY).length === 0);

console.log('\n■ 前の日からの順位の動き（rankMove）');
const prev = new Map([['a', 5], ['b', 1], ['c', 2]]);
check('上がった・下がった・同じ・初登場', T.rankMove('a', 2, prev).text === '▲3' && T.rankMove('c', 4, prev).text === '▼2' && T.rankMove('b', 1, prev).kind === 'same' && T.rankMove('z', 7, prev).text === '初登場');
check('読み上げ用の文も付く', T.rankMove('a', 2, prev).label === 'きのう5位から3つ上がった');
check('前の日の順位がまだ無い（集め始めた日）・今の順位が無いときは null', T.rankMove('a', 2, new Map()) === null && T.rankMove('a', null, prev) === null);

console.log('\n■ きょうの話題（buildTopics）');
const many = [
  it('t1', '2026-10-01', 1), it('t2', '2026-10-01', 2), it('t3', '2026-10-01', 3), // TOP3（話題では除く）
  it('r1', '2026-10-01', 4, { actress: ['花子'] }), // 前の日 40位 → 4位
  it('r2', '2026-10-02', 6, { actress: ['花子'], vr: true }), // 前の日は圏外（41位あつかい）→ 6位（VR）
  it('r3', '2026-10-02', 30), // 前の日 35位 → 30位（上がり幅が小さい）
  it('r4', '2026-10-01', 12), // 前の日 30位 → 12位（VR作品を隠したときの、急上昇の繰り上げ）
  it('n1', TODAY, 7, { actress: ['月子'], maker: 'メーカーA' }), // きょう発売（前の日は無いので、急上昇には入れない）
  it('db', '2026-10-03', 9, { actress: ['新人'], genres: ['デビュー作品'] }),
  it('s1', '2026-09-01', null, { popAll: 5 }),
];
const pop = normalizePopularity({ date: TODAY, new: {}, prev_date: '2026-10-04', prev: { t1: 1, t2: 2, t3: 3, r1: 40, r3: 35, r4: 30, db: 10 } });
const saleData = normalizeSale({
  date: TODAY,
  campaigns: [
    { title: '週末セール', begin: '2026-10-01 00:00', end: '2026-10-06 23:59' },
    { title: '長いセール', begin: '2026-10-01', end: '2026-10-30' },
    { title: '秋の新作セール', begin: '2026-10-04 10:00', end: '2026-10-10 23:59' },
  ],
  items: [{ c: 's1', k: 0 }, { c: 'r3', k: 1 }, { c: 't1', k: 2 }, { c: 't2', k: 2 }, { c: 't3', k: 2 }],
});
const ctx = {
  items: many, today: TODAY, popularity: pop, todayData: td, sale: saleData, linkOf,
  actressPage: (n) => (n === '花子' ? '/actress/hanako/' : ''), faceOf: (n) => (n === '新人' ? 'https://pics.dmm.co.jp/face.jpg' : ''),
  skip: new Set(['t1', 't2', 't3']),
};
const topics = T.buildTopics(ctx);
const kinds = topics.map((t) => t.kind).join();
check('種類と順番: 急上昇 → きょう発売 → 予約で人気 → 予約に初登場 → セール開始 → もうすぐ終わるセール（人気の女優・デビュー作は、別の欄）', kinds === 'rise,rise,today,upcoming,entry,salenew,sale', kinds);
const rise = topics.filter((t) => t.kind === 'rise');
check('急上昇: 上がり幅の大きい順・前の日の順位から（圏外からも）。TOP3の作品・上がり幅の小さい作品・きょう発売の作品は入れない',
  rise.map((t) => t.text).join('/') === '新着の人気順 40位 → 4位/新着の人気順 圏外 → 6位', rise.map((t) => t.text).join('/'));
check('VR作品の話題には印（VR作品を隠すと消える）', rise[0].vr === false && rise[1].vr === true);
check('VR作品の急上昇には、VRでない次の作品の代わり（繰り上げ）が付く。VRでない話題には付かない', rise[1].alt?.title === '作品 r4' && rise[1].alt.vr === false && rise[1].alt.kind === 'rise' && rise[1].alt.text === '新着の人気順 30位 → 12位' && !rise[0].alt, JSON.stringify(rise[1].alt));
const tday = topics.find((t) => t.kind === 'today');
check('きょう発売: 出演者・メーカー・順位', tday.title === '作品 n1' && tday.text === '月子｜メーカーA｜新着の人気順 7位' && tday.href === '/item/n1/', tday.text);
const up = topics.find((t) => t.kind === 'upcoming');
check('予約で人気: 予約の人気順の順位・発売日・出演者', up.label === '予約で人気' && up.text === '予約の人気順 1位｜10月8日発売｜花子' && up.vr === true, up.text);
check('予約で人気の1位がVR作品なら、VRでない次の作品が代わり（繰り上げ）', up.alt?.title === '予約2' && up.alt.text === '予約の人気順 2位｜10月9日発売', JSON.stringify(up.alt));
const entry = topics.find((t) => t.kind === 'entry');
check('予約に初登場: 前の日の予約の人気順にいなかった作品（ほかの話題に出した作品・繰り上げに使った作品は出さない）', entry.title === '予約6' && entry.text === '予約の人気順 3位｜10月12日発売', entry.text);
const sale = topics.find((t) => t.kind === 'sale');
check('もうすぐ終わるセール: 終わりが2日以内のキャンペーンだけ。セールのページへ・終わりの時刻（ブラウザが、すぎたら隠す）',
  sale.title === '週末セール' && sale.text === '10月6日 23:59まで｜1本がセール中' && sale.href === '/sale/#sale-0' && sale.end === '2026-10-06T23:59:59+09:00', sale.text);
const salenew = topics.find((t) => t.kind === 'salenew');
check('セール開始: きのう・きょう始まったキャンペーン（このサイトの作品が3本以上）。始まりと終わり・本数・その特集の見出しへ・表紙',
  salenew.label === 'セール開始' && salenew.title === '秋の新作セール' && salenew.text === '10月4日から10月10日 23:59まで｜3本がセール中' && salenew.href === '/sale/#sale-2' && salenew.end === '2026-10-10T23:59:59+09:00' && salenew.image === 'https://pics.dmm.co.jp/t1pl.jpg', JSON.stringify(salenew));
const viaPage = T.buildTopics({ ...ctx, campaignHref: (g) => `/sale/page-${g.k}/` }).find((t) => t.kind === 'sale');
check('セールの話題のリンク先は、特集のページを渡せばそこへ（渡さなければ、セールのページの、その特集の見出し）', viaPage.href === '/sale/page-0/' && sale.href === '/sale/#sale-0', viaPage.href);
const saleWith = (campaigns, rows) => T.buildTopics({ ...ctx, sale: normalizeSale({ date: TODAY, campaigns, items: rows }) }).filter((t) => t.kind === 'salenew' || t.kind === 'sale').map((t) => `${t.kind}:${t.title}`).join();
check('始まって2日以上たったキャンペーン・このサイトの作品が3本より少ないキャンペーンは、セール開始にしない',
  saleWith([{ title: '前からのセール', begin: '2026-10-03 00:00', end: '2026-10-20 23:59' }, { title: '小さなセール', begin: TODAY, end: '2026-10-20 23:59' }], [{ c: 't1', k: 0 }, { c: 't2', k: 0 }, { c: 't3', k: 0 }, { c: 's1', k: 1 }, { c: 'r3', k: 1 }]) === '');
check('始まったばかりで、もうすぐ終わるキャンペーンは、セール開始にだけ出す（もうすぐ終わるは、次のキャンペーン）',
  saleWith([{ title: '1日だけ', begin: TODAY, end: '2026-10-05 23:59' }, { title: '週末セール', begin: '2026-10-01', end: '2026-10-06 23:59' }], [{ c: 't1', k: 0 }, { c: 't2', k: 0 }, { c: 't3', k: 0 }, { c: 's1', k: 1 }]) === 'salenew:1日だけ,sale:週末セール');
// セールで人気: 値引きの分かるセール中の作品の中で、人気のいちばん高い作品（発売済み・TOP3と同じ作品は出さない・未成年を連想させるタイトルは入れない）
const pricedSale = normalizeSale({
  date: TODAY,
  campaigns: [{ title: '週末セール', begin: '2026-10-01 00:00', end: '2026-10-06 23:59' }],
  items: [{ c: 't1', k: 0, p: 700, l: 1000 }, { c: 's1', k: 0, p: 1400, l: 2000 }, { c: 'r3', k: 0, p: 980, l: 1980 }, { c: 'm1', k: 0, p: 500, l: 1000 }, { c: 'r1', k: 0 }],
});
const withHot = T.buildTopics({ ...ctx, items: [...many, it('m1', '2026-09-01', null, { popAll: 1, title: '女子校生の作品' })], sale: pricedSale }, 20);
const hotT = withHot.find((t) => t.kind === 'salehot');
check('セールで人気: 値引きの分かる作品の中で人気のいちばん高い作品（TOP3・未成年を連想させるタイトル・値引きの分からない作品は除く）。「○%OFF ○円〜｜いつまで」',
  hotT && hotT.label === 'セールで人気' && hotT.title === '作品 s1' && hotT.text === '30%OFF 1,400円〜｜10月6日 23:59まで' && hotT.end === '2026-10-06T23:59:59+09:00' && hotT.href === '/item/s1/', JSON.stringify(hotT));
check('セールで人気: 予約に初登場のあと、週のまとめ・セールの特集の話題の前', withHot.map((t) => t.kind).indexOf('salehot') === withHot.map((t) => t.kind).indexOf('entry') + 1, withHot.map((t) => t.kind).join());
check('セールで人気: 値引きの分かるセール中の作品が無ければ出さない', !topics.some((t) => t.kind === 'salehot'));
// イベント: 予約に初登場のあと、セールで人気の前（2件まで。lib/events.js の eventTopics）
const evData = normalizeEvents({ rows: [
  { date: '2026-10-07', names: ['架空ゆめか'], agency: 'tpowers', kind: '撮影会', url: 'https://www.t-powers.co.jp/event/', seen: TODAY },
  { date: '2026-10-08', names: ['見本はるな'], agency: 'capsule', kind: 'オフ会', url: 'https://capsule.bz/a/', seen: TODAY },
  { date: '2026-10-09', names: ['三人目'], agency: 'capsule', kind: 'オフ会', url: 'https://capsule.bz/b/', seen: TODAY },
] });
const withEv = T.buildTopics({ ...ctx, items: [...many, it('m1', '2026-09-01', null, { popAll: 1 })], sale: pricedSale, events: evData }, 20);
const evKinds = withEv.map((t) => t.kind);
check('イベント: 予約に初登場のあと・セールで人気の前に、近い順に2件', evKinds.join().includes('entry,event,event,salehot') && withEv.filter((t) => t.kind === 'event').map((t) => t.title).join() === '架空ゆめか,見本はるな', evKinds.join());
const evFull = T.buildTopics({ ...ctx, items: [...many, it('m1', '2026-09-01', null, { popAll: 1 })], sale: pricedSale, events: evData, roundup: { week_start: '2026-09-28', week_end: '2026-10-04', lead: 'x', picks: [], written: TODAY } });
const evCut = T.buildTopics({ ...ctx, items: [...many, it('m1', '2026-09-01', null, { popAll: 1 })], sale: pricedSale, events: evData, roundup: { week_start: '2026-09-28', week_end: '2026-10-04', lead: 'x', picks: [], written: TODAY } }, 9);
check('イベント: データが無ければ出さない・いろいろな種類がそろって10件・入りきらないときは、まず2つ目の急上昇を外す', !topics.some((t) => t.kind === 'event')
  && evFull.length === T.TOPICS_LIMIT && evCut.filter((t) => t.kind === 'rise').length === 1 && evCut.filter((t) => t.kind === 'event').length === 2, evFull.map((t) => t.kind).join());
const shownTitles = topics.flatMap((t) => [t, ...(t.alt ? [t.alt] : [])]).filter((t) => t.kind !== 'actress' && t.kind !== 'sale' && t.kind !== 'salenew').map((t) => t.title);
check('同じ作品は2回出さない（繰り上げの作品も含めて）', new Set(shownTitles).size === shownTitles.length, shownTitles.join());
check('人気の女優・デビュー作の話題は出さない（トップの「いま人気の女優」・発売中の新作の「今週のデビュー作」の欄で出す）', !topics.some((t) => t.kind === 'actress' || t.kind === 'debut'));
check('数が多いときは、まず2つ目の急上昇を外す', T.buildTopics(ctx, 5).map((t) => t.kind).join() === 'rise,today,upcoming,entry,salenew' && T.buildTopics(ctx, 3).length === 3);

const withSkipVrOff = T.buildTopics({ ...ctx, skipVrOff: new Set(['r4']) }).find((t) => t.kind === 'rise' && t.vr);
check('VR作品を隠したときにTOP3に出る作品（skipVrOff）は、繰り上げに使わない', withSkipVrOff && withSkipVrOff.alt?.title !== '作品 r4', JSON.stringify(withSkipVrOff?.alt));
const allVr = T.buildTopics({ ...ctx, items: many.map((i) => (i.cid === 'n1' ? i : { ...i, vr: i.cid.startsWith('r') ? true : i.vr })) }).filter((t) => t.kind === 'rise');
check('代わりになるVRでない作品が無ければ、繰り上げは付かない（VR作品を隠すと、その話題は消える）', allVr.every((t) => t.vr && !t.alt), JSON.stringify(allVr.map((t) => [t.title, t.alt?.title])));

const lowToday = T.buildTopics({ ...ctx, items: [...many.map((i) => (i.cid === 'n1' ? { ...i, vr: true } : i)), it('n2', TODAY, 160, { actress: ['星子'] })] }).find((t) => t.kind === 'today');
check('きょう発売の繰り上げは、新着の人気TOP100の外からも探す（きょう発売の上位がVRばかりの日）', lowToday?.vr === true && lowToday.alt?.title === '作品 n2' && lowToday.alt.text === '星子｜M｜新着の人気順 160位', JSON.stringify(lowToday?.alt));

console.log('\n■ いま人気の女優（hotActresses）');
const hotItems = [
  it('h1', '2026-10-03', 1, { actress: ['花子'] }),
  it('h2', '2026-10-03', 2, { actress: ['月子', '星子'] }),
  it('h3', '2026-10-02', 3, { actress: ['月子'], vr: true }),
  it('h4', '2026-10-02', 50, { actress: ['花子'] }),
  it('h5', '2026-10-01', 4, { actress: ['a', 'b', 'c', 'd', 'e'] }), // 5人出ている作品（オムニバス）は数えない
  it('h6', '2026-10-01', 120, { actress: ['海子'] }), // TOP100の外は数えない
  it('h7', '2026-09-01', 5, { actress: ['空子'] }), // 1週間より前の発売は数えない
];
const hot = T.hotActresses(hotItems, TODAY);
check('人気の高い作品に多く出ている人が上（101−順位の点を足す）・3人まで', hot.map((r) => r.name).join() === '月子,花子,星子' && hot[0].score === 99 + 98 && hot[1].score === 100 + 51, JSON.stringify(hot.map((r) => [r.name, r.score])));
check('本数といちばん上の順位', hot[0].count === 2 && hot[0].best === 2 && hot[1].count === 2 && hot[1].best === 1 && hot[2].count === 1);
check('出演者が5人以上の作品・TOP100の外・1週間より前の作品は数えない', !T.hotActresses(hotItems, TODAY, { limit: 10 }).some((r) => ['a', '海子', '空子'].includes(r.name)));
const hotNoVr = T.hotActresses(hotItems, TODAY, { excludeVr: true });
check('VR作品を隠すときの並び: VR作品を数えない', hotNoVr.map((r) => r.name).join() === '花子,星子,月子' && hotNoVr[1].score === 99, JSON.stringify(hotNoVr.map((r) => [r.name, r.score])));
check('人気の作品が無いときは空', T.hotActresses([], TODAY).length === 0 && T.HOT_LIMIT === 3 && T.HOT_MAX_CAST === 4);
check('顔写真がある人だけ（順位は繰り上がる）', T.hotActresses(hotItems, TODAY, { hasFace: (n) => n !== '月子' }).map((r) => r.name).join() === '花子,星子');

console.log('\n■ 人気のジャンル（hotGenres）');
const gItems = [
  it('g1', '2026-10-03', 1, { genres: ['巨乳', '単体作品'], vr: true }),
  it('g2', '2026-10-03', 2, { genres: ['巨乳', '人妻・主婦'] }),
  it('g3', '2026-10-02', 3, { genres: ['人妻・主婦', '熟女'] }),
  it('g4', '2026-10-02', 4, { genres: ['熟女', 'OL'] }),
  it('g5', '2026-10-01', 90, { genres: ['OL'] }),
  it('g6', '2026-10-01', 120, { genres: ['痴女'] }), // TOP100の外は数えない
  it('g7', '2026-09-01', 5, { genres: ['痴女'] }), // 1週間より前は数えない
];
const allowed = new Set(['巨乳', '人妻・主婦', '熟女', 'OL', '痴女']);
const hg = T.hotGenres(gItems, TODAY, { allowed });
check('いま人気の女優と同じ点（101−順位）をジャンルごとに足して、上から3つ。決めた一覧のジャンルだけ（単体作品などは数えない）', hg.map((g) => g.name).join() === '巨乳,人妻・主婦,熟女' && hg[0].score === 100 + 99 && hg[0].count === 2, JSON.stringify(hg.map((g) => [g.name, g.score])));
check('表紙は、そのジャンルでいちばん点の高い作品（VRでない作品を先に）', hg[0].top.cid === 'g2' && hg[1].top.cid === 'g2' && hg[2].top.cid === 'g3');
check('TOP100の外・1週間より前の作品は数えない・人気の作品が無ければ空', !T.hotGenres(gItems, TODAY, { allowed, limit: 10 }).some((g) => g.name === '痴女') && T.hotGenres([], TODAY, { allowed }).length === 0 && T.HOT_GENRE_LIMIT === 3 && T.HOT_GENRE_SKIP.includes('ベスト・総集編'));

console.log('\n■ 今週のデビュー作（weekDebuts）');
const deb = [
  it('d1', '2026-10-05', 30, { genres: ['デビュー作品'] }), it('d2', '2026-10-01', 5, { genres: ['デビュー作品', '単体作品'] }),
  it('d3', '2026-09-29', null, { genres: ['デビュー作品'] }), it('d4', '2026-09-28', 1, { genres: ['デビュー作品'] }), // d4 は8日前（入れない）
  it('d5', '2026-10-06', 2, { genres: ['デビュー作品'] }), // 予約（まだ発売前）は入れない
  it('d6', '2026-10-04', 3), // デビュー作品でない
];
check('きょうまでの7日間に発売された「デビュー作品」を、新着の人気順に（順位の無い作品はあと）', T.weekDebuts(deb, TODAY).map((i) => i.cid).join() === 'd2,d1,d3', T.weekDebuts(deb, TODAY).map((i) => i.cid).join());
check('出すのは3本・データは差し替え用に6本まで', T.DEBUT_SHOWN === 3 && T.DEBUT_DATA === 6 && T.weekDebuts(deb, TODAY, 1).length === 1);

console.log('\n■ 誕生日の近い女優（birthdaySoon）');
check('誕生日まで何日か（きょうは0・過ぎていたら来年）', T.daysUntilBirthday('10-07', TODAY) === 2 && T.daysUntilBirthday('10-05', TODAY) === 0 && T.daysUntilBirthday('10-04', TODAY) === 364 && T.daysUntilBirthday('01-02', '2026-12-31') === 2);
check('2月29日生まれは、うるう年でない年は2月28日・形が違えば null', T.daysUntilBirthday('02-29', '2026-02-27') === 1 && T.daysUntilBirthday('02-29', '2028-02-27') === 2 && T.daysUntilBirthday('', TODAY) === null && T.daysUntilBirthday('1999-10-07', TODAY) === null);
const bdItems = [it('b1', '2026-09-01', null, { actress: ['花子'] }), it('b2', '2026-09-02', null, { actress: ['花子', '月子'] }), it('b3', '2026-09-03', null, { actress: ['星子'] }), it('b4', '2026-09-04', null, { actress: ['海子'] }), it('b5', '2026-09-05', null, { actress: ['空子'] })];
const births = { 花子: '10-07', 月子: '10-05', 星子: '10-07', 海子: '10-20', 空子: '10-06', 雪子: '10-05' };
const bd = T.birthdaySoon(bdItems, TODAY, { birthOf: (n) => births[n] ?? '', hasFace: (n) => n !== '空子' });
check('このサイトに作品があり・顔写真がある人だけ。近い順（同じ日なら作品の多い人から）・14日のうち', bd.map((r) => `${r.name}${r.days}`).join() === '月子0,花子2,星子2' && !bd.some((r) => ['空子', '海子', '雪子'].includes(r.name)), JSON.stringify(bd));
check('3人まで・誕生日が分からない人は入れない', T.BIRTHDAY_LIMIT === 3 && T.birthdaySoon(bdItems, TODAY, { birthOf: () => '', hasFace: () => true }).length === 0);

const roundup = { week_start: '2026-09-28', week_end: '2026-10-04', lead: 'まとめの書き出し。'.repeat(10), picks: [{ cid: 'n1', note: 'x' }], written: TODAY };
const withWeekly = T.buildTopics({ ...ctx, roundup }, 20);
const weekly = withWeekly.find((t) => t.kind === 'weekly');
check('週のまとめ: 書かれてから2日のあいだだけ。まとめ記事へ', weekly && weekly.title === '9月28日〜10月4日の新作まとめ' && weekly.href === '/weekly/2026-09-28/' && Array.from(weekly.text).length <= 46);
check('週のまとめ: 3日たったら出さない・未来の日付も出さない', !T.buildTopics({ ...ctx, roundup: { ...roundup, written: '2026-10-02' } }, 20).some((t) => t.kind === 'weekly') && !T.buildTopics({ ...ctx, roundup: { ...roundup, written: '2026-10-07' } }, 20).some((t) => t.kind === 'weekly'));

const bare = T.buildTopics({ items: [], today: TODAY, popularity: normalizePopularity(null), todayData: empty, sale: normalizeSale(null), linkOf });
check('データが何も無いときは空（落ちない）', Array.isArray(bare) && bare.length === 0);
const noPrev = T.buildTopics({ ...ctx, popularity: normalizePopularity({ date: TODAY }), todayData: { ...td, prevUpcoming: new Set() } });
check('前の日の順位が無い日は、急上昇・予約に初登場を出さない', !noPrev.some((t) => t.kind === 'rise' || t.kind === 'entry'));
check('評価の言葉を書かない（データで決まった形の文だけ）', !topics.some((t) => /おすすめ|話題作|必見|最高傑作|大人気/.test(t.title + t.text)));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
