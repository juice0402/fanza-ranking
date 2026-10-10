// 独自の価値を足す部品（運営者の希望「中身の薄いページを大量に作らない。自動化はそのままで、独自の価値を足す」。2026-10-07。画面に依存しない。tests/test_insights.mjs）。
//   ・人気の動き（作品ページのグラフ・ランキングの最高順位）: data/rank_history.json（lib/popularity.js の normalizeRankHistory）
//   ・シリーズ・レーベルのページ（/series/<id>/・/label/<id>/）
//   ・内部リンク: 同じジャンルで人気の作品・関連するジャンル・その作品が載った週のまとめ
// 文はデータで決まった形だけ（評価の言葉は書かない）。こちらから案内する欄には、未成年を連想させるタイトル・名前を出さない
import { SITE_NAME, addDays, isDay, rankedNames, truncate } from './items.js';
import { isMinorTitle } from './gacha.js';
import { bestRank } from './popularity.js';

const md = (d) => `${+d.slice(5, 7)}月${+d.slice(8, 10)}日`;
const mdShort = (d) => `${+d.slice(5, 7)}/${+d.slice(8, 10)}`;

// ------------------------------------------------------------------
// 人気の動き（作品ページのグラフ）
// ------------------------------------------------------------------

export const TREND_MAX_RANK = 500; // 新着の人気順で記録している深さ（get_new_releases.py の NEW_RANK_CALLS×100）
export const TREND_W = 320;
export const TREND_H = 132;
const PAD = { left: 40, right: 14, top: 14, bottom: 24 };

/** 順位 → 縦の位置（対数の目盛り。1位がいちばん上、max 位（ふつうは500位）がいちばん下。上のほうの動きが見えるように） */
export const rankY = (rank, h = TREND_H, max = TREND_MAX_RANK) => {
  const t = Math.log10(Math.max(1, Math.min(rank, max))) / Math.log10(max);
  return +(PAD.top + t * (h - PAD.top - PAD.bottom)).toFixed(1);
};

/**
 * 作品ページの「発売後の人気の動き」のグラフ（新着の人気順。1日1点・対数の目盛り）。max: いちばん下の順位（同人・ゲームは300。lib/floors.js）。
 * 記録が無い・順位の分かる日が2日に満たないときは null（グラフは出さず、文だけにする）。
 * { points: [{ i, date, label, rank, x, y }], outs: [{ x, date }]（圏外の日）, path, best, grid: [{ rank, y }], days: [{ x, label }] }
 */
export function trendChart(hist, { w = TREND_W, h = TREND_H, max = TREND_MAX_RANK } = {}) {
  if (!hist || !Array.isArray(hist.n)) return null;
  const known = hist.n.filter((v) => v !== null);
  const ranked = hist.n.filter((v) => v > 0);
  if (known.length < 2 || ranked.length < 1) return null;
  const count = hist.n.length;
  const step = count > 1 ? (w - PAD.left - PAD.right) / (count - 1) : 0;
  const xOf = (i) => +(PAD.left + i * step).toFixed(1);
  const points = [];
  const outs = [];
  hist.n.forEach((v, i) => {
    const date = addDays(hist.start, i);
    if (v > 0) points.push({ i, date, label: mdShort(date), rank: v, x: xOf(i), y: rankY(v, h, max) });
    else if (v === 0) outs.push({ x: xOf(i), date, label: mdShort(date) });
  });
  // 線は、続いている日だけをつなぐ（圏外・取れなかった日で切る）
  let path = '';
  let prev = null;
  for (const p of points) {
    path += `${prev && p.i === prev.i + 1 ? 'L' : 'M'}${p.x} ${p.y}`;
    prev = p;
  }
  const best = points.reduce((b, p) => (!b || p.rank < b.rank ? p : b), null);
  const grid = [1, 10, 100, max].map((rank) => ({ rank, y: rankY(rank, h, max) }));
  const days = hist.n.map((_, i) => ({ x: xOf(i), label: mdShort(addDays(hist.start, i)) }));
  return { w, h, points, outs, path, best, grid, days, bottom: h - PAD.bottom, left: PAD.left, right: w - PAD.right };
}

