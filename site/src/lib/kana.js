// 読みがな（data/readings.json。scripts/readings.py が FANZA公式のAPIから集める）と、50音の並びの部品
// （画面に依存しない。tests/test_kana.mjs）。運営者の希望「APIで使えるものは全部。SEO対策も徹底」（2026-10-10）。
// 使い道: 一覧のページ（メーカー・シリーズ・ジャンル・サークル/ブランド・作家）の「50音で探す」と、作品検索で、ひらがなで打っても見つかるようにすること

/** 50音の行（見出し・印・その行に入る文字）。濁音・半濁音・小さい字は、もとの行に入れる */
export const KANA_ROWS = [
  { head: 'あ', key: 'a', chars: 'あいうえおぁぃぅぇぉゔ' },
  { head: 'か', key: 'ka', chars: 'かきくけこがぎぐげごゕゖ' },
  { head: 'さ', key: 'sa', chars: 'さしすせそざじずぜぞ' },
  { head: 'た', key: 'ta', chars: 'たちつてとだぢづでどっ' },
  { head: 'な', key: 'na', chars: 'なにぬねの' },
  { head: 'は', key: 'ha', chars: 'はひふへほばびぶべぼぱぴぷぺぽ' },
  { head: 'ま', key: 'ma', chars: 'まみむめも' },
  { head: 'や', key: 'ya', chars: 'やゆよゃゅょ' },
  { head: 'ら', key: 'ra', chars: 'らりるれろ' },
  { head: 'わ', key: 'wa', chars: 'わをんゎゐゑ' },
];
export const KANA_OTHER = { head: '英数', key: 'other', chars: '' };
export const KANA_INDEX_MIN = 20; // 50音の並びを出すのは、読みの分かる名前がこれ以上あり、
export const KANA_INDEX_RATIO = 0.5; // 全体のこの割合以上のときだけ（読みの分からない名前ばかりの一覧では出さない）
export const KANA_TOP = 30; // 50音の並びの上に出す「作品数の多い順」のタイル

/** カタカナ → ひらがな（NFKC で半角・全角もそろえる）。読みの比べ方に使う */
export function toHiragana(text) {
  let s = String(text ?? '');
  s = s.normalize('NFKC');
  return s.replace(/[ァ-ヶ]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0x60));
}

/** 読み → 50音の行（KANA_ROWS の1つか KANA_OTHER） */
export function kanaRow(reading) {
  const first = toHiragana(reading).trim().charAt(0);
  return KANA_ROWS.find((r) => first && r.chars.includes(first)) ?? KANA_OTHER;
}

// 読みは、ひらがな・カタカナ・英数字・記号だけ（FANZAの一覧には、読みの欄に漢字の名前がそのまま入っているものがある。2026-10-10 に本物で確かめた）
const KANJI = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/;
const isRuby = (v) => typeof v === 'string' && v.trim() !== '' && v.length <= 60 && !KANJI.test(v);
const READING_KINDS = ['genre', 'maker', 'series', 'author'];

/**
 * readings.json → { updated, of(floor, kind, key) → 読み（ひらがな。無ければ ''） }
 * floor: 'video'・'doujin'・'game' など。kind: genre（キーは名前）・maker（動画は名前、ほかは id）・series（id）・author（名前）
 */
export function normalizeReadings(raw) {
  const ok = raw && typeof raw === 'object' && !Array.isArray(raw);
  const maps = new Map();
  if (ok) {
    for (const [floor, kinds] of Object.entries(raw)) {
      if (floor === 'updated' || floor === 'next' || !kinds || typeof kinds !== 'object' || Array.isArray(kinds)) continue;
      for (const kind of READING_KINDS) {
        const src = kinds[kind];
        if (!src || typeof src !== 'object' || Array.isArray(src)) continue;
        const m = new Map();
        for (const [k, v] of Object.entries(src)) if (isRuby(v)) m.set(String(k), toHiragana(v).replace(/\s+/g, ''));
        maps.set(`${floor}.${kind}`, m);
      }
    }
  }
  return {
    updated: ok && /^\d{4}-\d{2}-\d{2}$/.test(String(raw.updated ?? '')) ? raw.updated : '',
    of: (floor, kind, key) => maps.get(`${floor}.${kind}`)?.get(String(key ?? '')) ?? '',
    size: (floor, kind) => maps.get(`${floor}.${kind}`)?.size ?? 0,
  };
}

const byReading = (a, b) => (a.reading < b.reading ? -1 : a.reading > b.reading ? 1 : a.name < b.name ? -1 : a.name > b.name ? 1 : 0);

/**
 * 一覧の名前を、50音の行ごとに分ける → { show, top, rows: [{ head, key, id, entries }] }
 * entries: [{ name, path, count, reading }]（作品数の多い順で渡す）。読みの分からない名前は「英数」の行のあと（読みの代わりに名前で並べる）
 * show: 50音の並びを出すか（読みの分かる名前が KANA_INDEX_MIN 以上・KANA_INDEX_RATIO 以上）
 */
export function kanaIndex(entries, { top = KANA_TOP, prefix = 'kana' } = {}) {
  const withReading = entries.filter((e) => e.reading);
  const show = withReading.length >= KANA_INDEX_MIN && withReading.length >= entries.length * KANA_INDEX_RATIO;
  if (!show) return { show: false, top: entries, rows: [] };
  const rows = new Map();
  for (const e of entries) {
    const row = e.reading ? kanaRow(e.reading) : KANA_OTHER;
    if (!rows.has(row.key)) rows.set(row.key, { head: row.head, key: row.key, id: `${prefix}-${row.key}`, entries: [] });
    rows.get(row.key).entries.push({ ...e, reading: e.reading || toHiragana(e.name).toLowerCase() });
  }
  const order = [...KANA_ROWS, KANA_OTHER].map((r) => r.key);
  return {
    show: true,
    top: entries.slice(0, top),
    rows: order.filter((k) => rows.has(k)).map((k) => ({ ...rows.get(k), entries: rows.get(k).entries.sort(byReading) })),
  };
}

/** 50音の行の、飛び先のボタン（行が無ければ押せない） */
export function kanaJumps(rows, prefix = 'kana') {
  const has = new Set(rows.map((r) => r.key));
  return [...KANA_ROWS, KANA_OTHER].map((r) => ({ head: r.head, href: has.has(r.key) ? `#${prefix}-${r.key}` : '' }));
}

/** 見出しの下に出す読みがな（名前と同じ読み＝ひらがなの名前などは出さない） */
export function readingLine(name, reading) {
  const norm = (t) => toHiragana(t).toLowerCase().replace(/[\s　・·.\-]/g, '');
  const r = String(reading ?? '').trim();
  return r && !KANJI.test(r) && norm(r) !== norm(name) ? toHiragana(r) : '';
}
