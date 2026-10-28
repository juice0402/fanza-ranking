// 読み物（/yomimono/。運営者の「ちょっとした調べ物はAIがすぐ答えるので、読み物で情報の価値を増やしたい」。2026-10-28 #181）の部品。
// 画面に依存しない（tests/test_yomimono.mjs）。データは data/yomimono.json（Claude が scripts/claude_yomimono.py の list → 書く → apply で書く）。
// 読み物の下に、テーマの作品の棚（人気・評価・いまセール中・新作と予約。毎日のビルドで入れかわる）を自動で並べる。
// テーマに入る作品の決まり（matchesTheme）は、道具（claude_yomimono.py）と同じ: テーマのジャンルのどれかが付いている作品か、テーマの言葉のどれかを題に含む作品。
// こちらから案内する欄なので、未成年を連想させる題（isMinorTitle）と、無理やり・犯罪を思わせる題（yomimono-exclude.json の title_words）の作品は出さない。
// 外す言葉の一覧は yomimono-exclude.json だけに書く（道具も同じファイルを読む）
import exclude from './yomimono-exclude.json' with { type: 'json' };
import { isMinorTitle } from './gacha.js';
import { bestRank } from './popularity.js';
import { REVIEW_SHELF_MIN, ratedShelf } from './reviews.js';
import { SALE_PATH, offPercent, onSaleItems } from './sale.js';
import { SEARCH_PATH } from './search.js';
import { VR_TAG_NAME } from './collections.js';
import { SITE_NAME, SITE_URL, isVrWork } from './items.js';

export const YOMIMONO_PATH = '/yomimono/';
export const yomimonoPath = (slug) => `${YOMIMONO_PATH}${slug}/`;
export const YOMIMONO_SHELF_SIZE = 6; // 棚1つに並べる本数
export const YOMIMONO_PICKS_HEADING = '最初に見るならこの5本'; // 厳選の見出し（データの picks_h が無いとき）
export const YOMIMONO_TITLE_WORDS = Object.freeze((Array.isArray(exclude?.title_words) ? exclude.title_words : []).filter((w) => typeof w === 'string' && w));

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const SLUG = /^[a-z0-9][a-z0-9-]{0,59}$/;
const CID = /^[A-Za-z0-9_-]{1,40}$/;
const str = (v, max) => (typeof v === 'string' ? v.trim().slice(0, max) : '');
const strList = (v, max) => (Array.isArray(v) ? [...new Set(v.map((x) => str(x, 40)).filter(Boolean))].slice(0, max) : []);
/** "1段落目\n2段落目" → ['1段落目', '2段落目']（空の段落は捨てる） */
export const paragraphs = (text) => String(text ?? '').split('\n').map((s) => s.trim()).filter(Boolean);
/** "2026-10-28" → "10月28日" */
export const mdJp = (day) => (DAY.test(String(day ?? '')) ? `${+day.slice(5, 7)}月${+day.slice(8, 10)}日` : '');

/** 読み物の棚・厳選に出さない題か: 未成年を連想させる題（isMinorTitle）か、yomimono-exclude.json の言葉を含む題（道具の is_excluded と同じ決まり） */
export function isExcludedTitle(title) {
  const raw = String(title ?? '');
  return isMinorTitle(raw) || YOMIMONO_TITLE_WORDS.some((w) => raw.includes(w));
}

/** その作品がテーマに入るか（道具と同じ決まり）: テーマのジャンルのどれかが付いている、またはテーマの言葉のどれかを題に含む */
export function matchesTheme(work, theme) {
  const genres = Array.isArray(work?.genres) ? work.genres : [];
  const title = String(work?.title ?? '');
  return (theme?.genres ?? []).some((g) => genres.includes(g)) || (theme?.keywords ?? []).some((k) => k && title.includes(k));
}

/** VRのテーマか（VRの売り場のトップ・VR作品のページに入口の1行を出す）: theme.floor が 'vr' か、テーマのジャンルが VR のもの（VR専用など） */
export const isVrTheme = (theme) => theme?.floor === 'vr' || (theme?.genres ?? []).some((g) => isVrWork({ genres: [g] }));

