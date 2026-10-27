// 女優の歩み（年表）の部品（画面に依存しない。テスト: tests/test_history.mjs）。運営者の希望「世界一の女優深掘りサイトにしたい」。2026-10-27。
// データは data/actress_history.json（scripts/actress_history.py が FANZA公式のAPIで、出演者ごとの全作品を数えたもの）と、
// data/actress_stories.json（Claude が数字だけを使って書いた短い紹介文。scripts/claude_history.py）。
// 書くのは FANZA の作品の数字だけ。「デビュー作」とは言い切らず「FANZAでいちばん古い作品」と書く（配信より前の作品があるため）。

import { KANA_ROWS, KANA_OTHER, kanaRow, toHiragana } from './kana.js';

const DAY = /^\d{4}-\d{2}-\d{2}$/;
export const NENPYO_PATH = '/actress/nenpyo/'; // 女優の年表の一覧（2026-10-27。運営者「名前は女優の年表、入口は女優検索のページだけ」）
export const HISTORY_MAKER_MIN = 3; // 年表に「〇〇でいちばん古い作品」を出すのは、そのメーカーの作品が3本以上あるときだけ
export const HISTORY_MAKER_MAX = 4; // 年表に出すメーカーの数（最初の作品のメーカーは除く）
export const HISTORY_GENRES = 5; // 「多いジャンル」の数

const pick = (w) => (w && typeof w === 'object' && /^[a-z0-9_]+$/.test(String(w.c ?? '')) && DAY.test(String(w.d ?? '')) ? { c: String(w.c), d: String(w.d), m: String(w.m ?? ''), t: String(w.t ?? '') } : null);
const num = (v) => (Number.isInteger(v) && v >= 0 ? v : 0);
const pairs = (list) => (Array.isArray(list) ? list.filter((p) => Array.isArray(p) && typeof p[0] === 'string' && p[0] && Number.isInteger(p[1]) && p[1] > 0).map(([name, n]) => ({ name, n })) : []);

/** actress_history.json → 名前 → 1人分（読めない人は入れない） */
export function normalizeHistory(raw) {
  const out = new Map();
  const rows = raw && typeof raw === 'object' && raw.actresses && typeof raw.actresses === 'object' ? raw.actresses : {};
  for (const [id, r] of Object.entries(rows)) {
    if (!r || typeof r !== 'object' || typeof r.name !== 'string' || !r.name || !DAY.test(String(r.checked ?? ''))) continue;
    const first = pick(r.first);
    const total = num(r.total);
    if (!first || total < 1) continue;
    const years = [];
    for (const [y, v] of Object.entries(r.years && typeof r.years === 'object' ? r.years : {})) {
      if (/^\d{4}$/.test(y) && v && num(v.n) > 0) years.push({ year: +y, n: num(v.n), makers: pairs(v.m) });
    }
    years.sort((a, b) => a.year - b.year);
    out.set(r.name, {
      id: String(id),
      name: r.name,
      checked: r.checked,
      total,
      upcoming: num(r.upcoming),
      first,
      latest: pick(r.latest),
      years,
      makers: (Array.isArray(r.makers) ? r.makers : []).filter((m) => m && typeof m.m === 'string' && m.m && num(m.n) > 0 && DAY.test(String(m.f ?? ''))).map((m) => ({ name: m.m, n: num(m.n), first: String(m.f), c: String(m.c ?? '') })),
      milestones: (Array.isArray(r.milestones) ? r.milestones : []).map((m) => (pick(m) && num(m.n) > 0 ? { ...pick(m), n: num(m.n) } : null)).filter(Boolean),
      vr: r.vr && num(r.vr.n) > 0 && pick(r.vr.first) ? { n: num(r.vr.n), first: pick(r.vr.first) } : null,
      best: num(r.best),
      solo: num(r.solo),
      costars: pairs(r.costars),
      genres: pairs(r.genres),
    });
  }
  return out;
}

/** actress_stories.json → 名前 → { text, written }（Claude が書いた紹介文。数字を書いたときの集めた日 checked も） */
export function normalizeStories(raw) {
  const out = new Map();
  const rows = raw && typeof raw === 'object' && raw.stories && typeof raw.stories === 'object' ? raw.stories : {};
  for (const [name, s] of Object.entries(rows)) {
    if (!s || typeof s.text !== 'string' || !s.text.trim() || !DAY.test(String(s.written ?? ''))) continue;
    out.set(name, { text: s.text.trim(), written: s.written, checked: DAY.test(String(s.checked ?? '')) ? s.checked : '' });
  }
  return out;
}

/** 年ごとの本数を、いちばん古い年から最後の年まで、0本の年も入れて並べる（棒グラフ用） */
export function yearBars(h) {
  if (!h || h.years.length === 0) return [];
  const by = new Map(h.years.map((y) => [y.year, y]));
  const from = h.years[0].year;
  const to = h.years[h.years.length - 1].year;
  const out = [];
  for (let y = from; y <= to; y++) out.push({ year: y, n: by.get(y)?.n ?? 0, makers: by.get(y)?.makers ?? [] });
  return out;
}

