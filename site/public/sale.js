// セールのページ・トップの「セール中」で、終わりの時刻をすぎたキャンペーンを隠す（ビルドは1日1回なので、終わったあとも次の更新まで残るため）。
// 印: data-sale-end="2026-10-05T09:59:59+09:00"（lib/sale.js の endIso）。隠すのは、見た目のクラス（sale-ended）を付けるだけ
(function () {
  'use strict';
  function ended(iso, now) {
    var t = Date.parse(String(iso || ''));
    return !isNaN(t) && t < now;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ended: ended };
    return;
  }
  if (typeof document === 'undefined') return;
  var now = Date.now();
  var marks = document.querySelectorAll('[data-sale-end]');
  for (var i = 0; i < marks.length; i++) {
    if (ended(marks[i].getAttribute('data-sale-end'), now)) marks[i].classList.add('sale-ended');
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
