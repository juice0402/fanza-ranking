// 品番・作品ページの「この作品のデータ」欄・月ごとのページ・ジャンルのページの部品のテスト。
// 実行: node tests/test_seo.mjs （site/src/lib/facts.js・collections.js・items.js の itemPageTitle など）
import * as F from '../site/src/lib/facts.js';
import * as C from '../site/src/lib/collections.js';
import * as L from '../site/src/lib/items.js';
import fs from 'node:fs';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

console.log('■ 品番');
const code = F.productCode;
check('先頭の「1」とメーカーの記号・5桁の番号 → 品番（1dldss00566 → DLDSS-566）', code('1dldss00566') === 'DLDSS-566', code('1dldss00566'));
check('先頭に何も付かない形も読める。番号は先頭の0を除いて3桁にそろえる（bibivr00176 → BIBIVR-176、sqte00721 → SQTE-721）', code('bibivr00176') === 'BIBIVR-176' && code('sqte00721') === 'SQTE-721');
check('4桁の番号はそのまま（vrkm01942 → VRKM-1942、parathd04568 → PARATHD-4568）', code('vrkm01942') === 'VRKM-1942' && code('parathd04568') === 'PARATHD-4568');
check('0が多い番号も3桁にそろう（…00009 → 009）。h_1234 の形の先頭も読める（h_1758jjgg00009 → JJGG-009）', code('xyz00009') === 'XYZ-009' && code('h_1758jjgg00009') === 'JJGG-009' && code('h_1732orecs00701') === 'ORECS-701');
check('先頭が15・118 のような数字でも読める（15ald00063 → ALD-063）', code('15ald00063') === 'ALD-063' && code('118abp00123') === 'ABP-123');
check('大文字が混ざっていても同じ', code('1DLDSS00566') === 'DLDSS-566');
check('最後に英字が付くもの（1sun00072a・15ald00063ai）は、確実に読めないので作らない', code('1sun00072a') === '' && code('15ald00063ai') === '');
check('英字が1文字のもの・数字が混ざる記号・番号が桁の範囲外のものは作らない', code('h_1651y00444') === '' && code('h_113h113gl00010ai') === '' && code('h_1651kist0700004') === '' && code('abc12') === '' && code('abc123456') === '');
check('空・数字だけ・変な値でも落ちずに ""', code('') === '' && code(null) === '' && code(undefined) === '' && code('12345') === '' && code(12345) === '');
check('品番にURLや記号は入らない（英大文字・ハイフン・数字だけ）', /^[A-Z]+-\d{3,5}$/.test(code('1dldss00566')) && code('dss/../00123') === '');

const mk = (o) => L.normalizeItems([{ title: 'テスト', date: '2026-11-01', maker: 'メーカーA', ...o }])[0];
check('タイトルの先頭に品番が付く。無いときは従来どおり', L.itemPageTitle(mk({ cid: 'a1', actress: ['花子'] }), 'DLDSS-566').startsWith('DLDSS-566 テスト（花子）') && L.itemPageTitle(mk({ cid: 'a1', actress: ['花子'] })) === 'テスト（花子）｜' + L.SITE_NAME);
const longTitle = mk({ cid: 'a1', title: 'あ'.repeat(80), actress: ['花子', '月子', '星子'] });
check('長いタイトルは、品番があっても、切って「…」にする（出演者は2人まで）', [...L.itemPageTitle(longTitle, 'ABC-123')].length <= 12 + 38 + 8 + L.SITE_NAME.length + 2 && L.itemPageTitle(longTitle, 'ABC-123').includes('（花子・月子）') && L.itemPageTitle(longTitle, 'ABC-123').includes('…'), L.itemPageTitle(longTitle, 'ABC-123'));
const named = mk({ cid: 'a1', title: '新作 小泉玖美 デビュー', actress: ['小泉玖美', '月子'] });
check('タイトルに名前が入っている出演者は、かっこの中にくり返さない', L.itemPageTitle(named, 'ABC-123') === `ABC-123 新作 小泉玖美 デビュー（月子）｜${L.SITE_NAME}` && L.itemPageTitle(mk({ cid: 'a1', title: '小泉玖美 新作', actress: ['小泉玖美'] })) === `小泉玖美 新作｜${L.SITE_NAME}`, L.itemPageTitle(named, 'ABC-123'));
const desc = L.itemPageDescription(mk({ cid: 'a1', comment: 'コメントです。' }), 'DLDSS-566');
check('説明文に品番が入り、120文字を超えない', desc.includes('品番 DLDSS-566') && [...desc].length <= 120 && !L.itemPageDescription(mk({ cid: 'a1', comment: 'コメント' })).includes('品番'), desc);

