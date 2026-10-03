// JSON（Pythonが毎日貯めているデータ）を読み込んで、画面で使う形にします。
import raw from '../data/new_releases.json';
import { normalizeItems, splitByRelease, jstToday, groupByActress, groupByMaker, indexByName } from './items.js';

export const today = jstToday();
export const all = normalizeItems(raw);
export const { released, upcoming } = splitByRelease(all, today);

// 出演者・メーカーごとのページ（作品が ENTITY_MIN_ITEMS 本以上の人・メーカーだけ）
export const actressGroups = groupByActress(all);
export const makerGroups = groupByMaker(all);
export const actressByName = indexByName(actressGroups);
export const makerByName = indexByName(makerGroups);
