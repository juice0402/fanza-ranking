// 月のまとめ記事の部品（site/src/lib/monthly.js。2026-10-07 から）のテスト。実行: node tests/test_monthly.mjs
// Python の道具（scripts/claude_monthly.py）の月の終わり・傾向の数字と、サイト側の読み込みが一致するかの突き合わせも行う。
import * as M from '../site/src/lib/monthly.js';
import { normalizeItems, SITE_NAME } from '../site/src/lib/items.js';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

console.log('■ 月の日付・タイトル');
check('月の最後の日（31日・30日・うるう年の2月・平年の2月・12月）', M.monthLastDay('2026-10') === '2026-10-31' && M.monthLastDay('2026-11') === '2026-11-30'
  && M.monthLastDay('2028-02') === '2028-02-29' && M.monthLastDay('2026-02') === '2026-02-28' && M.monthLastDay('2026-12') === '2026-12-31');
check('タイトル・説明文', M.monthlyTitle({ month: '2026-10' }) === '2026年10月のFANZA新作まとめ' && M.monthJp('2027-01') === '2027年1月'
  && M.monthlyDescription({ lead: 'あ'.repeat(300) }).length <= 120);

console.log('\n■ 記事の読み込み（normalizeMonthly）');
const items = normalizeItems([
  { cid: 'o1', title: 't', date: '2026-10-03', maker: 'M' },
  { cid: 'o2', title: 't', date: '2026-10-20', maker: 'M' },
  { cid: 's1', title: 't', date: '2026-09-30', maker: 'M' },
]);
const facts = { total: 40, prev_total: 6, vr: 3, prev_vr: 1, debut: 2, genres: [{ name: '巨乳', count: 20, prev: 3 }], popular: [{ cid: 'o1', best: 2, days10: 4 }] };
const good = { month: '2026-10', lead: '導入文です。', trend: '傾向です。', picks: [{ cid: 'o1', note: 'ひとこと' }, { cid: 'o2', note: 'ふたこと' }], written: '2026-11-01', facts };
const norm = M.normalizeMonthly([good], items);
check('正しい記事はそのまま読める', norm.length === 1 && norm[0].month === '2026-10' && norm[0].trend === '傾向です。' && norm[0].picks.length === 2 && norm[0].facts.total === 40, JSON.stringify(norm));
check('月の形が違う・導入文なし・公開日なし・その月が終わる前の公開日・重複した月は捨てる', M.normalizeMonthly([
  { ...good, month: '2026-13' }, { ...good, month: '2026/10' }, { ...good, lead: ' ' }, { ...good, written: '' }, { ...good, written: '2026-10-31' }, good, { ...good, lead: '2つ目' },
], items).length === 1);
check('作品データに無い・その月の発売でない注目の作品・ひとことが空の作品は外す', M.normalizeMonthly([
  { ...good, picks: [{ cid: 'o1', note: 'ok' }, { cid: 's1', note: '前の月' }, { cid: 'zz', note: 'データに無い' }, { cid: 'o2', note: '  ' }, null] },
], items)[0].picks.map((p) => p.cid).join() === 'o1');
check('傾向・数字が無くても読める（傾向の欄を出さない）', M.normalizeMonthly([{ ...good, trend: undefined, facts: undefined }], items)[0].facts === null);
check('新しい月が先頭', M.normalizeMonthly([good, { ...good, month: '2026-11', written: '2026-12-01' }], items).map((r) => r.month).join() === '2026-11,2026-10');
check('壊れた入力でも落ちない', M.normalizeMonthly(null, items).length === 0 && M.normalizeMonthly({}, items).length === 0 && M.normalizeMonthly([1, 'a', null], items).length === 0);

console.log('\n■ 構造化データ');
const ld = M.monthlyLd(norm[0]);
check('Article: 種類・見出し・公開日・URL（月のページ）', ld['@type'] === 'Article' && ld.headline === '2026年10月のFANZA新作まとめ' && ld.datePublished === '2026-11-01'
  && ld.mainEntityOfPage['@id'] === 'https://fanza-ranking.pages.dev/month/2026-10/', JSON.stringify(ld));
check('Article: 発行元はサイト自身（人の名前を入れない）', ld.author['@type'] === 'Organization' && ld.author.name === SITE_NAME && ld.publisher.name === SITE_NAME);

console.log('\n■ Python との突き合わせ');
const code = `
import json, sys
sys.path.insert(0, ${JSON.stringify(path.join(path.dirname(new URL(import.meta.url).pathname), '..', 'scripts'))})
import claude_monthly as m
print(json.dumps({x: m.month_last(x) for x in sys.argv[1:]}))
`;
const months = ['2026-01', '2026-02', '2028-02', '2026-04', '2026-09', '2026-10', '2026-12', '2100-02'];
try {
  const py = JSON.parse(execFileSync('python3', ['-c', code, ...months], { encoding: 'utf-8', env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } }));
  check('月の最後の日が Python と同じ（2100年2月のような、うるう年でない100年も）', months.every((x) => py[x] === M.monthLastDay(x)), JSON.stringify(py));
} catch (e) {
  check('Python の month_last を呼べる', false, String(e.message).slice(0, 200));
}

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
