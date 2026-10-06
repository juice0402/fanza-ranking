// 作品ページの「次に見るもの」の部品（運営者の希望「サイト滞在時間を伸ばしたい」。2026-10-06。画面に依存しない。tests/test_stay.mjs）。
// 検索から作品ページに来た人が、そこで帰らずに、次の作品・女優・セールへ進めるように:
//   次の新作（この作品の出演者の、予約受付中の作品）・同じ出演者/メーカーの作品（小さな表紙の棚）
// どちらも、こちらから案内する欄なので、未成年を連想させるタイトルの作品は入れない（運命の作品・きょうの話題と同じ）
import { relatedItems } from './items.js';
import { isMinorTitle } from './gacha.js';

export const NEXT_WORKS_SHOWN = 3; // 作品ページの「次の新作」の本数
export const NEXT_WORKS_MAX_CAST = 4; // 出演者がこの人数までの作品だけ（オムニバス・総集編で、関係の薄い作品が並ばないように）
export const RELATED_SHOWN = 6; // 「同じ出演者・メーカーの作品」の本数（スマホで3列×2段）

/**
 * この作品の出演者の、次の新作（予約受付中。発売日が近い順に limit 本。この作品は入れない）: { names（次の新作がある出演者。この作品の並び順）, items }。
 * byName: 出演者の名前 → その人の作品（出演者のページのまとまり。actressByName）
 */
export function nextWorksOf(item, byName, today, { limit = NEXT_WORKS_SHOWN, maxCast = NEXT_WORKS_MAX_CAST } = {}) {
  if (!item.actress.length || item.actress.length > maxCast) return { names: [], items: [] };
  const seen = new Set([item.cid]);
  const found = [];
  const names = [];
  for (const name of item.actress) {
    const works = (byName.get(name)?.items ?? []).filter((w) => w.dateKey > today && !seen.has(w.cid) && !isMinorTitle(w.title));
    if (works.length) names.push(name);
    for (const w of works) {
      seen.add(w.cid);
      found.push(w);
    }
  }
  found.sort((a, b) => a.dateKey.localeCompare(b.dateKey) || a.cid.localeCompare(b.cid));
  return { names, items: found.slice(0, limit) };
}

/** 同じ出演者・メーカーの作品（relatedItems と同じ選び方で、未成年を連想させるタイトルの作品を除いて limit 本） */
export function relatedForPage(item, all, limit = RELATED_SHOWN) {
  return relatedItems(item, all, limit * 3).filter((w) => !isMinorTitle(w.title)).slice(0, limit);
}
