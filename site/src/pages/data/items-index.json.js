// 作品検索（/search/）が、タイトル・出演者・メーカー・ジャンル（タグ）で絞り込むための索引（/data/items-index.json）。
// 短い名前の項目の意味は site/src/lib/search.js の buildItemsIndex を参照。毎日のビルドで作り直します。
// 検索結果は作品ページへリンクするので、作品ページがある作品だけを入れる。
import { itemsIndex } from '../../lib/data.js';

export function GET() {
  return new Response(JSON.stringify(itemsIndex()), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}
