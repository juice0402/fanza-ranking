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
  RANKING_SHOWN,
  CAST_LIMIT,
} from '../config.js';

// ページ側が items.js からまとめて読めるように、そのまま出し直しています
export { SITE_NAME, SITE_URL, HOME_RELEASED_LIMIT, HOME_UPCOMING_LIMIT, ARCHIVE_PAGE_SIZE, NEW_BADGE_DAYS, ENTITY_MIN_ITEMS, RANKING_SHOWN, CAST_LIMIT };

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

/** "YYYY-MM-DD" から n 日あと（n が負なら前）の "YYYY-MM-DD"（日付だけで計算するので、時差の影響を受けない） */
export function addDays(dateKey, n) {
  return new Date(Date.UTC(+dateKey.slice(0, 4), +dateKey.slice(5, 7) - 1, +dateKey.slice(8, 10)) + n * 86400000).toISOString().slice(0, 10);
}

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

/**
 * VR作品か。次のどれかなら VR（どれか1つでも載っていれば足りる。予約の作品はジャンルがまだ空のことがあるので、タイトルも見る）
 *  ・タイトルの【VR】【8K】のような括弧書きに VR がある
 *  ・形式タグ（formats）に VR を含むもの（VR・8KVR など）がある
 *  ・ジャンルに「VR専用」「ハイクオリティVR」「8KVR」のような VR を含むものがある
 */
export function isVrWork({ title = '', formats = [], genres = [] } = {}) {
  return (
    /【[^】]*VR[^】]*】/i.test(String(title)) ||
    formats.some((f) => /VR/i.test(f)) ||
    genres.some((g) => /VR/i.test(g))
  );
}

/**
 * 単体作品（出演者が1人の作品）か。FANZAのジャンル「単体作品」があれば単体。ジャンルがまだ載っていない作品（予約など）は、出演者が1人なら単体とみなす
 * （「単体作品のみ表示」スイッチの目印。運営者の希望。2026-10-05）
 */
export function isSoloWork({ genres = [], actress = [] } = {}) {
  return genres.length > 0 ? genres.includes('単体作品') : actress.length === 1;
}

/**
 * 小さなサムネ（話題・セールの特集・今週のデビュー作・運命の作品・検索結果など）用の、軽い画像のURL。
 * FANZA のパッケージ画像（…pl.jpg。800×538、表紙と背表紙と裏）を、表紙だけの小さな画像（…ps.jpg。147×200）に置きかえる
 * （ファイルが数分の1になり、読み込みが軽くなる。運営者の「読み込みのストレスをフリーに」。2026-10-05）。形が違うURLはそのまま
 */
export const smallImage = (url) => (/^https:\/\/pics\.dmm\.co\.jp\/.+pl\.jpg$/.test(String(url ?? '')) ? String(url).replace(/pl\.jpg$/, 'ps.jpg') : String(url ?? ''));
/** 小さな画像が読めなかったら、もとのパッケージ画像に戻す（それも読めなければ隠す）。img の onerror に入れる */
export const SMALL_IMG_ONERROR = "if(/ps\\.jpg$/.test(this.src)){this.src=this.src.replace(/ps\\.jpg$/,'pl.jpg');this.classList.remove('is-small')}else{this.style.visibility='hidden'}";

/**
 * 一覧の1マス（li）に付ける目印。VR作品に data-vr、単体作品に data-solo が付く（「VR作品を隠す」「単体作品のみ表示」スイッチが、これを目印に隠す。site/public/vr-filter.js）。
 * vr: false のときは data-vr を付けない（VR作品のページ。そこで全部が消えて空になるのを防ぐ）
 */
export const filterAttrs = (item, { vr = true } = {}) => ({ ...(vr && item.vr ? { 'data-vr': 'true' } : {}), ...(item.solo ? { 'data-solo': 'true' } : {}) });

/** 一覧に出す出演者（先頭から max 人）と、出しきれない人数。オムニバスなど出演者が多い作品で、カードが長くならないように（運営者の希望。2026-10-05） */
export function castParts(actress, max = CAST_LIMIT) {
  const list = Array.isArray(actress) ? actress : [];
  const names = list.slice(0, Math.max(0, max));
  return { names, more: list.length - names.length };
}

