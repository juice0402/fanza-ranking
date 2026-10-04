// セールのページ・トップの「セール中の特集」で、終わりの時刻をすぎたキャンペーンを隠す（ビルドは1日1回なので、終わったあとも次の更新まで残るため）。
// 印: data-sale-end="2026-10-05T09:59:59+09:00"（lib/sale.js の endIso）。隠すのは、見た目のクラス（sale-ended）を付けるだけ。
// トップの特集のカード（data-sale-show="4" の一覧）は、終わっていないものを先頭から4つだけ見せる（終わった特集の分は、次の特集が繰り上がる。
// ふだん隠してある5つ目からのカードには sale-more が付いている）
(function () {
  'use strict';
  function ended(iso, now) {
    var t = Date.parse(String(iso || ''));
    return !isNaN(t) && t < now;
  }
  // 終わったかどうかの並び → 見せるかどうかの並び（終わっていないものを、先頭から n 個まで）
  function shownSlots(endedFlags, n) {
    var out = [];
    var left = n;
    for (var i = 0; i < endedFlags.length; i++) {
      var show = !endedFlags[i] && left > 0;
      if (show) left--;
      out.push(show);
    }
    return out;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ended: ended, shownSlots: shownSlots };
    return;
  }
  if (typeof document === 'undefined') return;
  var now = Date.now();
  var marks = document.querySelectorAll('[data-sale-end]');
  for (var i = 0; i < marks.length; i++) {
    if (ended(marks[i].getAttribute('data-sale-end'), now)) marks[i].classList.add('sale-ended');
  }
  // 見せる数の決まった一覧（トップの特集のカード）: 終わっていないものを先頭から n 個
  var lists = document.querySelectorAll('[data-sale-show]');
  for (var l = 0; l < lists.length; l++) {
    var n = parseInt(lists[l].getAttribute('data-sale-show'), 10) || 0;
    var rows = lists[l].querySelectorAll('[data-sale-end]');
    var flags = [];
    for (var r = 0; r < rows.length; r++) flags.push(rows[r].classList.contains('sale-ended'));
    var show = shownSlots(flags, n);
    for (var s = 0; s < rows.length; s++) {
      if (!flags[s]) rows[s].classList.toggle('sale-more', !show[s]);
    }
  }
  // まとまり（キャンペーン・トップの欄）の中が全部終わっていたら、まとまりごと隠す
  var groups = document.querySelectorAll('[data-sale-group]');
  for (var j = 0; j < groups.length; j++) {
    var cells = groups[j].querySelectorAll('[data-sale-end]');
    var left = 0;
    for (var k = 0; k < cells.length; k++) if (!cells[k].classList.contains('sale-ended')) left++;
    if (cells.length && !left) groups[j].classList.add('sale-ended');
  }
})();
