// ビルドの最後に、できあがった全ページのHTMLの日本語の文章へ、文節の区切り（<wbr>）を足す Astro の拡張。
// 中身は site/src/lib/phrase.js（なぜ必要か・しくみはそちら）。ページごとに手で印を付ける必要は無い（作品のコメントなど、あとから増える文章も、自動で対象になる）。
// 開発サーバー（npm run dev）では動かない（ビルドしたときだけ）。
// 失敗してもサイトの公開は止めない（そのときは、区切りが入らず、文章が以前の折り返し方になるだけ）。足りないことは tests/verify_dist.py が見つける。
import { fileURLToPath } from 'node:url';
import { phraseDirectory } from '../lib/phrase.js';

export default function phraseBreaks() {
  return {
    name: 'phrase-breaks',
    hooks: {
      'astro:build:done': ({ dir, logger }) => {
        try {
          const changed = phraseDirectory(fileURLToPath(dir));
          logger.info(`日本語の文章に、文節の区切りを入れました（${changed}ページ）`);
        } catch (e) {
          logger.warn(`文節の区切りを入れられませんでした（文章は、これまでの折り返し方になります）: ${e && e.message ? e.message : e}`);
        }
      },
    },
  };
}
