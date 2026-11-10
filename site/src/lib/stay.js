// 作品ページの「次に見るもの」の部品（運営者の希望「サイト滞在時間を伸ばしたい」。2026-10-06。画面に依存しない。tests/test_stay.mjs）。
// 検索から作品ページに来た人が、そこで帰らずに、次の作品・女優・セールへ進めるように:
//   次の新作（この作品の出演者の、予約受付中の作品）・同じ出演者/メーカーの作品（小さな表紙の棚）
// どちらも、こちらから案内する欄なので、未成年を連想させるタイトルの作品は入れない（運命の作品・きょうの話題と同じ）
import { relatedItems } from './items.js';
import { isMinorTitle } from './gacha.js';
import { FLOORS, FLOOR_GENRE_OK, floorItemPagePath } from './floors.js';

export const NEXT_WORKS_SHOWN = 3; // 作品ページの「次の新作」の本数
export const NEXT_WORKS_MAX_CAST = 4; // 出演者がこの人数までの作品だけ（オムニバス・総集編で、関係の薄い作品が並ばないように）
export const RELATED_SHOWN = 6; // 「同じ出演者・メーカーの作品」の本数（スマホで3列×2段）

/**
 * この作品の出演者の、次の新作（予約受付中。発売日が近い順に limit 本。この作品は入れない）: { names（次の新作がある出演者。この作品の並び順）, items }。
 * byName: 出演者の名前 → その人の作品（出演者のページのまとまり。actressByName）
 */
export function nextWorksOf(item, byName, today, { limit = NEXT_WORKS_SHOWN, maxCast = NEXT_WORKS_MAX_CAST } = {}) {
  if (!item.actress.length || item.actress.length > maxCast) return { names: [], items: [] };
  const seen = new Set([item.cid]);
  const found = [];
  const names = [];
  for (const name of item.actress) {
    const works = (byName.get(name)?.items ?? []).filter((w) => w.dateKey > today && !seen.has(w.cid) && !isMinorTitle(w.title));
    if (works.length) names.push(name);
    for (const w of works) {
      seen.add(w.cid);
      found.push(w);
    }
  }
  found.sort((a, b) => a.dateKey.localeCompare(b.dateKey) || a.cid.localeCompare(b.cid));
  return { names, items: found.slice(0, limit) };
}

/** 同じ出演者・メーカーの作品（relatedItems と同じ選び方で、未成年を連想させるタイトルの作品を除いて limit 本） */
export function relatedForPage(item, all, limit = RELATED_SHOWN) {
  return relatedItems(item, all, limit * 3).filter((w) => !isMinorTitle(w.title)).slice(0, limit);
}

// ---------- 作品ページの「ほかの売り場から」（2026-11-06 運営者「動画好きな人は同人とかブックスでも絶対に釣れる。売り場のリンクも1個ずつくらい」。連絡 C-025 の「買いに来る理由」） ----------
// 品番で来た人が、名前を知ったあとに、ほかの売り場（写真集・VR見放題・成人映画・同人・コミック・アニメ）へも迷い込めるように。
//   出演者が出ている売り場（写真集・VR見放題・成人映画）は、同じ出演者の、いちばん人気の1本
//   出演者のいない売り場（同人・コミック・アニメ）は、同じジャンル（おだやかなジャンル名 FLOOR_GENRE_OK だけ）でいちばん人気の1本
// どの売り場も1本まで・全部で FLOOR_PICKS_SHOWN 本まで。出演者の売り場が先。リンクはこのサイトの売り場の作品ページへ
export const FLOOR_PICKS_SHOWN = 4;
export const FLOOR_PICKS_BY_CAST = ['photo', 'vr', 'cinema'];
export const FLOOR_PICKS_BY_GENRE = ['doujin', 'comic', 'anime'];
const CAST_WORD = { photo: '写真集', vr: 'VR', cinema: '成人映画' };
const pickIndexes = new WeakMap();

