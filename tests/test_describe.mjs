// 検索結果に出る説明文（meta description）の部品のテスト（site/src/lib/describe.js。2026-10-26 司令塔の連絡 C-003）
// 実行: node tests/test_describe.mjs
import * as D from '../site/src/lib/describe.js';

let passed = 0;
let failed = 0;
function check(name, cond, detail = '') {
  if (cond) {
    passed += 1;
    console.log(`  ✅ ${name}`);
  } else {
    failed += 1;
    console.log(`  ❌ ${name}${detail !== '' ? `  → ${JSON.stringify(detail)}` : ''}`);
  }
}

// 使わない言葉（site-principles.md の「文章」。scripts/claude_comments.py の AI_STYLE_WORDS と同じもの＋お得）
const BANNED = /おすすめ|オススメ|お得|ぜひ|是非|便利|簡単|安心|コツ|しましょう|ポイント|——/;
const ok = (s) => D.descLength(s) >= D.DESC_MIN && D.descLength(s) <= D.DESC_MAX && !BANNED.test(s);

console.log('■ 部品');
check('値段の幅: 0円→無料・10円→10円・580円→500円台・1,980円→1,000円台・12,800円→12,000円台・分からない→空', [0, 10, 580, 1980, 12800, null, -1, 'x'].map(D.priceBand).join('|') === '無料|10円|500円台|1,000円台|12,000円台|||');
check('収録時間: 45分・2時間・2時間5分・24時間2分・分からない→空', [45, 120, 125, 1442, null, 0].map(D.durationJp).join('|') === '45分|2時間|2時間5分|24時間2分||');
check('期間: 同じ日・同じ月・同じ年・年をまたぐ（逆の順でもよい）',
  D.dayRangeJp('2026-10-24', '2026-10-24') === '2026年10月24日' && D.dayRangeJp('2026-10-25', '2026-10-24') === '2026年10月24日〜25日'
  && D.dayRangeJp('2026-09-30', '2026-10-01') === '2026年9月30日〜10月1日' && D.dayRangeJp('2025-12-31', '2026-01-01') === '2025年12月31日〜2026年1月1日');
check('文をつなぐ: 先頭の文は必ず（長ければ切る）・あとの文は入るものだけ', D.fit(['あ'.repeat(130)]).length === 120 && D.fit(['あ'.repeat(100), 'い'.repeat(30), 'う'.repeat(10)]) === 'あ'.repeat(100) + 'う'.repeat(10));
check('多い順の名前（「不明」は数えない・同じ数なら先に出たもの）', D.topNames(['A', 'B', 'B', '不明', '不明', '不明', 'C'], 2).join() === 'B,A');
check('だれの作品か: 出演者とメーカー・出演者だけ・メーカーだけ・どちらも無い',
  D.whoMade({ actress: ['桐谷エマ', 'x'], maker: 'エスワン' }) === '桐谷エマさん出演のエスワン作品' && D.whoMade({ actress: ['花子'], maker: '不明' }) === '花子さんの出演作品'
  && D.whoMade({ actress: [], maker: 'S1' }) === 'S1の作品' && D.whoMade({ actress: [], maker: '不明' }) === '');

check('おだやかな名前: ブランド名は入れる・行為や暴力・未成年を連想させる言葉を含む名前は入れない',
  D.calmName('ながえSTYLE') && D.calmName('エスワン') && !D.calmName('婦女暴行') && !D.calmName('痴漢電車') && !D.calmName('女子校生シリーズ') && !D.calmName('') && !D.calmName(null));
check('動画のジャンル: ジャンルのページがあるもの・形式だけ（上から3つ）',
  D.calmVideoGenres(['ハイビジョン', 'パイズリ', '巨乳', '中出し', '単体作品', 'OL']).join() === 'ハイビジョン,巨乳,単体作品' && D.calmVideoGenres(['姉・妹', 'フェラ']).length === 0);
check('多い順の名前・だれの作品か: おだやかでない名前のメーカーは出さない',
  D.topNames(['痴漢電車', '痴漢電車', 'S1'], 2).join() === 'S1' && D.whoMade({ actress: ['花子'], maker: '痴漢電車' }) === '花子さんの出演作品');

const it = (n, dateKey, extra = {}) => ({ cid: `abc${n}`, dateKey, maker: `メーカー${n % 3}`, actress: [`女優${n % 4}`], vr: n % 5 === 0, ...extra });
const released = [it(1, '2026-10-26'), it(2, '2026-10-26'), it(3, '2026-10-25'), it(4, '2026-10-24')];

console.log('\n■ トップ');
const home = D.homeDescription({ today: '2026-10-26', released, upcomingShown: 60, upcomingLast: '2026-11-22', top1: { actress: ['桐谷エマ'], maker: 'エスワン ナンバーワンスタイル' }, topIsNew: true, saleCount: 8 });
check('トップ: 更新日・きょう発売の本数・予約受付中の本数と最後の発売日・人気1位・セール中の特集の数・80〜120文字・使わない言葉なし',
  home.startsWith('10月26日更新。きょう発売のFANZA新作2本と、11月22日発売分までの予約受付中60本を発売日ごとに並べています。新着の人気1位は桐谷エマさん出演のエスワン ナンバーワンスタイル作品で、セール中の特集は8件です。') && ok(home), [home, D.descLength(home)]);
