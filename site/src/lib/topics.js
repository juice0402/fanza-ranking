// トップの「きょうの数字」「きょうの新着人気TOP3」「きょうの話題」の部品（画面に依存しない。tests/test_topics.mjs）。
// 運営者の希望（2026-10-04 夜）「訪れるたびに新しい情報が手に入るように」「作品は毎日たくさん増えているので、その情報を知りたい人は多い」
// 「きょうの話題は、サクッと毎日の情報を仕入れられるように、見やすく。作品や女優さんの話題なら画像を使って」。
// 材料は、毎日の更新が集めたデータだけ（FANZA公式のAPIの人気順・本数・キャンペーン）。文は、データから決まった形で作る（評価の言葉は書かない）。
import { FANZA_HOSTS, FANZA_LINK_HOSTS, RANKING_SHOWN, addDays, dateParts, daysBetween, isDay, isVrWork, safeHttpsUrl, truncate } from './items.js';
import { newRanking } from './popularity.js';
import { RANKING_MAX } from './profiles.js';
import { weeklyPath } from './roundups.js';
import { SALE_PATH, endIso, endLabel, saleGroups } from './sale.js';

export const TOP_SHOWN = RANKING_SHOWN; // トップに出す本数（3本）
export const TOP_DATA = RANKING_MAX; // データに持つ本数（VR作品を隠したときの差し替え用に、多めの6本）
export const TOPICS_LIMIT = 8; // 「きょうの話題」の最大数
export const RISE_MIN = 10; // 「急上昇」: 前の日から、この順位以上あがった作品
export const RISE_WITHIN = 50; // 「急上昇」: きょうの新着の人気順が、この順位までの作品
export const SALE_SOON_DAYS = 2; // 「もうすぐ終わるセール」: 終わりがこの日数以内のキャンペーン

const mdLabel = (dateKey) => {
  const p = dateParts(dateKey);
  return `${p.m}月${p.d}日`;
};

/**
 * today.json → { date, daily: [{d, n}]（古い日から）, upcomingTotal, upcoming: [作品の形], prevUpcoming: Set }。無い・形が違うときは空。
 * 予約の人気順の作品は、一覧のカードで使えるよう、作品データ（normalizeItems）に近い形にする（rank: 予約の人気順の順位）
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

/**
 * きょうの数字: { today: きょう発売の本数, week: この7日の本数, upcoming: 予約受付中の本数, bars: [{d, n, label, today, ratio}] }。
 * データが今日のものでなければ null（古い数字を「きょう」として出さない）
 */
