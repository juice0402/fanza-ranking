// 「運命の作品」（トップ）: スロットマシンのように、3つの窓で表紙が回って、左から順に止まり、人気の作品（ひとことコメントのある作品）が3本決まる。
// 候補はページの中の小さなデータ（#gacha-data。site/src/lib/gacha.js が作る）。「VR作品を隠す」のときはVR作品を、「単体作品のみ表示」のときは
// 単体作品でない作品を、候補から外す。直前に出た作品は、しばらく出さない。動きを減らす設定の人には、回す演出をしない。
// JavaScript が使えないときは、欄ごと出さない（ボタンが動かないため）。DOM は textContent で作る
(function () {
  var REELS = 3; // 窓の数（決まる作品の数）
  var RECENT = 9; // 直前に出たこの本数は、続けて出さない
  var TICK_MS = 80; // 回っているあいだ、表紙が入れかわる間隔
  var STOP_MS = [700, 1150, 1600]; // 左から順に止まる時刻

  // 候補の番号の中から、重ならない n 本。recent（直前に出た番号）は、ほかに候補があるあいだは選ばない。rand() は 0以上1未満
  function pickMany(candidates, recent, rand, n) {
    var fresh = candidates.filter(function (c) {
      return recent.indexOf(c) < 0;
    });
    var stale = candidates.filter(function (c) {
      return recent.indexOf(c) >= 0;
    });
    var out = [];
    [fresh, stale].forEach(function (from) {
      var rest = from.slice();
      while (out.length < n && rest.length) {
        var at = Math.min(rest.length - 1, Math.floor(rand() * rest.length));
        out.push(rest.splice(at, 1)[0]);
      }
    });
    return out;
  }

  // 候補にする番号（VR作品を隠すときはVRでない作品、単体作品のみのときは単体作品だけ）
  function eligible(pool, hideVr, onlySolo) {
    var out = [];
    for (var i = 0; i < pool.length; i++) {
      if (hideVr && pool[i].v === 1) continue;
      if (onlySolo && pool[i].o !== 1) continue;
      out.push(i);
    }
    return out;
  }

  // スマホ（画面の幅が THUMB_MEDIA）のときは、表紙のいちばん小さい版（…pt.jpg。90×122）を読む
  // （運営者の希望「スマホのサムネは画素数を落として最高速化」。2026-10-07。site/src/lib/items.js の THUMB_MEDIA・tinyImage と同じ）
  var THUMB_MEDIA = '(max-width: 480px)';
  function tinyImageUrl(url) {
    var s = String(url || '');
    return /^https:\/\/pics\.dmm\.co\.jp\//.test(s) && /p[ls]\.jpg$/.test(s) ? s.replace(/p[ls]\.jpg$/, 'pt.jpg') : s;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { pickMany: pickMany, eligible: eligible, REELS: REELS, RECENT: RECENT, THUMB_MEDIA: THUMB_MEDIA, tinyImageUrl: tinyImageUrl }; // tests/test_gacha.mjs 用
    return;
  }
  if (typeof document === 'undefined') return;

  var section = document.getElementById('gacha');
  if (!section) return;
  // 候補: トップはページの中の小さなデータ（#gacha-data）、作品ページは1つのファイル（data-src="/data/gacha.json"）を読む
  var data = document.getElementById('gacha-data');
  var src = section.getAttribute('data-src');
  var exclude = section.getAttribute('data-exclude') || '';
  if (data) {
    try {
      start(JSON.parse(data.textContent || '[]'));
    } catch (e) {
      section.hidden = true;
    }
  } else if (src && typeof fetch === 'function') {
    fetch(src, { credentials: 'same-origin' })
      .then(function (res) {
        if (!res.ok) throw new Error('status ' + res.status);
        return res.json();
      })
      .then(start)
      .catch(function () {
        section.hidden = true; // 候補を読めなかったら、欄ごと隠す
      });
  } else {
    section.hidden = true;
  }

  function start(raw) {
  var pool = (Array.isArray(raw) ? raw : []).filter(function (row) {
    return row && typeof row.c === 'string' && /^[A-Za-z0-9_-]+$/.test(row.c) && row.c !== exclude && typeof row.t === 'string' && typeof row.i === 'string' && /^https:\/\/[^/]*dmm\.co\.jp\//.test(row.i);
  });
  var reels = section.querySelectorAll('.reel');
  var button = section.querySelector('[data-gacha-draw]');
  if (pool.length < REELS || reels.length !== REELS || !button) {
    section.hidden = true; // 候補が足りないときは、欄ごと隠す
    return;
  }
  section.hidden = false;
  button.disabled = false; // 欄は、はじめから出ている（CSS の html.js）。候補がそろったので「まわす」を押せるように

  var recent = [];
  var busy = false;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var root = document.documentElement;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  var tiny = Boolean(window.matchMedia && window.matchMedia(THUMB_MEDIA).matches);

  function windowWith(src) {
    var win = el('span', 'reel-window');
    var img = el('img', 'item-img is-small');
    img.alt = '';
    img.decoding = 'async';
    // 小さい版（…pt.jpg）が読めなければ表紙（…ps.jpg）に、それも読めなければパッケージ画像（…pl.jpg）に戻す。それも読めなければ隠す
    img.addEventListener('error', function () {
      if (/pt\.jpg$/.test(img.src)) {
        img.src = img.src.replace(/pt\.jpg$/, 'ps.jpg');
      } else if (/ps\.jpg$/.test(img.src)) {
        img.src = img.src.replace(/ps\.jpg$/, 'pl.jpg');
        img.classList.remove('is-small');
      } else {
        img.style.visibility = 'hidden';
      }
    });
    img.src = tiny ? tinyImageUrl(src) : src;
    win.appendChild(img);
    return win;
  }

  function spinFrame(reel, list) {
    var row = pool[list[Math.floor(Math.random() * list.length)]];
    reel.textContent = '';
    var box = el('span', 'reel-card is-spinning');
    box.appendChild(windowWith(row.i));
    reel.appendChild(box);
  }

  function land(reel, row) {
    reel.textContent = '';
    var card = el('a', 'reel-card is-landed');
    card.href = '/item/' + row.c + '/';
    card.appendChild(windowWith(row.i));
    card.appendChild(el('span', 'reel-title ph-js', row.t));
    if (row.a) card.appendChild(el('span', 'reel-cast', row.a));
    reel.appendChild(card);
  }

  button.addEventListener('click', function () {
    if (busy) return;
    var list = eligible(pool, root.classList.contains('hide-vr'), root.classList.contains('only-solo'));
    var picks = pickMany(list, recent, Math.random, REELS);
    if (picks.length < REELS) return;
    picks.forEach(function (n) {
      recent.push(n);
    });
    while (recent.length > RECENT) recent.shift();
    if (reduce) {
      for (var r = 0; r < REELS; r++) land(reels[r], pool[picks[r]]);
      button.textContent = 'もう1回まわす';
      return;
    }
    busy = true;
    button.disabled = true;
    section.classList.add('is-spinning');
    var stopped = 0;
    var timers = [];
    for (var k = 0; k < REELS; k++) {
      (function (k) {
        timers[k] = setInterval(function () {
          spinFrame(reels[k], list);
        }, TICK_MS);
        setTimeout(function () {
          clearInterval(timers[k]);
          land(reels[k], pool[picks[k]]);
          stopped++;
          if (stopped === REELS) {
            busy = false;
            button.disabled = false;
            button.textContent = 'もう1回まわす';
            section.classList.remove('is-spinning');
          }
        }, STOP_MS[k]);
      })(k);
    }
  });
  }
})();