/** 売り場ごとに、出演者 → いちばん人気の作品・ジャンル → いちばん人気の作品（作品ページごとに売り場の全作品を見直さないよう、1回だけ作る） */
function pickIndex(floors) {
  if (pickIndexes.has(floors)) return pickIndexes.get(floors);
  const ok = new Set(FLOOR_GENRE_OK);
  const index = {};
  for (const key of [...FLOOR_PICKS_BY_CAST, ...FLOOR_PICKS_BY_GENRE]) {
    const byName = new Map();
    const byGenre = new Map();
    // 売り場の作品は人気の高い順（lib/floors.js の byRank）なので、最初に見つかったものがいちばん人気
    for (const it of floors?.[key]?.items ?? []) {
      if (isMinorTitle(it.title)) continue;
      if (FLOOR_PICKS_BY_CAST.includes(key)) {
        for (const name of it.actress ?? []) if (!byName.has(name)) byName.set(name, it);
      } else {
        for (const g of it.genres ?? []) if (ok.has(g) && !byGenre.has(g)) byGenre.set(g, it);
      }
    }
    index[key] = { byName, byGenre };
  }
  pickIndexes.set(floors, index);
  return index;
}

/**
 * 動画の作品ページの「ほかの売り場から」: [{ floor, label（売り場の短い名前）, reason（「○○の写真集」「「人妻・主婦」で人気」）, item }]
 * floors: lib/data.js の floors（{ 売り場: { items } }）。出演者が maxCast 人より多い作品（総集編など）は、出演者で選ばない
 */
export function floorPicksFor(item, floors, { limit = FLOOR_PICKS_SHOWN, maxCast = NEXT_WORKS_MAX_CAST } = {}) {
  const index = pickIndex(floors);
  const picks = [];
  const cast = (item.actress ?? []).length <= maxCast ? item.actress ?? [] : [];
  for (const key of FLOOR_PICKS_BY_CAST) {
    const name = cast.find((n) => index[key].byName.has(n));
    if (name) picks.push({ floor: key, label: FLOORS[key].short, reason: `${name}の${CAST_WORD[key]}`, item: index[key].byName.get(name) });
  }
  for (const key of FLOOR_PICKS_BY_GENRE) {
    const genre = (item.genres ?? []).find((g) => index[key].byGenre.has(g));
    if (genre) picks.push({ floor: key, label: FLOORS[key].short, reason: `「${genre}」で人気`, item: index[key].byGenre.get(genre) });
  }
  return picks.slice(0, limit);
}

const comma = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
export const FLOOR_PICK_NAMES = 3; // 「ほかの売り場から」の行に出す作家・出演者の人数（それより多いときは「ほか」）

/**
 * 「ほかの売り場から」の1行（components/FloorRow.astro の row。売り場の作品検索の行と同じ横長の形）:
 * 選んだ理由は出さず、題名・作り手（サークル/出版社/メーカーと作家・出演者）・売り場と値段を出す
 * （2026-11-06 運営者「選定理由は書かなくていいから、しっかりタイトルとか表示させて」「タイルじゃなくて、横広で紹介」）
 */
export function floorPickRow({ floor, label, item }) {
  const names = [...(item.authors ?? []), ...(item.actress ?? [])];
  const who = names.length > FLOOR_PICK_NAMES ? `${names.slice(0, FLOOR_PICK_NAMES).join('、')}ほか` : names.join('、');
  const yen = item.price ? `${comma(item.price)}円${item.off ? `（${item.off}%OFF）` : ''}` : '';
  return {
    c: item.cid,
    href: floorItemPagePath(item, floor),
    title: item.title,
    img: item.image_url,
    line: [item.maker?.name, who].filter(Boolean).join('｜'),
    meta: [label, item.upcoming ? '予約' : '', yen].filter(Boolean).join('・'),
    upcoming: false,
  };
}
