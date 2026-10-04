// 出演者のプロフィール（顔写真・年齢・体型）と、売れ筋ランキングのための部品（画面に依存しない）。
// データは get_new_releases.py が毎日取ってくる actresses.json / ranking.json（FANZA公式のAPIの値）。
// ブラウザ側の絞り込みの動きは site/public/actress-search.js。
import { FANZA_HOSTS, daysBetween, isDay, isVrWork, safeHttpsUrl } from './items.js';

export const ACTRESS_SEARCH_INDEX_PATH = '/data/actresses-index.json';

// 女優検索の、スリーサイズの幅（cm。数字を入れる代わりにタップで選ぶ。運営者の希望「何センチと言われてもサイズ感が分からない」。2026-10-05）。
// FANZA公式の名簿の分かれ方（バスト・ヒップは80〜89cm、ウエストは56〜61cmの人が多い）に合わせた区切り。
// "-79" は79cmまで、"100-" は100cm以上。site/public/actress-search.js の BUCKETS と同じ（tests/test_profiles.mjs で突き合わせている）
export const SIZE_BUCKETS = {
  bust: ['-79', '80-84', '85-89', '90-94', '95-99', '100-'],
  waist: ['-55', '56-58', '59-61', '62-64', '65-'],
  hip: ['-79', '80-84', '85-89', '90-94', '95-'],
};

/** 幅の表示（"-79" → "〜79"、"80-84" → "80〜84"、"100-" → "100〜"） */
export const sizeBucketLabel = (bucket) => String(bucket).replace('-', '〜');

/** 幅ごとの人数（索引の行から。値が無い人は数えない）→ [{ bucket, count }] */
export function sizeBucketCounts(rows, key, buckets) {
  return buckets.map((bucket) => {
    const [lo, hi] = bucket.split('-').map((v) => (v === '' ? null : Number(v)));
    const count = rows.filter((r) => typeof r[key] === 'number' && (lo === null || r[key] >= lo) && (hi === null || r[key] <= hi)).length;
    return { bucket, count };
  });
}

/** いちばん人数の多い幅（同じなら先の幅。だれも数字が無ければ ''） */
export function commonSizeBucket(rows, key, buckets) {
  const counts = sizeBucketCounts(rows, key, buckets);
  const top = counts.reduce((best, c) => (c.count > best.count ? c : best), { bucket: '', count: 0 });
  return top.bucket;
}
export const FANZA_LIST_HOSTS = ['fanza.co.jp', 'dmm.co.jp']; // 「FANZAで全作品を見る」のリンクとして通してよいホスト
export const RANKING_MAX = 6; // 売れ筋ランキングの、取っておく本数の上限（画面に出すのは先頭の RANKING_SHOWN 本。VR作品を隠すとき、次の順位から差し替えるため、多めに持つ）
export const RANKING_STALE_DAYS = 7;
/** 女優の顔写真（FANZA公式）の置き場所。索引には、ファイル名（例 hasumi_kurea）だけを入れて、ブラウザで、ここにつなげる */
export const ACTRESS_IMAGE_BASE = 'https://pics.dmm.co.jp/mono/actjpgs/thumbnail/';
const IMAGE_KEY = /^https:\/\/pics\.dmm\.co\.jp\/mono\/actjpgs\/(?:thumbnail\/)?([a-z0-9_]{1,60})\.jpg$/;
const KEY_ONLY = /^[a-z0-9_]{1,60}$/; // 売れ筋ランキングが、これより古い日付になったら、画面には出さない（更新が止まっているときに、古い順位を出し続けない）

/** 整数で、範囲内のときだけその値（そうでなければ null） */
const intIn = (v, lo, hi) => (Number.isInteger(v) && v >= lo && v <= hi ? v : null);

