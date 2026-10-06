// 「運命の作品」の候補（/data/gacha.json）。作品ページの下の運命の作品が読む（2026-10-06。作品ページのたびに同じ候補を入れると、
// ページが重くなるため、1つのファイルにして、ブラウザに置いておく）。トップは、これまでどおりページの中の小さなデータ（#gacha-data）を使う
import { all, paged, today } from '../../lib/data.js';
import { gachaJson, gachaPool } from '../../lib/gacha.js';

export function GET() {
  return new Response(gachaJson(gachaPool(all, paged, today)), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}