/**
 * 人気の動きの短い文（作品ページ）。例: 「新着の人気順で最高3位（10月6日）・500位以内に5日」「全体の人気順でも最高120位」。
 * 記録が無い・一度も入っていなければ []
 */
export function trendLines(hist) {
  if (!hist?.bestNew) return [];
  const lines = [`新着の人気順で最高${hist.bestNew.rank}位（${md(addDays(hist.start, hist.bestNew.day))}）・${TREND_MAX_RANK}位以内に${hist.daysIn}日`];
  if (hist.bestAll) lines.push(`全体の人気順（上位1,000本）でも最高${hist.bestAll.rank}位（${md(addDays(hist.start, hist.bestAll.day))}）`);
  return lines;
}

/** 新着の人気ランキングのカードの下の1行: 「前日から▲3｜最高2位」。分からなければ '' */
export function rankNote(item, prevRank, hist) {
  const parts = [];
  const prev = prevRank?.get(item.cid);
  if (item.popNew && prev) {
    const d = prev - item.popNew;
    parts.push(d > 0 ? `前日から▲${d}` : d < 0 ? `前日から▼${-d}` : '前日と同じ');
  } else if (item.popNew && prevRank?.size) parts.push('初登場');
  const best = hist?.bestNew?.rank;
  if (best && item.popNew && best < item.popNew) parts.push(`最高${best}位`);
  else if (best && item.popNew > 1 && best === item.popNew && hist.n.some((v) => v > item.popNew)) parts.push('いまが最高位'); // 前より上がって、いまがいちばん上（1位は書かない）
  return parts.join('｜');
}

// ------------------------------------------------------------------
// シリーズ・レーベルのページ
// ------------------------------------------------------------------

export const SERIES_INDEX_PATH = '/series/';
export const LABEL_INDEX_PATH = '/label/';
export const seriesPath = (id) => `/series/${id}/`;
export const labelPath = (id) => `/label/${id}/`;

const byNewest = (a, b) => b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid);

/**
 * シリーズ・レーベルごとの作品グループ（key: 'series' か 'label'。FANZAの id でまとめる。名前は、いちばん多い名前）。
 * 作品が minItems 本未満・名前が未成年を連想させる・（レーベルは）メーカーと同じ名前のものは作らない。作品数の多い順に max 件まで
 */
export function groupByEntry(items, key, { minItems = 3, max = Infinity, pathOf = key === 'series' ? seriesPath : labelPath } = {}) {
  const groups = new Map();
  for (const item of items) {
    const e = item[key];
    if (!e) continue;
    let g = groups.get(e.id);
    if (!g) groups.set(e.id, (g = { id: e.id, names: new Map(), items: [] }));
    g.names.set(e.name, (g.names.get(e.name) ?? 0) + 1);
    g.items.push(item);
  }
  const out = [];
  for (const g of groups.values()) {
    if (g.items.length < minItems) continue;
    const name = [...g.names].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))[0][0];
    if (isMinorTitle(name)) continue;
    const makers = rankedNames(g.items.map((i) => i.maker).filter((m) => m && m !== '不明'), 3);
    if (key === 'label' && makers.names.length && makers.names[0] === name) continue; // メーカーのページと同じ中身になるので作らない
    out.push({ id: g.id, name, slug: String(g.id), path: pathOf(g.id), makers: makers.names, items: [...g.items].sort(byNewest), kind: key });
  }
  return out
    .sort((a, b) => b.items.length - a.items.length || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))
    .slice(0, max);
}

/** シリーズ・レーベルのページのタイトル: 「○○（シリーズ）の新作・予約・作品一覧【2026年10月】（12本）」 */
export function entryPageTitle(g, today = '') {
  const ym = isDay(today) ? `【${+today.slice(0, 4)}年${+today.slice(5, 7)}月】` : '';
  const up = isDay(today) && g.items.some((i) => i.dateKey > today) ? '・予約' : '';
  return `${truncate(g.name, 30)}（${g.kind === 'series' ? 'シリーズ' : 'レーベル'}）の新作${up}・作品一覧${ym}（${g.items.length}本）｜${SITE_NAME}`;
}