/** 実在する日付（YYYY-MM-DD）か */
function isRealDay(s) {
  if (!isDay(s)) return false;
  const [y, m, d] = s.split('-').map(Number);
  const t = new Date(Date.UTC(y, m - 1, d));
  return t.getUTCFullYear() === y && t.getUTCMonth() === m - 1 && t.getUTCDate() === d;
}

/** FANZAの顔写真のURL → ファイル名（例 hasumi_kurea）。決まった形でなければ '' */
export const imageKeyOf = (url) => (IMAGE_KEY.exec(String(url ?? '')) || [])[1] || '';

/**
 * actress_directory.json（女優検索の名簿。FANZA公式の出演者検索の一覧から、毎日の更新が集める）を、画面で使う形に揃える。
 * 生年月日は、年齢と、誕生日の月日（トップの「誕生日の近い女優」用。年は持ち出さない）にだけ変える。壊れた値は空にする。ファイルが無い・形が違っても落ちない
 */
export function normalizeDirectory(raw, today) {
  const rows = Array.isArray(raw?.rows) ? raw.rows : [];
  const seen = new Set();
  const out = [];
  for (const r of rows) {
    if (!r || typeof r !== 'object') continue;
    const id = String(r.id ?? '').trim();
    const name = String(r.name ?? '').trim();
    if (!/^\d{1,12}$/.test(id) || !name || seen.has(id)) continue;
    seen.add(id);
    const cup = typeof r.cup === 'string' && /^[A-Z]$/.test(r.cup) ? r.cup : '';
    out.push({
      id,
      name,
      ruby: String(r.ruby ?? '').trim(),
      img: typeof r.img === 'string' && KEY_ONLY.test(r.img) ? r.img : '',
      bust: intIn(r.bust, 50, 160),
      cup,
      waist: intIn(r.waist, 40, 130),
      hip: intIn(r.hip, 50, 160),
      height: intIn(r.height, 120, 210),
      age: ageFromBirthday(r.birthday, today),
      birthMD: birthMonthDay(r.birthday, today),
    });
  }
  return out;
}

/**
 * 生年月日 → 誕生日の月日（"MM-DD"）。トップの「誕生日の近い女優」だけに使う（運営者の希望。2026-10-05。年は出さない）。
 * 年齢が出せない（18〜80歳の範囲外・日付でない）ものは ''（あり得ない値は表示しない）
 */
export function birthMonthDay(birthday, today) {
  return ageFromBirthday(birthday, today) === null ? '' : birthday.slice(5, 10);
}

/** 「FANZAで全作品を見る」のURLの形（{ID} のところに女優の id が入る）を、保存済みのプロフィールのURLから作る。作れなければ '' */
export function listTemplateOf(profiles) {
  for (const p of profiles) {
    if (!p.listUrl || !p.id) continue;
    const parts = p.listUrl.split(p.id);
    if (parts.length === 2 && safeHttpsUrl(p.listUrl, FANZA_LIST_HOSTS)) return parts.join('{ID}');
  }
  return '';
}

/** 生年月日 → 今日の年齢。18〜80歳の範囲外・日付でないものは null（あり得ない値は表示しない） */
export function ageFromBirthday(birthday, today) {
  if (!isRealDay(birthday) || !isRealDay(today)) return null;
  const [y, m, d] = birthday.split('-').map(Number);
  const [ty, tm, td] = today.split('-').map(Number);
  const age = ty - y - (tm < m || (tm === m && td < d) ? 1 : 0);
  return age >= 18 && age <= 80 ? age : null;
}

/**
 * actresses.json の中身を、画面で使う形に揃える（壊れた値は空にする。ファイルが無い・形が違っても落ちない）。
 * 生年月日は、年齢と、誕生日の月日（トップの「誕生日の近い女優」用）にだけ変えて、年は持ち出さない（画面・JSONに生年月日が出ないようにするため）。
 */
