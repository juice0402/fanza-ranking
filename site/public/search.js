// 作品検索（/search/）。キーワード（タイトル・出演者・メーカー・品番・ジャンル）・ジャンル（タグ）・発売の状態で絞り込む。
// 検索のもとになるデータは /data/items-index.json（ビルドごとに作る。短い名前の項目は site/src/lib/search.js の説明を参照）。
// 「VR作品を隠す」は、サイト全体のスイッチ（site/public/vr-filter.js）と同じ状態を使う。
// 条件は URL にも反映する（?q=…&tag=…）。作品ページのジャンルから、この URL で飛んでくる。
// JavaScript が使えない・索引を読めないときは、ページに最初から載っている案内（過去の作品・出演者・メーカーへのリンク）のまま。
(function () {
  var PAGE_SIZE = 24; // 1回に出す作品の数（「もっと見る」で増やす）
  var TAGS_COLLAPSED = 14; // ジャンルを、最初に出す数（選んだものは、これとは別に必ず出す）
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

  // 検索用の文字を、行ごとに1回だけ作る（タイトル・出演者・メーカー・品番・ジャンル）
  function prepare(rows, genres) {
    rows.forEach(function (row) {
      var names = row.g.map(function (n) {
        return genres[n] || '';
      });
      row._h = normalizeText(row.t) + SEP + row.a.map(normalizeText).join(SEP) + SEP + normalizeText(row.m) + SEP + normalizeText(row.c) + SEP + normalizeText(typeof row.p === 'string' ? row.p : '') + SEP + names.map(normalizeText).join(SEP);
    });
    return rows;
  }

  // 条件: { terms: [語], tags: [ジャンルの番号], status: ''|'released'|'upcoming', sort: 'new'|'old' }
  // opts: { today, hideVr }
  function matches(row, state, opts, ignoreTags) {
    if (opts.hideVr && row.v === 1) return false;
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

  // 条件に合う作品（並べ替え済み）
  function filterRows(rows, state, opts) {
    return rows
      .filter(function (row) {
        return matches(row, state, opts, false);
      })
      .sort(state.sort === 'old' ? older : newer);
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
      sort: params.get('sort') === 'old' ? 'old' : 'new',
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
    if (form.sort === 'old') parts.push('sort=old');
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

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
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

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function opts() {
    return { today: jstToday(Date.now()), hideVr: document.documentElement.classList.contains('hide-vr') };
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
    var li = el('li', 'shelf-cell');
    var article = el('article', 'item');
    var href = '/item/' + row.c + '/';

    var cover = el('a', 'item-cover');
    cover.href = href;
    cover.tabIndex = -1;
    cover.setAttribute('aria-hidden', 'true');
    var src = imageUrl(row.i);
    if (src) {
      var img = document.createElement('img');
      img.className = 'item-img';
      img.alt = '';
      img.loading = 'lazy';
      img.decoding = 'async';
      img.addEventListener('error', function () {
        img.style.visibility = 'hidden';
      });
      img.src = src;
      cover.appendChild(img);
    }
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
    article.appendChild(names(el('p', 'item-cast ph-js'), cast, '、', '出演者の記載なし'));
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
    tagButtons.forEach(function (button, n) {
      var on = selected.indexOf(n) >= 0;
      // 隠すのは外側の li（隠れた li に、並びの間隔が残らないように）。いま押したボタンは隠さない（フォーカスが、ページの先頭に飛ばないように）
      button.parentNode.hidden = visible.indexOf(n) < 0 && button !== focused;
      button.setAttribute('aria-pressed', on ? 'true' : 'false');
      button.disabled = !on && counts[n] === 0; // 足すと0本になるジャンルは、押せなくする
      button.querySelector('.tag-count').textContent = String(counts[n]);
    });
    var hiddenCount = tagButtons.filter(function (b) {
      return b.parentNode.hidden;
    }).length;
    tagMore.hidden = !expanded && hiddenCount === 0;
    tagMore.textContent = expanded ? 'ジャンルを少なく表示' : 'すべてのジャンルを見る';
  }

  function render() {
    var o = opts();
    var state = readState();
    var found = filterRows(rows, state, o);
    var facets = facetCounts(rows, state, o, genres.length);
    updateTags(facets.counts);
    var visible = found.slice(0, shown);
    list.textContent = '';
    visible.forEach(function (row) {
      list.appendChild(card(row, o.today));
    });
    var vrNote = o.hideVr ? '（VR作品を除く）' : '';
    count.textContent = found.length ? found.length + '本が見つかりました' + vrNote : '条件に合う作品がありません。条件をゆるめてみてね。' + (o.hideVr ? 'VR作品は隠しています。' : '');
    more.hidden = found.length <= visible.length;
    if (filterNote) {
      var active = selected.length + (state.status ? 1 : 0) + (state.sort === 'old' ? 1 : 0);
      filterNote.textContent = active ? '（' + active + '件を指定中）' : '';
    }
    writeUrl();
  }

  function onChange() {
    shown = PAGE_SIZE;
    render();
  }

  function buildTagButtons() {
    tagList.textContent = '';
    tagButtons = genres.map(function (name, n) {
      var li = el('li');
      var button = el('button', 'tag-btn');
      button.type = 'button';
      button.setAttribute('aria-pressed', 'false');
      button.appendChild(el('span', 'tag-name', name));
      button.appendChild(el('span', 'tag-count', '0'));
      button.addEventListener('click', function () {
        var at = selected.indexOf(n);
        if (at >= 0) selected = selected.filter(function (x) {
          return x !== n;
        });
        else selected = selected.concat([n]);
        onChange();
      });
      li.appendChild(button);
      tagList.appendChild(li);
      return button;
    });
  }

  form.addEventListener('input', onChange);
  form.addEventListener('change', onChange);
  form.addEventListener('submit', function (event) {
    event.preventDefault();
    onChange();
  });
  form.addEventListener('reset', function () {
    selected = [];
    setTimeout(onChange, 0); // リセットで項目が空に戻ったあとに、結果を作り直す
  });
  tagMore.addEventListener('click', function () {
    expanded = !expanded;
    render();
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

  fetch(indexUrl, { credentials: 'same-origin' })
    .then(function (res) {
      if (!res.ok) throw new Error('status ' + res.status);
      return res.json();
    })
    .then(function (data) {
      genres = data && Array.isArray(data.genres) ? data.genres.filter(function (g) { return typeof g === 'string'; }) : [];
      rows = data && Array.isArray(data.items) ? data.items.filter(isRow) : [];
      if (data && typeof data.newDays === 'number') newDays = data.newDays;
      if (!rows.length) return; // データが無いときは、最初から載っている案内のまま
      prepare(rows, genres);
      buildTagButtons();
      var first = parseQuery(window.location.search, genres);
      form.elements.q.value = first.q;
      form.elements.status.value = first.status;
      form.elements.sort.value = first.sort;
      selected = first.tags;
      // 広い画面か、ジャンル・発売・並び順の指定つきで開いたときは、たためる欄を最初から開いておく
      var wide = typeof window.matchMedia === 'function' && window.matchMedia('(min-width: 720px)').matches;
      if (filters && (wide || first.tags.length || first.status || first.sort === 'old')) filters.open = true;
      root.hidden = false;
      if (fallback) fallback.hidden = true;
      render();
    })
    .catch(function () {
      // 読み込めなかったときも、最初から載っている案内のまま（何も起きない）
    });
})();
