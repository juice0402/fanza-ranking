// 作品ごとの値段の記録（price_history.json。get_new_releases.py の save_price_history が、sale.json を書くたびに足していく。issue #183。2026-10-29 から）。
// 作品ページのセールの欄の近くに「このサイトの記録（○年○月○日から）：…」の1行を出す（components/PriceRecord.astro。テストは tests/test_price_history.mjs）。
// ・記録は、このサイトが見かけた範囲だけ。「史上最安」のような言い方はしない（DMMアフィリエイト参加規約 第4条＝景品表示法の有利誤認にならないように）
// ・記録が PRICE_RECORD_MIN_DAYS 日たまるまで出さない（since からその日数たった日のビルドから、自動で出る）
// ・今の値段は今までどおり sale.json から。記録の値段を「今の値段」として出さない。構造化データには入れない
import { daysBetween, formatDateJp, isDay } from './items.js';

export const PRICE_RECORD_MIN_DAYS = 30;
// 使わない言葉（記録は見かけた範囲だけなので、言い切る言葉・急がせる言葉は書かない。tests/verify_dist.py も、作品ページの記録の行で同じ言葉を見張る）
export const PRICE_RECORD_NG = /史上最安|過去最安|最安値|底値|買い時|今だけ|見逃/;

const posInt = (v) => Number.isInteger(v) && v > 0;

/** price_history.json → { since, updated, items: Map(cid → { listPrice, low, lowDay, count, start, last }) }。形が違う作品は捨てる。無ければ空 */
export function normalizePriceHistory(raw) {
  const ok = raw && typeof raw === 'object' && !Array.isArray(raw) && isDay(raw.since);
  const items = new Map();
  const rows = ok && raw.items && typeof raw.items === 'object' && !Array.isArray(raw.items) ? raw.items : {};
  for (const [cid, r] of Object.entries(rows)) {
    if (!Array.isArray(r) || r.length !== 6) continue;
    const [listPrice, low, lowDay, count, start, last] = r;
    if (![listPrice, low, count].every(posInt) || ![lowDay, start, last].every(isDay) || lowDay > last || start > last) continue;
    items.set(cid, { listPrice, low, lowDay, count, start, last });
  }
  return { since: ok ? raw.since : '', updated: ok && isDay(raw.updated) ? raw.updated : '', items };
}

/** 記録を画面に出してよいか（since から PRICE_RECORD_MIN_DAYS 日たった日のビルドから） */
export const priceRecordShown = (history, today) => Boolean(history?.since) && isDay(today) && daysBetween(today, history.since) >= PRICE_RECORD_MIN_DAYS;

const yen = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
const md = (d) => `${+d.slice(5, 7)}月${+d.slice(8, 10)}日`;

/**
 * 作品ページの1行の文（出さないときは ''）。
 * onSale: いまセール中か（sale.json・10円セールの札が出ているか）。そのときだけ「セールは○回目」（記録の最後に見かけた日が saleDate と同じとき）、ほかは「セールは○回」。
 * nowPrice: いまの値段（あれば）。記録のいちばん安い値段より安ければ、記録が追いついていないので出さない
 */
export function priceRecordText(cid, history, today, { onSale = false, nowPrice = null, saleDate = '' } = {}) {
  if (!priceRecordShown(history, today)) return '';
  const r = history.items.get(cid);
  if (!r || r.lowDay < history.since || r.lowDay > today) return '';
  if (posInt(nowPrice) && nowPrice < r.low) return '';
  const lowDay = r.lowDay.slice(0, 4) === today.slice(0, 4) ? md(r.lowDay) : formatDateJp(r.lowDay);
  const current = onSale && (!saleDate || r.last === saleDate);
  const text = `このサイトの記録（${formatDateJp(history.since)}から）：いちばん安かったのは${lowDay}の${yen(r.low)}円・セールは${r.count}回${current ? '目' : ''}`;
  return PRICE_RECORD_NG.test(text) ? '' : text;
}
