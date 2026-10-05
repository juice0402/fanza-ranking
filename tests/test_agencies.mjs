// 所属事務所とSNSの部品（site/src/lib/agencies.js）と、女優検索の「所属事務所」（site/public/actress-search.js）のテスト。実行: node tests/test_agencies.mjs
import fs from 'node:fs';
import vm from 'node:vm';
import * as G from '../site/src/lib/agencies.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

console.log('■ 事務所の一覧（Python の道具と同じ）');
const py = fs.readFileSync(new URL('../scripts/agency_links.py', import.meta.url), 'utf-8');
const pySites = [...py.matchAll(/\{"key": "([a-z]+)", "name": "([^"]+)", "url": "([^"]+)"/g)].map((m) => [m[1], m[2], m[3]]);
const jsSites = Object.entries(G.AGENCIES).map(([k, v]) => [k, v.name, v.url]);
check('キー・名前・公式サイトが scripts/agency_links.py の SITES と同じ', JSON.stringify(pySites) === JSON.stringify(jsSites) && jsSites.length >= 5, JSON.stringify(pySites));
check('公式サイトは、ホスト名（と決まった場所）のあとが / で終わる（出どころの確かめに使う。http のままのサイトもある）', jsSites.every(([, , u]) => /^https?:\/\/[a-z0-9.-]+\/([a-z0-9_-]+\/)*$/.test(u)), jsSites.map(([, , u]) => u).join());

console.log('\n■ agencies.json の読み方');
const raw = {
  updated: '2026-10-05',
  rows: [
    { name: '河北彩花（河北彩伽）', id: '1044864', agency: 'tpowers', x: 'Saika_Kawakita', instagram: 'saika_kawakita__official', source: 'https://www.t-powers.co.jp/talent/kawakitasaika/', seen: '2026-10-05' },
    { name: '作品だけ子', agency: 'mines', x: 'bad handle!', instagram: '../evil', source: 'https://mines-pro.jp/model/1', seen: '2026-10-05' },
    { name: '知らない事務所', agency: 'evil', source: 'https://evil.example/', seen: '2026-10-05' },
    { name: 'なりすまし', agency: 'tpowers', source: 'https://www.t-powers.co.jp.evil.example/x', seen: '2026-10-05' },
    { name: '別のサイト', agency: 'tpowers', source: 'https://evil.example/www.t-powers.co.jp/', seen: '2026-10-05' },
    { name: '日付なし', agency: 'tpowers', source: 'https://www.t-powers.co.jp/talent/a/' },
    { name: 'ふたご', agency: 'bambi', source: 'https://bambi.ne.jp/model.php?id=1', seen: '2026-10-05' },
    { name: 'ふたご', agency: 'alive', source: 'https://alive-pro.tokyo/model/a', seen: '2026-10-05' },
    'x', null,
  ],
};
const ag = G.normalizeAgencies(raw);
check('正しい行だけ（知らない事務所・出どころが事務所のサイトでない・日付が無い行は捨てる）', ag.rows.map((r) => r.name).join() === '河北彩花（河北彩伽）,作品だけ子', ag.rows.map((r) => r.name).join());
const k = ag.byName.get('河北彩花（河北彩伽）');
check('事務所の名前・公式サイトは決まった一覧から・id・アカウント名', k.agency === 'ティーパワーズ' && k.agencyUrl === 'https://www.t-powers.co.jp/' && k.id === '1044864' && k.x === 'Saika_Kawakita' && k.instagram === 'saika_kawakita__official' && ag.updated === '2026-10-05');
check('アカウント名の形が違えば、そのSNSだけ捨てる', ag.byName.get('作品だけ子').x === '' && ag.byName.get('作品だけ子').instagram === '' && ag.byName.get('作品だけ子').id === '');
check('同じ名前が2行あれば、どちらも使わない', !ag.byName.has('ふたご'));
check('無い・形が違うときは空', [null, undefined, [], 'x', { rows: 'x' }].every((v) => { const a = G.normalizeAgencies(v); return a.rows.length === 0 && a.byName.size === 0 && a.updated === ''; }));
check('SNSのURL', G.xUrl('Saika_Kawakita') === 'https://x.com/Saika_Kawakita' && G.instagramUrl('a.b_c') === 'https://www.instagram.com/a.b_c/');

console.log('\n■ 女優検索の索引に足す');
const index = {
  generated: '2026-10-05',
  actresses: [
    { n: '河北彩花（河北彩伽）', id: '1044864', k: 3 },
    { n: '河北彩花（河北彩伽）', id: '999', k: 0 }, // 同じ名前の別人（id が違う）
    { n: '作品だけ子', s: 'abcdef0123', k: 2 },
    { n: '名簿の人', id: '5' },
  ],
};
const idx = G.withAgencies(index, ag);
check('id が分かる人は id で付ける（同じ名前の別人には付けない）', idx.actresses[0].g === 'tpowers' && !('g' in idx.actresses[1]));
check('id が分からない人は名前で付ける（索引に同じ名前が1人だけのとき）', idx.actresses[2].g === 'mines' && !('g' in idx.actresses[3]));
check('索引の事務所の名前は、使っている事務所だけ・元の索引は変えない', JSON.stringify(idx.agencies) === JSON.stringify({ tpowers: 'ティーパワーズ', mines: 'マインズ' }) && !('g' in index.actresses[0]));
const dupIndex = G.withAgencies({ actresses: [{ n: '作品だけ子' }, { n: '作品だけ子', id: '7' }] }, ag);
check('名前で付けるとき、索引に同じ名前が2人いれば付けない', dupIndex.actresses.every((r) => !r.g));
check('事務所ごとの人数（多い順）', JSON.stringify(G.agencyCounts({ actresses: [{ g: 'mines' }, { g: 'tpowers' }, { g: 'mines' }, {}] })) === JSON.stringify([{ key: 'mines', name: 'マインズ', count: 2 }, { key: 'tpowers', name: 'ティーパワーズ', count: 1 }]));

console.log('\n■ 女優検索の「所属事務所」（ブラウザ側）');
const sandbox = { module: { exports: {} }, URLSearchParams };
vm.runInNewContext(fs.readFileSync(new URL('../site/public/actress-search.js', import.meta.url), 'utf-8'), sandbox);
const S = sandbox.module.exports;
const rows = [{ n: 'A', k: 2, g: 'tpowers' }, { n: 'B', k: 1, g: 'mines' }, { n: 'C', k: 3 }];
const names = (q) => S.filterRows(rows, q).map((r) => r.n).join();
check('所属事務所で絞り込む・形が違う値は絞り込まない', names({ ag: 'tpowers' }) === 'A' && names({ ag: 'mines' }) === 'B' && names({ ag: '' }) === 'C,A,B' && names({ ag: 'TP!' }) === 'C,A,B');
const pq = JSON.parse(JSON.stringify(S.parseQuery('?ag=tpowers&cup=E')));
check('URL の読み書き（形が違う事務所のキーは捨てる）', pq.ag === 'tpowers' && S.buildQuery(pq) === '?cup=E&ag=tpowers' && JSON.parse(JSON.stringify(S.parseQuery('?ag=../x'))).ag === '');
check('結果の「所属：○○」（索引の agencies にある事務所だけ）', S.agencyLabel({ g: 'tpowers' }, { tpowers: 'ティーパワーズ' }) === '所属：ティーパワーズ' && S.agencyLabel({ g: 'mines' }, { tpowers: 'ティーパワーズ' }) === '' && S.agencyLabel({}, {}) === '' && S.agencyLabel({ g: 'constructor' }, {}) === '');

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
