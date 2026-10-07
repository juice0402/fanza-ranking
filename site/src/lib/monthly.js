// 「月のまとめ記事」の部品（画面に依存しない。2026-10-07 から。運営者の希望「月のまとめ記事」）。
// 記事の本体（導入文・この月の傾向・注目の作品）は、Claude が毎月1日に書いて site/src/data/monthly.json に入れます（scripts/claude_monthly.py）。
// 記事は、月のページ（/month/YYYY-MM/）のいちばん上に出ます。傾向の数字は、週のまとめと同じ形（lib/roundups.js の normalizeTrendFacts）
import { SITE_NAME, SITE_URL, isDay, truncate } from './items.js';
import { normalizeTrendFacts } from './roundups.js';
import { monthPath } from './collections.js';

const MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;

/** その月の最後の日（YYYY-MM-DD） */
export function monthLastDay(month) {
  const y = Number(month.slice(0, 4));
  const m = Number(month.slice(5, 7));
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return `${month}-${String(last).padStart(2, '0')}`;
}

/** 「2026年10月」 */
export const monthJp = (month) => `${Number(month.slice(0, 4))}年${Number(month.slice(5, 7))}月`;
export const monthlyTitle = (r) => `${monthJp(r.month)}のFANZA新作まとめ`;
export const monthlyDescription = (r) => truncate(r.lead, 120);

/**
 * monthly.json を画面で使う形にする。読めない記事（月の形が違う・その月が終わる前の公開日・導入文が無いなど）は捨てる
 * （tests/test_data.py が、そうなっていないかを見張っている）。注目の作品のうち、作品データに無いもの・その月の発売でないものは外す。新しい月が先頭
 */
export function normalizeMonthly(raw, items) {
  const dateOf = new Map(items.map((i) => [i.cid, i.dateKey]));
  const seen = new Set();
  const out = [];
  for (const r of Array.isArray(raw) ? raw : []) {
    if (!r || typeof r !== 'object') continue;
    const month = String(r.month ?? '');
    const lead = String(r.lead ?? '').trim();
    if (!MONTH_RE.test(month) || !lead || !isDay(r.written) || r.written <= monthLastDay(month) || seen.has(month)) continue;
    seen.add(month);
    const picks = (Array.isArray(r.picks) ? r.picks : [])
      .filter((p) => p && String(dateOf.get(String(p.cid)) ?? '').slice(0, 7) === month && String(p.note ?? '').trim())
      .map((p) => ({ cid: String(p.cid), note: String(p.note).trim() }));
    out.push({ month, lead, trend: String(r.trend ?? '').trim(), facts: normalizeTrendFacts(r.facts), picks, written: r.written });
  }
  return out.sort((a, b) => b.month.localeCompare(a.month));
}

/** 月のページの記事の構造化データ（Article）。著者・発行元はサイト自身（人の名前を入れない） */
export function monthlyLd(r, siteUrl = SITE_URL) {
  const publisher = { '@type': 'Organization', name: SITE_NAME, url: siteUrl + '/' };
  return {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: monthlyTitle(r),
    datePublished: r.written,
    dateModified: r.written,
    inLanguage: 'ja',
    mainEntityOfPage: { '@type': 'WebPage', '@id': siteUrl + monthPath(r.month) },
    author: publisher,
    publisher,
  };
}
