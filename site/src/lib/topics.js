// トップの「きょうの新着人気TOP3」「きょうの話題」の部品（画面に依存しない。tests/test_topics.mjs）。
// 運営者の希望（2026-10-04 夜）「訪れるたびに新しい情報が手に入るように」「作品は毎日たくさん増えているので、その情報を知りたい人は多い」
// 「きょうの話題は、サクッと毎日の情報を仕入れられるように、見やすく。作品や女優さんの話題なら画像を使って」。
// 材料は、毎日の更新が集めたデータだけ（FANZA公式のAPIの人気順・予約の人気順・キャンペーン）。文は、データから決まった形で作る（評価の言葉は書かない）。
import { FANZA_HOSTS, FANZA_LINK_HOSTS, RANKING_SHOWN, addDays, dateParts, daysBetween, isDay, isVrWork, safeHttpsUrl, truncate } from './items.js';
import { bestRank, newRanking } from './popularity.js';
import { isMinorTitle } from './gacha.js';
import { eventTopics } from './events.js';
import { RANKING_MAX } from './profiles.js';
import { weeklyPath } from './roundups.js';
import { endIso, endLabel, offPercent, saleGroups, saleHref } from './sale.js';

export const TOP_SHOWN = RANKING_SHOWN; // トップに出す本数（3本）
export const TOP_DATA = RANKING_MAX; // データに持つ本数（VR作品を隠したときの差し替え用に、多めの6本）
export const TOPICS_LIMIT = 10; // 「きょうの話題」の最大数（イベント・セールで人気を足したので 8 → 10。2026-10-05）
export const RISE_MIN = 10; // 「急上昇」: 前の日から、この順位以上あがった作品
export const RISE_WITHIN = 50; // 「急上昇」: きょうの新着の人気順が、この順位までの作品
export const SALE_SOON_DAYS = 2; // 「もうすぐ終わるセール」: 終わりがこの日数以内のキャンペーン
export const SALE_NEW_MIN = 3; // 「セール開始」: このサイトの作品が、この本数以上あるキャンペーンだけ（1本だけの特集は話題にしない）
export const HOT_LIMIT = 3; // 「いま人気の女優」に出す人数
export const HOT_MAX_CAST = 4; // 「いま人気の女優」で数える作品の出演者の人数の上限（オムニバス・総集編の大人数の作品は数えない）

const mdLabel = (dateKey) => {
  const p = dateParts(dateKey);
  return `${p.m}月${p.d}日`;
};

/**
 * today.json → { date, daily: [{d, n}]（古い日から）, upcomingTotal, upcoming: [作品の形], prevUpcoming: Set }。無い・形が違うときは空。
 * 予約の人気順の作品は、一覧のカードで使えるよう、作品データ（normalizeItems）に近い形にする（rank: 予約の人気順の順位）。
 * daily・upcomingTotal（日ごとの発売本数・予約受付中の本数）は、いまは画面に出していない（「きょうの数字」は運営者の判断で外した。2026-10-05）
 */
export function normalizeToday(raw) {
  const ok = raw && typeof raw === 'object' && !Array.isArray(raw);
  const daily = (ok && Array.isArray(raw.daily) ? raw.daily : []).filter((r) => r && isDay(r.d) && Number.isInteger(r.n) && r.n >= 0).map((r) => ({ d: r.d, n: r.n }));
  const upcoming = (ok && Array.isArray(raw.upcoming) ? raw.upcoming : [])
    .filter((r) => r && typeof r.c === 'string' && r.c && typeof r.t === 'string' && r.t.trim() && isDay(r.d) && Number.isInteger(r.r) && r.r >= 1)
    .map((r) => {
      const title = r.t.trim();
      return {
        cid: r.c,
        title,
        dateKey: r.d,
        actress: Array.isArray(r.a) ? r.a.filter((n) => typeof n === 'string' && n) : [],
        maker: typeof r.m === 'string' && r.m ? r.m : '不明',
        image_url: safeHttpsUrl(r.i, FANZA_HOSTS),
        url: safeHttpsUrl(r.u, FANZA_LINK_HOSTS),
        rank: r.r,
        vr: r.v === 1 || isVrWork({ title }),
      };
    })
    .filter((i) => i.url); // リンク先（FANZA）が無い作品は出さない
  return {
    date: ok && isDay(raw.date) ? raw.date : '',
    daily,
    upcomingTotal: ok && Number.isInteger(raw.upcoming_total) && raw.upcoming_total >= 0 ? raw.upcoming_total : null,
    upcoming,
    prevUpcoming: new Set(ok && Array.isArray(raw.prev_upcoming) ? raw.prev_upcoming.filter((c) => typeof c === 'string') : []),
  };
}

