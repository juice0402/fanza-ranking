// FANZA同人・FANZAゲーム（PCゲーム・DL版）のページの部品（画面に依存しない。tests/test_floors.mjs）。
// 運営者の希望「『FANZA セール』で上に来る、同人・ゲームのセール情報のページも」→「同人 1,000本・ゲーム 500本」（2026-10-09）。
// データは毎日の更新が集める site/src/data/doujin.json・game.json（scripts/doujin_game.py。形は scripts/floor_data.py）。
// 未成年を連想させる作品は、集めるときに入れていない。ここでも、タイトル・ジャンル・シリーズ・サークル/ブランド・作家の名前を調べて、念のため外す（二重の備え）。
import { FANZA_HOSTS, FANZA_LINK_HOSTS, isDay, safeHttpsUrl } from './items.js';
import { isMinorTitle } from './gacha.js';

/** 売り場の設定。label: 正式な名前・short: 短い名前・maker: サークル/ブランドの呼び方・kind: 作品の呼び方 */
export const FLOORS = {
  doujin: { key: 'doujin', label: 'FANZA同人', short: '同人', maker: 'サークル', kind: '同人作品' },
  game: { key: 'game', label: 'FANZAゲーム', short: 'ゲーム', maker: 'ブランド', kind: 'PCゲーム' },
};
export const FLOOR_KEYS = Object.keys(FLOORS);

export const floorPath = (key) => `/${key}/`;
export const floorRankingPath = (key) => `/${key}/ranking/`;
export const floorSalePath = (key) => `/${key}/sale/`;
export const floorItemPath = (key, cid) => `/${key}/item/${cid}/`;
export const floorMakerIndexPath = (key) => `/${key}/maker/`;
export const floorMakerPath = (key, id) => `/${key}/maker/${id}/`;

export const FLOOR_RANKING_LIMIT = 100; // 人気ランキングのページに並べる本数
export const FLOOR_HUB_SHOWN = 12; // 売り場のトップの、それぞれの棚に並べる本数
export const FLOOR_SALE_LIMIT = 120; // セールのページに並べる本数（同人。人気の高い順）
export const FLOOR_SALE_GROUP_LIMIT = 24; // セールのページの、セールごとの本数（ゲーム）
export const FLOOR_NEW_DAYS = 30; // 「新作で人気」に入れる、発売からの日数
export const FLOOR_MAKER_MIN = 2; // サークル・ブランドのページを作る、作品の数
export const FLOOR_MAKER_LIST = 60; // サークル・ブランドのページに並べる本数
export const FLOOR_SAMPLES = 8; // 作品ページのサンプル画像の枚数

const CID = /^[A-Za-z0-9_-]{1,40}$/;

/**
 * 同人の画像の置き場所（2026-10-09）。APIは doujin-assets.dmm.co.jp の URL を返すが、運営者のiPhoneでは、このサイトの中で表示されなかった
 * （画像を直接開くと出る。どのページから読んだかを送らないようにしても出なかった）。同じ場所の pics.dmm.co.jp（動画・ゲームの画像と同じ置き場所）に、
 * まったく同じ画像がある（表紙8枚・サンプル3枚で、中身が1バイトも違わないことを確かめた）ので、そちらを使う。集める道具（scripts/doujin_game.py の pics_url）も同じ
 */
const DOUJIN_ASSETS = 'https://doujin-assets.dmm.co.jp/';
const PICS = 'https://pics.dmm.co.jp/';
export const picsUrl = (u) => (typeof u === 'string' && u.startsWith(DOUJIN_ASSETS) ? PICS + u.slice(DOUJIN_ASSETS.length) : u);
/** 同人の画像が pics.dmm.co.jp で読めなかったら、もとの doujin-assets に1回だけ戻す（それも読めなければ隠す）。属性に入れるので、< > & " を使わない形で書く */
export const DOUJIN_IMG_ONERROR = "if(this.dataset.alt||this.src.indexOf('https://pics.dmm.co.jp/')){this.style.visibility='hidden'}else{this.dataset.alt='1';this.src='https://doujin-assets.dmm.co.jp/'+this.src.slice(23)}";
const minor = (text) => Boolean(text) && isMinorTitle(text);
const names = (list, limit) => (Array.isArray(list) ? list : []).map((s) => String(s ?? '').trim()).filter(Boolean).slice(0, limit);
const yen = (v) => (Number.isInteger(v) && v > 0 && v < 10_000_000 ? v : null);
const entry = (id, name) => {
  const n = Number(id);
  const text = String(name ?? '').trim();
  return Number.isInteger(n) && n > 0 && text ? { id: n, name: text } : null;
};

