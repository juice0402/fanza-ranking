// 月ごと・ジャンルごとの「作品のまとめページ」の部品（画面に依存しない。テスト: tests/test_seo.mjs）。
// 検索エンジンから「11月 新作 予約」「巨乳 新作」のような言葉で来てもらうためのページ。紹介文は作品データ（本数・発売日・メーカー・出演・形式）だけから作るので、事実と食い違わない。
import { MONTH_MIN_ITEMS, TAG_MIN_ITEMS, TAG_PAGE_GENRES, SITE_NAME } from '../config.js';
import { dateParts, dateRangeJp, formatsOf, groupItems, rankedNames, truncate } from './items.js';

// ------------------------------------------------------------------
// 月ごと（/month/2026-11/）
// ------------------------------------------------------------------

export const MONTH_INDEX_PATH = '/month/';
export const monthPath = (ym) => `/month/${ym}/`;

const byOldest = (a, b) => a.dateKey.localeCompare(b.dateKey) || a.cid.localeCompare(b.cid);

/** 発売月ごとの作品グループ（作品が minItems 本未満の月は作らない）。新しい月が先。月の中は発売日の早い順（カレンダーの順） */
export function groupByMonth(items, minItems = MONTH_MIN_ITEMS) {
  const months = new Map();
  for (const item of items) {
    const ym = item.dateKey.slice(0, 7);
    if (!months.has(ym)) months.set(ym, []);
    months.get(ym).push(item);
  }
  return [...months.entries()]
    .filter(([, list]) => list.length >= minItems)
    .map(([ym, list]) => {
      const { y, m } = dateParts(`${ym}-01`);
      return { ym, name: `${y}年${m}月`, path: monthPath(ym), items: [...list].sort(byOldest) };
    })
    .sort((a, b) => b.ym.localeCompare(a.ym));
}

/** 月のグループ → その月のページのパス（'YYYY-MM' → パス）。ページが無い月は引けない */
export const monthPathByKey = (groups) => new Map(groups.map((g) => [g.ym, g.path]));

/** 作品ページの「この月の発売日ごとの一覧」へのリンク（その日の位置まで飛ぶ）。その月のページが無ければ '' */
export function monthLinkFor(groupsByKey, dateKey) {
  const path = groupsByKey.get(dateKey.slice(0, 7));
  return path ? `${path}#day-${dateKey}` : '';
}

/** 前の月・次の月のグループ（ページがある月だけ）。groups は新しい月が先 */
export function neighborMonths(groups, ym) {
  const i = groups.findIndex((g) => g.ym === ym);
  if (i < 0) return { newer: null, older: null };
  return { newer: i > 0 ? groups[i - 1] : null, older: i < groups.length - 1 ? groups[i + 1] : null };
}

function listSummary(subject, items) {
  const makers = rankedNames(items.map((i) => i.maker).filter((m) => m !== '不明'), 3);
  const cast = rankedNames(items.flatMap((i) => i.actress), 4);
  const vr = items.filter((i) => i.vr).length;
  const formats = formatsOf(items);
  const parts = [`FANZAの新作・予約として掲載している${subject}は${items.length}本です。`, `発売日は${dateRangeJp(items)}です。`];
  if (makers.names.length) parts.push(`メーカーは${makers.names.join('、')}${makers.more ? 'ほか' : ''}です。`);
  if (cast.names.length) parts.push(`出演は${cast.names.join('、')}${cast.more ? 'ほか' : ''}です。`);
  if (vr > 0) parts.push(`VR作品は${vr}本です。`);
  else if (formats.length) parts.push(`${formats.join('・')}の作品を含みます。`);
  return parts.join('');
}

export const monthSummary = (group) => listSummary(`${group.name}発売の作品`, group.items);
export const monthPageTitle = (g) => `${g.name}発売のFANZA新作・予約作品一覧（${g.items.length}本）｜${SITE_NAME}`;

// ------------------------------------------------------------------
// ジャンルごと（/tag/…）
// ------------------------------------------------------------------

export const TAG_INDEX_PATH = '/tag/';
export const tagPath = (slug) => `/tag/${slug}/`;
/** VR作品のページの名前（FANZAのジャンル名ではなく、作品が VR かどうか（isVrWork）で集める） */
export const VR_TAG_NAME = 'VR作品';

/**
 * ジャンルごとの作品グループ。作るのは、TAG_PAGE_GENRES に書いたジャンルと、VR作品（いつも）。
 * 作品が minItems 本未満のものは作らない。作品数の多い順
 */
export function groupByTag(items, genres = TAG_PAGE_GENRES, minItems = TAG_MIN_ITEMS) {
  const allowed = new Set(genres);
  return groupItems(
    items,
    (item) => [...item.genres.filter((g) => allowed.has(g)), ...(item.vr ? [VR_TAG_NAME] : [])],
    tagPath,
    minItems,
  );
}

export const tagSummary = (group) => listSummary(group.name === VR_TAG_NAME ? 'VR作品' : `「${group.name}」のジャンルの作品`, group.items);
export const tagPageTitle = (g) => `${truncate(g.name, 30)}の新作・予約作品一覧（${g.items.length}本）｜${SITE_NAME}`;