console.log('\n■ 「この作品のデータ」欄');
const raw = JSON.parse(fs.readFileSync(new URL('./fixtures/items.json', import.meta.url), 'utf-8'));
const fixture = L.normalizeItems(raw);
const many = [];
for (let i = 0; i < 14; i++) {
  many.push(mk({ cid: `t${String(i).padStart(2, '0')}0000${i}`, date: i < 4 ? '2026-11-01' : '2026-11-0' + (2 + (i % 5)), maker: i % 2 ? 'メーカーA' : 'メーカーB', actress: i === 0 ? ['花子', '月子', '星子', '海子', '空子'] : i < 6 ? ['花子'] : ['月子'], duration_min: 60 + i * 10, tags: i === 3 ? ['VR'] : [] }));
}
many.push(mk({ cid: 'noinfo', date: '2026-12-24', maker: '不明', actress: [] }));
const ctx = F.buildFactsContext(many);
const first = many[0];
const pages = { month: (d) => `/month/${d.slice(0, 7)}/#day-${d}`, maker: new Map([['メーカーA', '/maker/aaa/']]), actress: new Map([['花子', '/actress/bbb/']]), vr: '/tag/vr/' };
const rows = F.itemFacts(first, ctx, pages);
const dayRow = rows[0];
const sameDay = many.filter((i) => i.dateKey === first.dateKey).length;
check('先頭の行は「同じ発売日」。その日の本数が、データを数えた値と同じ', dayRow.key === 'day' && dayRow.text.includes(`2026年11月1日発売の作品は、掲載中で${sameDay}本あります。`), dayRow.text);
check('同じ日・同じメーカーの本数も出す（2本以上のとき）', dayRow.text.includes('そのうちメーカーBの作品は') && dayRow.text.includes('本です。'), dayRow.text);
check('月のページがあれば、その日の位置（#day-…）へのリンクがつく。無ければリンクなし', dayRow.href === '/month/2026-11/#day-2026-11-01' && !('href' in F.itemFacts(first, ctx, {})[0]));
const actressRows = rows.filter((r) => r.key === 'actress');
const onceRow = rows.find((r) => r.key === 'actress-once');
check('出演者は、先頭から3人まで。掲載が2本以上の人は1人ずつの行、この1本だけの人は1つの行にまとめ、ほかは「ほか○名」', actressRows.length === 2 && onceRow && onceRow.text === '星子さん出演の作品は、掲載中ではこの1本です。ほか2名が出演しています。' && !rows.some((r) => r.key === 'cast-more'), JSON.stringify(rows.map((r) => [r.key, r.text])));
const twoOnce = F.itemFacts(mk({ cid: 'zz1', date: '2026-11-03', actress: ['一花', '二葉'] }), F.buildFactsContext([...many, mk({ cid: 'zz1', date: '2026-11-03', actress: ['一花', '二葉'] })]), {});
check('この1本だけの人が2人なら「どちらも」、3人なら「いずれも」の1行', twoOnce.find((r) => r.key === 'actress-once').text === '一花さん・二葉さんは、出演作品の掲載がどちらもこの1本です。', JSON.stringify(twoOnce));
const hanako = actressRows[0];
const hanakoCount = many.filter((i) => i.actress.includes('花子')).length;
check('出演者の行: 掲載本数と発売日の幅が、データを数えた値と同じ。ページがある人だけリンク', hanako.text.includes(`花子さん出演の作品は、掲載中で${hanakoCount}本あります（発売日は2026年11月1日から`) && hanako.href === '/actress/bbb/' && !('href' in actressRows[1]));
const makerRow = rows.find((r) => r.key === 'maker');
check('メーカーの行: 掲載本数。ページがあるメーカーだけリンク', makerRow.text.includes(`メーカーBの作品は、掲載中で${many.filter((i) => i.maker === 'メーカーB').length}本あります`) && !('href' in makerRow) && F.itemFacts(many[1], ctx, pages).find((r) => r.key === 'maker').href === '/maker/aaa/');
const only = F.itemFacts(many[many.length - 1], ctx, pages);
check('メーカー不明・出演者なし・収録時間なしの作品でも、「同じ発売日」の行は出る（この日はこの1本だけ）', only.length === 1 && only[0].text === '2026年12月24日発売の作品は、この1本だけです。', JSON.stringify(only));
const withDur = rows.find((r) => r.key === 'duration');
check('収録時間の行: 収録時間が分かる作品の中での順位（長いほうから○番目）。収録時間が分かる作品が10本未満なら出さない', withDur && withDur.text.includes(`収録時間が分かる掲載作品${ctx.durations.length}本の中では、短いほうから1番目`) && !F.itemFacts(many[13], F.buildFactsContext(many.slice(0, 5)), pages).some((r) => r.key === 'duration'), withDur?.text);
check('順位: 長いほう・短いほうの、数字が小さいほう。同じ長さは同じ順位', F.durationRank(130, [60, 70, 80, 90, 100, 110, 120, 130]).side === '長い' && F.durationRank(130, [60, 70, 80, 90, 100, 110, 120, 130]).rank === 1 && F.durationRank(60, [60, 60, 70, 80]).side === '短い' && F.durationRank(60, [60, 60, 70, 80]).rank === 1 && F.durationRank(90, [60, 70, 80, 90, 100]).side === '長い' && F.durationRank(90, [60, 70, 80, 90, 100]).rank === 2);
const vrRow = F.itemFacts(many[3], ctx, pages).find((r) => r.key === 'vr');
check('VR作品の行: 掲載中のVR作品の本数。VRのページがあればリンク。VRでない作品には出ない', vrRow && vrRow.text === `VR作品です。掲載中のVR作品は${many.filter((i) => i.vr).length}本あります。` && vrRow.href === '/tag/vr/' && !F.itemFacts(many[4], ctx, pages).some((r) => r.key === 'vr'));
check('行の文に、作品の中身・評価の言葉（人気・注目・おすすめ・期待）は入らない', many.every((i) => F.itemFacts(i, ctx, pages).every((r) => !/人気|注目|おすすめ|期待|話題|必見/.test(r.text))));
check('実データの形のフィクスチャでも落ちない。どの作品にも「同じ発売日」の行がある', fixture.every((i) => F.itemFacts(i, F.buildFactsContext(fixture), {})[0].key === 'day'));

