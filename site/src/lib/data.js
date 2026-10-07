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
import { campaignPages, normalizeSale, normalizeSaleHistory } from './sale.js';
import { normalizeAgencies, withAgencies } from './agencies.js';
import { eventsByName, normalizeEvents, upcomingEvents } from './events.js';
import { HOT_GENRE_SKIP, normalizeToday } from './topics.js';
import { LABEL_MIN_ITEMS, LABEL_PAGE_MAX, SERIES_MIN_ITEMS, SERIES_PAGE_MAX, TAG_PAGE_GENRES } from '../config.js';
import { genreTopLists, groupByEntry } from './insights.js';
import { buildItemsIndex } from './search.js';

// 出演者データ・売れ筋ランキングは、毎日の更新が作るファイル。まだ無いとき（最初の更新の前）でもビルドが止まらないよう、
// import ではなく glob で読む（無ければ空として扱う）
const optional = import.meta.glob('../data/{actresses,ranking,actress_directory,catalog_rank,popularity,sale,sale_history,today,agencies,events,rank_history,monthly}.json', { eager: true, import: 'default' });
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
// 毎日の更新で載せた作品（新作・予約。コメントがある）。トップ・月ごと/ジャンルごとのページ・お気に入り・カレンダー・まとめ記事は、これだけを使う
export const curated = normalizeItems(raw).map((i) => ({ ...i, popAll: popularity.allRank.get(i.cid) ?? null, popNew: popularity.newRank.get(i.cid) ?? null }));
const curatedCids = new Set(curated.map((i) => i.cid));
// （FANZAのURLが無い過去作品は、作品ページが無いときのリンク先が無いので、載せない）
// rank: 作品ページを作る順の順位（全体の人気順と新着の人気順の、上のほう。data/catalog_rank.json・popularity.json）。作品ページ・コメントは、人気の高い作品から
export const catalog = normalizeItems(catalogRaw)
  .filter((i) => !curatedCids.has(i.cid) && i.url)
  .map((i) => {
    const popAll = catalogAllRank(catalogRanks, i.cid);
    const popNew = popularity.newRank.get(i.cid) ?? null;
    return { ...i, catalog: true, popAll, popNew, rank: bestRank(popAll, popNew) };
  });
// すべての作品（毎日の更新で載せた作品＋過去作品）。作品ページ・過去の作品の一覧・出演者/メーカーのページ・「この作品のデータ」欄は、これを使う
export const all = [...curated, ...catalog];
export const { released, upcoming } = splitByRelease(curated, today);
export const allReleased = splitByRelease(all, today).released;

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
export const factsContext = buildFactsContext(all);
// シリーズ・レーベルのページ（2026-10-07。作品が3本以上のもの。名前が未成年を連想させるもの・メーカーと同じ名前のレーベルは作らない。lib/insights.js）
export const seriesGroups = groupByEntry(all, 'series', { minItems: SERIES_MIN_ITEMS, max: SERIES_PAGE_MAX });
export const labelGroups = groupByEntry(all, 'label', { minItems: LABEL_MIN_ITEMS, max: LABEL_PAGE_MAX });
export const seriesById = new Map(seriesGroups.map((g) => [g.id, g]));
export const labelById = new Map(labelGroups.map((g) => [g.id, g]));
// ジャンルごとの人気の作品（作品ページの「○○で人気の作品」。中身のジャンルだけ。1回だけ数える）
export const genreTops = genreTopLists(all, contentGenres, today);

// 週のまとめ記事（Claudeが毎週月曜に書く。まだ1本も無いときは空）
export const roundups = normalizeRoundups(rawRoundups, curated);
// 月のまとめ記事（Claudeが毎月1日に書く。月のページのいちばん上に出す。まだ無いときは空。2026-10-07 から）
export const monthly = normalizeMonthly(optionalData('monthly'), curated);
export const monthlyByMonth = new Map(monthly.map((r) => [r.month, r]));

// 作品ページを作る作品（サイト全体を2万ファイル以内に収める。lib/plan.js）
export const pagePlan = planPages(all, {
  actress: actressGroups.length,
  maker: makerGroups.length,
  series: seriesGroups.length + (seriesGroups.length > 0 ? 1 : 0), // ＋一覧のページ
  label: labelGroups.length + (labelGroups.length > 0 ? 1 : 0),
  month: monthGroups.length,
  tag: tagGroups.length,
  weekly: roundups.length,
  sale: saleCampaignPages.length + 1, // 特集ごとのページと「セールはいつ？」のページ
  ics: calendarActressGroups.length + calendarMakerGroups.length,
  archiveItems: allReleased.length,
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

// 作品検索の索引（/data/items-index.json と、検索ページの「はじめの一覧」が同じものを使う。作るのは1回だけ。lib/search.js）
let itemsIndexCache = null;
export function itemsIndex() {
  if (!itemsIndexCache) itemsIndexCache = buildItemsIndex(all.filter((i) => paged.has(i.cid)), today);
  return itemsIndexCache;
}
