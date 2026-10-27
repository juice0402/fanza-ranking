// 検索結果に出る説明文（meta description）の部品（画面に依存しない。tests/test_describe.mjs）。
// 司令塔の連絡 C-003（2026-10-26）・プロジェクトの claude/site-principles.md の「検索結果での見え方」:
// - そのページのデータから作り、そのページにしかない具体的な数字（本数・予約受付中・日付・順位・件数など）を入れる
// - 全角80〜120文字くらい（DESC_MIN〜DESC_MAX。長い文は、後ろの文から落とす。tests/verify_dist.py が長さを見張る）
// - 値段はピッタリではなく「1,000円台から」のような幅（検索結果に古い値段が残るため）
// - キャッチコピーにしない。使わない言葉（おすすめ・お得・便利・簡単・安心・ぜひ・ポイント・コツ・しましょう）は書かない
// - 同じ説明文のページを量産しない（ページごとの日付・本数・名前を入れる）

import { TAG_PAGE_GENRES } from '../config.js';

export const DESC_MIN = 80;
export const DESC_MAX = 120;

// 説明文に入れてよい、おだやかな名前か（レーベル・作家など）。行為・体の部位・暴力・同意の無い設定・未成年を連想させる言葉を含む名前は入れない
// （コメントの点検 scripts/claude_comments.py の EXPLICIT_WORDS・MINOR_WORDS の主なもの＋設定の言葉。説明文は検索結果にそのまま出るため）
const ROUGH = /中出|射精|精液|挿入|フェラ|レイプ|強姦|凌辱|陵辱|輪姦|セックス|SEX|性交|膣|精子|ザーメン|絶頂|潮吹|乳首|巨根|チンポ|ちんぽ|マンコ|まんこ|手コキ|パイズリ|クンニ|アナル|淫|ハメ|オナニー|イラマ|顔射|ぶっかけ|ごっくん|放尿|失禁|犯|便器|奴隷|鬼畜|エロ|拉致|拷問|暴行|痴漢|催眠|監禁|拘束|調教|寝取|盗撮|未成年|少女|ロリ|児童|幼|女子高|女子校|女子中|中学|高校|小学|JK|JC|制服|学生|生徒|教え子|園児|子供|子ども|妹|娘|童顔|貧乳|つるぺた|パイパン|処女|学園/;
export const calmName = (s) => Boolean(String(s ?? '').trim()) && !ROUGH.test(String(s));

// 動画の作品ページの説明文に入れるジャンル: サイトにジャンルのページがあるもの（config.js の TAG_PAGE_GENRES）と、作品の形式のジャンルだけ
const CALM_VIDEO_GENRES = new Set([...TAG_PAGE_GENRES, 'ハイビジョン', '4K', '独占配信', '単体作品', 'デビュー作品', 'VR専用', 'ハイクオリティVR', '8KVR',
  '4時間以上作品', '16時間以上作品', '企画', '主観', '美脚', 'モデル', 'グラマー', 'キャバ嬢・風俗嬢', 'セクシー']);
/** 動画のジャンルのうち、説明文に入れるもの（作品のジャンルの順に、上から limit 個） */
export const calmVideoGenres = (genres, limit = 3) => (genres ?? []).filter((g) => CALM_VIDEO_GENRES.has(g) && calmName(g)).slice(0, limit);

const chars = (s) => Array.from(String(s ?? ''));

/** 説明文の長さ（文字の数。全角も半角も1文字） */
export const descLength = (s) => chars(s).length;

/** max 文字までに切る（切ったときは最後を「…」に） */
export function cut(text, max) {
  const c = chars(text);
  return c.length > max ? c.slice(0, max - 1).join('') + '…' : c.join('');
}

/** 文をつなげて、max 文字に入るところまで。先頭の文は必ず入れる（入らなければ切る）。あとの文は、入るものだけ順に足す */
export function fit(sentences, max = DESC_MAX) {
  let out = '';
  for (const s of sentences.filter(Boolean)) {
    if (!out) out = cut(s, max);
    else if (descLength(out + s) <= max) out += s;
  }
  return out;
}

const isDay = (s) => typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s);

/** "2026-10-26" → "10月26日" */
export const dayJp = (key) => (isDay(key) ? `${+key.slice(5, 7)}月${+key.slice(8, 10)}日` : '');

