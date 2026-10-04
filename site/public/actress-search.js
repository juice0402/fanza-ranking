// 出演者検索（/actress/）。名前・年齢・身長・バスト・カップ・ウエスト・ヒップで絞り込む。
// 検索のもとになるデータは /data/actresses-index.json（ビルドごとに作る。短い名前の項目は site/src/lib/profiles.js の説明を参照）。
// JavaScript が使えないときは、ページに最初から載っている「作品が2本以上の出演者」の一覧がそのまま使える。
(function () {
  var PAGE_SIZE = 60; // 1回に出す人数（「もっと見る」で増やす）

  // 名前の照らし合わせ用に、全角/半角・大文字小文字・カタカナ/ひらがな・空白や中点の違いをそろえる
  function normalizeText(text) {
    var s = String(text == null ? '' : text);
    if (s.normalize) s = s.normalize('NFKC');
    s = s.toLowerCase().replace(/[ァ-ヶ]/g, function (c) {
      return String.fromCharCode(c.charCodeAt(0) - 0x60);
    });
    return s.replace(/[\s　・·.・]/g, '');
  }

  // "20-24"（20〜24）・"-19"（19まで）・"40-"（40から）。空・形が違うときは null（絞り込まない）
  function parseRange(text) {
    var m = /^(\d{0,3})-(\d{0,3})$/.exec(String(text == null ? '' : text));
    if (!m || (m[1] === '' && m[2] === '')) return null;
    return { min: m[1] === '' ? null : Number(m[1]), max: m[2] === '' ? null : Number(m[2]) };
  }

  // カップ: "D"（Dだけ）・"K+"（K以上）。空・形が違うときは null
  function parseCup(text) {
    var m = /^([A-Z])(\+?)$/.exec(String(text == null ? '' : text));
    if (!m) return null;
    return { min: m[1], max: m[2] ? null : m[1] };
  }

  // 値が範囲に入るか。値が無い（null）の人は、絞り込みをしているときは入らない（載っていない値を、条件に合うとは言えないため）
  function inRange(value, range) {
    if (!range) return true;
    if (typeof value !== 'number') return false;
    if (range.min !== null && value < range.min) return false;
    if (range.max !== null && value > range.max) return false;
    return true;
  }

  function cupMatches(cup, range) {
    if (!range) return true;
    if (typeof cup !== 'string' || !/^[A-Z]$/.test(cup)) return false;
    if (range.min !== null && cup < range.min) return false;
    if (range.max !== null && cup > range.max) return false;
    return true;
  }

  function byWorks(a, b) {
    return b.k - a.k || (a.n < b.n ? -1 : a.n > b.n ? 1 : 0);
  }

  function byName(a, b) {
    var x = normalizeText(a.r || a.n);
    var y = normalizeText(b.r || b.n);
    return x < y ? -1 : x > y ? 1 : byWorks(a, b);
  }

  // 条件: { text, age, height, bust, cup, waist, hip, sort }（すべて文字列。空なら絞り込まない。sort は 'works'（作品の多い順）か 'name'（名前順））
  function filterRows(rows, query) {
    var q = query || {};
    var text = normalizeText(q.text);
    var age = parseRange(q.age);
    var height = parseRange(q.height);
    var bust = parseRange(q.bust);
    var cup = parseCup(q.cup);
    var waist = parseRange(q.waist);
    var hip = parseRange(q.hip);
    var out = rows.filter(function (row) {
      if (text && normalizeText(row.n).indexOf(text) < 0 && normalizeText(row.r).indexOf(text) < 0) return false;
      return inRange(row.a, age) && inRange(row.h, height) && inRange(row.b, bust) && cupMatches(row.c, cup) && inRange(row.wa, waist) && inRange(row.hi, hip);
    });
    return out.sort(q.sort === 'name' ? byName : byWorks);
  }

  // 数字の条件を1つでも指定しているか（載っていない人は外れる、という注意書きを出すため）
  function hasNumericFilter(q) {
    return ['age', 'height', 'bust', 'cup', 'waist', 'hip'].some(function (key) {
      return Boolean(q && q[key]);
    });
  }

  // 検索結果に出す短い体型の文（site/src/lib/profiles.js の compactSpec と同じ書き方。tests/test_profiles.mjs で突き合わせている）
  function specText(row) {
    var parts = [];
    if (typeof row.a === 'number') parts.push(row.a + '歳');
    if (typeof row.h === 'number') parts.push(row.h + 'cm');
    var size = [];
    if (typeof row.b === 'number') size.push('B' + row.b + (row.c ? '(' + row.c + ')' : ''));
    else if (row.c) size.push(row.c + 'カップ');
    if (typeof row.wa === 'number') size.push('W' + row.wa);
    if (typeof row.hi === 'number') size.push('H' + row.hi);
    if (size.length) parts.push(size.join(' '));
    return parts.join('・');
  }

  // 画像・リンクとして使ってよいURLか（FANZA(DMM)の https だけ）
  function safeUrl(url, hosts) {
    if (typeof url !== 'string') return '';
    // ホストのあとに来てよいのは、ポート番号（数字）と、パス・?・#・終わりだけ。
    // 「https://dmm.co.jp:@別のサイト/」のように、ユーザー名の欄に FANZA のホストを入れて見せかける形は通さない
    var m = /^https:\/\/([A-Za-z0-9.-]+)(?::\d{1,5})?(?:[/?#]|$)/.exec(url);
    if (!m || /[\\\s\x00-\x1f\x7f]/.test(url)) return '';
    var host = m[1].toLowerCase();
    var ok = hosts.some(function (h) {
      return host === h || host.slice(-(h.length + 1)) === '.' + h;
    });
    return ok ? url : '';
  }

  // 出演者ページの短い名前（10桁の英数字）からパスを作る。それ以外なら ''
  function pagePath(slug) {
    return typeof slug === 'string' && /^[0-9a-f]{10}$/.test(slug) ? '/actress/' + slug + '/' : '';
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      normalizeText: normalizeText,
      parseRange: parseRange,
      parseCup: parseCup,
      filterRows: filterRows,
      hasNumericFilter: hasNumericFilter,
      specText: specText,
      safeUrl: safeUrl,
      pagePath: pagePath,
      PAGE_SIZE: PAGE_SIZE,
    }; // tests/test_profiles.mjs 用
    return;
  }
  if (typeof document === 'undefined') return;

  var root = document.getElementById('actress-search');
  if (!root) return;
  var form = root.querySelector('form');
  var list = document.getElementById('as-list');
  var count = document.getElementById('as-count');
  var more = document.getElementById('as-more');
  var note = document.getElementById('as-note');
  var staticList = document.getElementById('actress-static');
  var indexUrl = root.getAttribute('data-index');
  if (!form || !list || !count || !more || !indexUrl) return;

  var rows = [];
  var shown = PAGE_SIZE;
  var DMM = ['dmm.co.jp'];
  var LIST_HOSTS = ['fanza.co.jp', 'dmm.co.jp'];

  function readQuery() {
    var data = {};
    ['text', 'age', 'height', 'bust', 'cup', 'waist', 'hip', 'sort'].forEach(function (key) {
      var field = form.elements[key];
      data[key] = field ? String(field.value || '') : '';
    });
    return data;
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function face(row) {
    var wrap = el('span', 'face face-md');
    wrap.setAttribute('aria-hidden', 'true');
    wrap.appendChild(el('span', 'face-initial', Array.from(row.n)[0] || ''));
    var src = safeUrl(row.i, DMM);
    if (src) {
      var img = document.createElement('img');
      img.className = 'face-img';
      img.alt = '';
      img.width = 56;
      img.height = 56;
      img.loading = 'lazy';
      img.decoding = 'async';
      img.addEventListener('error', function () {
        if (img.parentNode) img.parentNode.removeChild(img);
      });
      img.src = src;
      wrap.appendChild(img);
    }
    return wrap;
  }

  function item(row) {
    var page = pagePath(row.s);
    var out = safeUrl(row.l, LIST_HOSTS);
    if (!page && !out) return null;
    var li = el('li', 'actress-row');
    var a = el('a', 'actress-row-link');
    if (page) {
      a.href = page;
    } else {
      a.href = out;
      a.target = '_blank';
      a.rel = 'sponsored nofollow noopener noreferrer';
    }
    a.appendChild(face(row));
    var text = el('span', 'actress-row-text');
    text.appendChild(el('span', 'actress-row-name', row.n));
    var spec = specText(row);
    if (spec) text.appendChild(el('span', 'actress-row-spec', spec)); // 数字が載っていない人は、行ごと出さない（同じ文が何十行も並ばないように）
    text.appendChild(el('span', 'actress-row-meta', page ? '掲載' + row.k + '本 ›' : 'FANZAで全作品を見る ›'));
    a.appendChild(text);
    li.appendChild(a);
    return li;
  }

  function render() {
    var q = readQuery();
    var found = filterRows(rows, q).filter(function (row) {
      return pagePath(row.s) || safeUrl(row.l, LIST_HOSTS);
    });
    var visible = found.slice(0, shown);
    list.textContent = '';
    visible.forEach(function (row) {
      var li = item(row);
      if (li) list.appendChild(li);
    });
    count.textContent = found.length ? found.length + '人が見つかりました' : '条件に合う出演者がいません。条件をゆるめてみてね。';
    more.hidden = found.length <= visible.length;
    if (note) note.hidden = !hasNumericFilter(q);
  }

  function onChange() {
    shown = PAGE_SIZE;
    render();
  }

  form.addEventListener('input', onChange);
  form.addEventListener('change', onChange);
  form.addEventListener('submit', function (event) {
    event.preventDefault();
    onChange();
  });
  form.addEventListener('reset', function () {
    setTimeout(onChange, 0); // リセットで項目が空に戻ったあとに、一覧を作り直す
  });
  more.addEventListener('click', function () {
    var before = shown;
    shown += PAGE_SIZE;
    render();
    // 増えた分の先頭の人へ、フォーカスを移す（「もっと見る」が消えても、フォーカスがページの先頭に飛ばないように）
    var first = list.children[before] && list.children[before].querySelector('a');
    if (first) first.focus();
  });

  fetch(indexUrl, { credentials: 'same-origin' })
    .then(function (res) {
      if (!res.ok) throw new Error('status ' + res.status);
      return res.json();
    })
    .then(function (data) {
      rows = data && Array.isArray(data.actresses) ? data.actresses : [];
      if (!rows.length) return; // データが無いときは、最初から載っている一覧のまま
      // 広い画面では、年齢・身長・サイズの欄を最初から開いておく（スマホでは、たたんだまま。結果がすぐ見えるように）
      var filters = document.getElementById('as-filters');
      if (filters && typeof window.matchMedia === 'function' && window.matchMedia('(min-width: 720px)').matches) filters.open = true;
      root.hidden = false;
      if (staticList) staticList.hidden = true;
      render();
    })
    .catch(function () {
      // 読み込めなかったときも、最初から載っている一覧のまま（何も起きない）
    });
})();