export function normalizeProfiles(raw, today) {
  const rows = Array.isArray(raw?.actresses) ? raw.actresses : [];
  // 同じ名前の人が別々の id で2人以上いるとき（作品には名前しか載らないので、どちらの人か決められない）は、どちらも使わない
  // （推測で選ぶと、別の人の顔・年齢・体型を出してしまうため）。同じ id が重なっているだけなら、先のものを使う
  const idsByName = new Map();
  for (const r of rows) {
    if (!r || typeof r !== 'object') continue;
    const id = String(r.id ?? '').trim();
    const name = String(r.name ?? '').trim();
    if (!/^\d{1,12}$/.test(id) || !name) continue;
    if (!idsByName.has(name)) idsByName.set(name, new Set());
    idsByName.get(name).add(id);
  }
  const seen = new Set();
  const profiles = [];
  for (const r of rows) {
    if (!r || typeof r !== 'object') continue;
    const id = String(r.id ?? '').trim();
    const name = String(r.name ?? '').trim();
    if (!/^\d{1,12}$/.test(id) || !name || seen.has(id) || idsByName.get(name).size > 1) continue;
    seen.add(id);
    const cup = typeof r.cup === 'string' && /^[A-Z]$/.test(r.cup) ? r.cup : '';
    profiles.push({
      id,
      name,
      ruby: String(r.ruby ?? '').trim(),
      imageSmall: safeHttpsUrl(r.image_small, FANZA_HOSTS),
      imageLarge: safeHttpsUrl(r.image_large, FANZA_HOSTS),
      bust: intIn(r.bust, 50, 160),
      cup,
      waist: intIn(r.waist, 40, 130),
      hip: intIn(r.hip, 50, 160),
      height: intIn(r.height, 120, 210),
      age: ageFromBirthday(r.birthday, today),
      birthMD: birthMonthDay(r.birthday, today),
      listUrl: safeHttpsUrl(r.list_url, FANZA_LIST_HOSTS),
      fetched: isDay(r.fetched) ? r.fetched : '',
    });
  }
  return profiles;
}

/** 名前 → プロフィール */
export const profileByName = (profiles) => new Map(profiles.map((p) => [p.name, p]));

/** 顔写真のURL。大きい画像（ページの見出し用）が無ければ小さい画像、その逆も。無ければ '' */
export const faceUrl = (profile, large = false) => (profile ? (large ? profile.imageLarge || profile.imageSmall : profile.imageSmall || profile.imageLarge) : '');

/** プロフィールの項目（出演者ページの表に出すもの）。載っている項目だけを [名前, 値] で返す */
export function profileFacts(p) {
  const facts = [];
  if (!p) return facts;
  if (p.age !== null) facts.push(['年齢', `${p.age}歳`]);
  if (p.height !== null) facts.push(['身長', `${p.height}cm`]);
  if (p.bust !== null) facts.push(['バスト', `${p.bust}cm${p.cup ? `（${p.cup}カップ）` : ''}`]);
  else if (p.cup) facts.push(['カップ', `${p.cup}カップ`]);
  if (p.waist !== null) facts.push(['ウエスト', `${p.waist}cm`]);
  if (p.hip !== null) facts.push(['ヒップ', `${p.hip}cm`]);
  return facts;
}

/** 検索結果に出す短い体型の文（例: 「28歳・158cm・B86(F) W57 H87」）。載っている項目だけをつなぐ。何も無ければ '' */
export function compactSpec({ age = null, height = null, bust = null, cup = '', waist = null, hip = null } = {}) {
  const parts = [];
  if (age !== null) parts.push(`${age}歳`);
  if (height !== null) parts.push(`${height}cm`);
  const size = [];
  if (bust !== null) size.push(`B${bust}${cup ? `(${cup})` : ''}`);
  else if (cup) size.push(`${cup}カップ`);
  if (waist !== null) size.push(`W${waist}`);
  if (hip !== null) size.push(`H${hip}`);
  if (size.length) parts.push(size.join(' '));
  return parts.join('・');
}

