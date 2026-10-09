// 画面の写真（スクリーンショット）を撮って、形のくずれを調べる道具（運営者の「改行・高さがそろっていない所を全域調査して」。2026-10-09）。
// .github/workflows/screens.yml が、GitHub の上で動かす（Claude のクラウド環境からは pages.dev が見えないため）。
// 設定は scripts/screens.json（base: 撮るサイト、paths: ページ、widths: 画面の幅、chunks: 1ページを何枚に分けて撮るか）。
// 作品の画像は写さない（灰色の箱にする。形だけを見るため・公開のリポジトリに作品の画像を置かないため）。
// 結果: shots/<ページ>-<幅>-<番号>.png と shots/report.json（横にはみ出す要素・同じ行の棚でタイトルの高さがずれている所・行の数がそろわない所）
import fs from 'node:fs';
import { chromium } from 'playwright';

const cfg = JSON.parse(fs.readFileSync(new URL('./screens.json', import.meta.url), 'utf-8'));
const out = 'shots';
fs.mkdirSync(out, { recursive: true });
const HIDE = `img, video, iframe, picture source { opacity: 0 !important; }
.item-cover, .mini-cover, .reel-window, .detail-cover, .medal-cover, .genre-thumb, .face, .topic-thumb, .sample-link, .pick-cover, .sale-stack { background: #4a4560 !important; }`;

const browser = await chromium.launch();
const report = [];
for (const width of cfg.widths) {
  const mobile = width < 600;
  const height = mobile ? 844 : 900;
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile, locale: 'ja-JP' });
  await context.addInitScript(() => {
    try { localStorage.setItem('age-ok', '1'); } catch (e) {}
  });
  for (const path of cfg.paths) {
    const page = await context.newPage();
    const name = path.replace(/^\/|\/$/g, '').replace(/[^A-Za-z0-9_-]+/g, '_') || 'home';
    try {
      await page.goto(`${cfg.base}${path}${path.includes('?') ? '&' : '?'}cb=${Date.now()}`, { waitUntil: 'networkidle', timeout: 60000 });
      await page.addStyleTag({ content: HIDE });
      await page.waitForTimeout(600);
      // 形の点検（数字で）
      const found = await page.evaluate(() => {
        const issues = [];
        const vw = document.documentElement.clientWidth;
        if (document.documentElement.scrollWidth > vw + 1) issues.push({ kind: 'page-overflow', w: document.documentElement.scrollWidth, vw });
        for (const el of document.querySelectorAll('body *')) {
          const r = el.getBoundingClientRect();
          if (r.width > 0 && r.right > vw + 2 && getComputedStyle(el).position !== 'fixed' && !el.closest('.seg-scroll, .ws-tag-list, [style*="overflow"]')) {
            issues.push({ kind: 'overflow', el: el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : ''), right: Math.round(r.right), text: (el.textContent || '').trim().slice(0, 30) });
            if (issues.length > 40) break;
          }
        }
        // 棚の同じ行で、タイトルの上の位置がずれている所
        for (const shelf of document.querySelectorAll('.shelf, .mini-shelf')) {
          const rows = new Map();
          for (const cell of shelf.children) {
            const t = cell.querySelector('.item-title, .mini-title');
            if (!t || cell.offsetParent === null) continue;
            const top = Math.round(cell.getBoundingClientRect().top);
            const tt = Math.round(t.getBoundingClientRect().top);
            if (!rows.has(top)) rows.set(top, []);
            rows.get(top).push(tt);
          }
          for (const [top, ts] of rows) if (Math.max(...ts) - Math.min(...ts) > 2) issues.push({ kind: 'title-misaligned', section: shelf.closest('section')?.querySelector('h2,h3')?.textContent?.trim().slice(0, 20) ?? '', diff: Math.max(...ts) - Math.min(...ts) });
        }
        // 1行に1〜2文字だけが残る改行（見出し・説明・チップ）
        for (const el of document.querySelectorAll('h1, h2, h3, .hero-lead, .section-note, .chip, .chip-link, .name-link-name, .item-title, .faq-text')) {
          if (el.offsetParent === null) continue;
          const range = document.createRange();
          range.selectNodeContents(el);
          const rects = [...range.getClientRects()].filter((r) => r.width > 0);
          const lines = new Map();
          for (const r of rects) lines.set(Math.round(r.top), (lines.get(Math.round(r.top)) ?? 0) + r.width);
          const ws = [...lines.values()];
          const fs = parseFloat(getComputedStyle(el).fontSize) || 14;
          if (ws.length >= 2 && ws.at(-1) < fs * 2.2) issues.push({ kind: 'orphan', el: el.tagName.toLowerCase() + '.' + String(el.className).split(' ')[0], text: el.textContent.trim().slice(0, 40), lines: ws.length });
        }
        return issues;
      });
      report.push({ path, width, issues: found });
      const total = await page.evaluate(() => document.documentElement.scrollHeight);
      const chunks = Math.min(cfg.chunks ?? 5, Math.ceil(total / height));
      for (let i = 0; i < chunks; i++) {
        await page.evaluate((y) => window.scrollTo(0, y), i * height);
        await page.waitForTimeout(250);
        await page.screenshot({ path: `${out}/${name}-${width}-${i + 1}.png` });
      }
    } catch (e) {
      report.push({ path, width, error: String(e).slice(0, 200) });
    }
    await page.close();
  }
  await context.close();
}
await browser.close();
fs.writeFileSync(`${out}/report.json`, JSON.stringify(report, null, 1));
console.log(`${report.length} pages`);
