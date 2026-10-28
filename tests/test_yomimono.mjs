// 読み物（/yomimono/。site/src/lib/yomimono.js）の部品のテスト。実行: node tests/test_yomimono.mjs
import fs from 'node:fs';
import * as Y from '../site/src/lib/yomimono.js';
import { normalizeSale } from '../site/src/lib/sale.js';
import { nonItemFileCount } from '../site/src/lib/plan.js';
import { FIXED_FILES } from '../site/src/config.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

const TODAY = '2026-10-28';
const w = (cid, o = {}) => ({ cid, title: `作品${cid}`, genres: [], dateKey: '2026-09-01', popAll: null, popNew: null, review: null, actress: [], vr: false, ...o });

console.log('■ テーマに入る作品・出さない題');
const theme = { genres: ['淫乱・ハード系'], keywords: ['AIリマスター'] };
check('テーマのジャンルが付いている作品は入る', Y.matchesTheme(w('a', { genres: ['巨乳', '淫乱・ハード系'] }), theme));
check('テーマの言葉を題に含む作品は入る', Y.matchesTheme(w('b', { title: '【AIリマスター版】昔の名作' }), theme));
check('どちらでもない作品は入らない・テーマが空なら何も入らない', !Y.matchesTheme(w('c', { genres: ['巨乳'], title: 'リマスター' }), theme)
  && !Y.matchesTheme(w('d', { genres: ['淫乱・ハード系'] }), { genres: [], keywords: [] }));
