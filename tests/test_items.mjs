// サイトの部品（site/src/lib/items.js）のテスト。実行: node tests/test_items.mjs
import * as L from '../site/src/lib/items.js';
import fs from 'node:fs';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

console.log('■ 日付');
// UTC 2026-10-01 15:30 = 日本時間 2026-10-02 00:30
check('日本時間の日付またぎ(UTC 15:30 → 翌日)', L.jstToday(Date.UTC(2026, 9, 1, 15, 30)) === '2026-10-02', L.jstToday(Date.UTC(2026, 9, 1, 15, 30)));
check('UTC 14:59 はまだ前日', L.jstToday(Date.UTC(2026, 9, 1, 14, 59)) === '2026-10-01');
check('曜日: 2026-10-02 は金', L.dateParts('2026-10-02').wd === '金', L.dateParts('2026-10-02').wd);
check('曜日: 2026-11-22 は日', L.dateParts('2026-11-22').wd === '日', L.dateParts('2026-11-22').wd);
check('曜日: 2026-01-01 は木', L.dateParts('2026-01-01').wd === '木');
check('日付の日本語表記', L.formatDateJp('2026-11-02') === '2026年11月2日');
check('日数の差(月またぎ)', L.daysBetween('2026-10-02', '2026-09-30') === 2);
check('日数の差(年またぎ)', L.daysBetween('2027-01-01', '2026-12-31') === 1);

console.log('\n■ 整形・分類');
const raw = JSON.parse(fs.readFileSync(new URL('./fixtures/items.json', import.meta.url), 'utf-8'));
const items = L.normalizeItems(raw);
check('壊れたデータ(cid無し/日付不正/タイトル無し/重複)を除外', items.length === raw.length - 4, `${items.length} / ${raw.length}`);
check('配列でない入力でも落ちない', L.normalizeItems(null).length === 0 && L.normalizeItems({}).length === 0);
check('足りない項目に既定値', items.every((i) => Array.isArray(i.actress) && Array.isArray(i.sample_images) && typeof i.comment === 'string'));
check('AI判定(comment_kind)', items.some((i) => i.isAi) && items.some((i) => !i.isAi));
const byCid = Object.fromEntries(items.map((i) => [i.cid, i]));
check('更新日(updated): 正しい日付はそのまま', /^\d{4}-\d{2}-\d{2}$/.test(byCid.smp0001.updated) && byCid.smp0001.updated === raw[0].updated, byCid.smp0001.updated);
check('更新日(updated): 無い作品は空（sitemapに載せない）', byCid.smp0003.updated === '' && byCid.smp0004.updated === '');
check('更新日(updated): 壊れた値（「昨日」）も空', byCid.smp0005.updated === '', byCid.smp0005.updated);
check('更新日(updated): すべて文字列（空か日付）', items.every((i) => i.updated === '' || /^\d{4}-\d{2}-\d{2}$/.test(i.updated)));

console.log('\n■ サンプル動画のURL・URLの安全確認');
const mv = L.normalizeItems([
  { cid: 'mv1', title: 't', date: '2026-10-01', sample_movie: 'https://www.dmm.co.jp/litevideo/-/part/=/cid=mv1/size=476_306/' },
  { cid: 'mv2', title: 't', date: '2026-10-01', sample_movie: 'http://www.dmm.co.jp/litevideo/x/' },
  { cid: 'mv3', title: 't', date: '2026-10-01', sample_movie: 'https://evil.example/x' },
  { cid: 'mv4', title: 't', date: '2026-10-01', sample_movie: 'javascript:alert(1)' },
  { cid: 'mv5', title: 't', date: '2026-10-01', sample_movie: 'https://dmm.co.jp.evil.example/x' },
  { cid: 'mv6', title: 't', date: '2026-10-01' },
  { cid: 'mv7', title: 't', date: '2026-10-01', sample_movie: 123 },
]);
const mvBy = Object.fromEntries(mv.map((i) => [i.cid, i.sample_movie]));
check('動画のURL: FANZA(DMM)の https はそのまま', mvBy.mv1 === 'https://www.dmm.co.jp/litevideo/-/part/=/cid=mv1/size=476_306/', mvBy.mv1);
check('動画のURL: http は https に直す', mvBy.mv2 === 'https://www.dmm.co.jp/litevideo/x/', mvBy.mv2);
check('動画のURL: 他のサイト・javascript:・似せたホスト名は空', mvBy.mv3 === '' && mvBy.mv4 === '' && mvBy.mv5 === '', JSON.stringify(mvBy));
check('動画のURL: 無い・文字列でない値でも落ちず、空', mvBy.mv6 === '' && mvBy.mv7 === '');
check('safeHttpsUrl: 複数のホストを指定でき、サブドメインも通る', L.safeHttpsUrl('https://al.fanza.co.jp/?x=1', ['fanza.co.jp', 'dmm.co.jp']) === 'https://al.fanza.co.jp/?x=1' && L.safeHttpsUrl('https://notfanza.co.jp/', ['fanza.co.jp']) === '');

