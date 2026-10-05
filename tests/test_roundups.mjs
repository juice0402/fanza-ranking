// 週のまとめ記事の部品（site/src/lib/roundups.js）のテスト。実行: node tests/test_roundups.mjs
// Python の道具（scripts/claude_roundups.py）の数え方と、サイト側の数え方が一致するかの突き合わせも行う。
import * as R from '../site/src/lib/roundups.js';
import { normalizeItems, SITE_NAME } from '../site/src/lib/items.js';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

console.log('■ 週の計算（月曜〜日曜）');
check('週の月曜: 水曜 2026-10-07 → 10-05', R.weekStartOf('2026-10-07') === '2026-10-05', R.weekStartOf('2026-10-07'));
check('週の月曜: 月曜はそのまま', R.weekStartOf('2026-10-05') === '2026-10-05');
check('週の月曜: 日曜 2026-10-04 は前の月曜(9-28)の週', R.weekStartOf('2026-10-04') === '2026-09-28', R.weekStartOf('2026-10-04'));
check('週の月曜: 年またぎ 2027-01-01(金) → 2026-12-28', R.weekStartOf('2027-01-01') === '2026-12-28', R.weekStartOf('2027-01-01'));
check('日付の足し算（月またぎ・うるう年）', R.addDays('2026-09-30', 1) === '2026-10-01' && R.addDays('2028-02-28', 1) === '2028-02-29' && R.addDays('2026-10-05', -7) === '2026-09-28');
check('月曜かどうか', R.isMonday('2026-10-05') && !R.isMonday('2026-10-06') && !R.isMonday('10/05') && !R.isMonday('') && !R.isMonday(undefined));
check('週の終わり（日曜）', R.weekEndOf('2026-09-28') === '2026-10-04');
check('期間の日本語: 同じ月', R.weekRangeJp('2026-10-05') === '2026年10月5日〜11日', R.weekRangeJp('2026-10-05'));
check('期間の日本語: 月またぎ', R.weekRangeJp('2026-09-28') === '2026年9月28日〜10月4日', R.weekRangeJp('2026-09-28'));
check('期間の日本語: 年またぎ', R.weekRangeJp('2026-12-28') === '2026年12月28日〜2027年1月3日', R.weekRangeJp('2026-12-28'));
check('ページのパス', R.weeklyPath('2026-09-28') === '/weekly/2026-09-28/' && R.WEEKLY_INDEX_PATH === '/weekly/');

console.log('\n■ 記事の読み込み（normalizeRoundups）');
const items = normalizeItems([
  { cid: 'a1', title: 't', date: '2026-09-28', maker: 'M' },
  { cid: 'a2', title: 't', date: '2026-09-29', maker: 'M' },
]);
const good = { week_start: '2026-09-28', lead: '導入文です。', picks: [{ cid: 'a1', note: 'ひとこと' }], written: '2026-10-05' };
const norm = R.normalizeRoundups([good], items);
check('正しい記事はそのまま読める（週の終わりも付く）', norm.length === 1 && norm[0].week_end === '2026-10-04' && norm[0].picks.length === 1 && norm[0].written === '2026-10-05', JSON.stringify(norm));
check('月曜でない週・導入文なし・公開日なし・重複した週は捨てる', R.normalizeRoundups([
  { ...good, week_start: '2026-09-29' }, { ...good, lead: '  ' }, { ...good, written: '' }, { ...good, written: '昨日' }, good, { ...good, lead: '2つ目' },
], items).length === 1);
check('作品データに無い注目の作品・ひとことが空の作品は外す', R.normalizeRoundups([
  { ...good, picks: [{ cid: 'a1', note: 'ok' }, { cid: 'zzz', note: 'データに無い' }, { cid: 'a2', note: '  ' }, null] },
], items)[0].picks.map((p) => p.cid).join() === 'a1');
check('picks が無くても読める', R.normalizeRoundups([{ ...good, picks: undefined }], items)[0].picks.length === 0);
check('新しい週が先頭', R.normalizeRoundups([good, { ...good, week_start: '2026-10-05', written: '2026-10-12' }], items).map((r) => r.week_start).join() === '2026-10-05,2026-09-28');
check('壊れた入力でも落ちない', R.normalizeRoundups(null, items).length === 0 && R.normalizeRoundups({}, items).length === 0 && R.normalizeRoundups([1, 'a', null], items).length === 0);

