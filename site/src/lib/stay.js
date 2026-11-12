// 作品ページの「次に見るもの」の部品（運営者の希望「サイト滞在時間を伸ばしたい」。2026-10-06。画面に依存しない。tests/test_stay.mjs）。
// 検索から作品ページに来た人が、そこで帰らずに、次の作品・女優・セールへ進めるように:
//   次の新作（この作品の出演者の、予約受付中の作品）・同じ出演者/メーカーの作品（小さな表紙の棚）
// どちらも、こちらから案内する欄なので、未成年を連想させるタイトルの作品は入れない（運命の作品・きょうの話題と同じ）
import { relatedItems } from './items.js';
import { isMinorTitle } from './gacha.js';
import { bestRank } from './popularity.js';
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

// ---------- 沼を深くする（2026-11-12 運営者「深掘りして、関連に派生して、サイト沼に入れる方針が完璧。もっと伸ばしたい」。案B「順に見る道」） ----------
// 11/12 に、女優のページ → 作品 → 女優のページに戻る → 別の作品…をくり返して、2時間で5人ほど渡り歩いた人がいた（claude/web-analytics.md）。
// 戻らずに次へ行けるよう、作品ページに「○○の作品を人気の順に」（前の作品・次の作品）を、女優のページに「次に見る女優」（共演・同じメーカー）を置く。
// 人気の順は、FANZA全体の人気の順位と新着の人気の順位の上のほう（bestRank）。順位の無い作品は、そのあとに新しい順
export const WALK_MAX_CAST = 2; // 作品ページの「人気の順に」の欄の数の上限（出演者の並び順の先頭から、作品が2本以上ある人を2人まで。出演者が NEXT_WORKS_MAX_CAST 人より多い作品には出さない）
export const NEXT_ACTRESS_SHOWN = 6; // 女優のページの「次に見る女優」の人数（顔の丸の3つ並び×2段）

const popRankOf = (w) => bestRank(w.popAll, w.popNew);

/** 人気の順の並べ方（順位の小さい順 → 順位の無い作品は新しい順） */
export function byPopularity(a, b) {
  const ra = popRankOf(a);
  const rb = popRankOf(b);
  if (ra && rb && ra !== rb) return ra - rb;
  if (ra && !rb) return -1;
  if (!ra && rb) return 1;
  return b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid);
}

/**
 * その人の作品を人気の順に（発売前の作品・未成年を連想させるタイトルの作品・出演者が maxCast 人より多い作品〔総集編・オムニバス〕は除く。
 * この作品だけは、発売前でも入れて位置を出す。2026-11-12 の写真で「前の作品」に「ほか50名」の総集編が出たので、総集編も除いた）
 */
export function walkList(item, works, today, maxCast = NEXT_WORKS_MAX_CAST) {
  return works.filter((w) => w.cid === item.cid || (w.dateKey <= today && w.actress.length <= maxCast && !isMinorTitle(w.title))).sort(byPopularity);
}

/** その人の、いちばん人気の作品（発売済み・未成年を連想させるタイトルと総集編〔出演者が maxCast 人より多い〕は除く。exclude の作品は除く）。無ければ null */
export function topWorkOf(works, today, exclude = '', maxCast = NEXT_WORKS_MAX_CAST) {
  return works.filter((w) => w.cid !== exclude && w.dateKey <= today && w.actress.length <= maxCast && !isMinorTitle(w.title)).sort(byPopularity)[0] ?? null;
}

/**
 * 作品ページの「○○の作品を人気の順に」: [{ name, path, total, at（この作品が何本めか。1から）, prev, next, nextName }]。
 * 出演者がその人の作品の中で前後の作品へ進める。いちばん最後の作品では、next に「次に見る女優」のいちばん人気の作品（nextName にその人の名前）。
 * 出演者が maxCast 人より多い作品（総集編など）・その人の作品が1本だけの人には出さない
 * nextActress: (名前) => { name, item } か null（lib/data.js の actressLinks で作る）
 */
