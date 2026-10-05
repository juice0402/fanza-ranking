// セール・キャンペーン（/sale/ とトップの「セール中」）の部品（画面に依存しない。tests/test_sale.mjs）。
// データは data/sale.json（毎日の更新が、FANZA公式のAPIの campaign・prices から、その日に見かけたセール中の作品を保存したもの）。
// 価格・期間は、その日の 0:05 ごろの情報。変わることがあるので、画面には「○日時点」と「最新はFANZAで」を必ず添える。
import { bestRank } from './popularity.js';
import { addDays, daysBetween, entitySlug, isDay } from './items.js';
import { isMinorTitle } from './gacha.js';

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
 * [{ k（キャンペーンの番号）, title, begin, end, items, total, covers, maxOff（値引きの分かる作品の、いちばん大きい割引。無ければ null）, makers, actresses, genres }]
 * （makers などは campaignSummary。全部の作品から数える）
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
      const offs = sorted.map((i) => offPercent(i.sale.price, i.sale.listPrice)).filter(Boolean);
      return { ...g, total: sorted.length, items: sorted.slice(0, perGroup), covers: campaignCovers(sorted), maxOff: offs.length ? Math.max(...offs) : null, ...campaignSummary(sorted, { genres }) };
    })
    .sort((a, b) => a.end.localeCompare(b.end) || b.total - a.total || (a.title < b.title ? -1 : a.title > b.title ? 1 : 0));
}

/** セール中の作品の数（今日より前に終わったキャンペーンは除く） */
export const saleCount = (items, sale, today) => saleGroups(items, sale, today, 0).reduce((n, g) => n + g.total, 0);

// ---------- セールの履歴・特集ごとのページ（運営者の希望「SEOを上位に」→「FANZAのセールはいつ？」と特集ごとのページ。2026-10-06） ----------
// 履歴は data/sale_history.json（毎日の更新が、その日に見かけたキャンペーンの名前・期間・このサイトの作品の本数・最大の割引を足していく。get_new_releases.py）。
// 記録は 2026-10-05 から。昔の履歴をほかのサイトから写すことはしない。

export const SALE_HISTORY_PATH = '/sale/history/';
export const CAMPAIGN_PAGE_DAYS = 90; // 特集のページは、最後に見かけてから、この日数のあいだ残す（開催中でないあいだは、検索エンジンに出さない）
export const CAMPAIGN_ITEM_LIMIT = 48; // 特集のページに並べる本数（人気の高い作品から）
export const SALE_HISTORY_START = '2026-10-05'; // 記録を始めた日

/** 特集の名前 → ページの印（名前ごとに1ページ。同じ名前の特集が、また開かれたら、同じページ）。全角・半角と空白の違いは同じあつかい */
export const campaignSlug = (title) => entitySlug(String(title ?? '').normalize('NFKC').replace(/\s+/g, ''));
export const campaignPath = (title) => `${SALE_PATH}${campaignSlug(title)}/`;

const DT = /^\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?$/;

/** sale_history.json → { updated, rows: [{ title, begin, end, first, last, count, maxOff }]（新しい順） }。形が違う行は捨てる */
export function normalizeSaleHistory(raw) {
  const ok = raw && typeof raw === 'object' && !Array.isArray(raw);
  const rows = [];
  for (const r of ok && Array.isArray(raw.campaigns) ? raw.campaigns : []) {
    if (!r || typeof r !== 'object') continue;
    const title = String(r.title ?? '').trim().slice(0, 60);
    const begin = String(r.begin ?? '');
    const end = String(r.end ?? '');
    if (!title || (begin && !DT.test(begin)) || !DT.test(end) || !isDay(r.first) || !isDay(r.last)) continue;
    rows.push({
      title, begin, end, first: r.first, last: r.last,
      count: Number.isInteger(r.count) && r.count >= 0 ? r.count : 0,
      maxOff: Number.isInteger(r.max_off) && r.max_off > 0 && r.max_off < 100 ? r.max_off : null,
    });
  }
  rows.sort((a, b) => (b.begin || b.first).localeCompare(a.begin || a.first) || b.end.localeCompare(a.end) || (a.title < b.title ? -1 : 1));
  return { updated: ok && isDay(raw.updated) ? raw.updated : '', rows };
}

/** 1回の開催の日数（始まりの日から終わりの日まで。両方の日を数える。始まりが分からなければ、最初に見かけた日から） */
export const runDays = (run) => daysBetween(run.end.slice(0, 10), (run.begin || run.first).slice(0, 10)) + 1;

/** "2026-10-05 10:00" → "10月5日"（日付だけ） */
export const mdOf = (dt) => (DT.test(String(dt ?? '')) ? `${+dt.slice(5, 7)}月${+dt.slice(8, 10)}日` : '');

