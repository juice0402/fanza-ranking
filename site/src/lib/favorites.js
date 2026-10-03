// お気に入り機能のための、サイト側の部品（画面に依存しない）。
// ブラウザ側の動き（☆の付け外し・保存）は site/public/favorites.js。
export const FAVORITES_PATH = '/favorites/';
export const FAVORITES_INDEX_PATH = '/data/favorites-index.json';
export const FAVORITES_INDEX_DAYS = 60; // 索引に入れる作品: 発売日がこの日数前から先（予約も全部）

const minusDays = (day, n) => new Date(Date.UTC(+day.slice(0, 4), +day.slice(5, 7) - 1, +day.slice(8, 10)) - n * 86400000).toISOString().slice(0, 10);

/**
 * 「お気に入りの出演者・メーカーの新作」を、ブラウザ側で探すための索引。
 * 短い名前の項目 {c: 品番, t: タイトル, d: 発売日, a: 出演者, m: メーカー, i: 画像} を、発売日の新しい順に並べる。
 * 古い作品まで入れると大きくなるので、最近の作品と予約だけにする。
 * pages: 専用ページがある出演者・メーカーの {名前: 短い名前}（{ actress: {...}, maker: {...} }）。
 *   ☆を付けたときは専用ページが無かった人（作品が1本）に、あとからページができたとき、「お気に入り」ページでリンクを出すため。
 */
export function buildFavoritesIndex(items, today, days = FAVORITES_INDEX_DAYS, pages = { actress: {}, maker: {} }) {
  const from = minusDays(today, days);
  return {
    generated: today,
    pages,
    items: items
      .filter((i) => i.dateKey >= from)
      .sort((a, b) => b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid))
      .map((i) => ({ c: i.cid, t: i.title, d: i.dateKey, a: i.actress, m: i.maker === '不明' ? '' : i.maker, i: i.image_url })),
  };
}

/** 出演者・メーカーのまとまり（groupByActress / groupByMaker の結果）→ {名前: 短い名前}（索引の pages 用） */
export const pageSlugMap = (groups) => Object.fromEntries(groups.map((g) => [g.name, g.slug]));

/** 作品の☆ボタンに持たせる情報（data-* に入れる値） */
export const workFavoriteAttrs = (item) => ({
  'data-fav-type': 'work',
  'data-fav-key': item.cid,
  'data-title': item.title,
  'data-image': item.image_url,
  'data-date': item.dateKey,
  'data-actress': item.actress.join('、'),
  'data-maker': item.maker === '不明' ? '' : item.maker,
});
