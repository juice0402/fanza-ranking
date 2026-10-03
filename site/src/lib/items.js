// サイト全体で使う「データの整形・日付・URL」の部品です。
// （JSONを読み込む処理は data.js に分けてあります）

export const SITE_NAME = 'FANZA新作情報';
export const SITE_URL = 'https://fanza-ranking.pages.dev'; // 独自ドメインにしたらここを書き換える

export const HOME_RELEASED_LIMIT = 36; // トップに並べる「発売中」の最大数
export const HOME_UPCOMING_LIMIT = 24; // トップに並べる「予約」の最大数
export const ARCHIVE_PAGE_SIZE = 30;   // 過去の作品の1ページあたりの件数
export const NEW_BADGE_DAYS = 6;       // 発売から何日間「新作」シールを付けるか

const WEEKDAYS = ['日', '月', '火', '水', '木', '金', '土'];

/** 日本時間の今日 "YYYY-MM-DD"（ビルドするサーバーの時刻設定に左右されない） */
export function jstToday(nowMs = Date.now()) {
  return new Date(nowMs + 9 * 3600 * 1000).toISOString().slice(0, 10);
}

/** "YYYY-MM-DD" 同士の日数の差（a - b） */
export function daysBetween(a, b) {
  const toDay = (s) => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / 86400000;
  return Math.round(toDay(a) - toDay(b));
}

export function dateParts(dateKey) {
  const y = +dateKey.slice(0, 4);
  const m = +dateKey.slice(5, 7);
  const d = +dateKey.slice(8, 10);
  const wd = WEEKDAYS[new Date(Date.UTC(y, m - 1, d, 12)).getUTCDay()];
  return { y, m, d, wd };
}

export function formatDateJp(dateKey) {
  const { y, m, d } = dateParts(dateKey);
  return `${y}年${m}月${d}日`;
}

export function truncate(text, max) {
  const s = String(text ?? '');
  return s.length > max ? s.slice(0, max - 1) + '…' : s;
}

export const itemPath = (cid) => `/item/${cid}/`;
export const archivePath = (n) => `/archive/${n}/`;

/** JSONの中身を、画面で使いやすい形に揃える（足りない項目があっても落ちない） */
export function normalizeItems(raw) {
  const list = Array.isArray(raw) ? raw : [];
  const seen = new Set();
  const items = [];
  for (const r of list) {
    if (!r || typeof r !== 'object') continue;
    const cid = String(r.cid ?? '').trim();
    const title = String(r.title ?? '').trim();
    const date = String(r.date ?? '').trim();
    if (!cid || !title || !/^\d{4}-\d{2}-\d{2}/.test(date) || seen.has(cid)) continue;
    seen.add(cid);
    items.push({
      cid,
      title,
      url: String(r.url ?? ''),
      image_url: String(r.image_url ?? ''),
      sample_images: Array.isArray(r.sample_images) ? r.sample_images.filter(Boolean) : [],
      date,
      dateKey: date.slice(0, 10),
      maker: String(r.maker ?? '') || '不明',
      actress: Array.isArray(r.actress) ? r.actress.filter(Boolean) : [],
      genres: Array.isArray(r.genres) ? r.genres.filter(Boolean) : [],
      duration_min: Number.isFinite(+r.duration_min) && +r.duration_min > 0 ? +r.duration_min : null,
      comment: String(r.comment ?? ''),
      isAi: r.comment_kind === 'ai',
    });
  }
  return items;
}

/** 発売済み（新しい順）と予約（近い順）に分ける */
export function splitByRelease(items, today) {
  const released = items
    .filter((i) => i.dateKey <= today)
    .sort((a, b) => b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid));
  const upcoming = items
    .filter((i) => i.dateKey > today)
    .sort((a, b) => a.dateKey.localeCompare(b.dateKey) || a.cid.localeCompare(b.cid));
  return { released, upcoming };
}

/** 並び順はそのままに、同じ発売日ごとにまとめる */
export function groupByDate(items) {
  const groups = [];
  for (const item of items) {
    const last = groups[groups.length - 1];
    if (last && last.dateKey === item.dateKey) last.items.push(item);
    else groups.push({ dateKey: item.dateKey, items: [item] });
  }
  return groups;
}

/** 'new'（発売から数日）/ 'wait'（予約）/ ''（それ以外） */
export function statusOf(item, today) {
  if (item.dateKey > today) return 'wait';
  return daysBetween(today, item.dateKey) <= NEW_BADGE_DAYS ? 'new' : '';
}

/** 同じ出演者 → 同じメーカー の順で、関連作品を選ぶ */
export function relatedItems(item, all, limit = 8) {
  const others = all.filter((o) => o.cid !== item.cid);
  const byCast = others.filter((o) => o.actress.some((a) => item.actress.includes(a)));
  const byMaker = item.maker === '不明' ? [] : others.filter((o) => o.maker === item.maker);
  const picked = [];
  for (const o of [...byCast, ...byMaker]) {
    if (!picked.some((p) => p.cid === o.cid)) picked.push(o);
    if (picked.length >= limit) break;
  }
  return picked;
}

export function archivePageCount(releasedCount) {
  return Math.max(1, Math.ceil(releasedCount / ARCHIVE_PAGE_SIZE));
}

/** ページ番号の並び。例: [1, '…', 4, 5, 6, '…', 20] */
export function pageWindow(current, last, around = 2) {
  const pages = [];
  for (let p = 1; p <= last; p++) {
    if (p === 1 || p === last || Math.abs(p - current) <= around) pages.push(p);
    else if (pages[pages.length - 1] !== '…') pages.push('…');
  }
  return pages;
}

const escapeXml = (s) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

export function buildSitemap(paths, siteUrl = SITE_URL) {
  const rows = paths.map((p) => `  <url><loc>${escapeXml(siteUrl + p)}</loc></url>`).join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${rows}\n</urlset>\n`;
}

/** 作品ページのタイトル（検索結果に出る部分） */
export function itemPageTitle(item) {
  const cast = item.actress.slice(0, 2).join('・');
  return `${truncate(item.title, 44)}${cast ? `（${cast}）` : ''}｜${SITE_NAME}`;
}

/** 作品ページの説明文 */
export function itemPageDescription(item) {
  const base = `${item.maker}の${formatDateJp(item.dateKey)}発売作品。`;
  return truncate(`${item.comment} ${base}`.trim(), 120);
}
