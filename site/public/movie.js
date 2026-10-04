// サンプル動画の枠（作品ページ）。
// ・最初は、パッケージ画像と「再生」ボタンだけ（FANZAの再生ページは重いので、押されてから読み込む）。押すと、その場に再生ページ（iframe）を入れる
// ・FANZAの再生ページは 476x306 の固定サイズなので、枠（.movie-box）の幅に合わせて、中のiframeを拡大・縮小して見せる（スマホでは縮小、広い画面では少し拡大）
// 枠の高さは CSS の aspect-ratio で決まる。JavaScript が使えないときは、<noscript> の再生ページが等倍（476px）で出る。
(function () {
  var WIDTH = 476; // FANZAの再生ページの幅（px）
  var HEIGHT = 306;

  // 枠の幅 → 倍率。幅が分からない（0・数字でない）ときは等倍
  function scaleFor(boxWidth) {
    return typeof boxWidth === 'number' && isFinite(boxWidth) && boxWidth > 0 ? boxWidth / WIDTH : 1;
  }

  // 再生ページのURLとして使ってよいか（FANZA(DMM) の https だけ）
  function safeMovieUrl(url) {
    if (typeof url !== 'string' || !/^https:\/\//.test(url) || /[\\\s]/.test(url)) return ''; // バックスラッシュ・空白入りは使わない（ホストを偽る形）
    var host = url.slice(8).split(/[/?#]/)[0].toLowerCase();
    if (host.indexOf('@') >= 0 || host.indexOf(':') >= 0) return '';
    return host === 'dmm.co.jp' || /\.dmm\.co\.jp$/.test(host) ? url : '';
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { scaleFor: scaleFor, safeMovieUrl: safeMovieUrl, WIDTH: WIDTH }; // tests/test_movie.mjs 用
    return;
  }
  if (typeof document === 'undefined') return;

  var boxes = document.querySelectorAll('.movie-box');
  if (!boxes.length) return;

  function fit(box) {
    box.style.setProperty('--movie-scale', String(scaleFor(box.clientWidth)));
  }

  function play(box, button) {
    var src = safeMovieUrl(button.getAttribute('data-movie-src'));
    if (!src) return;
    var frame = document.createElement('iframe');
    frame.className = 'movie-frame';
    frame.src = src;
    frame.width = String(WIDTH);
    frame.height = String(HEIGHT);
    frame.title = button.getAttribute('data-movie-title') || 'サンプル動画';
    frame.setAttribute('scrolling', 'no');
    frame.setAttribute('frameborder', '0');
    frame.setAttribute('allow', 'autoplay; fullscreen');
    frame.setAttribute('allowfullscreen', '');
    box.replaceChild(frame, button);
    fit(box);
    try {
      frame.focus();
    } catch (e) {}
  }

  Array.prototype.forEach.call(boxes, function (box) {
    fit(box);
    var button = box.querySelector('.movie-play');
    if (button) {
      button.addEventListener('click', function () {
        play(box, button);
      });
    }
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