/** きょうの新着人気TOP3（VR作品を隠したときの差し替え用に TOP_DATA 本）。新着の人気順が無いあいだは [] */
export const topEntries = (items, today, limit = TOP_DATA) => newRanking(items, today, limit);

/**
 * 前の日からの順位の動き: { kind: 'up' | 'down' | 'same' | 'new', n（動いた数）, text（画面に出す短い文字）, label（読み上げ用） }。
 * 前の日の順位が1本も無いとき（集め始めた日）は null。前の日の順位に無い作品は「初登場」
 */
export function rankMove(cid, now, prevRank) {
  if (!prevRank || prevRank.size === 0 || !Number.isInteger(now)) return null;
  const prev = prevRank.get(cid);
  if (!prev) return { kind: 'new', n: 0, text: '初登場', label: 'きのうは圏外' };
  if (prev === now) return { kind: 'same', n: 0, text: '→', label: 'きのうと同じ順位' };
  const n = Math.abs(prev - now);
  return prev > now
    ? { kind: 'up', n, text: `▲${n}`, label: `きのう${prev}位から${n}つ上がった` }
    : { kind: 'down', n, text: `▼${n}`, label: `きのう${prev}位から${n}つ下がった` };
}

/**
 * いま人気の女優（トップ。運営者の希望「きょうの顔」→ 名前は「いま人気の女優」。2026-10-05）:
 * この1週間に発売された作品の、新着の人気TOP100に出ている女優を、作品ごとに「101 − 順位」の点を足して並べる（人気の高い作品に多く出ている人が上）。
 * 出演者が HOT_MAX_CAST 人をこえる作品（オムニバス・総集編）は数えない（1本で何十人もの点が入ってしまうため）。
 * excludeVr: VR作品を数えない（「VR作品を隠す」のときの並び）。hasFace(name): 顔写真がある人だけにする（運営者の希望。2026-10-05。順位は変わってよい）。
 * [{ name, score, count（本数）, best（いちばん上の順位）, top（いちばん上の作品） }]
 */
export function hotActresses(items, today, { excludeVr = false, limit = HOT_LIMIT, hasFace = () => true } = {}) {
  const board = new Map();
  for (const i of newRanking(items, today, 100)) {
    if (i.popNew > 100 || (excludeVr && i.vr)) continue;
    const cast = [...new Set(i.actress)];
    if (cast.length === 0 || cast.length > HOT_MAX_CAST) continue;
    for (const name of cast) {
      const row = board.get(name) ?? { name, score: 0, count: 0, best: i.popNew, top: i };
      row.score += 101 - i.popNew;
      row.count += 1;
      board.set(name, row);
    }
  }
  return [...board.values()]
    .filter((r) => hasFace(r.name))
    .sort((a, b) => b.score - a.score || a.best - b.best || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))
    .slice(0, limit);
}

export const HOT_GENRE_LIMIT = 3; // 「人気のジャンル」に出す数
export const HOT_GENRE_SKIP = ['ベスト・総集編']; // ジャンルのページの一覧のうち、「人気のジャンル」に入れないもの（作品の内容ではなく、まとめ方のため）

/**
 * 人気のジャンル（トップ。「いま人気の女優」の真下。運営者の希望。2026-10-05）: いま人気の女優と同じ数え方（この1週間の発売で新着の人気順100位までの
 * 作品に「101−順位」の点）を、ジャンルごとに足して、上から3つ。数えるのは allowed のジャンルだけ（サイトの「ジャンルのページ」の一覧
 * config.js の TAG_PAGE_GENRES から HOT_GENRE_SKIP を除いたもの。過激・未成年を連想させる名前は入っていない）。
 * [{ name, score, count（本数）, top（いちばん点の高い作品。VRでない作品を先に） }]
 */
export function hotGenres(items, today, { allowed, limit = HOT_GENRE_LIMIT }) {
  const board = new Map();
  for (const i of newRanking(items, today, 100)) {
    if (i.popNew > 100) continue;
    for (const g of new Set(i.genres ?? [])) {
      if (!allowed.has(g)) continue;
      const row = board.get(g) ?? { name: g, score: 0, count: 0, works: [] };
      row.score += 101 - i.popNew;
      row.count += 1;
      row.works.push(i);
      board.set(g, row);
    }
  }
  return [...board.values()]
    .sort((a, b) => b.score - a.score || b.count - a.count || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))
    .slice(0, limit)
    .map(({ works, ...r }) => ({ ...r, top: works.find((w) => !w.vr) ?? works[0] }));
}