const today = '2026-10-02';
const { released, upcoming } = L.splitByRelease(items, today);
check('発売済み: 新しい順', released.every((x, i, a) => i === 0 || a[i - 1].dateKey >= x.dateKey));
check('予約: 近い順', upcoming.every((x, i, a) => i === 0 || a[i - 1].dateKey <= x.dateKey));
check('当日発売は「発売済み」', released.some((i) => i.dateKey === today));
check('翌日発売は「予約」', upcoming.some((i) => i.dateKey === '2026-10-03'));
check('発売済み+予約=全件', released.length + upcoming.length === items.length);

const groups = L.groupByDate(released);
check('日付ごとのまとめ: 日付が重複しない', new Set(groups.map((g) => g.dateKey)).size === groups.length);
check('日付ごとのまとめ: 件数の合計が一致', groups.reduce((n, g) => n + g.items.length, 0) === released.length);
check('空でも落ちない', L.groupByDate([]).length === 0);

check('シール: 当日=new', L.statusOf({ dateKey: '2026-10-02' }, today) === 'new');
check('シール: 6日前=new', L.statusOf({ dateKey: '2026-09-26' }, today) === 'new');
check('シール: 7日前=なし', L.statusOf({ dateKey: '2026-09-25' }, today) === '');
check('シール: 翌日=wait', L.statusOf({ dateKey: '2026-10-03' }, today) === 'wait');

console.log('\n■ 関連作品・ページ送り');
const base = items.find((i) => i.actress.length && i.actress[0] === '佐藤みお');
const rel = L.relatedItems(base, items, 8);
check('関連: 自分自身を含まない', !rel.some((r) => r.cid === base.cid));
check('関連: 重複なし', new Set(rel.map((r) => r.cid)).size === rel.length);
check('関連: 同じ出演者が先頭', rel.length > 0 && rel[0].actress.includes('佐藤みお'));
check('関連: 上限を守る', L.relatedItems(base, items, 2).length <= 2);
check('関連: メーカー不明どうしを関連にしない', L.relatedItems({ cid: 'x', actress: [], maker: '不明' }, items, 8).length === 0);
check('ページ数: 0件でも1ページ', L.archivePageCount(0) === 1);
check('ページ数: 30件=1, 31件=2', L.archivePageCount(30) === 1 && L.archivePageCount(31) === 2);
check('ページ番号の窓', JSON.stringify(L.pageWindow(10, 20)) === JSON.stringify([1, '…', 8, 9, 10, 11, 12, '…', 20]), JSON.stringify(L.pageWindow(10, 20)));
check('ページ番号: 全部表示できる少なさ', JSON.stringify(L.pageWindow(1, 3)) === JSON.stringify([1, 2, 3]));

