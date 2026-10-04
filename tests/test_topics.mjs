// トップの「きょうの数字」「きょうの新着人気TOP3」「きょうの話題」の部品（site/src/lib/topics.js）のテスト。実行: node tests/test_topics.mjs
import * as T from '../site/src/lib/topics.js';
import { normalizePopularity } from '../site/src/lib/popularity.js';
import { normalizeSale } from '../site/src/lib/sale.js';
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
  ],
  prev_upcoming: ['up9', 7],
};
const td = T.normalizeToday(rawToday);
check('日付・本数を読む（形の違う行は捨てる）', td.date === TODAY && td.daily.length === 2 && td.upcomingTotal === 3402, JSON.stringify(td.daily));
check('予約の人気順: タイトル・順位・FANZAのリンクがある作品だけ（リンクはFANZAのhttpsだけ・画像もFANZAだけ）',
  td.upcoming.map((u) => u.cid).join() === 'up1,up2' && td.upcoming[1].image_url === '' && td.upcoming[0].title === '予約の作品', td.upcoming.map((u) => u.cid).join());
check('出演者は文字だけ・メーカーが空なら「不明」・VRの印（v:1）', td.upcoming[0].actress.join() === '花子' && td.upcoming[0].maker === '不明' && td.upcoming[0].vr === true && td.upcoming[1].vr === false);
check('前の日の予約の人気順は、作品IDの文字だけ', td.prevUpcoming.has('up9') && td.prevUpcoming.size === 1);
const empty = T.normalizeToday(null);
check('無い・形が違うときは空（落ちない）', empty.date === '' && empty.daily.length === 0 && empty.upcomingTotal === null && empty.upcoming.length === 0 && T.normalizeToday([1]).date === '');

console.log('\n■ きょうの数字（todayStats）');
const st = T.todayStats(T.normalizeToday({ date: TODAY, daily: [{ d: '2026-10-03', n: 100 }, { d: '2026-10-04', n: 250 }, { d: TODAY, n: 200 }], upcoming_total: 50 }), TODAY);
check('きょう発売・期間の合計・予約受付中', st.today === 200 && st.week === 550 && st.days === 3 && st.upcoming === 50);
check('棒の高さは、いちばん多い日を1として・きょうの棒に印', st.bars[1].ratio === 1 && st.bars[0].ratio === 0.4 && st.bars[2].today && !st.bars[1].today && st.bars[2].label.wd === '月');
check('今日のデータでなければ出さない（古い数字を「きょう」として出さない）', T.todayStats(td, '2026-10-06') === null && T.todayStats(T.normalizeToday({ date: TODAY, daily: [{ d: '2026-10-04', n: 1 }] }), TODAY) === null && T.todayStats(empty, TODAY) === null);
check('予約の本数が無いときは null（画面で出さない）', T.todayStats(T.normalizeToday({ date: TODAY, daily: [{ d: TODAY, n: 3 }] }), TODAY).upcoming === null);
check('全部0本でも落ちない', T.todayStats(T.normalizeToday({ date: TODAY, daily: [{ d: TODAY, n: 0 }] }), TODAY).bars[0].ratio === 0);

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
  it('n1', TODAY, 7, { actress: ['月子'], maker: 'メーカーA' }), // きょう発売（前の日は無いので、急上昇には入れない）
  it('db', '2026-10-03', 9, { actress: ['新人'], genres: ['デビュー作品'] }),
  it('s1', '2026-09-01', null, { popAll: 5 }),
];
const pop = normalizePopularity({ date: TODAY, new: {}, prev_date: '2026-10-04', prev: { t1: 1, t2: 2, t3: 3, r1: 40, r3: 35 } });
const saleData = normalizeSale({
  date: TODAY,
  campaigns: [{ title: '週末セール', begin: '2026-10-01 00:00', end: '2026-10-06 23:59' }, { title: '長いセール', begin: '2026-10-01', end: '2026-10-30' }],
  items: [{ c: 's1', k: 0 }, { c: 'r3', k: 1 }],
});
const ctx = {
  items: many, today: TODAY, popularity: pop, todayData: td, sale: saleData, linkOf,
  actressPage: (n) => (n === '花子' ? '/actress/hanako/' : ''), faceOf: (n) => (n === '新人' ? 'https://pics.dmm.co.jp/face.jpg' : ''),
  skip: new Set(['t1', 't2', 't3']),
};
const topics = T.buildTopics(ctx);
const kinds = topics.map((t) => t.kind).join();
check('種類と順番: 急上昇 → きょう発売 → 予約の人気1位 → 予約に初登場 → デビュー作 → 人気の女優 → もうすぐ終わるセール', kinds === 'rise,rise,today,upcoming,entry,debut,actress,sale', kinds);
const rise = topics.filter((t) => t.kind === 'rise');
check('急上昇: 上がり幅の大きい順・前の日の順位から（圏外からも）。TOP3の作品・上がり幅の小さい作品・きょう発売の作品は入れない',
  rise.map((t) => t.text).join('/') === '新着の人気順 40位 → 4位/新着の人気順 圏外 → 6位', rise.map((t) => t.text).join('/'));
check('VR作品の話題には印（VR作品を隠すと消える）', rise[0].vr === false && rise[1].vr === true);
const tday = topics.find((t) => t.kind === 'today');
check('きょう発売: 出演者・メーカー・順位', tday.title === '作品 n1' && tday.text === '月子｜メーカーA｜新着の人気順 7位' && tday.href === '/item/n1/', tday.text);
const up = topics.find((t) => t.kind === 'upcoming');
check('予約の人気1位: 発売日と出演者', up.text === '10月8日発売｜花子' && up.vr === true);
const entry = topics.find((t) => t.kind === 'entry');
check('予約に初登場: 前の日の予約の人気順にいなかった作品（1位は別の話題に出したので、次の作品）', entry.title === '予約2' && entry.text === '予約の人気順 2位｜10月9日発売', entry.text);
const debut = topics.find((t) => t.kind === 'debut');
check('デビュー作: 出演者の名前と、顔写真（あれば）', debut.title === '新人のデビュー作' && debut.face === 'https://pics.dmm.co.jp/face.jpg');
const actress = topics.find((t) => t.kind === 'actress');
check('人気の女優: 新着の人気TOP100に2本以上。女優のページへ', actress.title === '花子' && actress.text === '新着の人気TOP100に出演作が2本｜最高4位' && actress.href === '/actress/hanako/' && actress.external === false, actress.text);
const sale = topics.find((t) => t.kind === 'sale');
check('もうすぐ終わるセール: 終わりが2日以内のキャンペーンだけ。セールのページへ・終わりの時刻（ブラウザが、すぎたら隠す）',
  sale.title === '週末セール' && sale.text === '10月6日 23:59まで｜1本がセール中' && sale.href === '/sale/' && sale.end === '2026-10-06T23:59:59+09:00', sale.text);
check('同じ作品は2回出さない', new Set(topics.filter((t) => t.kind !== 'actress' && t.kind !== 'sale').map((t) => t.title)).size === topics.length - 2);
check('数が多いときは、まず2つ目の急上昇を外す', T.buildTopics(ctx, 7).map((t) => t.kind).join() === 'rise,today,upcoming,entry,debut,actress,sale' && T.buildTopics(ctx, 3).length === 3);

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
