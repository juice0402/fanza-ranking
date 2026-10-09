// JSON（Pythonが毎日貯めているデータ）を読み込んで、画面で使う形にします。
import raw from '../data/new_releases.json';
import rawRoundups from '../data/roundups.json';
import { normalizeItems, splitByRelease, jstToday, groupByActress, groupByMaker, indexByName } from './items.js';
import { normalizeRoundups } from './roundups.js';
import { normalizeMonthly } from './monthly.js';
import { groupByMonth, groupByTag, monthPathByKey } from './collections.js';
import { buildFactsContext } from './facts.js';
import { buildActressSearchIndex, indexCoverage, normalizeDirectory, normalizeProfiles, profileByName, profileCoverage, rankingForDisplay, ACTRESS_IMAGE_BASE, faceUrl } from './profiles.js';
import { hasCalendar, planPages } from './plan.js';
import { bestRank, catalogAllRank, normalizePopularity, normalizeRankHistory } from './popularity.js';
import { campaignPages, campaignSlug, isTenYenCampaign, normalizeSale, normalizeSaleHistory, saleHref } from './sale.js';
import { normalizeAgencies, withAgencies } from './agencies.js';
import { eventsByName, normalizeEvents, upcomingEvents } from './events.js';
import { HOT_GENRE_SKIP, normalizeToday } from './topics.js';
import { LABEL_MIN_ITEMS, LABEL_PAGE_MAX, SERIES_MIN_ITEMS, SERIES_PAGE_MAX, TAG_PAGE_GENRES } from '../config.js';
import { genreTopLists, groupByEntry, normalizeGenreTops } from './insights.js';
import { buildItemsIndex } from './search.js';
import { TEN_YEN_KEYS, TEN_YEN_PATH, normalizeTenYen, tenYenState } from './ten-yen.js';
import { FLOOR_REVIEW_MIN, REVIEW_RANKING_MIN_ITEMS, normalizeReviews, topRated } from './reviews.js';
import { normalizeReadings } from './kana.js';
import { FLOOR_KEYS, floorCollections, floorEntityRanking, floorFileCount, floorGachaPool, floorMakers, floorSalePages, floorSearchIndex, normalizeFloor, normalizeFloorRankHistory, normalizeFloorSaleHistory } from './floors.js';

// 出演者データ・売れ筋ランキングは、毎日の更新が作るファイル。まだ無いとき（最初の更新の前）でもビルドが止まらないよう、
// import ではなく glob で読む（無ければ空として扱う）
const optional = import.meta.glob('../data/{actresses,ranking,actress_directory,catalog_rank,popularity,sale,sale_history,today,agencies,events,rank_history,monthly,ten_yen,reviews,readings,genre_tops}.json', { eager: true, import: 'default' });
const optionalData = (name) => optional[`../data/${name}.json`] ?? null;

// 過去作品（カタログ）: 毎日の更新が、FANZAの人気順に少しずつ集める発売済み作品（data/catalog/YYYY-MM.json。コメントは無いか、あとから Claude が書く）。
// まだ無ければ空。毎日の更新で載せた作品（new_releases.json）と同じ作品があれば、そちらを使う
const catalogShards = import.meta.glob('../data/catalog/*.json', { eager: true, import: 'default' });
const catalogRaw = Object.keys(catalogShards).sort().flatMap((k) => (Array.isArray(catalogShards[k]) ? catalogShards[k] : []));

