// 10円セールの部品（site/src/lib/ten-yen.js）のテスト。実行: node tests/test_ten_yen.mjs
// （作品・名前は、どれも作ったもの）
import { execFileSync } from 'node:child_process';
import * as T from '../site/src/lib/ten-yen.js';
import { isTenYenCampaign } from '../site/src/lib/sale.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

const video = (n, extra = {}) => ({
  cid: `abc${n}`, title: `作った動画${n}`, url: `https://al.fanza.co.jp/?lurl=x${n}`, image_url: `https://pics.dmm.co.jp/digital/video/abc${n}/abc${n}pl.jpg`,
  date: '2024-05-01 10:00:00', maker: 'メーカー', actress: ['女優'], genres: ['単体作品'], tags: [], price: 10, list_price: 2980,
  sale_title: '10円セール第1弾', sale_end: '2026-10-11 09:59', ...extra,
});
const floor = (n, key = 'doujin', extra = {}) => ({
  cid: key === 'doujin' ? `d_${n}` : `brand_${n}`, title: `作った作品${n}`, url: `https://al.fanza.co.jp/?lurl=y${n}`,
  image_url: `https://pics.dmm.co.jp/digital/${key === 'doujin' ? 'comic' : 'pcgame'}/c${n}/c${n}pl.jpg`, date: '2025-01-10 00:00:00',
  maker: `サークル${n}`, maker_id: 300 + n, authors: [], series: '', series_id: 0, genres: ['巨乳'], formats: [], sales: [],
  price: 10, list_price: 1100, sale_title: '', sale_end: '', rank: n, ...extra,
});
const raw = {
  checked: '2026-10-09 10:15',
  video: [video(1, { list_price: 1980 }), video(2), video(3, { sale_end: '2026-10-09 09:59' }), video(4, { title: '放課後のなにか' }), video(5, { price: 20 }), video(6, { date: '2026-12-01 10:00:00' })],
  doujin: [floor(7), floor(3, 'doujin', { list_price: null }), floor(9, 'doujin', { title: '制服のなにか' })],
  game: [],
  runs: [
    { floor: 'video', first: '2026-10-09', last: '2026-10-09', count: 3, end: '2026-10-11 09:59', titles: ['10円セール第1弾'] },
    { floor: 'doujin', first: '2026-10-09', last: '2026-10-09', count: 2, end: '', titles: [] },
    { floor: 'video', first: '2026-09-12', last: '2026-09-18', count: 10, end: '2026-09-19 09:59', titles: ['10円セール'] },
    { floor: 'x', first: '2026-01-01', last: '2026-01-01' }, { floor: 'game', first: '2026-02-02', last: '2026-02-01' },
  ],
};
const mine = { ...video(2), cid: 'abc2', comment: 'このサイトのひとこと', popAll: 5, popNew: null };
const ty = T.normalizeTenYen(raw, { today: '2026-10-09', videoByCid: new Map([['abc2', { ...mine, dateKey: '2024-05-01' }]]), floorByCid: { doujin: new Map(), game: new Map() } });

console.log('■ ten_yen.json の読み方');
check('動画: 10円で、確かめた時刻より前に終わっていない・発売済み・未成年を連想させない作品だけ（このサイトの作品の形を使い、人気の高い順）',
  ty.items.video.map((i) => i.cid).join() === 'abc2,abc1' && ty.items.video[0].comment === 'このサイトのひとこと', ty.items.video.map((i) => i.cid).join());
check('作品に10円の情報（定価・割引・セールの名前・終わり）', ty.items.video[1].tenYen.listPrice === 1980 && ty.items.video[1].tenYen.off === 99
  && ty.items.video[1].tenYen.title === '10円セール第1弾' && ty.items.video[1].tenYen.end === '2026-10-11 09:59');
check('同人: 人気順・作品ページの有無・定価が分からなければ割引も無し', ty.items.doujin.map((i) => i.cid).join() === 'd_3,d_7' && ty.items.doujin.every((i) => i.hasPage === false)
  && ty.items.doujin[0].tenYen.listPrice === null && ty.items.doujin[0].tenYen.off === null, ty.items.doujin.map((i) => i.cid).join());
check('開催の記録: 形の違う行は捨てる・新しい順', ty.runs.length === 3 && ty.runs[0].floor === 'video' && ty.runs[2].first === '2026-09-12');
check('無い・形が違うときは空', [null, undefined, [], 'x', { video: 'x', runs: {} }].every((v) => { const e = T.normalizeTenYen(v); return e.checked === '' && T.TEN_YEN_KEYS.every((k) => e.items[k].length === 0) && e.runs.length === 0; }));

