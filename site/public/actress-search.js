// 女優検索（/actress/）。名前・年齢・身長・バスト・ウエスト・ヒップ（それぞれ下限〜上限）・カップ（いくつでも）で絞り込み、並べ替える。
// 検索のもとになるデータは /data/actresses-index.json（ビルドごとに作る。項目は site/src/lib/profiles.js の buildActressSearchIndex の説明を参照）。
//   FANZA公式の出演者検索で、体型・身長・生年月日が載っている人（約1万人）と、このサイトの作品の出演者が入っている。
// 条件は URL（?q=&age=20-25&cup=E,F&sort=…）にも書くので、その条件のまま、ほかの人に送ったり、あとで開き直したりできる。
// JavaScript が使えないときは、ページに最初から載っている「作品が2本以上の出演者」の一覧がそのまま使える。
(function () {
  var PAGE_SIZE = 60; // 1回に出す人数（「もっと見る」で増やす）
  var CUPS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']; // カップの選択肢（L以上は「L〜」の1つにまとめる）
  // 数字の条件（下限・上限）。名前は URL とフォームの項目名、key は索引の項目名、lo/hi は入力してよい範囲
  var RANGES = [
    { name: 'age', key: 'a', lo: 18, hi: 80 },
    { name: 'height', key: 'h', lo: 120, hi: 210 },
    { name: 'bust', key: 'b', lo: 50, hi: 160 },
    { name: 'waist', key: 'wa', lo: 40, hi: 130 },
    { name: 'hip', key: 'hi', lo: 50, hi: 160 },
  ];
  // 並び順（値 → 並べ方）。値が無い人は、いつも後ろ
  var SORTS = {
    works: { key: 'k', dir: -1 }, // このサイトの作品の多い順
    bust: { key: 'b', dir: -1 },
    cup: { key: 'c', dir: -1 },
    young: { key: 'a', dir: 1 },
    old: { key: 'a', dir: -1 },
    tall: { key: 'h', dir: -1 },
    short: { key: 'h', dir: 1 },
    waist: { key: 'wa', dir: 1 },
    hip: { key: 'hi', dir: -1 },
    newest: { key: 'id', dir: -1 }, // FANZAに新しく登録された順（id の大きい順）
    name: null, // 読みの順
  };

  // 名前の照らし合わせ用に、全角/半角・大文字小文字・カタカナ/ひらがな・空白や中点の違いをそろえる
  function normalizeText(text) {
    var s = String(text == null ? '' : text);
    if (s.normalize) s = s.normalize('NFKC');
    s = s.toLowerCase().replace(/[ァ-ヶ]/g, function (c) {
      return String.fromCharCode(c.charCodeAt(0) - 0x60);
    });
    return s.replace(/[\s　・·.・]/g, '');
  }

  // 数字の入力 → 整数（空・数字でない・範囲外は null）
  function toInt(text, lo, hi) {
    var t = String(text == null ? '' : text).trim();
    if (t.normalize) t = t.normalize('NFKC');
    if (!/^\d{1,3}$/.test(t)) return null;
    var n = Number(t);
    return n >= lo && n <= hi ? n : null;
  }

  // "20-25"（20〜25）・"-19"（19まで）・"40-"（40から）→ { min, max }。空・形が違うときは null（絞り込まない）。下限が上限より大きければ入れ替える
  function parseRange(text, lo, hi) {
    var m = /^(\d{0,3})-(\d{0,3})$/.exec(String(text == null ? '' : text));
    if (!m || (m[1] === '' && m[2] === '')) return null;
    var min = m[1] === '' ? null : toInt(m[1], lo == null ? 0 : lo, hi == null ? 999 : hi);
    var max = m[2] === '' ? null : toInt(m[2], lo == null ? 0 : lo, hi == null ? 999 : hi);
    if (min === null && max === null) return null;
    if (min !== null && max !== null && min > max) return { min: max, max: min };
    return { min: min, max: max };
  }

  // カップ: "E,F,L+"（E と F と L以上）→ ['E','F','L+']。知らない値は捨てる
  function parseCups(text) {
    var out = [];
    String(text == null ? '' : text)
      .split(',')
      .forEach(function (c) {
        c = c.trim().toUpperCase();
        if ((CUPS.indexOf(c) >= 0 || c === 'L+') && out.indexOf(c) < 0) out.push(c);
      });
    return out;
  }

  // 値が範囲に入るか。値が無い人は、絞り込みをしているときは入らない（載っていない値を、条件に合うとは言えないため）
  function inRange(value, range) {
    if (!range) return true;
    if (typeof value !== 'number') return false;
    if (range.min !== null && value < range.min) return false;
    if (range.max !== null && value > range.max) return false;
    return true;
  }

  function cupMatches(cup, cups) {
    if (!cups || !cups.length) return true;
    if (typeof cup !== 'string' || !/^[A-Z]$/.test(cup)) return false;
    return cups.indexOf(cup) >= 0 || (cups.indexOf('L+') >= 0 && cup >= 'L');
  }

  function nameKey(row) {
    return normalizeText(row.r || row.n);
  }

  function compareBy(sort) {
    var rule = Object.prototype.hasOwnProperty.call(SORTS, sort) ? SORTS[sort] : SORTS.works;
    if (sort === 'name') {
      return function (a, b) {
        var x = nameKey(a);
        var y = nameKey(b);
        return x < y ? -1 : x > y ? 1 : (b.k || 0) - (a.k || 0);
      };
    }
    return function (a, b) {
      if (rule) {
        var x = rule.key === 'id' ? Number(a.id || 0) : a[rule.key];
        var y = rule.key === 'id' ? Number(b.id || 0) : b[rule.key];
        var hx = x !== undefined && x !== null && x !== '' && x !== 0;
        var hy = y !== undefined && y !== null && y !== '' && y !== 0;
        if (hx !== hy) return hx ? -1 : 1; // 値が無い人は後ろ
        if (hx && x !== y) return (x < y ? -1 : 1) * rule.dir;
      }
      var kx = a.k || 0;
      var ky = b.k || 0;
      if (kx !== ky) return ky - kx;
      var nx = nameKey(a);
      var ny = nameKey(b);
      return nx < ny ? -1 : nx > ny ? 1 : 0;
    };
  }

  // 条件: { q 名前, age/height/bust/waist/hip "下限-上限", cup "E,F,L+", sort, site "1"（このサイトに作品がある人だけ）, face "1"（顔写真がある人だけ） }
  function filterRows(rows, query) {
    var q = query || {};
    var text = normalizeText(q.q);
    var ranges = RANGES.map(function (r) {
      return { key: r.key, range: parseRange(q[r.name], r.lo, r.hi) };
    });
    var cups = parseCups(q.cup);
    var onlySite = q.site === '1';
    var onlyFace = q.face === '1';
    var out = rows.filter(function (row) {
      if (text && normalizeText(row.n).indexOf(text) < 0 && normalizeText(row.r).indexOf(text) < 0) return false;
      if (onlySite && !(row.k > 0)) return false;
      if (onlyFace && !row.i) return false;
      for (var i = 0; i < ranges.length; i++) if (!inRange(row[ranges[i].key], ranges[i].range)) return false;
      return cupMatches(row.c, cups);
    });
    return out.sort(compareBy(q.sort));
  }

  // 数字・カップの条件を1つでも指定しているか（載っていない人は外れる、という注意書きを出すため）
  function hasNumericFilter(q) {
    if (!q) return false;
    if (parseCups(q.cup).length) return true;
    return RANGES.some(function (r) {
      return parseRange(q[r.name], r.lo, r.hi) !== null;
    });
  }

  // URL の ?… → 条件。知らない項目・変な値は捨てる
  function parseQuery(search) {
    var params = new URLSearchParams(search || '');
    var q = { q: (params.get('q') || '').slice(0, 50), cup: parseCups(params.get('cup')).join(','), sort: params.get('sort') || 'works' };
    if (!Object.prototype.hasOwnProperty.call(SORTS, q.sort)) q.sort = 'works';
    RANGES.forEach(function (r) {
      var range = parseRange(params.get(r.name), r.lo, r.hi);
      q[r.name] = range ? (range.min === null ? '' : range.min) + '-' + (range.max === null ? '' : range.max) : '';
    });
    q.site = params.get('site') === '1' ? '1' : '';
    q.face = params.get('face') === '1' ? '1' : '';
    return q;
  }

  // 条件 → URL の ?…（空の条件は書かない）
  function buildQuery(q) {
    var parts = [];
    if (q.q) parts.push('q=' + encodeURIComponent(q.q));
    RANGES.forEach(function (r) {
      if (q[r.name]) parts.push(r.name + '=' + encodeURIComponent(q[r.name]));
    });
    if (q.cup) parts.push('cup=' + encodeURIComponent(q.cup));
    if (q.site === '1') parts.push('site=1');
    if (q.face === '1') parts.push('face=1');
    if (q.sort && q.sort !== 'works') parts.push('sort=' + encodeURIComponent(q.sort));
    return parts.length ? '?' + parts.join('&') : '';
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

  // 顔写真のURL: 索引の i がファイル名（例 hasumi_kurea）なら、置き場所（index.img）とつなげる。URL ならそのまま（FANZAの https だけ）
  function imageUrl(i, base) {
    if (typeof i !== 'string' || !i) return '';
    if (/^[a-z0-9_]{1,60}$/.test(i)) return safeUrl(String(base || '') + i + '.jpg', ['dmm.co.jp']);
    return safeUrl(i, ['dmm.co.jp']);
  }

  // 「FANZAで全作品を見る」のURL: 行の l があればそれ、無ければ形（index.list の {ID}）に id を入れる（FANZAの https だけ）
  function listUrl(row, template) {
    if (row.l) return safeUrl(row.l, ['fanza.co.jp', 'dmm.co.jp']);
    if (!row.id || !/^\d{1,12}$/.test(String(row.id)) || typeof template !== 'string' || template.split('{ID}').length !== 2) return '';
    return safeUrl(template.replace('{ID}', String(row.id)), ['fanza.co.jp', 'dmm.co.jp']);
  }

  // 出演者ページの短い名前（10桁の英数字）からパスを作る。それ以外なら ''
  function pagePath(slug) {
    return typeof slug === 'string' && /^[0-9a-f]{10}$/.test(slug) ? '/actress/' + slug + '/' : '';
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      normalizeText: normalizeText,
      parseRange: parseRange,
      parseCups: parseCups,
      filterRows: filterRows,
      hasNumericFilter: hasNumericFilter,
      parseQuery: parseQuery,
      buildQuery: buildQuery,
      specText: specText,
      safeUrl: safeUrl,
      imageUrl: imageUrl,
      listUrl: listUrl,
      pagePath: pagePath,
      PAGE_SIZE: PAGE_SIZE,
      CUPS: CUPS,
      SORTS: Object.keys(SORTS),
      RANGES: RANGES.map(function (r) {
        return r.name;
      }),
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
  var filters = document.getElementById('as-filters');
  var filterNote = document.getElementById('as-filter-note');
  var indexUrl = root.getAttribute('data-index');
  if (!form || !list || !count || !more || !indexUrl) return;

  var rows = [];
  var imgBase = '';
  var template = '';
  var shown = PAGE_SIZE;

  function field(name) {
    return form.elements[name];
  }

  // フォーム → 条件
  function readQuery() {
    var q = { q: field('q') ? String(field('q').value || '').trim() : '', sort: field('sort') ? field('sort').value : 'works' };
    RANGES.forEach(function (r) {
      var lo = field(r.name + '_min');
      var hi = field(r.name + '_max');
      var a = lo ? String(lo.value || '').trim() : '';
      var b = hi ? String(hi.value || '').trim() : '';
      q[r.name] = a || b ? a + '-' + b : '';
    });
    var cups = [];
    Array.prototype.forEach.call(form.querySelectorAll('input[name="cup"]:checked'), function (box) {
      cups.push(box.value);
    });
    q.cup = cups.join(',');
    q.site = field('site') && field('site').checked ? '1' : '';
    q.face = field('face') && field('face').checked ? '1' : '';
    return q;
  }

  // 条件 → フォーム（URL から開いたとき）
  function writeForm(q) {
    if (field('q')) field('q').value = q.q;
    if (field('sort')) field('sort').value = q.sort;
    RANGES.forEach(function (r) {
      var range = parseRange(q[r.name], r.lo, r.hi);
      if (field(r.name + '_min')) field(r.name + '_min').value = range && range.min !== null ? String(range.min) : '';
      if (field(r.name + '_max')) field(r.name + '_max').value = range && range.max !== null ? String(range.max) : '';
    });
    var cups = parseCups(q.cup);
    Array.prototype.forEach.call(form.querySelectorAll('input[name="cup"]'), function (box) {
      box.checked = cups.indexOf(box.value) >= 0;
    });
    if (field('site')) field('site').checked = q.site === '1';
    if (field('face')) field('face').checked = q.face === '1';
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
    var src = imageUrl(row.i, imgBase);
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
    var out = listUrl(row, template);
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
    text.appendChild(el('span', 'actress-row-meta', page ? 'このサイトの作品 ' + row.k + '本 ›' : row.k ? 'このサイトの作品 ' + row.k + '本・FANZAで全作品を見る ›' : 'FANZAで全作品を見る ›'));
    a.appendChild(text);
    li.appendChild(a);
    return li;
  }

  function writeUrl(q) {
    try {
      window.history.replaceState(null, '', window.location.pathname + buildQuery(q));
    } catch (e) {}
  }

  function render() {
    var q = readQuery();
    var found = filterRows(rows, q).filter(function (row) {
      return pagePath(row.s) || listUrl(row, template);
    });
    var visible = found.slice(0, shown);
    list.textContent = '';
    visible.forEach(function (row) {
      var li = item(row);
      if (li) list.appendChild(li);
    });
    count.textContent = found.length ? found.length.toLocaleString('ja-JP') + '人が見つかりました' : '条件に合う女優がいません。条件をゆるめてみてね。';
    more.hidden = found.length <= visible.length;
    if (note) note.hidden = !hasNumericFilter(q);
    if (filterNote) {
      var active = RANGES.filter(function (r) {
        return q[r.name];
      }).length + (q.cup ? 1 : 0) + (q.site ? 1 : 0) + (q.face ? 1 : 0);
      filterNote.textContent = active ? '（' + active + '件を指定中）' : '';
    }
    writeUrl(q);
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
      rows = data && Array.isArray(data.actresses) ? data.actresses.filter(function (r) {
        return r && typeof r === 'object' && typeof r.n === 'string' && r.n;
      }) : [];
      if (!rows.length) return; // データが無いときは、最初から載っている一覧のまま
      imgBase = data && typeof data.img === 'string' ? data.img : '';
      template = data && typeof data.list === 'string' ? data.list : '';
      var first = parseQuery(window.location.search);
      writeForm(first);
      // 広い画面か、条件つきで開いたときは、くわしい条件の欄を最初から開いておく（スマホでは、たたんだまま。結果がすぐ見えるように）
      var wide = typeof window.matchMedia === 'function' && window.matchMedia('(min-width: 720px)').matches;
      if (filters && (wide || hasNumericFilter(first) || first.site || first.face || first.sort !== 'works')) filters.open = true;
      root.hidden = false;
      if (staticList) staticList.hidden = true;
      render();
    })
    .catch(function () {
      // 読み込めなかったときも、最初から載っている一覧のまま（何も起きない）
    });
})();
