// 発売日カレンダー（.ics）の部品（画面に依存しない）。
// iPad・iPhone・Googleカレンダーなどで「購読」すると、発売日が自動でカレンダーに入る（毎日の更新に合わせて、カレンダー側が定期的に読み直す）。
// カレンダーの予定の「題名」には、作品のタイトルを入れない（カレンダーを人に見られても困らないように）。タイトルと品番・リンクは、予定の詳細（説明）に入れる。
import { SITE_URL, addDays, itemPagePath, isDay } from './items.js';
import { productCode } from './facts.js';
import { isMinorTitle } from './gacha.js';
import { endLabel } from './sale.js';
import { createHash } from 'node:crypto';

export const CALENDAR_PATH = '/calendar/';
export const UPCOMING_ICS_PATH = '/calendar/upcoming.ics';
export const actressIcsPath = (slug) => `/calendar/actress/${slug}.ics`;
export const makerIcsPath = (slug) => `/calendar/maker/${slug}.ics`;
export const CALENDAR_PAST_DAYS = 14; // 発売日がこの日数前までの作品も入れる（購読した直後に「最近出たもの」も見えるように）
export const CALENDAR_MAX_EVENTS = 200;
const ALARM_HOURS = 9; // 発売日の朝9時に通知（カレンダー側の設定で通知が出ないこともある）

/** https://example.com + /calendar/a.ics → webcal://example.com/calendar/a.ics（タップするとカレンダーアプリが「購読」を開く） */
export const webcalUrl = (path, siteUrl = SITE_URL) => siteUrl.replace(/^https?:/, 'webcal:') + path;

/** iCalendar の文章の記号（\ ; , 改行）を、決まりどおりに書き換える。制御文字は取り除く */
export function escapeIcsText(text) {
  return String(text)
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '')
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r\n|\r|\n/g, '\\n');
}

/** 1行を、75バイトずつに折り返す（2行目以降は先頭に空白1つ）。日本語の文字の途中では切らない */
export function foldIcsLine(line) {
  const enc = new TextEncoder();
  const rows = [];
  let current = '';
  let size = 0;
  for (const ch of line) {
    const n = enc.encode(ch).length;
    const limit = rows.length === 0 ? 75 : 74; // 2行目以降は、先頭の空白の1バイトぶんを引く
    if (size + n > limit) {
      rows.push(current);
      current = ch;
      size = n;
    } else {
      current += ch;
      size += n;
    }
  }
  rows.push(current);
  return rows.join('\r\n ');
}

const compact = (day) => day.replace(/-/g, '');
const nextDay = (day) => compact(addDays(day, 1));

/**
 * カレンダーに入れる作品: 発売日が（今日 − CALENDAR_PAST_DAYS日）以降のもの。発売日の早い順。
 * 多すぎるときは、これから発売される作品（今日以降）を先に残し、枠が余れば、最近発売された作品を新しい方から入れる
 * （古い方から入れると、遠い先の予約が切れてしまうため）。
 */
export function calendarItems(items, today, limit = CALENDAR_MAX_EVENTS) {
  const from = addDays(today, -CALENDAR_PAST_DAYS);
  const sorted = items
    .filter((i) => i.dateKey >= from)
    .sort((a, b) => a.dateKey.localeCompare(b.dateKey) || a.cid.localeCompare(b.cid));
  const upcoming = sorted.filter((i) => i.dateKey >= today).slice(0, limit);
  const past = sorted.filter((i) => i.dateKey < today);
  const room = limit - upcoming.length;
  return [...(room > 0 ? past.slice(Math.max(0, past.length - room)) : []), ...upcoming];
}

/** 予定の題名（作品タイトルは入れない）。subject は出演者名・メーカー名。無ければ作品の出演者→メーカーから */
export function eventSummary(item, subject = '') {
  const who = subject || item.actress[0] || (item.maker !== '不明' ? item.maker : '');
  return who ? `【発売】${who}の新作` : '【発売】FANZAの新作';
}

/**
 * .ics の中身（改行は CRLF）。
 * calName: カレンダーの名前 / items: 作品（normalizeItems の形）/ today: 今日(YYYY-MM-DD) / subject: 題名に入れる名前（省略可）
 */
export function buildIcs({ calName, items, today, subject = '', siteUrl = SITE_URL }) {
  const host = new URL(siteUrl).host;
  const stamp = `${compact(today)}T000000Z`; // 同じ日なら同じ値（毎回の差分を増やさない）
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    `PRODID:-//${host}//JA`,
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    `X-WR-CALNAME:${escapeIcsText(calName)}`,
    'X-WR-TIMEZONE:Asia/Tokyo',
    'REFRESH-INTERVAL;VALUE=DURATION:P1D',
    'X-PUBLISHED-TTL:P1D',
  ];
  for (const item of calendarItems(items, today)) {
    if (!isDay(item.dateKey)) continue;
    const summary = eventSummary(item, subject);
    const code = productCode(item.cid); // 作品ページと同じ品番（作れないときは作品ID）
    const description = `${item.title}\n${code ? `品番: ${code}` : `作品ID: ${item.cid}`}\n${siteUrl}${itemPagePath(item)}`;
    lines.push(
      'BEGIN:VEVENT',
      `UID:${item.cid}@${host}`,
      `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${compact(item.dateKey)}`,
      `DTEND;VALUE=DATE:${nextDay(item.dateKey)}`,
      `SUMMARY:${escapeIcsText(summary)}`,
      `DESCRIPTION:${escapeIcsText(description)}`,
      `URL:${siteUrl}${itemPagePath(item)}`,
      'TRANSP:TRANSPARENT',
    );
    if (item.dateKey >= today) {
      lines.push('BEGIN:VALARM', 'ACTION:DISPLAY', `DESCRIPTION:${escapeIcsText(summary)}`, `TRIGGER:PT${ALARM_HOURS}H`, 'END:VALARM');
    }
    lines.push('END:VEVENT');
  }
  lines.push('END:VCALENDAR');
  return lines.map(foldIcsLine).join('\r\n') + '\r\n';
}

