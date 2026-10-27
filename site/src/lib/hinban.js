// 品番の見方（/hinban/。運営者の希望「ライバルのよい所を載せよう」。2026-10-27）。画面に依存しない部品（テスト: tests/test_hinban.mjs）。
// 品番の頭の英字（SSIS・MIDA など）ごとに、このサイトの作品から数えた「どのメーカー・レーベルの作品か」「本数」「いちばん新しい発売日」を出す。
// 品番は facts.js の productCode（作品IDから確実に読めるものだけ）。数字はビルドのたびに数え直す（手で打ちこまない）。
import { productCode } from './facts.js';

export const HINBAN_PATH = '/hinban/';
export const HINBAN_MIN_ITEMS = 3; // 一覧に出すのは、このサイトに3本以上ある記号だけ（たまたまの1本で、メーカーを言い切らないように）
export const HINBAN_INDEX_MIN = 20; // 記号がこれより少ないあいだは、検索エンジンに出さない
export const HINBAN_TOP = 2; // 記号ごとに出すメーカー・レーベルの数（多い順）

/** 品番 "SSIS-818" → 頭の英字 "SSIS"（読めないときは ''） */
export const hinbanPrefix = (code) => (/^([A-Z]{2,10})-\d{3,5}$/.exec(String(code ?? '')) || [])[1] || '';

/** 作品ID（cid）の先頭に付く、FANZA独自の部分（"1start00413" → "1"、"h_086jrze00326" → "h_086"。無ければ ''） */
export const cidHead = (cid) => (/^(h_\d+|\d{1,3})(?=[a-z]{2,10}\d{3,5}$)/.exec(String(cid ?? '').toLowerCase()) || [])[1] || '';

const topNames = (counter, n) => [...counter.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)).slice(0, n).map(([name, count]) => ({ name, count }));

/**
 * 頭の英字ごとのまとめ。本数の多い順。
 * 返す形: [{ prefix, count, makers: [{name,count}], labels: [{name,id,count}]（id は FANZA のレーベル番号）, last: 'YYYY-MM-DD' }]
 */
export function hinbanPrefixes(items, { min = HINBAN_MIN_ITEMS, top = HINBAN_TOP } = {}) {
  const map = new Map();
  for (const item of items) {
    const prefix = hinbanPrefix(productCode(item.cid));
    if (!prefix) continue;
    let row = map.get(prefix);
    if (!row) map.set(prefix, (row = { prefix, count: 0, makers: new Map(), labels: new Map(), labelIds: new Map(), last: '' }));
    row.count++;
    if (item.maker && item.maker !== '不明') row.makers.set(item.maker, (row.makers.get(item.maker) ?? 0) + 1);
    const label = item.label?.name ?? '';
    if (label) {
      row.labels.set(label, (row.labels.get(label) ?? 0) + 1);
      if (item.label.id && !row.labelIds.has(label)) row.labelIds.set(label, item.label.id);
    }
    const day = item.dateKey ?? '';
    if (day > row.last) row.last = day;
  }
  return [...map.values()]
    .filter((r) => r.count >= min)
    .map((r) => ({
      prefix: r.prefix,
      count: r.count,
      makers: topNames(r.makers, top),
      labels: topNames(r.labels, top).map((l) => ({ ...l, id: r.labelIds.get(l.name) ?? '' })),
      last: r.last,
    }))
    .sort((a, b) => b.count - a.count || (a.prefix < b.prefix ? -1 : 1));
}

/** 頭の文字（A〜Z）ごとに分ける（一覧の目次用）。中は記号のアルファベット順 */
export function hinbanByLetter(rows) {
  const out = new Map();
  for (const r of [...rows].sort((a, b) => (a.prefix < b.prefix ? -1 : a.prefix > b.prefix ? 1 : 0))) {
    const k = r.prefix[0];
    if (!out.has(k)) out.set(k, []);
    out.get(k).push(r);
  }
  return [...out.entries()].map(([letter, list]) => ({ letter, rows: list }));
}

/** 説明に使う実例（このサイトの作品から。いちばん本数の多い記号の、いちばん新しい作品の作品IDと品番。先頭に数字などが付く作品ID も1つ） */
export function hinbanExamples(items, rows) {
  const top = rows[0]?.prefix ?? '';
  let plain = null;
  let headed = null;
  for (const item of items) {
    const code = productCode(item.cid);
    if (!code) continue;
    if (!cidHead(item.cid)) {
      if (hinbanPrefix(code) === top && (!plain || (item.dateKey ?? '') > (plain.dateKey ?? ''))) plain = item;
    } else if (!headed || (item.dateKey ?? '') > (headed.dateKey ?? '')) headed = item;
  }
  const ex = (item) => (item ? { cid: String(item.cid), code: productCode(item.cid), head: cidHead(item.cid) } : null);
  return { plain: ex(plain), headed: ex(headed) };
}