/** 値引きの割合（%。四捨五入。サイトのほかの所と同じ）。分からなければ 0 */
export const offOf = (price, listPrice) => (price && listPrice && price < listPrice ? Math.round((1 - price / listPrice) * 100) : 0);

/**
 * doujin.json・game.json → { key, updated, items }。items は人気の高い順（順位の無い作品はそのあと、発売日の新しい順）。
 * 作品: { floor, cid, title, url, image_url, sample_images, date, dateKey, maker:{id,name}|null, authors, series:{id,name}|null,
 *         genres, formats, sales, price, listPrice, off, campaign:{title,begin}|null, comment, updated, rank, upcoming }
 */
export function normalizeFloor(raw, key, today) {
  const data = raw && typeof raw === 'object' ? raw : {};
  const ranks = data.ranks && typeof data.ranks === 'object' ? data.ranks : {};
  const seen = new Set();
  const items = [];
  for (const r of Array.isArray(data.items) ? data.items : []) {
    if (!r || typeof r !== 'object') continue;
    const cid = String(r.cid ?? '');
    const title = String(r.title ?? '').trim();
    const date = String(r.date ?? '');
    const url = safeHttpsUrl(r.url, FANZA_LINK_HOSTS);
    if (!CID.test(cid) || seen.has(cid) || !title || !isDay(date.slice(0, 10)) || !url) continue;
    const genres = names(r.genres, 30);
    const formats = names(r.formats, 12);
    const sales = names(r.sales, 8);
    const authors = names(r.authors, 4);
    const maker = entry(r.maker_id, r.maker);
    const series = entry(r.series_id, r.series);
    // 未成年を連想させる作品は出さない（集めるときにも外している。二重の備え）
    if ([title, ...genres, ...formats, ...sales, ...authors, maker?.name, series?.name].some(minor)) continue;
    seen.add(cid);
    const price = yen(r.price);
    const listPrice = yen(r.list_price);
    const rank = Number.isInteger(ranks[cid]) && ranks[cid] > 0 ? ranks[cid] : null;
    const camp = r.campaign && typeof r.campaign === 'object' && String(r.campaign.title ?? '').trim()
      ? { title: String(r.campaign.title).trim().slice(0, 40), begin: isDay(String(r.campaign.begin ?? '')) ? r.campaign.begin : '' }
      : null;
    items.push({
      floor: key,
      cid,
      title,
      url,
      image_url: safeHttpsUrl(picsUrl(r.image_url), FANZA_HOSTS),
      sample_images: (Array.isArray(r.sample_images) ? r.sample_images : []).map((u) => safeHttpsUrl(picsUrl(u), FANZA_HOSTS)).filter(Boolean),
      date,
      dateKey: date.slice(0, 10),
      maker,
      authors,
      series,
      genres,
      formats,
      sales,
      price,
      listPrice: listPrice && price && price <= listPrice ? listPrice : null,
      off: offOf(price, listPrice),
      campaign: camp,
      comment: r.comment_kind === 'claude' ? String(r.comment ?? '').trim() : '',
      updated: isDay(r.updated) ? r.updated : '',
      rank,
      upcoming: date.slice(0, 10) > today,
    });
  }
  items.sort(byRank);
  return { key, updated: isDay(data.updated) ? data.updated : '', items };
}

/** 人気の高い順（順位の無い作品はそのあと、発売日の新しい順・品番の順） */
export function byRank(a, b) {
  return (a.rank ?? Infinity) - (b.rank ?? Infinity) || b.dateKey.localeCompare(a.dateKey) || (a.cid < b.cid ? -1 : a.cid > b.cid ? 1 : 0);
}

/** 人気ランキング（発売済みで順位のある作品を、順位の順に limit 本） */
export const floorRanking = (items, limit = FLOOR_RANKING_LIMIT) => items.filter((i) => i.rank && !i.upcoming).sort(byRank).slice(0, limit);

/** 新作で人気（発売から days 日のうちの作品を、人気の高い順に） */
export function floorNewPopular(items, today, limit = FLOOR_HUB_SHOWN, days = FLOOR_NEW_DAYS) {
  const from = new Date(Date.parse(today + 'T00:00:00Z') - days * 86400000).toISOString().slice(0, 10);
  return items.filter((i) => !i.upcoming && i.dateKey >= from && i.rank).sort(byRank).slice(0, limit);
}

/** 予約（発売日の近い順） */
export const floorUpcoming = (items) => items.filter((i) => i.upcoming).sort((a, b) => a.dateKey.localeCompare(b.dateKey) || byRank(a, b));