check('外す言葉の一覧は yomimono-exclude.json から読む（JS に一覧を書かない）',
  JSON.stringify(Y.YOMIMONO_TITLE_WORDS) === JSON.stringify(JSON.parse(fs.readFileSync(new URL('../site/src/lib/yomimono-exclude.json', import.meta.url), 'utf-8')).title_words)
  && !/['"]痴漢['"]/.test(fs.readFileSync(new URL('../site/src/lib/yomimono.js', import.meta.url), 'utf-8')));
check('外す言葉を含む題・未成年を連想させる題は出さない', ['痴漢電車の午後', '催眠アプリ', '○○を脅して', '女子校生の放課後', 'J●の夏', '伏せ字●あり', '暗闇の痴○映画館', 'レ×プ'].every((t) => Y.isExcludedTitle(t)));
check('ふつうの題・大人どうしの言葉は出す', ['人妻の午後', '幼なじみの人妻', '【AIリマスター版】名作', 'ハーレム温泉'].every((t) => !Y.isExcludedTitle(t)));

console.log('\n■ 読み込み');
const raw = {
  updated: '2026-10-28',
  articles: {
    'ai-remaster': {
      theme: { keywords: ['AIリマスター'] }, title: 'AIリマスター版の読みかた', description: '説明', lead: '1段落目\n\n2段落目',
      sections: [{ h: '節1', text: 'a\nb', chart: 'years' }, { h: '', text: 'x' }, { h: '節2', text: 'c', chart: 'pie' }],
      picks_h: '', picks: [{ cid: 'p1', why: '理由1' }, { cid: 'p1', why: '重複' }, { cid: 'bad id', why: 'x' }, { cid: 'p2', why: '' }],
      years: [{ y: 2024, n: 3 }, { y: 2022, n: 1 }, { y: 'x', n: 1 }], total: 12, written: '2026-10-20', checked: '2026-10-28',
    },
    hard: { theme: { genres: ['淫乱・ハード系'] }, title: 'ハード系', lead: 'L', sections: [], picks: [], written: '2026-10-25', checked: '2026-10-25' },
    'Bad Slug': { theme: { genres: ['x'] }, title: 't', lead: 'l', written: '2026-10-01', checked: '2026-10-01' },
    notheme: { theme: {}, title: 't', lead: 'l', written: '2026-10-01', checked: '2026-10-01' },
    nodate: { theme: { genres: ['x'] }, title: 't', lead: 'l', written: '', checked: '2026-10-01' },
  },
};
const n = Y.normalizeYomimono(raw);
check('形の違う読み物（slug・テーマ・日付）は捨てる・新しく書いた順', n.articles.map((a) => a.slug).join() === 'hard,ai-remaster', n.articles.map((a) => a.slug).join());
const ai = n.articles.find((a) => a.slug === 'ai-remaster');
check('段落は「\\n」で分ける（空の段落は捨てる）', ai.lead.join('|') === '1段落目|2段落目' && ai.sections[0].paras.join('|') === 'a|b');
check('節: 見出しの無い節は捨てる・chart は "years" だけ', ai.sections.length === 2 && ai.sections[0].chart === 'years' && ai.sections[1].chart === '');
check('厳選: 重複・形の違う作品ID・理由の無いものは捨てる・見出しが無ければ「最初に見るならこの5本」',
  ai.picks.map((p) => p.cid).join() === 'p1' && ai.picksHeading === '最初に見るならこの5本');
check('年ごとの本数は古い順・形の違う行は捨てる', ai.years.map((y) => y.y).join() === '2022,2024' && ai.total === 12);
check('無い・壊れたデータは空（ビルドが止まらない）', [null, [], 'x', { articles: [] }, { articles: null }].every((v) => Y.normalizeYomimono(v).articles.length === 0)
  && Y.normalizeYomimono(JSON.parse(fs.readFileSync(new URL('../site/src/data/yomimono.json', import.meta.url), 'utf-8'))).articles !== undefined);
check('URL', ai.path === '/yomimono/ai-remaster/' && Y.YOMIMONO_PATH === '/yomimono/');

console.log('\n■ 棚');
const works = [];
for (let i = 1; i <= 9; i++) works.push(w(`r${i}`, { title: `【AIリマスター版】作品${i}`, popAll: 100 + i, dateKey: `2026-0${i}-01`, review: { avg: 4 + i / 20, count: 10 + i } }));
works.push(w('ng', { title: '【AIリマスター版】痴漢の作品', popAll: 1, review: { avg: 5, count: 99 } }));
works.push(w('minor', { title: '【AIリマスター版】女子校生', popAll: 2, review: { avg: 5, count: 99 } }));
works.push(w('up', { title: '【AIリマスター版】予約の作品', dateKey: '2026-11-20' }));
works.push(w('other', { title: '関係ない作品', popAll: 3 }));
const sale = normalizeSale({
  date: TODAY,
  campaigns: [{ title: '開催中のセール', end: '2026-11-03 09:59' }, { title: '終わったセール', end: '2026-10-20 09:59' }],
  items: [{ c: 'r1', k: 0, p: 500, l: 1000 }, { c: 'r2', k: 1, p: 500, l: 1000 }, { c: 'ng', k: 0, p: 100, l: 1000 }, { c: 'up', k: 0 }],
});
const tagPathOf = (name) => (name === '淫乱・ハード系' ? '/tag/abc/' : '');
const shelves = Y.yomimonoShelves(works, { genres: [], keywords: ['AIリマスター'] }, { today: TODAY, sale, popDate: TODAY, saleDate: TODAY, tagPathOf });
const byKey = Object.fromEntries(shelves.map((s) => [s.key, s]));
check('4つの棚（人気・評価の高い・いまセール中・新作と予約）', shelves.map((s) => s.key).join() === 'pop,rated,sale,new');
check('どの棚も6本まで', shelves.every((s) => s.items.length <= 6) && byKey.pop.items.length === 6 && byKey.new.items.length === 6);
check('出さない題の作品は、どの棚にも入らない・テーマの外の作品も入らない', shelves.every((s) => s.items.every((i) => !['ng', 'minor', 'other'].includes(i.cid))));
check('人気の作品: 人気の順位の上から', byKey.pop.items.map((i) => i.cid).join() === 'r1,r2,r3,r4,r5,r6', byKey.pop.items.map((i) => i.cid).join());
check('評価の高い作品: レビュー3件以上を、ならした評価の高い順', byKey.rated.items[0].cid === 'r9' && byKey.rated.items.length === 6);
check('いまセール中: 終わったキャンペーン・予約の作品は入れない・終わりの時刻を持つ', byKey.sale.items.map((i) => i.cid).join() === 'r1' && byKey.sale.items[0].sale.end === '2026-11-03 09:59'
  && byKey.sale.note.includes('最大50%OFF'), byKey.sale.items.map((i) => i.cid).join());
check('新作と予約: 発売日が新しい順で、予約も入る', byKey.new.items[0].cid === 'up' && byKey.new.items[1].cid === 'r9');
check('棚の下の1行: ジャンルのページがあればそこ、無ければ作品検索（題の言葉で探す）・矢印を付けない',
  byKey.new.more.href === '/search/?q=' + encodeURIComponent('AIリマスター') && byKey.pop.more.href.endsWith('&sort=pop') && byKey.rated.more.href.endsWith('&sort=review')
  && shelves.every((s) => !/[→›»]/.test(s.more.text)));
const hardShelves = Y.yomimonoShelves([w('h1', { genres: ['淫乱・ハード系'], popAll: 5 })], { genres: ['淫乱・ハード系'], keywords: [] }, { today: TODAY, tagPathOf });
check('ジャンルのページがあるテーマは、新作と予約の下の1行がジャンルのページ', hardShelves.find((s) => s.key === 'new').more.href === '/tag/abc/');

console.log('\n■ ページを作る読み物・厳選');
const arts = Y.normalizeYomimono({
  articles: {
    ok: { theme: { keywords: ['AIリマスター'] }, title: 'T', lead: 'L', picks: [{ cid: 'r1', why: 'a' }, { cid: 'ng', why: 'b' }, { cid: 'gone', why: 'c' }, { cid: 'r2', why: 'd' }], written: '2026-10-20', checked: '2026-10-28' },
    empty: { theme: { keywords: ['どこにも無い言葉'] }, title: 'E', lead: 'L', written: '2026-10-20', checked: '2026-10-28' },
    onlyng: { theme: { keywords: ['痴漢'] }, title: 'N', lead: 'L', written: '2026-10-20', checked: '2026-10-28' },
  },
}).articles;
const pages = Y.buildYomimonoPages(arts, { works, today: TODAY, sale, tagPathOf });
check('棚が全部空の読み物（出さない題の作品しか無いものも）は、ページを作らない', pages.map((p) => p.slug).join() === 'ok', pages.map((p) => p.slug).join());
check('中身のある棚だけ残す', pages[0].shelves.every((s) => s.items.length > 0));
check('厳選: 見つからない作品・出さない題の作品は飛ばし、理由をそのまま', pages[0].picks.map((p) => `${p.item.cid}:${p.why}`).join() === 'r1:a,r2:d');
check('厳選の見出しの本数は、出せた本数に直す', Y.picksHeadingFor('最初に見るならこの5本', 2) === '最初に見るならこの2本' && Y.picksHeadingFor('最初に見るならこの5本', 5) === '最初に見るならこの5本'
  && Y.picksHeadingFor('まずはここから', 3) === 'まずはここから');
check('テーマの作品の数（出さない題は数えない）', pages[0].count === 10, pages[0].count);

console.log('\n■ 入口（ジャンルのページ・VRの売り場）');
const vrTheme = { genres: ['VR専用', 'ハイクオリティVR'], keywords: [] };
check('VRのジャンルのテーマ・floor が vr のテーマは VR の読み物', Y.isVrTheme(vrTheme) && Y.isVrTheme({ genres: [], keywords: ['x'], floor: 'vr' }) && !Y.isVrTheme(theme));
check('VRのテーマの関係するジャンルのページは「VR作品」', Y.themeTagNames(vrTheme).join() === 'VR作品' && Y.themeTagNames(theme).join() === '淫乱・ハード系');
const hardPages = Y.buildYomimonoPages(Y.normalizeYomimono({ articles: { hard: { theme: { genres: ['淫乱・ハード系'] }, title: 'H', lead: 'L', written: '2026-10-20', checked: '2026-10-28' } } }).articles,
  { works: [w('h1', { genres: ['淫乱・ハード系'], popAll: 5 })], today: TODAY, tagPathOf });
check('ジャンルのページの入口: そのジャンルの読み物だけ', Y.yomimonoForTag(hardPages, '淫乱・ハード系').length === 1 && Y.yomimonoForTag(hardPages, '巨乳').length === 0);

console.log('\n■ 年ごとの棒・構造化データ・ファイル数');
const bars = Y.yomimonoYearBars([{ y: 2020, n: 2 }, { y: 2023, n: 5 }]);
check('無い年は0本で埋める・いちばん多い年', bars.map((b) => `${b.year}:${b.n}`).join() === '2020:2,2021:0,2022:0,2023:5' && Y.yomimonoPeak(bars).year === 2023 && Y.yomimonoYearBars([]).length === 0);
const ld = Y.yomimonoArticleLd(ai, 'https://example.com');
check('Article: 題・公開日＝書いた日・更新日＝数えた日・書き手と発行はこのサイト', ld['@type'] === 'Article' && ld.headline === ai.title && ld.datePublished === '2026-10-20'
  && ld.dateModified === '2026-10-28' && ld.mainEntityOfPage['@id'] === 'https://example.com/yomimono/ai-remaster/' && ld.author.name === ld.publisher.name);
const il = Y.yomimonoPicksLd([{ item: w('x1') }, { item: w('x2') }], (i) => (i.cid === 'x1' ? '/item/x1/' : ''), 'https://example.com');
check('ItemList: 作品ページのある厳選の作品だけ・無ければ出さない', il.numberOfItems === 1 && il.itemListElement[0].url === 'https://example.com/item/x1/' && Y.yomimonoPicksLd([], () => '') === null);
check('ファイル数の計画に、読み物のページを数える', nonItemFileCount({ yomimono: 5 }) === FIXED_FILES + 5 + 1);
check('一覧の説明文は60〜120文字・使わない言葉が無い', [[], [1, 2]].every((p) => { const d = Y.yomimonoIndexDescription(p); return d.length >= 60 && d.length <= 120 && !/おすすめ|ぜひ|便利|簡単|安心|ポイント|コツ/.test(d); }));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
