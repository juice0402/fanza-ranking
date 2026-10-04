// お気に入り（ブックマーク）。作品・出演者・メーカーに ☆ を付けて、「お気に入り」ページに集める。
// 保存先は、この端末のこのブラウザの localStorage だけ（サーバーには何も送らない）。
// お気に入りの出演者・メーカーの新作・予約は、「お気に入り」ページと、トップの小さなお知らせで教える。
// JavaScript や localStorage が使えないときは、☆ボタンを出さない（サイトの他の機能には影響しない）。
(function () {
  var KEY = 'fanza-fav-v1';
  var TYPES = ['work', 'actress', 'maker'];
  var LIMIT = 300; // 種類ごとの最大数（端末の保存容量を使い切らないため）
  var CID = /^[A-Za-z0-9_-]+$/;
  var DAY = /^\d{4}-\d{2}-\d{2}$/;
  var SLUG = /^[0-9a-f]{10}$/;
  var RECENT_DAYS = 30; // 「最近発売」に出す日数
  var BANNER_DAYS = 7; // トップのお知らせに数える、発売済みの日数

  // ------------------------------------------------------------
  // 部品（画面に依存しない。tests/test_favorites.mjs でテストしている）
  // ------------------------------------------------------------
  function emptyStore() {
    return { v: 1, work: {}, actress: {}, maker: {} };
  }

  function str(value, max) {
    return typeof value === 'string' ? value.slice(0, max) : '';
  }

  // 1件分を、安全な形に直す。使えない値なら null
  function cleanEntry(type, key, raw) {
    if (typeof key !== 'string' || !key || key.length > 200) return null;
    var src = raw && typeof raw === 'object' ? raw : {};
    var at = typeof src.at === 'number' && isFinite(src.at) ? src.at : 0;
    if (type === 'work') {
      if (!CID.test(key)) return null;
      var title = str(src.t, 300);
      if (!title) return null;
      var actress = Array.isArray(src.a) ? src.a.filter(function (n) { return typeof n === 'string' && n; }).slice(0, 10).map(function (n) { return n.slice(0, 100); }) : [];
      return {
        t: title,
        i: typeof src.i === 'string' && src.i.indexOf('https://') === 0 ? src.i.slice(0, 500) : '',
        d: typeof src.d === 'string' && DAY.test(src.d) ? src.d : '',
        a: actress,
        m: str(src.m, 100),
        at: at,
      };
    }
    if (type === 'actress' || type === 'maker') {
      return { slug: typeof src.slug === 'string' && SLUG.test(src.slug) ? src.slug : '', at: at };
    }
    return null;
  }

  // 保存されている文字列を、安全な形に直して読む（壊れていたら空にする）
  function parseStore(text) {
    var store = emptyStore();
    var data;
    try {
      data = JSON.parse(text);
    } catch (e) {
      return store;
    }
    if (!data || typeof data !== 'object') return store;
    TYPES.forEach(function (type) {
      var src = data[type];
      if (!src || typeof src !== 'object' || Array.isArray(src)) return;
      Object.keys(src).slice(0, LIMIT).forEach(function (key) {
        var entry = cleanEntry(type, key, src[key]);
        if (entry) store[type][key] = entry;
      });
    });
    return store;
  }

  function isOn(store, type, key) {
    return Object.prototype.hasOwnProperty.call(store[type] || {}, key);
  }

  // お気に入りの付け外し。{ store, on, full } を返す（上限に達したときは追加せず full: true）
  function toggle(store, type, key, info, now) {
    var next = parseStore(JSON.stringify(store));
    if (TYPES.indexOf(type) < 0) return { store: next, on: false, full: false };
    if (isOn(next, type, key)) {
      delete next[type][key];
      return { store: next, on: false, full: false };
    }
    if (Object.keys(next[type]).length >= LIMIT) return { store: next, on: false, full: true };
    var entry = cleanEntry(type, key, Object.assign({}, info, { at: now }));
    if (!entry) return { store: next, on: false, full: false };
    next[type][key] = entry;
    return { store: next, on: true, full: false };
  }

  function remove(store, type, key) {
    var next = parseStore(JSON.stringify(store));
    if (TYPES.indexOf(type) >= 0) delete next[type][key];
    return next;
  }

  function hasPeople(store) {
    return Object.keys(store.actress).length + Object.keys(store.maker).length > 0;
  }

  // 作品（索引の1件 {c,t,d,a,m,i}）が、お気に入りの出演者・メーカーの作品か
  function matches(store, item) {
    var cast = Array.isArray(item.a) ? item.a : [];
    for (var i = 0; i < cast.length; i++) if (isOn(store, 'actress', cast[i])) return true;
    return Boolean(item.m) && isOn(store, 'maker', item.m);
  }

  // 専用ページ（作品が2本以上になるとできる）の短い名前を、☆を付けたあとで分かったときに補う。
  // pages は索引の { actress: {名前: 短い名前}, maker: {...} }。{ store, changed } を返す（元の store は変えない）
  function resolveSlugs(store, pages) {
    var next = parseStore(JSON.stringify(store));
    var changed = false;
    ['actress', 'maker'].forEach(function (type) {
      var known = pages && typeof pages[type] === 'object' && pages[type] ? pages[type] : {};
      Object.keys(next[type]).forEach(function (name) {
        var entry = next[type][name];
        if (entry.slug || !Object.prototype.hasOwnProperty.call(known, name)) return;
        if (typeof known[name] === 'string' && SLUG.test(known[name])) {
          entry.slug = known[name];
          changed = true;
        }
      });
    });
    return { store: next, changed: changed };
  }

  // 索引の pages（専用ページと発売日カレンダーの両方がある人・メーカー）に、同じ短い名前で入っているか
  function hasCalendar(pages, type, name, slug) {
    var known = pages && typeof pages[type] === 'object' && pages[type] ? pages[type] : {};
    return Boolean(slug) && Object.prototype.hasOwnProperty.call(known, name) && known[name] === slug;
  }

  // "2026-10-07" → "2026年10月7日"（日付でなければ空）
  function jpDate(day) {
    return typeof day === 'string' && DAY.test(day) ? +day.slice(0, 4) + '年' + +day.slice(5, 7) + '月' + +day.slice(8, 10) + '日' : '';
  }

  function addDays(day, n) {
    var t = Date.UTC(+day.slice(0, 4), +day.slice(5, 7) - 1, +day.slice(8, 10)) + n * 86400000;
    return new Date(t).toISOString().slice(0, 10);
  }

  function jstToday(nowMs) {
    return new Date(nowMs + 9 * 3600000).toISOString().slice(0, 10);
  }

  // お気に入りの新作。upcoming は発売日の近い順、recent は発売日の新しい順
  function pickNew(store, items, today, recentDays) {
    var from = addDays(today, -recentDays);
    var upcoming = [];
    var recent = [];
    (Array.isArray(items) ? items : []).forEach(function (item) {
      if (!item || typeof item.c !== 'string' || !CID.test(item.c) || typeof item.d !== 'string' || !DAY.test(item.d) || !matches(store, item)) return;
      if (item.d > today) upcoming.push(item);
      else if (item.d >= from) recent.push(item);
    });
    upcoming.sort(function (a, b) { return a.d < b.d ? -1 : a.d > b.d ? 1 : 0; });
    recent.sort(function (a, b) { return a.d < b.d ? 1 : a.d > b.d ? -1 : 0; });
    return { upcoming: upcoming, recent: recent };
  }

  // 一覧に出す出演者（先頭から max 人）と、出しきれない人数（オムニバスなど出演者が多い作品で、カードが長くならないように。
  // max は site/src/config.js の CAST_LIMIT と同じ3人。tests で突き合わせている）
  var CAST_LIMIT = 3;
  function castShown(list, max) {
    var names = list.slice(0, max);
    return { names: names, more: list.length - names.length };
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      castShown: castShown, CAST_LIMIT: CAST_LIMIT,
      emptyStore: emptyStore, parseStore: parseStore, isOn: isOn, toggle: toggle, remove: remove,
      hasPeople: hasPeople, matches: matches, pickNew: pickNew, resolveSlugs: resolveSlugs, hasCalendar: hasCalendar, addDays: addDays, jstToday: jstToday, jpDate: jpDate, LIMIT: LIMIT,
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
    storage.setItem('fanza-fav-test', '1');
    storage.removeItem('fanza-fav-test');
  } catch (e) {
    storage = null; // 保存できない環境（プライベートブラウズなど）
  }
  if (!storage) {
    // 保存できない環境（プライベートブラウズなど）。「お気に入り」ページが空白にならないよう、理由を出す
    var emptyRoot = document.getElementById('fav-root');
    if (emptyRoot) {
      emptyRoot.textContent = '';
      var note = document.createElement('p');
      note.className = 'empty';
      note.textContent = 'このブラウザでは、お気に入りを保存できません（プライベートブラウズなど）。通常のブラウズで開くと使えます。';
      emptyRoot.appendChild(note);
    }
    return;
  }

  function read() {
    try {
      return parseStore(storage.getItem(KEY));
    } catch (e) {
      return emptyStore();
    }
  }

  function write(store) {
    try {
      storage.setItem(KEY, JSON.stringify(store));
      return true;
    } catch (e) {
      return false;
    }
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function refreshButtons(store) {
    Array.prototype.forEach.call(document.querySelectorAll('.fav-btn'), function (button) {
      var on = isOn(store, button.getAttribute('data-fav-type'), button.getAttribute('data-fav-key'));
      button.hidden = false;
      button.setAttribute('aria-pressed', on ? 'true' : 'false');
      button.querySelector('.fav-star').textContent = on ? '★' : '☆';
      var label = button.querySelector('.fav-label');
      if (label) label.textContent = button.getAttribute(on ? 'data-on' : 'data-off') || '';
    });
  }

  function infoOf(button) {
    var type = button.getAttribute('data-fav-type');
    if (type === 'work') {
      return {
        t: button.getAttribute('data-title'),
        i: button.getAttribute('data-image'),
        d: button.getAttribute('data-date'),
        a: (button.getAttribute('data-actress') || '').split('、').filter(Boolean),
        m: button.getAttribute('data-maker'),
      };
    }
    return { slug: button.getAttribute('data-slug') || '' };
  }

  document.addEventListener('click', function (event) {
    var button = event.target.closest ? event.target.closest('.fav-btn') : null;
    if (!button) return;
    var result = toggle(read(), button.getAttribute('data-fav-type'), button.getAttribute('data-fav-key'), infoOf(button), Date.now());
    if (result.full) {
      window.alert('お気に入りがいっぱいです（' + LIMIT + '件まで）。「お気に入り」ページで、いらないものを外してください。');
      return;
    }
    write(result.store);
    refreshButtons(result.store);
  });

  refreshButtons(read());
  // 「戻る」で前のページに戻ったとき（ブラウザが前の状態をそのまま出すとき）や、別のタブで付け外ししたときも、☆を今の状態にそろえる
  window.addEventListener('pageshow', function (event) {
    if (event.persisted) refreshButtons(read());
  });
  window.addEventListener('storage', function (event) {
    if (event.key === KEY) refreshButtons(read());
  });

  // 索引（お気に入りの出演者・メーカーの新作を探すための、最近の作品の一覧）
  var indexPromise = null;
  function loadIndex() {
    if (!indexPromise) {
      indexPromise = fetch('/data/favorites-index.json', { cache: 'no-cache' })
        .then(function (res) {
          if (!res.ok) throw new Error('status ' + res.status);
          return res.json();
        })
        .then(function (data) {
          var d = data && typeof data === 'object' ? data : {};
          return { items: Array.isArray(d.items) ? d.items : [], pages: d.pages && typeof d.pages === 'object' ? d.pages : {} };
        })
        .catch(function (error) {
          indexPromise = null; // 失敗を覚えっぱなしにしない（つながるようになったら、次に開いたときに読み直す）
          throw error;
        });
    }
    return indexPromise;
  }

  // ---- トップの小さなお知らせ ----
  var banner = document.getElementById('fav-banner');
  if (banner) {
    var s = read();
    if (hasPeople(s)) {
      loadIndex().then(function (index) {
        var found = pickNew(s, index.items, jstToday(Date.now()), BANNER_DAYS);
        var count = found.upcoming.length + found.recent.length;
        if (count > 0) {
          banner.textContent = '★ お気に入りの新作・予約が ' + count + '本あります';
          banner.hidden = false;
        }
      }).catch(function () {});
    }
  }

  // ---- 「お気に入り」ページ ----
  var root = document.getElementById('fav-root');
  if (root) renderPage(root);

  function workRow(item, onRemove) {
    var row = el('li', 'fav-row');
    var link = el('a', 'fav-row-link');
    link.href = '/item/' + item.c + '/';
    if (item.i && item.i.indexOf('https://') === 0) {
      var img = el('img', 'fav-thumb');
      img.src = item.i;
      img.alt = '';
      img.loading = 'lazy';
      img.width = 60;
      img.height = 84;
      link.appendChild(img);
    }
    var body = el('span', 'fav-row-body');
    // ph-js: 文節の区切り（タイトルに入っている U+200B）と「、」の所だけで改行する（名前・語の途中で改行しない）
    body.appendChild(el('span', 'fav-row-title ph-js', item.t));
    var cast = Array.isArray(item.a) ? item.a.filter(function (n) { return typeof n === 'string' && n; }) : [];
    var meta = el('span', 'fav-row-meta ph-js', jpDate(item.d) + (cast.length ? '　' : ''));
    var shown = castShown(cast, CAST_LIMIT);
    shown.names.forEach(function (name, i) {
      if (i > 0) meta.appendChild(document.createTextNode('、'));
      meta.appendChild(el('span', name.length <= 10 ? 'nb' : '', name)); // 短い名前は、途中で改行しない
    });
    if (shown.more > 0) meta.appendChild(document.createTextNode(' ほか' + shown.more + '名'));
    body.appendChild(meta);
    link.appendChild(body);
    row.appendChild(link);
    if (onRemove) {
      var button = el('button', 'fav-remove', '外す');
      button.type = 'button';
      button.addEventListener('click', function () {
        onRemove(button);
      });
      row.appendChild(button);
    }
    return row;
  }

  function section(title, note) {
    var box = el('section', 'section');
    box.appendChild(el('h2', 'section-title', title));
    if (note) box.appendChild(el('p', 'section-note', note));
    return box;
  }

  // 「外す」を押すと一覧を作り直すので、フォーカスを、同じ位置の「外す」（無ければ、ページの最初の見出し）へ移す（ページの先頭に飛ばないように）
  function indexOfRemove(container, button) {
    return Array.prototype.indexOf.call(container.querySelectorAll('.fav-remove'), button);
  }

  function refocus(container, at) {
    var buttons = container.querySelectorAll('.fav-remove');
    var target = buttons.length ? buttons[Math.max(0, Math.min(at, buttons.length - 1))] : container.querySelector('h2, .empty');
    if (!target) return;
    if (!buttons.length) target.setAttribute('tabindex', '-1');
    try {
      target.focus({ preventScroll: false });
    } catch (e) {}
  }

  function addCalendarLink(body, type, name, slug, base) {
    loadIndex().then(function (index) {
      if (!hasCalendar(index.pages, type, name, slug) || !body.isConnected) return;
      var cal = el('a', 'fav-row-meta', '発売日をカレンダーで受け取る');
      cal.href = 'webcal://' + location.host + base + slug + '.ics';
      body.appendChild(cal);
    }).catch(function () {});
  }

  function renderPage(container) {
    var store = read();
    var people = hasPeople(store);
    container.textContent = '';

    if (!people && !Object.keys(store.work).length) {
      container.appendChild(el('p', 'empty', 'まだお気に入りがありません。作品・出演者・メーカーのページにある ☆ を押すと、ここに集まります。'));
      return;
    }

    // 1) お気に入りの新作・予約
    if (people) {
      var news = section('お気に入りの新作・予約', '登録した出演者・メーカーの、これから発売される作品と、最近発売された作品です。');
      var holder = el('div');
      holder.appendChild(el('p', 'fav-loading', '読み込み中…'));
      news.appendChild(holder);
      container.appendChild(news);
      loadIndex().then(function (index) {
        // ☆を付けたときは専用ページが無かった人に、あとからページができていたら、リンクを補って描き直す
        var resolved = resolveSlugs(read(), index.pages);
        if (resolved.changed && write(resolved.store)) {
          renderPage(container);
          return;
        }
        var found = pickNew(store, index.items, jstToday(Date.now()), RECENT_DAYS);
        holder.textContent = '';
        [['これから発売（' + found.upcoming.length + '本）', found.upcoming], ['最近発売（' + found.recent.length + '本）', found.recent]].forEach(function (pair) {
          holder.appendChild(el('h3', 'fav-sub', pair[0]));
          if (!pair[1].length) {
            holder.appendChild(el('p', 'fav-none', '該当する作品はありません'));
            return;
          }
          var list = el('ul', 'fav-list');
          pair[1].forEach(function (item) { list.appendChild(workRow(item)); });
          holder.appendChild(list);
        });
      }).catch(function () {
        holder.textContent = '';
        holder.appendChild(el('p', 'fav-none', '新作の一覧を読み込めませんでした。しばらくしてからもう一度開いてください。'));
      });
    }

    // 2) お気に入りの出演者・メーカー
    [['actress', 'お気に入りの出演者', '/actress/', '/calendar/actress/'], ['maker', 'お気に入りのメーカー', '/maker/', '/calendar/maker/']].forEach(function (def) {
      var names = Object.keys(store[def[0]]);
      if (!names.length) return;
      var box = section(def[1]);
      var list = el('ul', 'fav-list');
      names.sort(function (a, b) { return store[def[0]][b].at - store[def[0]][a].at; }).forEach(function (name) {
        var entry = store[def[0]][name];
        var row = el('li', 'fav-row');
        var body = el('span', 'fav-row-body');
        if (entry.slug) {
          var link = el('a', 'fav-row-title fav-row-title-link ph-js', name);
          link.href = def[2] + entry.slug + '/';
          body.appendChild(link);
          // 発売日カレンダーは、新作・予約が載っている人・メーカーだけにある（索引の pages に入っている人）。索引を読んでから、あるときだけ出す
          addCalendarLink(body, def[0], name, entry.slug, def[3]);
        } else {
          body.appendChild(el('span', 'fav-row-title ph-js', name));
          body.appendChild(el('span', 'fav-row-meta', '作品が2本以上になると、専用ページとカレンダーが使えます'));
        }
        row.appendChild(body);
        var button = el('button', 'fav-remove', '外す');
        button.type = 'button';
        button.addEventListener('click', function () {
          var at = indexOfRemove(container, button);
          write(remove(read(), def[0], name));
          renderPage(container);
          refocus(container, at);
        });
        row.appendChild(button);
        list.appendChild(row);
      });
      box.appendChild(list);
      container.appendChild(box);
    });

    // 3) お気に入りの作品
    var works = Object.keys(store.work);
    if (works.length) {
      var wbox = section('お気に入りの作品（' + works.length + '本）');
      var wlist = el('ul', 'fav-list');
      works.sort(function (a, b) { return store.work[b].at - store.work[a].at; }).forEach(function (cid) {
        var w = store.work[cid];
        wlist.appendChild(workRow({ c: cid, t: w.t, i: w.i, d: w.d, a: w.a }, function (button) {
          var at = indexOfRemove(container, button);
          write(remove(read(), 'work', cid));
          renderPage(container);
          refocus(container, at);
        }));
      });
      wbox.appendChild(wlist);
      container.appendChild(wbox);
    }
  }
})();
