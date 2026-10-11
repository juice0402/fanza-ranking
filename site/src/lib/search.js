// 作品検索（/search/）のための、サイト側の部品（画面に依存しない）。
// ブラウザ側の動き（絞り込み・結果の表示）は site/public/search.js、「VR作品を隠す」スイッチは site/public/vr-filter.js。
import { NEW_BADGE_DAYS } from '../config.js';
import { namesPattern, phraseZwsp } from './phrase.js';
import { productCode } from './facts.js';

export const SEARCH_PATH = '/search/';
export const ITEMS_INDEX_PATH = '/data/items-index.json';
export const ITEMS_INDEX_LIMIT = 3000; // 索引に入れる作品の最大数（新しい順）。毎回ダウンロードされるので、古いものから外す
export const ITEMS_INDEX_POPULAR = 1000; // そのうち、全体の人気順の上位は、古くてもこの本数まで先に入れる（「人気順（全体）」で並べたときに出るように）
export const DMM_IMAGE_PREFIX = 'https://pics.dmm.co.jp/'; // 画像のURLの先頭がこれなら、索引では省く（ブラウザ側で付け直す）

/** ジャンル（タグ）で絞り込んだ検索ページへのリンク */
export const searchPath = (tag = '') => (tag ? `${SEARCH_PATH}?tag=${encodeURIComponent(tag)}` : SEARCH_PATH);

/**
 * 作品検索のための索引（/data/items-index.json）。
 *   generated: 作った日 / newDays: 「新作」シールを付ける日数 / genres: ジャンル名の一覧（作品の多い順）
 *   items: 発売日の新しい順に、{ c 作品ID, p 品番（例 DLDSS-566。作れないときは無い）, t タイトル, d 発売日, a 出演者, m メーカー,
 *           g ジャンルの番号（genres の何番目か）, v VRなら 1（VRでなければ無い）, o 単体作品なら 1（そうでなければ無い）, i 画像,
 *           r 全体の人気順の順位・n 新着の人気順の順位（分からなければ無い。lib/popularity.js） }
 * 入れる作品: 全体の人気順の上位 ITEMS_INDEX_POPULAR 本と、残りは新しい順に、合わせて limit 本まで（並びは発売日の新しい順）
 * タイトルには、文節の区切りに幅のない空白（U+200B）が入っている（ブラウザで、語の途中で改行しないため。site/src/lib/phrase.js の phraseZwsp）。
 * 出演者・メーカー・ジャンルは、作品ページと同じ名前。メーカーが「不明」のときは ''。
 * 画像は、DMMの画像のURLの先頭（https://pics.dmm.co.jp/）を省いた形（ほかのホストのURLはそのまま）。
 */
/** 索引で省く、決まった形の画像のパス（DMM の URL の先頭を除いたもの） */
// 読みと名前が同じ（ひらがなの名前など）なら、索引に入れない（public/search.js の normalizeText と同じそろえ方の一部）
const normalizeYomi = (t) => String(t ?? '').normalize('NFKC').toLowerCase().replace(/[ァ-ヶ]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0x60)).replace(/[\s　・·.\-]/g, '');

export const standardImage = (cid) => `digital/video/${cid}/${cid}pl.jpg`;

/**
 * readingOf: 名前 → 読みがな（出演者・メーカー・ジャンル。無ければ ''）。索引の yomi（{名前: 読み}）に入れて、
 * ひらがなで打っても見つかるようにする（「みかみ」で 三上…。2026-10-10。読みは FANZA公式のAPIから＝lib/kana.js・profiles.js）
 */
export function buildItemsIndex(items, today, limit = ITEMS_INDEX_LIMIT, popularCount = ITEMS_INDEX_POPULAR, readingOf = () => '') {
  return indexOf(pickMain(items, limit, popularCount), [], today, readingOf);
}

// 索引の作品（全体の人気順の上位 popularCount 本と、残りは新しい順に、合わせて limit 本まで。並びは発売日の新しい順）
const newestFirst = (a, b) => b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid);
function pickMain(items, limit = ITEMS_INDEX_LIMIT, popularCount = ITEMS_INDEX_POPULAR) {
  const popular = items.filter((i) => i.popAll).sort((a, b) => a.popAll - b.popAll || newestFirst(a, b)).slice(0, Math.min(popularCount, limit));
  const chosen = new Set(popular.map((i) => i.cid));
  return [...popular, ...[...items].sort(newestFirst).filter((i) => !chosen.has(i.cid))].slice(0, limit).sort(newestFirst);
}

