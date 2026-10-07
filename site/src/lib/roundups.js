// 「週のまとめ記事」の部品（画面に依存しない）。
// 記事の本体（導入文・注目の作品）は、Claude が毎週月曜に書いて site/src/data/roundups.json に入れます。
// 本数・メーカー別などの数字は、作品データから毎回自動で数えます（scripts/claude_roundups.py の week_stats と同じ数え方）。
import { SITE_NAME, SITE_URL, addDays, dateParts, isDay, truncate } from './items.js';

export { addDays }; // 以前からここにあった名前（テストなどが使う）

export const WEEKLY_INDEX_PATH = '/weekly/';
export const weeklyPath = (weekStart) => `/weekly/${weekStart}/`;

const TOP_MAKERS = 5;
const TOP_ACTRESSES = 5; // 2本以上に出た人だけ

const toUtc = (dateKey) => Date.UTC(+dateKey.slice(0, 4), +dateKey.slice(5, 7) - 1, +dateKey.slice(8, 10));

/** その日を含む週の月曜日 */
export function weekStartOf(dateKey) {
  const dow = new Date(toUtc(dateKey)).getUTCDay(); // 日=0
  return addDays(dateKey, -((dow + 6) % 7));
}

export const isMonday = (dateKey) => isDay(dateKey) && weekStartOf(dateKey) === dateKey;
export const weekEndOf = (weekStart) => addDays(weekStart, 6);

/** 記事のタイトル用の期間。例: 2026年10月5日〜11日 / 2026年9月28日〜10月4日 / 2026年12月28日〜2027年1月3日 */
export function weekRangeJp(weekStart) {
  const a = dateParts(weekStart);
  const b = dateParts(weekEndOf(weekStart));
  if (a.y !== b.y) return `${a.y}年${a.m}月${a.d}日〜${b.y}年${b.m}月${b.d}日`;
  if (a.m !== b.m) return `${a.y}年${a.m}月${a.d}日〜${b.m}月${b.d}日`;
  return `${a.y}年${a.m}月${a.d}日〜${b.d}日`;
}

export const roundupTitle = (r) => `${weekRangeJp(r.week_start)}のFANZA新作まとめ`;

/** 年を入れない短い期間（トップの右の欄・話題用）。例: 9月28日〜10月4日 / 10月5日〜11日 */
export function weekRangeShort(weekStart) {
  const a = dateParts(weekStart);
  const b = dateParts(weekEndOf(weekStart));
  return a.m !== b.m ? `${a.m}月${a.d}日〜${b.m}月${b.d}日` : `${a.m}月${a.d}日〜${b.d}日`;
}

/** 導入文のはじめの1文（トップの右の欄の「週のまとめ」の概要。くわしくは記事のページで）。長ければ max 文字で切る */
export function roundupSummary(r, max = 70) {
  const lead = String(r?.lead ?? '').trim();
  const end = lead.indexOf('。');
  return truncate(end >= 0 ? lead.slice(0, end + 1) : lead, max);
}

/**
 * トップの右の欄の「週のまとめ」に並べる、注目の作品の表紙（記事の順に、画像があってVRでない作品を n 本）。
 * VR作品を入れないのは、「VR作品を隠す」を押しても、ここの3枚の並びがくずれないように
 */
export function roundupCovers(r, items, n = 3) {
  const byCid = new Map(items.map((i) => [i.cid, i]));
  return (r?.picks ?? [])
    .map((p) => byCid.get(p.cid))
    .filter((i) => i && i.image_url && !i.vr)
    .slice(0, n);
}
export const roundupPageTitle = (r) => `${roundupTitle(r)}｜${SITE_NAME}`;
export const roundupDescription = (r) => truncate(r.lead, 120);

/**
 * roundups.json を画面で使う形にする。
 * 読めない記事（月曜でない・導入文や公開日が無いなど）は捨てる（tests/test_data.py が、そうなっていないかを見張っている）。注目の作品のうち、作品データに無いものは外す。
 * 新しい週が先頭。
 */
export function normalizeRoundups(raw, items) {
  const known = new Set(items.map((i) => i.cid));
  const seen = new Set();
  const out = [];
  for (const r of Array.isArray(raw) ? raw : []) {
    if (!r || typeof r !== 'object') continue;
    const weekStart = String(r.week_start ?? '');
    const lead = String(r.lead ?? '').trim();
    if (!isMonday(weekStart) || !lead || !isDay(r.written) || seen.has(weekStart)) continue;
    seen.add(weekStart);
    const picks = (Array.isArray(r.picks) ? r.picks : [])
      .filter((p) => p && known.has(String(p.cid)) && String(p.note ?? '').trim())
      .map((p) => ({ cid: String(p.cid), note: String(p.note).trim() }));
    out.push({
      week_start: weekStart,
      week_end: weekEndOf(weekStart),
      lead,
      trend: String(r.trend ?? '').trim(), // この週の傾向（2026-10-07 から。Claude が書く）
      facts: normalizeTrendFacts(r.facts), // 書いたときの傾向の数字（表にする）。読めなければ null
      picks,
      written: r.written,
    });
  }
  return out.sort((a, b) => b.week_start.localeCompare(a.week_start));
}

