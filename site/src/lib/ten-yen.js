// FANZAの「10円セール」（動画・同人・ゲーム）の部品（画面に依存しない。tests/test_ten_yen.mjs）。
// 運営者の希望「動画・同人・ゲームのどれも、10円セールの時は大イベント。開催中はものすごく訴求したいし、SEOもかなり上位に来るように」（2026-10-09）。
// データは data/ten_yen.json（scripts/ten_yen.py。毎日の更新と、開催中の入れかわりに合わせて1日に数回）。
// 書くのはデータから数えた事実だけ（いま10円の作品の本数・終わりの日時・このサイトが見かけた開催の日）。次の開催の予想は書かない。
import { isDay, normalizeItems } from './items.js';
import { floorItemPath, normalizeFloor } from './floors.js';
import { itemHref } from './plan.js';
import { isMinorTitle } from './gacha.js';
import { bestRank } from './popularity.js';
import { endIso, endLabel } from './sale.js';

export const TEN_YEN_PRICE = 10;
export const TEN_YEN_PATH = '/sale/10yen/';
export const TEN_YEN_KEYS = ['video', 'doujin', 'game'];
export const TEN_YEN_NAMES = { video: 'FANZA動画', doujin: 'FANZA同人', game: 'FANZAゲーム' };
export const TEN_YEN_SHORT = { video: '動画', doujin: '同人', game: 'ゲーム' };
export const TEN_YEN_SINCE = '2026-10-09'; // 記録を始めた日（scripts/ten_yen.py を足した日）
export const TEN_YEN_HERO_COVERS = 6; // トップ・売り場のトップの大きな案内に並べる表紙の数
export const TEN_YEN_DEALS = 6; // 開催していないあいだの「割引の大きい作品」の本数（売り場ごと）

const CHECKED = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;
const END = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;
const isObj = (v) => v && typeof v === 'object' && !Array.isArray(v);

/** 売り場ごとの10円セールのページ（動画＝全部の売り場をまとめたページ） */
export const tenYenPath = (key = 'video') => (key === 'video' ? TEN_YEN_PATH : `/${key}/sale/10yen/`);

/** "2026-10-09 22:15" → "10月9日 22:15" */
export const checkedLabel = (checked) => (CHECKED.test(String(checked ?? '')) ? `${+checked.slice(5, 7)}月${+checked.slice(8, 10)}日 ${+checked.slice(11, 13)}:${checked.slice(14, 16)}` : '');
const md = (day) => (isDay(day) ? `${+day.slice(5, 7)}月${+day.slice(8, 10)}日` : '');

/**
 * ten_yen.json → { checked, items: { video, doujin, game }（いま10円の作品）, runs（このサイトが見かけた開催。新しい順） }。
 * 作品には tenYen: { price, listPrice, off, title（キャンペーンの名前）, end（終わりの日時。分からなければ ''） } を足す。
 * このサイトのデータにある作品（動画は videoByCid・同人/ゲームは floorByCid）は、そちらの形（コメント・作品ページ）を使う。
 * 確かめた時刻より前に終わっていた作品・未成年を連想させる作品・予約の作品は入れない
 */