export const today = jstToday();
// 人気順（毎日の更新が、その日のFANZAの人気順を取り直したもの）。popNew: 新着の人気順 / popAll: 全体の人気順（分からなければ null）
export const popularity = normalizePopularity(optionalData('popularity'));
// 人気の動き（毎日の更新が、新着の人気順に出てきた作品の毎日の順位をためたもの。2026-10-07 から。lib/popularity.js）。cid → 記録
export const rankHistory = normalizeRankHistory(optionalData('rank_history'));
// セール・キャンペーン（毎日の更新が、FANZA公式のAPIから、その日に見かけたセール中の作品を保存したもの。lib/sale.js）
export const sale = normalizeSale(optionalData('sale'));
// セールの履歴（毎日の更新が、その日に見かけたキャンペーンを足していく。2026-10-05 から。lib/sale.js）
export const saleHistory = normalizeSaleHistory(optionalData('sale_history'));
// きょうの数字・予約の人気順（毎日の更新が集めたもの。lib/topics.js）
export const todayData = normalizeToday(optionalData('today'));
const catalogRanks = optionalData('catalog_rank');
// FANZAのレビューの評価（get_new_releases.py が毎日の取得で見かけた作品からためる。2026-10-10 から。lib/reviews.js）。cid → { avg, count }
export const reviews = normalizeReviews(optionalData('reviews'));
const reviewOfCid = (cid) => reviews.byCid.get(cid) ?? null;
// 読みがな（scripts/readings.py が FANZA公式のAPIから集める。2026-10-10 から。lib/kana.js）。readings.of('video', 'maker', 名前) → ひらがな（無ければ ''）
export const readings = normalizeReadings(optionalData('readings'));
// 毎日の更新で載せた作品（新作・予約。コメントがある）。トップ・月ごと/ジャンルごとのページ・お気に入り・カレンダー・まとめ記事は、これだけを使う
export const curated = normalizeItems(raw).map((i) => ({ ...i, popAll: popularity.allRank.get(i.cid) ?? null, popNew: popularity.newRank.get(i.cid) ?? null, review: reviewOfCid(i.cid) }));
const curatedCids = new Set(curated.map((i) => i.cid));
// （FANZAのURLが無い過去作品は、作品ページが無いときのリンク先が無いので、載せない）
// rank: 作品ページを作る順の順位（全体の人気順と新着の人気順の、上のほう。data/catalog_rank.json・popularity.json）。作品ページ・コメントは、人気の高い作品から
export const catalog = normalizeItems(catalogRaw)
  .filter((i) => !curatedCids.has(i.cid) && i.url)
  .map((i) => {
    const popAll = catalogAllRank(catalogRanks, i.cid);
    const popNew = popularity.newRank.get(i.cid) ?? null;
    return { ...i, catalog: true, popAll, popNew, rank: bestRank(popAll, popNew), review: reviewOfCid(i.cid) };
  });
// すべての作品（毎日の更新で載せた作品＋過去作品）。作品ページ・過去の作品の一覧・出演者/メーカーのページ・「この作品のデータ」欄は、これを使う
export const all = [...curated, ...catalog];
export const { released, upcoming } = splitByRelease(curated, today);
export const allReleased = splitByRelease(all, today).released;
// 高評価ランキング（FANZAのレビューが10件以上の発売済みの作品を、ならした評価の高い順に100本。/ranking/review/。lib/reviews.js）
export const reviewRanking = topRated(all, today);
// 順位は、ランキングのページがあるとき（REVIEW_RANKING_MIN_ITEMS 本以上）だけ（作品ページの「高評価ランキング○位」のリンク先が無くならないように）
export const reviewRankOf = new Map(reviewRanking.length >= REVIEW_RANKING_MIN_ITEMS ? reviewRanking.map((i, n) => [i.cid, n + 1]) : []);

// 出演者・メーカーごとのページ（作品が ENTITY_MIN_ITEMS 本以上の人・メーカーだけ）
export const actressGroups = groupByActress(all);
export const makerGroups = groupByMaker(all);
export const actressByName = indexByName(actressGroups);
export const makerByName = indexByName(makerGroups);
// 発売日カレンダー（.ics）を作る出演者・メーカー: 毎日の更新で載せた作品がある人・メーカーだけ（過去作品だけの人の分まで作ると、ファイルが多くなりすぎるため）
export const calendarActressGroups = actressGroups.filter(hasCalendar);
export const calendarMakerGroups = makerGroups.filter(hasCalendar);