console.log('\n■ 月ごとのページ');
const months = C.groupByMonth(many, 5);
check('作品が5本以上ある月だけ、ページが作られる（11月は14本・12月は1本）', months.length === 1 && months[0].ym === '2026-11' && months[0].items.length === 14, JSON.stringify(months.map((m) => [m.ym, m.items.length])));
check('月のグループ: 名前（2026年11月）・パス（/month/2026-11/）。月の中は発売日の早い順', months[0].name === '2026年11月' && months[0].path === '/month/2026-11/' && months[0].items.every((it, i, a) => i === 0 || a[i - 1].dateKey <= it.dateKey));
const m3 = C.groupByMonth([...many, ...Array.from({ length: 6 }, (_, i) => mk({ cid: `old${i}abc`, date: '2026-10-1' + i })), ...Array.from({ length: 5 }, (_, i) => mk({ cid: `older${i}`, date: '2026-09-1' + i }))], 5);
check('新しい月が先に並ぶ', m3.map((m) => m.ym).join() === '2026-11,2026-10,2026-09', m3.map((m) => m.ym).join());
check('前の月・次の月（ページがある月だけ）', C.neighborMonths(m3, '2026-10').newer.ym === '2026-11' && C.neighborMonths(m3, '2026-10').older.ym === '2026-09' && C.neighborMonths(m3, '2026-11').newer === null && C.neighborMonths(m3, '2026-09').older === null && C.neighborMonths(m3, '1999-01').newer === null);
check('作品ページから、その月のページの、その日の位置へのリンク。ページが無い月は ""', C.monthLinkFor(C.monthPathByKey(m3), '2026-10-12') === '/month/2026-10/#day-2026-10-12' && C.monthLinkFor(C.monthPathByKey(m3), '2026-12-24') === '');
const ms = C.monthSummary(months[0]);
check('月の紹介文: 本数・発売日の幅・メーカー・出演者・VR の本数が、データを数えた値と同じ', ms.includes('2026年11月発売の作品は14本です') && ms.includes('メーカーは') && ms.includes('出演は') && ms.includes('VR作品は1本です'), ms);
check('月のタイトル: 「○年○月発売のFANZA新作・予約作品一覧（N本）｜サイト名」', C.monthPageTitle(months[0]) === `2026年11月発売のFANZA新作・予約作品一覧（14本）｜${L.SITE_NAME}`, C.monthPageTitle(months[0]));
check('作品が1本も無くても落ちない', C.groupByMonth([]).length === 0);

