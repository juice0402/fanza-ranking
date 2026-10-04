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
// 伏せ字（「チ○ポ」「J●」など）の記号。前後の文字とくっつけて、語の途中で改行しない
const CENSOR = /[○●◯〇×✕＊*■□]/;

/** i の前で改行してよいか（禁則・英数字・重ねる記号・伏せ字・守る範囲を守る）。keep: 改行してはいけない位置の Set（出演者名・メーカー名の途中など） */
function canBreakAt(text, i, keep) {
  if (keep && keep.has(i)) return false;
  const prev = text[i - 1];
  const next = text[i];
  if (CENSOR.test(prev) || CENSOR.test(next)) return false;
  // 数字と、そのあとの単位（「11／月」「3／本」「246／分」）、「年」「月」と、そのあとの数字（「2026年／10月」）は離さない（日付・本数を1かたまりに）
  if (/[0-9０-９]/.test(prev) && !/\s/.test(next)) return false;
  if (/[年月]/.test(prev) && /[0-9０-９]/.test(next)) return false;
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

/** text の [start, end) の文節が長ければ、禁則を守りながら、真ん中あたりで分ける（MAX_PHRASE 以下になるまで）。
 * 文字の種類が変わる所を、先に選ぶ（「ご利用／いただけません」）。分ける位置（text の中の番号）を cuts に足す */
function splitLong(text, start, end, keep, cuts) {
  const piece = text.slice(start, end);
  if (piece.trimEnd().length <= MAX_PHRASE) return;
  const mid = start + piece.length / 2;
  let best = -1;
  let bestScore = Infinity;
  for (let i = start + 2; i <= end - 2; i++) {
    if (!canBreakAt(text, i, keep)) continue;
    const score = Math.abs(i - mid) + (kindOf(text[i - 1]) !== kindOf(text[i]) ? 0 : 3);
    if (score < bestScore) {
      best = i;
      bestScore = score;
    }
  }
  if (best < 0) return; // 禁則・英数字・名前の途中で、分けられる所が無い
  cuts.push(best);
  splitLong(text, start, best, keep, cuts);
  splitLong(text, best, end, keep, cuts);
}

/** 守る語（出演者名・メーカー名）が text の中にあれば、その途中の位置の Set を返す（そこでは改行しない） */
export function protectedPositions(text, namesRe) {
  const keep = new Set();
  if (!namesRe || !text) return keep;
  for (const m of namesRe.find(text)) {
    for (let i = m.index + 1; i < m.index + m.text.length; i++) keep.add(i);
  }
  return keep;
}

/** 文章（HTMLの記号を含まない普通の文字列）→ 文節の配列。namesRe: 途中で改行しない語（出演者名・メーカー名）を探す道具（namesPattern で作る。無くてもよい） */
export function splitPhrases(text, namesRe = null) {
  if (!text) return [];
  const keep = protectedPositions(text, namesRe);
  const found = new Set(parser.parseBoundaries(text));
  for (let i = 1; i < text.length; i++) {
    // 中黒（・）のあと、開きかっこの前、閉じかっこのあと（次がひらがなでないとき。「…」から、のように続く助詞は離さない）も、改行してよい所にする（BudouXの区切りに足す）
    if (text[i - 1] === '\u30fb' || OPEN.test(text[i]) || (CLOSE.test(text[i - 1]) && kindOf(text[i]) !== 'hira')) found.add(i);
    // 空白のあとは、もともと改行してよい所（そこで先に分けてから、長いものだけを分ける）
    if (/\s/.test(text[i - 1]) && !/\s/.test(text[i])) found.add(i);
  }
  const bounds = [...found].sort((x, y) => x - y).filter((i) => (/\s/.test(text[i - 1]) && !keep.has(i)) || canBreakAt(text, i, keep));
  const cuts = [...bounds];
  let start = 0;
  for (const b of [...bounds, text.length]) {
    splitLong(text, start, b, keep, cuts);
    start = b;
  }
  const all = [...new Set(cuts)].sort((x, y) => x - y);
  const out = [];
  start = 0;
  for (const c of all) {
    out.push(text.slice(start, c));
    start = c;
  }
  out.push(text.slice(start));
  return out.filter((p) => p !== '');
}

// 名前のすぐあとの「さん」「ちゃん」「様」も、名前にくっつける（「青坂あおい／さん」で改行しない）
const NAME_SUFFIXES = ['さん', 'ちゃん', '様'];

/**
 * 名前の一覧 → 文章の中から名前を探す道具（2文字以上の名前だけ。名前が無ければ null）。
 * find(text) は、左から順に、重ならないように、その位置で一番長い名前（＋すぐあとの「さん」など）を探して [{ index, text }] を返す。
 * 過去作品が増えると名前が数万になり、1つの大きな正規表現では、ビルドが何十分もかかったため、名前の先頭2文字と長さで引く表にしてある。
 */
export function namesPattern(names) {
  const list = [...new Set((names || []).filter((n) => typeof n === 'string' && [...n.trim()].length >= 2).map((n) => n.trim()))];
  if (!list.length) return null;
  const known = new Set(list);
  const byHead = new Map(); // 先頭の2文字（UTF-16で2つ）→ その文字で始まる名前の長さ（長い順。同じ位置で、長い名前を先に選ぶ）
  for (const n of list) {
    const head = n.slice(0, 2);
    if (!byHead.has(head)) byHead.set(head, new Set());
    byHead.get(head).add(n.length);
  }
  for (const [head, lengths] of byHead) byHead.set(head, [...lengths].sort((x, y) => y - x));
  return {
    find(text) {
      const found = [];
      const str = String(text ?? '');
      for (let i = 0; i + 1 < str.length; ) {
        const lengths = byHead.get(str.slice(i, i + 2));
        const len = lengths ? lengths.find((l) => known.has(str.slice(i, i + l))) : undefined;
        const hit = len ? str.slice(i, i + len) : '';
        if (!hit) {
          i++;
          continue;
        }
        let end = i + hit.length;
        const suffix = NAME_SUFFIXES.find((x) => str.startsWith(x, end));
        if (suffix) end += suffix.length;
        found.push({ index: i, text: str.slice(i, end) });
        i = end;
      }
      return found;
    },
  };
}

/** この長さ（文字数）以下の名前は、<span class="nb">（white-space: nowrap）で包み、まったく改行しない（「S-Cute」の「-」のあとや、「犬/妄想族」の「/」のあとでも）。
 * 長い名前は包まない（狭い画面ではみ出さないように。区切りの <wbr> を入れないだけ） */
export const NOWRAP_MAX = 10;

// HTMLの文字参照（&amp; &#39; &#x27; など）。1文字として扱い、途中で区切らない
const ENTITY = /&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);/g;