/** 棒グラフの下に出す年（多いときは、最初・最後と5で割り切れる年。最初・最後に近すぎる年は出さない） */
export function yearTicks(bars) {
  if (bars.length <= 12) return bars.map((b) => b.year); // 12年までは全部（スマホの幅で、4けたの年が12個ならぶ）
  const first = bars[0].year;
  const last = bars[bars.length - 1].year;
  return bars.map((b) => b.year).filter((y) => y === first || y === last || (y % 5 === 0 && y - first >= 2 && last - y >= 2));
}

const ym = (d) => `${+d.slice(0, 4)}年${+d.slice(5, 7)}月`;

/**
 * 年表の行（古い順）: FANZAでいちばん古い作品・メーカーごとのいちばん古い作品（3本以上のメーカー）・いちばん古いVR作品・100本目などの節目・いちばん新しい作品。
 * 返す形: [{ d, when: '2018年4月', label, c, t, m }]
 */
export function historyTimeline(h, { makerMin = HISTORY_MAKER_MIN, makerMax = HISTORY_MAKER_MAX } = {}) {
  if (!h) return [];
  const rows = [{ d: h.first.d, label: 'FANZAでいちばん古い作品', ...h.first, order: 0 }];
  const firstMaker = h.first.m;
  for (const m of h.makers.filter((x) => x.name !== firstMaker && x.n >= makerMin).slice(0, makerMax)) {
    rows.push({ d: m.first, label: `${m.name}でいちばん古い作品`, c: m.c, t: '', m: m.name, order: 1 });
  }
  if (h.vr && h.vr.first.c !== h.first.c) rows.push({ d: h.vr.first.d, label: 'いちばん古いVR作品', ...h.vr.first, order: 2 });
  for (const ms of h.milestones) rows.push({ d: ms.d, label: `${ms.n.toLocaleString('ja-JP')}本目`, c: ms.c, t: ms.t, m: ms.m, order: 3 });
  if (h.latest && h.latest.c !== h.first.c) rows.push({ d: h.latest.d, label: 'いちばん新しい作品', ...h.latest, order: 4 });
  const seen = new Set();
  return rows
    .sort((a, b) => a.d.localeCompare(b.d) || a.order - b.order)
    .filter((r) => (seen.has(`${r.label}|${r.c}`) ? false : seen.add(`${r.label}|${r.c}`)))
    .map(({ order, ...r }) => ({ ...r, when: ym(r.d) }));
}

/** 見出しの下の1行: 「FANZAの作品277本・2018年から（予約3本）」 */
export function historyLine(h) {
  if (!h) return '';
  return `FANZAの作品${h.total.toLocaleString('ja-JP')}本・${+h.first.d.slice(0, 4)}年から${h.upcoming > 0 ? `（予約${h.upcoming}本）` : ''}`;
}

/** 多いジャンル（内容のジャンルだけ。形式のジャンル「ハイビジョン」「独占配信」などは、allowed に無いので出ない） */
export const historyGenres = (h, allowed, limit = HISTORY_GENRES) => (h ? h.genres.filter((g) => allowed.has(g.name)).slice(0, limit) : []);

/** いちばん本数の多い年（同じなら新しい年） */
export function peakYear(h) {
  if (!h || h.years.length === 0) return null;
  return h.years.reduce((best, y) => (y.n > best.n || (y.n === best.n && y.year > best.year) ? y : best));
}

/** 説明文（meta description）の頭に付ける1文: 「FANZAの作品は277本（2018年から）。」 */
export const historyDescriptionHead = (h) => (h ? `FANZAの作品は${h.total.toLocaleString('ja-JP')}本（${+h.first.d.slice(0, 4)}年から）。` : '');

/** 一覧の1行の短い数字: 「2018〜2026年・120本」（同じ年なら「2026年・12本」） */
export function historyBrief(h) {
  if (!h) return '';
  const from = +h.first.d.slice(0, 4);
  const lastYear = h.years.length ? h.years[h.years.length - 1].year : from;
  const to = Math.max(from, h.latest ? +h.latest.d.slice(0, 4) : lastYear, lastYear);
  return `${from === to ? `${from}年` : `${from}〜${to}年`}・${h.total.toLocaleString('ja-JP')}本`;
}

const NENPYO_NONE = { head: 'その他', key: 'none' };

/**
 * 女優の年表の一覧（/actress/nenpyo/）: 50音の行ごとに分ける → [{ head, key, id, entries: [{ name, path, reading, brief }] }]
 * entries: [{ name, path, history, reading }]。読みがなの無い人は、いちばん最後の「その他」（名前の順）
 */
export function nenpyoIndex(entries, prefix = 'nenpyo') {
  const rows = new Map();
  for (const e of entries) {
    if (!e || !e.name || !e.path || !e.history) continue;
    const reading = toHiragana(e.reading ?? '').replace(/\s+/g, '');
    const row = reading ? kanaRow(reading) : NENPYO_NONE;
    if (!rows.has(row.key)) rows.set(row.key, { head: row.head, key: row.key, id: `${prefix}-${row.key}`, entries: [] });
    rows.get(row.key).entries.push({ name: e.name, path: e.path, reading, brief: historyBrief(e.history) });
  }
  const by = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const order = [...KANA_ROWS, KANA_OTHER, NENPYO_NONE].map((r) => r.key);
  return order
    .filter((k) => rows.has(k))
    .map((k) => {
      const r = rows.get(k);
      return { ...r, entries: r.entries.sort((a, b) => by(a.reading, b.reading) || by(a.name, b.name)) };
    });
}