// 月ごと・ジャンルごとのまとめページ（作品が少ない月・ジャンルは作らない）と、作品ページの「この作品のデータ」欄の集計
export const monthGroups = groupByMonth(curated);
export const monthByKey = monthPathByKey(monthGroups);
export const tagGroups = groupByTag(curated);
export const tagByName = indexByName(tagGroups);
// 中身のジャンル（トップの「人気のジャンル」と、セールの特集の「多いジャンル」で数える）: ジャンルのページを作るジャンルから、ベスト・総集編を除いたもの。
// ハイビジョン・単体作品のような形式のジャンルは、いつも上に来てしまうので数えない
export const contentGenres = new Set(TAG_PAGE_GENRES.filter((g) => !HOT_GENRE_SKIP.includes(g)));
// 特集（キャンペーンの名前）ごとのページ（/sale/<印>/。開催中のものと、最後に見かけてから90日のあいだのもの。lib/sale.js）
export const saleCampaignPages = campaignPages(all, sale, saleHistory, today, { genres: contentGenres });
export const saleCampaignBySlug = new Map(saleCampaignPages.map((p) => [p.slug, p]));
/** 特集（キャンペーン）へのリンク先: 10円セールの特集は10円セールのページ、ほかは特集ごとのページ（無ければ /sale/ のその特集の見出し）。c: { title, k } */
export const campaignHrefOf = (c) => (isTenYenCampaign(c.title) ? TEN_YEN_PATH : saleCampaignBySlug.get(campaignSlug(c.title))?.path ?? saleHref(c.k));
export const factsContext = buildFactsContext(all);
// シリーズ・レーベルのページ（2026-10-07。作品が3本以上のもの。名前が未成年を連想させるもの・メーカーと同じ名前のレーベルは作らない。lib/insights.js）
export const seriesGroups = groupByEntry(all, 'series', { minItems: SERIES_MIN_ITEMS, max: SERIES_PAGE_MAX });
export const labelGroups = groupByEntry(all, 'label', { minItems: LABEL_MIN_ITEMS, max: LABEL_PAGE_MAX });
export const seriesById = new Map(seriesGroups.map((g) => [g.id, g]));
export const labelById = new Map(labelGroups.map((g) => [g.id, g]));
// ジャンルごとの人気の作品（作品ページの「○○で人気の作品」。中身のジャンルだけ。1回だけ数える）
export const genreTops = genreTopLists(all, contentGenres, today);
// ジャンルの「FANZA全体で人気の作品 TOP20」（scripts/genre_tops.py が毎日。2026-10-10）。ジャンルの名前 → { date, items }
export const fanzaGenreTops = normalizeGenreTops(optionalData('genre_tops'), new Map(all.map((i) => [i.cid, i])));

// 週のまとめ記事（Claudeが毎週月曜に書く。まだ1本も無いときは空）
export const roundups = normalizeRoundups(rawRoundups, curated);
// 月のまとめ記事（Claudeが毎月1日に書く。月のページのいちばん上に出す。まだ無いときは空。2026-10-07 から）
export const monthly = normalizeMonthly(optionalData('monthly'), curated);
export const monthlyByMonth = new Map(monthly.map((r) => [r.month, r]));