/** 作品の出演者名ごとの本数（1本だけの人も数える） */
export function countWorksByName(items) {
  const counts = new Map();
  for (const item of items) for (const name of new Set(item.actress)) counts.set(name, (counts.get(name) ?? 0) + 1);
  return counts;
}

/**
 * 出演者検索の索引（/data/actresses-index.json）。ブラウザが読んで、年齢・身長・サイズで絞り込む。
 * 短い名前の項目: n 名前 / r 読み / s 出演者ページの短い名前（ページが無い人は ''）/ k 掲載作品の本数 / i 顔写真 /
 *   a 年齢 / h 身長 / b バスト / c カップ / wa ウエスト / hi ヒップ / l FANZAの全作品リンク。載っていない項目は null（カップは ''）。
 * 生年月日は入れない。作品の多い順。
 * 入れる人: プロフィールを取得済み（fetched がある）の人 ＋ 専用ページがある人。
 *   専用ページがある人は、プロフィールを取れていなくても入れる（検索の部品が出ると、最初から載っている一覧は隠れるため。
 *   入れないと、新しく2本以上になった出演者が一覧から消える）。その場合、数字は null。
 */
export function buildActressSearchIndex(profiles, items, actressByName, today, directory = []) {
  // 女優検索の索引（/data/actresses-index.json）。
  //   名簿（directory: FANZA公式の出演者検索で、体型・身長・生年月日が載っている人。約1万人）＋ 取得済みのプロフィール（このサイトの作品の出演者）
  //   ＋ 専用ページのある出演者（プロフィールが無くても、名前・作品数で探せるように）。
  // 1人の行: { n 名前, r 読み, id FANZAの女優の番号, s 専用ページの短い名前, k このサイトの作品数, i 顔写真のファイル名（または URL）,
  //            a 年齢, h 身長, b バスト, c カップ, wa ウエスト, hi ヒップ, l 全作品のURL（決まった形と違うときだけ） }。値が無い項目は入れない（索引を小さくするため）
  // 生年月日は入れない（年齢だけ）。同じ名前の別人（id が違う）は、それぞれ別の行（専用ページは、作品の出演者と同じ人の行にだけ付ける）
  const counts = countWorksByName(items);
  const template = listTemplateOf(profiles);
  const byId = new Map();
  const put = (id, fields) => {
    const row = byId.get(id) ?? { id };
    for (const [k, v] of Object.entries(fields)) if (v !== null && v !== '' && v !== undefined) row[k] = v;
    byId.set(id, row);
  };
  for (const d of directory) {
    put(d.id, { n: d.name, r: d.ruby, i: d.img, a: d.age, h: d.height, b: d.bust, c: d.cup, wa: d.waist, hi: d.hip });
  }
  const byName = profileByName(profiles);
  for (const p of profiles.filter((x) => x.fetched)) {
    const img = imageKeyOf(p.imageSmall) || imageKeyOf(p.imageLarge) || p.imageSmall || p.imageLarge;
    put(p.id, { n: p.name, r: p.ruby, i: img, a: p.age, h: p.height, b: p.bust, c: p.cup, wa: p.waist, hi: p.hip });
    if (p.listUrl && p.listUrl !== template.replace('{ID}', p.id)) byId.get(p.id).l = p.listUrl;
  }
  const rows = [...byId.values()];
  // このサイトの作品数・専用ページは、名前で付ける（作品には名前しか載らない）。同じ名前の別人がいるときは、プロフィールの id の人にだけ付ける
  for (const row of rows) {
    const p = byName.get(row.n);
    if (p && p.id !== row.id) continue;
    if (!p && rows.some((o) => o !== row && o.n === row.n)) continue; // 同じ名前が2人以上いて、どちらか分からない
    const k = counts.get(row.n);
    if (k) row.k = k;
    const slug = actressByName.get(row.n)?.slug;
    if (slug) row.s = slug;
  }
  const haveName = new Set(rows.filter((r) => r.s).map((r) => r.n));
  for (const [name, group] of actressByName) {
    if (haveName.has(name)) continue;
    const p = byName.get(name);
    const row = { n: name, s: group.slug, k: counts.get(name) ?? group.items?.length ?? 0 };
    if (p?.ruby) row.r = p.ruby;
    rows.push(row);
  }
  rows.sort((a, b) => (b.k ?? 0) - (a.k ?? 0) || (a.n < b.n ? -1 : a.n > b.n ? 1 : 0) || String(a.id ?? '').localeCompare(String(b.id ?? '')));
  return { generated: today, img: ACTRESS_IMAGE_BASE, list: template, actresses: rows };
}

