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
export const standardImage = (cid) => `digital/video/${cid}/${cid}pl.jpg`;

export function buildItemsIndex(items, today, limit = ITEMS_INDEX_LIMIT, popularCount = ITEMS_INDEX_POPULAR) {
  const newest = (a, b) => b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid);
  const popular = items.filter((i) => i.popAll).sort((a, b) => a.popAll - b.popAll || newest(a, b)).slice(0, Math.min(popularCount, limit));
  const chosen = new Set(popular.map((i) => i.cid));
  const picked = [...popular, ...[...items].sort(newest).filter((i) => !chosen.has(i.cid))].slice(0, limit).sort(newest);

  const counts = new Map();
  for (const item of picked) for (const g of new Set(item.genres)) counts.set(g, (counts.get(g) ?? 0) + 1);
  const genres = [...counts.keys()].sort((a, b) => counts.get(b) - counts.get(a) || (a < b ? -1 : a > b ? 1 : 0));
  const numberOf = new Map(genres.map((g, i) => [g, i]));
  const namesRe = namesPattern(picked.flatMap((i) => [...i.actress, i.maker]).filter((n) => n !== '不明'));

  return {
    generated: today,
    newDays: NEW_BADGE_DAYS,
    genres,
    items: picked.map((item) => {
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
    }),
  };
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
