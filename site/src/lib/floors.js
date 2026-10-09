// FANZA同人・FANZAゲーム（PCゲーム・DL版）のページの部品（画面に依存しない。tests/test_floors.mjs）。
// 運営者の希望「『FANZA セール』で上に来る、同人・ゲームのセール情報のページも」→「同人 1,000本・ゲーム 500本」（2026-10-09）。
// データは毎日の更新が集める site/src/data/doujin.json・game.json（scripts/doujin_game.py。形は scripts/floor_data.py）。
// 未成年を連想させる作品は、集めるときに入れていない。ここでも、タイトル・ジャンル・シリーズ・サークル/ブランド・作家の名前を調べて、念のため外す（二重の備え）。
import { FANZA_HOSTS, FANZA_LINK_HOSTS, addDays, daysBetween, entitySlug, isDay, resizedImage, safeHttpsUrl } from './items.js';
import { isMinorTitle } from './gacha.js';
import { bestOf } from './popularity.js';

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
/**
 * 同人の表紙のスマホ版（運営者の「スマホのサムネは少し粗すぎた。もう少しきれいに。同じしくみを同人とゲームにも」。2026-10-09）。
 * 同人には、カードに使える小さい版が無い（90×90・100×100 の四角だけ）ので、FANZA の「縮めて返す版」（items.js の resizedImage）で、
 * 横長の表紙（560×420）を、カードは幅300（300×225・約20KB。元は 50〜120KB）、小さな棚は幅240（約15KB）にする（2026-10-09 に本物で確かめた）
 */
export const DOUJIN_CARD_W = 300;
export const DOUJIN_TINY_W = 240;
export const doujinThumb = (url, kind = 'card') => ({ src: url, small: resizedImage(url, kind === 'tiny' ? DOUJIN_TINY_W : DOUJIN_CARD_W) });
/** <picture> の中の同人の img の onerror: スマホで縮めた版が読めなければ <source> を外して元の画像に。元の画像も読めなければ DOUJIN_IMG_ONERROR */
export const DOUJIN_THUMB_ONERROR = `var s=this.previousElementSibling,m=s?s.tagName=='SOURCE'?matchMedia(s.media).matches:0:0;if(m){s.remove()}else{${DOUJIN_IMG_ONERROR}}`;
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

// ---------- コレクション（ジャンル・シリーズ・作家・発売月ごとのページ） ----------
// 運営者の希望「動画のページと同じレベルのコレクションを同人とゲームにも。SEO対策も徹底的に」（2026-10-09）。
// /doujin/genre/<印>/・/doujin/series/<FANZAの id>/・/game/author/<印>/・/doujin/month/2026-10/ と、それぞれの一覧（/doujin/genre/ など）。
// ジャンルは、おだやかなもの（FLOOR_GENRE_OK）だけ。作品が min 本以上のものだけ作る。どのページも、作品は人気の高い順

/** コレクションの種類。label: 呼び方・find: 一覧の見出し・min: ページを作る作品の数 */
export const FLOOR_COLLECTIONS = {
  genre: { label: 'ジャンル', find: 'ジャンルから探す', min: 3 },
  series: { label: 'シリーズ', find: 'シリーズから探す', min: 3 },
  author: { label: '作家', find: '作家から探す', min: 2 },
  month: { label: '発売月', find: '発売月から探す', min: 5 },
};
export const FLOOR_COLLECTION_KINDS = Object.keys(FLOOR_COLLECTIONS);
export const FLOOR_COLLECTION_LIST = 60; // 1ページに並べる本数（人気の高い順）
export const floorCollectionIndexPath = (key, kind) => `/${key}/${kind}/`;
export const floorCollectionPath = (key, kind, slug) => `/${key}/${kind}/${slug}/`;
/** 「2026-10」→「2026年10月」 */
export const monthName = (ym) => `${Number(ym.slice(0, 4))}年${Number(ym.slice(5, 7))}月`;

/**
 * 売り場の作品 → { genre: [グループ], series: […], author: […], month: […] }。
 * グループ: { kind, slug, name, path, items（人気の高い順）, total }。ジャンル・シリーズ・作家は作品の多い順（同じなら名前の順）、発売月は新しい月から
 */