// FANZA同人・FANZAゲームなどの売り場（毎日の更新が集める doujin.json・game.json など。2026-10-09 から。まだ無ければ空で、ページも作らない。lib/floors.js）
// 売り場のファイル（lib/floors.js の FLOOR_KEYS と同じ名前。glob の形は、ビルドの道具の決まりで、文字のまま書く。アニメ・素人・成人映画・コミック・写真集・VR見放題は 2026-10-10 から）
const floorShards = import.meta.glob('../data/{doujin,game,anime,amateur,cinema,comic,photo,vr}.json', { eager: true, import: 'default' });
export const floors = Object.fromEntries(FLOOR_KEYS.map((k) => [k, normalizeFloor(floorShards[`../data/${k}.json`] ?? null, k, today)]));
export const floorMakerGroups = Object.fromEntries(FLOOR_KEYS.map((k) => [k, floorMakers(floors[k].items, k)]));
export const floorMakerById = Object.fromEntries(FLOOR_KEYS.map((k) => [k, new Map(floorMakerGroups[k].map((g) => [g.id, g]))]));
/** 売り場ごとのコレクション（ジャンル・シリーズ・作家・発売月。lib/floors.js の floorCollections。2026-10-09） */
export const floorCollectionGroups = Object.fromEntries(FLOOR_KEYS.map((k) => [k, floorCollections(floors[k].items, k, today)]));
/** 売り場ごとのセールのページ（ゲームはセールの札ごと・同人は割引ごと。lib/floors.js の floorSalePages。2026-10-09） */
export const floorSalePageGroups = Object.fromEntries(FLOOR_KEYS.map((k) => [k, floorSalePages(floors[k].items, k)]));
export const floorSalePageBySlug = Object.fromEntries(FLOOR_KEYS.map((k) => [k, new Map(floorSalePageGroups[k].map((p) => [p.slug, p]))]));
// 人気の動き（毎日の順位）・セールの記録（scripts/floor_history.py が毎日足す。まだ無くてもビルドは止まらない）
const floorHistShards = import.meta.glob('../data/floor_{rank,sale}_history.json', { eager: true, import: 'default' });
export const floorRankHistory = normalizeFloorRankHistory(floorHistShards['../data/floor_rank_history.json'] ?? null);
export const floorSaleHistory = normalizeFloorSaleHistory(floorHistShards['../data/floor_sale_history.json'] ?? null);
/** 人気サークル/ブランド・作家ランキング（lib/floors.js の floorEntityRanking。2026-10-09）: { doujin: { maker: […] }, game: { maker: […], author: […] } }。作家のいない売り場（同人）は作家のランキングを作らない */
export const floorEntityRankings = Object.fromEntries(FLOOR_KEYS.map((k) => {
  const opts = (by) => ({
    hist: floorRankHistory[k],
    day: floors[k].updated,
    pathOf: by === 'maker'
      ? (id) => floorMakerById[k].get(Number(id))?.path ?? ''
      : (name) => floorCollectionGroups[k].author.find((g) => g.name === name)?.path ?? '',
  });
  const out = { maker: floorEntityRanking(floors[k].items, 'maker', opts('maker')) };
  const author = floorEntityRanking(floors[k].items, 'author', opts('author'));
  if (author.length >= 10) out.author = author;
  return [k, out];
}));
/** 運命の作品の候補（売り場ごと。トップはページの中に、作品ページは /data/<売り場>-gacha.json を読む） */
export const floorGachaPools = Object.fromEntries(FLOOR_KEYS.map((k) => [k, floorGachaPool(floors[k].items)]));
/** 作品検索の索引（/data/<売り場>-index.json と、検索のページの「はじめの一覧」） */
export const floorSearchIndexes = Object.fromEntries(FLOOR_KEYS.map((k) => [k, floorSearchIndex(floors[k].items, k, floorCollectionGroups[k], (kind, key) => readings.of(k, kind, key))]));
/** ページのある売り場（作品が1本以上） */
export const activeFloors = FLOOR_KEYS.filter((k) => floors[k].items.length > 0);
/** 売り場ごとの高評価ランキング（レビュー FLOOR_REVIEW_MIN 件以上。/<売り場>/ranking/review/。2026-10-10） */
export const floorReviewRankings = Object.fromEntries(FLOOR_KEYS.map((k) => [k, topRated(floors[k].items, today, { min: FLOOR_REVIEW_MIN })]));
export const floorReviewRankOf = Object.fromEntries(FLOOR_KEYS.map((k) => [k, new Map(floorReviewRankings[k].length >= REVIEW_RANKING_MIN_ITEMS ? floorReviewRankings[k].map((i, n) => [i.cid, n + 1]) : [])]));

// 10円セール（動画・同人・ゲーム。scripts/ten_yen.py が毎日と、開催中は1日に数回確かめる。2026-10-09 から。まだ無ければ空。lib/ten-yen.js）
export const tenYen = normalizeTenYen(optionalData('ten_yen'), {
  today,
  videoByCid: new Map(all.map((i) => [i.cid, i])),
  floorByCid: Object.fromEntries(FLOOR_KEYS.map((k) => [k, new Map(floors[k].items.map((i) => [i.cid, i]))])),
});
/** いまの様子（開催中の売り場・本数・終わり。全部の売り場） */
export const tenYenNow = tenYenState(tenYen);
const tenYenInfoMap = new Map(Object.entries(tenYen.items).flatMap(([k, list]) => list.map((i) => [`${k}:${i.cid}`, i.tenYen])));
/** その作品が、いま10円セールの対象なら { price, listPrice, off, title, end }（作品ページの札。key: 'video'・'doujin'・'game'） */
export const tenYenInfo = (key, cid) => tenYenInfoMap.get(`${key}:${cid}`) ?? null;
/** 10円セールのページのある売り場（まとめのページ /sale/10yen/ はいつも。同人・ゲームは、その売り場のページがあるときだけ） */
// 10円セールを集めている売り場（同人・ゲーム。ten_yen.py の FLOOR_KEYS と同じ）のうち、ページのある売り場
export const tenYenFloors = activeFloors.filter((k) => TEN_YEN_KEYS.includes(k));

