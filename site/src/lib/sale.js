// セール・キャンペーン（/sale/ とトップの「セール中」）の部品（画面に依存しない。tests/test_sale.mjs）。
// データは data/sale.json（毎日の更新が、FANZA公式のAPIの campaign・prices から、その日に見かけたセール中の作品を保存したもの）。
// 価格・期間は、その日の 0:05 ごろの情報。変わることがあるので、画面には「○日時点」と「最新はFANZAで」を必ず添える。
import { bestRank } from './popularity.js';

export const SALE_PATH = '/sale/';
export const SALE_GROUP_LIMIT = 12; // 1つのキャンペーンに並べる本数（人気の高い作品から）
export const SALE_HOME_CAMPAIGNS = 4; // トップの「セール中の特集」に出す特集（キャンペーン）の数
export const SALE_COVERS = 3; // 特集のカードに重ねる表紙の数
export const SALE_SUMMARY_LIMIT = 3; // 特集ごとの「おもなメーカー」「よく出ている女優」「多いジャンル」の数
export const SALE_ACTRESS_MAX_CAST = 4; // 女優を数えるのは、出演者が4人までの作品だけ（オムニバス・総集編で数がふくらまないように）
export const SALE_ACTRESS_MIN = 2; // 「よく出ている女優」は、その特集の作品が2本以上ある人だけ

/** 特集（キャンペーン）の見出しの id と、そこへのリンク（キャンペーンの番号は sale.json の campaigns の順。その日のあいだは変わらない） */
export const saleAnchor = (k) => `sale-${k}`;
export const saleHref = (k) => `${SALE_PATH}#${saleAnchor(k)}`;

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

/** 終わりが今日・あすなら「きょうまで」「あすまで」の札（それより先は空） */
export function endSoonTag(end, today) {
  const day = String(end ?? '').slice(0, 10);
  if (!DAY_TIME.test(String(end ?? '')) || !/^\d{4}-\d{2}-\d{2}$/.test(String(today ?? ''))) return '';
  if (day === today) return 'きょうまで';
  const next = new Date(`${today}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + 1);
  return day === next.toISOString().slice(0, 10) ? 'あすまで' : '';
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

/** 名前の数を数えて、多い順に [{name, count}]（同数なら名前の順）。min 本未満の名前は入れない */
function topCounts(names, limit, min = 1) {
  const counts = new Map();
  for (const n of names) counts.set(n, (counts.get(n) ?? 0) + 1);
  return [...counts]
    .filter(([, count]) => count >= min)
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
    .slice(0, limit)
    .map(([name, count]) => ({ name, count }));
}

/**
 * 特集の中身（このサイトの作品から数えた事実だけ。評価の言葉は書かない）:
 *   makers おもなメーカー / actresses よく出ている女優（出演者が SALE_ACTRESS_MAX_CAST 人までの作品で、SALE_ACTRESS_MIN 本以上）/
 *   genres 多いジャンル（genres に入っているジャンルだけ。ページを作るジャンルの一覧を渡す。形式のジャンル（ハイビジョン・単体作品など）が上に来ないように）
 */
export function campaignSummary(works, { genres = new Set(), limit = SALE_SUMMARY_LIMIT } = {}) {
  return {
    makers: topCounts(works.map((w) => w.maker).filter((m) => m && m !== '不明'), limit),
    actresses: topCounts(works.filter((w) => (w.actress?.length ?? 0) <= SALE_ACTRESS_MAX_CAST).flatMap((w) => [...new Set(w.actress ?? [])]), limit, SALE_ACTRESS_MIN),
    genres: topCounts(works.flatMap((w) => [...new Set(w.genres ?? [])].filter((g) => genres.has(g))), limit),
  };
}

/** 特集のカードに重ねる表紙: 人気の高い順に、VRでない作品を先に（足りなければVR作品で埋める。VR作品の表紙は「VR作品を隠す」で隠れる） */
export function campaignCovers(sortedWorks, n = SALE_COVERS) {
  const plain = sortedWorks.filter((w) => !w.vr);
  return [...plain, ...sortedWorks.filter((w) => w.vr)].slice(0, n);
}

/**
 * キャンペーンごとのまとまり（終わりが近い順）。items: このサイトの作品（人気の高い順に、perGroup 本まで）。
 * 今日より前に終わったキャンペーンは入れない（データが古いとき用）。
 * [{ k（キャンペーンの番号）, title, begin, end, items, total, covers, makers, actresses, genres }]（makers などは campaignSummary。全部の作品から数える）
 */
export function saleGroups(items, sale, today, perGroup = SALE_GROUP_LIMIT, { genres = new Set() } = {}) {
  const groups = new Map();
  for (const item of items) {
    const info = sale.byCid.get(item.cid);
    if (!info) continue;
    const camp = sale.campaigns[info.k];
    if (!camp || camp.end.slice(0, 10) < today) continue;
    if (!groups.has(info.k)) groups.set(info.k, { k: info.k, ...camp, items: [] });
    groups.get(info.k).items.push({ ...item, sale: info });
  }
  return [...groups.values()]
    .map((g) => {
      const sorted = [...g.items].sort(byPopular);
      return { ...g, total: sorted.length, items: sorted.slice(0, perGroup), covers: campaignCovers(sorted), ...campaignSummary(sorted, { genres }) };
    })
    .sort((a, b) => a.end.localeCompare(b.end) || b.total - a.total || (a.title < b.title ? -1 : a.title > b.title ? 1 : 0));
}

/** セール中の作品の数（今日より前に終わったキャンペーンは除く） */
export const saleCount = (items, sale, today) => saleGroups(items, sale, today, 0).reduce((n, g) => n + g.total, 0);