/** テーマに関係するジャンルのページの名前（テーマのジャンル。VRのジャンルは「VR作品」のページ） */
export function themeTagNames(theme) {
  const names = (theme?.genres ?? []).filter((g) => !isVrWork({ genres: [g] }));
  return [...new Set([...names, ...(isVrTheme(theme) ? [VR_TAG_NAME] : [])])];
}

/**
 * yomimono.json → { updated, articles: [...] }（新しく書いた順）。形の違う読み物は捨てる（無い・壊れていても空）。
 * 読み物の形: { slug, path, theme: { genres, keywords, floor }, title, description, lead: [段落], sections: [{ h, paras: [段落], chart: 'years'|'' }],
 *   picksHeading, picks: [{ cid, why }], years: [{ y, n }]（古い順）, total, written, checked }
 */
export function normalizeYomimono(raw) {
  const ok = raw && typeof raw === 'object' && !Array.isArray(raw);
  const src = ok && raw.articles && typeof raw.articles === 'object' && !Array.isArray(raw.articles) ? raw.articles : {};
  const articles = [];
  for (const [slug, a] of Object.entries(src)) {
    if (!SLUG.test(slug) || !a || typeof a !== 'object' || Array.isArray(a)) continue;
    const theme = { genres: strList(a.theme?.genres, 20), keywords: strList(a.theme?.keywords, 20), floor: str(a.theme?.floor, 20) };
    const title = str(a.title, 80);
    const lead = paragraphs(a.lead);
    if (!title || lead.length === 0 || (theme.genres.length === 0 && theme.keywords.length === 0) || !DAY.test(String(a.written ?? '')) || !DAY.test(String(a.checked ?? ''))) continue;
    const sections = (Array.isArray(a.sections) ? a.sections : [])
      .map((s) => ({ h: str(s?.h, 80), paras: paragraphs(s?.text), chart: s?.chart === 'years' ? 'years' : '' }))
      .filter((s) => s.h && s.paras.length > 0);
    const seen = new Set();
    const picks = (Array.isArray(a.picks) ? a.picks : [])
      .map((p) => ({ cid: str(p?.cid, 40), why: str(p?.why, 200) }))
      .filter((p) => CID.test(p.cid) && p.why && !seen.has(p.cid) && seen.add(p.cid));
    const years = [...new Map((Array.isArray(a.years) ? a.years : [])
      .filter((y) => Number.isInteger(y?.y) && y.y >= 1970 && y.y <= 2100 && Number.isInteger(y?.n) && y.n >= 0)
      .map((y) => [y.y, { y: y.y, n: y.n }])).values()].sort((x, y) => x.y - y.y);
    articles.push({
      slug,
      path: yomimonoPath(slug),
      theme,
      title,
      description: str(a.description, 300),
      lead,
      sections,
      picksHeading: str(a.picks_h, 40) || YOMIMONO_PICKS_HEADING,
      picks,
      years,
      total: Number.isInteger(a.total) && a.total >= 0 ? a.total : 0,
      written: a.written,
      checked: a.checked,
    });
  }
  articles.sort((x, y) => y.written.localeCompare(x.written) || (x.slug < y.slug ? -1 : x.slug > y.slug ? 1 : 0));
  return { updated: ok && DAY.test(String(raw.updated ?? '')) ? raw.updated : '', articles };
}

/** テーマの作品（出さない題の作品は除く） */
export const themeWorks = (works, theme) => works.filter((w) => matchesTheme(w, theme) && !isExcludedTitle(w.title));

const rankOf = (i) => bestRank(i.popAll ?? null, i.popNew ?? null) ?? Infinity;
const byNewest = (a, b) => b.dateKey.localeCompare(a.dateKey) || (a.cid < b.cid ? -1 : a.cid > b.cid ? 1 : 0);

