// @ts-check
import { defineConfig } from 'astro/config';
import { SITE_URL } from './src/config.js';

// https://astro.build/config
export default defineConfig({
  // 独自ドメインにしたら、src/config.js の SITE_URL を書き換えるだけでOK
  site: SITE_URL,
});
