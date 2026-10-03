// サイト全体で使う「データの整形・日付・URL」の部品です。
// （JSONを読み込む処理は data.js に分けてあります）

// 設定値（サイト名・URL・表示件数）は ../config.js にまとめてあります。
import {
  SITE_NAME,
  SITE_URL,
  HOME_RELEASED_LIMIT,
  HOME_UPCOMING_LIMIT,
  ARCHIVE_PAGE_SIZE,
  NEW_BADGE_DAYS,
  ENTITY_MIN_ITEMS,
} from '../config.js';

// ページ側が items.js からまとめて読めるように、そのまま出し直しています
export { SITE_NAME, SITE_URL, HOME_RELEASED_LIMIT, HOME_UPCOMING_LIMIT, ARCHIVE_PAGE_SIZE, NEW_BADGE_DAYS, ENTITY_MIN_ITEMS };

import { createHash } from 'node:crypto';

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

/** 長い文字列を max 文字までに切る。絵文字や旧字体の「𠮷」のような2つ分の文字（サロゲートペア）の途中では切らない */
export function truncate(text, max) {
  const chars = Array.from(String(text ?? ''));
  return chars.length > max ? chars.slice(0, max - 1).join('') + '…' : chars.join('');
}

/** "YYYY-MM-DD" の形か */
export const isDay = (s) => typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s);

export const itemPath = (cid) => `/item/${cid}/`;
export const archivePath = (n) => `/archive/${n}/`;

/**
 * https のURLだけを通す（http は https に直す）。ホストが hostSuffixes のどれかでなければ ''。
 * 取得スクリプト（get_new_releases.py の safe_https_url）と同じ決まり。データに変なURLが紛れても、画面に出さないための二重の備え
 */
export function safeHttpsUrl(url, hostSuffixes) {
  if (typeof url !== 'string') return '';
  let text = url.trim();
  if (text.startsWith('http://')) text = 'https://' + text.slice('http://'.length);
  let parsed;
  try { parsed = new URL(text); } catch { return ''; }
  const host = parsed.hostname.toLowerCase();
  if (parsed.protocol !== 'https:' || !hostSuffixes.some((h) => host === h || host.endsWith('.' + h))) return '';
  return text;
}

/** サンプル動画・画像（顔写真・パッケージ・サンプル画像）として使ってよいホスト（DMM） */
export const FANZA_HOSTS = ['dmm.co.jp'];
/** 作品・出演者のリンク（アフィリエイトのURL）として使ってよいホスト（FANZA / DMM） */
export const FANZA_LINK_HOSTS = ['fanza.co.jp', 'dmm.co.jp'];

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
      // URLは、FANZA(DMM)のhttpsだけ通す（javascript: や他のサイトのURLがデータに紛れても、画面に出さない）
      url: safeHttpsUrl(r.url, FANZA_LINK_HOSTS),
      image_url: safeHttpsUrl(r.image_url, FANZA_HOSTS),
      sample_images: Array.isArray(r.sample_images) ? r.sample_images.map((u) => safeHttpsUrl(u, FANZA_HOSTS)).filter(Boolean) : [],
      date,
      dateKey: date.slice(0, 10),
      maker: String(r.maker ?? '') || '不明',
      actress: Array.isArray(r.actress) ? r.actress.filter(Boolean) : [],
      genres: Array.isArray(r.genres) ? r.genres.filter(Boolean) : [],
      duration_min: Number.isFinite(+r.duration_min) && +r.duration_min > 0 ? +r.duration_min : null,
      // サンプル動画のページURL（FANZAの476x306の再生ページ）。無い・怪しいURLなら ''（その作品は表紙画像のまま）
      sample_movie: safeHttpsUrl(r.sample_movie, FANZA_HOSTS),
      // 形式（VR・8K など）。英数字だけのタグに絞る（日本語のタグは作品の内容を表す言葉が混ざるため使わない）
      formats: Array.isArray(r.tags) ? r.tags.filter((t) => typeof t === 'string' && /^[0-9A-Za-z]{1,6}$/.test(t)) : [],
      comment: String(r.comment ?? ''),
      isAi: r.comment_kind === 'ai',
      // データ（コメント）を最後に変えた日。分からなければ ''（sitemap には載せない）
      updated: isDay(r.updated) ? r.updated : '',
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
export function groupByDate(items, totals = null) {
  const groups = [];
  for (const item of items) {
    const last = groups[groups.length - 1];
    if (last && last.dateKey === item.dateKey) last.items.push(item);
    else groups.push({ dateKey: item.dateKey, items: [item] });
  }
  // total: その日の作品の全部の数。一覧が途中で切れている（トップの件数の上限・過去の作品のページ分け）とき、
  // 「その日の本数」を、見えている数ではなく全部の数で出すため。totals（countByDate の結果）を渡さなければ、見えている数
  for (const g of groups) g.total = totals?.get(g.dateKey) ?? g.items.length;
  return groups;
}

