// 日本語の文章を文節で改行させる部品（site/src/lib/phrase.js）のテスト。実行: node tests/test_phrase.mjs
// （画面での見え方・Astro の拡張が実際に動くかは、PRのビルド（tests/verify_dist.py）とプレビューで見る）
import fs from 'node:fs';
import { splitPhrases, phraseText, phraseHtml, unphraseHtml, phraseZwsp, namesPattern, MIN_JAPANESE, MAX_PHRASE, NOWRAP_MAX, ZWSP } from '../site/src/lib/phrase.js';
import { namesFromData } from '../site/src/integrations/phrase-breaks.js';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
};

console.log('■ 文節の区切り（運営者が見つけた「変な改行」の文章）');
const lead = '名前・年齢・身長・スリーサイズ・カップで、出演者を探せます。掲載作品が2本以上の人は専用ページがあり、それ以外の人はFANZAの作品一覧にリンクします。';
const parts = splitPhrases(lead);
check('区切っても、つなげると元の文章に戻る', parts.join('') === lead);
check('「出演者を」「専用ページが」「あり、」「それ以外の」「FANZAの」「リンクします。」は、途中で切れない', ['出演者を', '専用ページが', 'あり、', 'それ以外の', 'FANZAの', 'リンクします。'].every((w) => parts.some((p) => p.includes(w))), JSON.stringify(parts));
check('「探せます。」と「掲載作品が」の間・「あり、」と「それ以外の」の間で、改行できる', parts.some((p) => p.endsWith('探せます。')) && parts.some((p) => p.endsWith('あり、')), JSON.stringify(parts));
check('「あ／り」「出演者／を」のような、語の途中の区切りが無い', !parts.some((p) => p === 'り、' || p.startsWith('を探')) && !parts.some((p) => p.endsWith('専用ページがあ')));

console.log('\n■ 区切ってはいけない所');
const asc = splitPhrases('FANZAで2026-10-04に発売のDMM(https://example.com/a-b)です');
check('英数字・記号の途中では区切らない（FANZA・日付・URL）', ['FANZA', '2026-10-04', 'https://example.com/a-b'].every((w) => asc.some((p) => p.includes(w))), JSON.stringify(asc));
const kin = splitPhrases('「発売日をカレンダーで受け取る」から、その人・そのメーカーの作品だけを入れられます。ええっ！？すごーい…。');
check('行のはじめに、「、」「。」「」」「！」「ー」「っ」「・」が来る区切りが無い', kin.slice(1).every((p) => !/^[、。」！？ーっ・…）]/.test(p)), JSON.stringify(kin));
check('開きかっこ（「）のすぐあとでは区切らない', kin.every((p) => !p.endsWith('「')), JSON.stringify(kin));
const long = splitPhrases('これは区切りの無いとても長いひとつながりのひらがなです');
check(`長いひとかたまり（${MAX_PHRASE}文字より長い）は、途中にも改行できる所を足す`, long.length >= 2 && long.every((p) => p.length <= MAX_PHRASE + 2), JSON.stringify(long));
check('空の文字列は空の配列', splitPhrases('').length === 0);

console.log('\n■ 実際のデータ（作品のコメント・題名）で壊れない');
const data = JSON.parse(fs.readFileSync(new URL('../site/src/data/new_releases.json', import.meta.url), 'utf-8'));
const items = Array.isArray(data) ? data : Object.values(data.items || data);
const texts = items.flatMap((x) => [x.comment, x.title]).filter((t) => typeof t === 'string' && t);
check(`${texts.length}件の文章が、つなげると元に戻る`, texts.length > 20 && texts.every((t) => splitPhrases(t).join('') === t));
const NO_START = /^[、。，．,.）)」』】〕〉》］｝!?！？:：;；・ー…‥々ゝゞヽヾぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ‼%％]/;
const badStart = texts.flatMap((t) => splitPhrases(t).slice(1).filter((p) => NO_START.test(p)).map((p) => p.slice(0, 6)));
check('どの文章でも、区切りのあとが、行のはじめに来てはいけない文字ではない', badStart.length === 0, JSON.stringify(badStart.slice(0, 5)));

