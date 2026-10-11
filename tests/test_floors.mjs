// FANZA同人・FANZAゲームのページの部品（site/src/lib/floors.js）のテスト。実行: node tests/test_floors.mjs
// （本番データには依存しない。作った作品で試す。名前・タイトルは、どれも作ったもの）
import fs from 'node:fs';
import * as L from '../site/src/lib/floors.js';
import { nonItemFileCount } from '../site/src/lib/plan.js';
import { trendChart } from '../site/src/lib/insights.js';
import { isMinorTitle } from '../site/src/lib/gacha.js';
import vm from 'node:vm';
// ブラウザで動くスクリプト（site/public/）の部品を、node の中で読む（module.exports に出している）
const loadPublic = (name) => {
  const sandbox = { module: { exports: {} } };
  vm.runInNewContext(fs.readFileSync(new URL(`../site/public/${name}`, import.meta.url), 'utf-8'), sandbox);
  return sandbox.module.exports;
};
const FS = loadPublic('floor-search.js');
const G = loadPublic('gacha.js');

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
check('割引は、価格が0円でなければ99%まで（10円・定価2,310円を「100%OFF」にしない。2026-10-11）', L.offOf(10, 2310) === 99 && L.offOf(550, 1100) === 50 && L.offOf(0, 100) === 0);
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
{
  // 売り場の表紙は components/FloorImg.astro に（2026-10-10）。同人・素人は <picture>（スマホは縮めた版）・img は framedThumb の onerror・どのページから読んだかを送らない
  const src = fs.readFileSync(new URL('../site/src/components/FloorImg.astro', import.meta.url), 'utf-8');
  check('FloorImg.astro: 同人・素人は <picture>（スマホは縮めた版）・img は framedThumb の onerror（同人は DOUJIN_THUMB_ONERROR）・どのページから読んだかを送らない',
    /<picture class="pic"><source media=\{THUMB_MEDIA\} srcset=\{t\.small\} \/><img class="floor-img"[^>]*referrerpolicy="no-referrer" onerror=\{t\.onerror\} \/><\/picture>/.test(src)
    && L.framedThumb('doujin', i1.image_url).onerror === L.DOUJIN_THUMB_ONERROR && L.framedThumb('amateur', 'https://pics.dmm.co.jp/digital/amateur/x/xjp.jpg', 'tiny').small === 'https://awsimgsrc.dmm.co.jp/pics_dig/digital/amateur/x/xjp.jpg?w=240&q=75');
  for (const f of ['FloorCard', 'FloorMiniShelf', 'FloorTop3', 'FloorTopics', 'FloorSaleCards', 'FloorRow']) {
    const c = fs.readFileSync(new URL(`../site/src/components/${f}.astro`, import.meta.url), 'utf-8');
    check(`${f}.astro: 表紙は FloorImg.astro（売り場ごとの枠の形）`, c.includes("import FloorImg from './FloorImg.astro'") && c.includes('<FloorImg ') && !c.includes("=== 'doujin'"));
  }
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
check('作品ページの札の行き先: セールはセールのページ・クーポンはクーポンの欄', L.saleTagHref('game', '500円セール【感謝祭オータム2026】') === '/game/sale/' && L.saleTagHref('game', '3点以上で5%OFFクーポン／感謝祭オータム2026対象') === '/game/sale/#coupons');
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
check('ファイルの数: 作品ページ＋サークル/ブランドのページ＋10（トップ・ランキング・セール・セールの記録・一覧・サークル/作家ランキング・検索・索引・運命の作品の候補）。作品が無い売り場は0', L.floorFileCount(fl, makers) === fl.items.length + 2 + 10 && L.floorFileCount({ items: [] }, []) === 0);
check('サイト全体の計画に、同人・ゲームのページの数を足せる（動画の作品ページより先に枠を取る）', nonItemFileCount({ floors: 100 }, 0, 30) - nonItemFileCount({}, 0, 30) === 100);
check('本数の決まり: 同人の作品ページは、そのまま全部（動画の作品ページの枠から先に引く）', L.FLOOR_RANKING_LIMIT === 100 && L.FLOOR_SAMPLES === 8);

// 運営者の希望「動画のページと同じレベルのコレクションを同人とゲームにも。SEO対策も徹底的に」（2026-10-09）
console.log('\n■ コレクション（ジャンル・シリーズ・作家・発売月のページ）');
const crow = (n, extra) => row(n, { cid: `d_${300000 + n}`, price: 1100, list_price: 1100, campaign: null, genres: [], authors: [], ...extra });
const cfl = L.normalizeFloor({
  ranks: { d_300001: 1, d_300002: 2, d_300003: 3, d_300005: 5, d_300007: 7 },
  items: [
    crow(1, { genres: ['巨乳', 'ファンタジー'], series: 'さくぶんシリーズ', series_id: 7, authors: ['作家A'], date: '2026-09-20 00:00:00', comment: 'Claudeが書いたコメント', comment_kind: 'claude' }),
    crow(2, { genres: ['巨乳'], series: 'さくぶんシリーズ', series_id: 7, authors: ['作家A', '作家B'], date: '2026-09-10 00:00:00' }),
    crow(3, { genres: ['巨乳', '中出し'], series: 'さくぶんシリーズ', series_id: 7, date: '2026-09-05 00:00:00', price: 550 }),
    crow(4, { genres: ['ファンタジー'], date: '2026-08-01 00:00:00' }),
    crow(5, { genres: ['ファンタジー'], date: '2026-09-01 00:00:00' }),
    crow(6, { genres: ['中出し'], authors: ['作家B'], date: '2026-11-01 00:00:00' }),
    crow(7, { date: '2026-09-25 00:00:00' }),
    crow(8, { genres: ['巨乳'], series: '放課後シリーズ', series_id: 9, date: '2026-09-02 00:00:00' }),
  ],
}, 'doujin', today);
const cols = L.floorCollections(cfl.items, 'doujin');
const colNames = (kind) => cols[kind].map((x) => `${x.name}:${x.items.map((i) => i.cid.slice(-1)).join('')}`).join();
check('ジャンル: おだやかなジャンルだけ・3本以上・作品の多い順（同じなら名前の順）・中は人気の高い順', colNames('genre') === 'ファンタジー:154,巨乳:123', colNames('genre'));
check('ジャンルのページの場所は、名前から決まる印（動画の出演者・メーカーと同じ entitySlug）', cols.genre[1].path === `/doujin/genre/${cols.genre[1].slug}/` && /^[0-9a-f]{10}$/.test(cols.genre[1].slug));
check('シリーズ: FANZAの id ごと・3本以上（未成年を連想させる名前のシリーズは、作品ごと出さない）', colNames('series') === 'さくぶんシリーズ:123' && cols.series[0].path === '/doujin/series/7/' && !cfl.items.some((i) => i.cid === 'd_300008'), colNames('series'));
check('作家: 2本以上・作品の多い順（同じなら名前の順）', colNames('author') === '作家A:12,作家B:26', colNames('author'));
check('発売月: 5本以上の月だけ・新しい月から・名前は「2026年9月」', colNames('month') === '2026年9月:12357' && cols.month[0].path === '/doujin/month/2026-09/' && L.monthName('2026-10') === '2026年10月', colNames('month'));
check('一覧の場所: /doujin/genre/・/game/author/', L.floorCollectionIndexPath('doujin', 'genre') === '/doujin/genre/' && L.floorCollectionIndexPath('game', 'author') === '/game/author/' && L.FLOOR_COLLECTION_KINDS.join() === 'genre,series,author,month,type,theme');
const big = cols.genre[1];
const facts = L.collectionFacts(big.items, today);
check('数字: 本数・セール中・最大の割引・新作（30日）・予約', JSON.stringify(facts) === JSON.stringify({ total: 3, sale: 1, maxOff: 50, fresh: 2, upcoming: 0 }), facts);
check('検索エンジンに出すのは、並べる作品（60本）にコメントのある作品があるページだけ・一覧は1つでもあれば',
  L.collectionIndexable(big) && !L.collectionIndexable(cols.author[1]) && L.collectionIndexIndexable(cols.author) && !L.collectionIndexIndexable([cols.author[1]]) && !L.collectionIndexIndexable([]));
const f = L.FLOORS.doujin;
check('タイトル: ジャンル「FANZA同人「巨乳」の人気作品一覧【2026年10月】（3本）｜サイト」',
  L.collectionTitle(f, big, '2026年10月', 'サイト') === 'FANZA同人「巨乳」の人気作品一覧【2026年10月】（3本）｜サイト', L.collectionTitle(f, big, '2026年10月', 'サイト'));
check('タイトル: シリーズ・作家・発売月',
  L.collectionTitle(f, cols.series[0], '2026年10月', 'サイト') === 'さくぶんシリーズ｜FANZA同人のシリーズ作品一覧【2026年10月】（3本）｜サイト'
  && L.collectionTitle(L.FLOORS.game, { ...cols.author[0], kind: 'author' }, '2026年10月', 'サイト') === '作家AのPCゲーム一覧（FANZAゲーム）【2026年10月】（2本）｜サイト'
  && L.collectionTitle(f, cols.month[0], '2026年10月', 'サイト') === 'FANZA同人 2026年9月発売の同人作品・人気順（5本）｜サイト');
check('見出し', L.collectionHeading(f, big) === 'FANZA同人の「巨乳」作品' && L.collectionHeading(f, cols.month[0]) === '2026年9月発売の同人作品');
const desc = L.collectionDescription(f, big, facts);
check('説明文: 数えた事実だけ（本数・セール中・最大の割引）', desc === 'FANZA同人の「巨乳」のジャンルの同人作品3本を、FANZAの人気順でまとめています。いまセール中の作品が1本（最大50%OFF）。毎日、日付が変わったあとに更新します。', desc);
check('いっしょに付いていることが多いジャンル: そのジャンル自身・行為のジャンルは出さない', L.relatedFloorGenres(big.items, '巨乳').map((x) => x.name).join() === 'ファンタジー');
const c2 = cfl.items.find((i) => i.cid === 'd_300002');
const links = L.collectionLinksFor(c2, cols);
check('作品ページから: ジャンル・シリーズ・作家・発売月のページへ（ページのあるものだけ）',
  links.genres.get('巨乳') === big.path && links.series.path === '/doujin/series/7/' && links.authors.size === 2 && links.month.path === '/doujin/month/2026-09/', [...links.genres, links.series?.path, [...links.authors], links.month?.path]);
const l6 = L.collectionLinksFor(cfl.items.find((i) => i.cid === 'd_300006'), cols);
check('ページの無いジャンル（行為のジャンル）・月にはリンクしない', l6.genres.size === 0 && l6.series === null && l6.authors.get('作家B') === cols.author[1].path && l6.month === null);
const ld = L.floorItemListLd(big.items, 'https://example.pages.dev', 2);
check('一覧の構造化データ（ItemList）: 作品ページへのリンクを並びの順に', ld['@type'] === 'ItemList' && ld.numberOfItems === 2 && ld.itemListElement[1].position === 2 && ld.itemListElement[1].url === 'https://example.pages.dev/doujin/item/d_300002/', ld);
check('ファイルの数: コレクションのページ＋種類ごとの一覧（ページが無い種類は一覧も無し）',
  L.floorFileCount(cfl, [], cols) === cfl.items.length + 10 + (2 + 1) + (1 + 1) + (2 + 1) + (1 + 1) + (1 + 1) && L.floorFileCount(cfl, [], { genre: [], series: [], author: [], month: [] }) === cfl.items.length + 10);

// 運営者の希望「人気の動き」「セールの充実」（2026-10-09）
console.log('\n■ 人気の動き（毎日の順位の記録。data/floor_rank_history.json）');
const hpy = fs.readFileSync(new URL('../scripts/floor_history.py', import.meta.url), 'utf-8');
check('記録の深さ・日数は scripts/floor_history.py と同じ（300本・30日）',
  L.FLOOR_TREND_TRACK === Number(hpy.match(/^RANK_TRACK = (\d+)/m)[1]) && L.FLOOR_TREND_DAYS === Number(hpy.match(/^RANK_DAYS = (\d+)/m)[1]));
const RH = L.normalizeFloorRankHistory({
  updated: '2026-10-09',
  doujin: {
    d_1: { d: '2026-10-05', r: [20, 12, null, 8, 5] }, // 上がり続け（10/7 は読めなかった日）
    d_2: { d: '2026-10-07', r: [3, 4, 9] }, // 下がった
    d_3: { d: '2026-10-09', r: [40] }, // きょう初めて入った
    d_4: { d: '2026-10-06', r: [50, 0, 0, 30] }, // いちど圏外になって、また入った
    d_5: { d: '2026-10-08', r: [7, 7] }, // 同じ
    'bad cid': { d: '2026-10-09', r: [1] }, d_6: { d: 'x', r: [1] }, d_7: { d: '2026-10-09', r: [] }, d_8: { d: '2026-10-09', r: [-1, 'x'] },
  },
  game: 'こわれた',
});
check('読み込み: こわれた行は捨てる・順位は 0（圏外）と null（分からない）を区別・いちばん上の順位と日・入っていた日数',
  RH.doujin.size === 6 && !RH.doujin.has('d_6') && RH.game.size === 0 && JSON.stringify(RH.doujin.get('d_1')) === JSON.stringify({ start: '2026-10-05', n: [20, 12, null, 8, 5], best: { rank: 5, day: 4 }, daysIn: 4 })
  && JSON.stringify(RH.doujin.get('d_8').n) === '[null,null]' && RH.since.doujin === '2026-10-05', [...RH.doujin.keys()]);
check('その日の順位: 記録の外は null', L.floorRankOn(RH.doujin.get('d_1'), '2026-10-08') === 8 && L.floorRankOn(RH.doujin.get('d_1'), '2026-10-04') === null && L.floorRankOn(RH.doujin.get('d_1'), '2026-10-10') === null && L.floorRankOn(undefined, '2026-10-09') === null);
const note = (cid) => L.floorRankNote(RH.doujin.get(cid), '2026-10-09', RH.since.doujin);
check('ランキングの1行: 「前日から▲3」「前日から▼5｜最高3位」「前日と同じ」「初登場」「再登場」',
  note('d_1') === '前日から▲3' && note('d_2') === '前日から▼5｜最高3位' && note('d_5') === '前日と同じ' && note('d_3') === '初登場' && note('d_4') === '再登場' && L.floorRankNote(undefined, '2026-10-09') === '',
  ['d_1', 'd_2', 'd_3', 'd_4', 'd_5'].map(note));
check('記録を始めた日は「初登場」と書かない（みんな初めてなので）', L.floorRankNote(RH.doujin.get('d_3'), '2026-10-09', '2026-10-09') === '');
check('作品ページの文: 「FANZA同人の人気ランキングで最高5位（10月9日）・300位以内に4日（10月5日からの記録）」（記録が1日だけ・入ったことが無ければ出さない）',
  JSON.stringify(L.floorTrendLines(RH.doujin.get('d_1'), L.FLOORS.doujin)) === JSON.stringify(['FANZA同人の人気ランキングで最高5位（10月9日）・300位以内に4日（10月5日からの記録）']) && L.floorTrendLines(RH.doujin.get('d_8'), L.FLOORS.doujin).length === 0 && L.floorTrendLines(RH.doujin.get('d_3'), L.FLOORS.doujin).length === 0);
const tc = trendChart(RH.doujin.get('d_1'), { max: L.FLOOR_TREND_TRACK });
check('グラフ: いちばん下の目もりは300位（動画は500位のまま）・読めなかった日で線を切る', tc.grid.map((g) => g.rank).join() === '1,10,100,300' && trendChart(RH.doujin.get('d_1')).grid.at(-1).rank === 500 && (tc.path.match(/M/g) || []).length === 2, tc.path);
const rItems = ['d_1', 'd_2', 'd_3', 'd_4', 'd_5'].map((cid) => ({ cid, upcoming: false }));
check('きのうから人気が上がった作品: 3つ以上・1.25倍以上上がった作品だけ（圏外から・初登場は入れない）', L.floorRisers(rItems, RH.doujin, '2026-10-09').map((r) => `${r.item.cid}:${r.rise}:${r.cur}`).join() === 'd_1:3:5', L.floorRisers(rItems, RH.doujin, '2026-10-09'));

console.log('\n■ セールのページ・セールの記録');
check('名前から読める最大の割引（scripts/floor_history.py の off_in_title と同じ）', L.offInTitle('最大90%OFFセール【秋】') === 90 && L.offInTitle('30％OFF・50%OFF') === 50 && L.offInTitle('半額セール') === 50 && L.offInTitle('500円セール') === 0 && hpy.includes('OFF_IN_TITLE = re.compile(r"(\\d{1,2})\\s*[%％]\\s*(?:OFF|ＯＦＦ|オフ)")'));
const gs = L.normalizeFloor({ ranks: { g_1: 1, g_2: 2, g_3: 3, g_4: 4 }, items: [1, 2, 3, 4].map((n) => row(n, { cid: `g_${n}`, price: 500, list_price: null, campaign: null, sales: n < 4 ? ['最大90%OFFセール【秋】', '3点以上で5%OFFクーポン'] : ['500円セール【秋】'] })) }, 'game', today);
const gp = L.floorSalePages(gs.items, 'game');
check('ゲーム: 値下げのセールの札ごとのページ（3本以上。クーポンは作らない）・場所は名前から決まる印', gp.length === 1 && gp[0].name === '最大90%OFFセール【秋】' && gp[0].total === 3 && gp[0].off === 90 && gp[0].path === `/game/sale/${gp[0].slug}/` && /^[0-9a-f]{10}$/.test(gp[0].slug), gp.map((p) => [p.name, p.total]));
const gpBy = new Map(gp.map((p) => [p.slug, p]));
check('作品ページの札の行き先: ページがあればそのページ・無ければセールのページの見出し・クーポンはクーポンの欄',
  L.saleTagLink('game', '最大90%OFFセール【秋】', gpBy) === gp[0].path && L.saleTagLink('game', '500円セール【秋】', gpBy) === '/game/sale/' && L.saleTagLink('game', '3点以上で5%OFFクーポン', gpBy) === '/game/sale/#coupons');
const ds = L.normalizeFloor({ items: [95, 92, 91, 75, 72, 55, 50, 30, 10].map((off, n) => row(n + 1, { cid: `d_${400 + n}`, price: 100 - off, list_price: 100 })) }, 'doujin', today);
const dp = L.floorSalePages(ds.items, 'doujin');
check('同人: 割引ごとのページ（90%OFF以上・70%OFF以上・半額以上。3本以上）', dp.map((p) => `${p.slug}:${p.total}`).join() === 'off90:3,off70:5,off50:7' && dp[2].name === '半額以上（50%OFF〜）' && dp[2].path === '/doujin/sale/off50/', dp.map((p) => [p.slug, p.total]));
check('セールのページのタイトル', L.floorSalePageTitle(L.FLOORS.game, gp[0], '10月9日', 'サイト') === '最大90%OFFセール【秋】の対象PCゲーム一覧【10月9日更新】（3本）｜サイト'
  && L.floorSalePageTitle(L.FLOORS.doujin, dp[2], '10月9日', 'サイト') === 'FANZA同人 半額以上（50%OFF〜）のセール作品一覧【10月9日更新】（7本）｜サイト');
check('セールのページを検索エンジンに出すのは、並べる作品にコメントのある作品があるときだけ', !L.floorSalePageIndexable(dp[0]) && L.floorSalePageIndexable({ items: [{ comment: 'x' }] }));
check('同人の、いまの割引ごとの本数', JSON.stringify(L.offBands(ds.items)) === JSON.stringify([{ name: '90%OFF以上', count: 3 }, { name: '70〜89%OFF', count: 2 }, { name: '50〜69%OFF', count: 2 }, { name: '30〜49%OFF', count: 1 }, { name: '30%OFF未満', count: 1 }]));
const SH = L.normalizeFloorSaleHistory({
  updated: '2026-10-09',
  game: {
    days: [{ d: '2026-10-08', n: 260, max: 90 }, { d: '2026-10-07', n: 0, max: 0 }, { d: 'x', n: 1, max: 1 }, { d: '2026-10-06', n: 5, max: 120 }],
    tags: [
      { title: '最大90%OFFセール【秋】', begin: '', first: '2026-10-07', last: '2026-10-09', count: 264, off: 90 },
      { title: '500円セール【夏】', begin: '', first: '2026-10-01', last: '2026-10-05', count: 12, off: 0 },
      { title: '3点以上で5%OFFクーポン', begin: '', first: '2026-10-07', last: '2026-10-09', count: 478, off: 5 },
      { title: '放課後セール', begin: '', first: '2026-10-07', last: '2026-10-09', count: 3, off: 0 },
      { title: '日付がこわれた', begin: '', first: '2026-10-09', last: '2026-10-01', count: 3, off: 0 },
    ],
  },
  doujin: null,
});
check('セールの記録の読み込み: こわれた日・割引が100をこえる日・未成年を連想させる名前・日付の前後が逆の名前は捨てる・日は古い順',
  SH.game.days.map((d) => d.d).join() === '2026-10-07,2026-10-08' && SH.game.tags.length === 3 && SH.doujin.days.length === 0, SH.game);
const sf = L.floorSaleFacts(SH.game, { d: '2026-10-09', n: 264, max: 90 }, 'game');
check('「セールはいつ？」の数字: 記録の日数（きょうを足す）・セール中の作品があった日・いちばん大きい割引・いま見かけるセール（クーポンは入れない）・終わったセール',
  sf.days === 3 && sf.withSale === 2 && sf.first === '2026-10-07' && sf.last === '2026-10-09' && sf.recordMax.max === 90 && sf.recordMax.d === '2026-10-08'
  && sf.ongoing.map((t) => t.title).join() === '最大90%OFFセール【秋】' && sf.ended.map((t) => t.title).join() === '500円セール【夏】', sf);
check('記録が7日に満たないあいだは、検索エンジンに出さない', L.floorSaleHistoryDays(SH.game, '2026-10-09') === 3 && !L.floorSaleHistoryIndexable(SH.game, '2026-10-09')
  && L.floorSaleHistoryIndexable({ days: [1, 2, 3, 4, 5, 6].map((n) => ({ d: `2026-10-0${n}` })) }, '2026-10-07'));
const dc = L.floorSaleDayChart(sf.list);
check('毎日の本数のグラフ: 1日1本・高さは本数に比べて・2日に満たなければ出さない',
  dc.bars.length === 3 && dc.bars[0].bh === 0 && dc.bars[2].bh > dc.bars[1].bh * 0.99 && dc.grid.at(-1).v >= 264 && dc.ticks[0].label === '10/7' && L.floorSaleDayChart([{ d: '2026-10-09', n: 1, max: 0 }]) === null, dc);

// 運営者の希望「同人ならでは・ゲームならではのコレクション」「人気の作家さんとか独自のランキング」「ルーレット」「検索」（2026-10-09）
console.log('\n■ 同人の形式・特集（同人ならでは・ゲームならでは）');
const trow = (n, extra) => row(n, { cid: `d_${500000 + n}`, price: 1100, list_price: 1100, campaign: null, genres: [], formats: ['男性向け'], ...extra });
const img = (type, n) => `https://doujin-assets.dmm.co.jp/digital/${type}/d_${500000 + n}/d_${500000 + n}pl.jpg`;
const tfl = L.normalizeFloor({
  ranks: { d_500001: 1, d_500002: 2, d_500003: 3, d_500004: 4, d_500005: 5, d_500006: 6 },
  items: [
    trow(1, { image_url: img('voice', 1), genres: ['KU100', 'ASMR'], formats: ['男性向け', '専売', 'コミケ108（2026夏）'], price: 440 }),
    trow(2, { image_url: img('voice', 2), genres: ['KU100'], formats: ['男性向け', '専売', 'コミケ108（2026夏）'], price: 500 }),
    trow(3, { image_url: img('voice', 3), genres: ['KU100'], formats: ['男性向け', '専売', 'コミケ108（2026夏）', 'デモ・体験版あり'], price: 330 }),
    trow(4, { image_url: img('comic', 4), formats: ['男性向け', 'コミケ107（2025冬）'], date: '2024-05-01 00:00:00' }),
    trow(5, { image_url: img('comic', 5), date: '2025-10-09 00:00:00' }),
    trow(6, { image_url: img('comic', 6), date: '2025-10-10 00:00:00' }),
    trow(7, { image_url: img('cg', 7) }),
    trow(8, { image_url: 'https://evil.example/x.jpg' }),
  ],
}, 'doujin', today);
check('同人の形式は、表紙の置き場所（/digital/<形式>/）で分かる・分からなければ空', tfl.items.map((i) => i.type).join() === 'voice,voice,voice,comic,comic,comic,cg,', tfl.items.map((i) => i.type));
const tcols = L.floorCollections(tfl.items, 'doujin', today);
check('形式のページ: 3本以上の形式だけ・決めた順（コミック・CG集・音声・ゲーム）・名前', tcols.type.map((g) => `${g.slug}:${g.name}:${g.total}`).join() === 'comic:同人コミック:3,voice:同人音声・ASMR:3' && tcols.type[0].path === '/doujin/type/comic/', tcols.type.map((g) => [g.slug, g.total]));
check('特集: 決めた順 → コミケ（新しい回から）・3本以上',
  tcols.theme.map((g) => `${g.slug}:${g.total}`).join() === 'senbai:3,ku100:3,coin:3,comiket108:3' && tcols.theme.find((g) => g.slug === 'comiket108').heading === 'コミケ108（2026夏）の同人作品', tcols.theme.map((g) => [g.slug, g.total]));
check('売り場のトップの特集: いちばん新しいコミケ → 決めた順（6つまで）', L.hubThemes(tcols.theme).map((g) => g.slug).join() === 'comiket108,senbai,ku100,coin' && L.hubThemes([...tcols.theme, ...tcols.theme], 2).length === 2);
const lcols = L.floorCollections([...tfl.items, ...L.normalizeFloor({ items: [trow(9, { image_url: img('comic', 9), date: '2020-01-01 00:00:00' })] }, 'doujin', today).items], 'doujin', today);
check('ロングセラー: 発売から365日以上前の作品（2025-10-09 は入り、2025-10-10 は入らない）', lcols.theme.find((g) => g.slug === 'longseller')?.items.map((i) => i.cid).sort().join() === 'd_500004,d_500005,d_500009');
check('特集の条件は、きょうの日付が無いと日付の特集を作らない', !L.floorCollections(tfl.items, 'doujin').theme.some((g) => g.slug === 'longseller'));
check('コミケの札の読み取り', JSON.stringify(L.comiketTheme('コミケ108（2026夏）')) === JSON.stringify({ slug: 'comiket108', name: 'コミケ108（2026夏）', heading: 'コミケ108（2026夏）の同人作品', no: 108 }) && L.comiketTheme('コミケ（夏）') === null);
check('ゲームの特集の決まり（体験版・ブラウザ・Win11・独占・セット・BEST PRICE・2,000円以下・アニメーション・名作）',
  L.FLOOR_THEMES.game.map((t) => t.slug).join() === 'trial,browser,win11,dlonly,set,bestprice,budget,anime,longseller' && L.FLOOR_THEMES.doujin.map((t) => t.slug).join() === 'senbai,anime,ku100,trial,coin,longseller');
check('特集・形式の名前に、未成年を連想させる言葉が無い', [...L.FLOOR_THEMES.doujin, ...L.FLOOR_THEMES.game, ...L.DOUJIN_TYPES].every((t) => !isMinorTitle(t.name) && !isMinorTitle(t.heading ?? '')));
check('タイトル: 形式「FANZA同人 同人音声・ASMRの人気ランキング【2026年10月】（3本）」・特集「FANZA専売の同人作品【FANZA同人・2026年10月】人気順（3本）」',
  L.collectionTitle(L.FLOORS.doujin, tcols.type[1], '2026年10月', 'サイト') === 'FANZA同人 同人音声・ASMRの人気ランキング【2026年10月】（3本）｜サイト'
  && L.collectionTitle(L.FLOORS.doujin, tcols.theme[0], '2026年10月', 'サイト') === 'FANZA専売の同人作品【FANZA同人・2026年10月】人気順（3本）｜サイト');
const tl = L.collectionLinksFor(tfl.items[0], tcols);
check('作品ページから: 形式のページ・入っている特集のページへ', tl.type.slug === 'voice' && tl.themes.map((g) => g.slug).join() === 'senbai,ku100,coin,comiket108');

console.log('\n■ 人気サークル・ブランド・作家ランキング');
const eg = L.normalizeFloor({ ranks: { g_1: 1, g_2: 2, g_3: 3, g_4: 4 }, items: [
  row(1, { cid: 'g_1', maker: 'ブランドA', maker_id: 1, authors: ['作家X'] }),
  row(2, { cid: 'g_2', maker: 'ブランドB', maker_id: 2, authors: ['作家X', '作家Y'] }),
  row(3, { cid: 'g_3', maker: 'ブランドB', maker_id: 2, authors: ['作家Y'] }),
  row(4, { cid: 'g_4', maker: 'ブランドC', maker_id: 3, authors: [] }),
] }, 'game', today);
const EH = L.normalizeFloorRankHistory({ game: { g_1: { d: '2026-10-08', r: [5, 1] }, g_2: { d: '2026-10-08', r: [1, 2] }, g_3: { d: '2026-10-08', r: [2, 3] } } });
const er = L.floorEntityRanking(eg.items, 'maker', { hist: EH.game, day: '2026-10-09', pathOf: (id) => (id === '2' ? '/game/maker/2/' : '') });
check('点数: 上位300本の順位から（1位＝300点）。サークル/ブランドごとに足した順', er.map((r) => `${r.name}:${r.score}:${r.count}:${r.best}`).join() === 'ブランドB:597:2:2,ブランドA:300:1:1,ブランドC:297:1:4', er.map((r) => [r.name, r.score]));
check('前日からの動き: 前の日の順位（記録から）とくらべる・前の日にいなければ初登場', er.map((r) => L.moveLabel(r.move)).join() === '→,→,初登場' && er[0].path === '/game/maker/2/' && er[1].path === '', er.map((r) => r.move));
const ea = L.floorEntityRanking(eg.items, 'author');
check('作家: 作品の作家ごと（1作品に2人なら、それぞれに点）・記録が無ければ動きは出さない', ea.map((r) => `${r.name}:${r.score}`).join() === '作家X:599,作家Y:597' && ea.every((r) => r.move === null && L.moveLabel(r.move) === ''));
check('動きの文字', L.moveLabel(2) === '▲2' && L.moveLabel(-1) === '▼1' && L.moveLabel(0) === '→' && L.moveLabel('new') === '初登場' && L.floorEntityRankingPath('doujin', 'maker') === '/doujin/ranking/maker/');

console.log('\n■ 運命の作品・作品検索');
const gp2 = L.floorGachaPool(tfl.items);
check('運命の作品の候補: 人気の順・作品ページの場所・同人は縮めた表紙（幅240）', gp2.length === 6 && gp2[0].h === '/doujin/item/d_500001/' && gp2[0].i === 'https://awsimgsrc.dmm.co.jp/pics_dig/digital/voice/d_500001/d_500001pl.jpg?w=240&q=75' && /^https:\/\/[^/]*dmm\.co\.jp\//.test(gp2[0].i), gp2[0]);
check('ゲームの候補は表紙（…ps.jpg）', L.floorGachaPool(g.items)[0].i.endsWith('ps.jpg'));
const gacha = fs.readFileSync(new URL('../site/public/gacha.js', import.meta.url), 'utf-8');
check('public/gacha.js: 候補の場所（h）が /<売り場>/item/…/ のときだけ使う・同人/ゲームは VR・単体の絞り込みを使わない（data-nofilter）',
  gacha.includes("/^\\/[a-z]{2,10}\\/item\\/[A-Za-z0-9_-]+\\/$/.test(row.h)") && gacha.includes("hasAttribute('data-nofilter')") && G.eligible([{ c: 'a' }, { c: 'b', o: 1 }], false, false).length === 2);
const SI = L.floorSearchIndex(tfl.items, 'doujin', tcols);
check('検索の索引: 決まった形の表紙は省く・形式・特集・順位・セール・ジャンルはおだやかなものだけ',
  SI.items.length === 8 && !('i' in SI.items[0]) && SI.items.some((r) => r.c === 'd_500008' && !r.i) && SI.items[0].y === 'voice' && SI.items[0].r === 1 && SI.items[0].h.length === 4 && SI.themes[3].s === 'comiket108'
  && SI.genres.every((x) => L.FLOOR_GENRE_OK.includes(x)) && SI.types.map((t) => t.s).join() === 'comic,cg,voice' && L.floorSearchIndexPath('game') === '/data/game-index.json', SI.items[0]);
check('検索の行: ページを作るときの形（lib）とブラウザの形（public/floor-search.js）が同じ', SI.items.every((r) => JSON.stringify(Object.entries(L.floorSearchRow(r, 'doujin')).filter(([k]) => k !== 'rank')) === JSON.stringify(Object.entries(FS.rowView(r, 'doujin')))),
  [L.floorSearchRow(SI.items[0], 'doujin'), FS.rowView(SI.items[0], 'doujin')]);
const idx = { genres: SI.genres, themes: SI.themes, items: SI.items.map((r) => ({ ...r, $k: FS.norm([r.t, r.m, r.a].join(' ')) })) };
const pick = (st) => FS.filterRows(idx, { q: '', sort: 'pop', st: '', type: '', g: [], h: [], ...st }).sort(FS.SORTS[st.sort || 'pop']).map((r) => r.c.slice(-1)).join('');
check('検索の絞り込み: 形式・特集（複数は全部）・キーワード（全角・半角をそろえる）・並び順', pick({ type: 'voice' }) === '123' && pick({ h: [0, 3] }) === '123' && pick({ g: [0], h: [0] }) === '1' && pick({ q: 'ＳＡＫＵ' }) === '' && pick({ q: 'その1' }) === '1' && pick({ sort: 'cheap' }).startsWith('312'), [pick({ type: 'voice' }), pick({ h: [0, 3] }), pick({ sort: 'cheap' })]);
check('検索のスマホの表紙: 同人は縮めた版（幅240）・ゲームは表紙（…ps.jpg）', FS.thumbUrl('doujin', 'https://pics.dmm.co.jp/digital/voice/x/xpl.jpg', true) === 'https://awsimgsrc.dmm.co.jp/pics_dig/digital/voice/x/xpl.jpg?w=240&q=75' && FS.thumbUrl('doujin', 'https://pics.dmm.co.jp/digital/voice/x/xpl.jpg', false).startsWith('https://pics.') && FS.thumbUrl('game', 'https://pics.dmm.co.jp/digital/pcgame/x/xpl.jpg', true).endsWith('xps.jpg') && FS.PAGE === L.FLOOR_SEARCH_PAGE);

// 運営者の希望「動画のページと、ほぼ同じ要領で同人とゲームも」（2026-10-09）: 売り場のトップの TOP3 の動き・きょうの話題
console.log('\n■ 売り場のトップ（TOP3 の動き・きょうの話題）');
check('TOP3 の前の日からの動き（動画の rankMove と同じ形）: ▲・▼・→・初登場・記録が無ければ出さない',
  JSON.stringify(['d_1', 'd_2', 'd_5', 'd_3', 'd_4'].map((c) => L.floorMove(RH.doujin.get(c), '2026-10-09', RH.since.doujin)?.text ?? null)) === JSON.stringify(['▲3', '▼5', '→', '初登場', '初登場'])
  && L.floorMove(undefined, '2026-10-09') === null && L.floorMove(RH.doujin.get('d_3'), '2026-10-09', '2026-10-09') === null);
const tp = L.floorTopics([...rItems.map((x) => ({ ...cfl.items[0], ...x, upcoming: false })), ...g.items], RH.doujin, '2026-10-09');
check('きょうの話題: 急上昇 → 新作で人気 → セールで人気（同じ作品は1回だけ・データで決まった文）', tp[0]?.label === '急上昇' && tp[0].text === '人気ランキング5位（前日から▲3）' && new Set(tp.map((t) => t.item.cid)).size === tp.length && tp.every((t) => t.kind && t.text), tp.map((t) => [t.label, t.text]));

console.log('\n■ 新しい売り場（アニメ・素人・成人映画・コミック・写真集・VR見放題。2026-10-10）');
const pyFloors = fs.readFileSync(new URL('../scripts/floor_data.py', import.meta.url), 'utf-8');
const pyKeys = [...pyFloors.matchAll(/^    "([a-z]+)": \{$/gm)].map((m) => m[1]);
check('売り場は、集める道具（scripts/floor_data.py の FLOORS）と同じ・同じ順', pyKeys.join() === L.FLOOR_KEYS.join() && L.FLOOR_KEYS.length === 8, [pyKeys.join(), L.FLOOR_KEYS.join()]);
check('どの売り場も、名前・短い名前・作り手の呼び方・数える言葉・作品の呼び方・枠の形・大きな表紙の形がある',
  L.FLOOR_KEYS.every((k) => ['label', 'short', 'maker', 'makerUnit', 'kind'].every((x) => L.FLOORS[k][x]) && ['wide', 'square', 'cover'].includes(L.FLOORS[k].frame) && ['wide', 'square', 'spread', 'tall'].includes(L.FLOORS[k].detail)));
check('枠の印: 同人は横長・素人は正方形（横長の札の置き方を使う）・ほかは縦長', JSON.stringify(L.frameClass('doujin')) === '{"is-wide":true,"is-square":false}'
  && JSON.stringify(L.frameClass('amateur')) === '{"is-wide":true,"is-square":true}' && JSON.stringify(L.frameClass('vr')) === '{"is-wide":false,"is-square":false}' && L.isFramed('amateur') && !L.isFramed('comic'));
check('検索の欄の案内', L.floorSearchHint('doujin') === 'タイトル・サークル' && L.floorSearchHint('game') === 'タイトル・ブランド・作家' && L.floorSearchHint('vr') === 'タイトル・メーカー・出演者' && L.floorSearchHint('photo') === 'タイトル・出版社・作家・出演者');
const nrow = (cid, extra = {}) => ({ cid, title: `作品${cid}`, url: 'https://al.fanza.co.jp/?x', image_url: `https://pics.dmm.co.jp/digital/video/${cid}/${cid}pl.jpg`, date: '2026-09-01 10:00:00', maker: 'M', maker_id: 1, price: 1980, list_price: 2980, ...extra });
const vrF = L.normalizeFloor({ items: [nrow('v1', { actress: ['出演A', '出演B', '出演C'], sample_movie: 'https://www.dmm.co.jp/litevideo/x/', trial_url: 'https://example.com/' }), nrow('v2', { actress: ['女子校生A'] })], ranks: { v1: 1 } }, 'vr', '2026-10-10');
const v1 = vrF.items[0];
check('出演者・サンプル動画（DMM のだけ）・立ち読み（FANZAのだけ）を読む・見放題は価格を出さない・出演者の名前でも未成年を連想させる作品は外す',
  vrF.items.length === 1 && v1.actress.join() === '出演A,出演B,出演C' && v1.sampleMovie.startsWith('https://www.dmm.co.jp/') && v1.trialUrl === '' && v1.price === null && v1.off === 0, v1);
check('カードの1行: 出演者のいる売り場は出演者を先に2人まで（ほか○名）', L.makerLine(v1) === '出演A、出演B ほか1名｜M' && L.makerLine({ ...v1, floor: 'anime', actress: [] }) === 'M');
const amF = L.normalizeFloor({ items: [nrow('a1', { image_url: 'https://pics.dmm.co.jp/digital/amateur/a1/a1jp.jpg' })], ranks: { a1: 1 } }, 'amateur', '2026-10-10');
check('素人の運命の作品・検索の行: 正方形の表紙を縮めた版・検索の索引にはいつも画像', L.floorGachaPool(amF.items)[0].i === 'https://awsimgsrc.dmm.co.jp/pics_dig/digital/amateur/a1/a1jp.jpg?w=240&q=75'
  && L.floorSearchIndex(amF.items, 'amateur', {}).items[0].i === amF.items[0].image_url && L.floorSearchRow(L.floorSearchIndex(amF.items, 'amateur', {}).items[0], 'amateur').square === true
  && JSON.stringify(FS.rowView(L.floorSearchIndex(amF.items, 'amateur', {}).items[0], 'amateur', 'square')) === JSON.stringify(Object.fromEntries(Object.entries(L.floorSearchRow(L.floorSearchIndex(amF.items, 'amateur', {}).items[0], 'amateur')).filter(([k]) => k !== 'rank'))));
check('ブックスの表紙: スマホの小さな表紙は表紙の小さい版（ebook-assets の …ps.jpg）', FS.thumbUrl('comic', 'https://ebook-assets.dmm.co.jp/digital/e-book/b1/b1pl.jpg', true, 'cover').endsWith('b1ps.jpg'));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
