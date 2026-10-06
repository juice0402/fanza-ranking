// 作品ページの「品番」と「この作品のデータ」欄の部品（画面に依存しない。テスト: tests/test_seo.mjs）。
// どちらも、保存してある作品データだけから、ビルドのたびに数えて作る（AIは使わない）。文章の数字は、いつも一覧と同じになる。

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
    if (item.vr) vrCount++;
  }
  return { byDate, byDateMaker, makers, cast, vrCount };
}

// 発売日の幅は、年だけの短い形（「2020〜2026年」。運営者の希望「長すぎる説明文は誰も読まない」。2026-10-06）
const yearsText = (info) => (info.first.slice(0, 4) === info.last.slice(0, 4) ? `${+info.first.slice(0, 4)}年` : `${+info.first.slice(0, 4)}〜${+info.last.slice(0, 4)}年`);

export const FACTS_MAX_CAST = 3;

/**
 * 作品ページの「この作品のデータ」欄の行。[{ key, label, text, href?, linkLabel? }]
 * pages: リンク先（あるものだけ）。{ month: (発売日) => '/month/…/#day-…' か ''、maker: Map(名前→パス)、actress: Map(名前→パス)、vr: VRページのパス }
 * 書くのは、数えた事実だけ（作品の中身・評価は書かない）。「同じ発売日」の行は、いつも出る
 */
export function itemFacts(item, ctx, pages = {}) {
  const rows = [];

  // 文は短く（「6本（うちムーディーズ 6本）」の形。運営者の希望「長すぎる説明文は誰も読まない」。2026-10-06）
  const sameDay = ctx.byDate.get(item.dateKey) ?? 1;
  let dayText = sameDay === 1 ? 'この1本だけ' : `${sameDay}本`;
  if (sameDay > 1 && item.maker !== '不明') {
    const sameMaker = ctx.byDateMaker.get(`${item.dateKey}|${item.maker}`) ?? 1;
    if (sameMaker >= 2) dayText += `（うち${item.maker} ${sameMaker}本）`;
  }
  const dayHref = pages.month ? pages.month(item.dateKey) : '';
  rows.push({ key: 'day', label: '同じ発売日', text: dayText, ...(dayHref ? { href: dayHref, linkLabel: 'この月の一覧' } : {}) });

  const makerInfo = item.maker !== '不明' ? ctx.makers.get(item.maker) : null;
  if (makerInfo) {
    const text = makerInfo.count === 1 ? `${item.maker}の作品はこの1本` : `${item.maker}の作品 ${makerInfo.count}本（${yearsText(makerInfo)}）`;
    const href = pages.maker?.get(item.maker) ?? '';
    rows.push({ key: 'maker', label: 'メーカー', text, ...(href ? { href, linkLabel: '一覧を見る' } : {}) });
  }

  // 出演者: 掲載が2本以上の人は1人ずつの行（先頭から FACTS_MAX_CAST 人まで）。この1本だけの人は、1つの行にまとめる（同じ文が何行も並ばないように）
  const once = [];
  for (const name of item.actress.slice(0, FACTS_MAX_CAST)) {
    const info = ctx.cast.get(name);
    if (!info) continue;
    if (info.count === 1) {
      once.push(name);
      continue;
    }
    const href = pages.actress?.get(name) ?? '';
    rows.push({ key: 'actress', label: '出演者', text: `${name}さんの出演作品 ${info.count}本（${yearsText(info)}）`, ...(href ? { href, linkLabel: '一覧を見る' } : {}) });
  }
  const more = Math.max(0, item.actress.length - FACTS_MAX_CAST);
  if (once.length > 0) {
    const who = once.map((n) => `${n}さん`).join('・');
    const text = once.length === 1 ? `${who}の出演作品はこの1本` : `${who}の出演作品は、${once.length > 2 ? 'いずれも' : 'どちらも'}この1本`;
    rows.push({ key: 'actress-once', label: '出演者', text: more ? `${text}（ほか${more}名）` : text });
  } else if (more) {
    rows.push({ key: 'cast-more', label: '出演者', text: `ほか${more}名` });
  }

  // 収録時間の長さくらべ（掲載作品の中で長いほうから○番目）は、運営者の判断で出さない（2026-10-05「長さで買っている人はいないと思う」）。
  // 収録時間そのものは、作品ページの基本情報に出している

  if (item.vr) {
    rows.push({ key: 'vr', label: '形式', text: `VR作品 ${ctx.vrCount}本`, ...(pages.vr ? { href: pages.vr, linkLabel: '一覧を見る' } : {}) });
  }

  return rows;
}
