// サイトのファイル数を、Cloudflare Pages の無料プランの上限（2万ファイル）に収める計画（画面に依存しない。tests/test_plan.mjs）。
// 過去作品（カタログ）を集めていくと、作品ページだけで2万をこえるため、作品ページは、優先順に、残りの枠の数だけ作る。
//   優先順: ①毎日の更新で載せた作品（新作・予約。コメントがある） ②コメントのある過去作品 ③そのほかの過去作品
//   同じ中では、過去作品は FANZAの人気順の順位が上の作品から（質の高い作品のページを先に作る。運営者の希望。2026-10-04）、そのあとは発売日の新しい順
// 作品ページの無い作品は、一覧・出演者/メーカーのページから、FANZAの作品ページへ直接リンクする（itemHref）。
import { ARCHIVE_PAGE_SIZE, FILE_BUDGET, FIXED_FILES } from '../config.js';
import { itemPath } from './items.js';

/** 作品ページ以外のファイルの数（見積もり）。counts: 出演者・メーカー・シリーズ・レーベル・月・ジャンル・まとめ記事・セール（特集ごと・履歴）のページの数、カレンダー（.ics）の数、過去の作品の一覧に並ぶ本数、
 * FANZA同人・FANZAゲームのページの数（floors。作品ページ・サークル/ブランドのページも全部入れる。動画の作品ページより先に枠を取る。2026-10-09。lib/floors.js の floorFileCount）、
 * 作品検索の続きのファイルの数（search。2026-10-11） */
export function nonItemFileCount({ actress = 0, maker = 0, series = 0, label = 0, month = 0, tag = 0, weekly = 0, sale = 0, ics = 0, archiveItems = 0, floors = 0, search = 0 } = {}, fixed = FIXED_FILES, pageSize = ARCHIVE_PAGE_SIZE) {
  return fixed + actress + maker + series + label + month + tag + weekly + sale + ics + floors + search + Math.max(1, Math.ceil(archiveItems / pageSize));
}

/** 作品ページの優先順（小さいほど先）: 毎日の更新で載せた作品 → コメントのある過去作品 → そのほかの過去作品 */
export const pagePriority = (item) => (!item.catalog ? 0 : item.comment ? 1 : 2);

// 同じ優先順の中の並び: 過去作品は、人気順の順位が上の作品から（順位が分からない作品は、そのあと）。そのあとは発売日の新しい順
const rankOrder = (a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity) || 0;

/** 作品ページを作る作品の cid の集まり。budget: 作品ページに使える数 */
export function pagedCids(items, budget) {
  const sorted = [...items].sort(
    (a, b) => pagePriority(a) - pagePriority(b) || rankOrder(a, b) || b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid),
  );
  return new Set(sorted.slice(0, Math.max(0, Math.floor(budget))).map((i) => i.cid));
}

/** サイト全体の計画: { paged: 作品ページを作る cid, itemBudget, nonItem } */
export function planPages(items, counts, total = FILE_BUDGET, fixed = FIXED_FILES) {
  const nonItem = nonItemFileCount(counts, fixed);
  const itemBudget = Math.max(0, total - nonItem);
  return { paged: pagedCids(items, itemBudget), itemBudget, nonItem };
}

/** 作品へのリンク: 作品ページがあれば作品ページ、無ければFANZAの作品ページ（外部リンクの印 external: true） */
export function itemHref(item, paged) {
  if (paged.has(item.cid)) return { href: itemPath(item.cid), external: false };
  return { href: item.url || itemPath(item.cid), external: Boolean(item.url) };
}

/** 外部（FANZA）へのリンクに付ける属性（サイトのほかの「FANZAで見る」と同じ） */
export const OUTBOUND_ATTRS = { target: '_blank', rel: 'sponsored nofollow noopener noreferrer' };

/** 一覧のページを検索エンジンに出してよいか: コメントのある作品が1本でもあれば true（古い過去作品だけの一覧は、FANZAへのリンクが並ぶだけなので出さない）。
 * 作品がまだ1本も無い（最初の状態の）一覧は、これまでどおり出す */
export const listIndexable = (items) => items.length === 0 || items.some((i) => String(i.comment ?? '').trim() !== '');

/** 作品ページを検索エンジンに出してよいか: 作品ページがあり、コメントがある作品だけ（sitemap に入れる作品） */
export const itemIndexable = (item, paged) => paged.has(item.cid) && String(item.comment ?? '').trim() !== '';

/** 出演者・メーカーの発売日カレンダー（.ics）を作るか: 毎日の更新で載せた作品（新作・予約）がある人・メーカーだけ。
 * 過去作品だけの人の分まで作ると、ファイルが多くなりすぎるため（新作が載れば、その日から作る） */
export const hasCalendar = (group) => group.items.some((i) => !i.catalog);

/** 出演者・メーカーのページに並べる作品（新しい順に limit 本まで）と、並べきれなかった本数 */
export function entityListing(items, limit) {
  const shown = items.slice(0, Math.max(0, limit));
  return { shown, hidden: items.length - shown.length };
}