/** "2026-10-26" → "2026年10月26日" */
export const fullDayJp = (key) => (isDay(key) ? `${+key.slice(0, 4)}年${dayJp(key)}` : '');

/** 期間: 「2026年10月24日〜25日」「2026年9月30日〜10月1日」「2025年12月31日〜2026年1月1日」（同じ日なら1日だけ） */
export function dayRangeJp(a, b) {
  if (!isDay(a) || !isDay(b)) return '';
  const [lo, hi] = a <= b ? [a, b] : [b, a];
  if (lo === hi) return fullDayJp(lo);
  if (lo.slice(0, 7) === hi.slice(0, 7)) return `${fullDayJp(lo)}〜${+hi.slice(8, 10)}日`;
  if (lo.slice(0, 4) === hi.slice(0, 4)) return `${fullDayJp(lo)}〜${dayJp(hi)}`;
  return `${fullDayJp(lo)}〜${fullDayJp(hi)}`;
}

/** 値段の幅: 0円→「無料」、10円→「10円」、580円→「500円台」、1,980円→「1,000円台」、12,800円→「12,000円台」（分からなければ ''） */
export function priceBand(yen) {
  const n = Math.floor(Number(yen));
  if (yen === null || yen === undefined || yen === '' || !Number.isFinite(n) || n < 0) return '';
  if (n === 0) return '無料';
  if (n < 100) return `${n}円`;
  const unit = n < 1000 ? 100 : 1000;
  return `${(Math.floor(n / unit) * unit).toLocaleString('ja-JP')}円台`;
}

/** 収録時間: 125分→「2時間5分」、120分→「2時間」、45分→「45分」（分からなければ ''） */
export function durationJp(min) {
  const n = Math.round(Number(min));
  if (!Number.isFinite(n) || n <= 0) return '';
  if (n < 60) return `${n}分`;
  return `${Math.floor(n / 60)}時間${n % 60 ? `${n % 60}分` : ''}`;
}