export function normalizeTenYen(raw, { today = '', videoByCid = new Map(), floorByCid = {} } = {}) {
  const data = isObj(raw) ? raw : {};
  const checked = CHECKED.test(String(data.checked ?? '')) ? data.checked : '';
  const rowsOf = (k) => (Array.isArray(data[k]) ? data[k] : []).filter((r) => isObj(r) && r.price === TEN_YEN_PRICE
    && !(END.test(String(r.sale_end ?? '')) && checked && r.sale_end < checked));
  const extra = (r) => {
    const listPrice = Number.isInteger(r?.list_price) && r.list_price > TEN_YEN_PRICE ? r.list_price : null;
    return {
      price: TEN_YEN_PRICE,
      listPrice,
      off: listPrice ? Math.round((1 - TEN_YEN_PRICE / listPrice) * 100) : null,
      title: String(r?.sale_title ?? '').trim().slice(0, 60),
      end: END.test(String(r?.sale_end ?? '')) ? r.sale_end : '',
    };
  };
  const items = {};
  // 動画: 人気の高い順（このサイトの人気順の順位）→ 定価の高い順（値引きの大きい順）
  const vRows = rowsOf('video');
  const vBy = new Map(vRows.map((r) => [String(r.cid), r]));
  items.video = normalizeItems(vRows)
    .filter((i) => i.url && i.dateKey <= (today || '9999') && !isMinorTitle(i.title))
    .map((i) => ({ ...(videoByCid.get(i.cid) ?? i), tenYen: extra(vBy.get(i.cid)) }))
    .sort((a, b) => (bestRank(a.popAll ?? null, a.popNew ?? null) ?? Infinity) - (bestRank(b.popAll ?? null, b.popNew ?? null) ?? Infinity)
      || (b.tenYen.listPrice ?? 0) - (a.tenYen.listPrice ?? 0) || a.cid.localeCompare(b.cid));
  // 同人・ゲーム: 人気順（集めたときの順位）
  for (const k of TEN_YEN_KEYS.slice(1)) {
    const rows = rowsOf(k);
    const by = new Map(rows.map((r) => [String(r.cid), r]));
    const ranks = Object.fromEntries(rows.filter((r) => Number.isInteger(r.rank) && r.rank > 0).map((r) => [String(r.cid), r.rank]));
    items[k] = normalizeFloor({ items: rows, ranks }, k, today || '9999-12-31').items
      .filter((i) => !i.upcoming)
      .map((i) => {
        const mine = floorByCid[k]?.get(i.cid);
        return { ...(mine ?? i), tenYen: extra(by.get(i.cid)), hasPage: Boolean(mine) };
      });
  }
  const runs = (Array.isArray(data.runs) ? data.runs : [])
    .filter((r) => isObj(r) && TEN_YEN_KEYS.includes(r.floor) && isDay(r.first) && isDay(r.last) && r.first <= r.last)
    .map((r) => ({
      floor: r.floor,
      first: r.first,
      last: r.last,
      count: Number.isInteger(r.count) && r.count > 0 ? r.count : 1,
      end: END.test(String(r.end ?? '')) ? r.end : '',
      titles: (Array.isArray(r.titles) ? r.titles : []).map((t) => String(t ?? '').trim()).filter((t) => t && !isMinorTitle(t)).slice(0, 3),
    }))
    .sort((a, b) => b.first.localeCompare(a.first) || TEN_YEN_KEYS.indexOf(a.floor) - TEN_YEN_KEYS.indexOf(b.floor));
  return { checked, items, runs };
}

/**
 * いまの様子: { live（開催中の売り場）, counts, total, end（どの作品も終わりが分かるときの、いちばん遅い終わり＝全部が終わる時刻。分からなければ ''）,
 *   sameEnd（全部の作品の終わりが同じなら、その日時。案内に「○月○日 9:59まで」と出す） }。keys で売り場を絞る
 */
export function tenYenState(ty, keys = TEN_YEN_KEYS) {
  const counts = Object.fromEntries(keys.map((k) => [k, ty.items[k]?.length ?? 0]));
  const live = keys.filter((k) => counts[k] > 0);
  const works = live.flatMap((k) => ty.items[k]);
  const ends = works.map((i) => i.tenYen.end);
  const known = ends.length > 0 && ends.every(Boolean);
  const sorted = [...ends].sort();
  return {
    live,
    counts,
    total: works.length,
    end: known ? sorted.at(-1) : '',
    sameEnd: known && sorted[0] === sorted.at(-1) ? sorted[0] : '',
  };
}

