// 女優のイベント情報の部品（site/src/lib/events.js）のテスト。実行: node tests/test_events.mjs
// 名前は、どれも作った名前
import fs from 'node:fs';
import * as V from '../site/src/lib/events.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

const TODAY = '2026-10-05';

console.log('■ Python の道具（scripts/agency_events.py）と同じ決まり');
const py = fs.readFileSync(new URL('../scripts/agency_events.py', import.meta.url), 'utf-8');
const pyKinds = [...py.slice(py.indexOf('KINDS = ['), py.indexOf('KIND_NAMES')).matchAll(/\("([^"]+)", r"/g)].map((m) => m[1]);
check('種類の一覧と並びが KINDS と同じ（最後は「イベント」）', JSON.stringify([...pyKinds, 'イベント']) === JSON.stringify(V.EVENT_KINDS), JSON.stringify(pyKinds));
check('出す日数が HORIZON_DAYS と同じ', new RegExp(`HORIZON_DAYS = ${V.EVENT_DAYS}\\b`).test(py));

console.log('\n■ events.json の読み方');
const raw = {
  updated: TODAY,
  rows: [
    { date: '2026-10-10', time: '18:00', names: ['架空ゆめか', '架空ゆめか', ' '], agency: 'tpowers', kind: '撮影会', title: '架空ゆめか 撮影会', place: '見本スタジオ', url: 'https://www.t-powers.co.jp/event/1/', seen: TODAY },
    { date: '2026-10-06', names: ['見本はるな'], agency: 'esflat', kind: 'イベント', url: 'http://www.style-1.jp/2026/10/01/a/', seen: TODAY },
    { date: '2026-10-06', time: '25:00', names: ['見本はるな'], agency: 'capsule', kind: 'オフ会', url: 'https://capsule.bz/a/', seen: TODAY },
    { date: '2026-10-07', names: ['なりすまし'], agency: 'tpowers', kind: 'イベント', url: 'https://www.t-powers.co.jp.evil.example/x', seen: TODAY },
    { date: '2026-10-07', names: ['別のサイト'], agency: 'tpowers', kind: 'イベント', url: 'https://www.av-event.jp/event/1/', seen: TODAY },
    { date: '2026-10-07', names: ['知らない事務所'], agency: 'evil', kind: 'イベント', url: 'https://evil.example/', seen: TODAY },
    { date: '2026-10-07', names: ['知らない種類'], agency: 'tpowers', kind: '飲み会', url: 'https://www.t-powers.co.jp/event/', seen: TODAY },
    { date: '2026-10-07', names: [], agency: 'tpowers', kind: 'イベント', url: 'https://www.t-powers.co.jp/event/', seen: TODAY },
    { date: '2026-10-07', names: ['見本みき'], agency: 'tpowers', kind: '撮影会', title: '制服撮影会', url: 'https://www.t-powers.co.jp/event/', seen: TODAY },
    { date: 'x', names: ['見本みき'], agency: 'tpowers', kind: 'イベント', url: 'https://www.t-powers.co.jp/event/', seen: TODAY },
  ],
};
const ev = V.normalizeEvents(raw);
check('形の違う行・知らない事務所・事務所のサイトの外（なりすましの形も）・知らない種類・名前の無い行・未成年を連想させる見出しは捨てる',
  ev.rows.map((e) => e.names[0]).join() === '見本はるな,見本はるな,架空ゆめか', ev.rows.map((e) => e.names[0]).join());
check('日付・時刻の順（時刻の無いイベントはその日のあと）・同じ名前は1つ・時刻の形が違えば空・事務所の名前', ev.rows.find((e) => e.agency === 'capsule').time === '' && ev.rows[2].names.length === 1
  && ev.rows[2].agencyName === 'ティーパワーズ' && ev.rows[2].time === '18:00' && ev.updated === TODAY, JSON.stringify(ev.rows));
check('http のままの事務所のサイト（エスフラート）も、その事務所のサイトの中なら通す', ev.rows.some((e) => e.agency === 'esflat'));
check('行の印（id）は中身から決まる（同じイベントなら毎日同じ・ほかのイベントと違う）',
  ev.rows[2].id === V.normalizeEvents(raw).rows[2].id && new Set(ev.rows.map((e) => e.id)).size === ev.rows.length && /^ev-20261010-[a-z0-9]+$/.test(ev.rows[2].id), ev.rows[2].id);
