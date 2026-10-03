// 「VR作品を隠す」スイッチ。VR作品の目印（data-vr）が付いた一覧のマスを、まとめて隠す。
// 状態は、この端末のこのブラウザの localStorage（キー hide-vr）にだけ保存する（サーバーには何も送らない）。
// 隠す動き自体は CSS（html.hide-vr [data-vr] { display: none }）。ページを開いた瞬間にチラつかないよう、
// html に hide-vr を付ける処理は、<head> の中の小さなスクリプト（site/src/layouts/Base.astro）が先にやる。
// ここでは、スイッチの表示と、日付ごとのまとまり（.day）の本数・空の日付の隠し方をやる。
// JavaScript や localStorage が使えないときは、スイッチを出さない（VR作品はそのまま出る）。
(function () {
  var KEY = 'hide-vr';
  var CLASS = 'hide-vr';

  // 日付ごとの本数の文字。hide のとき、VR を除いた本数にする（orig は最初に出ていた文字。「3本」「3本（全5本）」など）
  // shown: その日の一覧に出ている本数 / vr: そのうち VR の本数
  function dayCountText(orig, shown, vr, hide) {
    if (!hide || vr <= 0) return orig;
    return shown - vr + '本（VRを除く）';
  }

  // 日付のまとまりが、VR を隠すと空になるか（全部が VR のとき）
  function dayIsEmpty(shown, vr, hide) {
    return Boolean(hide) && shown > 0 && vr >= shown;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { KEY: KEY, CLASS: CLASS, dayCountText: dayCountText, dayIsEmpty: dayIsEmpty }; // tests/test_search.mjs 用
    return;
  }
  if (typeof document === 'undefined') return;

  var root = document.documentElement;

  function readStored() {
    try {
      return window.localStorage.getItem(KEY) === '1';
    } catch (e) {
      return false;
    }
  }

  function writeStored(hide) {
    try {
      if (hide) window.localStorage.setItem(KEY, '1');
      else window.localStorage.removeItem(KEY);
    } catch (e) {}
  }

  function isHidden() {
    return root.classList.contains(CLASS);
  }

  function updateButtons(hide) {
    var buttons = document.querySelectorAll('[data-vr-toggle]');
    for (var i = 0; i < buttons.length; i++) {
      var b = buttons[i];
      var label = b.querySelector('.vr-toggle-label');
      b.hidden = false;
      b.setAttribute('aria-pressed', hide ? 'true' : 'false');
      if (label) label.textContent = b.getAttribute(hide ? 'data-on' : 'data-off') || label.textContent;
    }
  }

  function updateDays(hide) {
    var days = document.querySelectorAll('.day');
    for (var i = 0; i < days.length; i++) {
      var day = days[i];
      var shown = day.querySelectorAll('.shelf-cell').length;
      var vr = day.querySelectorAll('.shelf-cell[data-vr]').length;
      var counter = day.querySelector('.divider-count');
      if (counter) {
        if (!counter.hasAttribute('data-orig')) counter.setAttribute('data-orig', counter.textContent);
        counter.textContent = dayCountText(counter.getAttribute('data-orig'), shown, vr, hide);
      }
      day.classList.toggle('vr-empty', dayIsEmpty(shown, vr, hide));
    }
  }

  function apply(hide) {
    root.classList.toggle(CLASS, hide);
    updateButtons(hide);
    updateDays(hide);
  }

  function set(hide) {
    writeStored(hide);
    apply(hide);
    document.dispatchEvent(new Event('vrfilterchange')); // 検索ページが、結果を作り直すため
  }

  apply(isHidden() || readStored());
  document.addEventListener('click', function (event) {
    var target = event.target;
    var button = target && target.closest ? target.closest('[data-vr-toggle]') : null;
    if (!button) return;
    set(!isHidden());
  });
})();