const homeOld = D.homeDescription({ today: '2026-10-27', released, upcomingShown: 0, top1: { actress: [], maker: 'S1' }, topIsNew: false, saleCount: 0 });
check('トップ: きょうの発売が無ければ、いちばん新しい発売日・予約が無い・売れ筋の1位', homeOld.includes('10月26日発売のFANZA新作2本を') && homeOld.includes('FANZAの売れ筋の1位はS1の作品です。') && !homeOld.includes('予約'), homeOld);
check('トップ: 日がちがえば説明文もちがう（同じ説明文を量産しない）', home !== D.homeDescription({ today: '2026-10-27', released: [it(9, '2026-10-27'), ...released], upcomingShown: 59, upcomingLast: '2026-11-23', top1: { actress: ['A'], maker: 'B' }, saleCount: 7 }));

console.log('\n■ 新着の人気ランキング');
const list = Array.from({ length: 100 }, (_, i) => it(i + 1, '2026-10-24'));
const rk = D.rankingDescription({ date: '2026-10-25', list });
check('ランキング: 日付・本数・1位・VR作品の本数・80〜120文字', rk === '10月25日の新着の人気順です。最近1週間に発売されたFANZA動画の新作から上位100本を並べています。1位は女優1さん出演のメーカー1作品で、100本のうちVR作品は20本です。' && ok(rk), [rk, D.descLength(rk)]);
check('ランキング: 空でも文になる', D.rankingDescription({ date: '2026-10-25', list: [] }).startsWith('10月25日の新着の人気順です。'));

console.log('\n■ 過去の作品の一覧');
const page2 = [it(1, '2026-10-25', { maker: 'アリーナエンターテインメント', actress: ['尾崎えりか'] }), it(2, '2026-10-24', { maker: 'million', actress: ['白羽舞菜'] }), it(3, '2026-10-24', { maker: 'アリーナエンターテインメント', actress: ['尾崎えりか', '白羽舞菜'] }), it(4, '2026-10-24', { maker: '不明', actress: [] })];
const ar = D.archiveDescription(page2, 2, 474);
check('過去の作品: 期間・本数・ページ・多いメーカー・多い出演者', ar === '2026年10月24日〜25日に発売されたFANZA動画4本の一覧です（2ページ目・全474ページ）。メーカーはアリーナエンターテインメントやmillionなど、出演は尾崎えりかさん、白羽舞菜さんほか。', ar);
check('過去の作品: ページごとに違う（期間・ページが変わる）', ar !== D.archiveDescription(page2.slice(1), 3, 474));

console.log('\n■ 一覧のページ');
const months = [{ ym: '2026-09', name: '2026年9月', items: Array(300) }, { ym: '2026-11', name: '2026年11月', items: Array(62) }, { ym: '2026-10', name: '2026年10月', items: Array(410) }];
const mi = D.monthIndexDescription(months);
check('月ごと: か月数・期間・いちばん新しい月の本数・いちばん多い月の本数・80〜120文字', mi === 'FANZA動画の新作と予約作品を、発売月ごとに3か月分まとめています（2026年9月〜2026年11月）。いちばん新しい2026年11月は62本、いちばん多い2026年10月は410本です。' && ok(mi), [mi, D.descLength(mi)]);
const tags = [{ name: 'ハイビジョン', items: Array(2345) }, { name: '巨乳', items: Array(800) }, { name: '単体作品', items: Array(1200) }, { name: 'VR', items: Array(10) }];
const ti = D.tagIndexDescription(tags);
check('ジャンル: 件数・多い順の上から3つと本数・80〜120文字', ti === 'FANZA動画の作品を、ジャンルごとに4件まとめた一覧です。作品がいちばん多いのはハイビジョン（2,345本）で、単体作品（1,200本）、巨乳（800本）と続きます。' && ok(ti), [ti, D.descLength(ti)]);
const wi = D.weeklyIndexDescription([{ week_start: '2026-10-19', facts: { total: 88 } }, { week_start: '2026-10-12', facts: { total: 70 } }]);
check('週のまとめ: 記事の数・いちばん新しい週の期間と本数・80〜120文字', wi === 'FANZA動画の新作を1週間ごとにまとめた記事2本の一覧です。いちばん新しいのは10月19日〜10月25日の週で、88本の新作をふり返っています。毎週月曜に、先週の分を足します。' && ok(wi), [wi, D.descLength(wi)]);
const ev = D.eventIndexDescription([{ date: '2026-10-26', kind: 'サイン会' }, { date: '2026-11-08', kind: '撮影会' }, { date: '2026-10-30', kind: 'サイン会' }]);
check('イベント: 件数・期間・多い種類・80〜120文字', ev === '所属事務所の公式サイトに載っている女優のイベント3件を、日付ごとにまとめています（10月26日〜11月8日）。サイン会が2件、撮影会が1件です。毎日、日付が変わったあとに更新します。' && ok(ev), [ev, D.descLength(ev)]);
const ac = D.actressIndexDescription({ total: 10480, withSize: 3210, agencies: 12 });
check('女優検索: 人数・体型の分かる人数・事務所の数・80〜120文字', ac.startsWith('FANZAのAV女優10,480人を、名前・年齢・身長・スリーサイズ・カップで探せます。スリーサイズの分かる3,210人は、体型でも絞り込めます。') && ok(ac), [ac, D.descLength(ac)]);
check('どの一覧も、データが空のときにも文になる（使わない言葉なし）',
  [D.monthIndexDescription([]), D.tagIndexDescription([]), D.weeklyIndexDescription([]), D.eventIndexDescription([]), D.actressIndexDescription()].every((s) => s.length > 20 && !BANNED.test(s)));

console.log(`\n=== ${passed}/${passed + failed} 合格 ===`);
process.exit(failed ? 1 : 0);
