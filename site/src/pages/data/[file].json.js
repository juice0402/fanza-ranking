// FANZA同人・FANZAゲームの小さなデータ（2026-10-09）:
//   /data/doujin-gacha.json・/data/game-gacha.json … 作品ページの「運命の作品」の候補（lib/floors.js の floorGachaPool。トップはページの中に入れる）
//   /data/doujin-index.json・/data/game-index.json … 作品検索の索引（lib/floors.js の floorSearchIndex。public/floor-search.js が読む）
import { activeFloors, floorGachaPools, floorSearchIndexes } from '../../lib/data.js';
import { gachaJson } from '../../lib/gacha.js';

export function getStaticPaths() {
  return activeFloors.flatMap((k) => [{ params: { file: `${k}-gacha` }, props: { kind: 'gacha', key: k } }, { params: { file: `${k}-index` }, props: { kind: 'index', key: k } }]);
}

export function GET({ props }) {
  const body = props.kind === 'gacha' ? floorGachaPools[props.key] : floorSearchIndexes[props.key];
  return new Response(gachaJson(body), { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}