// 名前（出演者・メーカー・ジャンル）→ 読み（名前と同じ読みは入れない）
function yomiOf(names, readingOf) {
  const yomi = {};
  for (const name of [...new Set(names)].sort()) {
    const r = name && name !== '不明' ? readingOf(name) : '';
    if (r && normalizeYomi(r) !== normalizeYomi(name)) yomi[name] = r;
  }
  return yomi;
}

// 索引の1行（短い名前の項目。buildItemsIndex の説明を参照）
function rowOf(item, numberOf, namesRe) {
  const row = {
    c: item.cid,
    t: phraseZwsp(item.title, namesRe),
    d: item.dateKey,
    a: item.actress,
    m: item.maker === '不明' ? '' : item.maker,
    g: [...new Set(item.genres)].map((g) => numberOf.get(g)).sort((x, y) => x - y),
  };
  // 画像: DMM の URL の先頭を省く。いちばん多い決まった形（digital/video/作品ID/作品IDpl.jpg）なら、項目ごと省く
  // （ブラウザ側の public/search.js の rowImage が作り直す。索引を軽くするため。2026-10-05）。画像が無い作品は ''
  const image = item.image_url.startsWith(DMM_IMAGE_PREFIX) ? item.image_url.slice(DMM_IMAGE_PREFIX.length) : item.image_url;
  if (image !== standardImage(item.cid)) row.i = image;
  if (item.vr) row.v = 1;
  if (item.solo) row.o = 1; // 単体作品（「単体作品のみ表示」スイッチ）
  if (item.popAll) row.r = item.popAll;
  if (item.popNew) row.n = item.popNew;
  // FANZAのレビューの評価（並び順「評価が高い順」。平均×100・件数。2026-10-10）
  if (item.review) {
    row.s = Math.round(item.review.avg * 100);
    row.sc = item.review.count;
  }
  const code = productCode(item.cid);
  if (code) row.p = code;
  return row;
}

// 索引（はじめに読む分）。ジャンルの一覧は、続きの作品（rest）の分も入れて数える（続きの行も同じ番号を使うため）
function indexOf(picked, rest, today, readingOf) {
  const counts = new Map();
  for (const item of [...picked, ...rest]) for (const g of new Set(item.genres)) counts.set(g, (counts.get(g) ?? 0) + 1);
  const genres = [...counts.keys()].sort((a, b) => counts.get(b) - counts.get(a) || (a < b ? -1 : a > b ? 1 : 0));
  const numberOf = new Map(genres.map((g, i) => [g, i]));
  const namesRe = namesPattern(picked.flatMap((i) => [...i.actress, i.maker]).filter((n) => n !== '不明'));
  return {
    generated: today,
    newDays: NEW_BADGE_DAYS,
    genres,
    yomi: yomiOf(picked.flatMap((i) => [...i.actress, i.maker]).concat(genres), readingOf),
    items: picked.map((item) => rowOf(item, numberOf, namesRe)),
  };
}

// ---- 作品検索の「続き」（運営者の希望「直リンクの作品も含めて、たくさんの作品から探せるように」→「①の方法で」。2026-10-11） ----
// はじめに読む索引（上の3,000本・圧縮して約210KB）は、今までどおりページを開いたときに読む。
// 載っているそのほかの作品（作品ページの無い、FANZAへ直接リンクする過去作品も）は、続きのファイル（/data/items-more/1.json …）に分け、
// キーワード・ジャンルで絞り込んだときや、古い順・人気順（全体）・評価が高い順で並べたときだけ、ブラウザが後ろで読む（public/search.js の needsMore）。
// 続きの1行は、索引の1行と同じ形。作品ページが無い作品は x:1（リンク先は、ファイルの fanza の {cid} を作品IDにしたFANZAの作品ページ）、
// FANZAのURLがその形でない作品は u（URLそのもの）。並びは人気の高い順（先に読むファイルに、見つかりやすい作品を入れる）

/** 続きのファイル1つに入れる作品の数（約1MB・圧縮して約220KB。並べて読む） */
export const SEARCH_MORE_SIZE = 3000;
/** 続きのファイルの場所（n は 1 から） */
export const searchMorePath = (n) => `/data/items-more/${n}.json`;
/** FANZAへのリンクとして使ってよいURL（https の al.fanza.co.jp・dmm.co.jp だけ。public/search.js の FANZA_HOSTS と同じ） */
export const SEARCH_LINK_HOSTS = ['fanza.co.jp', 'dmm.co.jp'];

