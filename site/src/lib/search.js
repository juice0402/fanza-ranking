// 作品検索（/search/）のための、サイト側の部品（画面に依存しない）。
// ブラウザ側の動き（絞り込み・結果の表示）は site/public/search.js、「VR作品を隠す」スイッチは site/public/vr-filter.js。
import { NEW_BADGE_DAYS } from '../config.js';
import { namesPattern, phraseZwsp } from './phrase.js';
import { productCode } from './facts.js';

export const SEARCH_PATH = '/search/';
export const ITEMS_INDEX_PATH = '/data/items-index.json';
export const ITEMS_INDEX_LIMIT = 3000; // 索引に入れる作品の最大数（新しい順）。毎回ダウンロードされるので、古いものから外す
export const DMM_IMAGE_PREFIX = 'https://pics.dmm.co.jp/'; // 画像のURLの先頭がこれなら、索引では省く（ブラウザ側で付け直す）

/** ジャンル（タグ）で絞り込んだ検索ページへのリンク */
export const searchPath = (tag = '') => (tag ? `${SEARCH_PATH}?tag=${encodeURIComponent(tag)}` : SEARCH_PATH);

/**
 * 作品検索のための索引（/data/items-index.json）。
 *   generated: 作った日 / newDays: 「新作」シールを付ける日数 / genres: ジャンル名の一覧（作品の多い順）
 *   items: 発売日の新しい順に、{ c 作品ID, p 品番（例 DLDSS-566。作れないときは無い）, t タイトル, d 発売日, a 出演者, m メーカー,
 *           g ジャンルの番号（genres の何番目か）, v VRなら 1（VRでなければ無い）, i 画像 }
 * タイトルには、文節の区切りに幅のない空白（U+200B）が入っている（ブラウザで、語の途中で改行しないため。site/src/lib/phrase.js の phraseZwsp）。
 * 出演者・メーカー・ジャンルは、作品ページと同じ名前。メーカーが「不明」のときは ''。
 * 画像は、DMMの画像のURLの先頭（https://pics.dmm.co.jp/）を省いた形（ほかのホストのURLはそのまま）。
 */
export function buildItemsIndex(items, today, limit = ITEMS_INDEX_LIMIT) {
  const picked = [...items]
    .sort((a, b) => b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid))
    .slice(0, limit);

  const counts = new Map();
  for (const item of picked) for (const g of new Set(item.genres)) counts.set(g, (counts.get(g) ?? 0) + 1);
  const genres = [...counts.keys()].sort((a, b) => counts.get(b) - counts.get(a) || (a < b ? -1 : a > b ? 1 : 0));
  const numberOf = new Map(genres.map((g, i) => [g, i]));
  const namesRe = namesPattern(picked.flatMap((i) => [...i.actress, i.maker]).filter((n) => n !== '不明'));

  return {
    generated: today,
    newDays: NEW_BADGE_DAYS,
    genres,
    items: picked.map((item) => {
      const row = {
        c: item.cid,
        t: phraseZwsp(item.title, namesRe),
        d: item.dateKey,
        a: item.actress,
        m: item.maker === '不明' ? '' : item.maker,
        g: [...new Set(item.genres)].map((g) => numberOf.get(g)).sort((x, y) => x - y),
        i: item.image_url.startsWith(DMM_IMAGE_PREFIX) ? item.image_url.slice(DMM_IMAGE_PREFIX.length) : item.image_url,
      };
      if (item.vr) row.v = 1;
      const code = productCode(item.cid);
      if (code) row.p = code;
      return row;
    }),
  };
}
