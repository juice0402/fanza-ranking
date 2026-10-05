// 作品検索（/search/）のための、サイト側の部品（画面に依存しない）。
// ブラウザ側の動き（絞り込み・結果の表示）は site/public/search.js、「VR作品を隠す」スイッチは site/public/vr-filter.js。
import { NEW_BADGE_DAYS } from '../config.js';
import { namesPattern, phraseZwsp } from './phrase.js';
import { productCode } from './facts.js';

export const SEARCH_PATH = '/search/';
export const ITEMS_INDEX_PATH = '/data/items-index.json';
export const ITEMS_INDEX_LIMIT = 3000; // 索引に入れる作品の最大数（新しい順）。毎回ダウンロードされるので、古いものから外す
export const ITEMS_INDEX_POPULAR = 1000; // そのうち、全体の人気順の上位は、古くてもこの本数まで先に入れる（「人気順（全体）」で並べたときに出るように）
export const DMM_IMAGE_PREFIX = 'https://pics.dmm.co.jp/'; // 画像のURLの先頭がこれなら、索引では省く（ブラウザ側で付け直す）

/** ジャンル（タグ）で絞り込んだ検索ページへのリンク */
export const searchPath = (tag = '') => (tag ? `${SEARCH_PATH}?tag=${encodeURIComponent(tag)}` : SEARCH_PATH);

/**
 * 作品検索のための索引（/data/items-index.json）。
 *   generated: 作った日 / newDays: 「新作」シールを付ける日数 / genres: ジャンル名の一覧（作品の多い順）
 *   items: 発売日の新しい順に、{ c 作品ID, p 品番（例 DLDSS-566。作れないときは無い）, t タイトル, d 発売日, a 出演者, m メーカー,
 *           g ジャンルの番号（genres の何番目か）, v VRなら 1（VRでなければ無い）, o 単体作品なら 1（そうでなければ無い）, i 画像,
 *           r 全体の人気順の順位・n 新着の人気順の順位（分からなければ無い。lib/popularity.js） }
 * 入れる作品: 全体の人気順の上位 ITEMS_INDEX_POPULAR 本と、残りは新しい順に、合わせて limit 本まで（並びは発売日の新しい順）
 * タイトルには、文節の区切りに幅のない空白（U+200B）が入っている（ブラウザで、語の途中で改行しないため。site/src/lib/phrase.js の phraseZwsp）。
 * 出演者・メーカー・ジャンルは、作品ページと同じ名前。メーカーが「不明」のときは ''。
 * 画像は、DMMの画像のURLの先頭（https://pics.dmm.co.jp/）を省いた形（ほかのホストのURLはそのまま）。
 */
/** 索引で省く、決まった形の画像のパス（DMM の URL の先頭を除いたもの） */
export const standardImage = (cid) => `digital/video/${cid}/${cid}pl.jpg`;

export function buildItemsIndex(items, today, limit = ITEMS_INDEX_LIMIT, popularCount = ITEMS_INDEX_POPULAR) {
  const newest = (a, b) => b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid);
  const popular = items.filter((i) => i.popAll).sort((a, b) => a.popAll - b.popAll || newest(a, b)).slice(0, Math.min(popularCount, limit));
  const chosen = new Set(popular.map((i) => i.cid));
  const picked = [...popular, ...[...items].sort(newest).filter((i) => !chosen.has(i.cid))].slice(0, limit).sort(newest);

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
      };
      // 画像: DMM の URL の先頭を省く。いちばん多い決まった形（digital/video/作品ID/作品IDpl.jpg）なら、項目ごと省く
      // （ブラウザ側の public/search.js の rowImage が作り直す。索引を軽くするため。2026-10-05）。画像が無い作品は ''
      const image = item.image_url.startsWith(DMM_IMAGE_PREFIX) ? item.image_url.slice(DMM_IMAGE_PREFIX.length) : item.image_url;
      if (image !== standardImage(item.cid)) row.i = image;
      if (item.vr) row.v = 1;
      if (item.solo) row.o = 1; // 単体作品（「単体作品のみ表示」スイッチ）
      if (item.popAll) row.r = item.popAll;
      if (item.popNew) row.n = item.popNew;
      const code = productCode(item.cid);
      if (code) row.p = code;
      return row;
    }),
  };
}