/** シリーズ・レーベルのページの紹介文（作品データだけから作る。説明文 description に使う） */
export function entrySummary(g) {
  const kind = g.kind === 'series' ? 'シリーズ' : 'レーベル';
  const days = g.items.map((i) => i.dateKey).sort();
  const cast = rankedNames(g.items.flatMap((i) => i.actress), 4);
  const parts = [`FANZAの「${g.name}」（${kind}）の作品を${g.items.length}本掲載しています。`];
  parts.push(days[0] === days[days.length - 1] ? `発売日は${md(days[0])}です。` : `発売日は${+days[0].slice(0, 4)}年${md(days[0])}から${+days[days.length - 1].slice(0, 4)}年${md(days[days.length - 1])}です。`);
  if (g.makers.length) parts.push(`メーカーは${g.makers.join('、')}です。`);
  if (cast.names.length) parts.push(`出演は${cast.names.join('、')}${cast.more ? 'ほか' : ''}です。`);
  return parts.join('');
}

/** 作品ページの「同じシリーズの作品」（この作品を除いて、発売日の近い順に limit 本。未成年を連想させるタイトルは出さない） */
export function sameSeries(item, group, limit = 6) {
  if (!group) return [];
  const t = Date.parse(item.dateKey);
  return group.items
    .filter((w) => w.cid !== item.cid && !isMinorTitle(w.title))
    .sort((a, b) => Math.abs(Date.parse(a.dateKey) - t) - Math.abs(Date.parse(b.dateKey) - t) || byNewest(a, b))
    .slice(0, limit);
}

/** メーカー・出演者のページの「シリーズ」チップ（そのまとまりの作品に多いシリーズで、ページがあるもの。本数の多い順に limit 件） */
export function entryChips(items, byId, key, limit = 8) {
  const counts = new Map();
  for (const i of items) if (i[key] && byId.has(i[key].id)) counts.set(i[key].id, (counts.get(i[key].id) ?? 0) + 1);
  return [...counts]
    .sort((a, b) => b[1] - a[1] || a[0] - b[0])
    .slice(0, limit)
    .map(([id, count]) => ({ name: byId.get(id).name, path: byId.get(id).path, count }));
}

// ------------------------------------------------------------------
// 内部リンク: 同じジャンルで人気・関連するジャンル・その作品が載った週のまとめ
// ------------------------------------------------------------------

/**
 * ジャンルごとの「人気の作品」の一覧（発売済み・人気順の順位がある作品だけ。全体の人気順と新着の人気順の上のほう。未成年を連想させるタイトルは入れない）。
 * genres: 数えるジャンル（中身のジャンル）。Map(ジャンル → 人気の順に keep 本)
 */
export function genreTopLists(items, genres, today, keep = 12) {
  const lists = new Map();
  const ranked = items
    .filter((i) => i.dateKey <= today && (i.popAll || i.popNew) && !isMinorTitle(i.title))
    .map((i) => ({ i, r: bestRank(i.popAll, i.popNew) }))
    .sort((a, b) => a.r - b.r || byNewest(a.i, b.i));
  for (const { i } of ranked) {
    for (const g of i.genres) {
      if (!genres.has(g)) continue;
      const list = lists.get(g) ?? [];
      if (list.length < keep) {
        list.push(i);
        lists.set(g, list);
      }
    }
  }
  return lists;
}

/** 作品のいちばん目立つ中身のジャンル（中身のジャンルのうち、作品に付いている順で最初のもの）。無ければ '' */
export const mainGenre = (item, genres) => item.genres.find((g) => genres.has(g)) ?? '';

/** 作品ページの「○○で人気の作品」（そのジャンルの人気の一覧から、この作品と exclude を除いて limit 本） */
export function popularInGenre(item, lists, genres, exclude = new Set(), limit = 6) {
  const genre = mainGenre(item, genres);
  if (!genre) return { genre: '', items: [] };
  const items = (lists.get(genre) ?? []).filter((w) => w.cid !== item.cid && !exclude.has(w.cid)).slice(0, limit);
  return { genre, items };
}

