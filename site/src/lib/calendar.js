// 発売日カレンダー（.ics）の部品（画面に依存しない）。
// iPad・iPhone・Googleカレンダーなどで「購読」すると、発売日が自動でカレンダーに入る（毎日の更新に合わせて、カレンダー側が定期的に読み直す）。
// カレンダーの予定の「題名」には、作品のタイトルを入れない（カレンダーを人に見られても困らないように）。タイトルと品番・リンクは、予定の詳細（説明）に入れる。
import { SITE_URL, itemPath, isDay } from './items.js';

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
const nextDay = (day) => compact(new Date(Date.UTC(+day.slice(0, 4), +day.slice(5, 7) - 1, +day.slice(8, 10)) + 86400000).toISOString().slice(0, 10));
const minusDays = (day, n) => new Date(Date.UTC(+day.slice(0, 4), +day.slice(5, 7) - 1, +day.slice(8, 10)) - n * 86400000).toISOString().slice(0, 10);

/** カレンダーに入れる作品: 発売日が（今日 − CALENDAR_PAST_DAYS日）以降のもの。発売日の早い順。多すぎるときは近い日から */
export function calendarItems(items, today, limit = CALENDAR_MAX_EVENTS) {
  const from = minusDays(today, CALENDAR_PAST_DAYS);
  return items
    .filter((i) => i.dateKey >= from)
    .sort((a, b) => a.dateKey.localeCompare(b.dateKey) || a.cid.localeCompare(b.cid))
    .slice(0, limit);
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
    const description = `${item.title}\n品番: ${item.cid}\n${siteUrl}${itemPath(item.cid)}`;
    lines.push(
      'BEGIN:VEVENT',
      `UID:${item.cid}@${host}`,
      `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${compact(item.dateKey)}`,
      `DTEND;VALUE=DATE:${nextDay(item.dateKey)}`,
      `SUMMARY:${escapeIcsText(summary)}`,
      `DESCRIPTION:${escapeIcsText(description)}`,
      `URL:${siteUrl}${itemPath(item.cid)}`,
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
