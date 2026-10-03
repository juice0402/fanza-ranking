// JSON（Pythonが毎日貯めているデータ）を読み込んで、画面で使う形にします。
import raw from '../data/new_releases.json';
import { normalizeItems, splitByRelease, jstToday } from './items.js';

export const today = jstToday();
export const all = normalizeItems(raw);
export const { released, upcoming } = splitByRelease(all, today);
