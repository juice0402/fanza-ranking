// FANZA同人・FANZAゲーム（PCゲーム・DL版）のページの部品（画面に依存しない。tests/test_floors.mjs）。
// 運営者の希望「『FANZA セール』で上に来る、同人・ゲームのセール情報のページも」→「同人 1,000本・ゲーム 500本」（2026-10-09）。
// データは毎日の更新が集める site/src/data/doujin.json・game.json（scripts/doujin_game.py。形は scripts/floor_data.py）。
// 未成年を連想させる作品は、集めるときに入れていない。ここでも、タイトル・ジャンル・シリーズ・サークル/ブランド・作家の名前を調べて、念のため外す（二重の備え）。
import { reviewOf } from './reviews.js';
import { FANZA_HOSTS, FANZA_LINK_HOSTS, addDays, daysBetween, entitySlug, isDay, resizedImage, safeHttpsUrl, smallImage } from './items.js';
import { isMinorTitle } from './gacha.js';
import { bestOf } from './popularity.js';
import { phraseZwsp } from './phrase.js';

/**
 * 売り場の設定。label: 正式な名前・short: 短い名前・maker: サークル/ブランド/メーカー/出版社の呼び方・makerUnit: 数えるときの言葉・kind: 作品の呼び方。
 * frame: 一覧の表紙の枠（'wide'＝横長 4:3・'square'＝正方形・'cover'＝動画と同じ縦長）。detail: 作品ページの大きな表紙の形
 * （'wide'・'square'・'spread'＝パッケージの見開き 800×538・'tall'＝縦長）。authors: 作家を出す。people: 出演者を出す。noPrice: 価格を出さない（見放題）。
 * 運営者の希望「アニメ動画・素人・成人映画・FANZAブックス（コミック・写真集）・VR見放題も。各100、素人は500」（2026-10-10）。
 * 集める道具は scripts/floor_data.py の FLOORS（同じ売り場・同じ順。tests/test_floors.mjs で突き合わせ）
 */
export const FLOORS = {
  doujin: { key: 'doujin', label: 'FANZA同人', short: '同人', maker: 'サークル', makerUnit: 'サークル', kind: '同人作品', frame: 'wide', detail: 'wide' },
  game: { key: 'game', label: 'FANZAゲーム', short: 'ゲーム', maker: 'ブランド', makerUnit: 'ブランド', kind: 'PCゲーム', frame: 'cover', detail: 'tall', authors: true },
  anime: { key: 'anime', label: 'FANZAアニメ', short: 'アニメ', maker: 'メーカー', makerUnit: '社', kind: 'アダルトアニメ', frame: 'cover', detail: 'spread' },
  amateur: { key: 'amateur', label: 'FANZA素人', short: '素人', maker: 'メーカー', makerUnit: '社', kind: '素人作品', frame: 'square', detail: 'square', people: true },
  cinema: { key: 'cinema', label: 'FANZA成人映画', short: '成人映画', maker: 'メーカー', makerUnit: '社', kind: '成人映画', frame: 'cover', detail: 'spread', people: true },
  comic: { key: 'comic', label: 'FANZAコミック', short: 'コミック', maker: '出版社', makerUnit: '社', kind: 'アダルトコミック', frame: 'cover', detail: 'tall', authors: true },
  photo: { key: 'photo', label: 'FANZA写真集', short: '写真集', maker: '出版社', makerUnit: '社', kind: '写真集', frame: 'cover', detail: 'tall', authors: true, people: true },
  vr: { key: 'vr', label: 'FANZA VR見放題', short: 'VR見放題', maker: 'メーカー', makerUnit: '社', kind: 'VR作品', frame: 'cover', detail: 'spread', people: true, noPrice: true },
};
export const FLOOR_KEYS = Object.keys(FLOORS);
/** 一覧の表紙の枠の印（class）: 同人＝is-wide（横長）・素人＝is-wide is-square（正方形。横長の枠の札の置き方を、そのまま使う）・ほか＝なし */
export const frameClass = (key) => ({ 'is-wide': FLOORS[key]?.frame === 'wide' || FLOORS[key]?.frame === 'square', 'is-square': FLOORS[key]?.frame === 'square' });
/** 作品検索の欄の案内（「タイトル・サークル」「タイトル・ブランド・作家」「タイトル・メーカー・出演者」など） */
export const floorSearchHint = (key) => `タイトル・${FLOORS[key].maker}${FLOORS[key].authors ? '・作家' : ''}${FLOORS[key].people ? '・出演者' : ''}`;
/** 横長・正方形の枠の売り場か（表紙を枠にまるごと入れる。<picture> で縮めた版） */
export const isFramed = (key) => FLOORS[key]?.frame === 'wide' || FLOORS[key]?.frame === 'square';