export function castWalksOf(item, byName, today, { maxCast = NEXT_WORKS_MAX_CAST, limit = WALK_MAX_CAST, nextActress = null } = {}) {
  if (!item.actress.length || item.actress.length > maxCast) return [];
  const walks = [];
  for (const name of item.actress) {
    const group = byName.get(name);
    if (!group?.items?.length) continue;
    const list = walkList(item, group.items, today, maxCast);
    const at = list.findIndex((w) => w.cid === item.cid);
    if (at < 0 || list.length < 2) continue;
    let next = list[at + 1] ?? null;
    let nextName = '';
    if (!next && nextActress) {
      const n = nextActress(name);
      if (n && n.item && n.item.cid !== item.cid && n.item.cid !== list[at - 1]?.cid) {
        next = n.item;
        nextName = n.name;
      }
    }
    walks.push({ name, path: group.path, total: list.length, at: at + 1, prev: list[at - 1] ?? null, next, nextName });
    if (walks.length >= limit) break;
  }
  return walks;
}

/**
 * 女優のつながりの索引（ビルドのはじめに1回だけ作る。作品ページごとに全作品を見直さない）。
 * groups: 出演者のページのまとまり（actressGroups＝作品が2本以上の人）。indexable: まとまり → 検索に出せるページか
 * 共演は、出演者が maxCast 人までの作品で数える（総集編で関係の薄い人が並ばないように。メーカーのページの「よく出ている女優」と同じ考え）
 */
export function actressLinkIndex(groups, indexable = () => false, { maxCast = NEXT_WORKS_MAX_CAST } = {}) {
  const byName = new Map();
  const coStar = new Map();
  const topMakers = new Map();
  const makerCount = new Map();
  const canIndex = new Map();
  for (const g of groups) {
    byName.set(g.name, g);
    canIndex.set(g.name, Boolean(indexable(g)));
    const co = new Map();
    const mk = new Map();
    for (const w of g.items) {
      if (w.actress.length > maxCast) continue;
      for (const o of w.actress) if (o !== g.name) co.set(o, (co.get(o) ?? 0) + 1);
      if (w.maker && w.maker !== '不明') mk.set(w.maker, (mk.get(w.maker) ?? 0) + 1);
    }
    coStar.set(g.name, co);
    topMakers.set(g.name, [...mk].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 2).map(([m]) => m));
    for (const [m, c] of mk) {
      if (!makerCount.has(m)) makerCount.set(m, new Map());
      makerCount.get(m).set(g.name, c);
    }
  }
  return { byName, coStar, topMakers, makerCount, canIndex, cache: new Map() };
}

/**
 * 「次に見る女優」: [{ name, path, kind（'costar'＝共演・'maker'＝同じメーカー）, count, maker }]。
 * 検索に出せるページの人が先（Google が検索に出せないページを読みに行く回数をふやさない。運営者 11/12「検索に出せる人を先に」）→ 共演 → 同じメーカー（その人にいちばん多いメーカー2つ）→ 本数の多い順
 */
export function nextActressesOf(name, index, limit = NEXT_ACTRESS_SHOWN) {
  const key = `${name}\n${limit}`;
  if (index.cache.has(key)) return index.cache.get(key);
  const rows = [];
  const seen = new Set([name]);
  // tier: 0＝共演・1＝いちばん多いメーカー・2＝2番めに多いメーカー
  const add = (other, kind, count, tier, maker = '') => {
    if (seen.has(other) || !index.byName.has(other)) return;
    seen.add(other);
    rows.push({ name: other, path: index.byName.get(other).path, kind, count, maker, tier, ok: index.canIndex.get(other) ? 1 : 0 });
  };
  for (const [other, c] of index.coStar.get(name) ?? []) add(other, 'costar', c, 0);
  (index.topMakers.get(name) ?? []).forEach((m, at) => {
    for (const [other, c] of index.makerCount.get(m) ?? []) add(other, 'maker', c, at + 1, m);
  });
  rows.sort((a, b) => b.ok - a.ok || a.tier - b.tier || b.count - a.count || a.name.localeCompare(b.name));
  const out = rows.slice(0, limit).map(({ ok, tier, ...r }) => r);
  index.cache.set(key, out);
  return out;
}

