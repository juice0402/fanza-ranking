// 「運命の作品」（トップの発売中の新作の、きょうの日付の下。運営者の希望「上から見ていって、作品が決まらなかった人にオススメしたい」「スロットマシンみたいに3本」。2026-10-05）の候補づくり。
// 画面に依存しない（tests/test_gacha.mjs）。ブラウザで3本えらぶ動き（スロット）は site/public/gacha.js。
// 候補は、ひとことコメントのある・作品ページのある・発売済みの作品を、人気の高い順に GACHA_POOL 本まで。
// 未成年を連想させるタイトルの作品は、候補に入れない（こちらから「おすすめ」として出すため。判定は scripts/claude_comments.py の
// タイトルの見方（title_block_reason の "minor"）と同じ言葉の一覧。tests/test_gacha.mjs で突き合わせている）
import { castLine, truncate } from './items.js';
import { bestRank } from './popularity.js';
import { namesPattern, phraseZwsp } from './phrase.js';

export const GACHA_POOL = 80; // 候補の本数（トップのページに、小さなデータとして入れる）
export const GACHA_COMMENT_MAX = 70; // 出すひとことの長さ

// claude_comments.py の MINOR_WORDS から、大人どうしの言葉（MINOR_TITLE_OK）を除き、「筆おろし」を足したもの
export const MINOR_WORDS = ['未成年', '少女', 'ロリ', '児童', '幼', '女子高生', '女子校生', '女子中', '中学生', '高校生', '小学生',
  'JK', 'JC', 'JS', '制服', '校生', '学生', '生徒', '教え子', '園児', '子供', '子ども', '妹', '娘', '童顔', '貧乳',
  'つるぺた', 'パイパン', '処女',
  '学園', '職業体験', '家庭教師', '放課後', '部活', '修学旅行', '体操着', 'ブルマ', 'スク水', 'ランドセル', '保健室', '通学', '登校', '下校', '塾', '女の子', 'いじめっ子', 'J系'];
export const MINOR_TITLE_OK = ['幼なじみ', '幼馴染', '姉妹', '母娘', '男の娘', '看板娘', '肛門娘', '女の子', '処女'];
export const MINOR_TITLE_WORDS = [...MINOR_WORDS.filter((w) => !MINOR_TITLE_OK.includes(w)), '筆おろし'];
const C = '[●○◯〇＊*×]';
const MINOR_CENSORED = new RegExp(`[JＪjｊ]${C}|女子${C}{1,2}生|${C}{1,2}[学校]生|[中小高]${C}生|ロ${C}`);

/** タイトルが未成年を連想させるか（claude_comments.py の title_block_reason が "minor" になるもの） */
export function isMinorTitle(title) {
  const raw = String(title ?? '');
  const norm = raw.normalize('NFKC');
  let low = norm.toLowerCase();
  for (const ok of MINOR_TITLE_OK) low = low.split(ok.toLowerCase()).join('\u0000');
  return MINOR_TITLE_WORDS.some((w) => low.includes(w.toLowerCase())) || MINOR_CENSORED.test(norm) || MINOR_CENSORED.test(raw);
}

const rankOf = (i) => bestRank(i.popAll ?? null, i.popNew ?? null) ?? Infinity;

/**
 * 「運命の作品」の候補: [{ c: 作品ID, t: タイトル（文節の区切り U+200B 入り）, i: 画像, a: 出演者の1行, x: ひとこと（短く）, v: VRなら1, o: 単体作品なら1 }]
 * items: このサイトの全作品、paged: 作品ページのある作品ID
 */
export function gachaPool(items, paged, today, limit = GACHA_POOL) {
  const picked = items
    .filter((i) => i.comment && i.comment.trim() && paged.has(i.cid) && i.dateKey <= today && i.image_url && !isMinorTitle(i.title))
    .sort((a, b) => rankOf(a) - rankOf(b) || b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid))
    .slice(0, limit);
  const namesRe = namesPattern(picked.flatMap((i) => [...i.actress, i.maker]).filter((n) => n && n !== '不明'));
  return picked.map((i) => ({
    c: i.cid,
    t: phraseZwsp(i.title, namesRe),
    i: i.image_url,
    a: castLine(i.actress, 3, ''),
    x: phraseZwsp(truncate(i.comment.trim(), GACHA_COMMENT_MAX), namesRe),
    ...(i.vr ? { v: 1 } : {}),
    ...(i.solo ? { o: 1 } : {}),
  }));
}

/** ページに入れるJSON（<script type="application/json"> の中。「<」を書きかえて、タグとして読まれないようにする） */
export const gachaJson = (pool) => JSON.stringify(pool).replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026');