export const floorPath = (key) => `/${key}/`;
export const floorRankingPath = (key) => `/${key}/ranking/`;
export const floorSalePath = (key) => `/${key}/sale/`;
export const floorItemPath = (key, cid) => `/${key}/item/${cid}/`;
export const floorMakerIndexPath = (key) => `/${key}/maker/`;
export const floorMakerPath = (key, id) => `/${key}/maker/${id}/`;

export const FLOOR_RANKING_LIMIT = 100; // 人気ランキングのページに並べる本数
export const FLOOR_HUB_SHOWN = 12; // 売り場のトップの、それぞれの棚に並べる本数
export const FLOOR_SALE_LIMIT = 48; // セールのページに並べる本数（人気の高い順。ほかは、セールごと・割引ごとのページ・作品検索で）
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
/** 素人の表紙（1200×1200 の四角。2026-10-10 に本物で確かめた。約160KB）も、スマホは「縮めて返す版」に。読めなければ元の画像、それも読めなければ隠す */
export const FRAMED_THUMB_ONERROR = "var s=this.previousElementSibling,m=s?s.tagName=='SOURCE'?matchMedia(s.media).matches:0:0;if(m){s.remove()}else{this.style.visibility='hidden'}";
/** 横長・正方形の枠の表紙: { src, small（スマホ）, onerror, width, height }（同人は doujin-assets に戻す道も） */
export function framedThumb(key, url, kind = 'card') {
  const t = doujinThumb(url, kind);
  return key === 'doujin'
    ? { ...t, onerror: DOUJIN_THUMB_ONERROR, width: 560, height: 420 }
    : { ...t, onerror: FRAMED_THUMB_ONERROR, width: 600, height: 600 };
}
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
 * 作品: { floor, cid, title, url, image_url, sample_images, date, dateKey, maker:{id,name}|null, authors, actress, sampleMovie, trialUrl, series:{id,name}|null,
 *         genres, formats, sales, price, listPrice, off, campaign:{title,begin}|null, comment, updated, rank, upcoming, type（同人の形式。comic・cg・voice・game） }
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
    const actress = names(r.actress, 8);
    const maker = entry(r.maker_id, r.maker);
    const series = entry(r.series_id, r.series);
    // 未成年を連想させる作品は出さない（集めるときにも外している。二重の備え）
    if ([title, ...genres, ...formats, ...sales, ...authors, ...actress, maker?.name, series?.name].some(minor)) continue;
    seen.add(cid);
    // 見放題（VR見放題）の価格は、作品の値段ではないので出さない
    const price = FLOORS[key]?.noPrice ? null : yen(r.price);
    const listPrice = FLOORS[key]?.noPrice ? null : yen(r.list_price);
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
      // 出演者（VR・成人映画・写真集など）・サンプル動画のページ（アニメ・素人・VR など）・立ち読みのページ（ブックス）。2026-10-10 から
      actress,
      sampleMovie: safeHttpsUrl(r.sample_movie, FANZA_HOSTS),
      trialUrl: safeHttpsUrl(r.trial_url, FANZA_LINK_HOSTS),
      series,
      genres,
      formats,
      sales,
      price,
      listPrice: listPrice && price && price <= listPrice ? listPrice : null,
      off: offOf(price, listPrice),
      campaign: camp,
      // FANZAのレビューの評価（2026-10-10 から。lib/reviews.js）。無ければ null
      review: reviewOf(r.review),
      comment: r.comment_kind === 'claude' ? String(r.comment ?? '').trim() : '',
      updated: isDay(r.updated) ? r.updated : '',
      rank,
      upcoming: date.slice(0, 10) > today,
      // 同人の作品の形式（コミック・CG集・音声・ゲーム）。表紙の置き場所（pics.dmm.co.jp/digital/<形式>/…）で分かる（2026-10-09 に本物で確かめた）
      type: key === 'doujin' ? (/^https:\/\/pics\.dmm\.co\.jp\/digital\/(comic|cg|voice|game)\//.exec(picsUrl(r.image_url) ?? '')?.[1] ?? '') : '',
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

/** ゲームの作品ページの札から、セールのページへ（セールのページが無い小さなセールは、セールのページ。クーポン・ポイント還元は、その欄） */
export const saleTagHref = (key, t) => (isSaleTag(t) ? floorSalePath(key) : `${floorSalePath(key)}#coupons`);

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
  '獣人', '天使・悪魔', 'お嬢様・令嬢', '王女・姫', '主従', '上司・部下',
  // 新しい売り場（アニメ・素人・成人映画・写真集・VR見放題。2026-10-10）で多い、おだやかなもの（動画のジャンルのページ TAG_PAGE_GENRES にもあるもの）
  '美乳', '巨尻', 'グラビア', 'ドラマ'];
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