/** 作品ページの「人気の順に」の最後で進む先: 次に見る女優の先頭から、いちばん人気の作品がある人（{ name, item }）。無ければ null */
export function nextActressWork(name, index, today, exclude = '') {
  for (const r of nextActressesOf(name, index)) {
    const top = topWorkOf(index.byName.get(r.name)?.items ?? [], today, exclude);
    if (top) return { name: r.name, item: top };
  }
  return null;
}

/** 「次に見る女優」の顔の下の短い文（共演3本／同じメーカー） */
export const nextActressNote = (r) => (r.kind === 'costar' ? `共演${r.count}本` : '同じメーカー');

export const BODY_NEAR_SHOWN = 6; // 女優のページの「身長とカップが近い女優」の人数（顔の丸の3つ並び×2段）
export const BODY_NEAR_CM = 3; // 身長の近さ（±cm）

const heightOf = (p) => (Number.isFinite(p?.height) && p.height >= 120 && p.height <= 210 ? Math.round(p.height) : null);
const cupOf = (p) => (typeof p?.cup === 'string' && /^[A-Z]$/.test(p.cup) ? p.cup : '');

/**
 * 「身長とカップが近い女優」の索引（ビルドのはじめに1回だけ作る）: カップ → [{ name, path, height, cup, works, ok }]。
 * FANZA公式のプロフィールに身長とカップがある、ページのある人だけ。顔や雰囲気が「似ている」は FANZA のデータに無く推測になるので出さない。
 * 公式の数字が近い人だけ（2026-11-12 運営者 OK）。groups: actressGroups。profileOf: 名前 → プロフィール。indexable: まとまり → 検索に出せるページか
 */
export function bodyIndex(groups, profileOf, indexable = () => false) {
  const byCup = new Map();
  for (const g of groups) {
    const p = profileOf(g.name);
    const height = heightOf(p);
    const cup = cupOf(p);
    if (!height || !cup) continue;
    if (!byCup.has(cup)) byCup.set(cup, []);
    byCup.get(cup).push({ name: g.name, path: g.path, height, cup, works: g.items.length, ok: indexable(g) ? 1 : 0 });
  }
  return byCup;
}

/**
 * 「身長とカップが近い女優」: { rows: [{ name, path, height, cup }], height, cup, min, max } か null（その人の身長かカップが無いとき）。
 * 同じカップで身長が ±cm の人。検索に出せるページの人が先 → 身長の近い順 → 作品の多い順。exclude（「次に見る女優」に出た人）は除く
 */
export function bodyNeighborsOf(name, profile, index, { exclude = [], limit = BODY_NEAR_SHOWN, cm = BODY_NEAR_CM } = {}) {
  const height = heightOf(profile);
  const cup = cupOf(profile);
  if (!height || !cup) return null;
  const skip = new Set([name, ...exclude]);
  const rows = (index.get(cup) ?? [])
    .filter((r) => !skip.has(r.name) && Math.abs(r.height - height) <= cm)
    .sort((a, b) => b.ok - a.ok || Math.abs(a.height - height) - Math.abs(b.height - height) || b.works - a.works || a.name.localeCompare(b.name))
    .slice(0, limit)
    .map(({ ok, works, ...r }) => r);
  return { rows, height, cup, min: height - cm, max: height + cm };
}

/** 「身長とカップが近い女優」の顔の下の短い文（158cm・Eカップ） */
export const bodyNote = (r) => `${r.height}cm・${r.cup}カップ`;

/** 女優検索を、その身長の幅とカップで開く住所（public/actress-search.js の height・cup）。robots.txt で止める（/actress/? の住所はいくらでも増えるため） */
export const bodySearchHref = (base, near) => `${base}?height=${near.min}-${near.max}&cup=${near.cup}`;

