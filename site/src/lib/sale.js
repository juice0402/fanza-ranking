// セール・キャンペーン（/sale/ とトップの「セール中」）の部品（画面に依存しない。tests/test_sale.mjs）。
// データは data/sale.json（毎日の更新が、FANZA公式のAPIの campaign・prices から、その日に見かけたセール中の作品を保存したもの）。
// 価格・期間は、その日の 0:05 ごろの情報。変わることがあるので、画面には「○日時点」と「最新はFANZAで」を必ず添える。
import { bestRank } from './popularity.js';

export const SALE_PATH = '/sale/';
export const SALE_GROUP_LIMIT = 12; // 1つのキャンペーンに並べる本数（人気の高い作品から）
export const SALE_HOME_LIMIT = 4; // トップの「セール中」に出す本数

const DAY_TIME = /^(\d{4})-(\d{2})-(\d{2})(?: (\d{2}):(\d{2}))?$/;

/** sale.json → { date, campaigns: [{title, begin, end}], byCid: Map(cid → {k, price, listPrice}) }。無い・形が違うときは空 */
export function normalizeSale(raw) {
  const ok = raw && typeof raw === 'object' && !Array.isArray(raw);
  const campaigns = (ok && Array.isArray(raw.campaigns) ? raw.campaigns : []).map((c) => ({
    title: String(c?.title ?? '').trim().slice(0, 60),
    begin: DAY_TIME.test(String(c?.begin ?? '')) ? c.begin : '',
    end: DAY_TIME.test(String(c?.end ?? '')) ? c.end : '',
  }));
  const byCid = new Map();
  for (const r of ok && Array.isArray(raw.items) ? raw.items : []) {
    if (!r || typeof r !== 'object' || typeof r.c !== 'string' || !Number.isInteger(r.k) || !campaigns[r.k]?.title || !campaigns[r.k]?.end) continue;
    const priced = Number.isInteger(r.p) && Number.isInteger(r.l) && r.p > 0 && r.p < r.l;
    byCid.set(r.c, { k: r.k, price: priced ? r.p : null, listPrice: priced ? r.l : null });
  }
  return { date: ok && /^\d{4}-\d{2}-\d{2}$/.test(String(raw.date ?? '')) ? raw.date : '', campaigns, byCid };
}

/** 値引きの割合（%。四捨五入）。分からなければ null */
export const offPercent = (price, listPrice) => (price && listPrice && price < listPrice ? Math.round((1 - price / listPrice) * 100) : null);

/** "2026-10-05 09:59" → "10月5日 9:59"（時刻が無ければ日付だけ） */
export function endLabel(end) {
  const m = DAY_TIME.exec(String(end ?? ''));
  if (!m) return '';
  return `${+m[2]}月${+m[3]}日${m[4] ? ` ${+m[4]}:${m[5]}` : ''}`;
}

/** "2026-10-05 09:59" → ブラウザで終わりを比べるための時刻（日本時間。時刻が無ければ、その日の終わり） */
export function endIso(end) {
  const m = DAY_TIME.exec(String(end ?? ''));
  if (!m) return '';
  return `${m[1]}-${m[2]}-${m[3]}T${m[4] ? `${m[4]}:${m[5]}` : '23:59'}:59+09:00`;
}

/** 1本の作品のセールの札・価格の文（「30%OFF」「1,884円〜（通常2,692円〜）」）。価格が分からなければ札は「セール」 */
export function saleBadge(info) {
  const pct = offPercent(info?.price, info?.listPrice);
  return pct ? `${pct}%OFF` : 'セール';
}
export function salePriceNote(info) {
  if (!info?.price) return '';
  const yen = (n) => n.toLocaleString('ja-JP');
  return `${yen(info.price)}円〜（通常${yen(info.listPrice)}円〜）`;
}

const popularity = (i) => bestRank(i.popAll ?? null, i.popNew ?? null) ?? Infinity;
const byPopular = (a, b) => popularity(a) - popularity(b) || b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid);

/**
 * キャンペーンごとのまとまり（終わりが近い順）。items: このサイトの作品（人気の高い順に、perGroup 本まで）。
 * 今日より前に終わったキャンペーンは入れない（データが古いとき用）。[{ title, begin, end, items, total }]
 */
export function saleGroups(items, sale, today, perGroup = SALE_GROUP_LIMIT) {
  const groups = new Map();
  for (const item of items) {
    const info = sale.byCid.get(item.cid);
    if (!info) continue;
    const camp = sale.campaigns[info.k];
    if (!camp || camp.end.slice(0, 10) < today) continue;
    if (!groups.has(info.k)) groups.set(info.k, { ...camp, items: [] });
    groups.get(info.k).items.push({ ...item, sale: info });
  }
  return [...groups.values()]
    .map((g) => ({ ...g, total: g.items.length, items: [...g.items].sort(byPopular).slice(0, perGroup) }))
    .sort((a, b) => a.end.localeCompare(b.end) || b.total - a.total || (a.title < b.title ? -1 : a.title > b.title ? 1 : 0));
}

/** トップの「セール中」: セール中の作品を、人気の高い順に limit 本まで（今日より前に終わったキャンペーンは除く） */
export function saleHighlights(items, sale, today, limit = SALE_HOME_LIMIT) {
  return items
    .filter((i) => {
      const info = sale.byCid.get(i.cid);
      return info && sale.campaigns[info.k] && sale.campaigns[info.k].end.slice(0, 10) >= today;
    })
    .map((i) => ({ ...i, sale: sale.byCid.get(i.cid) }))
    .sort(byPopular)
    .slice(0, limit);
}

/** セール中の作品の数（今日より前に終わったキャンペーンは除く） */
export const saleCount = (items, sale, today) => saleHighlights(items, sale, today, Infinity).length;
