// 女優検索（/actress/）。名前・年齢・身長（下限〜上限の数字）・バスト・ウエスト・ヒップ（「80〜84cm」のような幅を、いくつでも）・カップ（いくつでも）・所属事務所で絞り込み、並べ替える。
// 検索のもとになるデータは /data/actresses-index.json（ビルドごとに作る。項目は site/src/lib/profiles.js の buildActressSearchIndex の説明を参照）。
//   FANZA公式の出演者検索で、体型・身長・生年月日が載っている人（約1万人）と、このサイトの作品の出演者が入っている。
// 条件は URL（?q=&age=20-25&bust=85-89,90-94&cup=E,F&sort=…）にも書くので、その条件のまま、ほかの人に送ったり、あとで開き直したりできる。
// JavaScript が使えないときは、ページに最初から載っている「作品が2本以上の出演者」の一覧がそのまま使える。
(function () {
  var PAGE_SIZE = 30; // 1回に出す人数（「もっと見る」で増やす。site/src/lib/profiles.js の ACTRESS_PAGE_SIZE と同じ。2026-10-07 に 60→30）
  var TYPING_WAIT_MS = 180; // 名前の欄: 打ち終わってから、この時間たったら絞り込む
  var WARM_CHUNK = 1500; // 手のあいたときに、照らし合わせ用の文字を一度に作る人数
  var CUPS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']; // カップの選択肢（L以上は「L〜」の1つにまとめる）
  // 数字の条件（下限・上限）。名前は URL とフォームの項目名、key は索引の項目名、lo/hi は入力してよい範囲
  var RANGES = [
    { name: 'age', key: 'a', lo: 18, hi: 80 },
    { name: 'height', key: 'h', lo: 120, hi: 210 },
    { name: 'bust', key: 'b', lo: 50, hi: 160 },
    { name: 'waist', key: 'wa', lo: 40, hi: 130 },
    { name: 'hip', key: 'hi', lo: 50, hi: 160 },
  ];
  // スリーサイズは、数字を入れる代わりに、幅（cm）をタップで選ぶ（運営者の希望「何センチと言われてもサイズ感が分からないので、何センチ〜何センチの選択肢に」。2026-10-05）。
  // いくつでも選べて、どれかに入る人が出る。幅は site/src/lib/profiles.js の SIZE_BUCKETS と同じ（tests/test_profiles.mjs で突き合わせている）
  var BUCKETS = {
    bust: ['-79', '80-84', '85-89', '90-94', '95-99', '100-'],
    waist: ['-55', '56-58', '59-61', '62-64', '65-'],
    hip: ['-79', '80-84', '85-89', '90-94', '95-'],
  };
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
    if (/^[ぁ-ゖー]*$/.test(s)) return s; // ひらがなだけ（読みのほとんど）は、そろえる必要が無い（速くするため）
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

  // 幅のならび: "80-84,90-"（80〜84 と 90以上）→ [{ min, max }, …]。読めない幅は捨てる
  function parseRanges(text, lo, hi) {
    var out = [];
    String(text == null ? '' : text)
      .split(',')
      .forEach(function (part) {
        var range = parseRange(part.trim(), lo, hi);
        if (range) out.push(range);
      });
    return out;
  }

  // スリーサイズの幅（URL・フォームの値）: 決まった幅だけを、決まった順に残す（"85-89,-79,xx" → "-79,85-89"）
  function parseBuckets(text, name) {
    var allowed = BUCKETS[name] || [];
    var picked = String(text == null ? '' : text).split(',').map(function (v) {
      return v.trim();
    });
    return allowed.filter(function (v) {
      return picked.indexOf(v) >= 0;
    });
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

  // 値が、幅のどれかに入るか（幅が無ければ、絞り込まない）。値が無い人は、絞り込みをしているときは入らない（載っていない値を、条件に合うとは言えないため）
  function inRanges(value, ranges) {
    if (!ranges.length) return true;
    if (typeof value !== 'number') return false;
    return ranges.some(function (range) {
      return (range.min === null || value >= range.min) && (range.max === null || value <= range.max);
    });
  }

  function cupMatches(cup, cups) {
    if (!cups || !cups.length) return true;
    if (typeof cup !== 'string' || !/^[A-Z]$/.test(cup)) return false;
    return cups.indexOf(cup) >= 0 || (cups.indexOf('L+') >= 0 && cup >= 'L');
  }

  // 照らし合わせ・並べ替え用の文字は、1人につき1回だけ作って、その人の行にしまっておく（約1万人を、文字を入れるたび・並べ替えるたびに
  // 作り直していて、スマホで1回0.1〜0.25秒かかっていたため。運営者の「女優検索が少し重い」。2026-10-07）
  // （名前の照らし合わせ用 n・r と、並べ替え用 sort は、使うときに別々に作る。はじめの一覧は並べ替え用だけで済む）
  function keysOf(row) {
    var k = row.$keys;
    if (!k) {
      k = {};
      try {
        Object.defineProperty(row, '$keys', { value: k, enumerable: false, configurable: true });
      } catch (e) {}
    }
    return k;
  }

  function matchKeys(row) {
    var k = keysOf(row);
    if (k.n === undefined) {
      k.n = normalizeText(row.n);
      k.r = normalizeText(row.r);
    }
    return k;
  }

  function nameKey(row) {
    var k = keysOf(row);
    if (k.sort === undefined) k.sort = normalizeText(row.r || row.n);
    return k.sort;
  }

  // 並べ替えの値を、1人ずつ先に取り出しておく（比べるたびに取り出さない）。i は元の順（同じ順位なら元の順のまま）
  function sortEntry(row, i, rule) {
    var v = rule ? (rule.key === 'id' ? Number(row.id || 0) : row[rule.key]) : null;
    return { row: row, i: i, v: v, has: Boolean(rule) && v !== undefined && v !== null && v !== '' && v !== 0, k: row.k || 0, name: nameKey(row) };
  }

  // 並べ方（sortEntry どうしを比べる）。値が無い人は後ろ・同じなら作品の多い順・読みの順・元の順
  function compareBy(sort) {
    var rule = Object.prototype.hasOwnProperty.call(SORTS, sort) ? SORTS[sort] : SORTS.works;
    if (sort === 'name') {
      return function (a, b) {
        return a.name < b.name ? -1 : a.name > b.name ? 1 : b.k - a.k || a.i - b.i;
      };
    }
    return function (a, b) {
      if (rule) {
        if (a.has !== b.has) return a.has ? -1 : 1; // 値が無い人は後ろ
        if (a.has && a.v !== b.v) return (a.v < b.v ? -1 : 1) * rule.dir;
      }
      if (a.k !== b.k) return b.k - a.k;
      return a.name < b.name ? -1 : a.name > b.name ? 1 : a.i - b.i;
    };
  }

  // 所属事務所のキー（索引の g。site/src/lib/agencies.js の AGENCIES のキー）の形
  var AGENCY_KEY = /^[a-z]{2,12}$/;

  // 並べ替えた一覧は、並び順ごとに1回だけ作って覚えておく（条件を変えるたびに約1万人を並べ替えない）。
  // 並べ替えは安定（同じ順位なら元の順）なので、「並べ替えてから絞り込む」と「絞り込んでから並べ替える」は同じ結果になる
  var sortCache = { rows: null, len: -1, sort: '', list: null };
  function sortedRows(rows, sort) {
    var key = Object.prototype.hasOwnProperty.call(SORTS, sort) ? sort : 'works';
    if (sortCache.rows !== rows || sortCache.len !== rows.length || sortCache.sort !== key) {
      var rule = key === 'name' ? null : SORTS[key];
      var entries = rows.map(function (row, i) {
        return sortEntry(row, i, rule);
      });
      entries.sort(compareBy(key));
      sortCache = {
        rows: rows,
        len: rows.length,
        sort: key,
        list: entries.map(function (e) {
          return e.row;
        }),
      };
    }
    return sortCache.list;
  }

  // 条件: { q 名前, age/height "下限-上限", bust/waist/hip "幅,幅"（どれかに入る人。"80-84,90-"）, cup "E,F,L+", ag 所属事務所のキー, sort, site "1"（このサイトに作品がある人だけ）, face "1"（顔写真がある人だけ） }
  function filterRows(rows, query) {
    var q = query || {};
    var text = normalizeText(q.q);
    var ranges = RANGES.map(function (r) {
      return { key: r.key, ranges: parseRanges(q[r.name], r.lo, r.hi) };
    });
    var cups = parseCups(q.cup);
    var onlySite = q.site === '1';
    var onlyFace = q.face === '1';
    var agency = AGENCY_KEY.test(String(q.ag || '')) ? q.ag : '';
    return sortedRows(rows, q.sort).filter(function (row) {
      if (agency && row.g !== agency) return false;
      if (text) {
        var keys = matchKeys(row);
        if (keys.n.indexOf(text) < 0 && keys.r.indexOf(text) < 0) return false;
      }
      if (onlySite && !(row.k > 0)) return false;
      if (onlyFace && !row.i) return false;
      for (var i = 0; i < ranges.length; i++) if (!inRanges(row[ranges[i].key], ranges[i].ranges)) return false;
      return cupMatches(row.c, cups);
    });
  }

  // 数字・カップの条件を1つでも指定しているか（載っていない人は外れる、という注意書きを出すため）
  function hasNumericFilter(q) {
    if (!q) return false;
    if (parseCups(q.cup).length) return true;
    return RANGES.some(function (r) {
      return parseRanges(q[r.name], r.lo, r.hi).length > 0;
    });
  }

  // URL の ?… → 条件。知らない項目・変な値は捨てる
  function parseQuery(search) {
    var params = new URLSearchParams(search || '');
    var q = { q: (params.get('q') || '').slice(0, 50), cup: parseCups(params.get('cup')).join(','), sort: params.get('sort') || 'works' };
    if (!Object.prototype.hasOwnProperty.call(SORTS, q.sort)) q.sort = 'works';
    RANGES.forEach(function (r) {
      if (BUCKETS[r.name]) {
        q[r.name] = parseBuckets(params.get(r.name), r.name).join(',');
        return;
      }
      var range = parseRange(params.get(r.name), r.lo, r.hi);
      q[r.name] = range ? (range.min === null ? '' : range.min) + '-' + (range.max === null ? '' : range.max) : '';
    });
    q.site = params.get('site') === '1' ? '1' : '';
    q.face = params.get('face') === '1' ? '1' : '';
    q.ag = AGENCY_KEY.test(params.get('ag') || '') ? params.get('ag') : '';
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
    if (q.ag) parts.push('ag=' + encodeURIComponent(q.ag));
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

  // 検索結果の「所属：○○」（索引の agencies にある事務所だけ）
  function agencyLabel(row, names) {
    if (!row || !AGENCY_KEY.test(String(row.g || '')) || !names || !Object.prototype.hasOwnProperty.call(names, row.g)) return '';
    var name = String(names[row.g] || '');
    return name ? '所属：' + name : '';
  }

  // 出演者ページの短い名前（10桁の英数字）からパスを作る。それ以外なら ''
  function pagePath(slug) {
    return typeof slug === 'string' && /^[0-9a-f]{10}$/.test(slug) ? '/actress/' + slug + '/' : '';
  }

  // 検索結果の1行の中身。行を出せない（専用ページも全作品のリンクも無い）ときは null。
  // ctx: { template: 索引の list, img: 索引の img, agencies: 索引の agencies }。
  // ページを作るときに入れる「はじめの一覧」（site/src/lib/profiles.js の actressRowView）と同じ（tests/test_profiles.mjs で突き合わせている）
  function rowView(row, ctx) {
    var page = pagePath(row.s);
    var out = listUrl(row, ctx.template);
    if (!page && !out) return null;
    return {
      key: (row.id == null ? '' : row.id) + '|' + row.n,
      name: row.n,
      initial: Array.from(row.n)[0] || '',
      href: page || out,
      external: !page,
      img: imageUrl(row.i, ctx.img),
      spec: specText(row),
      agency: agencyLabel(row, ctx.agencies),
      meta: page ? 'このサイトの作品 ' + row.k + '本 ›' : row.k ? 'このサイトの作品 ' + row.k + '本・FANZAで全作品を見る ›' : 'FANZAで全作品を見る ›',
    };
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      normalizeText: normalizeText,
      parseRange: parseRange,
      parseRanges: parseRanges,
      parseBuckets: parseBuckets,
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
      rowView: rowView,
      agencyLabel: agencyLabel,
      PAGE_SIZE: PAGE_SIZE,
      CUPS: CUPS,
      BUCKETS: BUCKETS,
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
  var ctx = { template: '', img: '', agencies: {} };
  var shown = PAGE_SIZE;
  var ready = false; // 索引を読み終えたか
  var staticFallback = function () {
    // 索引を読めなかったとき: 検索の部品を隠し、JavaScript が使えないとき用の一覧を出す
    root.hidden = true;
    if (staticList) staticList.classList.add('is-fallback');
  };

  function field(name) {
    return form.elements[name];
  }

  // フォーム → 条件
  function readQuery() {
    var q = { q: field('q') ? String(field('q').value || '').trim() : '', sort: field('sort') ? field('sort').value : 'works' };
    RANGES.forEach(function (r) {
      if (BUCKETS[r.name]) {
        var picked = [];
        Array.prototype.forEach.call(form.querySelectorAll('input[name="' + r.name + '"]:checked'), function (box) {
          picked.push(box.value);
        });
        q[r.name] = parseBuckets(picked.join(','), r.name).join(',');
        return;
      }
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
    q.ag = field('ag') ? String(field('ag').value || '') : '';
    return q;
  }

  // 条件 → フォーム（URL から開いたとき）
  function writeForm(q) {
    if (field('q')) field('q').value = q.q;
    if (field('sort')) field('sort').value = q.sort;
    RANGES.forEach(function (r) {
      if (BUCKETS[r.name]) {
        var picked = parseBuckets(q[r.name], r.name);
        Array.prototype.forEach.call(form.querySelectorAll('input[name="' + r.name + '"]'), function (box) {
          box.checked = picked.indexOf(box.value) >= 0;
        });
        return;
      }
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
    if (field('ag')) {
      field('ag').value = q.ag || '';
      if (field('ag').value !== (q.ag || '')) field('ag').value = ''; // 選択肢に無い事務所（いまは所属の分かる人がいない）は、指定なしに
    }
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function face(view) {
    var wrap = el('span', 'face face-md');
    wrap.setAttribute('aria-hidden', 'true');
    wrap.appendChild(el('span', 'face-initial', view.initial));
    var src = view.img;
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
    var view = rowView(row, ctx);
    if (!view) return null;
    var li = el('li', 'actress-row');
    li.setAttribute('data-key', view.key);
    var a = el('a', 'actress-row-link');
    a.href = view.href;
    if (view.external) {
      a.target = '_blank';
      a.rel = 'sponsored nofollow noopener noreferrer';
    }
    a.appendChild(face(view));
    var text = el('span', 'actress-row-text');
    text.appendChild(el('span', 'actress-row-name', view.name));
    if (view.spec) text.appendChild(el('span', 'actress-row-spec', view.spec)); // 数字が載っていない人は、行ごと出さない（同じ文が何十行も並ばないように）
    if (view.agency) text.appendChild(el('span', 'actress-row-agency', view.agency));
    text.appendChild(el('span', 'actress-row-meta', view.meta));
    a.appendChild(text);
    li.appendChild(a);
    return li;
  }

  function writeUrl(q) {
    try {
      window.history.replaceState(null, '', window.location.pathname + buildQuery(q));
    } catch (e) {}
  }

  var lastKey = '';
  function render() {
    var q = readQuery();
    // 同じ条件・同じ人数なら、作り直さない（チェックボックスなどは「input」と「change」の両方が来て、同じ一覧を2回作っていたため）
    var key = buildQuery(q) + '|' + shown;
    if (key === lastKey) return;
    if (!ready) {
      // 索引がまだ届いていない: 条件は覚えておき（フォームに残っている）、届いたら作る
      count.textContent = '読み込み中…';
      list.setAttribute('aria-busy', 'true');
      return;
    }
    lastKey = key;
    list.removeAttribute('aria-busy');
    var found = filterRows(rows, q).filter(function (row) {
      return pagePath(row.s) || listUrl(row, ctx.template);
    });
    var visible = found.slice(0, shown);
    list.textContent = '';
    var frag = document.createDocumentFragment();
    visible.forEach(function (row) {
      var li = item(row);
      if (li) frag.appendChild(li);
    });
    list.appendChild(frag);
    count.textContent = countText(found.length);
    more.hidden = found.length <= visible.length;
    updateNotes(q);
    writeUrl(q);
  }

  function countText(n) {
    return n ? n.toLocaleString('ja-JP') + '人が見つかりました' : '条件に合う女優がいません。条件をゆるめてみてね。';
  }

  function updateNotes(q) {
    if (note) note.hidden = !hasNumericFilter(q);
    if (filterNote) {
      var active = RANGES.filter(function (r) {
        return q[r.name];
      }).length + (q.cup ? 1 : 0) + (q.ag ? 1 : 0) + (q.site ? 1 : 0) + (q.face ? 1 : 0);
      filterNote.textContent = active ? '（' + active + '件を指定中）' : '';
    }
  }

  function onChange() {
    shown = PAGE_SIZE;
    render();
  }

  // 名前の欄は、打ち終わるのを少し待ってから作る（1文字ごとに約1万人を絞り込んで、一覧を作り直さないように）
  var typingTimer = 0;
  form.addEventListener('input', function (event) {
    clearTimeout(typingTimer);
    if (event.target && event.target.name === 'q') typingTimer = setTimeout(onChange, TYPING_WAIT_MS);
    else onChange();
  });
  form.addEventListener('change', function (event) {
    if (event.target && event.target.name === 'q') return; // 名前の欄は input で扱う（欄から離れたときの change で、もう一度作らない）
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

  // URL の条件を、索引を待たずにフォームへ入れる（検索欄はページを開いたときから使える。2026-10-07）
  var first = parseQuery(window.location.search);
  writeForm(first);
  // 広い画面か、条件つきで開いたときは、くわしい条件の欄を最初から開いておく（スマホでは、たたんだまま。結果がすぐ見えるように）
  var wide = typeof window.matchMedia === 'function' && window.matchMedia('(min-width: 720px)').matches;
  if (filters && (wide || hasNumericFilter(first) || first.site || first.face || first.sort !== 'works')) filters.open = true;
  // ページを作るときに入れた「はじめの一覧」（条件なし・作品の多い順の、はじめの PAGE_SIZE 人）が、いまの条件の一覧なら、そのまま使う
  var prerendered = list.getAttribute('data-first') === '1';
  if (prerendered && buildQuery(first) === '') lastKey = '|' + PAGE_SIZE;
  else render(); // 条件つきで開いたとき: 「読み込み中…」にして、索引が届いたら作る

  // 索引を読み終えたあと、手のあいたときに、名前の照らし合わせ用の文字を先に作っておく（最初の1文字が重くならないように）
  function warmUp(start) {
    var idle = window.requestIdleCallback || function (fn) {
      return setTimeout(fn, 50);
    };
    idle(function () {
      var end = Math.min(rows.length, start + WARM_CHUNK);
      for (var i = start; i < end; i++) matchKeys(rows[i]);
      if (end < rows.length) warmUp(end);
    });
  }

  fetch(indexUrl, { credentials: 'same-origin' })
    .then(function (res) {
      if (!res.ok) throw new Error('status ' + res.status);
      return res.json();
    })
    .then(function (data) {
      rows = data && Array.isArray(data.actresses) ? data.actresses.filter(function (r) {
        return r && typeof r === 'object' && typeof r.n === 'string' && r.n;
      }) : [];
      if (!rows.length) {
        staticFallback(); // データが無いときは、最初から載っている一覧
        return;
      }
      ctx = {
        template: data && typeof data.list === 'string' ? data.list : '',
        img: data && typeof data.img === 'string' ? data.img : '',
        agencies: data && data.agencies && typeof data.agencies === 'object' ? data.agencies : {},
      };
      ready = true;
      if (lastKey) {
        // はじめの一覧が、ブラウザで作る一覧と同じか確かめる（違えば作り直す）
        var want = filterRows(rows, readQuery()).filter(function (row) {
          return pagePath(row.s) || listUrl(row, ctx.template);
        });
        var cells = list.children;
        var same = cells.length === Math.min(PAGE_SIZE, want.length) && countText(want.length) === count.textContent;
        for (var i = 0; same && i < cells.length; i++) {
          var view = rowView(want[i], ctx);
          same = Boolean(view) && cells[i].getAttribute('data-key') === view.key;
        }
        if (!same) lastKey = '';
      }
      render();
      warmUp(0);
    })
    .catch(function () {
      staticFallback();
    });
})();
