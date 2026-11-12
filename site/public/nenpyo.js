// 女優の年表の一覧（/actress/nenpyo/）のしぼりこみと並べかえ（2026-11-12 #255）。
// 行ごとの値はページの data 属性（site/src/lib/history.js の nenpyoFilters）。しぼり方・並べ方は同じファイルの nenpyoPick と同じ。
// 条件は URL に入れない（住所をふやさない）。サイトには何も送らない。JavaScript が無いときは、ページの50音の一覧がそのまま見える。
(function () {
  var root = document.getElementById('nenpyo');
  var form = root && root.querySelector('.np-form');
  if (!form) return;
  var count = document.getElementById('np-count');
  var note = document.getElementById('np-filter-note');
  var flat = document.getElementById('np-flat');
  var jump = root.querySelector('.nenpyo-jump');
  var blocks = [].slice.call(root.querySelectorAll('.kana-block'));
  var rows = [].slice.call(root.querySelectorAll('.kana-block li')).map(function (li) {
    return {
      li: li,
      home: li.parentNode,
      y: li.getAttribute('data-y'),
      m: Number(li.getAttribute('data-m')),
      a: Number(li.getAttribute('data-a')),
      t: Number(li.getAttribute('data-t')),
      f: Number(li.getAttribute('data-f')),
      o: Number(li.getAttribute('data-o')),
    };
  });
  var moved = false; // 行を np-flat に移しているか

  function value(name) {
    var el = form.elements[name];
    return el ? (el.type === 'checkbox' ? el.checked : el.value) : '';
  }

  function apply() {
    var year = value('year');
    var maker = value('maker');
    var active = value('active');
    var sort = value('sort') || 'kana';
    var hit = [];
    rows.forEach(function (r) {
      var ok = (!year || r.y === year) && (maker === '' || r.m === Number(maker)) && (!active || r.a === 1);
      r.li.hidden = !ok;
      if (ok) hit.push(r);
    });
    if (sort === 'kana') {
      if (moved) {
        rows.forEach(function (r) {
          r.home.appendChild(r.li); // rows は50音の順なので、元の行の中に元の順でもどる
        });
        moved = false;
      }
      flat.hidden = true;
      blocks.forEach(function (b) {
        b.hidden = !b.querySelector('li:not([hidden])');
      });
      [].forEach.call(jump.querySelectorAll('a'), function (a) {
        var block = document.getElementById(a.getAttribute('data-row'));
        a.hidden = !block || block.parentNode.hidden;
      });
      jump.hidden = hit.length === 0;
    } else {
      hit.sort(sort === 'first' ? function (a, b) { return b.f - a.f || a.o - b.o; } : function (a, b) { return b.t - a.t || a.o - b.o; });
      hit.forEach(function (r) {
        flat.appendChild(r.li);
      });
      moved = true;
      blocks.forEach(function (b) {
        b.hidden = true;
      });
      jump.hidden = true;
      flat.hidden = hit.length === 0;
    }
    count.textContent = hit.length.toLocaleString('ja-JP') + '人';
    var n = (year ? 1 : 0) + (maker !== '' ? 1 : 0) + (active ? 1 : 0);
    note.textContent = n > 0 ? '（' + n + 'つ）' : '';
  }

  form.addEventListener('change', apply);
  form.addEventListener('submit', function (e) {
    e.preventDefault();
  });
  form.addEventListener('reset', function () {
    setTimeout(apply, 0);
  });
  // 戻るボタンで来たとき、ブラウザが条件を残していることがある
  window.addEventListener('pageshow', apply);
  apply();
})();
