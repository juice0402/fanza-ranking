// 日本語の文章を「文節」のところで改行させるための部品（ビルドのときに、できあがったHTMLに足す。ブラウザでは動かない）。
//
// なぜ必要か:
//   日本語は、ふつうに折り返すと、どの文字の間でも改行されてしまう（例:「専用ページがあ／り」「出演者／を探せます」）。
//   CSS の `word-break: auto-phrase`（文節で折り返す）は、Chrome にはあるが、iPhone / iPad の Safari 系にはまだ無い（2026-10 に確認）。
//   そこで、文章を文節に区切って、区切りの所に <wbr>（ここで改行してよい、という目印）を入れておく。
//   あわせて、その文章を <span class="ph"> で包み、CSS（site.css の .ph）で `word-break: keep-all`（目印の所以外では改行しない）にする。
//   この組み合わせは、BudouX の公式の使い方で、Chrome・Safari・Firefox のどれでも同じように動く。
//
// 文節の区切りは BudouX（Google。Apache-2.0）の日本語モデルで決める。
//   モデル: site/src/lib/budoux-ja.js（https://github.com/google/budoux の budoux/models/ja.json を JavaScript の形にしたもの。ライセンスは budoux-LICENSE.txt）
//   区切りを決める式は、BudouX の javascript/src/parser.ts と同じ（下の parseBoundaries）。
//
// 使うところ: site/src/integrations/phrase-breaks.js（ビルドの最後に dist の全HTMLへ）。テスト: tests/test_phrase.mjs

import fs from 'node:fs';
import path from 'node:path';
import MODEL from './budoux-ja.js';

/** この数より日本語（ひらがな・カタカナ・漢字）が少ない文字列には、何もしない（ごく短いラベルなど）。これ以上あれば、区切りが無くても <span class="ph"> で包み、語の途中で改行されないようにする（出演者名など） */
export const MIN_JAPANESE = 4;

// 文字列の中で、日本語の文字の数
const JAPANESE = /[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]/g;
const japaneseCount = (s) => (s.match(JAPANESE) || []).length;

/** BudouX の「区切り」の式（javascript/src/parser.ts と同じ）。区切りの位置（その文字の前で改行してよい番号）の配列を返す */
export function createParser(model = MODEL) {
  const groups = Object.fromEntries(Object.entries(model).map(([k, v]) => [k, new Map(Object.entries(v))]));
  const baseScore = -0.5 * Object.values(model).flatMap((g) => Object.values(g)).reduce((a, b) => a + b, 0);
  const get = (name, key) => groups[name]?.get(key) || 0;
  return {
    parseBoundaries(sentence) {
      const out = [];
      for (let i = 1; i < sentence.length; i++) {
        if ((sentence.codePointAt(i - 1) ?? 0) > 0xffff) continue; // サロゲートペア（絵文字など）の途中では区切らない
        let score = baseScore;
        score += get('UW1', sentence.substring(i - 3, i - 2));
        score += get('UW2', sentence.substring(i - 2, i - 1));
        score += get('UW3', sentence.substring(i - 1, i));
        score += get('UW4', sentence.substring(i, i + 1));
        score += get('UW5', sentence.substring(i + 1, i + 2));
        score += get('UW6', sentence.substring(i + 2, i + 3));
        score += get('BW1', sentence.substring(i - 2, i));
        score += get('BW2', sentence.substring(i - 1, i + 1));
        score += get('BW3', sentence.substring(i, i + 2));
        score += get('TW1', sentence.substring(i - 3, i));
        score += get('TW2', sentence.substring(i - 2, i + 1));
        score += get('TW3', sentence.substring(i - 1, i + 2));
        score += get('TW4', sentence.substring(i, i + 3));
        if (score > 0) out.push(i);
      }
      return out;
    },
  };
}

const parser = createParser();

// 英数字・記号（ASCII）どうしの間では、区切らない（「FANZA」「2026-10-04」の途中で改行しないため）
const isAsciiWord = (ch) => /^[\x21-\x7e]$/.test(ch);