check('無い・形が違うときは空', V.normalizeEvents(null).rows.length === 0 && V.normalizeEvents([1]).rows.length === 0 && V.normalizeEvents({ rows: 'x' }).updated === '');

console.log('\n■ 日付の出し方');
check('日付の見出し: きょう・あすは前に付ける', V.eventDayLabel(TODAY, TODAY) === 'きょう 10月5日（月）' && V.eventDayLabel('2026-10-06', TODAY) === 'あす 10月6日（火）'
  && V.eventDayLabel('2026-10-10', TODAY) === '10月10日（土）' && V.eventDayLabel(TODAY, TODAY, { dayOnly: true }) === '10月5日（月）');
check('短い「いつ」', V.eventWhen({ date: TODAY, time: '18:00' }, TODAY) === 'きょう 18:00〜' && V.eventWhen({ date: '2026-10-06', time: '' }, TODAY) === 'あす'
  && V.eventWhen({ date: '2026-10-31', time: '12:00' }, TODAY) === '10月31日（土） 12:00〜');
check('きょうから60日先まで', V.upcomingEvents({ rows: [{ date: '2026-10-04' }, { date: TODAY }, { date: '2026-12-04' }, { date: '2026-12-05' }] }, TODAY).map((e) => e.date).join() === `${TODAY},2026-12-04`);
check('日付ごとのまとまり・名前ごとのイベント', V.eventsByDay(ev.rows).map((g) => `${g.date}:${g.events.length}`).join() === '2026-10-06:2,2026-10-10:1'
  && V.eventsByName(ev.rows).get('見本はるな').length === 2 && !V.eventsByName(ev.rows).has('なりすまし'));
check('出る人の1行（3人をこえたら「ほか○名」）', V.eventCast(['A', 'B']) === 'A・B' && V.eventCast(['A', 'B', 'C', 'D']) === 'A・B ほか2名');

console.log('\n■ きょうの話題のイベント');
const mk = (date, names, extra = {}) => ({ date, time: '', names, agency: 'tpowers', kind: 'イベント', url: 'https://www.t-powers.co.jp/event/', ...extra });
const list = V.normalizeEvents({
  rows: [
    mk('2026-10-08', ['顔なし子'], { kind: '撮影会', place: '見本スタジオ', time: '12:00' }),
    mk('2026-10-08', ['顔あり子'], { kind: 'サイン会' }),
    mk('2026-10-09', ['顔あり子'], { kind: 'オフ会' }),
    mk('2026-10-30', ['遠い子']),
    mk('2026-10-03', ['すぎた子']),
  ],
});
const faceOf = (n) => (n === '顔あり子' ? 'https://pics.dmm.co.jp/mono/actjpgs/face.jpg' : '');
const coverOf = (n) => (n === '顔なし子' ? 'https://pics.dmm.co.jp/digital/video/x/xpl.jpg' : '');
const tps = V.eventTopics(list, TODAY, { faceOf, coverOf });
check('近い順・同じ日なら顔写真のある人を先に・同じ人は1つ・14日より先とすぎたイベントは出さない', tps.map((t) => t.title).join() === '顔あり子,顔なし子', tps.map((t) => t.title).join());
check('札は「イベント」・文は「いつ｜種類｜会場」・イベント情報のページの、その行へ（サイトの中）', tps[1].label === 'イベント' && tps[1].text === '10月8日（木） 12:00〜｜撮影会｜見本スタジオ'
  && tps[1].href === `/event/#${list.rows.find((e) => e.names[0] === '顔なし子').id}` && tps[1].external === false && tps[1].vr === false, JSON.stringify(tps[1]));
check('種類が「イベント」なら文に書かない（札と同じなので）', V.eventTopics(V.normalizeEvents({ rows: [mk('2026-10-06', ['架空ゆめか'], { place: '見本店' })] }), TODAY)[0].text === 'あす｜見本店');
check('画像は顔写真（無ければ、その人の作品の表紙）', tps[0].face && !tps[0].image && !tps[1].face && tps[1].image === coverOf('顔なし子'));
check('評価の言葉を書かない', !tps.some((t) => /おすすめ|話題|必見|大人気|注目/.test(t.title + t.text)));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
