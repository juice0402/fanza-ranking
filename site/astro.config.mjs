// @ts-check
import { defineConfig } from 'astro/config';
import { SITE_URL } from './src/config.js';
import phraseBreaks from './src/integrations/phrase-breaks.js';

// https://astro.build/config
export default defineConfig({
  // 独自ドメインにしたら、src/config.js の SITE_URL を書き換えるだけでOK
  site: SITE_URL,
  // 日本語の文章を、文節のところで改行させる（ビルドの最後に、全ページへ）。しくみは src/lib/phrase.js
  integrations: [phraseBreaks()],
});