/**
 * ジャンルのページの「いっしょに付いていることが多いジャンル」: そのジャンルの作品に、ほかの中身のジャンルが付いている本数の多い順。
 * pages: ページがあるジャンルだけ（名前 → パス）。[{ name, path, count }]
 */
export function relatedGenres(groupItems, self, genres, pages, limit = 8) {
  const counts = new Map();
  for (const i of groupItems) for (const g of new Set(i.genres)) if (g !== self && genres.has(g) && pages.has(g)) counts.set(g, (counts.get(g) ?? 0) + 1);
  return [...counts]
    .filter(([, c]) => c >= 2)
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
    .slice(0, limit)
    .map(([name, count]) => ({ name, path: pages.get(name), count }));
}

/** その作品の発売週の「週のまとめ」（あれば { roundup, pick: 注目の作品として紹介したか }。無ければ null） */
export function roundupFor(item, roundups) {
  const r = roundups.find((x) => item.dateKey >= x.week_start && item.dateKey <= x.week_end);
  return r ? { roundup: r, pick: r.picks.some((p) => p.cid === item.cid) } : null;
}

/** 月のページの「この月の週のまとめ」（週の月曜日がその月に入る記事。古い順） */
export const roundupsInMonth = (roundups, ym) => roundups.filter((r) => r.week_start.slice(0, 7) === ym).sort((a, b) => a.week_start.localeCompare(b.week_start));


// ---- ジャンルの「FANZA全体で人気の作品」（data/genre_tops.json。scripts/genre_tops.py が毎日。2026-10-10） ----
const FANZA_HOST = /^https:\/\/([a-z0-9-]+\.)*(dmm\.co\.jp|fanza\.co\.jp)\//;
const GT_DAY = /^\d{4}-\d{2}-\d{2}$/;

/**
 * genre_tops.json → Map(ジャンルの名前 → { date, items })。items は人気の順。
 * このサイトに載っている作品は、そのまま（作品ページへ）。ほかは保存した形から作る（作品ページが無いので、FANZAへ直接）。
 * 未成年を連想させるタイトル・FANZA以外のURL・画像の無い行は捨てる。byCid: このサイトの作品（cid → 作品）
 */
export function normalizeGenreTops(raw, byCid = new Map()) {
  const out = new Map();
  const genres = raw && typeof raw === 'object' && raw.genres && typeof raw.genres === 'object' && !Array.isArray(raw.genres) ? raw.genres : {};
  for (const [name, g] of Object.entries(genres)) {
    if (!g || !Array.isArray(g.items) || !GT_DAY.test(String(g.date ?? ''))) continue;
    const items = [];
    const seen = new Set();
    for (const r of g.items) {
      if (!r || typeof r !== 'object' || typeof r.c !== 'string' || !/^[A-Za-z0-9_-]{1,40}$/.test(r.c) || seen.has(r.c)) continue;
      const own = byCid.get(r.c);
      if (own) {
        if (!isMinorTitle(own.title)) items.push(own);
        seen.add(r.c);
        continue;
      }
      const title = String(r.t ?? '').trim();
      if (!title || isMinorTitle(title) || !FANZA_HOST.test(String(r.u ?? '')) || !FANZA_HOST.test(String(r.i ?? '')) || !GT_DAY.test(String(r.d ?? ''))) continue;
      seen.add(r.c);
      items.push({
        cid: r.c,
        title,
        dateKey: r.d,
        actress: Array.isArray(r.a) ? r.a.filter((a) => typeof a === 'string' && a).slice(0, 4) : [],
        maker: typeof r.m === 'string' && r.m ? r.m : '不明',
        image_url: r.i,
        url: r.u,
        vr: r.v === 1,
        genres: [name],
        comment: '',
        fanzaOnly: true,
      });
    }
    if (items.length) out.set(name, { date: g.date, items });
  }
  return out;
}