console.log('\n■ sitemap / メタ情報');
const xml = L.buildSitemap(['/', '/item/a&b/']);
check('sitemap: 文字列だけでも作れる（lastmodなし）', !xml.includes('<lastmod>'));
const xml2 = L.buildSitemap([
  { path: '/', lastmod: '2026-10-03' },
  { path: '/item/x/', lastmod: '' },
  { path: '/item/y/', lastmod: '昨日' },
  { path: '/item/z/', lastmod: '2026-10-3' },
  { path: '/item/w/' },
]);
check('sitemap: 正しい日付だけ lastmod を出す', (xml2.match(/<lastmod>/g) || []).length === 1 && xml2.includes('<loc>https://fanza-ranking.pages.dev/</loc><lastmod>2026-10-03</lastmod></url>'), xml2);
check('sitemap: 日付が空・壊れていても、そのページ自体は載せる', ['/item/x/', '/item/y/', '/item/z/', '/item/w/'].every((p) => xml2.includes(`<loc>https://fanza-ranking.pages.dev${p}</loc></url>`)), xml2);
check('isDay: 形の判定', L.isDay('2026-10-03') && !L.isDay('2026-10-3') && !L.isDay('') && !L.isDay(undefined) && !L.isDay('2026-10-03 00:00:00'));
const lm = (list, t) => L.listLastmod(list.map((x) => ({ dateKey: '2000-01-01', updated: '', ...x })), t);
check('一覧の更新日: updated の一番新しい日', lm([{ updated: '2026-10-01' }, { updated: '2026-10-03' }, { updated: '2026-10-02' }], '2026-10-05') === '2026-10-03');
check('一覧の更新日: 発売日を迎えた日も数える（予約→発売中の切り替わり）', lm([{ updated: '2026-10-01', dateKey: '2026-10-04' }], '2026-10-05') === '2026-10-04');
check('一覧の更新日: まだ先の発売日は数えない', lm([{ updated: '2026-10-01', dateKey: '2026-10-09' }], '2026-10-05') === '2026-10-01');
check('一覧の更新日: 発売日当日は数える', lm([{ updated: '', dateKey: '2026-10-05' }], '2026-10-05') === '2026-10-05');
check('一覧の更新日: 分からないとき・空のときは空', lm([], '2026-10-05') === '' && L.listLastmod([{ dateKey: '2026-10-09', updated: '' }], '2026-10-05') === '');
check('一覧の更新日: 壊れた日付は無視', lm([{ updated: '昨日' }, { updated: '2026-10-02' }], '2026-10-05') === '2026-10-02');
check('sitemap: XMLの記号をエスケープ', xml.includes('/item/a&amp;b/') && !xml.includes('a&b'));
check('sitemap: 絶対URL', xml.includes('<loc>https://fanza-ranking.pages.dev/</loc>'));
check('sitemap: 宣言とurlset', xml.startsWith('<?xml version="1.0"') && xml.includes('<urlset'));
const robotsTxt = L.buildRobots();
check('robots.txt: 全体を許可し、sitemapの場所を案内', robotsTxt.includes('User-agent: *') && robotsTxt.includes('Allow: /') && robotsTxt.includes('Sitemap: https://fanza-ranking.pages.dev/sitemap.xml'), robotsTxt);
check('robots.txt: 指定したURLを使う', L.buildRobots('https://example.com').includes('Sitemap: https://example.com/sitemap.xml'));
const long = { ...base, title: 'あ'.repeat(200) };
check('タイトルを切り詰める', L.itemPageTitle(long).length < 80, L.itemPageTitle(long).length);
check('説明文は120字以内', L.itemPageDescription({ ...base, comment: 'い'.repeat(300) }).length <= 120);
check('作品パス', L.itemPath('abc123') === '/item/abc123/' && L.archivePath(3) === '/archive/3/');

console.log('\n■ 出演者ページ・メーカーページ');
check('形式(formats)は英数字のタグだけ', items.every((i) => i.formats.every((t) => /^[0-9A-Za-z]{1,6}$/.test(t))));
check('形式(formats): 日本語のタグは入れない', L.normalizeItems([{ cid: 'a', title: 't', date: '2026-10-01', tags: ['VR', '内容を表す言葉', '8K', 123] }])[0].formats.join() === 'VR,8K');
const slugA = L.entitySlug('花守夏歩');
check('URL用の名前: 10文字の英数字で、同じ名前なら同じ', /^[0-9a-f]{10}$/.test(slugA) && slugA === L.entitySlug('花守夏歩'), slugA);
check('URL用の名前: 違う名前なら違う（/ や 括弧を含む名前でも英数字だけ）',
  new Set(['花守夏歩', '花守夏帆', 'チキチキカマー/妄想族', '善場まみ（茉城まみ）']).size === new Set(['花守夏歩', '花守夏帆', 'チキチキカマー/妄想族', '善場まみ（茉城まみ）'].map(L.entitySlug)).size
  && ['チキチキカマー/妄想族', '善場まみ（茉城まみ）', 'a b?c#d%'].every((n) => /^[0-9a-f]{10}$/.test(L.entitySlug(n))));
