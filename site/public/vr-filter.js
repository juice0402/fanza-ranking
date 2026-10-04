// 「VR作品を隠す」スイッチ。VR作品の目印（data-vr）が付いた一覧のマスを、まとめて隠す。
// 状態は、この端末のこのブラウザの localStorage（キー hide-vr）にだけ保存する（サーバーには何も送らない）。
// 隠す動き自体は CSS（html.hide-vr [data-vr] { display: none }）。ページを開いた瞬間にチラつかないよう、
// html に hide-vr を付ける処理は、<head> の中の小さなスクリプト（site/src/layouts/Base.astro）が先にやる。
// ここでは、スイッチの表示と、日付ごとのまとまり（.day）の本数・空の日付の隠し方、売れ筋TOP3の並べ直し（残った本数でちょうど埋まるように）をやる。
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

  // 売れ筋TOP3の並べ方。flags[i] は、i番目の作品がVRか。hide のとき、VRの作品は見えない。
  // visible: 見えている本数 / hero: 先頭で大きく出す作品の番号（3本以上か1本のときだけ。2本のときは -1。見えるものが無いときも -1）
  // site/src/lib/items.js の rankHasHero と同じ決め方（tests/test_search.mjs で突き合わせている）
  function rankLayout(flags, hide) {
    var shown = [];
    for (var i = 0; i < flags.length; i++) {
      if (!(hide && flags[i])) shown.push(i);
    }
    var n = shown.length;
    return { visible: n, hero: n === 1 || n >= 3 ? shown[0] : -1 };
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { KEY: KEY, CLASS: CLASS, dayCountText: dayCountText, dayIsEmpty: dayIsEmpty, rankLayout: rankLayout }; // tests/test_search.mjs 用
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

  // 売れ筋TOP3: 見えている本数に合わせて、並べ方の印（data-visible・.is-hero）を付け直す。全部がVRなら、売れ筋の見出しごと隠す
  function updateRanking(hide) {
    var lists = document.querySelectorAll('.rank-podium');
    for (var i = 0; i < lists.length; i++) {
      var list = lists[i];
      var cells = list.querySelectorAll('.rank-cell');
      var flags = [];
      for (var j = 0; j < cells.length; j++) flags.push(cells[j].hasAttribute('data-vr'));
      var layout = rankLayout(flags, hide);
      list.setAttribute('data-visible', String(layout.visible));
      for (var k = 0; k < cells.length; k++) cells[k].classList.toggle('is-hero', k === layout.hero);
      var section = list.closest ? list.closest('#ranking') : null;
      if (section) section.classList.toggle('vr-empty', layout.visible === 0);
      var jumps = document.querySelectorAll('a[href="#ranking"]');
      for (var m = 0; m < jumps.length; m++) jumps[m].hidden = layout.visible === 0;
    }
  }

  function apply(hide) {
    root.classList.toggle(CLASS, hide);
    updateButtons(hide);
    updateDays(hide);
    updateRanking(hide);
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
