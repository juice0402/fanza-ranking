// 「運命の1本」（site/src/lib/gacha.js・site/public/gacha.js）のテスト。実行: node tests/test_gacha.mjs
import fs from 'node:fs';
import vm from 'node:vm';
import * as G from '../site/src/lib/gacha.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};
const source = fs.readFileSync(new URL('../site/public/gacha.js', import.meta.url), 'utf-8');
const sandbox = { module: { exports: {} } };
vm.runInNewContext(source, sandbox);
const B = sandbox.module.exports;
const plain = (v) => JSON.parse(JSON.stringify(v));

console.log('■ 未成年を連想させるタイトルの判定（scripts/claude_comments.py と同じ言葉）');
const py = fs.readFileSync(new URL('../scripts/claude_comments.py', import.meta.url), 'utf-8');
const pyList = (name) => {
  const m = new RegExp(`^${name} = \\[([\\s\\S]*?)\\]\\n`, 'm').exec(py);
  return m ? [...m[1].matchAll(/"([^"]*)"/g)].map((x) => x[1]) : null;
};
const pyMinor = pyList('MINOR_WORDS');
const pyOk = pyList('MINOR_TITLE_OK');
check('言葉の一覧が、claude_comments.py の MINOR_WORDS・MINOR_TITLE_OK と同じ', pyMinor && pyOk && JSON.stringify(pyMinor) === JSON.stringify(G.MINOR_WORDS) && JSON.stringify(pyOk) === JSON.stringify(G.MINOR_TITLE_OK), JSON.stringify([pyMinor?.length, G.MINOR_WORDS.length]));
check('伏せ字の形（J● など）も、claude_comments.py と同じ', py.includes('MINOR_CENSORED = re.compile(rf"[JＪjｊ]{_C}|女子{_C}{{1,2}}生|{_C}{{1,2}}[学校]生|[中小高]{_C}生|ロ{_C}")') && py.includes('_C = "[●○◯〇＊*×]"'));
check('未成年を連想させるタイトル', ['制服の少女', '女子校生の放課後', 'ＪＫ', '過去最高！制服J●の', '女子○生', 'ロ●'].every(G.isMinorTitle));
check('大人どうしの言葉は数えない（幼なじみ・姉妹・母娘・女の子・処女）', ['幼なじみの人妻', '美人姉妹', '母娘', '近所の女の子', '処女作'].every((t) => !G.isMinorTitle(t)) && !G.isMinorTitle('人妻の温泉旅行'));

console.log('\n■ 候補（gachaPool）');
const it = (cid, extra = {}) => ({ cid, title: `作品 ${cid}`, dateKey: '2026-10-01', comment: 'ひとこと。', image_url: `https://pics.dmm.co.jp/${cid}.jpg`, actress: ['花子'], maker: 'M', vr: false, popAll: null, popNew: null, ...extra });
const items = [
  it('a', { popAll: 30 }), it('b', { popNew: 2 }), it('c', { popAll: 10, popNew: 50 }),
  it('d', { comment: '' }), // コメントの無い作品は入れない
  it('e', { dateKey: '2026-10-09' }), // 予約（まだ発売前）は入れない
  it('f', { image_url: '' }), // 画像の無い作品は入れない
  it('g', { title: '女子校生の放課後' }), // 未成年を連想させるタイトルは入れない
  it('h', { vr: true, actress: ['a', 'b', 'c', 'd'], comment: 'あ'.repeat(100) }),
  it('nopage'), // 作品ページの無い作品は入れない
];
const paged = new Set(items.map((i) => i.cid).filter((c) => c !== 'nopage'));
const pool = G.gachaPool(items, paged, '2026-10-05');
check('コメント・作品ページ・画像のある発売済みの作品だけ・未成年を連想させるタイトルは入れない', pool.map((r) => r.c).sort().join() === 'a,b,c,h', pool.map((r) => r.c).join());
check('人気の高い順（全体と新着の順位の、上のほう）。順位の無い作品はあと', pool.map((r) => r.c).join() === 'b,c,a,h', pool.map((r) => r.c).join());
const h = pool.find((r) => r.c === 'h');
check('VRの印・出演者は3名まで・ひとことは短く', h.v === 1 && h.a === 'a、b、c ほか1名' && Array.from(h.x.replace(/[\u200b\u2060]/g, '')).length <= G.GACHA_COMMENT_MAX && !('v' in pool[0]));
check('本数の上限', G.gachaPool(items, paged, '2026-10-05', 2).length === 2);
const json = G.gachaJson([{ c: 'x', t: '</script><b>&', i: '', a: '', x: '' }]);
check('ページに入れるJSONは、「<」「>」「&」を書きかえる（タグとして読まれない）', !/[<>&]/.test(json) && JSON.parse(json)[0].t === '</script><b>&');

console.log('\n■ 1本ひく（public/gacha.js）');
check('VR作品を隠すときは、VR作品を候補から外す', JSON.stringify(plain(B.eligible([{}, { v: 1 }, {}], true))) === '[0,2]' && JSON.stringify(plain(B.eligible([{}, { v: 1 }], false))) === '[0,1]');
check('直前に出た作品は、ほかに候補があるあいだは選ばない', B.pick([0, 1, 2], [0, 1], 0.99) === 2 && B.pick([0, 1, 2], [0, 1], 0) === 2);
check('全部が直前に出た作品なら、その中から', [0, 1].includes(B.pick([0, 1], [0, 1], 0.5)));
check('候補が無ければ -1・乱数が1に近くてもはみ出さない', B.pick([], [], 0.5) === -1 && B.pick([3, 4], [], 0.9999999) === 4);

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