console.log('\n■ ジャンルごとのページ');
const gItems = [];
for (let i = 0; i < 12; i++) gItems.push(mk({ cid: `g${i}abc`, genres: [i < 5 ? '巨乳' : '素人', i < 2 ? '中出し' : 'ハイビジョン', i % 4 === 0 ? '制服' : '美少女'], tags: i < 3 ? ['VR'] : [], date: '2026-11-0' + (1 + (i % 9)) }));
const tags = C.groupByTag(gItems, ['巨乳', '素人', '美少女', '制服'], 3);
check('許可したジャンルだけ、ページが作られる（中出し・ハイビジョンは、許可していないので作らない）', tags.every((g) => ['巨乳', '素人', '美少女', '制服', C.VR_TAG_NAME].includes(g.name)) && !tags.some((g) => g.name === '中出し' || g.name === 'ハイビジョン'), tags.map((g) => g.name).join());
check('VR作品のページが、いつも作られる（VRと判定された作品: 3本）', tags.some((g) => g.name === C.VR_TAG_NAME && g.items.length === 3));
check('作品が3本未満のジャンルは作らない', C.groupByTag(gItems, ['巨乳'], 6).length === 0 || C.groupByTag(gItems, ['巨乳'], 6).every((g) => g.items.length >= 6));
check('作品数の多い順。パスは /tag/名前のハッシュ/', tags.every((g, i, a) => i === 0 || a[i - 1].items.length >= g.items.length) && tags.every((g) => /^\/tag\/[0-9a-f]{10}\/$/.test(g.path)), tags.map((g) => g.path).join());
check('作品は発売日が新しい順', tags[0].items.every((it, i, a) => i === 0 || a[i - 1].dateKey >= it.dateKey));
const ts = C.tagSummary(tags.find((g) => g.name === '巨乳'));
check('ジャンルの紹介文: 本数が、データを数えた値と同じ。VR のページは「VR作品は」', ts.includes('「巨乳」のジャンルの作品は5本です') && C.tagSummary(tags.find((g) => g.name === C.VR_TAG_NAME)).includes('VR作品は3本です'), ts);
check('ジャンルのタイトル: 「○○の新作・予約作品一覧（N本）｜サイト名」', C.tagPageTitle(tags.find((g) => g.name === '巨乳')) === `巨乳の新作・予約作品一覧（5本）｜${L.SITE_NAME}`);

console.log('\n■ 設定（config.js）');
const cfg = await import('../site/src/config.js');
check('ジャンルのページを作るジャンルの一覧に、技術的な区分（ハイビジョン・独占配信・4K・単体作品）が入っていない', !cfg.TAG_PAGE_GENRES.some((g) => ['ハイビジョン', '独占配信', '4K', '単体作品', '4時間以上作品'].includes(g)));
check('ジャンルのページを作るジャンルの一覧に、過激な行為・未成年を連想させる名前が入っていない', !cfg.TAG_PAGE_GENRES.some((g) => /制服|校生|学生|少女|ロリ|幼|中出|顔射|フェラ|レイプ|痴漢|盗撮|調教|ドラッグ|放尿|お漏らし|失禁/.test(g)), cfg.TAG_PAGE_GENRES.join());
check('VR作品の名前は、許可したジャンルの一覧と重ならない（VRはいつも別に作る）', !cfg.TAG_PAGE_GENRES.includes(C.VR_TAG_NAME));
check('設定値が、正しい数字', cfg.MONTH_MIN_ITEMS >= 2 && cfg.TAG_MIN_ITEMS >= 2 && cfg.TAG_PAGE_LIMIT >= 30);

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
