// つづきから（2026-11-12 #256）: 女優のページ・作品ページ（/item/・/w/）を開いたら、この端末の localStorage に記録し、
// トップの「つづきから」の棚（index.astro の #recent-shelf）に、最後に見た女優6人・作品3本を出す。
// 記録はこの端末の中だけ。どこにも送らない。題を隠している作品（未成年を連想させるタイトル）は、ページの側が記録の印を付けない。
// 記録するページ: この script のタグの data-recent-type（actress / work）と中身。トップ: この中身をそのまま棚のすぐ下に入れる（inlineScript。読みこむそばに出すので、下がずれない）
(function () {
  var KEY = 'fanza-recent-v1';
  var MAX_ACTRESS = 6;
  var MAX_WORK = 3;
  var TITLE_MAX = 40;
  var CID = /^[A-Za-z0-9_-]+$/;
  var ACTRESS_PATH = /^\/actress\/[A-Za-z0-9_-]+\/$/;
  var WORK_PATH = /^\/(?:item|w)\/[A-Za-z0-9_-]+\/$/;

  // ------------------------------------------------------------
  // 部品（画面に依存しない。tests/test_recent.mjs でテストしている）
  // ------------------------------------------------------------
  function emptyRecent() {
    return { v: 1, a: [], w: [] };
  }

  function str(value, max) {
    return typeof value === 'string' ? value.trim().slice(0, max) : '';
  }

  function httpsUrl(value) {
    return typeof value === 'string' && value.indexOf('https://') === 0 && value.length <= 500 ? value : '';
  }

  function stamp(value) {
    return typeof value === 'number' && isFinite(value) && value > 0 ? value : 0;
  }

  // 題を短く切る（文字の数で。切ったときは「…」）
  function shortTitle(title) {
    var chars = Array.from(String(title || '').replace(/​/g, '').trim());
    return chars.length > TITLE_MAX ? chars.slice(0, TITLE_MAX - 1).join('') + '…' : chars.join('');
  }

  // 1件を安全な形に直す。使えない値なら null
  function cleanActress(raw) {
    if (!raw || typeof raw !== 'object') return null;
    var name = str(raw.n, 100);
    var path = str(raw.p, 200);
    if (!name || !ACTRESS_PATH.test(path)) return null;
    return { n: name, p: path, f: httpsUrl(raw.f), at: stamp(raw.at) };
  }

  function cleanWork(raw) {
    if (!raw || typeof raw !== 'object') return null;
    var cid = str(raw.c, 100);
    var title = shortTitle(str(raw.t, 300));
    var path = str(raw.p, 200);
    if (!CID.test(cid) || !title || !WORK_PATH.test(path)) return null;
    return { c: cid, t: title, i: httpsUrl(raw.i), p: path, at: stamp(raw.at) };
  }

  var KINDS = {
    actress: { list: 'a', max: MAX_ACTRESS, clean: cleanActress, key: function (e) { return e.n; } },
    work: { list: 'w', max: MAX_WORK, clean: cleanWork, key: function (e) { return e.c; } },
  };

  // 並びを直す: こわれた行を捨て、同じ人・作品は前のほうだけ残し、数を切る
  function cleanList(kind, list) {
    var out = [];
    var seen = {};
    if (!Array.isArray(list)) return out;
    for (var n = 0; n < list.length && out.length < kind.max; n++) {
      var entry = kind.clean(list[n]);
      if (!entry) continue;
      var k = kind.key(entry);
      if (Object.prototype.hasOwnProperty.call(seen, k)) continue;
      seen[k] = 1;
      out.push(entry);
    }
    return out;
  }

  // 保存の文字から読む。こわれていれば空
  function parseRecent(text) {
    var data;
    try {
      data = JSON.parse(text || 'null');
    } catch (e) {
      return emptyRecent();
    }
    if (!data || typeof data !== 'object' || Array.isArray(data)) return emptyRecent();
    return { v: 1, a: cleanList(KINDS.actress, data.a), w: cleanList(KINDS.work, data.w) };
  }

  // 見たものを先頭に（同じ人・作品は先頭に移すだけで重ねない）
  function remember(store, type, raw, now) {
    var kind = KINDS[type];
    var base = store && typeof store === 'object' ? store : emptyRecent();
    var next = { v: 1, a: cleanList(KINDS.actress, base.a), w: cleanList(KINDS.work, base.w) };
    if (!kind) return next;
    var src = {};
    for (var p in raw) if (Object.prototype.hasOwnProperty.call(raw, p)) src[p] = raw[p];
    src.at = now;
    var entry = kind.clean(src);
    if (!entry) return next;
    var key = kind.key(entry);
    next[kind.list] = [entry].concat(next[kind.list].filter(function (e) { return kind.key(e) !== key; })).slice(0, kind.max);
    return next;
  }

  function hasRecent(store) {
    return Boolean(store && (store.a.length || store.w.length));
  }

  // サムネの画像のURL（site/src/lib/items.js の smallImage・tinyImage・THUMB_MEDIA、favorites.js と同じ）
  var THUMB_MEDIA = '(max-width: 480px)';
  var AWS_IMG = 'https://awsimgsrc.dmm.co.jp/pics_dig/';
  function smallImageUrl(url) {
    var s = String(url || '');
    return /^https:\/\/pics\.dmm\.co\.jp\/.+pl\.jpg$/.test(s) ? s.replace(/pl\.jpg$/, 'ps.jpg') : s;
  }
  function tinyImageUrl(url) {
    var s = String(url || '');
    if (/^https:\/\/pics\.dmm\.co\.jp\/digital\/video\/[^?#]+p[ls]\.jpg$/.test(s)) return AWS_IMG + s.slice(23).replace(/p[ls]\.jpg$/, 'ps.jpg') + '?w=200&q=75';
    return /^https:\/\/pics\.dmm\.co\.jp\/[^?#]+pl\.jpg$/.test(s) ? s.replace(/pl\.jpg$/, 'ps.jpg') : s;
  }
  function unresizedUrl(url) {
    var s = String(url || '');
    return s.indexOf(AWS_IMG) === 0 ? 'https://pics.dmm.co.jp/' + s.slice(AWS_IMG.length).replace(/\?.*$/, '') : s;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      KEY: KEY, MAX_ACTRESS: MAX_ACTRESS, MAX_WORK: MAX_WORK, TITLE_MAX: TITLE_MAX, THUMB_MEDIA: THUMB_MEDIA,
      emptyRecent: emptyRecent, parseRecent: parseRecent, remember: remember, hasRecent: hasRecent, shortTitle: shortTitle,
      smallImageUrl: smallImageUrl, tinyImageUrl: tinyImageUrl, unresizedUrl: unresizedUrl,
    };
    return;
  }
  if (typeof document === 'undefined') return;

  // ------------------------------------------------------------
  // 画面
  // ------------------------------------------------------------
  var storage = null;
  try {
    storage = window.localStorage;
  } catch (e) {
    storage = null;
  }

  function read() {
    try {
      return parseRecent(storage ? storage.getItem(KEY) : null);
    } catch (e) {
      return emptyRecent();
    }
  }

  // 見たページを記録する（女優のページ・作品ページ。script のタグの data-recent-type）
  var mark = document.querySelector('script[data-recent-type]');
  if (mark && storage) {
    var d = mark.dataset;
    var raw = d.recentType === 'actress' ? { n: d.name, p: d.path, f: d.face } : { c: d.cid, t: d.title, i: d.image, p: d.path };
    try {
      var next = remember(read(), d.recentType, raw, Date.now());
      if (hasRecent(next)) storage.setItem(KEY, JSON.stringify(next));
    } catch (e) {
      // 保存できない環境（プライベートブラウズ・容量いっぱいなど）。何もしない
    }
  }

  // トップの「つづきから」の棚
  var shelf = document.getElementById('recent-shelf');
  if (!shelf) return;
  var root = document.documentElement;
  function close() {
    shelf.hidden = true;
    root.classList.remove('has-recent');
  }
  var store = read();
  if (!hasRecent(store)) {
    close();
    return;
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  var body = shelf.querySelector('[data-recent-body]');
  body.textContent = '';

  // 女優: 顔の丸の3つ並び（CastFaces.astro と同じ形。順位の数字は出さない）
  if (store.a.length) {
    var faces = el('ol', 'hot cast-faces recent-faces');
    store.a.forEach(function (a) {
      var li = el('li', 'hot-cell');
      var link = el('a', 'hot-link');
      link.href = a.p;
      var wrap = el('span', 'hot-face');
      var face = el('span', 'face face-lg');
      face.setAttribute('aria-hidden', 'true');
      face.appendChild(el('span', 'face-initial', Array.from(a.n)[0] || ''));
      if (a.f) {
        var img = el('img', 'face-img');
        img.src = a.f;
        img.alt = '';
        img.width = 112;
        img.height = 112;
        img.decoding = 'async';
        img.referrerPolicy = 'no-referrer';
        img.onerror = function () { this.remove(); };
        face.appendChild(img);
      }
      wrap.appendChild(face);
      link.appendChild(wrap);
      link.appendChild(el('span', 'hot-name', a.n));
      li.appendChild(link);
      faces.appendChild(li);
    });
    body.appendChild(faces);
  }

  // 作品: 小さな表紙＋題の行（作品検索の結果と同じ形）
  if (store.w.length) {
    var rows = el('ul', 'ws-list work-rows recent-works');
    var small = window.matchMedia && window.matchMedia(THUMB_MEDIA).matches;
    store.w.forEach(function (w) {
      var li = el('li', 'ws-row');
      var item = el('article', 'item');
      var cover = el('a', 'item-cover');
      cover.href = w.p;
      cover.tabIndex = -1;
      cover.setAttribute('aria-hidden', 'true');
      if (w.i) {
        var img = el('img', 'item-img is-small');
        img.src = small ? tinyImageUrl(w.i) : smallImageUrl(w.i);
        img.alt = '';
        img.decoding = 'async';
        img.referrerPolicy = 'no-referrer';
        img.onerror = function () {
          var back = unresizedUrl(this.src);
          if (back !== this.src) this.src = back;
          else this.remove();
        };
        cover.appendChild(img);
      }
      item.appendChild(cover);
      var h = el('h3', 'item-title');
      var link = el('a', 'item-title-link', w.t);
      link.href = w.p;
      h.appendChild(link);
      item.appendChild(h);
      li.appendChild(item);
      rows.appendChild(li);
    });
    body.appendChild(rows);
  }

  var clear = el('button', 'recent-clear', '記録を消す');
  clear.type = 'button';
  clear.addEventListener('click', function () {
    try {
      storage.removeItem(KEY);
    } catch (e) {}
    close();
  });
  body.appendChild(clear);
  shelf.hidden = false;
})();