/** 作品検索へのリンク（テーマの最初のジャンルで絞り込む。ジャンルの無いテーマは、最初の言葉で探す）。sort: 'pop'・'review' など */
export function themeSearchHref(theme, sort = '') {
  const parts = [];
  if (theme?.genres?.[0]) parts.push(`tag=${encodeURIComponent(theme.genres[0])}`);
  else if (theme?.keywords?.[0]) parts.push(`q=${encodeURIComponent(theme.keywords[0])}`);
  if (sort) parts.push(`sort=${sort}`);
  return parts.length ? `${SEARCH_PATH}?${parts.join('&')}` : SEARCH_PATH;
}

/**
 * 読み物の下の棚（4つ。それぞれ size 本まで。出さない題の作品は入れない）: [{ key, title, note, items, more: { href, text } }]
 *   pop 人気の作品（FANZAの人気順の順位がある作品を、上から）／ rated 評価の高い作品（RatedShelf と同じ。レビュー3件以上・3本に満たなければ空）／
 *   sale いまセール中の作品（終わったキャンペーンの作品は入れない。人気の高い順。items の作品に sale: { k, price, listPrice, end, title }）／
 *   new 新作と予約（発売日が新しい順。予約も入る）
 * ctx: { today, sale（lib/sale.js の normalizeSale）, saleWorks（セール中の作品を探す作品。このサイトに無いセール中の作品も）, popDate, saleDate, tagPathOf（ジャンルの名前 → ページのパス。無ければ ''） }
 */
export function yomimonoShelves(works, theme, { today = '', sale = null, saleWorks = null, popDate = '', saleDate = '', tagPathOf = () => '', size = YOMIMONO_SHELF_SIZE } = {}) {
  const matched = themeWorks(works, theme);
  const pop = matched.filter((i) => rankOf(i) !== Infinity).sort((a, b) => rankOf(a) - rankOf(b) || byNewest(a, b)).slice(0, size);
  const rated = ratedShelf(matched, today, { limit: size });
  const onSale = sale ? onSaleItems(themeWorks(saleWorks ?? works, theme), sale, today) : [];
  const maxOff = Math.max(0, ...onSale.map((i) => offPercent(i.sale.price, i.sale.listPrice) ?? 0)) || null;
  const fresh = [...matched].sort(byNewest).slice(0, size);
  const tagName = themeTagNames(theme).find((n) => tagPathOf(n));
  return [
    { key: 'pop', title: '人気の作品', note: `FANZAの人気順${popDate ? `（${mdJp(popDate)}時点）` : ''}`, items: pop,
      more: { href: themeSearchHref(theme, 'pop'), text: '作品検索で、人気順にすべて見る' } },
    { key: 'rated', title: '評価の高い作品', note: `FANZAのレビュー（${REVIEW_SHELF_MIN}件以上）の評価から`, items: rated,
      more: { href: themeSearchHref(theme, 'review'), text: '作品検索で、評価が高い順にすべて見る' } },
    { key: 'sale', title: 'いまセール中の作品', note: `${onSale.length}本${maxOff ? `・最大${maxOff}%OFF` : ''}${saleDate ? `｜${mdJp(saleDate)}時点` : ''}`, items: onSale.slice(0, size),
      more: { href: SALE_PATH, text: 'ほかのセール中の作品は、セールのページで' } },
    { key: 'new', title: '新作と予約', note: '発売日が新しい順', items: fresh,
      more: tagName ? { href: tagPathOf(tagName), text: `${tagName}の新作・予約をすべて見る` } : { href: themeSearchHref(theme), text: '作品検索で、新しい順にすべて見る' } },
  ];
}

/** 厳選の作品: [{ why, item }]（見つからない作品・出さない題の作品は飛ばす）。byCid: cid → 作品 */
export const resolvePicks = (picks, byCid) => picks
  .map((p) => ({ why: p.why, item: byCid.get(p.cid) }))
  .filter((p) => p.item && !isExcludedTitle(p.item.title));

/**
 * ページを作る読み物（棚が1つでもあるものだけ）: 読み物に shelves（中身のある棚だけ）・picks（[{ why, item }]）・tags（関係するジャンルのページ [{ name, path }]）・vr を足したもの。
 * ctx: yomimonoShelves の ctx ＋ works（このサイトの全作品）
 */
