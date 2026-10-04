// 人気順（「新着の人気順」と「全体の人気順」）の部品（画面に依存しない。tests/test_popularity.mjs）。
// 順位は、毎日の更新が FANZA公式のAPIの人気順（sort=rank）を、その日に取り直したもの（get_new_releases.py）:
//   ・新着の人気順: data/popularity.json の new（最近30日に発売された作品の、その日の人気順）
//   ・全体の人気順: 過去作品は data/catalog_rank.json、毎日の更新の作品は data/popularity.json の all
// FANZAの「デイリーランキング」のページそのものは、APIに無く、自動で読むのも禁止なので使わない。
import { addDays } from './items.js';

export const RANKING_PATH = '/ranking/'; // 新着の人気順
export const RANKING_ALL_PATH = '/ranking/all/'; // 全体の人気順
export const RANKING_LIMIT = 100; // ランキングのページに並べる本数
export const NEW_RANK_DAYS = 30; // 「新着」の範囲（発売から何日まで。get_new_releases.py の NEW_RANK_DAYS と同じ）
const UNKNOWN_RANK = 50000; // 過去作品の順位の「まだ分からない」（新着の人気順だけで見つけた作品）

const rankValue = (v) => (Number.isInteger(v) && v >= 1 && v < UNKNOWN_RANK ? v : null);

/** popularity.json → { date, newRank: Map(cid → 順位), allRank: Map(cid → 順位) }。無い・形が違うときは空 */
export function normalizePopularity(raw) {
  const ok = raw && typeof raw === 'object' && !Array.isArray(raw);
  const toMap = (obj) =>
    new Map(Object.entries(obj && typeof obj === 'object' && !Array.isArray(obj) ? obj : {}).flatMap(([cid, v]) => (rankValue(v) ? [[cid, v]] : [])));
  return {
    date: ok && /^\d{4}-\d{2}-\d{2}$/.test(String(raw.date ?? '')) ? raw.date : '',
    newRank: toMap(ok ? raw.new : null),
    allRank: toMap(ok ? raw.all : null),
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

/** 全体の人気順: 発売済みの作品を、全体の人気順に、limit 本まで */
export function allRanking(items, today, limit = RANKING_LIMIT) {
  return items.filter((i) => i.popAll && i.dateKey <= today).sort(byRank('popAll')).slice(0, limit);
}
