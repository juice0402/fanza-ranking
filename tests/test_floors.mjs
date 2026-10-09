// FANZA同人・FANZAゲームのページの部品（site/src/lib/floors.js）のテスト。実行: node tests/test_floors.mjs
// （本番データには依存しない。作った作品で試す。名前・タイトルは、どれも作ったもの）
import fs from 'node:fs';
import * as L from '../site/src/lib/floors.js';
import { nonItemFileCount } from '../site/src/lib/plan.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + JSON.stringify(detail) : '')); }
};
const today = '2026-10-09';
const row = (n, extra = {}) => ({
  cid: `d_${100000 + n}`, title: `作った作品その${n}`, url: `https://al.fanza.co.jp/?lurl=x${n}&af_id=t-990`,
  image_url: `https://doujin-assets.dmm.co.jp/digital/comic/d_${100000 + n}/d_${100000 + n}pl.jpg`,
  sample_images: ['https://doujin-assets.dmm.co.jp/s1.jpg', 'https://evil.example/s2.jpg'], date: '2026-09-20 00:00:00',
  maker: `サークル${n % 3}`, maker_id: 200 + (n % 3), authors: [], series: '', series_id: 0, genres: ['巨乳', 'ファンタジー', '中出し'], formats: ['男性向け'], sales: [],
  price: 990, list_price: 1100, campaign: { title: '10%OFF', begin: '2026-10-01' }, comment: '', comment_kind: 'none', updated: '2026-10-09', ...extra,
});
const raw = {
  updated: '2026-10-09', scanned: 200, skipped: 20,
  ranks: { d_100001: 3, d_100002: 1, d_100003: 2, d_100004: 5, d_100006: 4 },
  items: [
    row(1), row(2, { price: 1100, list_price: 1100, campaign: null }), row(3, { comment: 'Claudeが書いたコメント', comment_kind: 'claude' }),
    row(4, { date: '2025-01-01 00:00:00' }), row(5, { title: '放課後のなにか' }), row(6, { genres: ['ロリ'] }),
    row(7, { url: 'https://evil.example/x' }), row(8, { date: '2026-11-20 00:00:00' }), row(9, { maker: 'JK工房' }), row(1),
    row(10, { comment: '書きかけ', comment_kind: 'none' }),
  ],
};
const fl = L.normalizeFloor(raw, 'doujin', today);
const cids = fl.items.map((i) => i.cid);

console.log('■ 読み込み（normalizeFloor）');
check('人気の高い順（順位の無い作品はそのあと、発売日の新しい順）・同じ品番は1つ', cids.join() === 'd_100002,d_100003,d_100001,d_100004,d_100008,d_100010', cids);
check('未成年を連想させる作品は出さない（タイトル・ジャンル・サークル。集めるときにも外しているが、念のため）', !cids.includes('d_100005') && !cids.includes('d_100006') && !cids.includes('d_100009'));
check('URL が FANZA の https でない作品は出さない・サンプル画像も DMM の https だけ', !cids.includes('d_100007') && fl.items[0].sample_images.length === 1);
const i1 = fl.items.find((i) => i.cid === 'd_100001');
check('値引き（%）・定価・キャンペーン・サークル（id）・順位', i1.off === 10 && i1.listPrice === 1100 && i1.campaign.title === '10%OFF' && i1.maker.id === 201 && i1.rank === 3, i1);
check('定価と同じ価格は値引きなし', fl.items.find((i) => i.cid === 'd_100002').off === 0);
check('コメントは Claude が書いたものだけ（none のコメントは出さない）', fl.items.find((i) => i.cid === 'd_100003').comment === 'Claudeが書いたコメント' && fl.items.find((i) => i.cid === 'd_100010').comment === '');
check('予約（発売日がきょうより先）', fl.items.find((i) => i.cid === 'd_100008').upcoming && !i1.upcoming);
check('同人の画像（doujin-assets）は、同じ場所の pics.dmm.co.jp にする・ほかの URL はそのまま',
  i1.image_url === 'https://pics.dmm.co.jp/digital/comic/d_100001/d_100001pl.jpg' && i1.sample_images[0] === 'https://pics.dmm.co.jp/s1.jpg'
  && L.picsUrl('https://pics.dmm.co.jp/a.jpg') === 'https://pics.dmm.co.jp/a.jpg' && L.picsUrl('') === '', i1.image_url);
