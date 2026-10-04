// 画像の拡大表示（作品ページ用）。
// 小さく並んだサンプル画像と、その下のパッケージ写真（動画がある作品だけ。どちらも a.sample-link。ページの上から下の順に送る）をタップすると、画面いっぱいに拡大して表示する。
// 前後ボタン・キーボードの ← →・横スワイプで送れる。背景や「閉じる」・Escで閉じる。
// JavaScript が使えない／<dialog> に対応していないときは、リンクのまま（画像が別タブで開く）。
(function () {
  var SWIPE_MIN = 50; // これ以上横に動いたらスワイプとみなす（px）

  // index から delta だけ送った位置（端まで来たら反対側へ回る）
  function step(index, delta, count) {
    if (count <= 0) return 0;
    return (((index + delta) % count) + count) % count;
  }

  // 拡大表示の画像の説明（alt）。リンクに data-label があればそれ（パッケージ画像など）、なければ「サンプル画像 N」
  function labelOf(label, index) {
    return label ? String(label) : 'サンプル画像 ' + (index + 1);
  }

  // スワイプの向き。左へ動かしたら次(+1)、右なら前(-1)。縦の動きのほうが大きいとき（スクロール）は 0
  function swipeDelta(dx, dy) {
    if (Math.abs(dx) < SWIPE_MIN || Math.abs(dx) < Math.abs(dy) * 1.2) return 0;
    return dx < 0 ? 1 : -1;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { step: step, swipeDelta: swipeDelta, labelOf: labelOf }; // tests/test_lightbox.mjs 用
    return;
  }
  if (typeof document === 'undefined') return;

  var links = document.querySelectorAll('a.sample-link');
  var dialog = document.getElementById('lightbox');
  if (!links.length || !dialog || typeof dialog.showModal !== 'function') return;

  var img = dialog.querySelector('.lightbox-img');
  var counter = dialog.querySelector('.lightbox-count');
  var sources = Array.prototype.map.call(links, function (a) {
    return a.getAttribute('href');
  });
  var labels = Array.prototype.map.call(links, function (a, i) {
    return labelOf(a.getAttribute('data-label'), i);
  });
  var current = 0;
  var opener = null;

  function show(index) {
    current = step(index, 0, sources.length);
    img.src = sources[current];
    img.alt = labels[current];
    counter.textContent = current + 1 + ' / ' + sources.length;
    // 前後の画像を先に読み込んでおく（送ったときに待たないように）
    [step(current, 1, sources.length), step(current, -1, sources.length)].forEach(function (i) {
      new Image().src = sources[i];
    });
  }

  function move(delta) {
    show(step(current, delta, sources.length));
  }

  Array.prototype.forEach.call(links, function (a, i) {
    a.addEventListener('click', function (event) {
      event.preventDefault();
      opener = a;
      show(i);
      document.documentElement.classList.add('lightbox-open');
      dialog.showModal();
      // showModal は、最初のボタン（前へ）にフォーカスを移す。すると iPad などで、そのボタンに黄色いフォーカスの輪が付いて見える。
      // そこで、フォーカスは枠そのものに置く（← → や Esc は、そのまま効く。Tab を押せば、ボタンに移れて、輪も出る）
      dialog.focus({ preventScroll: true });
    });
  });

  dialog.addEventListener('close', function () {
    document.documentElement.classList.remove('lightbox-open');
    if (opener) opener.focus();
  });

  dialog.addEventListener('click', function (event) {
    var button = event.target.closest ? event.target.closest('[data-lightbox]') : null;
    var action = button ? button.getAttribute('data-lightbox') : '';
    if (action === 'prev') move(-1);
    else if (action === 'next') move(1);
    else if (action === 'close' || event.target.classList.contains('lightbox-stage') || event.target === dialog) dialog.close();
  });

  dialog.addEventListener('keydown', function (event) {
    if (event.key === 'ArrowLeft') move(-1);
    else if (event.key === 'ArrowRight') move(1);
  });

  var start = null;
  dialog.addEventListener('touchstart', function (event) {
    start = event.touches.length === 1 ? { x: event.touches[0].clientX, y: event.touches[0].clientY } : null; // 2本指（拡大）は対象外
  }, { passive: true });
  dialog.addEventListener('touchend', function (event) {
    if (!start || !event.changedTouches.length) return;
    var delta = swipeDelta(event.changedTouches[0].clientX - start.x, event.changedTouches[0].clientY - start.y);
    start = null;
    if (delta) move(delta);
  }, { passive: true });
})();
