// JSON（Pythonが毎日貯めているデータ）を読み込んで、画面で使う形にします。
import raw from '../data/new_releases.json';
import rawRoundups from '../data/roundups.json';
import { normalizeItems, splitByRelease, jstToday, groupByActress, groupByMaker, indexByName } from './items.js';
import { normalizeRoundups } from './roundups.js';
import { groupByMonth, groupByTag, monthPathByKey } from './collections.js';
import { buildFactsContext } from './facts.js';
import { buildActressSearchIndex, indexCoverage, normalizeDirectory, normalizeProfiles, profileByName, profileCoverage, rankingForDisplay } from './profiles.js';
import { hasCalendar, planPages } from './plan.js';
import { bestRank, catalogAllRank, normalizePopularity } from './popularity.js';
import { normalizeSale } from './sale.js';

// 出演者データ・売れ筋ランキングは、毎日の更新が作るファイル。まだ無いとき（最初の更新の前）でもビルドが止まらないよう、
// import ではなく glob で読む（無ければ空として扱う）
const optional = import.meta.glob('../data/{actresses,ranking,actress_directory,catalog_rank,popularity,sale}.json', { eager: true, import: 'default' });
const optionalData = (name) => optional[`../data/${name}.json`] ?? null;

// 過去作品（カタログ）: 毎日の更新が、FANZAの人気順に少しずつ集める発売済み作品（data/catalog/YYYY-MM.json。コメントは無いか、あとから Claude が書く）。
// まだ無ければ空。毎日の更新で載せた作品（new_releases.json）と同じ作品があれば、そちらを使う
const catalogShards = import.meta.glob('../data/catalog/*.json', { eager: true, import: 'default' });
const catalogRaw = Object.keys(catalogShards).sort().flatMap((k) => (Array.isArray(catalogShards[k]) ? catalogShards[k] : []));

export const today = jstToday();
// 人気順（毎日の更新が、その日のFANZAの人気順を取り直したもの）。popNew: 新着の人気順 / popAll: 全体の人気順（分からなければ null）
export const popularity = normalizePopularity(optionalData('popularity'));
// セール・キャンペーン（毎日の更新が、FANZA公式のAPIから、その日に見かけたセール中の作品を保存したもの。lib/sale.js）
export const sale = normalizeSale(optionalData('sale'));
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
export const factsContext = buildFactsContext(all);

// 週のまとめ記事（Claudeが毎週月曜に書く。まだ1本も無いときは空）
export const roundups = normalizeRoundups(rawRoundups, curated);

// 作品ページを作る作品（サイト全体を2万ファイル以内に収める。lib/plan.js）
export const pagePlan = planPages(all, {
  actress: actressGroups.length,
  maker: makerGroups.length,
  month: monthGroups.length,
  tag: tagGroups.length,
  weekly: roundups.length,
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
export const actressSearchIndex = buildActressSearchIndex(profiles, all, actressByName, today, directory);
export const actressIndexCoverage = indexCoverage(actressSearchIndex);

// 売れ筋ランキング（FANZAの人気順の上位3本）。無い・古いときは null（画面に出さない）
export const ranking = rankingForDisplay(optionalData('ranking'), today, new Set(all.filter((i) => i.vr).map((i) => i.cid)));