export function floorCollections(items, key) {
  const maps = Object.fromEntries(FLOOR_COLLECTION_KINDS.map((k) => [k, new Map()]));
  const add = (kind, slug, name, item) => {
    const m = maps[kind];
    if (!m.has(slug)) m.set(slug, { kind, slug, name, items: [] });
    const g = m.get(slug);
    // シリーズは FANZA の id ごと（名前は、人気のいちばん高い作品のもの）。ジャンル・作家は、別の名前が同じ印になったとき（ほぼ起きない）は、はじめの名前だけ
    if (kind === 'series' || g.name === name) g.items.push(item);
  };
  for (const i of items) {
    for (const g of new Set(i.genres)) if (GENRE_OK.has(g)) add('genre', entitySlug(g), g, i);
    if (i.series) add('series', String(i.series.id), i.series.name, i);
    for (const a of new Set(i.authors)) add('author', entitySlug(a), a, i);
    add('month', i.dateKey.slice(0, 7), monthName(i.dateKey.slice(0, 7)), i);
  }
  const out = {};
  for (const kind of FLOOR_COLLECTION_KINDS) {
    const groups = [...maps[kind].values()]
      .filter((g) => g.items.length >= FLOOR_COLLECTIONS[kind].min)
      .map((g) => ({ ...g, path: floorCollectionPath(key, kind, g.slug), total: g.items.length, items: [...g.items].sort(byRank) }));
    groups.sort(kind === 'month'
      ? (a, b) => (a.slug < b.slug ? 1 : -1)
      : (a, b) => b.total - a.total || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    out[kind] = groups;
  }
  return out;
}

/** コレクションのページを検索エンジンに出してよいか: ページに並べる作品（人気の高い順に60本）に、コメントのある作品があるとき（sitemap も同じ） */
export const collectionIndexable = (group) => group.items.slice(0, FLOOR_COLLECTION_LIST).some((i) => i.comment);
/** コレクションの一覧のページ: 検索エンジンに出すページが1つでもあるとき */
export const collectionIndexIndexable = (groups) => groups.some(collectionIndexable);

/** コレクションの数字（見出しの下・説明文に使う）: セール中の本数・最大の割引・新作（発売から30日）・予約の本数 */
export function collectionFacts(items, today) {
  const sale = floorSaleItems(items);
  const from = addDays(today, -FLOOR_NEW_DAYS);
  return {
    total: items.length,
    sale: sale.length,
    maxOff: floorMaxOff(sale),
    fresh: items.filter((i) => !i.upcoming && i.dateKey >= from).length,
    upcoming: items.filter((i) => i.upcoming).length,
  };
}

/** まとまりの中で多いサークル/ブランド（作品の多い順に limit 個）: [{ id, name, count }] */
export function topMakersIn(items, limit = 8) {
  const counts = new Map();
  for (const i of items) if (i.maker) counts.set(i.maker.id, { ...i.maker, count: (counts.get(i.maker.id)?.count ?? 0) + 1 });
  return [...counts.values()].sort((a, b) => b.count - a.count || (a.name < b.name ? -1 : 1)).slice(0, limit);
}

/** いっしょに付いていることが多いジャンル（そのジャンル自身は除く。おだやかなジャンルだけ） */
export const relatedFloorGenres = (items, self, limit = 8) => topGenres(items, limit + 1).filter((g) => g.name !== self).slice(0, limit);

/** コレクションのページのタイトル（検索に出る名前）。updatedYm: 「2026年10月」 */
export function collectionTitle(f, group, updatedYm, siteName) {
  if (group.kind === 'genre') return `${f.label}「${group.name}」の人気作品一覧【${updatedYm}】（${group.total}本）｜${siteName}`;
  if (group.kind === 'series') return `${group.name}｜${f.label}のシリーズ作品一覧【${updatedYm}】（${group.total}本）｜${siteName}`;
  if (group.kind === 'author') return `${group.name}の${f.kind}一覧（${f.label}）【${updatedYm}】（${group.total}本）｜${siteName}`;
  return `${f.label} ${group.name}発売の${f.kind}・人気順（${group.total}本）｜${siteName}`;
}

/** コレクションのページの見出し */
export function collectionHeading(f, group) {
  if (group.kind === 'genre') return `${f.label}の「${group.name}」作品`;
  if (group.kind === 'series') return `${group.name}（シリーズ）`;
  if (group.kind === 'author') return `${group.name}の${f.kind}`;
  return `${group.name}発売の${f.kind}`;
}

/** コレクションのページの説明文（数えた事実だけ） */
export function collectionDescription(f, group, facts) {
  const what = group.kind === 'genre' ? `「${group.name}」のジャンルの${f.kind}`
    : group.kind === 'series' ? `シリーズ「${group.name}」の${f.kind}`
      : group.kind === 'author' ? `作家「${group.name}」の${f.kind}`
        : `${group.name}発売の${f.kind}`;
  const parts = [`${f.label}の${what}${facts.total}本を、FANZAの人気順でまとめています。`];
  if (facts.sale > 0) parts.push(`いまセール中の作品が${facts.sale}本${facts.maxOff ? `（最大${facts.maxOff}%OFF）` : ''}。`);
  if (facts.upcoming > 0) parts.push(`予約受付中の作品が${facts.upcoming}本。`);
  parts.push('毎日、日付が変わったあとに更新します。');
  return parts.join('');
}

/** 作品ページから、その作品のコレクションへのリンク（ページのあるものだけ）: { genre: Map(名前→path), series, authors: Map, month } */
export function collectionLinksFor(item, groups) {
  const bySlug = (kind) => new Map((groups[kind] ?? []).map((g) => [g.slug, g]));
  const genre = bySlug('genre');
  const author = bySlug('author');
  return {
    genres: new Map(item.genres.map((g) => [g, GENRE_OK.has(g) ? genre.get(entitySlug(g))?.path : undefined]).filter(([, p]) => p)),
    series: item.series ? bySlug('series').get(String(item.series.id)) ?? null : null,
    authors: new Map(item.authors.map((a) => [a, author.get(entitySlug(a))?.path]).filter(([, p]) => p)),
    month: bySlug('month').get(item.dateKey.slice(0, 7)) ?? null,
  };
}

/** 一覧のページの構造化データ（ItemList。作品ページへのリンクを、並びの順に limit 本） */
export function floorItemListLd(items, siteUrl, limit = 20) {
  return {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    numberOfItems: Math.min(items.length, limit),
    itemListElement: items.slice(0, limit).map((i, n) => ({ '@type': 'ListItem', position: n + 1, url: siteUrl + floorItemPath(i.floor, i.cid), name: i.title.slice(0, 100) })),
  };
}

// ---------- 人気の動き（毎日の順位。data/floor_rank_history.json。scripts/floor_history.py が毎日足す。2026-10-09） ----------
// 運営者の希望「動画と同じレベルの仕組みを同人とゲームにも」→「人気の動き」。順位は、このサイトの人気ランキングでの順位（FANZAの人気順）

export const FLOOR_TREND_TRACK = 300; // 順位を記録している深さ（floor_history.py の RANK_TRACK。tests/test_floors.mjs で突き合わせ）
export const FLOOR_TREND_DAYS = 30; // 何日分を持つか（floor_history.py の RANK_DAYS）
const histValue = (v) => (v === null ? null : Number.isInteger(v) && v >= 0 && v <= 100000 ? v : null);
const mdJp = (d) => `${+d.slice(5, 7)}月${+d.slice(8, 10)}日`;

/**
 * floor_rank_history.json → { updated, since: { doujin: 記録のいちばん古い日, game }, doujin: Map(cid → { start, n: [順位|0（圏外）|null（分からない）], best, daysIn }), game: Map }。
 * 壊れた行は捨てる。ファイルが無ければ空
 */
export function normalizeFloorRankHistory(raw) {
  const data = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  const out = { updated: isDay(data.updated) ? data.updated : '', since: {} };
  for (const key of FLOOR_KEYS) {
    const rows = data[key] && typeof data[key] === 'object' && !Array.isArray(data[key]) ? data[key] : {};
    const m = new Map();
    for (const [cid, r] of Object.entries(rows)) {
      if (!CID.test(cid) || !r || typeof r !== 'object' || !isDay(r.d)) continue;
      const n = (Array.isArray(r.r) ? r.r : []).slice(0, FLOOR_TREND_DAYS).map(histValue);
      if (!n.length) continue;
      m.set(cid, { start: r.d, n, best: bestOf(n), daysIn: n.filter((v) => v > 0).length });
      if (!out.since[key] || r.d < out.since[key]) out.since[key] = r.d;
    }
    out[key] = m;
  }
  return out;
}

/** その日の順位（記録の外・分からない日は null。0 は圏外＝300位より下） */
export function floorRankOn(hist, day) {
  if (!hist || !isDay(day)) return null;
  const i = daysBetween(day, hist.start);
  return i >= 0 && i < hist.n.length ? hist.n[i] : null;
}

/**
 * 人気ランキングのカードの下の1行: 「前日から▲3｜最高2位」。day: データの日、since: その売り場の記録の始まり（初登場の判定）。分からなければ ''。
 * 初登場＝きのうも記録していたのに、この作品の記録がきょう始まった（上位300本に入った）。再登場＝前は入っていて、きのうは圏外だった
 */
export function floorRankNote(hist, day, since = '') {
  const cur = floorRankOn(hist, day);
  if (!cur) return '';
  const prev = floorRankOn(hist, addDays(day, -1));
  const parts = [];
  if (prev > 0) {
    const d = prev - cur;
    parts.push(d > 0 ? `前日から▲${d}` : d < 0 ? `前日から▼${-d}` : '前日と同じ');
  } else if (prev === 0) parts.push('再登場');
  else if (hist.start === day && since && since < day) parts.push('初登場');
  if (hist.best && hist.best.rank < cur) parts.push(`最高${hist.best.rank}位`);
  return parts.join('｜');
}

/** 作品ページの「人気の動き」の文（f: 売り場の設定）。一度も上位300本に入っていない・順位の分かる日が2日に満たない（記録を始めたばかり）ときは [] */
export function floorTrendLines(hist, f) {
  if (!hist?.best || hist.n.filter((v) => v !== null).length < 2) return [];
  return [`${f.label}の人気ランキングで最高${hist.best.rank}位（${mdJp(addDays(hist.start, hist.best.day))}）・${FLOOR_TREND_TRACK}位以内に${hist.daysIn}日（${mdJp(hist.start)}からの記録）`];
}

/** 作品ページの「人気の動き」のグラフの下の注記 */
export const floorTrendCaption = (f) => `このサイトの${f.label}の人気ランキング（FANZAの人気順）の毎日の順位。毎日0時すぎの時点で、上位${FLOOR_TREND_TRACK}本まで記録しています。`;

/**
 * きのうから人気が上がった作品（売り場のトップ）: 発売済みで、きのうもきょうも上位300本に入っていて、3つ以上・1.25倍以上上がった作品を、
 * 上がった割合の大きい順（同じなら、いまの順位の高い順）に limit 本。[{ item, rise, cur }]
 */
export function floorRisers(items, histMap, day, limit = 6) {
  const out = [];
  for (const item of items) {
    if (item.upcoming) continue;
    const h = histMap?.get(item.cid);
    const cur = floorRankOn(h, day);
    const prev = floorRankOn(h, addDays(day, -1));
    if (cur > 0 && prev > 0 && prev - cur >= 3 && prev / cur >= 1.25) out.push({ item, rise: prev - cur, cur, ratio: prev / cur });
  }
  return out.sort((a, b) => b.ratio - a.ratio || a.cur - b.cur).slice(0, limit).map(({ item, rise, cur }) => ({ item, rise, cur }));
}

// ---------- セールのページ（ゲームはセールの札ごと・同人は割引ごと）と、セールの記録（2026-10-09） ----------
// 運営者の希望「動画と同じレベルの仕組みを同人とゲームにも。SEO対策も徹底的に」→「セールの充実」

export const FLOOR_SALE_PAGE_MIN = 3; // セールのページを作る作品の数
export const FLOOR_SALE_PAGE_LIST = 60; // セールのページに並べる本数（人気の高い順）
export const DOUJIN_OFF_BANDS = [90, 70, 50]; // 同人の割引のページ（○%OFF以上）
export const FLOOR_SALE_HISTORY_MIN_DAYS = 7; // 「セールはいつ？」を検索エンジンに出す、記録の日数（それまでは noindex）
export const floorSalePagePath = (key, slug) => `${floorSalePath(key)}${slug}/`;
export const floorSaleHistoryPath = (key) => `${floorSalePath(key)}history/`;

/** 名前から読める最大の割引（「最大90%OFF」→ 90、「半額」→ 50）。読めなければ 0（scripts/floor_history.py の off_in_title と同じ） */
export function offInTitle(title) {
  const nums = [...String(title ?? '').matchAll(/(\d{1,2})\s*[%％]\s*(?:OFF|ＯＦＦ|オフ)/g)].map((m) => Number(m[1]));
  if (nums.length) return Math.max(...nums);
  return String(title ?? '').includes('半額') ? 50 : 0;
}

/**
 * セールのページ: [{ kind: 'tag'|'off', slug, path, name, heading, off, items（人気の高い順・全部）, total }]。
 * ゲーム: 値下げのセールの札ごと（対象が3本以上。対象の多い順）。同人: 割引ごと（90%OFF以上・70%OFF以上・半額以上。3本以上）
 */
export function floorSalePages(items, key) {
  if (key === 'game') {
    return saleTagGroups(items, Infinity)
      .filter((g) => g.total >= FLOOR_SALE_PAGE_MIN)
      .map((g) => {
        const slug = entitySlug(g.title);
        return { kind: 'tag', slug, path: floorSalePagePath(key, slug), name: g.title, heading: g.title, off: offInTitle(g.title), items: g.items, total: g.total };
      });
  }
  const sale = floorSaleItems(items);
  return DOUJIN_OFF_BANDS.map((min) => {
    const list = sale.filter((i) => i.off >= min);
    const name = min === 50 ? '半額以上（50%OFF〜）' : `${min}%OFF以上`;
    return { kind: 'off', slug: `off${min}`, path: floorSalePagePath(key, `off${min}`), name, heading: `${name}の${FLOORS[key].kind}`, off: min, items: list, total: list.length };
  }).filter((p) => p.total >= FLOOR_SALE_PAGE_MIN);
}

/** 作品ページの札の行き先: セールのページがあれば、そのページ。無ければセールのページの中の見出し（saleTagHref） */
export function saleTagLink(key, t, pagesBySlug) {
  if (isSaleTag(t)) {
    const page = pagesBySlug?.get(entitySlug(t));
    if (page) return page.path;
  }
  return saleTagHref(key, t);
}

/** セールのページのタイトル（検索に出る名前）。dayLabel: 「10月9日」 */
export function floorSalePageTitle(f, page, dayLabel, siteName) {
  return page.kind === 'tag'
    ? `${page.name}の対象${f.kind}一覧【${dayLabel}更新】（${page.total}本）｜${siteName}`
    : `${f.label} ${page.name}のセール作品一覧【${dayLabel}更新】（${page.total}本）｜${siteName}`;
}

/**
 * floor_sale_history.json → { updated, doujin: { days: [{ d, n, max }]（古い順）, tags: [{ title, begin, first, last, count, off }] }, game }。
 * 壊れた行は捨てる。ファイルが無ければ空
 */
export function normalizeFloorSaleHistory(raw) {
  const data = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  const out = { updated: isDay(data.updated) ? data.updated : '' };
  const int = (v) => (Number.isInteger(v) && v >= 0 && v <= 1000000 ? v : null);
  for (const key of FLOOR_KEYS) {
    const fl = data[key] && typeof data[key] === 'object' ? data[key] : {};
    const days = (Array.isArray(fl.days) ? fl.days : [])
      .filter((d) => d && isDay(d.d) && int(d.n) !== null && int(d.max) !== null && d.max <= 100)
      .map((d) => ({ d: d.d, n: d.n, max: d.max }))
      .sort((a, b) => (a.d < b.d ? -1 : 1));
    const tags = (Array.isArray(fl.tags) ? fl.tags : [])
      .filter((t) => t && typeof t.title === 'string' && t.title.trim() && isDay(t.first) && isDay(t.last) && t.first <= t.last && !minor(t.title))
      .map((t) => ({ title: t.title.trim().slice(0, 60), begin: isDay(t.begin) ? t.begin : '', first: t.first, last: t.last, count: int(t.count) ?? 0, off: Math.min(int(t.off) ?? 0, 100) }));
    out[key] = { days, tags };
  }
  return out;
}

/** 「セールはいつ？」の記録の日数（記録の日と、きょうのデータの日）。FLOOR_SALE_HISTORY_MIN_DAYS 日に満たないあいだは、ページを検索エンジンに出さない（sitemap も同じ） */
export const floorSaleHistoryDays = (hist, updated) => new Set([...(hist?.days ?? []).map((d) => d.d), ...(isDay(updated) ? [updated] : [])]).size;
export const floorSaleHistoryIndexable = (hist, updated) => floorSaleHistoryDays(hist, updated) >= FLOOR_SALE_HISTORY_MIN_DAYS;
/** セールのページを検索エンジンに出してよいか: 並べる作品（60本）にコメントのある作品があるとき（sitemap も同じ） */
export const floorSalePageIndexable = (page) => page.items.slice(0, FLOOR_SALE_PAGE_LIST).some((i) => i.comment);

/**
 * 「セールはいつ？」の数字（データから数えた事実だけ。予想は書かない）。today: { d, n, max }（きょうのデータから数えたもの。記録にまだ無ければ足す）。
 * { days（記録の日数）, first, last, withSale（セール中の作品があった日数）, recordMax: { max, d }, today, ongoing（きょう見かけたセールの札）, ended }
 */
export function floorSaleFacts(hist, todayFacts, key) {
  const days = [...(hist?.days ?? [])];
  if (todayFacts && isDay(todayFacts.d) && !days.some((d) => d.d === todayFacts.d)) days.push(todayFacts);
  days.sort((a, b) => (a.d < b.d ? -1 : 1));
  const last = days.at(-1)?.d ?? '';
  const recordMax = days.reduce((b, d) => (d.max > (b?.max ?? 0) ? d : b), null);
  const tags = (hist?.tags ?? []).filter((t) => key !== 'game' || isSaleTag(t.title));
  const ongoing = tags.filter((t) => t.last === last).sort((a, b) => b.count - a.count || (a.title < b.title ? -1 : 1));
  const ended = tags.filter((t) => t.last < last).sort((a, b) => (a.last > b.last ? -1 : a.last < b.last ? 1 : b.count - a.count));
  return {
    days: days.length,
    list: days,
    first: days[0]?.d ?? '',
    last,
    withSale: days.filter((d) => d.n > 0).length,
    recordMax: recordMax ? { max: recordMax.max, d: recordMax.d } : null,
    today: days.at(-1) ?? null,
    ongoing,
    ended,
  };
}

/**
 * 毎日のセール中の本数のグラフ（SVG。1日1本の棒。最近 span 日）: { w, h, bars: [{ x, y, bw, bh, d, n, max }], grid: [{ v, y }], ticks: [{ x, label }] }。
 * 記録が2日に満たなければ null
 */
export function floorSaleDayChart(list, { w = 320, h = 120, span = 30 } = {}) {
  const days = (list ?? []).slice(-span);
  if (days.length < 2) return null;
  const pad = { left: 34, right: 8, top: 10, bottom: 22 };
  const from = days[0].d;
  const count = daysBetween(days.at(-1).d, from) + 1;
  const step = (w - pad.left - pad.right) / count;
  const top = Math.max(...days.map((d) => d.n), 1);
  const nice = top <= 10 ? 10 : 10 ** Math.floor(Math.log10(top)) * Math.ceil(top / 10 ** Math.floor(Math.log10(top)));
  const yOf = (v) => +(pad.top + (1 - v / nice) * (h - pad.top - pad.bottom)).toFixed(1);
  const bw = +Math.max(2, step - 2).toFixed(1);
  const bars = days.map((d) => {
    const i = daysBetween(d.d, from);
    const y = yOf(d.n);
    return { x: +(pad.left + i * step + (step - bw) / 2).toFixed(1), y, bw, bh: +(h - pad.bottom - y).toFixed(1), d: d.d, n: d.n, max: d.max };
  });
  const every = Math.max(1, Math.ceil(count / 6));
  const ticks = [];
  for (let i = 0; i < count; i++) {
    if (i === 0 || i === count - 1 || (i % every === 0 && count - 1 - i >= Math.ceil(every / 2))) {
      const d = addDays(from, i);
      ticks.push({ x: +(pad.left + i * step + step / 2).toFixed(1), label: `${+d.slice(5, 7)}/${+d.slice(8, 10)}` });
    }
  }
  return { w, h, bars, grid: [0, nice / 2, nice].map((v) => ({ v, y: yOf(v) })), ticks, left: pad.left, right: w - pad.right, bottom: h - pad.bottom };
}

/** 同人の、いまの割引ごとの本数（セールの記録のページ）: [{ name, count }]（割引の大きい順。0本の幅は出さない） */
export function offBands(items) {
  const bands = [[90, 100, '90%OFF以上'], [70, 89, '70〜89%OFF'], [50, 69, '50〜69%OFF'], [30, 49, '30〜49%OFF'], [1, 29, '30%OFF未満']];
  const sale = floorSaleItems(items);
  return bands.map(([lo, hi, name]) => ({ name, count: sale.filter((i) => i.off >= lo && i.off <= hi).length })).filter((b) => b.count > 0);
}

/** 売り場ごとのファイルの数（作品ページ・サークル/ブランドのページ・一覧・トップ・ランキング・セール・セールの記録・コレクションのページとその一覧・セールのページ）。サイト全体の計画（lib/plan.js）に足す */
export const floorFileCount = (floor, makers, collections = {}, salePages = []) => (floor.items.length > 0
  ? floor.items.length + makers.length + 5 + salePages.length + FLOOR_COLLECTION_KINDS.reduce((n, k) => n + (collections[k]?.length ? collections[k].length + 1 : 0), 0)
  : 0);
