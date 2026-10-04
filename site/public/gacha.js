// 「運命の1本」（トップ）: ボタンを押すと、人気の作品（ひとことコメントのある作品）から1本をえらんで見せる。
// 候補はページの中の小さなデータ（#gacha-data。site/src/lib/gacha.js が作る）。「VR作品を隠す」を選んでいるときは、VR作品を候補から外す。
// 直前に出た作品は、しばらく出さない。動きを減らす設定の人には、表紙が入れかわる演出をしない。
// JavaScript が使えないときは、欄ごと出さない（ボタンが動かないため）。DOM は textContent で作る
(function () {
  var RECENT = 6; // 直前に出たこの本数は、続けて出さない
  var SPINS = 9; // 決まるまでに入れかわる表紙の数
  var SPIN_MS = 70;

  // 候補の番号（0〜count-1）から1つ。recent（直前に出た番号）は、ほかに候補があるあいだは選ばない。rand は 0以上1未満
  function pick(candidates, recent, rand) {
    if (!candidates.length) return -1;
    var fresh = candidates.filter(function (n) {
      return recent.indexOf(n) < 0;
    });
    var from = fresh.length ? fresh : candidates;
    return from[Math.min(from.length - 1, Math.floor(rand * from.length))];
  }

  // 候補にする番号（VR作品を隠すときは、VRでない作品だけ）
  function eligible(pool, hideVr) {
    var out = [];
    for (var i = 0; i < pool.length; i++) if (!(hideVr && pool[i].v === 1)) out.push(i);
    return out;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { pick: pick, eligible: eligible, RECENT: RECENT }; // tests/test_gacha.mjs 用
    return;
  }
  if (typeof document === 'undefined') return;

  var section = document.getElementById('gacha');
  var data = document.getElementById('gacha-data');
  if (!section || !data) return;
  var pool = [];
  try {
    pool = JSON.parse(data.textContent || '[]');
  } catch (e) {
    return;
  }
  pool = pool.filter(function (row) {
    return row && typeof row.c === 'string' && /^[A-Za-z0-9_-]+$/.test(row.c) && typeof row.t === 'string' && typeof row.i === 'string' && /^https:\/\/[^/]*dmm\.co\.jp\//.test(row.i);
  });
  if (!pool.length) return;
  var stage = section.querySelector('.gacha-stage');
  var button = section.querySelector('[data-gacha-draw]');
  if (!stage || !button) return;
  section.hidden = false;

  var recent = [];
  var busy = false;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  function cover(src) {
    var box = el('span', 'gacha-cover');
    var img = el('img', 'item-img');
    img.alt = '';
    img.decoding = 'async';
    img.addEventListener('error', function () {
      img.style.visibility = 'hidden';
    });
    img.src = src;
    box.appendChild(img);
    return box;
  }

  function show(row) {
    var card = el('a', 'gacha-card');
    card.href = '/item/' + row.c + '/';
    card.appendChild(cover(row.i));
    var body = el('span', 'gacha-body');
    body.appendChild(el('span', 'gacha-title ph-js', row.t));
    if (row.a) body.appendChild(el('span', 'gacha-cast', row.a));
    if (row.x) body.appendChild(el('span', 'gacha-comment ph-js', row.x));
    body.appendChild(el('span', 'gacha-go', '作品ページを見る'));
    card.appendChild(body);
    stage.textContent = '';
    stage.appendChild(card);
    stage.classList.add('is-open');
  }

  function spin(list, left, done) {
    if (left <= 0) return done();
    var row = pool[list[Math.floor(Math.random() * list.length)]];
    stage.textContent = '';
    var shuffle = el('span', 'gacha-shuffle');
    shuffle.appendChild(cover(row.i));
    stage.appendChild(shuffle);
    setTimeout(function () {
      spin(list, left - 1, done);
    }, SPIN_MS);
  }

  button.addEventListener('click', function () {
    if (busy) return;
    var list = eligible(pool, document.documentElement.classList.contains('hide-vr'));
    var n = pick(list, recent, Math.random());
    if (n < 0) return;
    recent.push(n);
    if (recent.length > RECENT) recent.shift();
    busy = true;
    button.disabled = true;
    var finish = function () {
      show(pool[n]);
      busy = false;
      button.disabled = false;
      button.textContent = 'もう1回ひく';
    };
    if (reduce) finish();
    else spin(list, SPINS, finish);
  });
})();