/** 多い順の名前（おだやかな名前だけ。calmName）（同じ数なら先に出たもの）。skip の名前（「不明」など）は数えない */
export function topNames(names, n, skip = ['不明', '']) {
  const count = new Map();
  for (const name of names) {
    if (skip.includes(name) || !calmName(name)) continue;
    count.set(name, (count.get(name) ?? 0) + 1);
  }
  return [...count.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map(([name]) => name);
}

const san = (names) => names.map((n) => `${n}さん`).join('、');
const makerOf = (item) => (item?.maker && item.maker !== '不明' && calmName(item.maker) ? item.maker : ''); // おだやかな名前のメーカーだけ

/** 「桐谷エマさん出演のエスワン作品」（出演者・メーカーが無ければ、あるほうだけ。どちらも無ければ ''） */
export function whoMade(item) {
  const maker = makerOf(item);
  const cast = Array.isArray(item?.actress) && item.actress.length ? `${item.actress[0]}さん出演の` : '';
  if (cast && maker) return `${cast}${maker}作品`;
  if (cast) return `${item.actress[0]}さんの出演作品`;
  return maker ? `${maker}の作品` : '';
}

/**
 * トップ: 「10月26日更新。きょう発売のFANZA新作16本と、11月22日発売分までの予約受付中60本を発売日ごとに並べています。
 * 新着の人気1位は桐谷エマさん出演のエスワン作品で、セール中の特集は8件です。」
 * released: 発売済み（新しい順）・upcomingShown: 予約受付中の本数（画面の「予約受付中 N本」と同じ）・upcomingLast: いちばん先の発売日・
 * top1: 人気1位の作品（無ければ null）・topIsNew: 新着の人気順か（違えば売れ筋）・saleCount: セール中の特集の数
 */
export function homeDescription({ today, released = [], upcomingShown = 0, upcomingLast = '', top1 = null, topIsNew = true, saleCount = 0 }) {
  const newest = released[0]?.dateKey ?? '';
  const newestCount = released.filter((i) => i.dateKey === newest).length;
  const day = newest === today ? 'きょう' : dayJp(newest);
  const head = dayJp(today) ? `${dayJp(today)}更新。` : '';
  const rel = newestCount ? `${day}発売のFANZA新作${newestCount}本` : '';
  const up = upcomingShown > 0 ? `${dayJp(upcomingLast) ? `${dayJp(upcomingLast)}発売分までの` : ''}予約受付中${upcomingShown}本` : '';
  const list = rel || up ? `${[rel, up].filter(Boolean).join('と、')}を発売日ごとに並べています。` : 'FANZAの新作と予約受付中の作品を、発売日ごとに並べています。';
  const who = top1 ? whoMade(top1) : '';
  const tail = who
    ? `${topIsNew ? '新着の人気' : 'FANZAの売れ筋の'}1位は${who}${saleCount > 0 ? `で、セール中の特集は${saleCount}件です。` : 'です。'}`
    : saleCount > 0 ? `セール中の特集は${saleCount}件です。` : '';
  return fit([head + list, tail]);
}

/** 新着の人気ランキング: 「10月25日の新着の人気順です。最近1週間に発売されたFANZA動画の新作から上位100本を並べています。1位は…で、100本のうちVR作品は33本です。」 */
export function rankingDescription({ date, list = [] }) {
  const n = list.length;
  const head = `${dayJp(date) ? `${dayJp(date)}の` : ''}新着の人気順です。`;
  const body = n ? `最近1週間に発売されたFANZA動画の新作から上位${n}本を並べています。` : '最近1週間に発売されたFANZA動画の新作を、人気順に並べています。';
  const vr = list.filter((i) => i.vr).length;
  const who = n ? whoMade(list[0]) : '';
  const tail = who ? `1位は${who}${n > 1 ? `で、${n}本のうちVR作品は${vr}本です。` : 'です。'}` : '';
  return fit([head + body, tail]);
}

/** 過去作品の一覧: 「2026年10月24日〜25日に発売されたFANZA動画30本の一覧です（2ページ目・全474ページ）。メーカーは…など、出演は…ほか。」 */
export function archiveDescription(items, current, last) {
  const keys = items.map((i) => i.dateKey).filter(isDay).sort();
  const range = keys.length ? dayRangeJp(keys[0], keys[keys.length - 1]) : '';
  const head = `${range ? `${range}に発売された` : ''}FANZA動画${items.length}本の一覧です（${current}ページ目・全${last}ページ）。`;
  const makers = topNames(items.map((i) => i.maker), 2);
  const cast = topNames(items.flatMap((i) => i.actress ?? []), 2);
  const tail = [
    makers.length ? `メーカーは${makers.join('や')}${makers.length > 1 ? 'など' : ''}` : '',
    cast.length ? `出演は${san(cast)}ほか` : '',
  ].filter(Boolean).join('、');
  return fit([head, tail ? `${tail}。` : '']);
}

/** 月ごとの一覧: 「FANZA動画の新作を、発売月ごとに14か月分まとめています（2025年9月〜2026年11月）。いちばん新しい2026年11月は…本、…」 */
export function monthIndexDescription(groups) {
  if (!groups.length) return 'FANZA動画の新作と予約作品を、発売月ごとにまとめた一覧です。発売日の順に並べています。';
  const sorted = [...groups].sort((a, b) => String(a.ym).localeCompare(String(b.ym)));
  const first = sorted[0];
  const latest = sorted[sorted.length - 1];
  const most = [...groups].sort((a, b) => b.items.length - a.items.length)[0];
  return fit([
    `FANZA動画の新作と予約作品を、発売月ごとに${groups.length}か月分まとめています（${first.name}〜${latest.name}）。`,
    `いちばん新しい${latest.name}は${latest.items.length}本、`,
    most !== latest ? `いちばん多い${most.name}は${most.items.length}本です。` : '発売日の順に並べています。',
  ]);
}

/** ジャンルの一覧: 「FANZA動画の作品を、ジャンルごとに120件まとめた一覧です。作品がいちばん多いのはハイビジョン（2,345本）で、…」 */
export function tagIndexDescription(groups) {
  if (!groups.length) return 'FANZA動画の作品を、ジャンルごとにまとめた一覧です。作品数の多い順に並べています。';
  const sorted = [...groups].sort((a, b) => b.items.length - a.items.length);
  const fmt = (g) => `${g.name}（${g.items.length.toLocaleString('ja-JP')}本）`;
  const head = `FANZA動画の作品を、ジャンルごとに${groups.length}件まとめた一覧です。`;
  // 多い順に4つまで（入らなければ3つ・2つ…）。文の途中で切れないように、まるごと入るものを選ぶ
  for (let n = Math.min(4, sorted.length); n >= 1; n -= 1) {
    const top = sorted.slice(0, n);
    const body = n > 1 ? `作品がいちばん多いのは${fmt(top[0])}で、${top.slice(1).map(fmt).join('、')}と続きます。` : `作品がいちばん多いのは${fmt(top[0])}です。`;
    if (descLength(head + body) <= DESC_MAX) return head + body;
  }
  return cut(head, DESC_MAX);
}

/** 週のまとめの一覧: 「FANZA動画の新作を1週間ごとにまとめた記事3本の一覧です。いちばん新しいのは10月19日〜25日の週で、…本の新作をふり返っています。」 */
export function weeklyIndexDescription(roundups) {
  if (!roundups.length) return 'FANZA動画の新作を、1週間ごとにまとめた記事の一覧です。毎週月曜に、先週（月曜〜日曜）の分を公開します。';
  const r = roundups[0];
  const start = String(r.week_start ?? '');
  const end = isDay(start) ? new Date(Date.parse(`${start}T00:00:00Z`) + 6 * 86400000).toISOString().slice(0, 10) : '';
  const total = Number(r.facts?.total) || 0;
  return fit([
    `FANZA動画の新作を1週間ごとにまとめた記事${roundups.length}本の一覧です。`,
    end ? `いちばん新しいのは${dayJp(start)}〜${dayJp(end)}の週で、${total ? `${total}本の新作をふり返っています。` : '発売された新作をふり返っています。'}` : '',
    '毎週月曜に、先週の分を足します。',
  ]);
}

/** 女優のイベント情報: 「所属事務所の公式サイトに載っている女優のイベント22件を、日付ごとにまとめています（10月26日〜11月8日）。サイン会が9件、撮影会が5件です。」 */
export function eventIndexDescription(rows) {
  if (!rows.length) return '所属事務所の公式サイトに載っている、女優のサイン会・撮影会・発売記念イベントなどの予定を、日付ごとにまとめています。';
  const days = rows.map((e) => e.date).filter(isDay).sort();
  const kinds = new Map();
  for (const e of rows) if (e.kind) kinds.set(e.kind, (kinds.get(e.kind) ?? 0) + 1);
  const top = [...kinds.entries()].sort((a, b) => b[1] - a[1]).slice(0, 2);
  return fit([
    `所属事務所の公式サイトに載っている女優のイベント${rows.length}件を、日付ごとにまとめています（${days[0] === days[days.length - 1] ? dayJp(days[0]) : `${dayJp(days[0])}〜${dayJp(days[days.length - 1])}`}）。`,
    top.length ? `${top.map(([k, n]) => `${k}が${n}件`).join('、')}です。` : '',
    '毎日、日付が変わったあとに更新します。',
  ]);
}

/** 女優検索: 「FANZAのAV女優10,480人を、名前・年齢・身長・スリーサイズ・カップで探せます。…」 */
export function actressIndexDescription({ total = 0, withSize = 0, agencies = 0 } = {}) {
  const fmt = (n) => Number(n).toLocaleString('ja-JP');
  return fit([
    `FANZAのAV女優${total ? `${fmt(total)}人` : ''}を、名前・年齢・身長・スリーサイズ・カップで探せます。`,
    withSize ? `スリーサイズの分かる${fmt(withSize)}人は、体型でも絞り込めます。` : '',
    agencies ? `所属事務所${agencies}社の公式サイトの情報も入っています。` : '',
    'プロフィールはFANZA公式のデータです。',
  ]);
}

/** 女優の年表の一覧（/actress/nenpyo/。2026-10-27）: 人数・いちばん本数の多い人の数字から */
export function nenpyoDescription({ count = 0, top = null } = {}) {
  const fmt = (n) => Number(n).toLocaleString('ja-JP');
  return fit([
    count ? `FANZAのAV女優${fmt(count)}人の年表を、50音順にまとめました。` : 'FANZAのAV女優の年表を、50音順にまとめるページです。',
    'FANZAでいちばん古い作品の年、年ごとの本数、メーカーごとの歩みを、女優のページで見られます。',
    top ? `本数がいちばん多いのは${top.name}さんの${fmt(top.total)}本（${+top.first.d.slice(0, 4)}年から）。` : '',
    '数字はFANZA公式のデータで、毎日ふえていきます。',
  ]);
}
