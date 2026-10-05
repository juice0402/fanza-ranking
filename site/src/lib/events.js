// イベント情報（所属事務所の公式サイトのイベントの一覧から。scripts/agency_events.py が毎日 data/events.json に保存する）の部品。
// 画面に依存しない（tests/test_events.mjs）。運営者の希望「女優さんのニュースとかイベント情報…新鮮な情報がほしい」（2026-10-05）。
// 使う所: きょうの話題の「イベント」（lib/topics.js）、イベント情報のページ（/event/）、出演者のページの「イベントの予定」。
// 情報は、その日の 0:05 ごろに事務所の一覧で見かけたもの。中止・変更がありうるので、画面には「○日時点」「くわしくは公式サイトで」を必ず添える。
import { AGENCIES } from './agencies.js';
import { isMinorTitle } from './gacha.js';
import { addDays, dateParts, daysBetween, isDay } from './items.js';

export const EVENT_PATH = '/event/';
// 種類（scripts/agency_events.py の KINDS と同じ並び。tests/test_events.mjs で突き合わせている）
export const EVENT_KINDS = ['サイン・撮影会', '撮影会', 'サイン会', '握手会', 'チェキ会', 'オフ会', 'トークイベント', '来店イベント', '配信', '誕生日イベント', '発売記念イベント', 'イベント'];
export const EVENT_DAYS = 60; // この日数先までのイベントを出す（scripts/agency_events.py の HORIZON_DAYS と同じ）
export const EVENT_TOPICS = 2; // きょうの話題に出すイベントの数
export const EVENT_TOPIC_DAYS = 14; // きょうの話題に出すのは、この日数のうちのイベントだけ
export const EVENT_ACTRESS_LIMIT = 5; // 出演者のページに出すイベントの数
const TITLE_MAX = 40;
const PLACE_MAX = 30;
const NAMES_MAX = 6;

/** 事務所の公式サイトの中のURLか（http・https。「https://capsule.bz.evil/」のような形は通さない） */
function onAgencySite(url, agency) {
  const s = String(url ?? '');
  return s.startsWith(agency.url) && /^https?:\/\//.test(s) && !/[\s"'<>\\]/.test(s);
}