/** カードのサークル/ブランドの1行（ゲーム・コミックは作家も1人。出演者のいる売り場は、出演者を先に2人まで） */
export function makerLine(item) {
  const f = FLOORS[item.floor] ?? {};
  if (f.people && item.actress?.length > 0) return [item.actress.slice(0, 2).join('、') + (item.actress.length > 2 ? ` ほか${item.actress.length - 2}名` : ''), item.maker?.name ?? ''].filter(Boolean).join('｜');
  const parts = [item.maker?.name ?? ''];
  if (f.authors && item.authors.length > 0) parts.push(`作家 ${item.authors[0]}`);
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
  type: { label: '形式', find: '形式から探す', min: 3 },
  theme: { label: '特集', find: '特集から探す', min: 3 },
};

/**
 * 同人の作品の形式（運営者の希望「同人ならでは・ゲームならではのコレクションを」。2026-10-09）。表紙の置き場所で分かる（normalizeFloor の type）。
 * 形式ごとのページは、その形式の人気ランキング（/doujin/type/voice/ など）
 */
export const DOUJIN_TYPES = [
  { slug: 'comic', name: '同人コミック', short: 'コミック' },
  { slug: 'cg', name: 'CG・イラスト集', short: 'CG集' },
  { slug: 'voice', name: '同人音声・ASMR', short: '音声・ASMR' },
  { slug: 'game', name: '同人ゲーム', short: 'ゲーム' },
];
export const doujinTypeName = (slug) => DOUJIN_TYPES.find((t) => t.slug === slug)?.name ?? '';

/**
 * 同人ならでは・ゲームならではの特集（運営者の希望。2026-10-09）。決まった条件で作品を集める（作品が3本以上のときだけページを作る）。
 * slug: ページの場所・name: 短い名前（チップ）・heading: 見出し。test(item, today)。tests/verify_dist.py が、同じ条件で数えて突き合わせる。
 * 同人のコミケの作品は、FANZAの「コミケ108（2026夏）」のような札ごとに、別に作る（comiketTheme）
 */