check('pics.dmm.co.jp で読めなかったら doujin-assets に1回だけ戻す（属性に入れるので < > & " を使わない）',
  !/[<>&"]/.test(L.DOUJIN_IMG_ONERROR) && L.DOUJIN_IMG_ONERROR.includes("'https://doujin-assets.dmm.co.jp/'+this.src.slice(" + 'https://pics.dmm.co.jp/'.length + ')') && L.DOUJIN_IMG_ONERROR.includes('dataset.alt'));
// 同人のスマホ版（運営者の「スマホのサムネを少しきれいに。同じしくみを同人にも」。2026-10-09）
const dThumb = L.doujinThumb(i1.image_url);
check('同人のスマホ版: カードは幅300・小さな棚は幅240の縮めて返す版（画質75）・パソコンは元の画像',
  dThumb.src === i1.image_url && dThumb.small === 'https://awsimgsrc.dmm.co.jp/pics_dig/digital/comic/d_100001/d_100001pl.jpg?w=300&q=75'
  && L.doujinThumb(i1.image_url, 'tiny').small.endsWith('d_100001pl.jpg?w=240&q=75') && L.DOUJIN_CARD_W === 300 && L.DOUJIN_TINY_W === 240);
const runDoujinErr = ({ src, prev, matches, alt }) => {
  const log = [];
  const img = { src, dataset: alt ? { alt: '1' } : {}, style: {}, previousElementSibling: prev ? { tagName: prev, media: '(max-width: 480px)', remove: () => log.push('remove-source') } : null };
  new Function('matchMedia', L.DOUJIN_THUMB_ONERROR).call(img, () => ({ matches }));
  if (img.src !== src) log.push('src=' + img.src.slice(0, 31));
  if (img.style.visibility) log.push('hidden');
  return log.join(',');
};
check('同人のスマホ版が読めない → <source> を外す（元の画像に戻る）。元の画像が読めない → doujin-assets に1回だけ・それもだめなら隠す（< > & " を使わない）',
  !/[<>&"]/.test(L.DOUJIN_THUMB_ONERROR)
  && runDoujinErr({ src: i1.image_url, prev: 'SOURCE', matches: true }) === 'remove-source'
  && runDoujinErr({ src: i1.image_url, prev: 'SOURCE', matches: false }) === 'src=https://doujin-assets.dmm.co.jp'
  && runDoujinErr({ src: i1.image_url, prev: null, matches: false, alt: true }) === 'hidden');
for (const f of ['FloorCard', 'FloorMiniShelf']) {
  const src = fs.readFileSync(new URL(`../site/src/components/${f}.astro`, import.meta.url), 'utf-8');
  check(`${f}.astro: 同人は <picture>（スマホは縮めた版）・img は DOUJIN_THUMB_ONERROR・どのページから読んだかを送らない`,
    /<picture class="pic"><source media=\{THUMB_MEDIA\} srcset=\{doujinThumb\([^)]*\)\.small\} \/><img class="floor-img"[^>]*referrerpolicy="no-referrer" onerror=\{DOUJIN_THUMB_ONERROR\} \/><\/picture>/.test(src));
}
check('壊れたデータ・空でも落ちない', L.normalizeFloor(null, 'game', today).items.length === 0 && L.normalizeFloor({ items: 'x' }, 'game', today).items.length === 0);

console.log('\n■ 並べ方');
check('人気ランキング: 発売済みで順位のある作品を順位の順', L.floorRanking(fl.items).map((i) => i.cid).join() === 'd_100002,d_100003,d_100001,d_100004', L.floorRanking(fl.items).map((i) => i.cid));
check('新作で人気: 最近30日の発売だけ（古い作品・予約は入れない）', L.floorNewPopular(fl.items, today).map((i) => i.cid).join() === 'd_100002,d_100003,d_100001');
check('予約: 発売日の近い順', L.floorUpcoming(fl.items).map((i) => i.cid).join() === 'd_100008');
check('セール中（同人）: 値引きの分かる発売済みの作品を、人気の高い順', L.floorSaleItems(fl.items).map((i) => i.cid).join() === 'd_100003,d_100001,d_100004,d_100010' && L.floorMaxOff(L.floorSaleItems(fl.items)) === 10);
check('カードの札と価格: 「10%OFF」「990円（通常1,100円）」・値引きなしは「1,100円」', L.saleBadgeOf(i1) === '10%OFF' && L.priceNote(i1) === '990円（通常1,100円）' && L.priceNote(fl.items[0]) === '1,100円' && L.saleBadgeOf(fl.items[0]) === '');

console.log('\n■ ゲームのセール（値下げのセールと、クーポン・ポイント還元を分ける）');
const g = L.normalizeFloor({ ranks: { g_1: 1, g_2: 2, g_3: 3 }, items: [
  row(1, { cid: 'g_1', price: 8800, list_price: null, campaign: null, sales: ['最大90%OFFセール【感謝祭オータム2026】', '3点以上で5%OFFクーポン／感謝祭オータム2026対象', '秋の最大16%ポイント還元キャンペーン 第5弾'], authors: ['作った原画家'] }),
  row(2, { cid: 'g_2', price: 6600, list_price: null, campaign: null, sales: ['3点以上で5%OFFクーポン／感謝祭オータム2026対象'] }),
  row(3, { cid: 'g_3', price: 500, list_price: null, campaign: null, sales: ['500円セール【感謝祭オータム2026】', '最大90%OFFセール【感謝祭オータム2026】'] }),
] }, 'game', today);
check('値下げのセールの札だけをセール中と数える（クーポン・ポイント還元はほぼ全部に付くので数えない）',
  L.floorSaleItems(g.items).map((i) => i.cid).join() === 'g_1,g_3' && L.saleBadgeOf(g.items[0]) === 'セール中' && L.saleBadgeOf(g.items[1]) === '');
const groups = L.saleTagGroups(g.items);
check('セールの札ごと（対象の多い順・人気の高い順）', groups.map((x) => `${x.title}:${x.items.map((i) => i.cid).join('+')}`).join() === '最大90%OFFセール【感謝祭オータム2026】:g_1+g_3,500円セール【感謝祭オータム2026】:g_3', groups);
check('クーポン・ポイント還元は名前と本数だけ', JSON.stringify(L.couponTags(g.items)) === JSON.stringify([{ title: '3点以上で5%OFFクーポン／感謝祭オータム2026対象', total: 2 }, { title: '秋の最大16%ポイント還元キャンペーン 第5弾', total: 1 }]));
check('作品ページの札の行き先: セールはその見出し・クーポンはクーポンの欄', L.saleTagHref('game', '500円セール【感謝祭オータム2026】') === `/game/sale/#${L.saleTagAnchor('500円セール【感謝祭オータム2026】')}` && L.saleTagHref('game', '3点以上で5%OFFクーポン／感謝祭オータム2026対象') === '/game/sale/#coupons');
check('見出しの id は名前から決まる・英数字だけ', /^tag-[0-9a-z]+$/.test(L.saleTagAnchor('最大90%OFFセール【感謝祭オータム2026】')) && L.saleTagAnchor('a') === L.saleTagAnchor('a') && L.saleTagAnchor('a') !== L.saleTagAnchor('b'));
check('カードの1行: ゲームは作家も1人', L.makerLine(g.items[0]) === 'サークル1｜作家 作った原画家' && L.makerLine(i1) === 'サークル1');

console.log('\n■ サークル・ブランド・ジャンル・関連の作品');
const makers = L.floorMakers(fl.items, 'doujin');
check('サークル: 作品が2本以上・作品の多い順・ページの場所', makers.map((m) => `${m.name}:${m.total}`).join() === 'サークル1:3,サークル2:2' && makers[0].path === '/doujin/maker/201/', makers.map((m) => [m.name, m.total]));
const byId = new Map(makers.map((m) => [m.id, m]));
check('同じサークルの作品（その作品を除く・人気の高い順）', L.sameMaker(i1, byId).map((i) => i.cid).join() === 'd_100004,d_100010');
check('多いジャンル: おだやかなジャンルだけ（行為のジャンルは数えない）', L.topGenres(fl.items).map((x) => x.name).join() === 'ファンタジー,巨乳' && !L.topGenres(fl.items).some((x) => x.name === '中出し'));
const pop = L.popularInFloorGenre(i1, fl.items);
check('「○○で人気の作品」: おだやかなジャンルで、ほかの作品が4本以上あるもの', pop.genre === 'ファンタジー' || pop.genre === '巨乳', pop);
const py = fs.readFileSync(new URL('../scripts/claude_comments.py', import.meta.url), 'utf-8');
const pyList = [...py.match(/FLOOR_COMMENT_GENRES = \[([\s\S]*?)\]/)[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
check('見出し・多いジャンルに出すジャンルは、コメントの手がかりのジャンル（claude_comments.py の FLOOR_COMMENT_GENRES）と同じ', JSON.stringify(pyList) === JSON.stringify(L.FLOOR_GENRE_OK), [pyList.length, L.FLOOR_GENRE_OK.length]);

console.log('\n■ ページの場所・タイトル・ファイルの数');
check('場所: /doujin/・/doujin/ranking/・/doujin/sale/・/doujin/item/<品番>/・/game/maker/<id>/',
  L.floorPath('doujin') === '/doujin/' && L.floorRankingPath('doujin') === '/doujin/ranking/' && L.floorSalePath('doujin') === '/doujin/sale/'
  && L.floorItemPath('doujin', 'd_1') === '/doujin/item/d_1/' && L.floorMakerPath('game', 5) === '/game/maker/5/' && L.floorMakerIndexPath('game') === '/game/maker/');
check('作品ページのタイトル: 「タイトル｜FANZA同人（サークル）｜サイト名」', L.floorItemTitle(i1, 'サイト') === '作った作品その1｜FANZA同人（サークル1）｜サイト');
check('作品ページの説明文: コメントがあれば先に・発売日・サークル', L.floorItemDescription(fl.items.find((i) => i.cid === 'd_100003')).startsWith('Claudeが書いたコメント FANZA同人の同人作品「作った作品その3」（サークル：サークル0）。2026年9月20日発売。'));
check('ファイルの数: 作品ページ＋サークル/ブランドのページ＋4（トップ・ランキング・セール・一覧）。作品が無い売り場は0', L.floorFileCount(fl, makers) === fl.items.length + 2 + 4 && L.floorFileCount({ items: [] }, []) === 0);
check('サイト全体の計画に、同人・ゲームのページの数を足せる（動画の作品ページより先に枠を取る）', nonItemFileCount({ floors: 100 }, 0, 30) - nonItemFileCount({}, 0, 30) === 100);
check('本数の決まり: 同人の作品ページは、そのまま全部（動画の作品ページの枠から先に引く）', L.FLOOR_RANKING_LIMIT === 100 && L.FLOOR_SAMPLES === 8);

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