/** 1つのイベントの、ページの中の印（id）。中身から決まる短い文字（同じイベントなら、毎日同じ） */
export function eventId(e) {
  const text = [e.date, e.time, e.names.join('|'), e.agency, e.url, e.place].join('\u0000');
  let h = 0x811c9dc5;
  for (const ch of text) {
    h ^= ch.codePointAt(0);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return `ev-${e.date.replace(/-/g, '')}-${h.toString(36)}`;
}

/**
 * events.json → { updated, rows: [{ id, date, time, names, agency（キー）, agencyName, kind, title, place, url }] }。
 * 形が違う行・知らない事務所・事務所のサイトの外のURL・知らない種類は捨てる。見出しが未成年を連想させるイベントは、念のため出さない（取得の側でも外している）
 */
export function normalizeEvents(raw) {
  const ok = raw && typeof raw === 'object' && !Array.isArray(raw);
  const rows = [];
  for (const r of ok && Array.isArray(raw.rows) ? raw.rows : []) {
    if (!r || typeof r !== 'object') continue;
    const agency = Object.prototype.hasOwnProperty.call(AGENCIES, r.agency) ? AGENCIES[r.agency] : null;
    const names = Array.isArray(r.names) ? [...new Set(r.names.filter((n) => typeof n === 'string' && n.trim()).map((n) => n.trim()))].slice(0, NAMES_MAX) : [];
    const title = typeof r.title === 'string' ? r.title.trim() : '';
    const place = typeof r.place === 'string' ? r.place.trim() : '';
    if (!agency || !isDay(r.date) || names.length === 0 || !EVENT_KINDS.includes(r.kind) || !onAgencySite(r.url, agency)) continue;
    if (isMinorTitle(title) || isMinorTitle(place)) continue;
    const e = {
      date: r.date,
      time: /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(String(r.time ?? '')) ? r.time : '',
      names,
      agency: r.agency,
      agencyName: agency.name,
      kind: r.kind,
      title: Array.from(title).length <= TITLE_MAX + 1 ? title : '',
      place: Array.from(place).length <= PLACE_MAX ? place : '',
      url: r.url,
    };
    rows.push({ id: eventId(e), ...e });
  }
  rows.sort((a, b) => a.date.localeCompare(b.date) || (a.time || '99:99').localeCompare(b.time || '99:99') || (a.names[0] < b.names[0] ? -1 : a.names[0] > b.names[0] ? 1 : 0));
  return { updated: ok && isDay(raw.updated) ? raw.updated : '', rows };
}

/** きょうから days 日先までのイベント（日付・時刻の順） */
export const upcomingEvents = (events, today, days = EVENT_DAYS) => events.rows.filter((e) => e.date >= today && e.date <= addDays(today, days));

/** 日付の見出し: きょう・あすは「きょう」「あす」を前に（「きょう 10月5日（月）」）。dayOnly: 日付だけ */
export function eventDayLabel(date, today, { dayOnly = false } = {}) {
  const p = dateParts(date);
  const md = `${p.m}月${p.d}日（${p.wd}）`;
  if (dayOnly || !isDay(today)) return md;
  const left = daysBetween(date, today);
  return left === 0 ? `きょう ${md}` : left === 1 ? `あす ${md}` : md;
}

/** 短い「いつ」: 「きょう 18:00〜」「あす」「10月31日（土）12:00〜」 */
export function eventWhen(e, today) {
  const left = isDay(today) ? daysBetween(e.date, today) : null;
  const p = dateParts(e.date);
  const day = left === 0 ? 'きょう' : left === 1 ? 'あす' : `${p.m}月${p.d}日（${p.wd}）`;
  return `${day}${e.time ? ` ${e.time}〜` : ''}`;
}

/** 日付ごとのまとまり [{ date, events }] */
export function eventsByDay(events) {
  const groups = [];
  for (const e of events) {
    if (groups.at(-1)?.date !== e.date) groups.push({ date: e.date, events: [] });
    groups.at(-1).events.push(e);
  }
  return groups;
}

/** 出演者の名前 → その人のイベント（日付の順） */
export function eventsByName(events) {
  const map = new Map();
  for (const e of events) for (const n of e.names) map.set(n, [...(map.get(n) ?? []), e]);
  return map;
}

/** 出る人の短い1行（「Aさん・Bさん ほか2名」の形ではなく、名前を並べる。3人をこえたら「ほか○名」） */
export function eventCast(names, max = 2) {
  return names.length > max ? `${names.slice(0, max).join('・')} ほか${names.length - max}名` : names.join('・');
}

/**
 * きょうの話題に出すイベント: きょうから EVENT_TOPIC_DAYS 日のうちのイベントを、近い順に（同じ日なら、顔写真のある人のイベントを先に）。
 * 同じ人のイベントは1つだけ。faceOf(name) → 顔写真のURL | ''、coverOf(name) → その人の作品の表紙 | ''
 * [{ kind: 'event', label, title, text, image, face, vr: false, href, external: false }]
 */
export function eventTopics(events, today, { faceOf = () => '', coverOf = () => '', limit = EVENT_TOPICS, days = EVENT_TOPIC_DAYS } = {}) {
  const faceIn = (e) => e.names.map((n) => faceOf(n)).find(Boolean) || '';
  const near = upcomingEvents(events, today, days - 1)
    .map((e) => ({ e, face: faceIn(e) }))
    .sort((a, b) => a.e.date.localeCompare(b.e.date) || (a.face ? 0 : 1) - (b.face ? 0 : 1) || (a.e.time || '99:99').localeCompare(b.e.time || '99:99'));
  const used = new Set();
  const out = [];
  for (const { e, face } of near) {
    if (out.length >= limit) break;
    if (e.names.every((n) => used.has(n))) continue;
    e.names.forEach((n) => used.add(n));
    out.push({
      kind: 'event',
      label: 'イベント',
      title: eventCast(e.names),
      text: [eventWhen(e, today), e.kind === 'イベント' ? '' : e.kind, e.place].filter(Boolean).join('｜'), // 札が「イベント」なので、種類が「イベント」なら書かない
      image: face ? '' : e.names.map((n) => coverOf(n)).find(Boolean) || '',
      face,
      vr: false,
      href: `${EVENT_PATH}#${e.id}`,
      external: false,
    });
  }
  return out;
}
