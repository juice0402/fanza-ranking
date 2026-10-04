// サンプル動画の枠（作品ページ）。FANZAの再生ページは 476x306 の固定サイズなので、
// 枠（.movie-box）の幅に合わせて、中のiframeを拡大・縮小して見せる（スマホでは縮小、広い画面では少し拡大）。
// 枠の高さは CSS の aspect-ratio で決まる。JavaScript が使えないときは、等倍（476px）のまま。
//
// 画質のためしがけ: URLに ?msize=560_360（ほかに 644_414 / 720_480 / 476_306）を付けると、FANZAの再生ページの大きさを変えて開く。
// FANZAのプレーヤーの最初の画質は、プレーヤーの大きさ（URLの size=）で変わるかもしれないため、運営者が iPad で見比べるための道具
// （どの大きさが「中画質（432p）」から始まるかが分かったら、SampleMovie.astro の大きさを、それに決める）。許す値は下の SIZES だけ。
(function () {
  var WIDTH = 476; // FANZAの再生ページの、ふだんの幅（px）
  var SIZES = { '476_306': [476, 306], '560_360': [560, 360], '644_414': [644, 414], '720_480': [720, 480] }; // FANZAの再生ページの大きさ（幅, 高さ）

  // 枠の幅 → 倍率（frameWidth は、再生ページの幅。省くと 476）。幅が分からない（0・数字でない）ときは等倍
  function scaleFor(boxWidth, frameWidth) {
    var base = typeof frameWidth === 'number' && frameWidth > 0 ? frameWidth : WIDTH;
    return typeof boxWidth === 'number' && isFinite(boxWidth) && boxWidth > 0 ? boxWidth / base : 1;
  }

  // URLの ?msize=… から、使ってよい再生ページの大きさ（'560_360' など）を取り出す。許していない値・無いときは ''
  function sizeFromQuery(search) {
    var m = /[?&]msize=([0-9]+_[0-9]+)(?:&|$)/.exec(String(search || ''));
    return m && Object.prototype.hasOwnProperty.call(SIZES, m[1]) ? m[1] : '';
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { scaleFor: scaleFor, sizeFromQuery: sizeFromQuery, SIZES: SIZES, WIDTH: WIDTH }; // tests/test_movie.mjs 用
    return;
  }
  if (typeof document === 'undefined') return;

  var boxes = document.querySelectorAll('.movie-box');
  if (!boxes.length) return;

  var testSize = sizeFromQuery(window.location.search);
  var dim = testSize ? SIZES[testSize] : null;

  function fit(box) {
    box.style.setProperty('--movie-scale', String(scaleFor(box.clientWidth, dim ? dim[0] : WIDTH)));
  }

  // ためしがけ: 再生ページの大きさを変えて開き直す（枠の縦横比・iframeの大きさも合わせる）
  if (dim) {
    Array.prototype.forEach.call(boxes, function (box) {
      var frame = box.querySelector('iframe');
      if (!frame) return;
      frame.setAttribute('src', String(frame.getAttribute('src')).replace(/size=[0-9]+_[0-9]+/, 'size=' + testSize));
      frame.setAttribute('width', String(dim[0]));
      frame.setAttribute('height', String(dim[1]));
      frame.style.width = dim[0] + 'px';
      frame.style.height = dim[1] + 'px';
      box.style.aspectRatio = dim[0] + ' / ' + dim[1];
      var note = box.parentNode && box.parentNode.querySelector('.movie-note');
      if (note) note.insertBefore(document.createTextNode('（ためし表示: 再生ページの大きさ ' + dim[0] + '×' + dim[1] + '）'), note.firstChild); // リンクを壊さないよう、文字を前に足す
    });
  }

  Array.prototype.forEach.call(boxes, function (box) {
    fit(box);
    if (typeof ResizeObserver === 'function') {
      new ResizeObserver(function () {
        fit(box);
      }).observe(box);
    }
  });
  // ResizeObserver が無い古いブラウザ向け（画面の向きを変えたとき・幅を変えたとき）
  window.addEventListener('resize', function () {
    Array.prototype.forEach.call(boxes, fit);
  });
  window.addEventListener('orientationchange', function () {
    Array.prototype.forEach.call(boxes, fit);
  });
})();