const aGroups = L.groupByActress(items);
const mGroups = L.groupByMaker(items);
check('出演者グループ: 2本以上の人だけ', aGroups.length > 0 && aGroups.every((g) => g.items.length >= 2));
const mixed = L.normalizeItems([
  { cid: 's1', title: 't', date: '2026-10-01', actress: ['Solo', 'Duo'], maker: 'M1' },
  { cid: 's2', title: 't', date: '2026-10-02', actress: ['Duo'], maker: 'M1' },
  { cid: 's3', title: 't', date: '2026-10-03', actress: [], maker: 'M2' },
]);
check('出演者グループ: 作品が1本だけの人は作らない（最小本数を1にすれば作る）', L.groupByActress(mixed).map((g) => g.name).join() === 'Duo' && L.groupByActress(mixed, 1).length === 2);
check('メーカーグループ: 作品が1本だけのメーカーは作らない', L.groupByMaker(mixed).map((g) => g.name).join() === 'M1' && L.groupByMaker(mixed, 1).length === 2);
check('出演者グループ: 件数が実際の作品数と一致', aGroups.every((g) => g.items.length === items.filter((i) => i.actress.includes(g.name)).length));
check('出演者グループ: 作品は新しい順', aGroups.every((g) => g.items.every((x, i, a) => i === 0 || a[i - 1].dateKey >= x.dateKey)));
check('出演者グループ: 作品数の多い順', aGroups.every((g, i, a) => i === 0 || a[i - 1].items.length >= g.items.length));
check('出演者グループ: ページのパスと短い名前が重複しない', new Set(aGroups.map((g) => g.path)).size === aGroups.length && aGroups.every((g) => g.path === `/actress/${L.entitySlug(g.name)}/`));
check('メーカーグループ: 「不明」は作らない', !mGroups.some((g) => g.name === '不明') && !L.groupByMaker(items, 1).some((g) => g.name === '不明'));
check('メーカーグループ: 2本以上・パスは /maker/', mGroups.length > 0 && mGroups.every((g) => g.items.length >= 2 && g.path.startsWith('/maker/')));
const dup = L.normalizeItems([
  { cid: 'x1', title: 't', date: '2026-10-01', actress: ['A', 'A'], maker: 'M' },
  { cid: 'x2', title: 't', date: '2026-10-02', actress: ['A'], maker: 'M' },
  { cid: 'x3', title: 't', date: '2026-10-03', actress: [], maker: '' },
  { cid: 'x4', title: 't', date: '2026-10-04', actress: [], maker: '' },
]);
check('同じ作品に同じ名前が2回あっても1本と数える', L.groupByActress(dup)[0].items.length === 2 && L.groupByActress(dup)[0].items[0].cid === 'x2');
check('メーカーが「不明」の作品が何本あっても、「不明」のページは作らない', dup.filter((i) => i.maker === '不明').length === 2 && L.groupByMaker(dup).map((g) => g.name).join() === 'M');
const clash = L.groupItems(L.normalizeItems([
  { cid: 'c1', title: 't', date: '2026-10-01', actress: ['先に出た人'] }, { cid: 'c2', title: 't', date: '2026-10-02', actress: ['先に出た人', '同じ短い名前になった人'] },
  { cid: 'c3', title: 't', date: '2026-10-03', actress: ['同じ短い名前になった人'] },
]), (i) => i.actress, L.actressPath, 1, () => 'same');
check('別の名前が同じ短い名前になったときは、先の名前のページだけ作り、混ぜない', clash.length === 1 && clash[0].name === '先に出た人' && clash[0].items.length === 2, JSON.stringify(clash.map((g) => [g.name, g.items.length])));
check('空のデータでも落ちない', L.groupByActress([]).length === 0 && L.groupByMaker([]).length === 0);
check('名前から探す表（indexByName）', L.indexByName(aGroups).get(aGroups[0].name) === aGroups[0] && !L.indexByName(aGroups).has('いない人'));
check('形式の一覧: 重複なし・出てきた順', L.formatsOf([{ formats: ['VR', '8K'] }, { formats: ['8K', 'VR'] }]).join() === 'VR,8K');

