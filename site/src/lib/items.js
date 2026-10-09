// サイト全体で使う「データの整形・日付・URL」の部品です。
// （JSONを読み込む処理は data.js に分けてあります）

// 設定値（サイト名・URL・表示件数）は ../config.js にまとめてあります。
import {
  SITE_NAME,
  SITE_URL,
  HOME_RELEASED_LIMIT,
  HOME_UPCOMING_LIMIT,
  HOME_UPCOMING_SHOWN,
  ARCHIVE_PAGE_SIZE,
  NEW_BADGE_DAYS,
  ENTITY_MIN_ITEMS,
  RANKING_SHOWN,
  CAST_LIMIT,
} from '../config.js';

// ページ側が items.js からまとめて読めるように、そのまま出し直しています
export { SITE_NAME, SITE_URL, HOME_RELEASED_LIMIT, HOME_UPCOMING_LIMIT, HOME_UPCOMING_SHOWN, ARCHIVE_PAGE_SIZE, NEW_BADGE_DAYS, ENTITY_MIN_ITEMS, RANKING_SHOWN, CAST_LIMIT };

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
 * スマホのサムネを軽くする（運営者の希望「スマホの低速な回線だと画像が重い。サムネだけ画素数を落として最高速化。開いたときは元のまま」。2026-10-07）。
 * 画面の幅が THUMB_MEDIA（スマホの縦向き）のときだけ、<picture> の <source> で小さい版を読む。パソコン・タブレットは今までどおり
 * （components/Thumb.astro。ブラウザで作るサムネも同じ幅で切りかえる。CSS の @media も同じ幅）。
 * FANZAの画像の大きさと重さ（2026-10-07 に本物の約300本で調べた。どれも、小さい版が無い作品は無かった）:
 *   パッケージ …pl.jpg 800×538 前後・平均 約165KB ／ 表紙 …ps.jpg 147×200・約14KB ／ 表紙の小 …pt.jpg 90×122・約6KB
 * 作品ページのサンプル画像の並びは、スマホでも大きい版（…jp-N.jpg）のまま。小さい版（…-N.jpg。120×90・約5KB）は、
 * 形の違う画像に白い余白を足して 120×90 にしてある（縦長の写真は左右に、横長は上下に。2026-10-07 に本物の約2000枚で確かめた。
 * 縦長が2割ほど）ので、暗い背景の並びでは白い帯が目立つ。どの写真が縦長かは、読み込むまで分からない
 */
export const THUMB_MEDIA = '(max-width: 480px)';
const DMM_IMG = /^https:\/\/pics\.dmm\.co\.jp\//;
/** 表紙のいちばん小さい版（…pl.jpg・…ps.jpg → …pt.jpg。90×122）。形が違うURLはそのまま */
export const tinyImage = (url) => {
  const s = String(url ?? '');
  return DMM_IMG.test(s) && /p[ls]\.jpg$/.test(s) ? s.replace(/p[ls]\.jpg$/, 'pt.jpg') : s;
};
/**
 * サムネの画像のURL: src＝パソコン・タブレット（今までどおり）、small＝スマホ（src と同じなら、切りかえない）。
 * kind: 'card'＝作品カード・TOP3（スマホは表紙 ps）／'tiny'＝小さな表紙（話題・セールの特集・今週のデビュー作・小さな棚・行の一覧。ふだん ps・スマホは pt）／
 *       'genre'＝人気のジャンルの四角（スマホは pt。運営者の「ジャンル・セールの画像は特に荒くても良い」）
 */
export function thumbSources(url, kind = 'card') {
  const s = String(url ?? '');
  if (kind === 'tiny') return { src: smallImage(s), small: tinyImage(s) };
  if (kind === 'genre') return { src: s, small: tinyImage(s) };
  return { src: s, small: smallImage(s) };
}
/**
 * <picture> の中の img の onerror: スマホで小さい版が読めなかったら、<source> を外して、ふだんの画像に戻す
 * （ふだんの画像が表紙 ps なら、パッケージ pl に戻す。それも読めなければ隠す）。属性に入れるので、< > & " を使わない形で書く
 */
export const THUMB_ONERROR = "var s=this.previousElementSibling,m=s?s.tagName=='SOURCE'?matchMedia(s.media).matches:0:0;if(m){s.remove();this.classList.remove('has-small')}else if(/ps\\.jpg$/.test(this.src)){this.src=this.src.replace(/ps\\.jpg$/,'pl.jpg');this.classList.remove('is-small')}else{this.style.visibility='hidden'}";

/**
 * パッケージ画像の形の見分け（人気のジャンルの四角い表紙。運営者の指摘「パッケージの右上しか写ってない」。2026-10-07）。
 * FANZAのパッケージ画像は、ふつうは見開き（800×538 前後。左から裏表紙・背表紙・表紙）で、四角は右端の表紙の上のほうから切り出す。
 * 見開きでない形もある（2026-10-07 に本物の約800枚を調べた: 見開き 8割・VRなどの横長 800×500/600/450 が2割弱・表紙だけの縦長 563×800 など 3%）。
 * 同じ切り方だと、縦長は右上の角だけになる。読み込んだあとに縦横の比を見て、見開きの比（COVER_SPREAD_MIN〜MAX）でなければ印 is-flat を付ける
 * （CSS が画像の全体から切り出す。横長は右にそろえ、縦長は上から少し下＝顔の多い所。調べた顔の位置から決めた）。img の onload に入れる
 */
