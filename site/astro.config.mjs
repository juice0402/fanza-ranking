// @ts-check
import { defineConfig } from 'astro/config';

// https://astro.build/config
export default defineConfig({
  // 独自ドメインにしたら、ここと src/lib/items.js の SITE_URL、public/robots.txt を書き換えてね
  site: 'https://fanza-ranking.pages.dev',
});