const g0 = aGroups[0];
const sum = L.actressSummary(g0);
check('出演者の紹介文: 名前・本数・発売日の範囲が入る', sum.includes(g0.name) && sum.includes(`${g0.items.length}本`) && sum.includes('年') && sum.includes('発売日は'), sum);
const oneDay = { name: 'A', items: [{ dateKey: '2026-10-01', maker: '不明', actress: ['A'], formats: [] }, { dateKey: '2026-10-01', maker: '不明', actress: ['A'], formats: [] }] };
check('出演者の紹介文: 発売日が1日だけなら「から」を使わない・メーカー不明の文は出さない', !L.actressSummary(oneDay).includes('から') && !L.actressSummary(oneDay).includes('メーカー'), L.actressSummary(oneDay));
const manyMakers = { name: 'A', items: ['M1', 'M2', 'M3', 'M4'].map((m) => ({ dateKey: '2026-10-01', maker: m, actress: ['A'], formats: ['VR'] })) };
check('出演者の紹介文: メーカーは3つまで＋「ほか」・形式を書く', /M1、M2、M3ほか/.test(L.actressSummary(manyMakers)) && !L.actressSummary(manyMakers).includes('M4') && L.actressSummary(manyMakers).includes('VRの作品を含みます'), L.actressSummary(manyMakers));
const mg = mGroups[0];
check('メーカーの紹介文: 名前・本数が入る', L.makerSummary(mg).includes(mg.name) && L.makerSummary(mg).includes(`${mg.items.length}本`), L.makerSummary(mg));
check('紹介文に作品タイトルを含めない', aGroups.every((g) => !g.items.some((i) => L.actressSummary(g).includes(i.title))) && mGroups.every((g) => !g.items.some((i) => L.makerSummary(g).includes(i.title))));
check('ページのタイトル・説明文の長さ', L.actressPageTitle({ name: 'あ'.repeat(100), items: [1, 2] }).length < 70 && L.summaryDescription('い'.repeat(300)).length <= 120 && L.makerPageTitle(mg).includes(`${mg.items.length}本`));

console.log('\n■ 構造化データ（JSON-LD）');
const bc = L.breadcrumbLd([{ name: 'トップ', path: '/' }, { name: 'メーカー一覧', path: '/maker/' }, { name: 'A', path: '/maker/abc/' }]);
check('パンくず: 種類と順番（1から）', bc['@type'] === 'BreadcrumbList' && bc['@context'] === 'https://schema.org' && bc.itemListElement.map((e) => e.position).join() === '1,2,3');
check('パンくず: URLは絶対URL', bc.itemListElement.every((e) => e.item.startsWith('https://fanza-ranking.pages.dev/')) && bc.itemListElement[2].item === 'https://fanza-ranking.pages.dev/maker/abc/');
check('パンくず: 指定したURLを使う', L.breadcrumbLd([{ name: 'a', path: '/x/' }], 'https://example.com').itemListElement[0].item === 'https://example.com/x/');
const ws = L.websiteLd();
check('サイト情報: 名前・URL・言語', ws['@type'] === 'WebSite' && ws.name === L.SITE_NAME && ws.url === 'https://fanza-ranking.pages.dev/' && ws.inLanguage === 'ja');
const evil = { name: '</script><script>alert(1)</script>& ' };
const script = L.jsonLdScript(evil);
check('JSON-LD: ページを壊す記号（</script> など）を置き換える', !script.includes('<') && !script.includes('>') && !script.includes('&') && !script.includes(' '), script);
check('JSON-LD: 置き換えても、読み戻すと元のデータと同じ', JSON.stringify(JSON.parse(script)) === JSON.stringify(evil));

console.log('\n■ 発売日ごとの本数（一覧が途中で切れても、その日の全部の本数を出す）');
const dayItems = L.normalizeItems(Array.from({ length: 5 }, (_, i) => ({ cid: `d${i}`, title: 't', date: i < 3 ? '2026-10-03' : '2026-10-02' })));
const totalsAll = L.countByDate(dayItems);
check('日ごとの本数', totalsAll.get('2026-10-03') === 3 && totalsAll.get('2026-10-02') === 2 && totalsAll.size === 2);
const cut = L.groupByDate(dayItems.slice(0, 4), totalsAll);
check('途中で切れた日（見えているのは1本）でも、total はその日の全部の数', cut.map((g) => `${g.items.length}/${g.total}`).join() === '3/3,1/2', cut.map((g) => `${g.items.length}/${g.total}`).join());
check('totals を渡さなければ、見えている数が total', L.groupByDate(dayItems).map((g) => g.total).join() === '3,2');
check('totals に無い日は、見えている数', L.groupByDate(dayItems, new Map()).map((g) => g.total).join() === '3,2');

