// 発売日カレンダー（site/src/lib/calendar.js）とお気に入り索引（site/src/lib/favorites.js）のテスト。実行: node tests/test_calendar.mjs
import * as C from '../site/src/lib/calendar.js';
import * as F from '../site/src/lib/favorites.js';
import { normalizeItems } from '../site/src/lib/items.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};
const unfold = (ics) => ics.replace(/\r\n /g, '');

console.log('■ 文章の書き換え・折り返し');
check('記号の書き換え: ; , \\ 改行', C.escapeIcsText('a;b,c\\d\ne') === 'a\\;b\\,c\\\\d\\ne', C.escapeIcsText('a;b,c\\d\ne'));
check('制御文字は取り除く', C.escapeIcsText('a\u0000b\u0007c') === 'abc');
const long = 'あ'.repeat(100) + 'abc' + '🎉'.repeat(20);
const folded = C.foldIcsLine('DESCRIPTION:' + long);
const rows = folded.split('\r\n');
check('折り返し: 1行は75バイト以内（日本語・絵文字でも）', rows.every((r) => new TextEncoder().encode(r).length <= 75), rows.map((r) => new TextEncoder().encode(r).length).join(','));
check('折り返し: 2行目以降は空白で始まる', rows.slice(1).every((r) => r.startsWith(' ')) && rows.length > 2);
check('折り返し: つなぎ直すと元の文と同じ（文字の途中で切れていない）', folded.replace(/\r\n /g, '') === 'DESCRIPTION:' + long);
check('短い行は折り返さない', C.foldIcsLine('BEGIN:VCALENDAR') === 'BEGIN:VCALENDAR');
check('ちょうど75バイトは折り返さない・76バイトは折り返す', !C.foldIcsLine('a'.repeat(75)).includes('\r\n') && C.foldIcsLine('a'.repeat(76)).split('\r\n').length === 2);

console.log('\n■ カレンダーの中身');
const items = normalizeItems([
  { cid: 'old1', title: '古い作品（対象外）', date: '2026-09-01', actress: ['A'], maker: 'M' },
  { cid: 'recent1', title: '最近の作品, セミコロン; あり', date: '2026-09-25 00:00:00', actress: ['A'], maker: 'M' },
  { cid: 'today1', title: '今日の作品', date: '2026-10-03', actress: ['B'], maker: '不明' },
  { cid: 'soon1', title: '月またぎの予約', date: '2026-10-31', actress: [], maker: 'メーカーX' },
  { cid: 'soon2', title: '年またぎの予約', date: '2026-12-31', actress: [], maker: '不明' },
]);
const today = '2026-10-03';
const ci = C.calendarItems(items, today);
check('対象は、発売日が14日前以降の作品だけ（古い作品は入らない）', ci.map((i) => i.cid).join() === 'recent1,today1,soon1,soon2', ci.map((i) => i.cid).join());
check('14日前ちょうど(9/19)は入り、その前日(9/18)は入らない', C.calendarItems(normalizeItems([{ cid: 'e1', title: 't', date: '2026-09-19' }, { cid: 'e2', title: 't', date: '2026-09-18' }]), today).map((i) => i.cid).join() === 'e1');
check('件数の上限: これから発売される作品（今日以降）を先に残す（枠が余れば、最近発売された作品を新しい方から）', C.calendarItems(items, today, 2).map((i) => i.cid).join() === 'today1,soon1' && C.calendarItems(items, today, 3).map((i) => i.cid).join() === 'today1,soon1,soon2' && C.calendarItems(items, today, 4).map((i) => i.cid).join() === 'recent1,today1,soon1,soon2');
// 毎日12本ずつ14日ぶんの発売済み（168本）＋ 予約130本 → 上限200では、予約はすべて残り、過去は新しい方の70本
const dayOf = (n) => new Date(Date.UTC(2026, 9, 3 + n)).toISOString().slice(0, 10);
const crowd = normalizeItems([
  ...Array.from({ length: 168 }, (_, i) => ({ cid: `p${String(i).padStart(3, '0')}`, title: 't', date: dayOf(-1 - Math.floor(i / 12)) })),
  ...Array.from({ length: 130 }, (_, i) => ({ cid: `u${String(i).padStart(3, '0')}`, title: 't', date: dayOf(1 + Math.floor(i / 5)) })),
]);
const kept = C.calendarItems(crowd, today);
check('多すぎるとき（298本・上限200本）: 予約130本はすべて残り、枠が余った70本分は最近の発売済み', kept.length === 200 && kept.filter((i) => i.dateKey >= today).length === 130 && kept.filter((i) => i.dateKey < today).length === 70 && kept.every((i, n) => n === 0 || kept[n - 1].dateKey <= i.dateKey), kept.length + ' / ' + kept.filter((i) => i.dateKey >= today).length);
check('予約だけで上限を超えるときは、近い日から残す', C.calendarItems(normalizeItems(Array.from({ length: 10 }, (_, i) => ({ cid: `x${i}`, title: 't', date: dayOf(i + 1) }))), today, 3).map((i) => i.cid).join() === 'x0,x1,x2');
const ics = C.buildIcs({ calName: 'テスト,カレンダー', items, today });
const text = unfold(ics);
check('CRLF で、BEGIN:VCALENDAR で始まり END:VCALENDAR で終わる', ics.startsWith('BEGIN:VCALENDAR\r\n') && ics.endsWith('END:VCALENDAR\r\n') && !/[^\r]\n/.test(ics));
check('予定の数 = 対象の作品の数（4件）・BEGIN と END が同数', (text.match(/BEGIN:VEVENT/g) || []).length === 4 && (text.match(/END:VEVENT/g) || []).length === 4);
check('カレンダー名は記号を書き換えて入る', text.includes('X-WR-CALNAME:テスト\\,カレンダー'));
check('UID は「品番@ホスト名」', text.includes('UID:soon1@fanza-ranking.pages.dev'));
check('終日の予定: 開始は発売日・終了は翌日（月またぎ 10/31 → 11/1）', text.includes('DTSTART;VALUE=DATE:20261031\r\nDTEND;VALUE=DATE:20261101'));
check('終日の予定: 年またぎ 12/31 → 1/1', text.includes('DTSTART;VALUE=DATE:20261231\r\nDTEND;VALUE=DATE:20270101'));
check('DTSTAMP は、その日の0時（同じ日なら同じ値）', text.includes('DTSTAMP:20261003T000000Z') && C.buildIcs({ calName: 'x', items, today }) === C.buildIcs({ calName: 'x', items, today }));
check('予定の題名に、作品タイトルを入れない', !/SUMMARY:[^\r\n]*(古い作品|最近の作品|今日の作品|月またぎ|年またぎ)/.test(text));
check('題名: 出演者がいれば出演者名・いなければメーカー名・どちらもなければ「FANZAの新作」', text.includes('SUMMARY:【発売】Aの新作') && text.includes('SUMMARY:【発売】メーカーXの新作') && text.includes('SUMMARY:【発売】FANZAの新作'));
check('題名: subject を指定すれば、それが入る', C.buildIcs({ calName: 'x', items, today, subject: '花子' }).includes('SUMMARY:【発売】花子の新作'));
check('説明には、タイトル・作品ID（品番を作れないとき）・リンクが入る（記号は書き換え済み）', text.includes('DESCRIPTION:最近の作品\\, セミコロン\\; あり\\n作品ID: recent1\\nhttps://fanza-ranking.pages.dev/item/recent1/'));
check('説明の品番は、作品ページと同じ形（1dldss00566 → DLDSS-566）', unfold(C.buildIcs({ calName: 'x', items: normalizeItems([{ cid: '1dldss00566', title: 'テスト', date: today }]), today })).includes('\\n品番: DLDSS-566\\n'));
check('URL の行に、作品ページのURLが入る', text.includes('URL:https://fanza-ranking.pages.dev/item/soon1/'));
const alarms = (text.match(/BEGIN:VALARM/g) || []).length;
check('通知（朝9時）は、今日以降に発売の予定だけ（3件）・発売済みの予定には付けない', alarms === 3 && text.includes('TRIGGER:PT9H'), String(alarms));
check('1行が75バイトを超えない（折り返し済み）', ics.split('\r\n').every((r) => new TextEncoder().encode(r).length <= 75));
check('作品が0件でも、正しいカレンダーになる', C.buildIcs({ calName: 'x', items: [], today }).includes('BEGIN:VCALENDAR') && !C.buildIcs({ calName: 'x', items: [], today }).includes('VEVENT'));
check('webcal のURL', C.webcalUrl('/calendar/a.ics') === 'webcal://fanza-ranking.pages.dev/calendar/a.ics' && C.webcalUrl('/x.ics', 'http://example.com') === 'webcal://example.com/x.ics');
check('カレンダーのパス', C.actressIcsPath('abc') === '/calendar/actress/abc.ics' && C.makerIcsPath('abc') === '/calendar/maker/abc.ics' && C.UPCOMING_ICS_PATH === '/calendar/upcoming.ics');