/**
 * HTMLの「文字だけの部分」（タグの外）を1つ受け取り、文節の区切りに <wbr> を入れて、<span class="ph"> で包んで返す。
 * 日本語が MIN_JAPANESE 文字より少なければ、そのまま返す。前後の空白は、包みの外に残す。
 */
export function phraseText(htmlText, namesRe = null) {
  const m = htmlText.match(/^(\s*)([\s\S]*?)(\s*)$/);
  const [, lead, core, tail] = m;
  if (japaneseCount(core) < MIN_JAPANESE) {
    // 日本語が少ない（短い名前・英字の名前など）ときは、区切りは入れず、短い名前だけを改行しないように包む
    const wrapped = wrapNames(core, namesRe);
    return wrapped === core ? htmlText : `${lead}${wrapped}${tail}`;
  }
  // 文字参照は、1文字（￼）に置き換えてから区切りを探し、あとで元に戻す
  const refs = core.match(ENTITY) || [];
  const plain = core.replace(ENTITY, '￼');
  const phrases = splitPhrases(plain, namesRe);
  // 空白のあとには、<wbr> は要らない（空白で、もともと改行できる）
  const body = phrases.map((p, i) => (i === 0 || /\s$/.test(phrases[i - 1]) ? p : '<wbr>' + p)).join('');
  // 「～」をくっつけてから、名前を包む（文字参照は、まだ ￼ のまま。名前が「amp」などでも、文字参照の中を包まないように）。最後に文字参照を戻す
  let r = 0;
  const html = wrapNames(glueTilde(body), namesRe).replace(/￼/g, () => refs[r++]);
  return `${lead}<span class="ph">${html}</span>${tail}`;
}

/** 「～」「〜」の前では改行しない（「気持ちよ／～く」「オニごっこ／～集団」のように、行の頭に「～」が来るのを防ぐ）。
 * ブラウザは keep-all でも「～」の前で改行することがあるので、前の1文字（と、あいだの空白）と一緒に <span class="nb"> で包む */
