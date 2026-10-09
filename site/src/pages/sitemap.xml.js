// 検索エンジンに教えるための地図（/sitemap.xml）を、ビルド時に自動で作ります。
// lastmod（最後に変わった日）は、データにある updated（コメントを変えた日）から付けます。分からないページには付けません。
// 検索エンジンに出さない（noindex の）ページ（コメントの無い作品ページ・過去作品だけの一覧）は、地図にも入れません。
import { all, allReleased, events, paged, popularity, sale, saleCampaignPages, saleHistory, released, today, upcoming, upcomingEventList, actressGroups, makerGroups, roundups, monthGroups, monthlyByMonth, tagGroups, seriesGroups, labelGroups, activeFloors, floors, floorMakerGroups, floorCollectionGroups, floorEntityRankings, floorSaleHistory, floorSalePageGroups, tenYen, tenYenFloors, reviewRanking, reviews, floorReviewRankings } from '../lib/data.js';
import { REVIEW_RANKING_MIN_ITEMS, REVIEW_RANKING_PATH, floorReviewRankingPath } from '../lib/reviews.js';
import { FLOOR_COLLECTION_KINDS, FLOOR_HUB_SHOWN, floorEntityIndexable, floorEntityRankingPath, collectionIndexIndexable, collectionIndexable, floorCollectionIndexPath, floorSaleHistoryIndexable, floorSaleHistoryPath, floorSalePageIndexable, FLOOR_RANKING_LIMIT, FLOOR_SALE_LIMIT, floorItemPath, floorMakerIndexPath, floorNewPopular, floorPath, floorRanking, floorRankingPath, floorSaleItems, floorSalePath, floorUpcoming } from '../lib/floors.js';
import { LABEL_INDEX_PATH, SERIES_INDEX_PATH } from '../lib/insights.js';
import { EVENT_PATH } from '../lib/events.js';
import { itemIndexable, listIndexable } from '../lib/plan.js';
import { RANKING_PATH, newRanking } from '../lib/popularity.js';
import { SALE_HISTORY_PATH, SALE_PATH, isTenYenCampaign, saleGroups } from '../lib/sale.js';
import { TEN_YEN_PATH, tenYenIndexable, tenYenPath } from '../lib/ten-yen.js';
import { isMinorTitle } from '../lib/gacha.js';
import { MONTH_INDEX_PATH, TAG_INDEX_PATH } from '../lib/collections.js';
import {
  ABOUT_PATH,
  ABOUT_UPDATED,
  ACTRESS_INDEX_PATH,
  ARCHIVE_PAGE_SIZE,
  HOME_RELEASED_LIMIT,
  HOME_UPCOMING_LIMIT,
  MAKER_INDEX_PATH,
  archivePageCount,
  buildSitemap,
  itemPath,
  listLastmod,
} from '../lib/items.js';
import { WEEKLY_INDEX_PATH, weeklyPath } from '../lib/roundups.js';