console.log('\n■ いまの様子・ページの文');
const st = T.tenYenState(ty);
check('開催中の売り場・本数・終わり（全部の作品の終わりが分かるときだけ）', st.live.join() === 'video,doujin' && st.total === 4 && st.end === '' && st.sameEnd === '');
const stv = T.tenYenState(ty, ['video']);
check('売り場を絞ると、その売り場だけ（全部の終わりが同じなら、その日時）', stv.total === 2 && stv.end === '2026-10-11 09:59' && stv.sameEnd === '2026-10-11 09:59' && T.untilText(stv) === '10月11日 9:59まで' && T.hideAt(stv) === '2026-10-11T09:59:59+09:00');
check('本数の文', T.countsText(st) === '動画2本・同人2本');
check('タイトル（開催中）: 「FANZA 10円セール開催中｜対象○本【○月○日更新】」', T.tenYenTitle(ty) === 'FANZA 10円セール開催中｜対象4本【10月9日更新】', T.tenYenTitle(ty));
const empty = T.normalizeTenYen({ ...raw, video: [], doujin: [] });
check('タイトル（開催していない）: 「FANZA 10円セールはいつ？…【2026年10月】」・売り場のページ', T.tenYenTitle(empty) === 'FANZA 10円セールはいつ？開催状況と対象作品【2026年10月】'
  && T.tenYenTitle(empty, 'doujin') === 'FANZA同人の10円セールはいつ？開催状況と対象作品【2026年10月】', T.tenYenTitle(empty));
check('説明文に、本数・確かめた時刻／前回の開催', T.tenYenDescription(ty).includes('動画2本・同人2本') && T.tenYenDescription(ty).includes('10月9日 10:15の時点')
  && T.tenYenDescription(empty).includes('前回は10月9日に見かけました（動画）'), T.tenYenDescription(empty));
check('検索エンジンに出すか: まとめのページはいつも・売り場のページは開催中か記録があるときだけ',
  T.tenYenIndexable(empty) && T.tenYenIndexable(empty, 'doujin') && !T.tenYenIndexable(empty, 'game') && !T.tenYenIndexable(T.normalizeTenYen({}), 'doujin'));
const faq = T.tenYenFaq(ty);
check('よくある質問: いま開催中（本数）・いつまで・前回（いまの回は除く）・次は分からない・探し方',
  faq.length === 5 && faq[0].key === '4本' && faq[1].a.includes('動画は10月11日 9:59まで') && faq[2].key === '9月12日〜9月18日' && faq[3].a.includes('分かりません'), JSON.stringify(faq.map((f) => f.key)));
const faqOff = T.tenYenFaq(T.normalizeTenYen({ checked: '2026-10-09 10:15' }));
check('記録が無いときの答え・予想の言葉を使わない', faqOff[0].key === 'なし' && faqOff[1].a.includes('まだありません')
  && ![...faq, ...faqOff].some((f) => /予想|見込み|はず|おそらく|たぶん|予定です/.test(f.a)));
check('FAQPage の構造化データ', T.faqLd(faq).mainEntity.length === 5 && T.faqLd(faq).mainEntity[0].acceptedAnswer.text === faq[0].a);
check('カードの1行', T.tenYenNote(ty.items.video[1]) === '10円（通常1,980円）' && T.tenYenNote(ty.items.doujin[0]) === '10円');

console.log('\n■ 案内の表紙・リンク');
const covers = T.heroCovers(ty, ['doujin', 'video'], 3);
check('表紙は、売り場から1本ずつ順番に（先に並べる売り場から）', covers.map((i) => i.cid).join() === 'd_3,abc2,d_7', covers.map((i) => i.cid).join());
check('作品ページがあれば作品ページ、無ければFANZAへ', T.tenYenHref(ty.items.doujin[0], new Set()).external === true && T.tenYenHref({ ...ty.items.doujin[0], hasPage: true }, new Set()).href === '/doujin/item/d_3/'
  && T.tenYenHref(ty.items.video[0], new Set(['abc2'])).href === '/item/abc2/');
check('ページのURL', T.tenYenPath() === '/sale/10yen/' && T.tenYenPath('doujin') === '/doujin/sale/10yen/' && T.tenYenPath('game') === '/game/sale/10yen/');
const names = ['10円セール第1弾', '１０円セール', '【10円】作品', '100円セール', '110円セール', '1,010円均一', '30％OFF'];
check('10円セールの特集の見分け（全角の「１０円」も。「110円」「1,010円」は入れない）・集める道具と同じ',
  names.map(isTenYenCampaign).join() === 'true,true,true,false,false,false,false'
  && JSON.parse(execFileSync('python3', ['-c', `import sys,json; sys.path.insert(0,"scripts"); import ten_yen as T; print(json.dumps([T.has_ten_yen(n) for n in json.loads(sys.argv[1])]))`, JSON.stringify(names)], { encoding: 'utf-8' })).join() === names.map(isTenYenCampaign).join());

console.log('\n■ 集める道具（scripts/ten_yen.py）との突き合わせ');
const py = JSON.parse(execFileSync('python3', ['-c', 'import sys,json; sys.path.insert(0,"scripts"); import ten_yen as T; print(json.dumps({"price": T.PRICE, "keys": list(T.FLOOR_KEYS)}))'], { encoding: 'utf-8' }));
check('10円・売り場の並びが同じ', py.price === T.TEN_YEN_PRICE && py.keys.join() === T.TEN_YEN_KEYS.join());

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