console.log('\n■ URLの安全確認・文字の切り方');
const urlItem = L.normalizeItems([{
  cid: 'u1', title: 't', date: '2026-10-01',
  url: 'javascript:alert(1)', image_url: 'data:text/html,<b>x</b>',
  sample_images: ['https://pics.dmm.co.jp/a.jpg', 'http://pics.dmm.co.jp/b.jpg', 'https://evil.example/c.jpg', 'javascript:alert(2)', 'https://evil.com\\@dmm.co.jp/d.jpg', 'https://dmm.co.jp:x@evil.com/e.jpg', 42, null],
}])[0];
check('作品のリンク・画像: javascript: や data: は空にする', urlItem.url === '' && urlItem.image_url === '');
check('サンプル画像: DMMのhttpsだけ残す（httpはhttpsに直す・他のサイト・javascript:・ブラウザと解釈がずれるURL・数字やnullは除く）', urlItem.sample_images.join() === 'https://pics.dmm.co.jp/a.jpg,https://pics.dmm.co.jp/b.jpg', urlItem.sample_images.join());
const okItem = L.normalizeItems([{ cid: 'u2', title: 't', date: '2026-10-01', url: 'https://al.fanza.co.jp/?lurl=https%3A%2F%2Fvideo.dmm.co.jp%2Fav%2Fcontent%2F%3Fid%3Dx&af_id=a-990', image_url: 'https://pics.dmm.co.jp/digital/video/x/xpl.jpg' }])[0];
check('本物の形のアフィリエイトURL（al.fanza.co.jp）・画像URL（pics.dmm.co.jp）は通る', okItem.url.startsWith('https://al.fanza.co.jp/?lurl=') && okItem.image_url === 'https://pics.dmm.co.jp/digital/video/x/xpl.jpg');
check('作品のリンクに他のサイトのURLは通さない', L.normalizeItems([{ cid: 'u3', title: 't', date: '2026-10-01', url: 'https://evil.example/?x=fanza.co.jp' }])[0].url === '');
const hasLone = (str) => /[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/.test(str);
check('文字を切る: 絵文字（2つ分の文字）の途中で切らない', !hasLone(L.truncate('あ'.repeat(42) + '😀' + 'い'.repeat(10), 44)), JSON.stringify(L.truncate('あ'.repeat(42) + '😀' + 'い'.repeat(10), 44)));
check('文字を切る: 「𠮷」の途中でも切らない・文字数は見た目の文字数で数える', L.truncate('𠮷'.repeat(10), 5) === '𠮷𠮷𠮷𠮷…' && L.truncate('𠮷𠮷', 2) === '𠮷𠮷');
check('文字を切る: 短ければそのまま・長ければ max 文字（…を含む）', L.truncate('abc', 5) === 'abc' && L.truncate('abcdef', 4) === 'abc…' && L.truncate(null, 3) === '');

console.log('\n■ VR作品の判定（「VR作品を隠す」・検索の除外に使う）');
check('タイトルの【VR】で判定（【VR】【8K】のように複数の括弧でも）', L.isVrWork({ title: '【VR】テスト' }) && L.isVrWork({ title: '【8K】【VR】テスト' }) && L.isVrWork({ title: '【VR】【8K】テスト' }));
check('形式タグ（VR・8KVR）で判定', L.isVrWork({ formats: ['VR'] }) && L.isVrWork({ formats: ['8K', '8KVR'] }));
check('ジャンル（VR専用・ハイクオリティVR・8KVR）で判定。予約でタイトルが紛らわしくても、ジャンルが載れば分かる', ['VR専用', 'ハイクオリティVR', '8KVR'].every((g) => L.isVrWork({ title: 'ふつうのタイトル', genres: ['中出し', g] })));
check('VRではない作品は false（8K・4K・NTR・タイトル本文の「VR」は、括弧書きでなければ数えない）', !L.isVrWork({ title: '【8K】テスト', formats: ['8K'], genres: ['4K', 'ハイビジョン', 'NTR'] }) && !L.isVrWork({ title: 'VRのような体験の人妻', genres: [] }) && !L.isVrWork({}) && !L.isVrWork());
const vrItems = L.normalizeItems([
  { cid: 'v1', title: '【VR】テスト', date: '2026-10-01', tags: ['VR'] },
  { cid: 'v2', title: 'ふつう', date: '2026-10-01', genres: ['VR専用'] },
  { cid: 'v3', title: 'ふつう', date: '2026-10-01', genres: ['中出し'], tags: ['8K'] },
]);
check('normalizeItems が vr を付ける（タイトル・ジャンル・どちらでもVR、VRでなければ false）', vrItems.map((i) => i.vr).join() === 'true,true,false', vrItems.map((i) => i.vr).join());
check('一覧の1マスの目印（vrAttrs）: VR作品だけ data-vr が付く', L.vrAttrs(vrItems[0])['data-vr'] === 'true' && Object.keys(L.vrAttrs(vrItems[2])).length === 0);

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
