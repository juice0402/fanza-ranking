// FANZAのレビューの評価（★の平均と件数）と、高評価ランキングの部品（画面に依存しない。tests/test_reviews.mjs）。
// 運営者の希望「APIで使えるものは全部。SEO対策も徹底」（2026-10-10）。
// 動画の評価は data/reviews.json（get_new_releases.py が毎日の取得で見かけた作品からためる）、同人・ゲームなどは各売り場のデータの review。
// 評価はFANZAのもので、このサイトの評価ではない。検索結果の星マーク（構造化データの AggregateRating）には使わない
// （Googleの決まりで、ほかのサイトの評価を集めたものは星マークにできないため）。画面には「FANZAのレビュー」と分かるように出す。

export const REVIEW_RANKING_PATH = '/ranking/review/';
export const floorReviewRankingPath = (key) => `/${key}/ranking/review/`;
export const REVIEW_MIN = 10; // 高評価ランキングに入れるレビューの件数（少ない件数の満点が上に来すぎないように）
export const FLOOR_REVIEW_MIN = 5; // 同人・ゲームなどの売り場は、レビューの数が動画より少ないので5件から
export const REVIEW_RANKING_MIN_ITEMS = 10; // ランキングのページを作るのは、入る作品がこの本数以上のときだけ
export const REVIEW_RANKING_LIMIT = 100;
export const REVIEW_RECENT_DAYS = 30; // 「最近の発売で評価が高い作品」の日数
export const REVIEW_RECENT_MIN = 3;
export const REVIEW_SHELF_MIN = 3; // 女優・メーカー・ジャンルのページの「評価の高い作品」に入れる件数
export const REVIEW_PRIOR = 10; // 並べるときに、平均にならす件数（ベイズ平均。件数が少ないほど、全体の平均に近づける）

/** [平均×100, 件数] → { avg: 4.71, count: 31 }（読めなければ null） */
export function reviewOf(v) {
  if (!Array.isArray(v) || v.length !== 2 || !Number.isInteger(v[0]) || !Number.isInteger(v[1]) || v[0] < 100 || v[0] > 500 || v[1] < 1) return null;
  return { avg: v[0] / 100, count: v[1] };
}

/** reviews.json → { updated, byCid: Map(cid → { avg, count }) }（無い・形が違うときは空） */
export function normalizeReviews(raw) {
  const ok = raw && typeof raw === 'object' && !Array.isArray(raw);
  const byCid = new Map();
  const items = ok && raw.items && typeof raw.items === 'object' && !Array.isArray(raw.items) ? raw.items : {};
  for (const [cid, v] of Object.entries(items)) {
    const r = reviewOf(v);
    if (r && /^[A-Za-z0-9_-]{1,40}$/.test(cid)) byCid.set(cid, r);
  }
  return { updated: ok && /^\d{4}-\d{2}-\d{2}$/.test(String(raw.updated ?? '')) ? raw.updated : '', byCid };
}

/** 「★4.71（31件）」 */
export const reviewLabel = (r) => (r ? `★${r.avg.toFixed(2)}（${r.count.toLocaleString('ja-JP')}件）` : '');

/** 並べるための点（ベイズ平均）: (件数×平均 + PRIOR×全体の平均) ÷ (件数 + PRIOR) */
export const reviewScore = (r, mean, prior = REVIEW_PRIOR) => (r ? (r.count * r.avg + prior * mean) / (r.count + prior) : -Infinity);

/** 評価のある作品の、全体の平均（件数で重みをつける）。無ければ 4 */
export function reviewMean(items) {
  let n = 0;
  let sum = 0;
  for (const i of items) if (i.review) { n += i.review.count; sum += i.review.count * i.review.avg; }
  return n ? sum / n : 4;
}

const byScore = (mean) => (a, b) => reviewScore(b.review, mean) - reviewScore(a.review, mean) || b.review.count - a.review.count || (a.cid < b.cid ? -1 : a.cid > b.cid ? 1 : 0);

/**
 * 高評価ランキング: 発売済みで、レビューが min 件以上の作品を、ならした評価の高い順に limit 本。
 * skip: 入れない作品（こちらから勧める欄なので、未成年を連想させるタイトルの作品など）
 */
export function topRated(items, today, { min = REVIEW_MIN, limit = REVIEW_RANKING_LIMIT, skip = () => false } = {}) {
  const pool = items.filter((i) => i.review && i.review.count >= min && i.dateKey <= today && !skip(i));
  return pool.sort(byScore(reviewMean(pool))).slice(0, limit);
}

/** 最近 days 日の発売で、評価が高い作品（レビュー REVIEW_RECENT_MIN 件以上） */
export function recentTopRated(items, today, { days = REVIEW_RECENT_DAYS, limit = 12, skip = () => false } = {}) {
  const from = addDaysIso(today, -days);
  return topRated(items.filter((i) => i.dateKey >= from), today, { min: REVIEW_RECENT_MIN, limit, skip });
}

/** 女優・メーカー・ジャンルのページの「評価の高い作品」（レビュー REVIEW_SHELF_MIN 件以上。3本に満たなければ空） */
export function ratedShelf(items, today, { limit = 6, skip = () => false } = {}) {
  const list = topRated(items, today, { min: REVIEW_SHELF_MIN, limit, skip });
  return list.length >= 3 ? list : [];
}

function addDaysIso(day, n) {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