const isCount = (v) => Number.isInteger(v) && v >= 0;
export const TREND_GENRES_MAX = 6; // scripts/claude_roundups.py の TREND_GENRES と同じ
export const TREND_POPULAR_MAX = 5; // 同じく FACTS_POPULAR

/**
 * 記事と一緒に保存した、書いたときの傾向の数字（scripts/claude_roundups.py の trend_facts）を画面で使う形にする。
 * 本数のどれかが読めなければ null（傾向の表を出さない）。ジャンル・人気の作品は、読めない行だけ捨てる。月のまとめ記事も同じ形
 */
export function normalizeTrendFacts(f) {
  if (!f || typeof f !== 'object') return null;
  const keys = ['total', 'prev_total', 'vr', 'prev_vr', 'debut'];
  if (!keys.every((k) => isCount(f[k]))) return null;
  const genres = (Array.isArray(f.genres) ? f.genres : [])
    .filter((g) => g && typeof g.name === 'string' && g.name && isCount(g.count) && isCount(g.prev))
    .slice(0, TREND_GENRES_MAX)
    .map((g) => ({ name: g.name, count: g.count, prev: g.prev }));
  const popular = (Array.isArray(f.popular) ? f.popular : [])
    .filter((p) => p && typeof p.cid === 'string' && p.cid && isCount(p.best) && p.best >= 1 && isCount(p.days10))
    .slice(0, TREND_POPULAR_MAX)
    .map((p) => ({ cid: p.cid, best: p.best, days10: p.days10 }));
  return { ...Object.fromEntries(keys.map((k) => [k, f[k]])), genres, popular };
}

/** 前と比べた増減の札。例: ▲21 / ▼3 / ±0（前が0で今もあれば「新しく」） */
export function deltaLabel(now, prev) {
  if (prev === 0 && now > 0) return '新しく';
  const d = now - prev;
  return d > 0 ? `▲${d}` : d < 0 ? `▼${-d}` : '±0';
}

/** 増減の向き（CSS の印に使う）: up / down / same */
export const deltaKind = (now, prev) => (now > prev ? 'up' : now < prev ? 'down' : 'same');

/**
 * ジャンルの本数の横棒（いまと前の期間）。幅は、表の中のいちばん大きい本数を100%とした割合（1本でも見えるよう、0本でなければ4%以上）
 */
export function genreBars(genres) {
  const max = Math.max(1, ...genres.flatMap((g) => [g.count, g.prev]));
  const pct = (n) => (n > 0 ? Math.max(4, Math.round((n / max) * 100)) : 0);
  return genres.map((g) => ({ ...g, now: pct(g.count), before: pct(g.prev), delta: deltaLabel(g.count, g.prev), kind: deltaKind(g.count, g.prev) }));
}

/** その週（月〜日）に発売された作品。日付の古い順 */
export function itemsInWeek(items, weekStart) {
  const end = weekEndOf(weekStart);
  return items
    .filter((i) => i.dateKey >= weekStart && i.dateKey <= end)
    .sort((a, b) => a.dateKey.localeCompare(b.dateKey) || a.cid.localeCompare(b.cid));
}

const rankedCounts = (names, minimum, limit) => {
  const counts = new Map();
  for (const n of names) counts.set(n, (counts.get(n) ?? 0) + 1);
  const rows = [...counts]
    .filter(([, c]) => c >= minimum)
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
    .map(([name, count]) => ({ name, count }));
  return limit ? rows.slice(0, limit) : rows;
};

/** その週の集計（scripts/claude_roundups.py の week_stats と同じ数え方） */
export function weekStats(items, weekStart) {
  const rows = itemsInWeek(items, weekStart);
  const perDay = new Map();
  for (const i of rows) perDay.set(i.dateKey, (perDay.get(i.dateKey) ?? 0) + 1);
  return {
    total: rows.length,
    per_day: [...perDay].sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([date, count]) => ({ date, count })),
    makers: rankedCounts(rows.map((i) => i.maker).filter((m) => m && m !== '不明'), 1, TOP_MAKERS),
    actresses: rankedCounts(rows.flatMap((i) => [...new Set(i.actress)]), 2, TOP_ACTRESSES),
    formats: rankedCounts(rows.flatMap((i) => [...new Set(i.formats)]), 1, 0),
  };
}

/** 前の週・次の週の記事（あるときだけ） */
export function neighbours(roundups, weekStart) {
  const sorted = [...roundups].sort((a, b) => a.week_start.localeCompare(b.week_start));
  const i = sorted.findIndex((r) => r.week_start === weekStart);
  return { prev: i > 0 ? sorted[i - 1] : null, next: i >= 0 && i < sorted.length - 1 ? sorted[i + 1] : null };
}

/** 記事の構造化データ（Article）。著者・発行元はサイト自身 */
export function articleLd(r, siteUrl = SITE_URL) {
  const url = siteUrl + weeklyPath(r.week_start);
  const publisher = { '@type': 'Organization', name: SITE_NAME, url: siteUrl + '/' };
  return {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: roundupTitle(r),
    datePublished: r.written,
    dateModified: r.written,
    inLanguage: 'ja',
    mainEntityOfPage: { '@type': 'WebPage', '@id': url },
    author: publisher,
    publisher,
  };
}
