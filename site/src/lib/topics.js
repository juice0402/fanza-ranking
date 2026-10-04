// トップの「きょうの新着人気TOP3」「きょうの話題」の部品（画面に依存しない。tests/test_topics.mjs）。
// 運営者の希望（2026-10-04 夜）「訪れるたびに新しい情報が手に入るように」「作品は毎日たくさん増えているので、その情報を知りたい人は多い」
// 「きょうの話題は、サクッと毎日の情報を仕入れられるように、見やすく。作品や女優さんの話題なら画像を使って」。
// 材料は、毎日の更新が集めたデータだけ（FANZA公式のAPIの人気順・予約の人気順・キャンペーン）。文は、データから決まった形で作る（評価の言葉は書かない）。
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
 * きょうの話題: [{ kind, label, title, text, image, face, href, external, vr, alt? }]（大事な順に、最大 limit 件）。
 *   kind: rise 急上昇 / today きょう発売 / upcoming 予約で人気 / entry 予約に初登場 / debut デビュー作 / actress 出演が多い女優 / weekly 週のまとめ / sale もうすぐ終わるセール
 *   image: 作品の表紙（パッケージ画像。表紙の部分を切り出して見せる）、face: 出演者の顔写真（あるときだけ。image より先に使う）
 *   end: セールの終わりの時刻（sale だけ。ブラウザが、すぎたら隠す /sale.js）
 *   alt: 話題の作品がVR作品のとき、「VR作品を隠す」を選んだ人に代わりに出す、同じ種類のVRでない次の作品の話題（繰り上げ。運営者の希望。2026-10-05）
 * ctx: { items（このサイトの全作品）, today, popularity, todayData（normalizeToday）, sale（normalizeSale）, roundup（いちばん新しい週のまとめ）, linkOf(item) → {href, external},
 *        actressPage(name) → path | '', faceOf(name) → url | '', skip: Set（TOP3など、ほかの欄に出ている作品ID）,
 *        skipVrOff: Set（VR作品を隠したときにTOP3に出る作品ID。繰り上げの作品には使わない） }
 */
export function buildTopics(ctx, limit = TOPICS_LIMIT) {
  const { items, today, popularity, todayData, sale, roundup = null, linkOf, actressPage = () => '', faceOf = () => '', skip = new Set(), skipVrOff = new Set() } = ctx;
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
  const ranked = newRanking(items, today, 100);

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
  pick(ranked.filter((i) => i.dateKey === today), (i) => {
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

  // デビュー作: ジャンルに「デビュー作品」がある作品の中で、新着の人気順がいちばん上の作品
  pick(ranked.filter((i) => i.genres?.includes('デビュー作品')), (i) => {
    const name = i.actress[0];
    return { ...workTopic(i, 'debut', 'デビュー作', name ? `${name}のデビュー作` : truncate(i.title, 40), `新着の人気順 ${i.popNew}位｜${mdLabel(i.dateKey)}発売`), face: name ? faceOf(name) : '' };
  });

  // 出演が多い女優: 新着の人気TOP100に、出演作が2本以上ある人（いちばん多い人）
  const counts = new Map();
  for (const i of ranked) for (const n of new Set(i.actress)) counts.set(n, (counts.get(n) ?? 0) + 1);
  const busy = [...counts.entries()].filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1] || ranked.findIndex((i) => i.actress.includes(a[0])) - ranked.findIndex((i) => i.actress.includes(b[0])))[0];
  if (busy) {
    const [name, n] = busy;
    const works = ranked.filter((i) => i.actress.includes(name));
    const shown = nonVrFirst(works); // 顔写真が無いときの表紙・リンク先は、VRでない作品を先に（VR作品を隠していても見られるように）
    const page = actressPage(name);
    topics.push({
      kind: 'actress', label: '人気の女優', title: name, text: `新着の人気TOP100に出演作が${n}本｜最高${works[0].popNew}位`,
      image: shown.image_url, face: faceOf(name), vr: false, ...(page ? { href: page, external: false } : linkOf(shown)),
    });
  }

  // 週のまとめ: 月曜に出た、前の週の新作のまとめ記事（出てから2日のあいだ）
  if (roundup && roundup.written <= today && daysBetween(today, roundup.written) <= 2) {
    const first = nonVrFirst(roundup.picks.map((p) => items.find((i) => i.cid === p.cid)).filter(Boolean));
    topics.push({
      kind: 'weekly', label: '週のまとめ', title: `${mdLabel(roundup.week_start)}〜${mdLabel(roundup.week_end)}の新作まとめ`, text: truncate(roundup.lead, 46),
      image: first ? first.image_url : '', face: '', vr: false, href: weeklyPath(roundup.week_start), external: false,
    });
  }

  // もうすぐ終わるセール: 終わりが SALE_SOON_DAYS 日以内のキャンペーン（いちばん早く終わるもの）
  const soon = saleGroups(items, sale, today, 12).find((g) => g.end.slice(0, 10) <= addDays(today, SALE_SOON_DAYS));
  if (soon) {
    topics.push({ kind: 'sale', label: 'もうすぐ終わる', title: soon.title, text: `${endLabel(soon.end)}まで｜${soon.total}本がセール中`, image: nonVrFirst(soon.items).image_url, face: '', vr: false, href: SALE_PATH, external: false, end: endIso(soon.end) });
  }

  // 多すぎるときは、まず2つ目の「急上昇」を外す（いろいろな種類の話題を残すため）
  if (topics.length > limit) {
    const second = topics.findIndex((t, i) => t.kind === 'rise' && topics.findIndex((u) => u.kind === 'rise') < i);
    if (second >= 0) topics.splice(second, 1);
  }
  return topics.slice(0, limit);
}