/** 作品のFANZAのURLの、いちばん多い形（作品IDの所が {cid}）。作れなければ '' */
export function fanzaTemplate(items) {
  const counts = new Map();
  for (const i of items) {
    const url = String(i.url ?? '');
    if (!i.cid || url.split(i.cid).length !== 2 || !searchSafeUrl(url, SEARCH_LINK_HOSTS)) continue;
    const t = url.split(i.cid).join('{cid}');
    counts.set(t, (counts.get(t) ?? 0) + 1);
  }
  let best = '';
  for (const [t, n] of counts) if (!best || n > counts.get(best) || (n === counts.get(best) && t < best)) best = t;
  return best;
}

/**
 * 作品検索の索引と、続きのファイル。
 *   pagedItems: 作品ページのある作品（はじめの索引はこの中から）/ allItems: 載っている作品のすべて（続きは、はじめの索引に無いもの）
 * → { main: buildItemsIndex と同じ形（ジャンルの一覧は、続きの作品も入れて数える）, more: [{ generated, part, parts, fanza, yomi, items }] }
 */
export function buildSearchIndexes(pagedItems, allItems, today, readingOf = () => '', { limit = ITEMS_INDEX_LIMIT, popularCount = ITEMS_INDEX_POPULAR, size = SEARCH_MORE_SIZE } = {}) {
  const picked = pickMain(pagedItems, limit, popularCount);
  const inMain = new Set(picked.map((i) => i.cid));
  const pagedSet = new Set(pagedItems.map((i) => i.cid));
  const fanza = fanzaTemplate(allItems);
  const linkOf = (i) => (pagedSet.has(i.cid) ? {} : fanza && i.url === fanza.replace('{cid}', i.cid) ? { x: 1 } : searchSafeUrl(i.url, SEARCH_LINK_HOSTS) ? { u: i.url } : null);
  const seen = new Set(inMain);
  const rest = [];
  for (const i of allItems) {
    if (seen.has(i.cid) || !linkOf(i)) continue;
    seen.add(i.cid);
    rest.push(i);
  }
  // 人気の高い順（全体の人気順の順位が無い作品は、そのあとに新しい順）
  rest.sort((a, b) => (a.popAll ?? Infinity) - (b.popAll ?? Infinity) || newestFirst(a, b));
  const main = indexOf(picked, rest, today, readingOf);
  const numberOf = new Map(main.genres.map((g, i) => [g, i]));
  const parts = Math.ceil(rest.length / Math.max(1, size));
  const more = [];
  for (let n = 0; n < parts; n++) {
    const chunk = rest.slice(n * size, (n + 1) * size);
    const names = chunk.flatMap((i) => [...i.actress, i.maker]).filter((x) => x !== '不明');
    const namesRe = namesPattern(names);
    // 読み: はじめの索引に無い名前だけ（ブラウザが、はじめの索引の読みと合わせて使う）
    const yomi = Object.fromEntries(Object.entries(yomiOf(names, readingOf)).filter(([k]) => !(k in main.yomi)));
    more.push({
      generated: today,
      part: n + 1,
      parts,
      fanza,
      yomi,
      items: chunk.map((i) => ({ ...rowOf(i, numberOf, namesRe), ...linkOf(i) })),
    });
  }
  return { main, more };
}

// ---- 作品検索の「はじめの一覧」（運営者の「ほかのページでも、あとから出てくる・重い所を直して」。2026-10-07） ----
// 作品検索は、索引（3,000本・圧縮して約340KB）を読み終えるまで、検索の部品を隠していた（スマホで開いてから約1.6秒。出てきたときに画面が大きくずれた）。
// 条件なし（新しい順・すべて）のときの、はじめの1ページ（SEARCH_PAGE_SIZE 本）・ジャンルのボタンを、ページを作るときに先に入れておく
// （本数は、条件なしのあいだは出さない「ーー本」。total は「もっと見る」を出すかに使う）。
// 中身は、ブラウザの public/search.js と同じ決まりで作る（tests/test_search.mjs で突き合わせている）。
// ブラウザは、索引が届いたら、入っている一覧が自分の作る一覧と同じかを確かめ、同じなら作り直さない（違えば作り直す）

/** 作品検索で1回に出す本数（public/search.js の PAGE_SIZE と同じ） */
export const SEARCH_PAGE_SIZE = 24;
/** ジャンルを最初に出す数（public/search.js の TAGS_COLLAPSED と同じ） */
export const SEARCH_TAGS_COLLAPSED = 14;
/** 一覧に出す出演者の数（public/search.js の CAST_LIMIT と同じ） */
const SEARCH_CAST_LIMIT = 3;
/**
 * 条件なしのときの本数の代わり（public/search.js の COUNT_BLANK・COUNT_BLANK_NOTE と同じ）。
 * 索引は最大 ITEMS_INDEX_LIMIT 本なので、条件なしの本数（3,000本）が「掲載している作品の数」と誤解される（運営者の指摘。2026-10-09）。
 * 本数は、キーワード・ジャンル・発売の状態で絞り込んだときだけ出し、条件なしは「ーー本」。NOTE は読み上げ用（画面には出さない）
 */
