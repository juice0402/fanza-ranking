// FANZA同人・FANZAゲームの作品検索（/doujin/search/・/game/search/。運営者の希望「検索とかもあってもいいかもしれない」。2026-10-09）。
// 索引（data-index。site/src/lib/floors.js の floorSearchIndex）を読んで、キーワード・並び順・セール中/予約・形式（同人）・特集・ジャンルで、
// 端末の中で絞り込む。条件は URL（?q=&sort=&st=&type=&th=&tag=）にも書く。条件なし（人気順）の「はじめの一覧」は、ページに入っている。
// 行の形は components/FloorRow.astro と同じ（lib/floors.js の floorSearchRow と同じ中身）。DOM は textContent で作る
(function () {
  var PAGE = 30; // 1回に出す本数（lib/floors.js の FLOOR_SEARCH_PAGE と同じ）
  var TYPING_WAIT_MS = 180; // キーワードは、打ち終わって少したってから探す
  var THUMB_MEDIA = '(max-width: 480px)'; // スマホ（lib/items.js の THUMB_MEDIA と同じ）
  var AWS_IMG = 'https://awsimgsrc.dmm.co.jp/pics_dig/';

  // くらべるための文字（全角・半角、大文字・小文字、カタカナ・ひらがな、文節の区切りの見えない文字をそろえる）
  function norm(s) {
    return String(s || '')
      .normalize('NFKC')
      .replace(/[​⁠ ]/g, '')
      .toLowerCase()
      .replace(/[ァ-ヶ]/g, function (c) {
        return String.fromCharCode(c.charCodeAt(0) - 0x60);
      });
  }

  function comma(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  // 表紙の決まった置き場所（lib/floors.js の floorImageOf と同じ）
  function imageOf(key, row) {
    if (row.i) return row.i;
    if (key === 'game') return 'https://pics.dmm.co.jp/digital/pcgame/' + row.c + '/' + row.c + 'pl.jpg';
    return row.y ? 'https://pics.dmm.co.jp/digital/' + row.y + '/' + row.c + '/' + row.c + 'pl.jpg' : '';
  }

  // 小さな表紙: 同人は、スマホのとき FANZA の「縮めて返す版」の幅240（lib/floors.js の doujinThumb の tiny）。ゲームは表紙（…ps.jpg）
  function thumbUrl(key, url, tiny) {
    var s = String(url || '');
    if (key === 'doujin') return tiny && s.indexOf('https://pics.dmm.co.jp/') === 0 ? AWS_IMG + s.slice(23) + '?w=240&q=75' : s;
    return /^https:\/\/pics\.dmm\.co\.jp\/[^?#]+pl\.jpg$/.test(s) ? s.replace(/pl\.jpg$/, 'ps.jpg') : s;
  }

  // 並べ方（lib/floors.js の byRank と同じ考え方: 順位のある作品を順位の順、そのあと発売日の新しい順）
  function byPop(a, b) {
    return (a.r || Infinity) - (b.r || Infinity) || (a.d < b.d ? 1 : a.d > b.d ? -1 : 0) || (a.c < b.c ? -1 : 1);
  }
  var SORTS = {
    pop: byPop,
    new: function (a, b) {
      return (a.d < b.d ? 1 : a.d > b.d ? -1 : 0) || byPop(a, b);
    },
    cheap: function (a, b) {
      return (a.p || Infinity) - (b.p || Infinity) || byPop(a, b);
    },
    off: function (a, b) {
      return (b.o || 0) - (a.o || 0) || byPop(a, b);
    },
    // 評価が高い順（索引の v: レビューの平均×100・vc: 件数。2026-10-10）: 3件以上の作品を、件数でならした評価の高い順（作品検索の search.js と同じ）
    review: function (a, b) {
      return reviewScore(b) - reviewScore(a) || byPop(a, b);
    },
  };
  function reviewScore(row) {
    if (typeof row.v !== 'number' || typeof row.vc !== 'number' || row.vc < 3) return -1;
    return (row.vc * row.v / 100 + 10 * 4.2) / (row.vc + 10);
  }

  // 条件に合う作品（state: { q, sort, st, type, g: [ジャンルの番号], h: [特集の番号] }）
  function filterRows(index, state) {
    var words = norm(state.q).split(/\s+/).filter(Boolean);
    return index.items.filter(function (row) {
      if (state.st === 'sale' && row.s !== 1) return false;
      if (state.st === 'upcoming' && row.u !== 1) return false;
      if (state.type && row.y !== state.type) return false;
      var g = row.g || [];
      var h = row.h || [];
      for (var i = 0; i < state.g.length; i++) if (g.indexOf(state.g[i]) < 0) return false;
      for (var j = 0; j < state.h.length; j++) if (h.indexOf(state.h[j]) < 0) return false;
      if (!words.length) return true;
      var hay = row.$k;
      for (var w = 0; w < words.length; w++) if (hay.indexOf(words[w]) < 0) return false;
      return true;
    });
  }

  // 行の中身（lib/floors.js の floorSearchRow と同じ）
  function rowView(row, key) {
    var yen = row.p ? comma(row.p) + '円' + (row.o ? '（' + row.o + '%OFF）' : '') : '';
    var day = row.u
      ? +row.d.slice(5, 7) + '月' + +row.d.slice(8, 10) + '日発売予定'
      : row.d.slice(0, 4) + '年' + +row.d.slice(5, 7) + '月' + +row.d.slice(8, 10) + '日発売';
    return {
      c: row.c,
      href: '/' + key + '/item/' + row.c + '/',
      title: row.t,
      img: imageOf(key, row),
      wide: key === 'doujin',
      line: [row.m, row.a].filter(Boolean).join('｜'),
      meta: [day, yen].filter(Boolean).join('・'),
      upcoming: row.u === 1,
    };
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { norm: norm, filterRows: filterRows, SORTS: SORTS, rowView: rowView, imageOf: imageOf, thumbUrl: thumbUrl, PAGE: PAGE }; // tests/test_floors.mjs 用
    return;
  }
  if (typeof document === 'undefined') return;

  var root = document.getElementById('floor-search');
  if (!root) return;
  var key = root.getAttribute('data-floor') === 'game' ? 'game' : 'doujin';
  var form = root.querySelector('form');
  var input = document.getElementById('fs-q');
  var list = document.getElementById('fs-list');
  var count = document.getElementById('fs-count');
  var more = document.getElementById('fs-more');
  var tagMore = document.getElementById('fs-tag-more');
  var tagList = document.getElementById('fs-tag-list');
  var fallback = document.getElementById('ws-fallback');
  var buttons = Array.prototype.slice.call(root.querySelectorAll('.tag-btn'));
  var tiny = Boolean(window.matchMedia && window.matchMedia(THUMB_MEDIA).matches);
  var index = null;
  var found = [];
  var shownCount = PAGE;
  var timer = 0;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  function radio(name) {
    var checked = form.querySelector('input[name="' + name + '"]:checked');
    return checked ? checked.value : '';
  }

  function setRadio(name, value) {
    var inputs = form.querySelectorAll('input[name="' + name + '"]');
    var hit = false;
    for (var i = 0; i < inputs.length; i++) {
      inputs[i].checked = inputs[i].value === value;
      if (inputs[i].checked) hit = true;
    }
    if (!hit && inputs.length) inputs[0].checked = true;
  }

  function pressed(kind) {
    return buttons
      .filter(function (b) {
        return b.getAttribute('data-kind') === kind && b.getAttribute('aria-pressed') === 'true';
      })
      .map(function (b) {
        return Number(b.getAttribute('data-n'));
      });
  }

  function state() {
    return { q: input.value, sort: radio('sort') || 'pop', st: radio('st'), type: radio('type'), g: pressed('g'), h: pressed('h') };
  }

  function isBlank(s) {
    return !s.q.trim() && s.sort === 'pop' && !s.st && !s.type && !s.g.length && !s.h.length;
  }

  // 条件を URL に書く（共有・戻るで同じ結果に）
  function writeUrl(s) {
    var p = new URLSearchParams();
    if (s.q.trim()) p.set('q', s.q.trim());
    if (s.sort !== 'pop') p.set('sort', s.sort);
    if (s.st) p.set('st', s.st);
    if (s.type) p.set('type', s.type);
    if (s.h.length) p.set('th', s.h.map(function (n) { return index.themes[n].s; }).join(','));
    if (s.g.length) p.set('tag', s.g.map(function (n) { return index.genres[n]; }).join(','));
    var qs = p.toString();
    history.replaceState(null, '', location.pathname + (qs ? '?' + qs : ''));
  }

  function readUrl() {
    var p = new URLSearchParams(location.search);
    input.value = p.get('q') || '';
    setRadio('sort', p.get('sort') || 'pop');
    setRadio('st', p.get('st') || '');
    setRadio('type', p.get('type') || '');
    var themes = (p.get('th') || '').split(',');
    var tags = (p.get('tag') || '').split(',');
    buttons.forEach(function (b) {
      var n = Number(b.getAttribute('data-n'));
      var on = b.getAttribute('data-kind') === 'h' ? themes.indexOf(index.themes[n] && index.themes[n].s) >= 0 : tags.indexOf(index.genres[n]) >= 0;
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      if (on && b.parentNode.hidden) b.parentNode.hidden = false; // たたんだ所のジャンルでも、選んでいれば見せる
    });
  }

  function thumb(url) {
    var img = el('img', key === 'doujin' ? 'floor-img' : 'item-img is-small');
    img.alt = '';
    img.loading = 'lazy';
    img.decoding = 'async';
    img.referrerPolicy = 'no-referrer';
    // 縮めた版が読めなければ元の画像に、表紙（…ps.jpg）が読めなければパッケージ画像に戻す。それも読めなければ隠す
    img.addEventListener('error', function () {
      if (img.src.indexOf(AWS_IMG) === 0) img.src = 'https://pics.dmm.co.jp/' + img.src.slice(AWS_IMG.length).replace(/\?.*$/, '');
      else if (/ps\.jpg$/.test(img.src)) {
        img.src = img.src.replace(/ps\.jpg$/, 'pl.jpg');
        img.classList.remove('is-small');
      } else img.style.visibility = 'hidden';
    });
    if (key === 'doujin') {
      img.width = 560;
      img.height = 420;
    }
    img.src = thumbUrl(key, url, tiny);
    return img;
  }

  function card(v) {
    var li = el('li', 'ws-row');
    li.setAttribute('data-c', v.c);
    var article = el('article', 'item');
    var cover = el('a', 'item-cover' + (v.wide ? ' is-wide' : ''));
    cover.href = v.href;
    cover.tabIndex = -1;
    cover.setAttribute('aria-hidden', 'true');
    if (v.img) cover.appendChild(thumb(v.img));
    if (v.upcoming) cover.appendChild(el('span', 'pop pop-wait', '予約'));
    article.appendChild(cover);
    var heading = el('h3', 'item-title');
    var link = el('a', 'item-title-link ph-js', v.title);
    link.href = v.href;
    heading.appendChild(link);
    article.appendChild(heading);
    if (v.line) article.appendChild(el('p', 'item-cast', v.line));
    if (v.meta) article.appendChild(el('p', 'item-meta', v.meta));
    li.appendChild(article);
    return li;
  }

  function render(s) {
    found = filterRows(index, s).sort(SORTS[s.sort] || byPop);
    count.textContent = '';
    count.appendChild(el('strong', 'ws-num', comma(found.length)));
    count.appendChild(document.createTextNode('本'));
    list.removeAttribute('data-first');
    list.textContent = '';
    if (!found.length) {
      list.appendChild(el('li', 'empty', '条件に合う作品はありません。条件をへらしてみてください。'));
    }
    found.slice(0, shownCount).forEach(function (row) {
      list.appendChild(card(rowView(row, key)));
    });
    more.hidden = found.length <= shownCount;
    // ボタンの本数（いまの結果の中で、そのボタンも足したときの本数）。足すと0本になるボタンは押せない
    buttons.forEach(function (b) {
      var n = Number(b.getAttribute('data-n'));
      var field = b.getAttribute('data-kind');
      var on = b.getAttribute('aria-pressed') === 'true';
      var c = 0;
      for (var i = 0; i < found.length; i++) if ((found[i][field] || []).indexOf(n) >= 0) c++;
      var label = b.querySelector('.tag-count');
      if (label && label.textContent !== String(c)) label.textContent = String(c);
      b.disabled = !on && c === 0;
    });
  }

  function update(resetPage) {
    if (!index) return;
    if (resetPage) shownCount = PAGE;
    var s = state();
    writeUrl(s);
    render(s);
  }

  function start(raw) {
    if (!raw || !Array.isArray(raw.items) || !Array.isArray(raw.genres) || !Array.isArray(raw.themes)) throw new Error('index');
    index = raw;
    var yomi = raw.yomi && typeof raw.yomi === 'object' ? raw.yomi : {};
    index.items.forEach(function (row) {
      // 照らし合わせ用の文字は1作品1回だけ作る（タイトル・サークル/ブランド・作家・ジャンルと、その読みがな＝索引の yomi。ひらがなで打っても見つかるように）
      var names = [row.m].concat(String(row.a || '').split('、')).concat((row.g || []).map(function (n) { return raw.genres[n]; }));
      var readings = names.map(function (n) { return n && Object.prototype.hasOwnProperty.call(yomi, n) && typeof yomi[n] === 'string' ? yomi[n] : ''; });
      row.$k = norm([row.t, row.m, row.a].concat((row.g || []).map(function (n) { return raw.genres[n]; })).concat(readings).join(' '));
    });
    readUrl();
    if (!isBlank(state())) update(true); // 条件つきの URL で開いたときだけ作り直す（条件なしは、ページに入っている一覧のまま）
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (input.blur) input.blur();
    update(true);
  });
  input.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      update(true);
    }, TYPING_WAIT_MS);
  });
  form.addEventListener('change', function (e) {
    if (e.target && e.target.type === 'radio') update(true);
  });
  form.addEventListener('reset', function () {
    setTimeout(function () {
      buttons.forEach(function (b) {
        b.setAttribute('aria-pressed', 'false');
      });
      update(true);
    }, 0);
  });
  buttons.forEach(function (b) {
    b.addEventListener('click', function () {
      b.setAttribute('aria-pressed', b.getAttribute('aria-pressed') === 'true' ? 'false' : 'true');
      update(true);
    });
  });
  more.addEventListener('click', function () {
    if (!index) return;
    shownCount += PAGE;
    render(state());
  });
  if (tagMore && tagList) {
    tagMore.addEventListener('click', function () {
      var open = tagMore.getAttribute('aria-expanded') !== 'true';
      tagMore.setAttribute('aria-expanded', open ? 'true' : 'false');
      tagMore.textContent = open ? 'たたむ' : 'すべてのジャンル';
      tagList.classList.toggle('is-open', open);
      Array.prototype.forEach.call(tagList.children, function (li) {
        if (li.hasAttribute('data-was-hidden')) li.hidden = !open;
      });
    });
  }

  fetch(root.getAttribute('data-index'), { credentials: 'same-origin' })
    .then(function (res) {
      if (!res.ok) throw new Error('status ' + res.status);
      return res.json();
    })
    .then(start)
    .catch(function () {
      // 索引を読めなかったら、検索の部品を隠して「ほかの探し方」を出す
      root.hidden = true;
      if (fallback) fallback.classList.add('is-fallback');
    });
})();