export const COVER_SPREAD_MIN = 1.35;
export const COVER_SPREAD_MAX = 1.53;
// （属性に入れるので、< > & " を使わない形で書く。大きさが分からないときは見開きとみなす）
export const COVER_SHAPE_ONLOAD = `var r=this.naturalWidth/this.naturalHeight||1.5;if(Math.min(Math.max(r,${COVER_SPREAD_MIN}),${COVER_SPREAD_MAX})!=r)this.classList.add('is-flat')`;

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
/** シリーズ・レーベルの { id, name }（get_new_releases.py の clean_entry と同じ決まり。id は1以上の整数・名前は空でない。「----」は無し）。無ければ null */
export function entryOf(id, name) {
  const num = Number(id);
  const text = String(name ?? '').trim().replace(/\s+/g, ' ').slice(0, 80);
  if (!Number.isInteger(num) || num < 1 || num === 99999 || !text || /^-+$/.test(text)) return null;
  return { id: num, name: text };
}

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
      // シリーズ・レーベル（FANZAのAPIの iteminfo。2026-10-07 から保存。無ければ null）。レーベルがメーカーと同じ名前のときも、そのまま持つ
      series: entryOf(r.series_id, r.series),
      label: entryOf(r.label_id, r.label),
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
/**
 * FANZA のクレジット（DMMアフィリエイト公式の「クレジット表示」にある、FANZA クレジットのテキスト形式。2026-10-07 に運営者が公式のページで確かめた）。
 * 規定のHTMLを改変すると API の利用を止められることがあるので、1文字も変えない（Base.astro が set:html でそのまま入れる。
 * 文節の区切りも入れない＝lib/phrase.js が <p class="foot-credit"> の中を飛ばす。tests/verify_dist.py が全ページで突き合わせる）
 */
export const DMM_CREDIT_HTML = 'Powered by <a href="https://affiliate.dmm.com/api/">FANZA Webサービス</a>';

export const ABOUT_PATH = '/about/'; // このサイトについて（運営者の希望「SEOの対策として。フッターのいちばん下に小さくリンク」。2026-10-06）
export const ABOUT_UPDATED = '2026-10-09'; // 「このサイトについて」の中身を最後に変えた日（sitemap の lastmod。中身を変えたら、この日付も変える）

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

/**
 * 発売日の幅の短い形（一覧のページの見出しの下・出演者/メーカーの「掲載作品」に使う。長い紹介文の代わり。2026-10-06）:
 * 同じ年なら「10月3日〜10月20日」（同じ日なら「10月3日」）、年をまたぐなら「2025年5月〜2026年10月」
 */
export function shortSpan(items) {
  const days = items.map((i) => i.dateKey).filter(isDay).sort();
  if (!days.length) return '';
  const [a, b] = [days[0], days[days.length - 1]];
  const md = (d) => `${+d.slice(5, 7)}月${+d.slice(8, 10)}日`;
  if (a === b) return md(a);
  if (a.slice(0, 4) === b.slice(0, 4)) return `${md(a)}〜${md(b)}`;
  return `${+a.slice(0, 4)}年${+a.slice(5, 7)}月〜${+b.slice(0, 4)}年${+b.slice(5, 7)}月`;
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

/** タイトルの【2026年10月】と「・予約」（today を渡したときだけ。予約の作品があるときだけ「予約」） */
const titleParts = (g, today) => ({
  ym: isDay(today) ? `【${+today.slice(0, 4)}年${+today.slice(5, 7)}月】` : '',
  up: isDay(today) && g.items.some((i) => i.dateKey > today) ? '・予約' : '',
});

/**
 * 出演者のページのタイトル（運営者の希望「SEOを上位に」→ ②女優のページを強く。2026-10-06）:
 * 「○○の新作・予約・出演作品一覧【2026年10月】（42本）」。予約の作品があるときだけ「予約」、today を渡せば年月（毎日のビルドの日）を入れる
 */
export const actressPageTitle = (g, today = '') => {
  const { ym, up } = titleParts(g, today);
  return `${truncate(g.name, 30)}の新作${up}・出演作品一覧${ym}（${g.items.length}本）｜${SITE_NAME}`;
};

/** メーカーのページのタイトル（女優のページと同じ形。2026-10-06）: 「○○の新作・予約・作品一覧【2026年10月】（120本）」 */
export const makerPageTitle = (g, today = '') => {
  const { ym, up } = titleParts(g, today);
  return `${truncate(g.name, 30)}の新作${up}・作品一覧${ym}（${g.items.length}本）｜${SITE_NAME}`;
};

/**
 * 出演者・メーカーのページの説明文: 「次の新作は10月17日発売。いまセール中の作品が3本（最大50%OFF）。」＋紹介文（120文字まで。作品タイトルは入れない）。
 * next: 次に発売される作品（無ければ null）、saleCount・maxOff: セール中の作品の本数と、いちばん大きい割引
 */
export function entityDescription(summary, { next = null, saleCount = 0, maxOff = null } = {}) {
  const head = [
    next ? `次の新作は${+next.dateKey.slice(5, 7)}月${+next.dateKey.slice(8, 10)}日発売。` : '',
    saleCount > 0 ? `いまセール中の作品が${saleCount}本${maxOff ? `（最大${maxOff}%OFF）` : ''}。` : '',
  ].join('');
  return truncate(head + summary, 120);
}
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
