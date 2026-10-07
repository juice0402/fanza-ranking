// 人気順（「新着の人気順」と「全体の人気順」）の部品（画面に依存しない。tests/test_popularity.mjs）。
// ランキングのページは「新着の人気ランキング」（/ranking/）だけ。「全体の人気ランキング」（/ranking/all/）のページは、運営者の判断でやめた（2026-10-05。
// 古いURLは public/_redirects で /ranking/ へ）。全体の人気順は、作品検索の並べ替え「人気順（全体）」に使っている
// 順位は、毎日の更新が FANZA公式のAPIの人気順（sort=rank）を、その日に取り直したもの（get_new_releases.py）:
//   ・新着の人気順: data/popularity.json の new（最近1週間に発売された作品の、その日の人気順）。prev は前の日の新着の人気順（急上昇を見つける用）
//   ・全体の人気順: 過去作品は data/catalog_rank.json、毎日の更新の作品は data/popularity.json の all
// FANZAの「デイリーランキング」のページそのものは、APIに無く、自動で読むのも禁止なので使わない。
import { addDays } from './items.js';

export const RANKING_PATH = '/ranking/'; // 新着の人気順
export const RANKING_LIMIT = 100; // ランキングのページに並べる本数
export const NEW_RANK_DAYS = 7; // 「新着」の範囲（発売から何日まで。get_new_releases.py の NEW_RANK_DAYS と同じ。運営者の希望で1週間）
const UNKNOWN_RANK = 50000; // 過去作品の順位の「まだ分からない」（新着の人気順だけで見つけた作品）

const rankValue = (v) => (Number.isInteger(v) && v >= 1 && v < UNKNOWN_RANK ? v : null);

/** popularity.json → { date, newRank, allRank, prevDate, prevRank }（Map は cid → 順位。prev は前の日の新着の人気順）。無い・形が違うときは空 */
export function normalizePopularity(raw) {
  const ok = raw && typeof raw === 'object' && !Array.isArray(raw);
  const toMap = (obj) =>
    new Map(Object.entries(obj && typeof obj === 'object' && !Array.isArray(obj) ? obj : {}).flatMap(([cid, v]) => (rankValue(v) ? [[cid, v]] : [])));
  return {
    date: ok && /^\d{4}-\d{2}-\d{2}$/.test(String(raw.date ?? '')) ? raw.date : '',
    newRank: toMap(ok ? raw.new : null),
    allRank: toMap(ok ? raw.all : null),
    prevDate: ok && /^\d{4}-\d{2}-\d{2}$/.test(String(raw.prev_date ?? '')) ? raw.prev_date : '',
    prevRank: toMap(ok ? raw.prev : null),
  };
}

/** catalog_rank.json の {cid: [順位, 一回りの番号]} → 全体の人気順の順位（分からなければ null） */
export const catalogAllRank = (ranks, cid) => {
  const v = ranks && typeof ranks === 'object' && Object.prototype.hasOwnProperty.call(ranks, cid) ? ranks[cid] : null;
  return Array.isArray(v) ? rankValue(v[0]) : null;
};

/** 2つの順位の、上のほう（どちらも無ければ null） */
export const bestRank = (a, b) => (a && b ? Math.min(a, b) : a || b || null);

const byRank = (key) => (a, b) => a[key] - b[key] || b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid);

/** 新着の人気順: 最近 days 日に発売された作品（予約は除く）を、その日の新着の人気順に、limit 本まで */
export function newRanking(items, today, limit = RANKING_LIMIT, days = NEW_RANK_DAYS) {
  const from = addDays(today, -days);
  return items.filter((i) => i.popNew && i.dateKey <= today && i.dateKey >= from).sort(byRank('popNew')).slice(0, limit);
}

// ------------------------------------------------------------------
// 人気の動き（data/rank_history.json。運営者の希望「独自の価値を足す」。2026-10-07）
// 毎日の更新が、新着の人気順（上位500本）に出てきた作品について、毎日の順位をためたもの（get_new_releases.py の merge_rank_history）。
//   n: 新着の人気順（記録を始めた日から8日分）・a: 全体の人気順の上位1,000本（30日分）。0 は圏外、null はその日に取れなかった
// ------------------------------------------------------------------
const histRank = (v) => (v === null ? null : Number.isInteger(v) && v >= 0 && v <= UNKNOWN_RANK ? v : null);

/** 順位の並びのうち、いちばん上の順位と、その日（何日目か。0から）。1つも無ければ null */
export function bestOf(values) {
  let best = null;
  values.forEach((v, i) => {
    if (v && (!best || v < best.rank)) best = { rank: v, day: i };
  });
  return best;
}

/** rank_history.json → Map(cid → { start: 記録を始めた日, n: [...], a: [...], bestNew: {rank, day}|null, bestAll: {rank, day}|null, daysIn: 新着の人気順に出ていた日数 }) */
export function normalizeRankHistory(raw) {
  const rows = raw && typeof raw === 'object' && raw.items && typeof raw.items === 'object' && !Array.isArray(raw.items) ? raw.items : {};
  const out = new Map();
  for (const [cid, r] of Object.entries(rows)) {
    if (!r || typeof r !== 'object' || !/^\d{4}-\d{2}-\d{2}$/.test(String(r.d ?? '')) || !/^[A-Za-z0-9_-]+$/.test(cid)) continue;
    const n = (Array.isArray(r.n) ? r.n : []).slice(0, 8).map(histRank);
    const a = (Array.isArray(r.a) ? r.a : []).slice(0, 30).map(histRank);
    out.set(cid, { start: r.d, n, a, bestNew: bestOf(n), bestAll: bestOf(a), daysIn: n.filter((v) => v > 0).length });
  }
  return out;
}