console.log('\n■ HTMLの文章の部分だけに足す');
const html = '<p class="a>b" title="日本語の説明文を入れた属性です">専用ページがあり、それ以外の人は<a href="/x">FANZAの作品一覧</a>へ。</p>';
const out = phraseHtml(html);
check('文章が <span class="ph"> で包まれ、文節の間に <wbr> が入る', /<span class="ph">専用ページが<wbr>あり、<wbr>それ以外の<wbr>人は<\/span>/.test(out), out);
check('タグの属性（> を含む値・日本語の値）は、そのまま', out.includes('<p class="a>b" title="日本語の説明文を入れた属性です">') && out.includes('<a href="/x">'), out);
check('元に戻せる（<wbr> を消し、<span class="ph"> の包みを外すと、元のHTML）', unphraseHtml(out) === html);
check('2回かけても、同じ結果（二重に包まない）', phraseHtml(out) === out);
const skip = '<script>var s="日本語のテキストを含む文字列";</script><style>.a::after{content:"日本語の文字列です"}</style><title>日本語のタイトルです</title><textarea>日本語の入力欄の中身です</textarea><button>日本語のボタンの文字です</button><pre>日本語の整形済みの文章です</pre><code>日本語のコードの文章です</code><noscript>日本語の注意書きです</noscript><svg><text>日本語のSVGの文字です</text></svg><select><option>日本語の選択肢の文字です</option></select><!-- 日本語のコメントの文章です -->';
check('script・style・title・textarea・button・pre・code・noscript・svg・select・コメントの中は、触らない', phraseHtml(skip) === skip);
check(`日本語が${MIN_JAPANESE}文字より少ない文字列（短いラベル）は、触らない`, phraseHtml('<a>発売中</a><a>予約</a>') === '<a>発売中</a><a>予約</a>');
check('英語・数字だけの文章は、触らない', phraseHtml('<p>Hello world 2026-10-04 and more text here</p>') === '<p>Hello world 2026-10-04 and more text here</p>');
const ent = phraseHtml('<p>専用ページ&amp;それ以外の人は&#12354;&#x3042;&lt;と出ます。</p>');
check('文字参照（&amp; &#12354; &lt; など）は、途中で切らない', ['&amp;', '&#12354;', '&#x3042;', '&lt;'].every((e) => ent.includes(e)) && !/&[^;<]*<wbr>/.test(ent), ent);
check('区切りが無い短い名前も、語の途中で改行されないよう、包む', phraseText('三葉ちはる') === '<span class="ph">三葉ちはる</span>', phraseText('三葉ちはる'));
check('前後の空白は、包みの外に残る', phraseText('\n  専用ページがあり、それ以外の人は \n') .startsWith('\n  <span class="ph">') && phraseText('\n  専用ページがあり、それ以外の人は \n').endsWith('</span> \n'));
check('空白のあとには <wbr> を入れない（空白で改行できるため）', !/\s<wbr>/.test(phraseText('Where is my wife？ 三葉ちはる')), phraseText('Where is my wife？ 三葉ちはる'));

console.log('\n■ 出演者名・メーカー名の途中では改行しない（運営者が見つけた「波多｜野結衣」「パラダイ｜ステレビ」のような改行）');
const names = ['青坂あおい', '波多野結衣', 'パラダイステレビ', 'グローリークエスト', '無理くりえいてぃぶ', 'S-Cute', '犬/妄想族', 'KMPVR-彩-', 'とても長い名前のメーカーの株式会社です', 'ケイ・エム・プロデュース'];
const re = namesPattern(names);
const sent = 'パラダイステレビの作品です。出演は青坂あおいさんと波多野結衣さん。グローリークエスト・無理くりえいてぃぶ・S-Cute・犬/妄想族の新作も。';
const sp = splitPhrases(sent, re);
check('区切っても、つなげると元に戻る（名前つき）', sp.join('') === sent);
check('名前（と、すぐあとの「さん」）の途中に区切りが無い', ['パラダイステレビ', '青坂あおいさん', '波多野結衣さん', 'グローリークエスト', '無理くりえいてぃぶ'].every((n) => sp.some((p) => p.includes(n))), JSON.stringify(sp));
check('名前が無いときは、いままでどおり（名前の途中で切れることがある）', splitPhrases(sent).join('｜') !== sp.join('｜'));
const hx = phraseHtml(`<p>${sent}</p><a>S-Cute</a><a>犬/妄想族</a><dd>青坂あおい</dd><p>とても長い名前のメーカーの株式会社ですの作品の説明です。</p>`, re);
check(`${NOWRAP_MAX}文字以下の名前は <span class="nb">（改行しない）で包む。英字の名前（S-Cute）や「/」入りの名前も`, ['<span class="nb">青坂あおいさん</span>', '<span class="nb">パラダイステレビ</span>', '<a><span class="nb">S-Cute</span></a>', '<span class="nb">犬/妄想族</span></span></a>', '<dd><span class="ph"><span class="nb">青坂あおい</span></span></dd>'].every((x) => hx.includes(x)), hx);
check(`${NOWRAP_MAX}文字より長い名前は包まない（狭い画面ではみ出さないように）が、途中に <wbr> も入れない`, !hx.includes('<span class="nb">とても') && hx.includes('とても長い名前のメーカーの株式会社です'), hx);
check('2回かけても同じ（名前の包みも二重にしない）', phraseHtml(hx, re) === hx);
check('元に戻せる（<span class="nb"> も外れる）', unphraseHtml(hx) === `<p>${sent}</p><a>S-Cute</a><a>犬/妄想族</a><dd>青坂あおい</dd><p>とても長い名前のメーカーの株式会社ですの作品の説明です。</p>`);
check('名前の一覧が空・1文字の名前だけなら、守る語なし（null）', namesPattern([]) === null && namesPattern(['A', '']) === null && namesPattern(null) === null);
check('名前に正規表現の記号（. * + ( ) など）が入っていても壊れない', splitPhrases('メーカー(株).*の新作です', namesPattern(['メーカー(株).*'])).join('') === 'メーカー(株).*の新作です');
check('ビルドで使う名前の一覧を、作品データから集められる（出演者・メーカー。「不明」は除く）', namesFromData().length > 20 && !namesFromData().includes('不明'));
check('作品データが読めなければ、名前の一覧は空（ビルドは止めない）', namesFromData(new URL('file:///no/such/file.json')).length === 0);

