// 出演者のプロフィール（顔写真・年齢・体型）と、売れ筋ランキングのための部品（画面に依存しない）。
// データは get_new_releases.py が毎日取ってくる actresses.json / ranking.json（FANZA公式のAPIの値）。
// ブラウザ側の絞り込みの動きは site/public/actress-search.js。
import { FANZA_HOSTS, daysBetween, isDay, safeHttpsUrl } from './items.js';

export const ACTRESS_SEARCH_INDEX_PATH = '/data/actresses-index.json';
export const FANZA_LIST_HOSTS = ['fanza.co.jp', 'dmm.co.jp']; // 「FANZAで全作品を見る」のリンクとして通してよいホスト
export const RANKING_STALE_DAYS = 7; // 売れ筋ランキングが、これより古い日付になったら、画面には出さない（更新が止まっているときに、古い順位を出し続けない）

/** 整数で、範囲内のときだけその値（そうでなければ null） */
const intIn = (v, lo, hi) => (Number.isInteger(v) && v >= lo && v <= hi ? v : null);

/** 実在する日付（YYYY-MM-DD）か */
function isRealDay(s) {
  if (!isDay(s)) return false;
  const [y, m, d] = s.split('-').map(Number);
  const t = new Date(Date.UTC(y, m - 1, d));
  return t.getUTCFullYear() === y && t.getUTCMonth() === m - 1 && t.getUTCDate() === d;
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
 * 生年月日は年齢にだけ変えて、ここから先には持ち出さない（画面・JSONに生年月日が出ないようにするため）。
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
export function buildActressSearchIndex(profiles, items, actressByName, today) {
  const counts = countWorksByName(items);
  const rows = profiles
    .filter((p) => p.fetched)
    .map((p) => ({
      n: p.name,
      r: p.ruby,
      s: actressByName.get(p.name)?.slug ?? '',
      k: counts.get(p.name) ?? 0,
      i: p.imageSmall,
      a: p.age,
      h: p.height,
      b: p.bust,
      c: p.cup,
      wa: p.waist,
      hi: p.hip,
      l: p.listUrl,
    }));
  const have = new Set(rows.map((r) => r.n));
  const byName = profileByName(profiles);
  for (const [name, group] of actressByName) {
    if (have.has(name)) continue;
    const p = byName.get(name);
    rows.push({ n: name, r: p?.ruby ?? '', s: group.slug, k: counts.get(name) ?? group.items?.length ?? 0, i: '', a: null, h: null, b: null, c: '', wa: null, hi: null, l: '' });
  }
  rows.sort((a, b) => b.k - a.k || (a.n < b.n ? -1 : a.n > b.n ? 1 : 0));
  return { generated: today, actresses: rows };
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

/**
 * 売れ筋ランキングの表示用の形。画面に出せないとき（無い・古い・壊れている）は null。
 * 出せるときは { date, items }（items は 1〜3本。順位・品番・題名・リンク・画像・メーカー・出演者）
 */
export function rankingForDisplay(raw, today) {
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
    });
    if (items.length >= 3) break;
  }
  return items.length ? { date: raw.date, items } : null;
}