export const DEBUT_SHOWN = 3; // 「今週のデビュー作」に出す本数（データは、VR作品を隠す・単体作品のみのときの差し替え用に DEBUT_DATA 本）
export const DEBUT_DATA = 6;
export const BIRTHDAY_DAYS = 14; // 「誕生日の近い女優」: きょうから、この日数のうちに誕生日が来る人
export const BIRTHDAY_LIMIT = 3;

/** 今週のデビュー作（運営者の希望。2026-10-05）: きょうまでの7日間に発売された、ジャンル「デビュー作品」の作品。多ければ新着の人気順の上から（順位が無い作品はあと） */
export function weekDebuts(items, today, limit = DEBUT_DATA) {
  const from = addDays(today, -6);
  return items
    .filter((i) => i.dateKey >= from && i.dateKey <= today && i.genres?.includes('デビュー作品'))
    .sort((a, b) => (a.popNew ?? Infinity) - (b.popNew ?? Infinity) || b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid))
    .slice(0, limit);
}

/** "MM-DD" の誕生日が、today から何日後に来るか（きょうなら0）。2月29日生まれは、うるう年でない年は2月28日 */
export function daysUntilBirthday(md, today) {
  if (!/^\d{2}-\d{2}$/.test(String(md ?? '')) || !isDay(today)) return null;
  const year = +today.slice(0, 4);
  const at = (y) => {
    const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
    return `${y}-${md === '02-29' && !leap ? '02-28' : md}`;
  };
  const d = daysBetween(at(year), today);
  return d >= 0 ? d : daysBetween(at(year + 1), today);
}

/**
 * 誕生日の近い女優（運営者の希望。2026-10-05）: このサイトに作品がある人で、顔写真と誕生日（FANZA公式のプロフィール）が分かる人のうち、
 * きょうから BIRTHDAY_DAYS 日のうちに誕生日が来る人を、近い順に（同じ日なら、このサイトの作品が多い人から）。
 * birthOf(name) → "MM-DD" | ''、hasFace(name) → bool。[{ name, md: "MM-DD", days, works }]
 */
export function birthdaySoon(items, today, { birthOf, hasFace, days = BIRTHDAY_DAYS, limit = BIRTHDAY_LIMIT }) {
  const works = new Map();
  for (const i of items) for (const n of new Set(i.actress)) works.set(n, (works.get(n) ?? 0) + 1);
  const rows = [];
  for (const [name, count] of works) {
    const md = birthOf(name);
    if (!md || !hasFace(name)) continue;
    const until = daysUntilBirthday(md, today);
    if (until === null || until >= days) continue;
    rows.push({ name, md, days: until, works: count });
  }
  return rows.sort((a, b) => a.days - b.days || b.works - a.works || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0)).slice(0, limit);
}

/**
 * きょうの話題: [{ kind, label, title, text, image, face, href, external, vr, alt? }]（大事な順に、最大 limit 件）。
 *   kind: rise 急上昇 / today きょう発売 / upcoming 予約で人気 / entry 予約に初登場 / event イベント / salehot セールで人気 / weekly 週のまとめ /
 *         salenew セール開始 / sale もうすぐ終わるセール
 *   image: 作品の表紙（パッケージ画像。表紙の部分を切り出して見せる）、face: 出演者の顔写真（あるときだけ。image より先に使う）
 *   end: セールの終わりの時刻（salenew・sale だけ。ブラウザが、すぎたら隠す /sale.js）
 *   alt: 話題の作品がVR作品のとき、「VR作品を隠す」を選んだ人に代わりに出す、同じ種類のVRでない次の作品の話題（繰り上げ。運営者の希望。2026-10-05）
 * ctx: { items（このサイトの全作品）, today, popularity, todayData（normalizeToday）, sale（normalizeSale）, roundup（いちばん新しい週のまとめ）, linkOf(item) → {href, external},
 *        faceOf(name) → url | '', coverOf(name) → その人の作品の表紙 | ''（イベントの話題で、顔写真が無いとき）, events（normalizeEvents。無ければ null）,
 *        skip: Set（TOP3など、ほかの欄に出ている作品ID）,
 *        skipVrOff: Set（VR作品を隠したときにTOP3に出る作品ID。繰り上げの作品には使わない） }
 */