const hasFormat = (name) => (i) => i.formats.includes(name);
const hasGenre = (name) => (i) => i.genres.includes(name);
export const FLOOR_THEMES = {
  doujin: [
    { slug: 'senbai', name: 'FANZA専売', heading: 'FANZA専売の同人作品', test: hasFormat('専売') },
    { slug: 'anime', name: 'アニメーション', heading: '動く同人作品（アニメーション）', test: hasGenre('動画・アニメーション') },
    { slug: 'ku100', name: 'KU100', heading: 'KU100で録った同人音声', test: hasGenre('KU100') },
    { slug: 'trial', name: '体験版あり', heading: '体験版のある同人作品', test: hasFormat('デモ・体験版あり') },
    { slug: 'coin', name: '500円以下', heading: '500円以下で買える同人作品', test: (i) => Boolean(i.price) && i.price <= 500 },
    { slug: 'longseller', name: 'ロングセラー', heading: '発売から1年以上たっても人気の同人作品', test: (i, today) => isDay(today) && !i.upcoming && i.dateKey <= addDays(today, -365) },
  ],
  game: [
    { slug: 'trial', name: '体験版あり', heading: '体験版のあるPCゲーム', test: hasFormat('デモ・体験版あり') },
    { slug: 'browser', name: 'ブラウザで遊べる', heading: 'ブラウザで遊べるPCゲーム', test: hasFormat('ブラウザ対応') },
    { slug: 'win11', name: 'Windows11対応', heading: 'Windows11対応のPCゲーム', test: hasFormat('Windows11対応作品') },
    { slug: 'dlonly', name: 'DL版独占販売', heading: 'FANZAのDL版独占販売のPCゲーム', test: hasFormat('DL版独占販売') },
    { slug: 'set', name: 'セット商品', heading: 'まとめて買えるセット商品', test: hasFormat('セット商品') },
    { slug: 'bestprice', name: 'BEST PRICE版', heading: 'BEST PRICE版（廉価版）のPCゲーム', test: hasGenre('BEST PRICE版') },
    { slug: 'budget', name: '2,000円以下', heading: '2,000円以下で買えるPCゲーム', test: (i) => Boolean(i.price) && i.price <= 2000 },
    { slug: 'anime', name: 'アニメーション', heading: 'アニメーションで動くPCゲーム', test: hasGenre('アニメーション') },
    { slug: 'longseller', name: '名作・ロングセラー', heading: '発売から5年以上たっても人気のPCゲーム', test: (i, today) => isDay(today) && !i.upcoming && i.dateKey <= addDays(today, -365 * 5) },
  ],
};
const COMIKET = /^コミケ(\d{2,3})（(\d{4})(夏|冬)）$/;
/** 「コミケ108（2026夏）」の札 → { slug: 'comiket108', name, heading, no }。ちがえば null */
export function comiketTheme(format) {
  const m = COMIKET.exec(format);
  return m ? { slug: `comiket${m[1]}`, name: format, heading: `${format}の同人作品`, no: Number(m[1]) } : null;
}
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
export function floorCollections(items, key, today = '') {
  const maps = Object.fromEntries(FLOOR_COLLECTION_KINDS.map((k) => [k, new Map()]));
  const add = (kind, slug, name, item, extra = {}) => {
    const m = maps[kind];
    if (!m.has(slug)) m.set(slug, { kind, slug, name, items: [], ...extra });
    const g = m.get(slug);
    // シリーズは FANZA の id ごと（名前は、人気のいちばん高い作品のもの）。ジャンル・作家は、別の名前が同じ印になったとき（ほぼ起きない）は、はじめの名前だけ
    if (kind === 'series' || g.name === name) g.items.push(item);
  };
  const themes = FLOOR_THEMES[key] ?? [];
  for (const i of items) {
    for (const g of new Set(i.genres)) if (GENRE_OK.has(g)) add('genre', entitySlug(g), g, i);
    if (i.series) add('series', String(i.series.id), i.series.name, i);
    for (const a of new Set(i.authors)) add('author', entitySlug(a), a, i);
    add('month', i.dateKey.slice(0, 7), monthName(i.dateKey.slice(0, 7)), i);
    if (i.type) add('type', i.type, doujinTypeName(i.type), i);
    if (key === 'doujin') {
      for (const f of new Set(i.formats)) {
        const c = comiketTheme(f);
        if (c) add('theme', c.slug, c.name, i, { heading: c.heading, order: 1000 - c.no, comiket: true });
      }
    }
    themes.forEach((t, n) => {
      if (t.test(i, today)) add('theme', t.slug, t.name, i, { heading: t.heading, order: n });
    });
  }
  const out = {};
  for (const kind of FLOOR_COLLECTION_KINDS) {
    const groups = [...maps[kind].values()]
      .filter((g) => g.items.length >= FLOOR_COLLECTIONS[kind].min)
      .map((g) => ({ ...g, path: floorCollectionPath(key, kind, g.slug), total: g.items.length, items: [...g.items].sort(byRank) }));
    // 発売月は新しい月から・形式は決めた順・特集は決めた順 → コミケ（新しい回から）・ほかは作品の多い順
    const typeOrder = (g) => DOUJIN_TYPES.findIndex((t) => t.slug === g.slug);
    groups.sort(kind === 'month' ? (a, b) => (a.slug < b.slug ? 1 : -1)
      : kind === 'type' ? (a, b) => typeOrder(a) - typeOrder(b)
        : kind === 'theme' ? (a, b) => a.order - b.order
          : (a, b) => b.total - a.total || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    out[kind] = groups;
  }
  return out;
}

/** コレクションのページを検索エンジンに出してよいか: ページに並べる作品（人気の高い順に60本）に、コメントのある作品があるとき（sitemap も同じ） */
export const collectionIndexable = (group) => group.items.slice(0, FLOOR_COLLECTION_LIST).some((i) => i.comment);
/** コレクションの一覧のページ: 検索エンジンに出すページが1つでもあるとき */
export const collectionIndexIndexable = (groups) => groups.some(collectionIndexable);

/** 売り場のトップに出す特集（いちばん新しいコミケ → 決めた順。limit 個） */
export const hubThemes = (themes, limit = 6) => [...themes.filter((g) => g.comiket).slice(0, 1), ...themes.filter((g) => !g.comiket)].slice(0, limit);

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
  if (group.kind === 'type') return `${f.label} ${group.name}の人気ランキング【${updatedYm}】（${group.total}本）｜${siteName}`;
  if (group.kind === 'theme') return `${group.heading}【${f.label}・${updatedYm}】人気順（${group.total}本）｜${siteName}`;
  if (group.kind === 'genre') return `${f.label}「${group.name}」の人気作品一覧【${updatedYm}】（${group.total}本）｜${siteName}`;
  if (group.kind === 'series') return `${group.name}｜${f.label}のシリーズ作品一覧【${updatedYm}】（${group.total}本）｜${siteName}`;
  if (group.kind === 'author') return `${group.name}の${f.kind}一覧（${f.label}）【${updatedYm}】（${group.total}本）｜${siteName}`;
  return `${f.label} ${group.name}発売の${f.kind}・人気順（${group.total}本）｜${siteName}`;
}

