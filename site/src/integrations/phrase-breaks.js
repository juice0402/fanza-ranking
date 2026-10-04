// ビルドの最後に、できあがった全ページのHTMLの日本語の文章へ、文節の区切り（<wbr>）を足す Astro の拡張。
// 中身は site/src/lib/phrase.js（なぜ必要か・しくみはそちら）。ページごとに手で印を付ける必要は無い（作品のコメントなど、あとから増える文章も、自動で対象になる）。
// 開発サーバー（npm run dev）では動かない（ビルドしたときだけ）。
// 失敗してもサイトの公開は止めない（そのときは、区切りが入らず、文章が以前の折り返し方になるだけ）。足りないことは tests/verify_dist.py が見つける。
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { phraseDirectory } from '../lib/phrase.js';

/** 途中で改行しない名前（出演者・メーカー）を、作品データから集める。読めなければ空（名前を守らないだけ） */
export function namesFromData(file = new URL('../data/new_releases.json', import.meta.url)) {
  try {
    const items = JSON.parse(fs.readFileSync(file, 'utf-8'));
    if (!Array.isArray(items)) return [];
    return [...new Set(items.flatMap((x) => [...(Array.isArray(x?.actress) ? x.actress : []), x?.maker]))].filter((n) => typeof n === 'string' && n && n !== '不明');
  } catch {
    return [];
  }
}

export default function phraseBreaks() {
  return {
    name: 'phrase-breaks',
    hooks: {
      'astro:build:done': ({ dir, logger }) => {
        try {
          const changed = phraseDirectory(fileURLToPath(dir), namesFromData());
          logger.info(`日本語の文章に、文節の区切りを入れました（${changed}ページ）`);
        } catch (e) {
          logger.warn(`文節の区切りを入れられませんでした（文章は、これまでの折り返し方になります）: ${e && e.message ? e.message : e}`);
        }
      },
    },
  };
}