console.log('\n■ 前後の週・タイトル・構造化データ');
const three = R.normalizeRoundups([
  good, { ...good, week_start: '2026-10-05', written: '2026-10-12' }, { ...good, week_start: '2026-10-12', written: '2026-10-19' },
], items);
const mid = R.neighbours(three, '2026-10-05');
check('前の週・次の週', mid.prev.week_start === '2026-09-28' && mid.next.week_start === '2026-10-12');
check('いちばん古い週は「前」なし・いちばん新しい週は「次」なし', R.neighbours(three, '2026-09-28').prev === null && R.neighbours(three, '2026-10-12').next === null);
check('記事が1本だけなら前後なし', R.neighbours(norm, '2026-09-28').prev === null && R.neighbours(norm, '2026-09-28').next === null);
check('タイトル・ページタイトル・説明文', R.roundupTitle(norm[0]) === '2026年9月28日〜10月4日のFANZA新作まとめ' && R.roundupPageTitle(norm[0]).endsWith(`｜${SITE_NAME}`) && R.roundupDescription({ lead: 'あ'.repeat(300) }).length <= 120);
const ld = R.articleLd(norm[0]);
check('Article: 種類・見出し・公開日・URL', ld['@type'] === 'Article' && ld['@context'] === 'https://schema.org' && ld.headline === R.roundupTitle(norm[0]) && ld.datePublished === '2026-10-05' && ld.mainEntityOfPage['@id'] === 'https://fanza-ranking.pages.dev/weekly/2026-09-28/', JSON.stringify(ld));
check('Article: 発行元はサイト自身（人の名前を入れない）', ld.author['@type'] === 'Organization' && ld.author.name === SITE_NAME && ld.publisher.name === SITE_NAME);
check('Article: 指定したURLを使う', R.articleLd(norm[0], 'https://example.com').mainEntityOfPage['@id'] === 'https://example.com/weekly/2026-09-28/');

console.log('\n■ 集計（weekStats）');
// 月〜日に出る人・メーカー・形式をいろいろ入れたデータ。2本以上の人だけ載る・メーカーは上位5つ・「不明」は数えない・同じ人が1作品に2回いても1本
const makers = ['メーカーA', 'メーカーA', 'メーカーA', 'メーカーB', 'メーカーB', 'メーカーC', 'メーカーD', 'メーカーE', 'メーカーF', 'メーカーG', '不明', ''];
const people = ['花子', '葵', '彩', '月', '桜', '星', '花子', '', '単発', '葵', '彩', '月'];
const rawItems = [];
for (let i = 0; i < 30; i++) {
  const day = R.addDays('2026-09-28', [0, 0, 1, 2, 2, 2, 3, 4, 4, 5, 6, 6, 7, 8, 9, 10, 11, 13, 13, 13, 14, 15, 15, 16, 17, 18, 19, 19, 20, 20][i]);
  const who = people[i % people.length];
  rawItems.push({
    cid: `w${String(i).padStart(2, '0')}`, title: `タイトル${i}`, date: `${day} 00:00:00`, maker: makers[i % makers.length] || undefined,
    actress: who ? (i % 5 === 0 ? [who, who] : [who]) : [], tags: i % 3 === 0 ? ['VR'] : i % 3 === 1 ? ['8K', '内容を表すタグ'] : [],
  });
}
const data = normalizeItems(rawItems);
const w1 = R.weekStats(data, '2026-09-28');
const inWeek = R.itemsInWeek(data, '2026-09-28');
check('その週(月〜日)だけを数える・日付の古い順', inWeek.length === w1.total && inWeek.every((i) => i.dateKey >= '2026-09-28' && i.dateKey <= '2026-10-04') && inWeek.every((x, k, a) => k === 0 || a[k - 1].dateKey <= x.dateKey));
check('日曜(10-04)は前の週・月曜(10-05)は次の週に入る', R.itemsInWeek(data, '2026-09-28').some((i) => i.dateKey === '2026-10-04') && !R.itemsInWeek(data, '2026-10-05').some((i) => i.dateKey === '2026-10-04') && R.itemsInWeek(data, '2026-10-05').some((i) => i.dateKey === '2026-10-05'));
check('発売日別の本数の合計 = 全体の本数', w1.per_day.reduce((s, d) => s + d.count, 0) === w1.total && w1.per_day.every((d, k, a) => k === 0 || a[k - 1].date < d.date));
check('メーカー: 上位5つまで・多い順・「不明」と空は数えない', w1.makers.length <= 5 && w1.makers.every((m, k, a) => k === 0 || a[k - 1].count >= m.count) && w1.makers.every((m) => m.name && m.name !== '不明'), JSON.stringify(w1.makers));
check('出演者: 2本以上の人だけ・同じ人が1作品に2回いても1本と数える', w1.actresses.every((a) => a.count >= 2) && w1.actresses.every((a) => a.count <= w1.total), JSON.stringify(w1.actresses));
check('形式: VR/8K だけ（「内容を表すタグ」は入らない）', w1.formats.map((f) => f.name).sort().join() === '8K,VR', JSON.stringify(w1.formats));
check('作品が無い週でも落ちない', R.weekStats(data, '2030-01-07').total === 0 && R.weekStats([], '2026-09-28').makers.length === 0);