// 作品ページを作る作品（サイト全体を2万ファイル以内に収める。lib/plan.js）
export const pagePlan = planPages(all, {
  actress: actressGroups.length,
  maker: makerGroups.length,
  series: seriesGroups.length + (seriesGroups.length > 0 ? 1 : 0), // ＋一覧のページ
  label: labelGroups.length + (labelGroups.length > 0 ? 1 : 0),
  month: monthGroups.length,
  tag: tagGroups.length,
  weekly: roundups.length,
  sale: saleCampaignPages.length + 1 + 1 + FLOOR_KEYS.length + 1 + FLOOR_KEYS.length, // 特集ごとのページと「セールはいつ？」のページ・10円セールのページ（まとめ＋売り場ごと）・高評価ランキング（動画＋売り場ごと）
  ics: calendarActressGroups.length + calendarMakerGroups.length,
  archiveItems: allReleased.length,
  floors: FLOOR_KEYS.reduce((n, k) => n + floorFileCount(floors[k], floorMakerGroups[k], floorCollectionGroups[k], floorSalePageGroups[k]), 0),
});
export const paged = pagePlan.paged;

// 出演者のプロフィール（顔写真・年齢・体型・FANZAの全作品リンク）。名前で引く
export const profiles = normalizeProfiles(optionalData('actresses'), today);
export const profilesByName = profileByName(profiles);
export const profilesCoverage = profileCoverage(profiles);
// 女優検索の名簿（FANZA公式の出演者検索の一覧。体型・身長・生年月日が載っている人）。まだ無ければ空
export const directory = normalizeDirectory(optionalData('actress_directory'), today);
// 女優の顔写真と誕生日の月日（トップの「いま人気の女優」「誕生日の近い女優」）。プロフィール（actresses.json）を先に、無ければ女優検索の名簿の値。
// 名簿に同じ名前の人が2人以上いるときは、どちらの人か決められないので使わない
const directoryByName = (() => {
  const count = new Map();
  for (const d of directory) count.set(d.name, (count.get(d.name) ?? 0) + 1);
  return new Map(directory.filter((d) => count.get(d.name) === 1).map((d) => [d.name, d]));
})();
export const faceOfName = (name, large = false) => faceUrl(profilesByName.get(name), large) || (directoryByName.get(name)?.img ? `${ACTRESS_IMAGE_BASE}${directoryByName.get(name).img}.jpg` : '');
export const birthOfName = (name) => profilesByName.get(name)?.birthMD || directoryByName.get(name)?.birthMD || '';
// 所属事務所とSNS（事務所の公式サイトから週1回。scripts/agency_links.py）。まだ無ければ空
export const agencies = normalizeAgencies(optionalData('agencies'));
export const agencyOfName = (name) => agencies.byName.get(name) ?? null;
// イベント情報（所属事務所の公式サイトのイベントの一覧から。scripts/agency_events.py が毎日集める。lib/events.js）。きょうから先のものだけ使う
export const events = normalizeEvents(optionalData('events'));
export const upcomingEventList = upcomingEvents(events, today);
export const eventsOfName = eventsByName(upcomingEventList);
// その人の、このサイトのいちばん新しい発売済みの作品の表紙（VRでない作品。顔写真が無い人の、きょうの話題のイベントの画像に使う）
export const coverOfName = (name) => actressByName.get(name)?.items.find((i) => !i.vr && i.image_url && i.dateKey <= today)?.image_url ?? '';
export const actressSearchIndex = withAgencies(buildActressSearchIndex(profiles, all, actressByName, today, directory), agencies);
export const actressIndexCoverage = indexCoverage(actressSearchIndex);

// 売れ筋ランキング（FANZAの人気順の上位3本）。無い・古いときは null（画面に出さない）
export const ranking = rankingForDisplay(optionalData('ranking'), today, new Set(all.filter((i) => i.vr).map((i) => i.cid)));

// 名前の読みがな（出演者はFANZAのプロフィール・名簿、メーカー・ジャンルは readings.json。作品検索で、ひらがなで打っても見つかるように）
export const actressReading = (name) => profilesByName.get(name)?.ruby || directoryByName.get(name)?.ruby || '';
export const nameReading = (name) => actressReading(name) || readings.of('video', 'maker', name) || readings.of('video', 'genre', name) || '';

// 作品検索の索引（/data/items-index.json と、検索ページの「はじめの一覧」が同じものを使う。作るのは1回だけ。lib/search.js）
let itemsIndexCache = null;
export function itemsIndex() {
  if (!itemsIndexCache) itemsIndexCache = buildItemsIndex(all.filter((i) => paged.has(i.cid)), today, undefined, undefined, nameReading);
  return itemsIndexCache;
}
