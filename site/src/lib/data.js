// JSON（Pythonが毎日貯めているデータ）を読み込んで、画面で使う形にします。
import raw from '../data/new_releases.json';
import rawRoundups from '../data/roundups.json';
import { normalizeItems, splitByRelease, jstToday, groupByActress, groupByMaker, indexByName } from './items.js';
import { normalizeRoundups } from './roundups.js';
import { buildActressSearchIndex, normalizeProfiles, profileByName, profileCoverage, rankingForDisplay } from './profiles.js';

// 出演者データ・売れ筋ランキングは、毎日の更新が作るファイル。まだ無いとき（最初の更新の前）でもビルドが止まらないよう、
// import ではなく glob で読む（無ければ空として扱う）
const optional = import.meta.glob('../data/{actresses,ranking}.json', { eager: true, import: 'default' });
const optionalData = (name) => optional[`../data/${name}.json`] ?? null;

export const today = jstToday();
export const all = normalizeItems(raw);
export const { released, upcoming } = splitByRelease(all, today);

// 出演者・メーカーごとのページ（作品が ENTITY_MIN_ITEMS 本以上の人・メーカーだけ）
export const actressGroups = groupByActress(all);
export const makerGroups = groupByMaker(all);
export const actressByName = indexByName(actressGroups);
export const makerByName = indexByName(makerGroups);

// 週のまとめ記事（Claudeが毎週月曜に書く。まだ1本も無いときは空）
export const roundups = normalizeRoundups(rawRoundups, all);

// 出演者のプロフィール（顔写真・年齢・体型・FANZAの全作品リンク）。名前で引く
export const profiles = normalizeProfiles(optionalData('actresses'), today);
export const profilesByName = profileByName(profiles);
export const profilesCoverage = profileCoverage(profiles);
export const actressSearchIndex = buildActressSearchIndex(profiles, all, actressByName, today);

// 売れ筋ランキング（FANZAの人気順の上位3本）。無い・古いときは null（画面に出さない）
export const ranking = rankingForDisplay(optionalData('ranking'), today);