console.log('\n■ Python の数え方との突き合わせ');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'roundups_'));
const dataFile = path.join(tmp, 'items.json');
fs.writeFileSync(dataFile, JSON.stringify(rawItems));
const weeks = ['2026-09-21', '2026-09-28', '2026-10-05', '2026-10-12', '2026-10-19', '2030-01-07'];
const code = `
import json, sys
sys.path.insert(0, ${JSON.stringify(path.join(path.dirname(new URL(import.meta.url).pathname), '..', 'scripts'))})
import claude_roundups as r
items = json.load(open(sys.argv[1], encoding="utf-8"))
print(json.dumps({w: r.week_stats(items, w) for w in sys.argv[2:]}, ensure_ascii=False))
`;
let py = null;
try {
  py = JSON.parse(execFileSync('python3', ['-c', code, dataFile, ...weeks], { encoding: 'utf-8', env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } }));
} catch (e) {
  check('Python の week_stats を呼べる', false, String(e.message).slice(0, 200));
}
if (py) {
  for (const w of weeks) {
    const js = R.weekStats(data, w);
    check(`${w} の週: 本数・日別・メーカー・出演者・形式がすべて同じ`, same(js, py[w]), JSON.stringify({ js, py: py[w] }).slice(0, 300));
  }
  check('突き合わせた週のうち、中身のある週が3つ以上ある', weeks.filter((w) => py[w].total > 0).length >= 3);
}
fs.rmSync(tmp, { recursive: true, force: true });

console.log('\n■ トップの右の欄の「週のまとめ」（概要だけ）');
check('短い期間（年を入れない）', R.weekRangeShort('2026-09-28') === '9月28日〜10月4日' && R.weekRangeShort('2026-10-05') === '10月5日〜11日' && R.weekRangeShort('2026-12-28') === '12月28日〜1月3日');
check('概要は導入文のはじめの1文', R.roundupSummary({ lead: '今週は12本でした。メーカーは…です。' }) === '今週は12本でした。' && R.roundupSummary({ lead: '句点の無い文' }) === '句点の無い文' && R.roundupSummary(null) === '');
check('概要が長ければ切る', R.roundupSummary({ lead: 'あ'.repeat(100) + '。' }, 20).length <= 20);
const cvItems = normalizeItems([
  { cid: 'c1', title: '作品1', date: '2026-09-29', image_url: 'https://pics.dmm.co.jp/digital/video/c1/c1pl.jpg' },
  { cid: 'c2', title: '【VR】作品2', date: '2026-09-29', image_url: 'https://pics.dmm.co.jp/digital/video/c2/c2pl.jpg' },
  { cid: 'c3', title: '作品3', date: '2026-09-30', image_url: '' },
  { cid: 'c4', title: '作品4', date: '2026-09-30', image_url: 'https://pics.dmm.co.jp/digital/video/c4/c4pl.jpg' },
  { cid: 'c5', title: '作品5', date: '2026-10-01', image_url: 'https://pics.dmm.co.jp/digital/video/c5/c5pl.jpg' },
  { cid: 'c6', title: '作品6', date: '2026-10-01', image_url: 'https://pics.dmm.co.jp/digital/video/c6/c6pl.jpg' },
]);
const cv = R.roundupCovers({ picks: ['c2', 'c1', 'c3', 'zz', 'c4', 'c5', 'c6'].map((cid) => ({ cid, note: 'n' })) }, cvItems);
check('表紙は記事の順に、画像があってVRでない作品を3本（「VR作品を隠す」でも並びがくずれない）', cv.map((i) => i.cid).join() === 'c1,c4,c5', cv.map((i) => i.cid).join());
check('注目の作品が無ければ空', R.roundupCovers({ picks: [] }, cvItems).length === 0 && R.roundupCovers(undefined, cvItems).length === 0);

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