// ---------- セールのカレンダー（/calendar/sale.ics。issue #239。2026-11-07） ----------
// 動画のセール特集・売り場のセール・10円セールの「始まり〜終わり」を、1つのセール＝1つの予定にして入れる（時刻は日本時間）。
// 新しく始まったセールの RSS（/sale/feed.xml。lib/feed.js の saleFeedItems）も、同じ並べ方（saleEvents）を使う。
export const SALE_ICS_PATH = '/calendar/sale.ics';
export const SALE_CALENDAR_MAX = 50; // 多すぎるときは、終わりの近い順にここまで
const SALE_TIME = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;

/** 日本時間のいま "YYYY-MM-DD HH:MM"（ビルドするサーバーの時刻設定に左右されない） */
export const jstNow = (nowMs = Date.now()) => new Date(nowMs + 9 * 3600 * 1000).toISOString().slice(0, 16).replace('T', ' ');

/**
 * カレンダー・RSS に入れるセール。sources: [{ key（売り場の印）, floor（売り場の名前）, title, begin, end（"YYYY-MM-DD HH:MM"）, path（このサイトのページ）, count（本数） }]。
 * 始まりと終わりの時刻が分からない・終わった（now より前）・未成年を連想させる名前のものは入れない。
 * 同じ売り場の同じ名前は1つ（早く終わるほう）。売り場がちがえば別の予定。終わりの近い順に limit まで
 */
export function saleEvents(sources, now, limit = SALE_CALENDAR_MAX) {
  const map = new Map();
  for (const s of Array.isArray(sources) ? sources : []) {
    const title = String(s?.title ?? '').trim();
    if (!title || !s.key || !s.floor || !SALE_TIME.test(String(s.begin)) || !SALE_TIME.test(String(s.end)) || s.begin >= s.end || s.end <= now || isMinorTitle(title)) continue;
    const id = `${s.key}\u0000${title}`;
    const prev = map.get(id);
    if (prev && prev.end <= s.end) continue;
    const hash = createHash('sha1').update(`${title}\u0000${s.begin}`).digest('hex').slice(0, 12);
    map.set(id, { id: `${s.key}-${hash}`, key: s.key, floor: s.floor, title, begin: s.begin, end: s.end, path: s.path || '/sale/', count: Number.isInteger(s.count) && s.count > 0 ? s.count : 0 });
  }
  return [...map.values()]
    .sort((a, b) => a.end.localeCompare(b.end) || a.begin.localeCompare(b.begin) || a.id.localeCompare(b.id))
    .slice(0, limit);
}

/** 予定の名前: 「セールの名前（FANZA動画）」 */
export const saleEventSummary = (ev) => `${ev.title}（${ev.floor}）`;

/** "2026-11-04 00:10" → "20261104T001000" */
const icsTime = (t) => `${t.slice(0, 10).replace(/-/g, '')}T${t.slice(11, 13)}${t.slice(14, 16)}00`;

/** セールのカレンダーの .ics の中身（改行は CRLF）。events は saleEvents の答え */
export function buildSaleIcs({ calName, events, today, siteUrl = SITE_URL }) {
  const host = new URL(siteUrl).host;
  const stamp = `${compact(today)}T000000Z`;
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    `PRODID:-//${host}//JA`,
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    `X-WR-CALNAME:${escapeIcsText(calName)}`,
    'X-WR-TIMEZONE:Asia/Tokyo',
    'REFRESH-INTERVAL;VALUE=DURATION:P1D',
    'X-PUBLISHED-TTL:P1D',
    'BEGIN:VTIMEZONE',
    'TZID:Asia/Tokyo',
    'BEGIN:STANDARD',
    'DTSTART:19700101T000000',
    'TZOFFSETFROM:+0900',
    'TZOFFSETTO:+0900',
    'TZNAME:JST',
    'END:STANDARD',
    'END:VTIMEZONE',
  ];
  for (const ev of events) {
    const url = siteUrl + ev.path;
    const description = [`${endLabel(ev.end)}まで`, ev.count ? `このサイトの作品: ${ev.count.toLocaleString('ja-JP')}本` : '', url].filter(Boolean).join('\n');
    lines.push(
      'BEGIN:VEVENT',
      `UID:sale-${ev.id}@${host}`,
      `DTSTAMP:${stamp}`,
      `DTSTART;TZID=Asia/Tokyo:${icsTime(ev.begin)}`,
      `DTEND;TZID=Asia/Tokyo:${icsTime(ev.end)}`,
      `SUMMARY:${escapeIcsText(saleEventSummary(ev))}`,
      `DESCRIPTION:${escapeIcsText(description)}`,
      `URL:${url}`,
      'TRANSP:TRANSPARENT',
      'END:VEVENT',
    );
  }
  lines.push('END:VCALENDAR');
  return lines.map(foldIcsLine).join('\r\n') + '\r\n';
}