/** 期間の短い文字: 「10月2日〜10月5日 9:59」（始まりが分からなければ「〜10月5日 9:59」） */
export const runRange = (run) => `${run.begin ? mdOf(run.begin) : ''}〜${endLabel(run.end)}`;

/**
 * 特集（キャンペーンの名前）ごとのページ: [{ slug, path, title, active（開催中なら saleGroups のまとまり。無ければ null）, runs（これまでの開催。新しい順）, lastSeen }]。
 * 開催中のもの（終わりが近い順）→ 終わったもの（最後に見かけた日が新しい順）。最後に見かけてから days 日をすぎたもの・未成年を連想させる名前は作らない
 * （こちらから案内するページのため。セールのページの一覧には、これまでどおり出る）
 */
export function campaignPages(items, sale, history, today, { genres = new Set(), days = CAMPAIGN_PAGE_DAYS, perGroup = CAMPAIGN_ITEM_LIMIT } = {}) {
  const pages = new Map();
  const add = (title) => {
    const slug = campaignSlug(title);
    if (!pages.has(slug)) pages.set(slug, { slug, path: `${SALE_PATH}${slug}/`, title, active: null, runs: [], lastSeen: '' });
    return pages.get(slug);
  };
  for (const g of saleGroups(items, sale, today, perGroup, { genres })) {
    if (isMinorTitle(g.title)) continue;
    const p = add(g.title);
    if (!p.active || g.end < p.active.end) p.active = g; // 同じ名前の特集が2つ同時に開いていたら、早く終わるほう
    p.lastSeen = sale.date || today;
  }
  const since = addDays(today, -days);
  for (const r of history.rows) {
    if (isMinorTitle(r.title) || (r.last < since && !pages.has(campaignSlug(r.title)))) continue;
    const p = add(r.title);
    p.runs.push(r);
    if (r.last > p.lastSeen) p.lastSeen = r.last;
  }
  return [...pages.values()].sort((a, b) =>
    (a.active ? 0 : 1) - (b.active ? 0 : 1)
    || (a.active && b.active ? a.active.end.localeCompare(b.active.end) || b.active.total - a.active.total : b.lastSeen.localeCompare(a.lastSeen))
    || (a.title < b.title ? -1 : 1)); // 開催中は、セールのページと同じ並び（終わりが近い順・同じなら本数の多い順）
}

/**
 * 「FANZAのセールはいつ？」のページの材料（データから数えた事実だけ。予想はしない）:
 * { runs（未成年を連想させる名前を除いた全部の開催。新しい順）, byMonth: [{ ym, runs }], repeats: [{ title, path, runs }]（2回以上開かれた名前。回数の多い順）,
 *   minDays, maxDays, avgDays（期間の日数）, since（記録の始まり） }
 */
export function saleHistoryFacts(history, pagesBySlug = new Map()) {
  const runs = history.rows.filter((r) => !isMinorTitle(r.title));
  const byMonth = [];
  for (const r of runs) {
    const ym = (r.begin || r.first).slice(0, 7);
    if (byMonth.at(-1)?.ym !== ym) byMonth.push({ ym, runs: [] });
    byMonth.at(-1).runs.push(r);
  }
  const titles = new Map();
  for (const r of runs) titles.set(r.title, [...(titles.get(r.title) ?? []), r]);
  const repeats = [...titles]
    .filter(([, rs]) => rs.length >= 2)
    .map(([title, rs]) => ({ title, path: pagesBySlug.get(campaignSlug(title))?.path ?? '', runs: rs }))
    .sort((a, b) => b.runs.length - a.runs.length || (b.runs[0].begin || b.runs[0].first).localeCompare(a.runs[0].begin || a.runs[0].first) || (a.title < b.title ? -1 : 1));
  const lens = runs.map(runDays).filter((n) => Number.isFinite(n) && n > 0);
  const since = runs.length ? runs.map((r) => r.first).sort()[0] : '';
  return {
    runs, byMonth, repeats,
    minDays: lens.length ? Math.min(...lens) : null,
    maxDays: lens.length ? Math.max(...lens) : null,
    avgDays: lens.length ? Math.round((lens.reduce((a, b) => a + b, 0) / lens.length) * 10) / 10 : null,
    since,
  };
}

/**
 * 作品の中で、いまセール中のもの（出演者のページの「セール中の作品」。2026-10-06）: 人気の高い順に [{ ...作品, sale: { k, price, listPrice, end, title } }]。
 * 終わったキャンペーンの作品は入れない
 */
export function onSaleItems(items, sale, today) {
  const out = [];
  for (const item of items) {
    const info = sale.byCid.get(item.cid);
    const camp = info && sale.campaigns[info.k];
    if (!camp || camp.end.slice(0, 10) < today || item.dateKey > today) continue;
    out.push({ ...item, sale: { ...info, end: camp.end, title: camp.title } });
  }
  return out.sort(byPopular);
}