export function buildYomimonoPages(articles, { works = [], ...ctx } = {}) {
  const byCid = new Map(works.map((w) => [w.cid, w]));
  const tagPathOf = ctx.tagPathOf ?? (() => '');
  return articles.flatMap((a) => {
    const shelves = yomimonoShelves(works, a.theme, ctx).filter((s) => s.items.length > 0);
    if (shelves.length === 0) return [];
    const tags = themeTagNames(a.theme).filter((n) => tagPathOf(n)).map((name) => ({ name, path: tagPathOf(name) }));
    const count = themeWorks(works, a.theme).length;
    return [{ ...a, shelves, picks: resolvePicks(a.picks, byCid), tags, vr: isVrTheme(a.theme), count }];
  });
}

/** そのジャンルのページ（名前）に関係する読み物（入口の1行） */
export const yomimonoForTag = (pages, name) => pages.filter((p) => p.tags.some((t) => t.name === name));

/** 年ごとの本数の棒: 最初の年から最後の年まで、無い年は0本で埋める（[{ year, n }]） */
export function yomimonoYearBars(years) {
  if (!Array.isArray(years) || years.length === 0) return [];
  const by = new Map(years.map((y) => [y.y, y.n]));
  const out = [];
  for (let y = years[0].y; y <= years[years.length - 1].y; y++) out.push({ year: y, n: by.get(y) ?? 0 });
  return out;
}

/** いちばん多い年（同じ本数なら新しい年。全部0本なら null） */
export const yomimonoPeak = (bars) => bars.reduce((best, b) => (b.n > 0 && (!best || b.n >= best.n) ? b : best), null);

/** 厳選の見出し: 見出しの「◯本」が、出せた本数と違えば、出せた本数に直す（見つからない作品を飛ばしたとき） */
export const picksHeadingFor = (heading, n) => String(heading || YOMIMONO_PICKS_HEADING).replace(/[0-9０-９]+本/, (m) => (Number(m.normalize('NFKC').slice(0, -1)) === n ? m : `${n}本`));

/** 記事の構造化データ（Article。公開日＝書いた日・更新日＝数えた日。書き手・発行はこのサイト。週のまとめと同じ） */
export function yomimonoArticleLd(a, siteUrl = SITE_URL) {
  const url = siteUrl + a.path;
  const publisher = { '@type': 'Organization', name: SITE_NAME, url: siteUrl + '/' };
  return {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: a.title,
    ...(a.description ? { description: a.description } : {}),
    datePublished: a.written,
    dateModified: a.checked > a.written ? a.checked : a.written,
    inLanguage: 'ja',
    mainEntityOfPage: { '@type': 'WebPage', '@id': url },
    author: publisher,
    publisher,
  };
}

/** 厳選の作品の構造化データ（ItemList。このサイトに作品ページがある作品だけ。1本も無ければ null）。pathOf: 作品 → 作品ページのパス（無ければ ''） */
export function yomimonoPicksLd(picks, pathOf, siteUrl = SITE_URL) {
  const rows = picks.map((p) => ({ path: pathOf(p.item), name: String(p.item.title ?? '').slice(0, 100) })).filter((r) => r.path);
  if (rows.length === 0) return null;
  return {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    numberOfItems: rows.length,
    itemListElement: rows.map((r, n) => ({ '@type': 'ListItem', position: n + 1, url: siteUrl + r.path, name: r.name })),
  };
}

/** 一覧のページ（/yomimono/）の説明文（60〜120文字） */
export function yomimonoIndexDescription(pages) {
  if (pages.length === 0) return 'FANZA動画のジャンルやテーマを、このサイトが毎日集めている人気の順位・レビュー・セールの数字から読む記事の一覧です。記事は書きあがりしだい公開します。';
  return `FANZA動画のジャンルやテーマを、毎日集めている人気の順位・レビュー・セールの数字から読む記事${pages.length}本の一覧です。記事の下には、テーマの作品を人気・評価・セール・新作の順に並べています。`;
}