console.log('\n■ お気に入りの索引');
const idx = F.buildFavoritesIndex(items, today);
check('索引: 予約も含めて、新しい順（9/1 は32日前なので入る）', idx.items.map((i) => i.c).join() === 'soon2,soon1,today1,recent1,old1', idx.items.map((i) => i.c).join());
check('索引: ちょうど60日前(8/4)は入り、その前日(8/3)は入らない', F.buildFavoritesIndex(normalizeItems([{ cid: 'in', title: 't', date: '2026-08-04' }, { cid: 'out', title: 't', date: '2026-08-03' }]), today).items.map((i) => i.c).join() === 'in');
check('索引: 日付は generated に入る', idx.generated === today);
check('索引: 専用ページのある出演者・メーカーの {名前: 短い名前}（pages）。渡さなければ空', JSON.stringify(idx.pages) === JSON.stringify({ actress: {}, maker: {} }) && JSON.stringify(F.buildFavoritesIndex(items, today, 60, { actress: { A: 'abcdef0123' }, maker: {} }).pages) === JSON.stringify({ actress: { A: 'abcdef0123' }, maker: {} }));
check('索引: グループ → {名前: 短い名前}', JSON.stringify(F.pageSlugMap([{ name: 'A', slug: 's1' }, { name: 'B', slug: 's2' }])) === JSON.stringify({ A: 's1', B: 's2' }) && JSON.stringify(F.pageSlugMap([])) === '{}');
const one = idx.items.find((i) => i.c === 'recent1');
check('索引: 短い名前の項目（c,t,d,a,m,i）。タイトルは、幅のない空白（文節の区切り）を除くと元どおり', one && one.t.replace(/\u200b/g, '') === items.find((i) => i.cid === 'recent1').title && one.d === '2026-09-25' && one.a.join() === 'A' && one.m === 'M' && 'i' in one, JSON.stringify(one));
check('索引: メーカー「不明」は空文字にする', idx.items.find((i) => i.c === 'today1').m === '');
const attrs = F.workFavoriteAttrs(items[1]);
check('作品の☆ボタンの情報', attrs['data-fav-type'] === 'work' && attrs['data-fav-key'] === 'recent1' && attrs['data-actress'] === 'A' && attrs['data-date'] === '2026-09-25' && attrs['data-maker'] === 'M');
check('ページのパス', F.FAVORITES_PATH === '/favorites/' && F.FAVORITES_INDEX_PATH === '/data/favorites-index.json');

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
