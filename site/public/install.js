// 「ホーム画面に追加」（運営者の希望「リピーターをつけたい」。2026-10-06）。フッターのいちばん下の小さなボタン。
// ・Android・パソコンの Chrome など: ブラウザが追加できると知らせてきたとき（beforeinstallprompt）だけボタンを出し、押すと追加の画面を開く
// ・iPhone・iPad の Safari: 追加の画面を開く仕組みが無いので、押すと、やり方（共有ボタン →「ホーム画面に追加」）を1行出す
// ・もうホーム画面から開いているとき・どちらでもないときは、何も出さない
(function () {
  'use strict';
  if (typeof document === 'undefined') return;
  var btn = document.getElementById('install-btn');
  var hint = document.getElementById('install-hint');
  if (!btn) return;
  var prompted = null;
  var standalone = (window.matchMedia && window.matchMedia('(display-mode: standalone), (display-mode: minimal-ui)').matches) || window.navigator.standalone === true;
  if (standalone) return;
  var ua = window.navigator.userAgent || '';
  var ios = /iP(hone|ad|od)/.test(ua) || (window.navigator.platform === 'MacIntel' && window.navigator.maxTouchPoints > 1);
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    prompted = e;
    btn.hidden = false;
  });
  if (ios && hint) btn.hidden = false;
  btn.addEventListener('click', function () {
    if (prompted) {
      prompted.prompt();
      prompted = null;
      btn.hidden = true;
    } else if (hint) {
      hint.hidden = !hint.hidden;
      btn.setAttribute('aria-expanded', hint.hidden ? 'false' : 'true');
    }
  });
})();