/** 発売日ごとの作品の数 Map（"YYYY-MM-DD" → 本数） */
export function countByDate(items) {
  const counts = new Map();
  for (const item of items) counts.set(item.dateKey, (counts.get(item.dateKey) ?? 0) + 1);
  return counts;
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

/**
 * 並べたページ（トップ・一覧など）が「最後に変わった日」。
 * 作品のデータを変えた日（updated）と、発売日を迎えた日（表示が「予約」から「発売中」に変わる）のうち、一番新しいもの。
 * 分からなければ ''。
 */
export function listLastmod(items, today) {
  let latest = '';
  for (const i of items) {
    for (const d of [i.updated, i.dateKey <= today ? i.dateKey : '']) {
      if (isDay(d) && d > latest) latest = d;
    }
  }
  return latest;
}

/** sitemap.xml の中身。entries は '/path/' の文字列、または { path, lastmod } （lastmod は YYYY-MM-DD の形のときだけ出す） */
export function buildSitemap(entries, siteUrl = SITE_URL) {
  const rows = entries
    .map((e) => {
      const { path, lastmod } = typeof e === 'string' ? { path: e, lastmod: '' } : e;
      const mod = isDay(lastmod) ? `<lastmod>${lastmod}</lastmod>` : '';
      return `  <url><loc>${escapeXml(siteUrl + path)}</loc>${mod}</url>`;
    })
    .join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${rows}\n</urlset>\n`;
}

/** robots.txt の中身（検索エンジン向け。sitemap の場所を教える） */
export function buildRobots(siteUrl = SITE_URL) {
  return `User-agent: *\nAllow: /\n\nSitemap: ${siteUrl}/sitemap.xml\n`;
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

// ------------------------------------------------------------------
// 出演者ページ・メーカーページ
// ------------------------------------------------------------------

/**
 * 出演者名・メーカー名から、URLに使う短い英数字の名前を作る。
 * 日本語や記号（/ や ? など）をURLに入れないため。同じ名前なら必ず同じ名前になる。
 */
export function entitySlug(name) {
  return createHash('sha1').update(String(name).normalize('NFC')).digest('hex').slice(0, 10);
}

export const actressPath = (slug) => `/actress/${slug}/`;
export const makerPath = (slug) => `/maker/${slug}/`;
export const ACTRESS_INDEX_PATH = '/actress/';
export const MAKER_INDEX_PATH = '/maker/';

const byNewest = (a, b) => b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid);

/** 名前ごとに作品をまとめる（slugOf は短い名前の作り方。テストで差し替えるために引数にしてある） */
export function groupItems(items, namesOf, pathOf, minItems, slugOf = entitySlug) {
  const groups = new Map(); // 短い名前 → { name, slug, path, items }
  for (const item of items) {
    for (const name of new Set(namesOf(item))) {
      const slug = slugOf(name);
      let g = groups.get(slug);
      if (!g) {
        g = { name, slug, path: pathOf(slug), items: [] };
        groups.set(slug, g);
      }
      if (g.name !== name) continue; // 別の名前が同じ短い名前になったとき（ほぼ起きない）は、あとの名前のページは作らない
      g.items.push(item);
    }
  }
  return [...groups.values()]
    .filter((g) => g.items.length >= minItems)
    .map((g) => ({ ...g, items: [...g.items].sort(byNewest) }))
    .sort((a, b) => b.items.length - a.items.length || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

/** 出演者ごとの作品グループ（作品が minItems 本未満の人は作らない）。作品数の多い順 */
export const groupByActress = (items, minItems = ENTITY_MIN_ITEMS) =>
  groupItems(items, (i) => i.actress, actressPath, minItems);

/** メーカーごとの作品グループ（「不明」は作らない）。作品数の多い順 */
export const groupByMaker = (items, minItems = ENTITY_MIN_ITEMS) =>
  groupItems(items, (i) => (i.maker === '不明' ? [] : [i.maker]), makerPath, minItems);

/** 名前 → グループ（作品ページなどから、ページがあるときだけリンクするため） */
export const indexByName = (groups) => new Map(groups.map((g) => [g.name, g]));

/** 多く出てきた順に、重複なしで並べる（同数なら先に出てきた順） */
function rankedNames(names, limit) {
  const counts = new Map();
  for (const n of names) counts.set(n, (counts.get(n) ?? 0) + 1);
  const ranked = [...counts.keys()].sort((a, b) => counts.get(b) - counts.get(a));
  return { names: ranked.slice(0, limit), more: ranked.length > limit };
}

/** 重複なし・出てきた順の形式（VR・8K など） */
export function formatsOf(items) {
  return [...new Set(items.flatMap((i) => i.formats))];
}

function dateRangeJp(items) {
  const days = items.map((i) => i.dateKey).sort();
  const [first, last] = [days[0], days[days.length - 1]];
  return first === last ? `${formatDateJp(first)}` : `${formatDateJp(first)}から${formatDateJp(last)}`;
}

/** 出演者ページの紹介文。作品データ（件数・発売日・メーカー・形式）だけから作るので、事実と食い違わない */
export function actressSummary(group) {
  const { name, items } = group;
  const makers = rankedNames(items.map((i) => i.maker).filter((m) => m !== '不明'), 3);
  const formats = formatsOf(items);
  const parts = [
    `FANZAの新作・予約として掲載している${name}さん出演の作品は${items.length}本です。`,
    `発売日は${dateRangeJp(items)}です。`,
  ];
  if (makers.names.length) parts.push(`メーカーは${makers.names.join('、')}${makers.more ? 'ほか' : ''}です。`);
  if (formats.length) parts.push(`${formats.join('・')}の作品を含みます。`);
  return parts.join('');
}

/** メーカーページの紹介文 */
export function makerSummary(group) {
  const { name, items } = group;
  const cast = rankedNames(items.flatMap((i) => i.actress), 4);
  const formats = formatsOf(items);
  const parts = [
    `FANZAの新作・予約として掲載している${name}の作品は${items.length}本です。`,
    `発売日は${dateRangeJp(items)}です。`,
  ];
  if (cast.names.length) parts.push(`出演は${cast.names.join('、')}${cast.more ? 'ほか' : ''}などです。`);
  if (formats.length) parts.push(`${formats.join('・')}の作品を含みます。`);
  return parts.join('');
}

export const actressPageTitle = (g) => `${truncate(g.name, 30)}の新作・出演作品一覧（${g.items.length}本）｜${SITE_NAME}`;
export const makerPageTitle = (g) => `${truncate(g.name, 30)}の新作・作品一覧（${g.items.length}本）｜${SITE_NAME}`;
export const summaryDescription = (summary) => truncate(summary, 120);

// ------------------------------------------------------------------
// 構造化データ（JSON-LD）
// ------------------------------------------------------------------

const absoluteUrl = (path, siteUrl = SITE_URL) => siteUrl + path;

/** パンくず。trail は [{ name, path }, ...]（最後が今のページ） */
export function breadcrumbLd(trail, siteUrl = SITE_URL) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map((t, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: t.name,
      item: absoluteUrl(t.path, siteUrl),
    })),
  };
}

/** サイト全体の情報（トップページ用） */
export function websiteLd(siteUrl = SITE_URL) {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: SITE_NAME,
    url: absoluteUrl('/', siteUrl),
    inLanguage: 'ja',
  };
}

/** <script type="application/ld+json"> の中身にする文字列。</script> などでページが壊れないよう記号を置き換える */
export function jsonLdScript(data) {
  return JSON.stringify(data)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}