export function GET() {
  const home = [...released.slice(0, HOME_RELEASED_LIMIT), ...upcoming.slice(0, HOME_UPCOMING_LIMIT)];
  const archive = Array.from({ length: archivePageCount(allReleased.length) }, (_, i) => allReleased.slice(i * ARCHIVE_PAGE_SIZE, (i + 1) * ARCHIVE_PAGE_SIZE))
    .map((items, i) => ({ path: `/archive/${i + 1}/`, items }))
    .filter((p) => listIndexable(p.items))
    .map((p) => ({ path: p.path, lastmod: listLastmod(p.items, today) }));
  // 人気ランキング（作品が無い・コメントのある作品が1本も無いあいだは、ページが noindex なので入れない）
  const rankingPages = [
    [RANKING_PATH, newRanking(all, today)],
  ].filter(([, list]) => list.length > 0 && listIndexable(list)).map(([path]) => ({ path, lastmod: popularity.date || today }));
  // セール・キャンペーン（作品が無い・コメントのある作品が1本も無いあいだは、ページが noindex なので入れない）
  const saleItems = saleGroups(all, sale, today).flatMap((g) => g.items);
  if (saleItems.length > 0 && listIndexable(saleItems)) rankingPages.push({ path: SALE_PATH, lastmod: sale.date || today });
  // 特集ごとのページ（開催中で、コメントのある作品があるものだけ。開催していないあいだは noindex）と「FANZAのセールはいつ？」
  for (const p of saleCampaignPages) {
    if (!isTenYenCampaign(p.title) && p.active && p.active.items.length > 0 && listIndexable(p.active.items)) rankingPages.push({ path: p.path, lastmod: sale.date || today });
  }
  // 10円セール（2026-10-09）。まとめのページはいつも、同人・ゲームのページは、開催中か開催を見かけたことがあるときだけ（ページの側と同じ決まり）
  const tenLastmod = tenYen.checked ? tenYen.checked.slice(0, 10) : today;
  rankingPages.push({ path: TEN_YEN_PATH, lastmod: tenLastmod });
  for (const k of tenYenFloors) if (tenYenIndexable(tenYen, k)) rankingPages.push({ path: tenYenPath(k), lastmod: tenLastmod });
  if (saleHistory.rows.some((r) => !isMinorTitle(r.title))) rankingPages.push({ path: SALE_HISTORY_PATH, lastmod: saleHistory.updated || today });
  // 高評価ランキング（2026-10-10。ページの側と同じ決まり）
  if (reviewRanking.length >= REVIEW_RANKING_MIN_ITEMS && listIndexable(reviewRanking)) rankingPages.push({ path: REVIEW_RANKING_PATH, lastmod: reviews.updated || today });
  // 女優のイベント情報（1件も無いあいだは、ページが noindex なので入れない）
  if (upcomingEventList.length > 0) rankingPages.push({ path: EVENT_PATH, lastmod: events.updated || today });
  const groupPages = (groups) => groups.filter((g) => listIndexable(g.items)).map((g) => ({ path: g.path, lastmod: listLastmod(g.items, today) }));
  // FANZA同人・FANZAゲーム（2026-10-09）。どのページも、コメントのある作品が1本も無いあいだは noindex なので入れない（ページの側と同じ決まり）
  const commented = (list) => list.length > 0 && list.some((i) => i.comment);
  const floorPages = activeFloors.flatMap((k) => {
    const fl = floors[k];
    const out = [];
    const lastmod = fl.updated || today;
    const hub = [...floorRanking(fl.items, FLOOR_HUB_SHOWN), ...floorSaleItems(fl.items, FLOOR_HUB_SHOWN), ...floorNewPopular(fl.items, today), ...floorUpcoming(fl.items)];
    if (commented(hub)) out.push({ path: floorPath(k), lastmod });
    if (commented(floorRanking(fl.items, FLOOR_RANKING_LIMIT))) out.push({ path: floorRankingPath(k), lastmod });
    const saleShown = floorSaleItems(fl.items, FLOOR_SALE_LIMIT);
    if (commented(saleShown)) out.push({ path: floorSalePath(k), lastmod });
    const makers = floorMakerGroups[k].filter((g) => commented(g.items.slice(0, 60)));
    if (floorMakerGroups[k].some((g) => commented(g.items))) out.push({ path: floorMakerIndexPath(k), lastmod });
    for (const g of makers) out.push({ path: g.path, lastmod: listLastmod(g.items, today) });
    // 人気サークル/ブランド・作家ランキング（2026-10-09）。ページの側と同じ決まり
    for (const [by, list] of Object.entries(floorEntityRankings[k])) if (list.length > 0 && floorEntityIndexable(list)) out.push({ path: floorEntityRankingPath(k, by), lastmod });
    // セールごと（ゲーム）・割引ごと（同人）のページと「セールはいつ？」（2026-10-09）。ページの側と同じ決まり
    for (const p of floorSalePageGroups[k]) if (floorSalePageIndexable(p)) out.push({ path: p.path, lastmod });
    if (floorSaleHistoryIndexable(floorSaleHistory[k], fl.updated)) out.push({ path: floorSaleHistoryPath(k), lastmod: floorSaleHistory.updated || lastmod });
    if (floorReviewRankings[k].length >= REVIEW_RANKING_MIN_ITEMS && listIndexable(floorReviewRankings[k])) out.push({ path: floorReviewRankingPath(k), lastmod });
    // コレクション（ジャンル・シリーズ・作家・発売月。2026-10-09）。ページの側と同じ決まり（collectionIndexable）
    for (const kind of FLOOR_COLLECTION_KINDS) {
      const groups = floorCollectionGroups[k][kind];
      if (collectionIndexIndexable(groups)) out.push({ path: floorCollectionIndexPath(k, kind), lastmod });
      for (const g of groups) if (collectionIndexable(g)) out.push({ path: g.path, lastmod: listLastmod(g.items, today) });
    }
    for (const i of fl.items) if (i.comment) out.push({ path: floorItemPath(k, i.cid), lastmod: i.updated });
    return out;
  });
  const entries = [
    { path: '/', lastmod: listLastmod(home, today) },
    ...rankingPages,
    ...archive,
    { path: ACTRESS_INDEX_PATH, lastmod: listLastmod(actressGroups.flatMap((g) => g.items), today) },
    ...groupPages(actressGroups),
    { path: MAKER_INDEX_PATH, lastmod: listLastmod(makerGroups.flatMap((g) => g.items), today) },
    ...groupPages(makerGroups),
    // シリーズ・レーベルのページ（2026-10-07。コメントのある作品があるページだけ。一覧のページは、載せたページが1つでもあるとき）
    ...(groupPages(seriesGroups).length > 0 ? [{ path: SERIES_INDEX_PATH, lastmod: listLastmod(seriesGroups.flatMap((g) => g.items), today) }, ...groupPages(seriesGroups)] : []),
    ...(groupPages(labelGroups).length > 0 ? [{ path: LABEL_INDEX_PATH, lastmod: listLastmod(labelGroups.flatMap((g) => g.items), today) }, ...groupPages(labelGroups)] : []),
    // 月ごと・ジャンルごとのまとめページ（1つも無いあいだは、一覧ページも地図に入れない）
    // 月のページは、月のまとめ記事があれば、その公開日のほうが新しければそれ（2026-10-07）
    ...(monthGroups.length > 0
      ? [{ path: MONTH_INDEX_PATH, lastmod: listLastmod(monthGroups.flatMap((g) => g.items), today) },
        ...groupPages(monthGroups).map((e) => {
          const written = monthlyByMonth.get(e.path.slice(7, 14))?.written ?? '';
          return written > e.lastmod ? { ...e, lastmod: written } : e;
        })]
      : []),
    ...(tagGroups.length > 0 ? [{ path: TAG_INDEX_PATH, lastmod: listLastmod(tagGroups.flatMap((g) => g.items), today) }, ...groupPages(tagGroups)] : []),
    ...all.filter((item) => itemIndexable(item, paged)).map((item) => ({ path: itemPath(item.cid), lastmod: item.updated })),
    ...floorPages,
    // このサイトについて（lastmod は、中身を最後に変えた日）
    { path: ABOUT_PATH, lastmod: ABOUT_UPDATED },
    // 週のまとめ記事（1本も無いあいだは、一覧ページも地図に入れない）
    ...(roundups.length > 0
      ? [
          { path: WEEKLY_INDEX_PATH, lastmod: roundups.map((r) => r.written).sort().at(-1) },
          ...roundups.map((r) => ({ path: weeklyPath(r.week_start), lastmod: r.written })),
        ]
      : []),
  ];

  return new Response(buildSitemap(entries), {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
}