// 禁則（行のはじめに来てはいけない文字・行の終わりに来てはいけない文字）。ここでは区切らない
const NO_START = /[\s、。，．,.）)」』】〕〉》］｝!?！？:：;；・ー…‥〜～々ゝゞヽヾぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ‼⁇⁈⁉%％°′″\u2060]/;
const NO_END = /[\s（(「『【〔〈《［｛]/;
const OPEN = /[（「『【〔〈《［｛]/; // 日本語のかっこだけ（ASCIIの ( ) は、BudouXに任せる）
const CLOSE = /[）」』】〕〉》］｝]/;
// 同じ文字を2つ重ねて使う記号（「……」「――」）は、間で区切らない
const PAIRED = /[…‥―─━]/;

/** i の前で改行してよいか（禁則・英数字・重ねる記号を守る） */
function canBreakAt(text, i) {
  const prev = text[i - 1];
  const next = text[i];
  if (NO_START.test(next) && !(next === '・')) return false;
  if (next === '・') return false; // 中黒は、前の語にくっつける（「・」で改行するのは、その後ろ）
  if (NO_END.test(prev) && !/\s/.test(prev)) return false;
  if (isAsciiWord(prev) && isAsciiWord(next)) return false;
  if (PAIRED.test(prev) && prev === next) return false;
  return true;
}

/** この長さ（文字数）をこえる文節は、途中にも、改行してよい所を足す（長い題名などが、狭い画面で、禁則を無視して折り返されないように） */
export const MAX_PHRASE = 8;

// 文字の種類（ひらがな・カタカナ・漢字・それ以外）。種類が変わる所は、語の切れ目になりやすい
const kindOf = (ch) => (/[\u3040-\u309f]/.test(ch) ? 'hira' : /[\u30a0-\u30ff]/.test(ch) ? 'kata' : /[\u3400-\u4dbf\u4e00-\u9fff]/.test(ch) ? 'kanji' : 'other');

/** 長い文節を、禁則を守りながら、真ん中あたりで分ける（MAX_PHRASE 以下になるまで）。文字の種類が変わる所を、先に選ぶ（「ご利用／いただけません」） */
function splitLong(phrase) {
  if (phrase.trimEnd().length <= MAX_PHRASE) return [phrase];
  const mid = phrase.length / 2;
  let best = -1;
  let bestScore = Infinity;
  for (let i = 2; i <= phrase.length - 2; i++) {
    if (!canBreakAt(phrase, i)) continue;
    const score = Math.abs(i - mid) + (kindOf(phrase[i - 1]) !== kindOf(phrase[i]) ? 0 : 3);
    if (score < bestScore) {
      best = i;
      bestScore = score;
    }
  }
  if (best < 0) return [phrase]; // 禁則・英数字で、分けられる所が無い
  return [...splitLong(phrase.slice(0, best)), ...splitLong(phrase.slice(best))];
}

/** 文章（HTMLの記号を含まない普通の文字列）→ 文節の配列 */
export function splitPhrases(text) {
  if (!text) return [];
  const found = new Set(parser.parseBoundaries(text));
  for (let i = 1; i < text.length; i++) {
    // 中黒（・）のあと、開きかっこの前、閉じかっこのあと（次がひらがなでないとき。「…」から、のように続く助詞は離さない）も、改行してよい所にする（BudouXの区切りに足す）
    if (text[i - 1] === '\u30fb' || OPEN.test(text[i]) || (CLOSE.test(text[i - 1]) && kindOf(text[i]) !== 'hira')) found.add(i);
  }
  const bounds = [...found].sort((x, y) => x - y).filter((i) => canBreakAt(text, i));
  const rough = [];
  let start = 0;
  for (const b of bounds) {
    rough.push(text.slice(start, b));
    start = b;
  }
  rough.push(text.slice(start));
  // 空白のあとは、もともと改行してよい所。そこで先に分けてから、長いものだけを分ける
  return rough.flatMap((p) => p.split(/(?<=\s)(?=\S)/)).flatMap(splitLong);
}

// HTMLの文字参照（&amp; &#39; &#x27; など）。1文字として扱い、途中で区切らない
const ENTITY = /&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);/g;

/**
 * HTMLの「文字だけの部分」（タグの外）を1つ受け取り、文節の区切りに <wbr> を入れて、<span class="ph"> で包んで返す。
 * 日本語が MIN_JAPANESE 文字より少なければ、そのまま返す。前後の空白は、包みの外に残す。
 */
export function phraseText(htmlText) {
  const m = htmlText.match(/^(\s*)([\s\S]*?)(\s*)$/);
  const [, lead, core, tail] = m;
  if (japaneseCount(core) < MIN_JAPANESE) return htmlText;
  // 文字参照は、1文字（￼）に置き換えてから区切りを探し、あとで元に戻す
  const refs = core.match(ENTITY) || [];
  const plain = core.replace(ENTITY, '￼');
  const phrases = splitPhrases(plain);
  let r = 0;
  const restored = phrases.map((p) => p.replace(/￼/g, () => refs[r++]));
  // 空白のあとには、<wbr> は要らない（空白で、もともと改行できる）
  const body = restored.map((p, i) => (i === 0 || /\s$/.test(restored[i - 1]) ? p : '<wbr>' + p)).join('');
  return `${lead}<span class="ph">${body}</span>${tail}`;
}

// 触らない所: コメント・script・style・title・textarea・pre・code・noscript・svg・template・select・option・button（中身ごと飛ばす）、
// すでに処理した <span class="ph">…</span>（もう一度かけても二重にならない）、ふつうのタグ、doctype
const SKIP = String.raw`<!--[\s\S]*?-->` +
  String.raw`|<(script|style|textarea|title|pre|code|noscript|svg|template|select|option|button)\b(?:"[^"]*"|'[^']*'|[^>"'])*>[\s\S]*?<\/\1\s*>` +
  String.raw`|<span class="ph">[\s\S]*?<\/span>` +
  String.raw`|<\/?[A-Za-z][A-Za-z0-9:-]*(?:"[^"]*"|'[^']*'|[^>"'])*>` +
  String.raw`|<![A-Za-z][^>]*>`;

/** HTML全体 → 文章の部分だけに文節の区切りを足したHTML */
export function phraseHtml(html) {
  const re = new RegExp(SKIP, 'gi');
  let out = '';
  let last = 0;
  for (const m of html.matchAll(re)) {
    out += phraseText(html.slice(last, m.index)) + m[0];
    last = m.index + m[0].length;
  }
  return out + phraseText(html.slice(last));
}

/** フォルダの中の全 .html を書き換える（ビルドの最後に使う）。書き換えたファイルの数を返す */
export function phraseDirectory(dir) {
  let changed = 0;
  const walk = (d) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith('.html')) {
        const before = fs.readFileSync(p, 'utf-8');
        const after = phraseHtml(before);
        if (after !== before) {
          fs.writeFileSync(p, after);
          changed++;
        }
      }
    }
  };
  walk(dir);
  return changed;
}

/** 元に戻す（テストと検査用）: <wbr> を消し、<span class="ph"> の包みを外す */
export function unphraseHtml(html) {
  return html.replace(/<wbr\s*\/?>/g, '').replace(/<span class="ph">([\s\S]*?)<\/span>/g, '$1');
}