/** 「動画12本・同人30本」（order: 並べる順。売り場のトップでは、その売り場を先に） */
export const countsText = (state, order = state.live) => order.filter((k) => state.counts[k] > 0).map((k) => `${TEN_YEN_SHORT[k]}${state.counts[k]}本`).join('・');

/** 終わりの「○月○日 9:59まで」（全部の作品が同じ終わりのときだけ。分からなければ ''） */
export const untilText = (state) => (state.sameEnd ? `${endLabel(state.sameEnd)}まで` : '');

/** 案内を隠す時刻（どの作品も終わりが分かるときの、全部が終わる時刻。ISO。分からなければ ''。public/sale.js の data-sale-end） */
export const hideAt = (state) => (state.end ? endIso(state.end) : '');

/** いちばん新しい開催（key の売り場。null なら全部の売り場から） */
export const latestRun = (ty, key = null) => ty.runs.find((r) => !key || r.floor === key) ?? null;

/** 開催の期間の文字（このサイトが見かけた日）: 「10月9日〜10月11日」（1日なら「10月9日」） */
export const runRangeText = (run) => (run.first === run.last ? md(run.first) : `${md(run.first)}〜${md(run.last)}`);

/** ページの title（検索結果に出る）。key: 'video' はまとめのページ（全部の売り場）、'doujin'・'game' は売り場のページ */
export function tenYenTitle(ty, key = 'video') {
  const state = tenYenState(ty, key === 'video' ? TEN_YEN_KEYS : [key]);
  const name = key === 'video' ? 'FANZA' : TEN_YEN_NAMES[key];
  const day = ty.checked ? `${+ty.checked.slice(5, 7)}月${+ty.checked.slice(8, 10)}日` : '';
  if (state.total > 0) {
    const until = untilText(state);
    return `${name} 10円セール開催中｜対象${state.total}本${until ? `・${until}` : ''}${day ? `【${day}更新】` : ''}`;
  }
  const ym = ty.checked ? `【${ty.checked.slice(0, 4)}年${+ty.checked.slice(5, 7)}月】` : '';
  return `${name}${key === 'video' ? ' ' : 'の'}10円セールはいつ？開催状況と対象作品${ym}`;
}

/** ページの説明文（meta description） */
export function tenYenDescription(ty, key = 'video') {
  const keys = key === 'video' ? TEN_YEN_KEYS : [key];
  const state = tenYenState(ty, keys);
  const name = key === 'video' ? 'FANZA' : TEN_YEN_NAMES[key];
  const at = checkedLabel(ty.checked);
  if (state.total > 0) {
    const until = untilText(state);
    return `${name}の10円セールで、いま10円で買える作品を${key === 'video' ? countsText(state) : `${state.total}本`}まとめました（${at}の時点）。${until ? `${until}。` : ''}開催中は1日に数回確かめて更新しています。`;
  }
  const run = key === 'video' ? latestRun(ty) : latestRun(ty, key);
  return `${name}の10円セール${key === 'video' ? '（動画・同人・ゲーム）' : ''}の開催状況を毎日確かめ、開催中は10円の対象作品を一覧にします。`
    + (run ? `前回は${runRangeText(run)}に見かけました（${TEN_YEN_SHORT[run.floor]}）。` : '');
}

/** 検索エンジンに出すか: まとめのページはいつも。売り場のページは、開催中か、その売り場の開催を見かけたことがあるときだけ（中身の無いページを出さない） */
export const tenYenIndexable = (ty, key = 'video') => key === 'video' || (ty.items[key]?.length ?? 0) > 0 || ty.runs.some((r) => r.floor === key);

/**
 * よくある質問（データから数えた事実だけ。次の開催の予想はしない）: [{ q, key（先に大きく出す答え。無ければ ''）, a }]
 */