export function todayStats(data, today) {
  if (!data || data.date !== today || data.daily.length === 0) return null;
  const last = data.daily[data.daily.length - 1];
  if (last.d !== today) return null;
  const max = Math.max(1, ...data.daily.map((r) => r.n));
  return {
    today: last.n,
    week: data.daily.reduce((n, r) => n + r.n, 0),
    days: data.daily.length,
    upcoming: data.upcomingTotal,
    bars: data.daily.map((r) => ({ d: r.d, n: r.n, label: dateParts(r.d), today: r.d === today, ratio: r.n / max })),
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
 * きょうの話題: [{ kind, label, title, text, image, face, href, external, vr }]（大事な順に、最大 limit 件）。
 *   kind: rise 急上昇 / today きょう発売 / upcoming 予約の人気1位 / entry 予約に初登場 / debut デビュー作 / actress 出演が多い女優 / weekly 週のまとめ / sale もうすぐ終わるセール
 *   image: 作品の表紙（パッケージ画像。表紙の部分を切り出して見せる）、face: 出演者の顔写真（あるときだけ。image より先に使う）
 *   end: セールの終わりの時刻（sale だけ。ブラウザが、すぎたら隠す /sale.js）
 * ctx: { items（このサイトの全作品）, today, popularity, todayData（normalizeToday）, sale（normalizeSale）, roundup（いちばん新しい週のまとめ）, linkOf(item) → {href, external},
 *        actressPage(name) → path | '', faceOf(name) → url | '', skip: Set（トップの3本など、ほかの欄に出ている作品ID） }
 */
export function buildTopics(ctx, limit = TOPICS_LIMIT) {
  const { items, today, popularity, todayData, sale, roundup = null, linkOf, actressPage = () => '', faceOf = () => '', skip = new Set() } = ctx;
  const topics = [];
  const used = new Set(skip);
  const add = (topic, cid) => {
    if (cid) used.add(cid);
    topics.push(topic);
  };
  const workTopic = (item, kind, label, title, text) => ({ kind, label, title, text, image: item.image_url, face: '', vr: Boolean(item.vr), ...linkOf(item) });
  const ranked = newRanking(items, today, 100);

  // 急上昇: 前の日の新着の人気順から、大きく順位を上げた作品（前の日の順位が無い作品は、前の日の圏外から）。
  // きょう発売の作品は、前の日にはまだ無いので入れない（「きょう発売」の話題で出す）
  if (popularity.prevRank.size > 0) {
    const outside = Math.max(...popularity.prevRank.values()) + 1;
    const rising = ranked
      .filter((i) => i.popNew <= RISE_WITHIN && i.dateKey < today && !used.has(i.cid))
      .map((i) => ({ item: i, prev: popularity.prevRank.get(i.cid) ?? null, gain: (popularity.prevRank.get(i.cid) ?? outside) - i.popNew }))
      .filter((r) => r.gain >= RISE_MIN)
      .sort((a, b) => b.gain - a.gain || a.item.popNew - b.item.popNew)
      .slice(0, 2);
    for (const r of rising) {
      const text = `新着の人気順 ${r.prev ? `${r.prev}位` : '圏外'} → ${r.item.popNew}位`;
      add(workTopic(r.item, 'rise', '急上昇', truncate(r.item.title, 40), text), r.item.cid);
    }
  }

  // きょう発売: きょう発売の作品の中で、新着の人気順がいちばん上の作品
  const todays = ranked.filter((i) => i.dateKey === today && !used.has(i.cid));
  if (todays.length > 0) {
    const i = todays[0];
    const who = [i.actress.slice(0, 2).join('・'), i.maker !== '不明' ? i.maker : ''].filter(Boolean).join('｜');
    add(workTopic(i, 'today', 'きょう発売', truncate(i.title, 40), `${who ? `${who}｜` : ''}新着の人気順 ${i.popNew}位`), i.cid);
  }

  // 予約の人気1位
  const up = todayData.date === today ? todayData.upcoming : [];
  if (up.length > 0 && !used.has(up[0].cid)) {
    const i = up[0];
    add(workTopic(i, 'upcoming', '予約の人気1位', truncate(i.title, 40), `${mdLabel(i.dateKey)}発売${i.actress.length ? `｜${i.actress.slice(0, 2).join('・')}` : ''}`), i.cid);
  }

  // 予約に初登場: 予約の人気順の上位10本に、前の日はいなかった作品
  if (todayData.prevUpcoming.size > 0) {
    const entry = up.slice(0, 10).find((i) => !todayData.prevUpcoming.has(i.cid) && !used.has(i.cid));
    if (entry) add(workTopic(entry, 'entry', '予約に初登場', truncate(entry.title, 40), `予約の人気順 ${entry.rank}位｜${mdLabel(entry.dateKey)}発売`), entry.cid);
  }

  // デビュー作: ジャンルに「デビュー作品」がある作品の中で、新着の人気順がいちばん上の作品
  const debut = ranked.find((i) => i.genres?.includes('デビュー作品') && !used.has(i.cid));
  if (debut) {
    const name = debut.actress[0];
    add({ ...workTopic(debut, 'debut', 'デビュー作', name ? `${name}のデビュー作` : truncate(debut.title, 40), `新着の人気順 ${debut.popNew}位｜${mdLabel(debut.dateKey)}発売`), face: name ? faceOf(name) : '' }, debut.cid);
  }

  // 出演が多い女優: 新着の人気TOP100に、出演作が2本以上ある人（いちばん多い人）
  const counts = new Map();
  for (const i of ranked) for (const n of new Set(i.actress)) counts.set(n, (counts.get(n) ?? 0) + 1);
  const busy = [...counts.entries()].filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1] || ranked.findIndex((i) => i.actress.includes(a[0])) - ranked.findIndex((i) => i.actress.includes(b[0])))[0];
  if (busy) {
    const [name, n] = busy;
    const best = ranked.find((i) => i.actress.includes(name));
    const page = actressPage(name);
    add({
      kind: 'actress', label: '人気の女優', title: name, text: `新着の人気TOP100に出演作が${n}本｜最高${best.popNew}位`,
      image: best.image_url, face: faceOf(name), vr: false, ...(page ? { href: page, external: false } : linkOf(best)),
    });
  }

  // 週のまとめ: 月曜に出た、前の週の新作のまとめ記事（出てから2日のあいだ）
  if (roundup && roundup.written <= today && daysBetween(today, roundup.written) <= 2) {
    const first = roundup.picks.map((p) => items.find((i) => i.cid === p.cid)).find(Boolean);
    add({
      kind: 'weekly', label: '週のまとめ', title: `${mdLabel(roundup.week_start)}〜${mdLabel(roundup.week_end)}の新作まとめ`, text: truncate(roundup.lead, 46),
      image: first ? first.image_url : '', face: '', vr: false, href: weeklyPath(roundup.week_start), external: false,
    });
  }

  // もうすぐ終わるセール: 終わりが SALE_SOON_DAYS 日以内のキャンペーン（いちばん早く終わるもの）
  const soon = saleGroups(items, sale, today, 1).find((g) => g.end.slice(0, 10) <= addDays(today, SALE_SOON_DAYS));
  if (soon) {
    add({ kind: 'sale', label: 'もうすぐ終わる', title: soon.title, text: `${endLabel(soon.end)}まで｜${soon.total}本がセール中`, image: soon.items[0].image_url, face: '', vr: false, href: SALE_PATH, external: false, end: endIso(soon.end) });
  }

  // 多すぎるときは、まず2つ目の「急上昇」を外す（いろいろな種類の話題を残すため）
  if (topics.length > limit) {
    const second = topics.findIndex((t, i) => t.kind === 'rise' && topics.findIndex((u) => u.kind === 'rise') < i);
    if (second >= 0) topics.splice(second, 1);
  }
  return topics.slice(0, limit);
}