/**
 * ゲームの札のうち、値下げのセール（「最大90%OFFセール【感謝祭オータム2026】」「500円セール」など）か。
 * 「3点以上で5%OFFクーポン」のようなクーポン・「最大16%ポイント還元キャンペーン」は、ほぼ全部の作品に付くので、セール中とは数えない（2026-10-09 に本物で確かめた: 500本のうち478本）
 */
export const isSaleTag = (t) => /セール/.test(t) && !/クーポン|還元/.test(t);

/** セール中か: 値引きが分かる作品（同人）・値下げのセールの札がある作品（ゲーム） */
export const onSale = (item) => item.off > 0 || item.sales.some(isSaleTag);

/** セール中の作品（人気の高い順） */
export const floorSaleItems = (items, limit = Infinity) => items.filter((i) => !i.upcoming && onSale(i)).sort(byRank).slice(0, limit);

/** いちばん大きい割引（%。分からなければ 0） */
export const floorMaxOff = (items) => items.reduce((m, i) => Math.max(m, i.off || 0), 0);

/** 値下げのセールの札ごとのまとまり（ゲーム）: [{ title, items（人気の高い順）, total }]。対象の多い順。札の名前の「最大90%OFF」は、FANZAが付けたセールの名前のまま */
export function saleTagGroups(items, perGroup = FLOOR_SALE_GROUP_LIMIT) {
  const map = new Map();
  for (const i of items) {
    if (i.upcoming) continue;
    for (const t of i.sales.filter(isSaleTag)) {
      if (!map.has(t)) map.set(t, []);
      map.get(t).push(i);
    }
  }
  return [...map]
    .map(([title, list]) => ({ title, total: list.length, items: [...list].sort(byRank).slice(0, perGroup) }))
    .sort((a, b) => b.total - a.total || (a.title < b.title ? -1 : 1));
}

/** クーポン・ポイント還元の札（ゲーム）: [{ title, total }]。対象の多い順（セールのページでは、名前と本数だけを出す） */
export function couponTags(items) {
  const counts = new Map();
  for (const i of items) for (const t of i.sales) if (!isSaleTag(t)) counts.set(t, (counts.get(t) ?? 0) + 1);
  return [...counts].map(([title, total]) => ({ title, total })).sort((a, b) => b.total - a.total || (a.title < b.title ? -1 : 1));
}

/** ゲームの作品ページの札から、セールのページの中の行き先（セールなら、その見出し。クーポン・ポイント還元なら、その欄） */
export const saleTagHref = (key, t) => `${floorSalePath(key)}#${isSaleTag(t) ? saleTagAnchor(t) : 'coupons'}`;

/** セールの札の、ページの中の見出しの id（ゲームのセールのページ。札の名前から決まる短い印） */
export function saleTagAnchor(title) {
  let h = 0;
  for (const ch of String(title)) h = (h * 31 + ch.codePointAt(0)) >>> 0;
  return `tag-${h.toString(36)}`;
}