/** 出演者の一覧に「どれくらいの人のデータがあるか」を出すための数（データが無い人が多いことを、正直に伝える） */
export function profileCoverage(profiles) {
  const got = profiles.filter((p) => p.fetched);
  return {
    total: got.length,
    withFace: got.filter((p) => p.imageSmall || p.imageLarge).length,
    withAge: got.filter((p) => p.age !== null).length,
    withHeight: got.filter((p) => p.height !== null).length,
    withSize: got.filter((p) => p.bust !== null && p.waist !== null && p.hip !== null).length,
  };
}

/** 女優検索の索引で、探せる人数（全体・年齢・身長・スリーサイズ・カップが分かる人数） */
export function indexCoverage(index) {
  const rows = Array.isArray(index?.actresses) ? index.actresses : [];
  return {
    total: rows.length,
    withAge: rows.filter((r) => typeof r.a === 'number').length,
    withHeight: rows.filter((r) => typeof r.h === 'number').length,
    withSize: rows.filter((r) => typeof r.b === 'number' && typeof r.wa === 'number' && typeof r.hi === 'number').length,
    withCup: rows.filter((r) => r.c).length,
  };
}

/**
 * 売れ筋ランキングの表示用の形。画面に出せないとき（無い・古い・壊れている）は null。
 * 出せるときは { date, items }（items は 1〜RANKING_MAX 本。順位・品番・題名・リンク・画像・メーカー・出演者・VRか）
 * VRか（vr）: データの vr（取得のときにジャンルなどから判定したもの）が true、または、題名の【VR】、
 *   または、当サイトに同じ品番の作品があって、そのジャンルなどからVRと分かるもの（vrCids: そうした品番の集まり（Set））
 */
export function rankingForDisplay(raw, today, vrCids = new Set()) {
  if (!raw || typeof raw !== 'object' || !isRealDay(raw.date) || !Array.isArray(raw.items)) return null;
  if (daysBetween(today, raw.date) > RANKING_STALE_DAYS) return null;
  const items = [];
  for (const r of raw.items) {
    if (!r || typeof r !== 'object') continue;
    const cid = String(r.cid ?? '').trim();
    const title = String(r.title ?? '').trim();
    const url = safeHttpsUrl(r.url, FANZA_LIST_HOSTS);
    if (!/^[A-Za-z0-9_-]+$/.test(cid) || !title || !url) continue;
    items.push({
      rank: items.length + 1, // 抜けがあっても、表示する順位は 1,2,3… とそろえる
      cid,
      title,
      url,
      image_url: safeHttpsUrl(r.image_url, FANZA_HOSTS),
      date: isDay(String(r.date ?? '').slice(0, 10)) ? String(r.date).slice(0, 10) : '',
      maker: String(r.maker ?? ''),
      actress: Array.isArray(r.actress) ? r.actress.filter((a) => typeof a === 'string' && a).slice(0, 6) : [],
      vr: r.vr === true || isVrWork({ title }) || vrCids.has(cid),
    });
    if (items.length >= RANKING_MAX) break;
  }
  return items.length ? { date: raw.date, items } : null;
}