function glueTilde(html) {
  // u フラグ: 絵文字など（4バイトの文字）を、半分に割らずに1文字として扱う。文字参照の代わりの ￼ と、タグの終わり（>）の直後は、くっつけない
  return html.replace(/([^\s>￼])(\s?)(?:<wbr>)?([～〜])/gu, '<span class="nb">$1$2$3</span>');
}

/** 文字列の中の短い名前（NOWRAP_MAX 文字以下）を <span class="nb"> で包む（名前の中には <wbr> が無いので、そのまま探せる） */
function wrapNames(text, namesRe) {
  if (!namesRe) return text;
  let out = '';
  let last = 0;
  for (const m of namesRe.find(text)) {
    // 長さは、あとに付けた「さん」などを除いて数える（「善場まみ（茉城まみ）さん」も、名前が10文字なので包む）
    const short = [...m.text.replace(/(?:さん|ちゃん|様)$/, '')].length <= NOWRAP_MAX;
    out += text.slice(last, m.index) + (short ? `<span class="nb">${m.text}</span>` : m.text);
    last = m.index + m.text.length;
  }
  return out + text.slice(last);
}

// 触らない所: コメント・script・style・title・textarea・pre・code・noscript・svg・template・select・option・button（中身ごと飛ばす）、
// すでに処理した <span class="ph">…</span>（もう一度かけても二重にならない）、ふつうのタグ、doctype
const SKIP = String.raw`<!--[\s\S]*?-->` +
  String.raw`|<(script|style|textarea|title|pre|code|noscript|svg|template|select|option|button)\b(?:"[^"]*"|'[^']*'|[^>"'])*>[\s\S]*?<\/\1\s*>` +
  String.raw`|<span class="ph">(?:[^<]|<wbr>|<span class="nb">[^<]*<\/span>)*<\/span>` +
  String.raw`|<span class="nb">[^<]*<\/span>` +
  String.raw`|<\/?[A-Za-z][A-Za-z0-9:-]*(?:"[^"]*"|'[^']*'|[^>"'])*>` +
  String.raw`|<![A-Za-z][^>]*>`;

/** HTML全体 → 文章の部分だけに文節の区切りを足したHTML。namesRe: 途中で改行しない名前（namesPattern で作る。無くてもよい） */
export function phraseHtml(html, namesRe = null) {
  const re = new RegExp(SKIP, 'gi');
  let out = '';
  let last = 0;
  for (const m of html.matchAll(re)) {
    out += phraseText(html.slice(last, m.index), namesRe) + m[0];
    last = m.index + m[0].length;
  }
  return out + phraseText(html.slice(last), namesRe);
}

/** フォルダの中の全 .html を書き換える（ビルドの最後に使う）。書き換えたファイルの数を返す。names: 途中で改行しない名前（出演者・メーカー） */
export function phraseDirectory(dir, names = []) {
  const namesRe = namesPattern(names);
  let changed = 0;
  const walk = (d) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith('.html')) {
        const before = fs.readFileSync(p, 'utf-8');
        const after = phraseHtml(before, namesRe);
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

/** 元に戻す（テストと検査用）: <wbr> を消し、<span class="nb"> と <span class="ph"> の包みを外す */
export function unphraseHtml(html) {
  return html
    .replace(/<wbr\s*\/?>/g, '')
    .replace(/<span class="nb">([^<]*)<\/span>/g, '$1')
    .replace(/<span class="ph">([^<]*)<\/span>/g, '$1');
}

/** ブラウザで作る文章（作品検索・お気に入り）のための形: 文節の区切りに、幅のない空白（U+200B）を入れた文字列。
 * 画面では、CSS の .ph-js（word-break: keep-all）と組み合わせて、区切りの所だけで改行させる（ビルドの <wbr> と同じ考え方） */
export const ZWSP = '\u200b';
export function phraseZwsp(text, namesRe = null) {
  if (!text || japaneseCount(text) < MIN_JAPANESE) return text || '';
  const parts = splitPhrases(text, namesRe);
  const joined = parts.map((p, i) => (i === 0 || /\s$/.test(parts[i - 1]) ? p : ZWSP + p)).join('');
  // 「～」の前で改行しない（ビルドの glueTilde と同じ考え方。文字で表すので、改行を止める見えない文字 U+2060 と、改行しない空白 U+00A0 を使う）
  return joined.replace(/(\S)\u200b?([～〜])/g, '$1\u2060$2').replace(/(\S) ([～〜])/g, '$1\u00a0$2');
}