/** サークル・ブランドごとのまとまり（作品が min 本以上）: [{ id, name, path, items（人気の高い順）, total }]。作品の多い順・名前の順 */
export function floorMakers(items, key, min = FLOOR_MAKER_MIN) {
  const map = new Map();
  for (const i of items) {
    if (!i.maker) continue;
    if (!map.has(i.maker.id)) map.set(i.maker.id, { id: i.maker.id, name: i.maker.name, items: [] });
    map.get(i.maker.id).items.push(i);
  }
  return [...map.values()]
    .filter((g) => g.items.length >= min)
    .map((g) => ({ ...g, path: floorMakerPath(key, g.id), total: g.items.length, items: [...g.items].sort(byRank) }))
    .sort((a, b) => b.total - a.total || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

/**
 * 見出し・「多いジャンル」に出してよいジャンル（舞台・関係・作品の形を表す、おだやかなものだけ。scripts/claude_comments.py の FLOOR_COMMENT_GENRES と同じ。
 * tests/test_floors.mjs で突き合わせ）。作品ページのジャンルの欄には、FANZAのジャンルをそのまま出す（動画と同じ）
 */
export const FLOOR_GENRE_OK = ['巨乳', '人妻・主婦', '人妻', '熟女', 'ギャル', 'お姉さん', 'OL', 'メイド', 'ナース', '巫女', 'シスター', 'エルフ', '魔法使い・魔女',
  '女騎士', 'ファンタジー', '異世界', '異世界転生', '恋愛', '純愛', 'ラブラブ・あまあま', 'ラブコメ', 'ハーレム', 'コメディ', 'ギャグ',
  '日常・生活', 'シリアス', 'ほのぼの', 'バトル', 'アクション', 'RPG', 'アドベンチャー', 'シミュレーション', 'ノベル', 'パズル',
  '動画・アニメーション', 'アニメーション', 'フルカラー', 'ボイス付き', '癒し', '耳かき', 'バイノーラル/ダミヘ', 'ASMR', '水着',
  '着物・和服', '褐色・日焼け', 'スレンダー', 'めがね', 'コスプレ', '温泉・銭湯', '旅行', 'オフィス・職場', '同棲', '夫婦', '不倫',
  '浮気', '未亡人', 'アイドル・芸能人', 'スポーツ', 'SF', 'ホラー', 'ミステリー', '歴史', '和風', 'ダークファンタジー', 'ケモミミ',
  '獣人', '天使・悪魔', 'お嬢様・令嬢', '王女・姫', '主従', '上司・部下'];
const GENRE_OK = new Set(FLOOR_GENRE_OK);

/** 中身のジャンルの多い順（数えるのは作品の数。おだやかなジャンル FLOOR_GENRE_OK だけ。上から limit 個）: [{ name, count }] */
export function topGenres(items, limit = 8) {
  const counts = new Map();
  for (const i of items) for (const g of new Set(i.genres)) if (GENRE_OK.has(g)) counts.set(g, (counts.get(g) ?? 0) + 1);
  return [...counts].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || (a.name < b.name ? -1 : 1)).slice(0, limit);
}

/** 作品ページの「同じサークル/ブランドの作品」（その作品を除いて、人気の高い順に limit 本） */
export const sameMaker = (item, groupsById, limit = 6) => (item.maker ? (groupsById.get(item.maker.id)?.items ?? []) : []).filter((i) => i.cid !== item.cid).slice(0, limit);

/** 作品ページの「○○で人気の作品」: その作品のいちばん上のジャンル（ほかの作品にも多いもの）で、人気の高い順に limit 本（exclude の作品は除く） */
export function popularInFloorGenre(item, items, exclude = new Set(), limit = 6) {
  const counts = new Map();
  for (const i of items) for (const g of i.genres) counts.set(g, (counts.get(g) ?? 0) + 1);
  const genre = [...item.genres].filter((g) => GENRE_OK.has(g) && (counts.get(g) ?? 0) >= 4).sort((a, b) => counts.get(b) - counts.get(a))[0] ?? '';
  if (!genre) return { genre: '', items: [] };
  const list = items.filter((i) => i.cid !== item.cid && !exclude.has(i.cid) && !i.upcoming && i.genres.includes(genre)).sort(byRank).slice(0, limit);
  return { genre, items: list };
}

const comma = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');

/** カードの札（同人「30%OFF」・ゲーム「セール中」。人気ランキングでは順位） */
export const saleBadgeOf = (item) => (item.off > 0 ? `${item.off}%OFF` : item.sales.some(isSaleTag) ? 'セール中' : '');

/** カードの価格の1行（同人「1,155円（通常1,650円）」・ゲーム「8,800円」。分からなければ ''） */
export function priceNote(item) {
  if (!item.price) return '';
  return item.listPrice && item.price < item.listPrice ? `${comma(item.price)}円（通常${comma(item.listPrice)}円）` : `${comma(item.price)}円`;
}

/** カードのサークル/ブランドの1行（ゲームは作家も1人） */
export function makerLine(item) {
  const parts = [item.maker?.name ?? ''];
  if (item.floor === 'game' && item.authors.length > 0) parts.push(`作家 ${item.authors[0]}`);
  return parts.filter(Boolean).join('｜');
}

/** 作品ページのタイトル（検索に出る名前）: 「タイトル｜FANZA同人（サークル）」の形 */
export function floorItemTitle(item, siteName) {
  const f = FLOORS[item.floor];
  return `${item.title}｜${f.label}${item.maker ? `（${item.maker.name}）` : ''}｜${siteName}`;
}

/** 作品ページの説明文（コメントがあればコメント、無ければ事実の1文） */
export function floorItemDescription(item) {
  const f = FLOORS[item.floor];
  const day = `${Number(item.dateKey.slice(0, 4))}年${Number(item.dateKey.slice(5, 7))}月${Number(item.dateKey.slice(8, 10))}日`;
  const base = `${f.label}の${f.kind}「${item.title.slice(0, 40)}」${item.maker ? `（${f.maker}：${item.maker.name}）` : ''}。${day}${item.upcoming ? '発売予定' : '発売'}。`;
  return (item.comment ? `${item.comment} ` : '') + base;
}

/** 売り場ごとのファイルの数（作品ページ・サークル/ブランドのページ・一覧・トップ・ランキング・セール）。サイト全体の計画（lib/plan.js）に足す */
export const floorFileCount = (floor, makers) => (floor.items.length > 0 ? floor.items.length + makers.length + 4 : 0);