check('10文字より長い名前（ケイ・エム・プロデュース）は包まない（狭い画面ではみ出さないように）が、途中に <wbr> は入れない', !phraseHtml('<p>ケイ・エム・プロデュースの新作です。</p>', re).includes('<span class="nb">ケイ') && !phraseHtml('<p>ケイ・エム・プロデュースの新作です。</p>', re).includes('ケイ・<wbr>'));
check('文字参照（&amp; など）の中は、名前として包まない（名前が「amp」でも）', phraseHtml('<p>A&amp;Bの新作です。ampの作品です。</p>', namesPattern(['amp'])).includes('A&amp;B') && unphraseHtml(phraseHtml('<p>A&amp;Bの新作です。ampの作品です。</p>', namesPattern(['amp']))) === '<p>A&amp;Bの新作です。ampの作品です。</p>');
check('絵文字のあとの「～」も、文字を壊さない', !/[\ud800-\udbff](?![\udc00-\udfff])/.test(phraseHtml('<p>美少女の作品です💕～最高の一本</p>')) && unphraseHtml(phraseHtml('<p>美少女の作品です💕～最高の一本</p>')) === '<p>美少女の作品です💕～最高の一本</p>');
check('名前の中の「～」でも、包みが入れ子にならず、2回かけても同じ', (() => { const r2 = namesPattern(['まりん～']); const h = phraseHtml('<p>出演はまりん～さんの新作です。</p>', r2); return !/<span class="nb">[^<]*<span/.test(h) && phraseHtml(h, r2) === h && unphraseHtml(h) === '<p>出演はまりん～さんの新作です。</p>'; })());
const dates = splitPhrases('発売日は2026年10月3日から2026年11月3日です。収録時間は約246分で、3本あります。');
check('日付・数字と単位は、途中で区切らない（「2026年11／月」「246／分」にしない）', ['2026年10月3日', '2026年11月3日', '約246分', '3本'].every((w) => dates.some((p) => p.includes(w))), JSON.stringify(dates));

console.log('\n■ 伏せ字（○●）のまわりでは改行しない');
const cz = splitPhrases('剥き出しチ○ポ中毒とJ●痴●ガチナマ路線の作品です');
check('「チ○ポ」「J●痴●」の途中で区切らない', cz.some((p) => p.includes('チ○ポ')) && cz.some((p) => p.includes('J●痴●')), JSON.stringify(cz));

console.log('\n■ ブラウザで作る文章（作品検索・お気に入り）用: 幅のない空白（U+200B）で区切る');
const z = phraseZwsp('専用ページがあり、それ以外の人はFANZAの作品一覧にリンクします。');
check('文節の区切りに U+200B が入り、取り除くと元に戻る', z.includes(ZWSP) && z.split(ZWSP).join('') === '専用ページがあり、それ以外の人はFANZAの作品一覧にリンクします。', JSON.stringify(z));
check('名前の途中には入れない', !phraseZwsp('出演は青坂あおいさんの作品です', re).split(ZWSP).some((p) => p.endsWith('青坂') || p.endsWith('青坂あ')));
check('短い文字列・空は、そのまま', phraseZwsp('発売中') === '発売中' && phraseZwsp('') === '' && phraseZwsp(null) === '');

console.log('\n■ 「～」の前では改行しない（ブラウザは keep-all でも「～」の前で改行することがある）');
const tl = '<p>お客様のザーメンを気持ちよ～く膣奥中出し アングルVR ～精子を全搾り</p>';
const th = phraseHtml(tl);
check('「～」は、前の1文字（と、あいだの空白）と一緒に <span class="nb"> で包む', th.includes('<span class="nb">よ～</span>') && th.includes('<span class="nb">R ～</span>'), th);
check('元に戻せる・2回かけても同じ', unphraseHtml(th) === tl && phraseHtml(th) === th);
const tz = phraseZwsp('お客様のザーメンを気持ちよ～く膣奥中出し アングルVR ～精子を全搾り');
check('ブラウザで作る文章では、「～」の前に改行を止める見えない文字（U+2060）・改行しない空白（U+00A0）を入れる', tz.includes('よ\u2060～') && tz.includes('R\u00a0～') && !/\u200b[～〜]/.test(tz), JSON.stringify(tz));

console.log(`\n=== ${pass}/${pass + fail} 合格 ===`);
process.exit(fail ? 1 : 0);
