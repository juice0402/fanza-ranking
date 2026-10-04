// サンプル動画の枠（作品ページ）。FANZAの再生ページは 476x306 の固定サイズなので、
// 枠（.movie-box）の幅に合わせて、中のiframeを拡大・縮小して見せる（スマホでは縮小、広い画面では少し拡大）。
// 枠の高さは CSS の aspect-ratio で決まる。JavaScript が使えないときは、等倍（476px）のまま。
// （「押してから読み込む」形は、iPhone で再生まで2回押すことになったので、やめた。2026-10-04）
(function () {
  var WIDTH = 476; // FANZAの再生ページの幅（px）

  // 枠の幅 → 倍率。幅が分からない（0・数字でない）ときは等倍
  function scaleFor(boxWidth) {
    return typeof boxWidth === 'number' && isFinite(boxWidth) && boxWidth > 0 ? boxWidth / WIDTH : 1;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { scaleFor: scaleFor, WIDTH: WIDTH }; // tests/test_movie.mjs 用
    return;
  }
  if (typeof document === 'undefined') return;

  var boxes = document.querySelectorAll('.movie-box');
  if (!boxes.length) return;

  function fit(box) {
    box.style.setProperty('--movie-scale', String(scaleFor(box.clientWidth)));
  }

  Array.prototype.forEach.call(boxes, function (box) {
    fit(box);
    if (typeof ResizeObserver === 'function') {
      new ResizeObserver(function () {
        fit(box);
      }).observe(box);
    }
  });
  // ResizeObserver が無い古いブラウザだけ、画面の幅・向きが変わったときに合わせ直す
  if (typeof ResizeObserver !== 'function') {
    window.addEventListener('resize', function () {
      Array.prototype.forEach.call(boxes, fit);
    });
  }
})();