export const SEARCH_COUNT_BLANK = 'ーー';
export const SEARCH_COUNT_BLANK_NOTE = '条件で絞り込むと、本数が出ます';

// public/search.js の safeUrl・imageUrl・rowImage・smallImageUrl・statusOf と同じ
function searchSafeUrl(url, hosts) {
  if (typeof url !== 'string') return '';
  const m = /^https:\/\/([A-Za-z0-9.-]+)(?::\d{1,5})?(?:[/?#]|$)/.exec(url);
  if (!m || /[\\\s\x00-\x1f\x7f]/.test(url)) return '';
  const host = m[1].toLowerCase();
  return hosts.some((h) => host === h || host.slice(-(h.length + 1)) === '.' + h) ? url : '';
}
function searchImageUrl(i) {
  if (typeof i !== 'string' || !i) return '';
  return searchSafeUrl(/^https:/.test(i) ? i : DMM_IMAGE_PREFIX + i, ['dmm.co.jp']);
}
function searchRowImage(row) {
  if (row.i === undefined) return /^[A-Za-z0-9_-]+$/.test(String(row.c || '')) ? searchImageUrl(standardImage(row.c)) : '';
  return searchImageUrl(row.i);
}
function searchSmallImage(url) {
  return /^https:\/\/pics\.dmm\.co\.jp\/.+pl\.jpg$/.test(String(url || '')) ? String(url).replace(/pl\.jpg$/, 'ps.jpg') : String(url || '');
}
const dayNumber = (s) => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / 86400000;
function searchStatus(day, today, newDays) {
  if (day > today) return 'wait';
  return dayNumber(today) - dayNumber(day) <= newDays ? 'new' : '';
}

/**
 * 検索結果の1件の中身（public/search.js の card と同じ）。
 * → { c, href, img, status（'new'|'wait'|''）, title, cast: [名前], castMore, date: "2026年10月7日", maker }
 */
export function searchCardView(row, today, newDays) {
  const cast = row.a.filter((n) => typeof n === 'string' && n);
  return {
    c: row.c,
    href: `/item/${row.c}/`,
    img: searchSmallImage(searchRowImage(row)),
    status: searchStatus(row.d, today, newDays),
    title: row.t,
    cast: cast.slice(0, SEARCH_CAST_LIMIT),
    castMore: cast.length - Math.min(cast.length, SEARCH_CAST_LIMIT),
    date: `${Number(row.d.slice(0, 4))}年${Number(row.d.slice(5, 7))}月${Number(row.d.slice(8, 10))}日`,
    maker: row.m || '',
  };
}

/**
 * 条件なし（新しい順・すべて・ジャンル指定なし。「VR作品を隠す」「単体作品のみ」も切）の検索結果の、はじめの size 本・全体の本数・ジャンルのボタン。
 * index は buildItemsIndex の結果（作品は、もう新しい順に並んでいる）。
 * → { total, rows: [searchCardView], tags: [{ n, name, count, hidden }], tagMore（「すべてのジャンル」を出すか） }
 */
export function searchFirstPage(index, today, size = SEARCH_PAGE_SIZE) {
  const genres = Array.isArray(index?.genres) ? index.genres.filter((g) => typeof g === 'string') : [];
  const rows = Array.isArray(index?.items) ? index.items : [];
  const newDays = typeof index?.newDays === 'number' ? index.newDays : NEW_BADGE_DAYS;
  const sorted = [...rows].sort((a, b) => (a.d < b.d ? 1 : a.d > b.d ? -1 : a.c < b.c ? -1 : a.c > b.c ? 1 : 0));
  const counts = genres.map(() => 0);
  for (const row of rows) for (const n of row.g) if (n >= 0 && n < genres.length) counts[n]++;
  let plain = 0;
  const tags = genres.map((name, n) => {
    const show = counts[n] > 0 && plain < SEARCH_TAGS_COLLAPSED;
    if (show) plain++;
    return { n, name, count: counts[n], hidden: !show };
  });
  return {
    total: rows.length,
    rows: sorted.slice(0, size).map((row) => ({ ...searchCardView(row, today, newDays), vr: row.v === 1, solo: row.o === 1 })),
    tags,
    tagMore: tags.some((t) => t.hidden),
  };
}