export function tenYenFaq(ty, key = 'video') {
  const keys = key === 'video' ? TEN_YEN_KEYS : [key];
  const state = tenYenState(ty, keys);
  const name = key === 'video' ? 'FANZA' : TEN_YEN_NAMES[key];
  const at = checkedLabel(ty.checked);
  const out = [];
  out.push(state.total > 0
    ? { q: `${name}の10円セールは、いま開催していますか？`, key: `${state.total}本`, a: `開催中です。${at}の時点で、10円の作品が${state.total}本${key === 'video' && state.live.length > 1 ? `（${countsText(state)}）` : ''}あります。` }
    : { q: `${name}の10円セールは、いま開催していますか？`, key: 'なし', a: `${at ? `${at}の時点では、` : ''}10円の作品は見つかりませんでした。` });
  if (state.total > 0) {
    const ends = keys.filter((k) => state.counts[k] > 0).map((k) => {
      const e = [...new Set(ty.items[k].map((i) => i.tenYen.end).filter(Boolean))].sort();
      return e.length ? { k, end: e[0], more: e.length > 1 } : null;
    }).filter(Boolean);
    out.push({
      q: 'いつまでですか？',
      key: ends.length === 1 && !ends[0].more ? `${endLabel(ends[0].end)}まで` : '',
      a: ends.length
        ? `${ends.map((e) => `${TEN_YEN_SHORT[e.k]}は${endLabel(e.end)}まで${e.more ? '（作品によって違います）' : ''}`).join('、')}です。終わりの日時は変わることがあるので、FANZAの作品ページで確かめてください。`
        : '終わりの日時は、FANZAの作品ページで確かめてください。',
    });
  }
  const past = ty.runs.filter((r) => keys.includes(r.floor) && !(state.counts[r.floor] > 0 && r === latestRun(ty, r.floor)));
  out.push(past[0]
    ? { q: '前回の10円セールはいつでしたか？', key: runRangeText(past[0]), a: `このサイトの記録では、${runRangeText(past[0])}に見かけました（${TEN_YEN_SHORT[past[0].floor]}・いちばん多い日で${past[0].count}本）。` }
    : { q: '前回の10円セールはいつでしたか？', key: '', a: `このサイトの記録（${md(TEN_YEN_SINCE)}から）には、まだありません。` });
  out.push({ q: '次の10円セールはいつですか？', key: '', a: '決まった予定は分かりません。このページは、毎日0時すぎと、日中にも数回確かめて更新しています。' });
  out.push({ q: '10円の作品は、どうやって探していますか？', key: '', a: 'FANZA公式のAPIで、価格がちょうど10円に値下げされている作品を探しています（動画は安い順、同人・ゲームは人気順の上位から）。' });
  return out;
}

/** FAQPage の構造化データ */
export const faqLd = (faq) => ({
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: faq.map((f) => ({ '@type': 'Question', name: f.q, acceptedAnswer: { '@type': 'Answer', text: f.a } })),
});

/** カードの下の1行: 「10円（通常2,980円）」 */
export const tenYenNote = (item) => (item.tenYen.listPrice ? `10円（通常${item.tenYen.listPrice.toLocaleString('ja-JP')}円）` : '10円');

/** トップ・売り場のトップの大きな案内の表紙（人気の高い順に、動画→同人→ゲームから順番に1本ずつ） */
export function heroCovers(ty, keys = TEN_YEN_KEYS, n = TEN_YEN_HERO_COVERS) {
  const lists = keys.map((k) => ty.items[k].filter((i) => i.image_url && !i.vr));
  const out = [];
  for (let i = 0; out.length < n && lists.some((l) => i < l.length); i++) {
    for (const l of lists) if (i < l.length && out.length < n) out.push(l[i]);
  }
  return out;
}

/** 作品のリンク先: 作品ページがあれば作品ページ、無ければFANZAの作品ページ（動画は lib/plan.js の itemHref と同じ） */
export function tenYenHref(item, paged) {
  if (!item.floor) return itemHref(item, paged);
  return item.hasPage ? { href: floorItemPath(item.floor, item.cid), external: false } : { href: item.url, external: true };
}
