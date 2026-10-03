// 出演者検索（/actress/）が、年齢・身長・サイズで絞り込むための索引（/data/actresses-index.json）。
// 短い名前の項目の意味は site/src/lib/profiles.js の buildActressSearchIndex を参照。生年月日は入れない（年齢だけ）。
import { actressSearchIndex } from '../../lib/data.js';

export function GET() {
  return new Response(JSON.stringify(actressSearchIndex), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}
