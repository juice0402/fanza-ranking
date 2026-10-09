// 作品検索（/search/）。キーワード（タイトル・出演者・メーカー・品番・ジャンル）・ジャンル（タグ）・発売の状態で絞り込む。
// 検索のもとになるデータは /data/items-index.json（ビルドごとに作る。短い名前の項目は site/src/lib/search.js の説明を参照）。
// 「VR作品を隠す」は、サイト全体のスイッチ（site/public/vr-filter.js）と同じ状態を使う。
// 条件は URL にも反映する（?q=…&tag=…）。作品ページのジャンルから、この URL で飛んでくる。
// JavaScript が使えない・索引を読めないときは、ページに最初から載っている案内（過去の作品・出演者・メーカーへのリンク）のまま。
(function () {
  var PAGE_SIZE = 24; // 1回に出す作品の数（「もっと見る」で増やす）
  var TAGS_COLLAPSED = 14; // ジャンルを、最初に出す数（選んだものは、これとは別に必ず出す）
  // 条件なしのときの本数の代わり（索引は最大3,000本なので、条件なしの本数が「掲載している作品の数」と誤解されるため。
  // 本数は、キーワード・ジャンル・発売の状態で絞り込んだときだけ出す。運営者の希望。2026-10-09。site/src/lib/search.js の SEARCH_COUNT_BLANK と同じ）
  var COUNT_BLANK = 'ーー';
  var COUNT_BLANK_NOTE = '条件で絞り込むと、本数が出ます'; // 読み上げ用（画面には出さない）
  var DMM = ['dmm.co.jp'];
  var DMM_IMAGE_PREFIX = 'https://pics.dmm.co.jp/';
  var CID = /^[A-Za-z0-9_-]+$/;
  var DAY = /^\d{4}-\d{2}-\d{2}$/;
  var SEP = '\u0001'; // 検索用の文字をつなぐ区切り（キーワードが、項目をまたいで当たらないように）

  // ------------------------------------------------------------
  // 部品（画面に依存しない。tests/test_search.mjs でテストしている）
  // ------------------------------------------------------------

  // 名前の照らし合わせ用に、全角/半角・大文字小文字・カタカナ/ひらがな・空白や中点の違いをそろえる（出演者検索と同じ決まり）
  function normalizeText(text) {
    var s = String(text == null ? '' : text);
    if (s.normalize) s = s.normalize('NFKC');
    s = s.toLowerCase().replace(/[ァ-ヶ]/g, function (c) {
      return String.fromCharCode(c.charCodeAt(0) - 0x60);
    });
    // 品番の「-」の有無（DLDSS-566 / dldss566）と、タイトルの文節の区切り（幅のない空白 U+200B）も、そろえる
    return s.replace(/[\s　・·.・\-\u200b\u2060]/g, '');
  }

  // キーワードを、空白で区切った語に分ける（全部の語を含む作品だけを探す）
  function splitTerms(q) {
    return String(q == null ? '' : q)
      .split(/[\s　]+/)
      .map(normalizeText)
      .filter(Boolean);
  }

  // 日本時間の今日 "YYYY-MM-DD"
  function jstToday(nowMs) {
    return new Date(nowMs + 9 * 3600 * 1000).toISOString().slice(0, 10);
  }

  function dayNumber(s) {
    return Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / 86400000;
  }

  // 'new'（発売から数日）/ 'wait'（予約）/ ''
  function statusOf(day, today, newDays) {
    if (day > today) return 'wait';
    return dayNumber(today) - dayNumber(day) <= newDays ? 'new' : '';
  }

  // 画像・リンクとして使ってよいURLか（FANZA(DMM)の https だけ）。出演者検索（actress-search.js）と同じ決まり
  function safeUrl(url, hosts) {
    if (typeof url !== 'string') return '';
    var m = /^https:\/\/([A-Za-z0-9.-]+)(?::\d{1,5})?(?:[/?#]|$)/.exec(url);
    if (!m || /[\\\s\x00-\x1f\x7f]/.test(url)) return '';
    var host = m[1].toLowerCase();
    var ok = hosts.some(function (h) {
      return host === h || host.slice(-(h.length + 1)) === '.' + h;
    });
    return ok ? url : '';
  }

  // 索引の画像（DMMのURLの先頭を省いた形。https から始まるものはそのまま）→ 使ってよいURL。使えなければ ''
  function imageUrl(i) {
    if (typeof i !== 'string' || !i) return '';
    return safeUrl(/^https:/.test(i) ? i : DMM_IMAGE_PREFIX + i, DMM);
  }

  // 索引の1行の画像（i が無い行は、決まった形 digital/video/作品ID/作品IDpl.jpg。site/src/lib/search.js の standardImage と同じ）
  function rowImage(row) {
    if (!row || typeof row !== 'object') return '';
    if (row.i === undefined) return CID.test(String(row.c || '')) ? imageUrl('digital/video/' + row.c + '/' + row.c + 'pl.jpg') : '';
    return imageUrl(row.i);
  }

  // パッケージ画像（…pl.jpg）→ 表紙だけの軽い画像（…ps.jpg）。FANZA の画像でなければ、そのまま（site/src/lib/items.js の smallImage と同じ）
  function smallImageUrl(url) {
    return /^https:\/\/pics\.dmm\.co\.jp\/.+pl\.jpg$/.test(String(url || '')) ? String(url).replace(/pl\.jpg$/, 'ps.jpg') : String(url || '');
  }

  // スマホ（画面の幅が THUMB_MEDIA）のときだけ読む、表紙の小さい版
  // （運営者の希望「スマホのサムネは画素数を落として最高速化」。2026-10-07。site/src/lib/items.js の THUMB_MEDIA・tinyImage と同じ）
  var THUMB_MEDIA = '(max-width: 480px)';
  // 2026-10-09 から、動画の表紙は FANZA の「縮めて返す版」の幅200（運営者の「少し粗すぎた」。前は …pt.jpg 90×122）。
  // ゲームなど、ほかの FANZA の画像は表紙（…ps.jpg）。site/src/lib/items.js の tinyImage と同じ
  var AWS_IMG = 'https://awsimgsrc.dmm.co.jp/pics_dig/';
  function tinyImageUrl(url) {
    var s = String(url || '');
    if (/^https:\/\/pics\.dmm\.co\.jp\/digital\/video\/[^?#]+p[ls]\.jpg$/.test(s)) return AWS_IMG + s.slice(23).replace(/p[ls]\.jpg$/, 'ps.jpg') + '?w=200&q=75';
    return /^https:\/\/pics\.dmm\.co\.jp\/[^?#]+pl\.jpg$/.test(s) ? s.replace(/pl\.jpg$/, 'ps.jpg') : s;
  }

  // 小さな表紙（site/src/components/Thumb.astro の kind="tiny" と同じ形）: スマホは <picture> の <source> で縮めた版（tinyImageUrl）、ほかは …ps.jpg。
  // 読めなければ、<source> を外して ps に、ps も読めなければパッケージ画像（…pl.jpg）に戻し、それも読めなければ隠す（items.js の THUMB_ONERROR と同じ）
  function thumbImage(src) {
    var img = document.createElement('img');
    img.className = 'item-img is-small';
    img.alt = '';
    img.loading = 'lazy';
    img.decoding = 'async';
    img.addEventListener('error', function () {
      var source = img.previousElementSibling;
      if (source && source.tagName === 'SOURCE' && window.matchMedia && window.matchMedia(source.media).matches) {
        source.parentNode.removeChild(source);
        img.classList.remove('has-small');
      } else if (/ps\.jpg$/.test(img.src)) {
        img.src = img.src.replace(/ps\.jpg$/, 'pl.jpg');
        img.classList.remove('is-small');
      } else {
        img.style.visibility = 'hidden';
      }
    });
    var small = tinyImageUrl(src);
    var box = img;
    if (small !== src) {
      box = el('picture', 'pic');
      var source = document.createElement('source');
      source.media = THUMB_MEDIA;
      source.srcset = small;
      box.appendChild(source);
      box.appendChild(img);
    }
    img.src = src;
    return box;
  }

  // 索引の1行が、使える形か
  function isRow(row) {
    return Boolean(
      row &&
        typeof row === 'object' &&
        typeof row.c === 'string' &&
        CID.test(row.c) &&
        typeof row.t === 'string' &&
        row.t &&
        typeof row.d === 'string' &&
        DAY.test(row.d) &&
        Array.isArray(row.a) &&
        Array.isArray(row.g)
    );
  }

  // 検索用の文字を、行ごとに1回だけ作る（タイトル・出演者・メーカー・品番・ジャンル・出演者/メーカー/ジャンルの読みがな）
  // yomi: 索引の { 名前: 読み }（ひらがなで打っても見つかるように。2026-10-10）
  function prepare(rows, genres, yomi) {
    var dict = yomi && typeof yomi === 'object' ? yomi : {};
    function reading(name) {
      var r = Object.prototype.hasOwnProperty.call(dict, name) ? dict[name] : '';
      return typeof r === 'string' && r ? SEP + normalizeText(r) : '';
    }
    rows.forEach(function (row) {
      var names = row.g.map(function (n) {
        return genres[n] || '';
      });
      var yomiText = row.a.map(reading).join('') + reading(row.m) + names.map(reading).join('');
      row._h = normalizeText(row.t) + SEP + row.a.map(normalizeText).join(SEP) + SEP + normalizeText(row.m) + SEP + normalizeText(row.c) + SEP + normalizeText(typeof row.p === 'string' ? row.p : '') + SEP + names.map(normalizeText).join(SEP) + yomiText;
    });
    return rows;
  }

  // 条件: { terms: [語], tags: [ジャンルの番号], status: ''|'released'|'upcoming', sort: 'new'|'old'|'popnew'|'pop' }
  // opts: { today, hideVr, onlySolo }（onlySolo: 単体作品（索引の o:1）だけ）
  function matches(row, state, opts, ignoreTags) {
    if (opts.hideVr && row.v === 1) return false;
    if (opts.onlySolo && row.o !== 1) return false;
    if (state.status === 'released' && row.d > opts.today) return false;
    if (state.status === 'upcoming' && row.d <= opts.today) return false;
    var h = row._h || '';
    for (var i = 0; i < state.terms.length; i++) {
      if (h.indexOf(state.terms[i]) < 0) return false;
    }
    if (!ignoreTags) {
      for (var j = 0; j < state.tags.length; j++) {
        if (row.g.indexOf(state.tags[j]) < 0) return false;
      }
    }
    return true;
  }

  function newer(a, b) {
    return a.d < b.d ? 1 : a.d > b.d ? -1 : a.c < b.c ? -1 : a.c > b.c ? 1 : 0;
  }

  function older(a, b) {
    return a.d < b.d ? -1 : a.d > b.d ? 1 : a.c < b.c ? -1 : a.c > b.c ? 1 : 0;
  }

  // 人気順（索引の r: 全体の人気順・n: 新着の人気順）。順位の無い作品は、そのあとに新しい順
  function byRank(key) {
    return function (a, b) {
      var x = typeof a[key] === 'number' ? a[key] : Infinity;
      var y = typeof b[key] === 'number' ? b[key] : Infinity;
      return x < y ? -1 : x > y ? 1 : newer(a, b);
    };
  }

  // 評価が高い順（索引の s: レビューの平均×100・sc: 件数。2026-10-10）: レビューが3件以上の作品を、件数でならした評価の高い順
  // （lib/reviews.js の reviewScore と同じ考え方。全体の平均は 4.2 とみなす）。3件に満たない・評価の無い作品は、そのあとに新しい順
  function reviewScore(row) {
    if (typeof row.s !== 'number' || typeof row.sc !== 'number' || row.sc < 3) return -1;
    return (row.sc * row.s / 100 + 10 * 4.2) / (row.sc + 10);
  }
  function byReview(a, b) {
    var x = reviewScore(a);
    var y = reviewScore(b);
    return x > y ? -1 : x < y ? 1 : newer(a, b);
  }

  // 並び順: new 新しい順 / old 古い順 / popnew 人気順（新着）/ pop 人気順（全体）/ review 評価が高い順
  var SORTS = { new: newer, old: older, popnew: byRank('n'), pop: byRank('r'), review: byReview };
  function sortOf(name) {
    return Object.prototype.hasOwnProperty.call(SORTS, name) ? name : 'new';
  }

  // 条件に合う作品（並べ替え済み）
  function filterRows(rows, state, opts) {
    return rows
      .filter(function (row) {
        return matches(row, state, opts, false);
      })
      .sort(SORTS[sortOf(state.sort)]);
  }

  // ジャンルごとの「それを足したときに残る作品の数」。選んでいるジャンルは、いまの結果の数と同じ（結果は、選んだものを全部含む作品だけのため）
  function facetCounts(rows, state, opts, genreCount) {
    var counts = [];
    for (var i = 0; i < genreCount; i++) counts.push(0);
    var total = 0;
    rows.forEach(function (row) {
      if (!matches(row, state, opts, false)) return;
      total++;
      row.g.forEach(function (n) {
        if (n >= 0 && n < genreCount) counts[n]++;
      });
    });
    return { counts: counts, total: total };
  }

  // 見つかった作品（filterRows の結果）の、ジャンルごとの本数。facetCounts と同じ数（結果は、選んだジャンルを全部含む作品なので）。
  // 絞り込みを2回しないで済む（3,000本を、もう一度しらべない。2026-10-07）
  function genreCounts(found, genreCount) {
    var counts = [];
    for (var i = 0; i < genreCount; i++) counts.push(0);
    for (var r = 0; r < found.length; r++) {
      var g = found[r].g;
      for (var j = 0; j < g.length; j++) if (g[j] >= 0 && g[j] < genreCount) counts[g[j]]++;
    }
    return counts;
  }

  // URL の ?q=…&tag=…&st=…&sort=… → 条件（ジャンルは名前から番号にする。知らない名前は捨てる）。q は入力欄に戻す元の文字
  function parseQuery(search, genres) {
    var params = new URLSearchParams(String(search || ''));
    var tags = [];
    params.getAll('tag').forEach(function (name) {
      var n = genres.indexOf(name);
      if (n >= 0 && tags.indexOf(n) < 0) tags.push(n);
    });
    var st = params.get('st');
    return {
      q: (params.get('q') || '').slice(0, 100),
      tags: tags,
      status: st === 'released' || st === 'upcoming' ? st : '',
      sort: sortOf(params.get('sort')),
    };
  }

  // 条件 → URL の ?… の部分（条件が無ければ ''）
  function buildQuery(form, genres) {
    var parts = [];
    var q = String(form.q || '').trim();
    if (q) parts.push('q=' + encodeURIComponent(q));
    (form.tags || []).forEach(function (n) {
      if (genres[n]) parts.push('tag=' + encodeURIComponent(genres[n]));
    });
    if (form.status === 'released' || form.status === 'upcoming') parts.push('st=' + form.status);
    if (sortOf(form.sort) !== 'new') parts.push('sort=' + form.sort);
    return parts.length ? '?' + parts.join('&') : '';
  }

  // 最初に出すジャンルの番号。選んだもの + 結果が1本以上あるものを、並び順（作品の多い順）のまま limit 個まで。expanded なら全部
  function visibleTags(counts, selected, limit, expanded) {
    var out = [];
    var plain = 0;
    for (var n = 0; n < counts.length; n++) {
      if (selected.indexOf(n) >= 0 || expanded) {
        out.push(n);
      } else if (counts[n] > 0 && plain < limit) {
        out.push(n);
        plain++;
      }
    }
    return out;
  }

  // 一覧に出す出演者（先頭から max 人）と、出しきれない人数（オムニバスなど出演者が多い作品で、カードが長くならないように。
  // max は site/src/config.js の CAST_LIMIT と同じ3人。tests で突き合わせている）
  var CAST_LIMIT = 3;
  function castShown(list, max) {
    var names = list.slice(0, max);
    return { names: names, more: list.length - names.length };
  }

  // 絞り込みの条件（キーワード・ジャンル・発売の状態）が1つでもあるか。並び順は絞り込まないので数えない。
  // 条件が無いあいだは、本数を出さない（COUNT_BLANK）
  function isNarrowed(state) {
    return !!state && ((state.terms && state.terms.length > 0) || (state.tags && state.tags.length > 0) || !!state.status);
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      smallImageUrl: smallImageUrl,
      tinyImageUrl: tinyImageUrl,
      THUMB_MEDIA: THUMB_MEDIA,
      rowImage: rowImage,
      castShown: castShown,
      CAST_LIMIT: CAST_LIMIT,
      isNarrowed: isNarrowed,
      COUNT_BLANK: COUNT_BLANK,
      COUNT_BLANK_NOTE: COUNT_BLANK_NOTE,
      normalizeText: normalizeText,
      splitTerms: splitTerms,
      jstToday: jstToday,
      statusOf: statusOf,
      safeUrl: safeUrl,
      imageUrl: imageUrl,
      isRow: isRow,
      prepare: prepare,
      filterRows: filterRows,
      facetCounts: facetCounts,
      genreCounts: genreCounts,
      parseQuery: parseQuery,
      buildQuery: buildQuery,
      visibleTags: visibleTags,
      PAGE_SIZE: PAGE_SIZE,
      TAGS_COLLAPSED: TAGS_COLLAPSED,
    }; // tests/test_search.mjs 用
    return;
  }
  if (typeof document === 'undefined') return;

  // ------------------------------------------------------------
  // 画面の動き
  // ------------------------------------------------------------
  var root = document.getElementById('work-search');
  if (!root) return;
  var form = root.querySelector('form');
  var tagList = document.getElementById('ws-tag-list');
  var tagMore = document.getElementById('ws-tag-more');
  var count = document.getElementById('ws-count');
  var list = document.getElementById('ws-list');
  var more = document.getElementById('ws-more');
  var fallback = document.getElementById('ws-fallback');
  var filters = document.getElementById('ws-filters'); // ジャンル・発売・並び順の、たためる欄（無くても動く）
  var filterNote = document.getElementById('ws-filter-note');
  var indexUrl = root.getAttribute('data-index');
  if (!form || !tagList || !tagMore || !count || !list || !more || !indexUrl) return;

  var rows = [];
  var genres = [];
  var newDays = 6;
  var tagButtons = [];
  var selected = [];
  var expanded = false;
  var shown = PAGE_SIZE;
  var ready = false; // 索引を読み終えたか
  var TYPING_WAIT_MS = 180; // キーワードの欄: 打ち終わってから、この時間たったら絞り込む（1文字ごとに作り直さない。2026-10-07）

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function opts() {
    return { today: jstToday(Date.now()), hideVr: document.documentElement.classList.contains('hide-vr'), onlySolo: document.documentElement.classList.contains('only-solo') };
  }

  function readState() {
    return {
      terms: splitTerms(form.elements.q.value),
      tags: selected,
      status: form.elements.status.value,
      sort: form.elements.sort.value,
    };
  }

  function jp(day) {
    return Number(day.slice(0, 4)) + '年' + Number(day.slice(5, 7)) + '月' + Number(day.slice(8, 10)) + '日';
  }

  // 名前を並べる。短い名前（10文字まで）は、途中で改行しない（.nb）。ビルドの phrase.js と同じ考え方
  function names(parent, list, sep, empty) {
    if (!list.length && empty) parent.appendChild(document.createTextNode(empty));
    list.forEach(function (name, i) {
      if (i > 0) parent.appendChild(document.createTextNode(sep));
      parent.appendChild(el('span', name.length <= 10 ? 'nb' : '', name));
    });
    return parent;
  }

  function card(row, today) {
    var li = el('li', 'ws-row');
    li.setAttribute('data-c', row.c);
    var article = el('article', 'item');
    var href = '/item/' + row.c + '/';

    var cover = el('a', 'item-cover');
    cover.href = href;
    cover.tabIndex = -1;
    cover.setAttribute('aria-hidden', 'true');
    // 結果のサムネは小さいので、表紙だけの軽い画像（…ps.jpg。スマホは縮めた版）
    var src = smallImageUrl(rowImage(row));
    if (src) cover.appendChild(thumbImage(src));
    var status = statusOf(row.d, today, newDays);
    if (status === 'new') cover.appendChild(el('span', 'pop pop-new', '新作'));
    if (status === 'wait') cover.appendChild(el('span', 'pop pop-wait', '予約'));
    article.appendChild(cover);

    var heading = el('h3', 'item-title');
    var link = el('a', 'item-title-link ph-js', row.t); // ph-js: 文節の区切り（索引のタイトルに入っている U+200B）の所だけで改行する
    link.href = href;
    heading.appendChild(link);
    article.appendChild(heading);

    var cast = row.a.filter(function (name) {
      return typeof name === 'string' && name;
    });
    var shown = castShown(cast, CAST_LIMIT);
    var castLine = names(el('p', 'item-cast ph-js'), shown.names, '、', '出演者の記載なし');
    if (shown.more > 0) castLine.appendChild(document.createTextNode(' ほか' + shown.more + '名'));
    article.appendChild(castLine);
    var meta = el('p', 'item-meta ph-js', jp(row.d) + '発売' + (row.m ? '・' : ''));
    if (row.m) names(meta, [row.m], '', '');
    article.appendChild(meta);
    li.appendChild(article);
    return li;
  }

  function writeUrl() {
    try {
      var query = buildQuery({ q: form.elements.q.value, tags: selected, status: form.elements.status.value, sort: form.elements.sort.value }, genres);
      window.history.replaceState(null, '', window.location.pathname + query);
    } catch (e) {}
  }

  function updateTags(counts) {
    var visible = visibleTags(counts, selected, TAGS_COLLAPSED, expanded);
    var focused = document.activeElement;
    var show = {};
    visible.forEach(function (n) {
      show[n] = true;
    });
    // 変わったところだけ書きかえる（ジャンルは200以上あり、毎回すべてを書きかえると、スマホで描き直しが重かった。2026-10-07）
    tagButtons.forEach(function (button, n) {
      var on = selected.indexOf(n) >= 0;
      // 隠すのは外側の li（隠れた li に、並びの間隔が残らないように）。いま押したボタンは隠さない（フォーカスが、ページの先頭に飛ばないように）
      var hide = !show[n] && button !== focused;
      if (button.parentNode.hidden !== hide) button.parentNode.hidden = hide;
      var pressed = on ? 'true' : 'false';
      if (button.getAttribute('aria-pressed') !== pressed) button.setAttribute('aria-pressed', pressed);
      var off = !on && counts[n] === 0; // 足すと0本になるジャンルは、押せなくする
      if (button.disabled !== off) button.disabled = off;
      var label = button.querySelector('.tag-count');
      var text = String(counts[n]);
      if (label.textContent !== text) label.textContent = text;
    });
    var hiddenCount = tagButtons.length - visible.length;
    tagMore.hidden = !expanded && hiddenCount === 0;
    tagMore.textContent = expanded ? 'ジャンルをたたむ' : 'すべてのジャンル';
    tagMore.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    tagList.classList.toggle('is-open', expanded); // スマホ: たたんでいるあいだは横に流れる1行、「すべてのジャンル」で折り返して全部
  }

  // 3桁ごとのカンマ（「3,000」）。toLocaleString は、はじめて使うときにスマホで0.1秒近くかかっていたので使わない（2026-10-07）
  function withCommas(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  // いまの条件の印（同じ印なら、作り直さない。ラジオボタンなどは「input」と「change」の両方が来るため）
  function stateKey(o) {
    return [buildQuery({ q: form.elements.q.value, tags: selected, status: form.elements.status.value, sort: form.elements.sort.value }, genres), shown, o.hideVr ? 1 : 0, o.onlySolo ? 1 : 0, expanded ? 1 : 0, o.today].join('|');
  }

  function countHtml(n, o, narrowed) {
    var vrNote = o.hideVr && o.onlySolo ? '（単体作品・VR作品を除く）' : o.onlySolo ? '（単体作品のみ）' : o.hideVr ? '（VR作品を除く）' : '';
    var offNote = (o.onlySolo ? '単体作品だけ表示しています。' : '') + (o.hideVr ? 'VR作品は隠しています。' : '');
    // 見つかった本数は、大きな数字で（「120本」。2026-10-06）。条件なしのときは「ーー本」（掲載数と誤解されないように。2026-10-09。
    // ページに入っている形（site/src/pages/search/index.astro）と同じ）
    count.textContent = '';
    if (n && !narrowed) {
      var shown = el('span');
      shown.setAttribute('aria-hidden', 'true');
      shown.appendChild(el('strong', 'ws-num ws-num-blank', COUNT_BLANK));
      shown.appendChild(document.createTextNode('本' + vrNote));
      count.appendChild(shown);
      count.appendChild(el('span', 'visually-hidden', COUNT_BLANK_NOTE));
    } else if (n) {
      count.appendChild(el('strong', 'ws-num', withCommas(n)));
      count.appendChild(document.createTextNode('本' + vrNote));
    } else {
      count.textContent = '条件に合う作品がありません。条件をゆるめてみてね。' + offNote;
    }
  }

  var lastKey = '';
  function render() {
    var o = opts();
    var key = stateKey(o);
    if (key === lastKey) return;
    if (!ready) {
      // 索引がまだ届いていない: 条件は覚えておき（フォームに残っている）、届いたら作る
      count.textContent = '読み込み中…';
      list.setAttribute('aria-busy', 'true');
      return;
    }
    lastKey = key;
    list.removeAttribute('aria-busy');
    list.removeAttribute('data-first'); // ページに入っていた「はじめの一覧」ではなくなる（CSS の「単体作品のみ」の仮の隠し方を外す）
    var state = readState();
    var found = filterRows(rows, state, o);
    updateTags(genreCounts(found, genres.length));
    var visible = found.slice(0, shown);
    list.textContent = '';
    var frag = document.createDocumentFragment();
    visible.forEach(function (row) {
      frag.appendChild(card(row, o.today));
    });
    list.appendChild(frag);
    countHtml(found.length, o, isNarrowed(state));
    more.hidden = found.length <= visible.length;
    if (filterNote) {
      var active = selected.length + (state.status ? 1 : 0) + (state.sort !== 'new' ? 1 : 0);
      filterNote.textContent = active ? '（' + active + '件を指定中）' : '';
    }
    writeUrl();
  }

  function onChange() {
    shown = PAGE_SIZE;
    render();
  }

  function toggleTag(n) {
    var at = selected.indexOf(n);
    if (at >= 0) selected = selected.filter(function (x) {
      return x !== n;
    });
    else selected = selected.concat([n]);
    onChange();
  }

  // ジャンルのボタン（ページに入っているものを使う。索引のジャンルと違うときだけ作り直す）
  function buildTagButtons() {
    tagList.textContent = '';
    tagButtons = genres.map(function (name, n) {
      var li = el('li');
      var button = el('button', 'tag-btn');
      button.type = 'button';
      button.setAttribute('aria-pressed', 'false');
      button.setAttribute('data-n', String(n));
      button.setAttribute('data-name', name);
      button.appendChild(el('span', 'tag-name', name));
      button.appendChild(el('span', 'tag-count', '0'));
      li.appendChild(button);
      tagList.appendChild(li);
      return button;
    });
  }
  tagList.addEventListener('click', function (event) {
    var button = event.target && event.target.closest ? event.target.closest('.tag-btn') : null;
    if (!button || button.disabled) return;
    var n = parseInt(button.getAttribute('data-n'), 10);
    if (n >= 0) toggleTag(n);
  });

  var typingTimer = 0;
  form.addEventListener('input', function (event) {
    clearTimeout(typingTimer);
    if (event.target && event.target.name === 'q') typingTimer = setTimeout(onChange, TYPING_WAIT_MS);
    else onChange();
  });
  form.addEventListener('change', function (event) {
    if (event.target && event.target.name === 'q') return; // キーワードの欄は input で扱う
    clearTimeout(typingTimer);
    onChange();
  });
  form.addEventListener('submit', function (event) {
    event.preventDefault();
    clearTimeout(typingTimer);
    onChange();
  });
  form.addEventListener('reset', function () {
    clearTimeout(typingTimer);
    selected = [];
    setTimeout(onChange, 0); // リセットで項目が空に戻ったあとに、結果を作り直す
  });
  tagMore.addEventListener('click', function () {
    expanded = !expanded;
    if (ready) render();
    else {
      // 索引を待つあいだも、ジャンルの全部の表示は切りかえられる（ページに入っているボタンで）
      tagButtons.forEach(function (b) {
        b.parentNode.hidden = !expanded && b.parentNode.hasAttribute('data-was-hidden');
      });
      tagMore.textContent = expanded ? 'ジャンルをたたむ' : 'すべてのジャンル';
      tagMore.setAttribute('aria-expanded', expanded ? 'true' : 'false');
      tagList.classList.toggle('is-open', expanded);
    }
  });
  more.addEventListener('click', function () {
    var before = shown;
    shown += PAGE_SIZE;
    render();
    // 増えた分の先頭の作品へ、フォーカスを移す（「もっと見る」が消えても、フォーカスがページの先頭に飛ばないように）
    var first = list.children[before] && list.children[before].querySelector('.item-title-link');
    if (first) first.focus();
  });
  document.addEventListener('vrfilterchange', onChange); // 「VR作品を隠す」スイッチが押されたとき

  // ページに入っている「はじめの一覧」・ジャンルのボタンを使う（索引を待たずに、検索の部品はページを開いたときから使える。2026-10-07）
  tagButtons = Array.prototype.slice.call(tagList.querySelectorAll('.tag-btn'));
  tagButtons.forEach(function (b) {
    if (b.parentNode.hidden) b.parentNode.setAttribute('data-was-hidden', '');
  });
  genres = tagButtons.map(function (b) {
    return b.getAttribute('data-name') || '';
  });
  var firstQuery = parseQuery(window.location.search, genres);
  form.elements.q.value = firstQuery.q;
  form.elements.status.value = firstQuery.status;
  form.elements.sort.value = firstQuery.sort;
  selected = firstQuery.tags;
  // 広い画面か、ジャンル・発売・並び順の指定つきで開いたときは、たためる欄を最初から開いておく
  var wide = typeof window.matchMedia === 'function' && window.matchMedia('(min-width: 720px)').matches;
  if (filters && (wide || firstQuery.tags.length || firstQuery.status || firstQuery.sort !== 'new')) filters.open = true;
  var o0 = opts();
  var prerendered = list.getAttribute('data-first') === '1' && list.getAttribute('data-today') === o0.today && !o0.hideVr && !o0.onlySolo;
  if (prerendered && buildQuery({ q: firstQuery.q, tags: selected, status: firstQuery.status, sort: firstQuery.sort }, genres) === '') lastKey = stateKey(o0);
  else render(); // 条件つき・絞り込みスイッチが入っているとき: 「読み込み中…」にして、索引が届いたら作る

  fetch(indexUrl, { credentials: 'same-origin' })
    .then(function (res) {
      if (!res.ok) throw new Error('status ' + res.status);
      return res.json();
    })
    .then(function (data) {
      var indexGenres = data && Array.isArray(data.genres) ? data.genres.filter(function (g) { return typeof g === 'string'; }) : [];
      rows = data && Array.isArray(data.items) ? data.items.filter(isRow) : [];
      if (data && typeof data.newDays === 'number') newDays = data.newDays;
      if (!rows.length) throw new Error('empty');
      prepare(rows, indexGenres, data.yomi);
      // ページのジャンルのボタンが、索引のジャンルと違えば作り直す（選んでいるジャンルは、名前で引き継ぐ）
      if (indexGenres.join('\n') !== genres.join('\n')) {
        var names = selected.map(function (n) {
          return genres[n];
        });
        genres = indexGenres;
        selected = names.map(function (name) {
          return genres.indexOf(name);
        }).filter(function (n) {
          return n >= 0;
        });
        buildTagButtons();
        lastKey = '';
      }
      ready = true;
      if (lastKey) {
        // はじめの一覧が、ブラウザで作る一覧と同じか確かめる（違えば作り直す）
        var o = opts();
        var want = filterRows(rows, readState(), o).slice(0, shown);
        var cells = list.children;
        var same = cells.length === want.length && o.today === list.getAttribute('data-today');
        for (var i = 0; same && i < cells.length; i++) same = cells[i].getAttribute('data-c') === want[i].c;
        if (!same) lastKey = '';
      }
      render();
    })
    .catch(function () {
      // 読み込めなかったとき: 検索の部品を隠し、ほかの探し方の案内を出す
      root.hidden = true;
      if (fallback) fallback.classList.add('is-fallback');
    });
})();
