// 作品検索の続きのファイル（/data/items-more/1.json …。2026-10-11）。はじめに読む索引（/data/items-index.json）に入っていない、
// 載っているそのほかの作品（作品ページの無い、FANZAへ直接リンクする過去作品も）。キーワード・ジャンルで絞り込んだときなどに、ブラウザが後ろで読む。
// 短い名前の項目の意味は site/src/lib/search.js の buildSearchIndexes を参照。毎日のビルドで作り直します。
import { itemsMore } from '../../../lib/data.js';

export function getStaticPaths() {
  return itemsMore().map((part) => ({ params: { n: String(part.part) }, props: { part } }));
}

export function GET({ props }) {
  return new Response(JSON.stringify(props.part), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}
