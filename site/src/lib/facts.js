// 作品ページの「品番」と「この作品のデータ」欄の部品（画面に依存しない。テスト: tests/test_seo.mjs）。
// どちらも、保存してある作品データだけから、ビルドのたびに数えて作る（AIは使わない）。文章の数字は、いつも一覧と同じになる。
import { formatDateJp } from './items.js';

/**
 * 作品ID（cid）から、メーカーの品番の形（例: dldss00566 → "DLDSS-566"）を作る。作れない（形が違う）ときは ''。
 * FANZAの作品IDは、先頭にFANZA独自の数字（1・15・h_1234 など）、そのあとにメーカーの記号（英字）、5桁の番号が付く形が多い。
 * 確実に読めるものだけを品番にする: 最後に英字が付くもの（…a・…ai）、英字が1文字のもの、番号が3〜5桁でないものは、作らない（間違った品番を出さないため）。
 * 番号は、先頭の0を除いて3桁にそろえる（00072 → 072、01942 → 1942）
 */
export function productCode(cid) {
  const m = /^(?:h_\d+|\d{1,3})?([a-z]{2,10})(\d{3,5})$/.exec(String(cid ?? '').toLowerCase());
  if (!m) return '';
  const number = String(parseInt(m[2], 10)).padStart(3, '0');
  return `${m[1].toUpperCase()}-${number}`;
}

/** 情報欄の計算に使う集計（全作品を1回だけ数えて、作品ごとの計算を軽くする） */
export function buildFactsContext(items) {
  const byDate = new Map(); // 発売日 → 本数
  const byDateMaker = new Map(); // `発売日|メーカー` → 本数
  const makers = new Map(); // メーカー → { count, first, last }
  const cast = new Map(); // 出演者 → { count, first, last }
  const durations = [];
  let vrCount = 0;
  const bump = (map, key, day) => {
    const cur = map.get(key);
    if (!cur) map.set(key, { count: 1, first: day, last: day });
    else {
      cur.count++;
      if (day < cur.first) cur.first = day;
      if (day > cur.last) cur.last = day;
    }
  };
  for (const item of items) {
    byDate.set(item.dateKey, (byDate.get(item.dateKey) ?? 0) + 1);
    if (item.maker !== '不明') {
      const k = `${item.dateKey}|${item.maker}`;
      byDateMaker.set(k, (byDateMaker.get(k) ?? 0) + 1);
      bump(makers, item.maker, item.dateKey);
    }
    for (const name of new Set(item.actress)) bump(cast, name, item.dateKey);
    if (item.duration_min) durations.push(item.duration_min);
    if (item.vr) vrCount++;
  }
  return { byDate, byDateMaker, makers, cast, durations, vrCount };
}

/** 収録時間の順位。「長いほうから○番目」か「短いほうから○番目」の、数字が小さいほう（同じ長さは同じ順位） */
export function durationRank(minutes, durations) {
  const longer = durations.filter((d) => d > minutes).length + 1;
  const shorter = durations.filter((d) => d < minutes).length + 1;
  return longer <= shorter ? { side: '長い', rank: longer } : { side: '短い', rank: shorter };
}

const rangeText = (info) => (info.first === info.last ? `発売日は${formatDateJp(info.first)}` : `発売日は${formatDateJp(info.first)}から${formatDateJp(info.last)}`);

/** 収録時間の順位を出すのに必要な、収録時間が分かる作品の数（これより少ないと、順位に意味がないので出さない） */
export const MIN_DURATIONS_FOR_RANK = 10;
/** 情報欄に出す出演者の最大人数 */
export const FACTS_MAX_CAST = 3;

/**
 * 作品ページの「この作品のデータ」欄の行。[{ key, label, text, href?, linkLabel? }]
 * pages: リンク先（あるものだけ）。{ month: (発売日) => '/month/…/#day-…' か ''、maker: Map(名前→パス)、actress: Map(名前→パス)、vr: VRページのパス }
 * 書くのは、数えた事実だけ（作品の中身・評価は書かない）。「同じ発売日」の行は、いつも出る
 */
export function itemFacts(item, ctx, pages = {}) {
  const rows = [];

  const sameDay = ctx.byDate.get(item.dateKey) ?? 1;
  let dayText = sameDay === 1 ? `${formatDateJp(item.dateKey)}発売の作品は、この1本だけです。` : `${formatDateJp(item.dateKey)}発売の作品は、掲載中で${sameDay}本あります。`;
  if (item.maker !== '不明') {
    const sameMaker = ctx.byDateMaker.get(`${item.dateKey}|${item.maker}`) ?? 1;
    if (sameMaker >= 2) dayText += `そのうち${item.maker}の作品は${sameMaker}本です。`;
  }
  const dayHref = pages.month ? pages.month(item.dateKey) : '';
  rows.push({ key: 'day', label: '同じ発売日', text: dayText, ...(dayHref ? { href: dayHref, linkLabel: 'この月の発売日ごとの一覧を見る' } : {}) });

  const makerInfo = item.maker !== '不明' ? ctx.makers.get(item.maker) : null;
  if (makerInfo) {
    const text = makerInfo.count === 1 ? `${item.maker}の作品は、掲載中ではこの1本です。` : `${item.maker}の作品は、掲載中で${makerInfo.count}本あります（${rangeText(makerInfo)}）。`;
    const href = pages.maker?.get(item.maker) ?? '';
    rows.push({ key: 'maker', label: 'メーカー', text, ...(href ? { href, linkLabel: `${item.maker}の作品一覧を見る` } : {}) });
  }

  for (const name of item.actress.slice(0, FACTS_MAX_CAST)) {
    const info = ctx.cast.get(name);
    if (!info) continue;
    const text = info.count === 1 ? `${name}さん出演の作品は、掲載中ではこの1本です。` : `${name}さん出演の作品は、掲載中で${info.count}本あります（${rangeText(info)}）。`;
    const href = pages.actress?.get(name) ?? '';
    rows.push({ key: 'actress', label: '出演者', text, ...(href ? { href, linkLabel: `${name}さんの出演作品を見る` } : {}) });
  }
  if (item.actress.length > FACTS_MAX_CAST) {
    rows.push({ key: 'cast-more', label: '出演者', text: `ほか${item.actress.length - FACTS_MAX_CAST}名が出演しています。` });
  }

  if (item.duration_min && ctx.durations.length >= MIN_DURATIONS_FOR_RANK) {
    const { side, rank } = durationRank(item.duration_min, ctx.durations);
    rows.push({ key: 'duration', label: '収録時間', text: `収録時間は約${item.duration_min}分です。収録時間が分かる掲載作品${ctx.durations.length}本の中では、${side}ほうから${rank}番目です。` });
  }

  if (item.vr) {
    rows.push({ key: 'vr', label: '形式', text: `VR作品です。掲載中のVR作品は${ctx.vrCount}本あります。`, ...(pages.vr ? { href: pages.vr, linkLabel: 'VR作品の一覧を見る' } : {}) });
  }

  return rows;
}