/** 一覧の出演者の1行（「花子、月子、星子 ほか31名」）。出演者がいなければ empty */
export function castLine(actress, max = CAST_LIMIT, empty = '出演者の記載なし') {
  const { names, more } = castParts(actress, max);
  if (names.length === 0) return empty;
  return names.join('、') + (more > 0 ? ` ほか${more}名` : '');
}

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
    const genres = Array.isArray(r.genres) ? r.genres.filter(Boolean) : [];
    // 形式（VR・8K など）。英数字だけのタグに絞る（日本語のタグは作品の内容を表す言葉が混ざるため使わない）
    const formats = Array.isArray(r.tags) ? r.tags.filter((t) => typeof t === 'string' && /^[0-9A-Za-z]{1,6}$/.test(t)) : [];
    const actress = Array.isArray(r.actress) ? r.actress.filter(Boolean) : [];
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
      actress,
      genres,
      duration_min: Number.isFinite(+r.duration_min) && +r.duration_min > 0 ? +r.duration_min : null,
      // サンプル動画のページURL（FANZAの476x306の再生ページ）。無い・怪しいURLなら ''（その作品は表紙画像のまま）
      sample_movie: safeHttpsUrl(r.sample_movie, FANZA_HOSTS),
      formats,
      vr: isVrWork({ title, formats, genres }),
      solo: isSoloWork({ genres, actress }),
      comment: String(r.comment ?? ''),
      // 文章のコメントか（ai＝Gemini の下書き、claude＝Claude が仕上げたもの）。定型文（template）なら false
      isAi: r.comment_kind === 'ai' || r.comment_kind === 'claude',
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

/**
 * 作品ページのタイトル（検索結果に出る部分）。品番（facts.js の productCode）が分かるときは、先頭に付ける
 * （品番で探す人が多いため。タイトルは長いので、品番・出演者を先に見せて、題名は途中で切る）
 */
export function itemPageTitle(item, code = '') {
  const shown = truncate(item.title, code ? 38 : 44);
  // タイトルに名前が入っている出演者は、かっこの中にくり返さない（同じ言葉の重ねすぎを避ける）
  const cast = item.actress.filter((name) => !shown.includes(name)).slice(0, 2).join('・');
  return `${code ? `${code} ` : ''}${shown}${cast ? `（${cast}）` : ''}｜${SITE_NAME}`;
}

/** 作品ページの説明文（コメント＋メーカー・発売日・品番） */
export function itemPageDescription(item, code = '') {
  const base = `${item.maker}の${formatDateJp(item.dateKey)}発売作品${code ? `（品番 ${code}）` : ''}。`;
  // メーカー・発売日・品番は、必ず最後まで残す（コメントが長いと、後ろに付けた品番が切れてしまうため。コメントのほうを縮める）
  const room = 120 - Array.from(base).length - 1;
  const comment = String(item.comment ?? '').trim();
  return comment && room >= 20 ? `${truncate(comment, room)} ${base}` : truncate(base, 120);
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
export function rankedNames(names, limit) {
  const counts = new Map();
  for (const n of names) counts.set(n, (counts.get(n) ?? 0) + 1);
  const ranked = [...counts.keys()].sort((a, b) => counts.get(b) - counts.get(a));
  return { names: ranked.slice(0, limit), more: ranked.length > limit };
}

/** 重複なし・出てきた順の形式（VR・8K など） */
export function formatsOf(items) {
  return [...new Set(items.flatMap((i) => i.formats))];
}

export function dateRangeJp(items) {
  const days = items.map((i) => i.dateKey).sort();
  const [first, last] = [days[0], days[days.length - 1]];
  return first === last ? `${formatDateJp(first)}` : `${formatDateJp(first)}から${formatDateJp(last)}`;
}

/** 紹介文の書き出し。過去作品（catalog）を含むときは、新作・予約だけではないことが分かる言い方にする */
const listedAs = (items) => (items.some((i) => i.catalog) ? 'FANZAの新作・予約と過去の作品として掲載している' : 'FANZAの新作・予約として掲載している');

/** 出演者ページの紹介文。作品データ（件数・発売日・メーカー・形式）だけから作るので、事実と食い違わない */
export function actressSummary(group) {
  const { name, items } = group;
  const makers = rankedNames(items.map((i) => i.maker).filter((m) => m !== '不明'), 3);
  const formats = formatsOf(items);
  const parts = [
    `${listedAs(items)}${name}さん出演の作品は${items.length}本です。`,
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
    `${listedAs(items)}${name}の作品は${items.length}本です。`,
    `発売日は${dateRangeJp(items)}です。`,
  ];
  if (cast.names.length) parts.push(`出演は${cast.names.join('、')}${cast.more ? 'ほか' : ''}です。`);
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