/** コレクションのページの見出し */
export function collectionHeading(f, group) {
  if (group.kind === 'type') return `${group.name}の人気ランキング`;
  if (group.kind === 'theme') return group.heading;
  if (group.kind === 'genre') return `${f.label}の「${group.name}」作品`;
  if (group.kind === 'series') return `${group.name}（シリーズ）`;
  if (group.kind === 'author') return `${group.name}の${f.kind}`;
  return `${group.name}発売の${f.kind}`;
}

/** コレクションのページの説明文（数えた事実だけ） */
export function collectionDescription(f, group, facts) {
  const what = group.kind === 'type' ? `${group.name}` : group.kind === 'theme' ? `「${group.name}」の${f.kind}`
    : group.kind === 'genre' ? `「${group.name}」のジャンルの${f.kind}`
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
    type: item.type ? bySlug('type').get(item.type) ?? null : null,
    themes: (groups.theme ?? []).filter((g) => g.items.some((i) => i.cid === item.cid)),
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

// ---------- 売り場のトップ（動画のトップと同じ形。運営者の希望「動画のページがよくできているので、ほぼ同じ要領で」。2026-10-09） ----------

/** 前の日からの順位の動き（TOP3 の表紙の右上の札。動画の topics.js の rankMove と同じ形）: { kind: 'up'|'down'|'same'|'new', text, label } か null（記録が無い） */
export function floorMove(hist, day, since = '') {
  const cur = floorRankOn(hist, day);
  if (!cur) return null;
  const prev = floorRankOn(hist, addDays(day, -1));
  if (prev > 0) {
    if (prev === cur) return { kind: 'same', text: '→', label: 'きのうと同じ順位' };
    const n = Math.abs(prev - cur);
    return prev > cur ? { kind: 'up', text: `▲${n}`, label: `きのう${prev}位から${n}つ上がった` } : { kind: 'down', text: `▼${n}`, label: `きのう${prev}位から${n}つ下がった` };
  }
  if (prev === 0 || (hist.start === day && since && since < day)) return { kind: 'new', text: '初登場', label: 'きのうは圏外' };
  return null;
}

/**
 * きょうの話題（売り場のトップの右の欄。動画の「きょうの話題」と同じ見た目）: 急上昇（3本まで）・新作で人気・セールで人気・予約で人気（ゲーム）。
 * [{ kind（動画の topic-○○ と同じ色の札）, label, item, text }]。文はデータで決まった形だけ
 */
export function floorTopics(items, histMap, day, limit = 6) {
  const pos = new Map(floorRanking(items, Infinity).map((i, n) => [i.cid, n + 1]));
  const md = (d) => `${+d.slice(5, 7)}月${+d.slice(8, 10)}日`;
  const used = new Set();
  const rows = [];
  const push = (row) => {
    if (row.item && !used.has(row.item.cid)) {
      used.add(row.item.cid);
      rows.push(row);
    }
  };
  if (isDay(day)) for (const r of floorRisers(items, histMap, day, 3)) push({ kind: 'rise', label: '急上昇', item: r.item, text: `人気ランキング${r.cur}位（前日から▲${r.rise}）` });
  const fresh = isDay(day) ? floorNewPopular(items, day, 3).find((i) => !used.has(i.cid)) : null;
  if (fresh) push({ kind: 'today', label: '新作で人気', item: fresh, text: `${md(fresh.dateKey)}発売・人気ランキング${pos.get(fresh.cid)}位` });
  const sale = floorSaleItems(items).find((i) => !used.has(i.cid));
  if (sale) push({ kind: 'salehot', label: 'セールで人気', item: sale, text: [sale.off ? `${sale.off}%OFF` : 'セール中', priceNote(sale)].filter(Boolean).join(' ') });
  const wait = items.filter((i) => i.upcoming && i.rank).sort(byRank)[0] ?? floorUpcoming(items)[0];
  if (wait) push({ kind: 'entry', label: '予約で人気', item: wait, text: `${md(wait.dateKey)}発売予定` });
  return rows.slice(0, limit);
}

// ---------- 人気サークル・ブランド・作家ランキング（運営者の希望「同人とかゲームも、人気の作家さんとか独自のランキングを」。2026-10-09） ----------
// 人気ランキングの上位300本の順位から点数（1位＝300点・300位＝1点）を付けて、サークル/ブランド・作家ごとに足した順。
// 前の日の点数は、人気の動きの記録（floor_rank_history.json）の前の日の順位から同じように数えて、順位の動きを出す

export const FLOOR_ENTITY_TOP = 300; // 点数を数える深さ（人気ランキングの上位300本）
export const FLOOR_ENTITY_LIMIT = 50; // ランキングのページに並べる数
export const floorEntityRankingPath = (key, by) => `${floorRankingPath(key)}${by}/`;
/** ランキングの呼び方: 「人気サークルランキング」「人気ブランドランキング」「人気作家ランキング」 */
export const floorEntityLabel = (f, by) => (by === 'maker' ? f.maker : '作家');

const entityKeys = (item, by) => (by === 'maker' ? (item.maker ? [[String(item.maker.id), item.maker.name]] : []) : [...new Set(item.authors)].map((a) => [a, a]));

/**
 * items: 売り場の作品、by: 'maker'（サークル/ブランド）か 'author'（作家）。opts: { hist（人気の動きの記録 Map）, day（データの日）, pathOf(キー) → ページの場所 }。
 * → [{ key, name, path, score, count（上位300本の本数）, best（いちばん上の順位）, items（上位の作品3本）, rank, move（前日からの動き。数・'new'（初登場）・null（分からない）） }]
 */
export function floorEntityRanking(items, by, { hist = null, day = '', pathOf = () => '' } = {}, limit = FLOOR_ENTITY_LIMIT) {
  const top = floorRanking(items, FLOOR_ENTITY_TOP);
  const rows = new Map();
  top.forEach((item, n) => {
    for (const [k, name] of entityKeys(item, by)) {
      if (!rows.has(k)) rows.set(k, { key: k, name, score: 0, count: 0, best: n + 1, items: [] });
      const r = rows.get(k);
      r.score += FLOOR_ENTITY_TOP - n;
      r.count += 1;
      if (r.items.length < 3) r.items.push(item);
    }
  });
  const order = (a, b) => b.score - a.score || a.best - b.best || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
  const list = [...rows.values()].sort(order);
  // 前の日の順位（記録があるときだけ）
  const prevRank = new Map();
  if (hist && isDay(day)) {
    const y = addDays(day, -1);
    const prev = new Map();
    for (const item of items) {
      const p = floorRankOn(hist.get(item.cid), y);
      if (!(p > 0 && p <= FLOOR_ENTITY_TOP)) continue;
      for (const [k, name] of entityKeys(item, by)) {
        if (!prev.has(k)) prev.set(k, { key: k, name, score: 0, best: p });
        const r = prev.get(k);
        r.score += FLOOR_ENTITY_TOP + 1 - p;
        r.best = Math.min(r.best, p);
      }
    }
    [...prev.values()].sort(order).forEach((r, n) => prevRank.set(r.key, n + 1));
  }
  return list.slice(0, limit).map((r, n) => {
    const was = prevRank.get(r.key);
    return { ...r, path: pathOf(r.key) || '', rank: n + 1, move: prevRank.size === 0 ? null : was ? was - (n + 1) : 'new' };
  });
}

/** ランキングのページを検索エンジンに出してよいか: 並べた作品（それぞれの上位3本）に、コメントのある作品があるとき（sitemap も同じ） */
export const floorEntityIndexable = (list) => list.some((r) => r.items.some((i) => i.comment));

/** ランキングの動きの文字: 「▲2」「▼1」「→」「初登場」（分からなければ ''） */
export const moveLabel = (move) => (move === null || move === undefined ? '' : move === 'new' ? '初登場' : move > 0 ? `▲${move}` : move < 0 ? `▼${-move}` : '→');

// ---------- 運命の作品（スロットで3本。動画と同じ部品 components/GachaCorner.astro・public/gacha.js。2026-10-09） ----------
export const FLOOR_GACHA_POOL = 80;
/**
 * 運命の作品の候補（人気ランキングの上から、表紙のある作品を limit 本）: [{ c, h（作品ページの場所）, t, i（小さな表紙）, a（サークル/ブランドの1行）}]。
 * 未成年を連想させる作品は、もともと売り場に入れていない（normalizeFloor）
 */
export function floorGachaPool(items, limit = FLOOR_GACHA_POOL) {
  return floorRanking(items, Infinity).filter((i) => i.image_url).slice(0, limit).map((i) => ({
    c: i.cid,
    h: floorItemPath(i.floor, i.cid),
    t: phraseZwsp(i.title),
    i: isFramed(i.floor) ? doujinThumb(i.image_url, 'tiny').small : smallImage(i.image_url),
    a: makerLine(i),
  }));
}

// ---------- 作品検索（/doujin/search/・/game/search/。public/floor-search.js。2026-10-09） ----------
export const floorSearchPath = (key) => `/${key}/search/`;
export const floorSearchIndexPath = (key) => `/data/${key}-index.json`;
export const FLOOR_SEARCH_PAGE = 30; // 1回に出す本数（はじめの一覧も同じ）
/** 表紙の決まった置き場所（同人 /digital/<形式>/<品番>/<品番>pl.jpg・ゲーム /digital/pcgame/…）。この形なら、索引から画像の項目を省く（索引を軽くするため）。
 * ほかの売り場は、いつも画像の項目を入れる（'' を返す） */
export const floorImageOf = (key, cid, type) => (key === 'game' || key === 'doujin' ? `https://pics.dmm.co.jp/digital/${key === 'game' ? 'pcgame' : type}/${cid}/${cid}pl.jpg` : '');

/**
 * 作品検索の索引: { key, genres: [名前]（おだやかなジャンルだけ）, themes: [{ s, n }]（特集）, types: [{ s, n }]（同人の形式）, yomi: { 名前: 読み },
 *   items: [{ c, t（文節の区切り入り）, m（サークル/ブランド）, a（作家）, g:[ジャンルの番号], h:[特集の番号], y（形式）, p（価格）, o（割引%）, r（人気の順位）, d（発売日）, u（予約なら1）, s（セール中なら1）, i（画像。決まった形なら省く） }] }。人気の高い順
 */
export function floorSearchIndex(items, key, groups, readingOf = () => '') {
  const genres = topGenres(items, FLOOR_GENRE_OK.length).map((g) => g.name);
  // 読みがな（サークル/ブランドは id、作家・ジャンルは名前で引く）→ { 名前: 読み }（ひらがなで打っても見つかるように。2026-10-10）
  const yomi = {};
  const put = (name, r) => {
    if (name && r && !(name in yomi) && r.replace(/\s/g, '') !== name.replace(/\s/g, '')) yomi[name] = r;
  };
  for (const i of items) {
    if (i.maker) put(i.maker.name, readingOf('maker', i.maker.id));
    for (const a of i.authors) put(a, readingOf('author', a));
  }
  for (const g of genres) put(g, readingOf('genre', g));
  const gIndex = new Map(genres.map((g, n) => [g, n]));
  const themes = (groups.theme ?? []).map((g) => ({ s: g.slug, n: g.name }));
  const themeOf = new Map();
  (groups.theme ?? []).forEach((g, n) => g.items.forEach((i) => themeOf.set(i.cid, [...(themeOf.get(i.cid) ?? []), n])));
  const pos = new Map(floorRanking(items, Infinity).map((i, n) => [i.cid, n + 1]));
  return {
    key,
    genres,
    themes,
    types: key === 'doujin' ? DOUJIN_TYPES.filter((t) => items.some((i) => i.type === t.slug)).map((t) => ({ s: t.slug, n: t.short })) : [],
    yomi,
    items: items.map((i) => {
      const g = [...new Set(i.genres)].filter((x) => gIndex.has(x)).map((x) => gIndex.get(x));
      const h = themeOf.get(i.cid) ?? [];
      return {
        c: i.cid,
        t: phraseZwsp(i.title),
        ...(i.maker ? { m: i.maker.name } : {}),
        ...(i.authors.length || i.actress?.length ? { a: [...i.authors, ...(i.actress ?? [])].join('、') } : {}),
        ...(g.length ? { g } : {}),
        ...(h.length ? { h } : {}),
        ...(i.type ? { y: i.type } : {}),
        ...(i.price ? { p: i.price } : {}),
        ...(i.off ? { o: i.off } : {}),
        // FANZAのレビューの評価（並び順「評価が高い順」。平均×100・件数。2026-10-10）
        ...(i.review ? { v: Math.round(i.review.avg * 100), vc: i.review.count } : {}),
        ...(pos.has(i.cid) ? { r: pos.get(i.cid) } : {}),
        d: i.dateKey,
        ...(i.upcoming ? { u: 1 } : {}),
        ...(onSale(i) && !i.upcoming ? { s: 1 } : {}),
        ...(i.image_url && i.image_url !== floorImageOf(key, i.cid, i.type) ? { i: i.image_url } : {}),
      };
    }),
  };
}

/** 作品検索の1行の中身（ページを作るときの「はじめの一覧」と public/floor-search.js の rowView が同じ形を作る）: { href, title, img, wide, line, meta } */
export function floorSearchRow(row, key) {
  const img = row.i || (key === 'doujin' && !row.y ? '' : floorImageOf(key, row.c, row.y));
  const yen = row.p ? `${comma(row.p)}円${row.o ? `（${row.o}%OFF）` : ''}` : '';
  return {
    c: row.c,
    href: floorItemPath(key, row.c),
    title: row.t,
    img,
    wide: isFramed(key),
    square: FLOORS[key]?.frame === 'square',
    line: [row.m, row.a].filter(Boolean).join('｜'),
    meta: [row.u ? `${+row.d.slice(5, 7)}月${+row.d.slice(8, 10)}日発売予定` : `${row.d.slice(0, 4)}年${+row.d.slice(5, 7)}月${+row.d.slice(8, 10)}日発売`, yen].filter(Boolean).join('・'),
    rank: row.r ?? 0,
    upcoming: Boolean(row.u),
  };
}

/** 売り場ごとのファイルの数（作品ページ・サークル/ブランドのページ・一覧・トップ・ランキング・セール・セールの記録・コレクションのページとその一覧・セールのページ）。サイト全体の計画（lib/plan.js）に足す */
export const floorFileCount = (floor, makers, collections = {}, salePages = []) => (floor.items.length > 0
  ? floor.items.length + makers.length + 5 + salePages.length + FLOOR_COLLECTION_KINDS.reduce((n, k) => n + (collections[k]?.length ? collections[k].length + 1 : 0), 0)
    + 2 + 3 // 人気サークル/ブランド・作家ランキング（2）＋作品検索のページ・索引・運命の作品の候補（3）
  : 0);