export function buildTopics(ctx, limit = TOPICS_LIMIT) {
  const { items, today, popularity, todayData, sale, roundup = null, events = null, linkOf, faceOf = () => '', coverOf = () => '', skip = new Set(), skipVrOff = new Set() } = ctx;
  const topics = [];
  const used = new Set(skip);
  const workTopic = (item, kind, label, title, text) => ({ kind, label, title, text, image: item.image_url, face: '', vr: Boolean(item.vr), ...linkOf(item) });
  // 作品の話題を1つ足す。candidates は大事な順の候補。まだ出していない先頭の作品を出し、それがVR作品なら、
  // VRでない次の候補を alt に付ける（「VR作品を隠す」を選んだ人には、こちらが出る）。どちらの作品も、ほかの話題には使わない
  // primaryOk: 話題そのもの（ふだん出す作品）に使える候補の条件（繰り上げの作品は、条件の外の候補からも探す）
  const pick = (candidates, make, primaryOk = () => true) => {
    const free = candidates.filter((i) => !used.has(i.cid));
    const at = free.findIndex(primaryOk);
    if (at < 0) return;
    const topic = make(free[at]);
    used.add(free[at].cid);
    if (topic.vr) {
      const next = free.slice(at + 1).find((i) => !i.vr && !skipVrOff.has(i.cid));
      if (next) {
        topic.alt = make(next);
        used.add(next.cid);
      }
    }
    topics.push(topic);
  };
  const nonVrFirst = (list) => list.find((i) => !i.vr) ?? list[0];
  const ranked = newRanking(items, today, 100); // 新着の人気TOP100（急上昇を探す範囲）
  const pool = newRanking(items, today, Infinity); // 新着の人気順の全部（きょう発売と、その繰り上げを探す範囲）

  // 急上昇: 前の日の新着の人気順から、大きく順位を上げた作品（前の日の順位が無い作品は、前の日の圏外から）。2件まで。
  // きょう発売の作品は、前の日にはまだ無いので入れない（「きょう発売」の話題で出す）
  if (popularity.prevRank.size > 0) {
    const outside = Math.max(...popularity.prevRank.values()) + 1;
    const gain = (i) => (popularity.prevRank.get(i.cid) ?? outside) - i.popNew;
    const rising = ranked
      .filter((i) => i.popNew <= RISE_WITHIN && i.dateKey < today && gain(i) >= RISE_MIN)
      .sort((a, b) => gain(b) - gain(a) || a.popNew - b.popNew);
    const make = (i) => {
      const prev = popularity.prevRank.get(i.cid);
      return workTopic(i, 'rise', '急上昇', truncate(i.title, 40), `新着の人気順 ${prev ? `${prev}位` : '圏外'} → ${i.popNew}位`);
    };
    pick(rising, make);
    pick(rising, make);
  }

  // きょう発売: きょう発売の作品の中で、新着の人気順がいちばん上の作品
  pick(pool.filter((i) => i.dateKey === today), (i) => {
    const who = [i.actress.slice(0, 2).join('・'), i.maker !== '不明' ? i.maker : ''].filter(Boolean).join('｜');
    return workTopic(i, 'today', 'きょう発売', truncate(i.title, 40), `${who ? `${who}｜` : ''}新着の人気順 ${i.popNew}位`);
  });

  // 予約で人気: 予約の人気順のいちばん上の作品
  const up = todayData.date === today ? todayData.upcoming : [];
  const upText = (i) => `予約の人気順 ${i.rank}位｜${mdLabel(i.dateKey)}発売${i.actress.length ? `｜${i.actress.slice(0, 2).join('・')}` : ''}`;
  pick(up, (i) => workTopic(i, 'upcoming', '予約で人気', truncate(i.title, 40), upText(i)));

  // 予約に初登場: 予約の人気順の上位10本に、前の日はいなかった作品（VR作品なら、繰り上げは上位30本の中から）
  if (todayData.prevUpcoming.size > 0) {
    const entries = up.filter((i) => !todayData.prevUpcoming.has(i.cid));
    pick(entries, (i) => workTopic(i, 'entry', '予約に初登場', truncate(i.title, 40), upText(i)), (i) => i.rank <= 10);
  }

  // イベント: 所属事務所の公式サイトに載っている、近いうちのイベント（運営者の希望「女優さんのイベント情報…新鮮な情報を」。2026-10-05。lib/events.js）。
  // 近い順に2件（同じ人は1件）。タップで、イベント情報のページの、そのイベントの行へ
  if (events) topics.push(...eventTopics(events, today, { faceOf, coverOf }));

  // セールで人気: いまセール中（値引きの分かる）の発売済みの作品の中で、人気（全体・新着の人気順の上のほう）がいちばん高い作品
  // （運営者の希望「毎日の訪問に価値を」。2026-10-05。こちらから勧める話題なので、未成年を連想させるタイトルの作品は入れない）
  const saleInfo = (i) => {
    const s = sale.byCid.get(i.cid);
    const c = s && sale.campaigns[s.k];
    return s && s.price && c && c.end.slice(0, 10) >= today ? { ...s, end: c.end } : null;
  };
  const rankOf = (i) => bestRank(i.popAll ?? null, i.popNew ?? null);
  const onSale = items
    .filter((i) => i.dateKey <= today && rankOf(i) && saleInfo(i) && !isMinorTitle(i.title))
    .sort((a, b) => rankOf(a) - rankOf(b) || b.dateKey.localeCompare(a.dateKey) || a.cid.localeCompare(b.cid));
  pick(onSale, (i) => {
    const s = saleInfo(i);
    return { ...workTopic(i, 'salehot', 'セールで人気', truncate(i.title, 40), `${offPercent(s.price, s.listPrice)}%OFF ${s.price.toLocaleString('ja-JP')}円〜｜${endLabel(s.end)}まで`), end: endIso(s.end) };
  });

  // デビュー作は、発売中の新作の中の「今週のデビュー作」の欄で出す（話題には入れない。2026-10-05）
  // 人気の女優は、トップの「いま人気の女優」の欄で出す（話題には入れない。2026-10-05）

  // 週のまとめ: 月曜に出た、前の週の新作のまとめ記事（出てから2日のあいだ）
  if (roundup && roundup.written <= today && daysBetween(today, roundup.written) <= 2) {
    const first = nonVrFirst(roundup.picks.map((p) => items.find((i) => i.cid === p.cid)).filter(Boolean));
    topics.push({
      kind: 'weekly', label: '週のまとめ', title: `${mdLabel(roundup.week_start)}〜${mdLabel(roundup.week_end)}の新作まとめ`, text: truncate(roundup.lead, 46),
      image: first ? first.image_url : '', face: '', vr: false, href: weeklyPath(roundup.week_start), external: false,
    });
  }

  // セールの話題は、セールのページの、その特集（キャンペーン）の見出しへ
  const campaigns = saleGroups(items, sale, today, 0);
  const saleTopic = (g, kind, label, text) => ({ kind, label, title: g.title, text, image: g.covers[0]?.image_url ?? '', face: '', vr: false, href: saleHref(g.k), external: false, end: endIso(g.end) });

  // セール開始: きのう・きょう始まったキャンペーン（前の日の更新のあとに始まったもの）。このサイトの作品が SALE_NEW_MIN 本以上のうち、いちばん多いもの
  const fresh = campaigns
    .filter((g) => g.begin && g.begin.slice(0, 10) >= addDays(today, -1) && g.total >= SALE_NEW_MIN)
    .sort((a, b) => b.total - a.total || a.end.localeCompare(b.end))[0];
  if (fresh) topics.push(saleTopic(fresh, 'salenew', 'セール開始', `${mdLabel(fresh.begin.slice(0, 10))}から${endLabel(fresh.end)}まで｜${fresh.total}本がセール中`));

  // もうすぐ終わるセール: 終わりが SALE_SOON_DAYS 日以内のキャンペーン（いちばん早く終わるもの。「セール開始」に出したものは除く）
  const soon = campaigns.find((g) => g !== fresh && g.end.slice(0, 10) <= addDays(today, SALE_SOON_DAYS));
  if (soon) topics.push(saleTopic(soon, 'sale', 'もうすぐ終わる', `${endLabel(soon.end)}まで｜${soon.total}本がセール中`));

  // 多すぎるときは、まず2つ目の「急上昇」を外す（いろいろな種類の話題を残すため）
  if (topics.length > limit) {
    const second = topics.findIndex((t, i) => t.kind === 'rise' && topics.findIndex((u) => u.kind === 'rise') < i);
    if (second >= 0) topics.splice(second, 1);
  }
  return topics.slice(0, limit);
}
