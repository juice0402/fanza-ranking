// 下調べ用（このブランチだけ）: 本物のブラウザ（GitHub の Chrome）でプレビューを開き、画像が読めているかを数える
import puppeteer from 'puppeteer-core';
const BASE = 'https://claude-doujin-game.fanza-ranking.pages.dev';
const out = [];
const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--lang=ja-JP'] });
for (const [w, h, mobile] of [[390, 844, true], [1280, 900, false]]) {
  for (const path of ['/doujin/', '/game/', '/', '/doujin/item/d_822811/']) {
    const page = await browser.newPage();
    await page.setViewport({ width: w, height: h, isMobile: mobile, deviceScaleFactor: 1 });
    await page.evaluateOnNewDocument(() => { try { localStorage.setItem('age-ok', '1'); } catch (e) {} });
    const failed = [];
    page.on('requestfailed', (r) => failed.push(`${r.url().slice(-50)} ${r.failure()?.errorText}`));
    page.on('response', (r) => { if (r.request().resourceType() === 'image' && r.status() >= 400) failed.push(`${r.status()} ${r.url().slice(-50)}`); });
    try {
      await page.goto(BASE + path, { waitUntil: 'networkidle2', timeout: 60000 });
      await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 120)); } });
      await new Promise((r) => setTimeout(r, 2500));
      const info = await page.evaluate(() => {
        const imgs = [...document.images];
        const ok = imgs.filter((i) => i.complete && i.naturalWidth > 0);
        const bad = imgs.filter((i) => i.complete && i.naturalWidth === 0).map((i) => i.currentSrc.slice(-45));
        const pending = imgs.filter((i) => !i.complete).length;
        const f = document.querySelector('.floor-img, .item-cover img');
        const cs = f ? getComputedStyle(f) : null;
        const box = f ? f.getBoundingClientRect() : null;
        const cover = document.querySelector('.item-cover');
        return { total: imgs.length, ok: ok.length, bad: bad.slice(0, 3), badN: bad.length, pending,
          first: f ? { cls: f.className, src: (f.currentSrc || f.src).slice(-45), nw: f.naturalWidth, vis: cs.visibility, disp: cs.display, op: cs.opacity, pos: cs.position, w: Math.round(box.width), h: Math.round(box.height) } : null,
          cover: cover ? (() => { const b = cover.getBoundingClientRect(); return { w: Math.round(b.width), h: Math.round(b.height) }; })() : null };
      });
      out.push(`${w}px ${path}: ${JSON.stringify(info)} 失敗=${JSON.stringify(failed.slice(0, 3))}`);
    } catch (e) {
      out.push(`${w}px ${path}: エラー ${String(e).slice(0, 120)}`);
    }
    await page.close();
  }
}
await browser.close();
console.log(JSON.stringify(out));
