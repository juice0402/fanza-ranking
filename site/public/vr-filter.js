// 「VR作品を隠す」「単体作品のみ表示」スイッチ。一覧のマスの目印（data-vr＝VR作品・data-solo＝単体作品）を見て、まとめて隠す。
// 状態は、この端末のこのブラウザの localStorage（キー hide-vr・only-solo）にだけ保存する（サーバーには何も送らない）。
// 隠す動き自体は CSS（html.hide-vr [data-vr]・html.only-solo の data-solo の無いマス を display: none）。ページを開いた瞬間にチラつかないよう、
// html に印を付ける処理は、<head> の中の小さなスクリプト（site/src/layouts/Base.astro）が先にやる。
// ここでは、スイッチの表示と、日付ごとのまとまり（.day）の本数・空の日付の隠し方、TOP3など（.rank-podium）の差し替え（隠れない先頭の3本・メダルの色と順位の数字）をやる。
// 「もっと見る」でたたむ一覧（[data-fold]。トップの予約受付中）も、絞り込みで隠れないマスを先頭から数えて、たたむ所を付け直す（運営者の「下のほうが重い」。2026-10-07）。
// JavaScript や localStorage が使えないときは、スイッチを出さない（作品はそのまま出る）。
(function () {
  var KEY = 'hide-vr';
  var CLASS = 'hide-vr';
  var SOLO_KEY = 'only-solo';
  var SOLO_CLASS = 'only-solo';

  // 本数のあとに付ける注記（どちらのスイッチが効いているか）。どちらも効いていなければ ''
  function filterNote(hideVr, onlySolo) {
    if (hideVr && onlySolo) return '（単体作品・VRを除く）';
    if (onlySolo) return '（単体作品のみ）';
    if (hideVr) return '（VRを除く）';
    return '';
  }

  // マスが隠れるか。vr: VR作品か / solo: 単体作品か
  function cellHidden(vr, solo, hideVr, onlySolo) {
    return Boolean((hideVr && vr) || (onlySolo && !solo));
  }

  // 日付ごとの本数の文字。絞り込んでいるときは、隠れていない本数にする（orig は最初に出ていた文字。「3本」「3本（全5本）」など）
  // shown: その日の一覧に出ている本数 / hidden: そのうち隠れる本数 / note: filterNote の注記
  function dayCountText(orig, shown, hidden, note) {
    if (!note || hidden <= 0) return orig;
    return shown - hidden + '本' + note;
  }

  // まとまりが、絞り込むと空になるか（全部が隠れるとき）
  function dayIsEmpty(shown, hidden) {
    return shown > 0 && hidden >= shown;
  }

  // TOP3などの出し方。flags[i] は、i番目（順位の順）の作品が隠れるか。show は、出す本数（3）。
  // 絞り込んでいないとき: 先頭の show 本。絞り込んでいるとき: 隠れない先頭の show 本（次の順位から差し替える）
  // shown: 出す作品の番号（順位の順） / visible: 出す本数
  function rankLayout(flags, hide, show) {
    var shown = [];
    for (var i = 0; i < flags.length && shown.length < show; i++) {
      if (!(hide && flags[i])) shown.push(i);
    }
    return { shown: shown, visible: shown.length };
  }

  // 「もっと見る」でたたむ一覧: 絞り込みで隠れないマスを先頭から数えて、n 本より後ろをたたむ（開いていれば、たたまない）。
  // hidden[i]: i番目のマスが絞り込みで隠れるか。off[i]: i番目をたたむか / rest: たたんだ本数（「あと○本」）
  function foldLayout(hidden, n, open) {
    var off = [];
    var seen = 0;
    var rest = 0;
    for (var i = 0; i < hidden.length; i++) {
      if (hidden[i]) {
        off.push(false);
        continue;
      }
      seen += 1;
      var fold = !open && n > 0 && seen > n;
      off.push(fold);
      if (fold) rest += 1;
    }
    return { off: off, rest: rest };
  }

  // 一部がたたまれている日付の本数の文字（「3本（全8本）」）。visible: 絞り込みで隠れない本数 / folded: そのうちたたんだ本数 / note: filterNote の注記
  function foldCountText(visible, folded, note) {
    return visible - folded + '本（全' + visible + '本）' + (note || '');
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { KEY: KEY, CLASS: CLASS, SOLO_KEY: SOLO_KEY, SOLO_CLASS: SOLO_CLASS, filterNote: filterNote, cellHidden: cellHidden, dayCountText: dayCountText, dayIsEmpty: dayIsEmpty, rankLayout: rankLayout, foldLayout: foldLayout, foldCountText: foldCountText }; // tests/test_search.mjs 用
    return;
  }
  if (typeof document === 'undefined') return;

  var root = document.documentElement;

  function readStored(key) {
    try {
      return window.localStorage.getItem(key) === '1';
    } catch (e) {
      return false;
    }
  }

  function writeStored(key, on) {
    try {
      if (on) window.localStorage.setItem(key, '1');
      else window.localStorage.removeItem(key);
    } catch (e) {}
  }

  function state() {
    return { hideVr: root.classList.contains(CLASS), onlySolo: root.classList.contains(SOLO_CLASS) };
  }

  function isHiddenCell(cell, s) {
    return cellHidden(cell.hasAttribute('data-vr'), cell.hasAttribute('data-solo'), s.hideVr, s.onlySolo);
  }

  function countHidden(cells, s) {
    var n = 0;
    for (var i = 0; i < cells.length; i++) if (isHiddenCell(cells[i], s)) n++;
    return n;
  }

  function updateButtons(s) {
    var defs = [['[data-vr-toggle]', s.hideVr], ['[data-solo-toggle]', s.onlySolo]];
    for (var d = 0; d < defs.length; d++) {
      var buttons = document.querySelectorAll(defs[d][0]);
      for (var i = 0; i < buttons.length; i++) {
        var b = buttons[i];
        var on = defs[d][1];
        var label = b.querySelector('.vr-toggle-label');
        b.hidden = false;
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
        if (label) label.textContent = b.getAttribute(on ? 'data-on' : 'data-off') || label.textContent;
      }
    }
  }

  // 「もっと見る」でたたむ一覧（[data-fold]）: たたむマスに fold-off、全部がたたまれた日付に fold-empty。ボタンの「あと○本」も付け直す
  function updateFolds(s) {
    var boxes = document.querySelectorAll('[data-fold]');
    for (var i = 0; i < boxes.length; i++) {
      var box = boxes[i];
      var cells = box.querySelectorAll('.shelf-cell');
      var flags = [];
      for (var j = 0; j < cells.length; j++) flags.push(isHiddenCell(cells[j], s));
      var layout = foldLayout(flags, parseInt(box.getAttribute('data-fold'), 10) || 0, box.classList.contains('is-open'));
      for (var k = 0; k < cells.length; k++) cells[k].classList.toggle('fold-off', layout.off[k]);
      var days = box.querySelectorAll('.day');
      for (var d = 0; d < days.length; d++) {
        var dayCells = days[d].querySelectorAll('.shelf-cell');
        var anyFolded = false;
        var anyShown = false;
        for (var c = 0; c < dayCells.length; c++) {
          if (dayCells[c].classList.contains('fold-off')) anyFolded = true;
          else if (!isHiddenCell(dayCells[c], s)) anyShown = true;
        }
        days[d].classList.toggle('fold-empty', anyFolded && !anyShown);
      }
      var more = box.querySelector('[data-fold-more]');
      if (more) {
        more.hidden = layout.rest === 0;
        var rest = more.querySelector('[data-fold-rest]');
        if (rest) rest.textContent = String(layout.rest);
      }
    }
  }

  function countFolded(cells) {
    var n = 0;
    for (var i = 0; i < cells.length; i++) if (cells[i].classList.contains('fold-off')) n++;
    return n;
  }

  function updateDays(s) {
    var note = filterNote(s.hideVr, s.onlySolo);
    var days = document.querySelectorAll('.day');
    for (var i = 0; i < days.length; i++) {
      var day = days[i];
      var cells = day.querySelectorAll('.shelf-cell');
      var hidden = note ? countHidden(cells, s) : 0;
      var folded = countFolded(cells);
      var counter = day.querySelector('.divider-count');
      if (counter) {
        if (!counter.hasAttribute('data-orig')) counter.setAttribute('data-orig', counter.textContent);
        counter.textContent = folded > 0 && !day.classList.contains('fold-empty') ? foldCountText(cells.length - hidden, folded, note) : dayCountText(counter.getAttribute('data-orig'), cells.length, hidden, note);
      }
      day.classList.toggle('vr-empty', Boolean(note) && dayIsEmpty(cells.length, hidden));
    }
  }

  // 作品ページの「同じ出演者・メーカーの作品」・週のまとめの「注目の作品」など（data-vr-group の付いたまとまり）:
  // 中の作品が全部隠れるなら、見出しごと隠す（見出しだけが残って、空に見えないように）
  function updateGroups(s) {
    var active = s.hideVr || s.onlySolo;
    var groups = document.querySelectorAll('[data-vr-group]');
    for (var i = 0; i < groups.length; i++) {
      var cells = groups[i].querySelectorAll('.shelf-cell');
      groups[i].classList.toggle('vr-empty', active && dayIsEmpty(cells.length, countHidden(cells, s)));
    }
  }

  // TOP3・今週のデビュー作（.rank-podium）: 絞り込むときは、隠れない先頭の3本に差し替え（順位の数字も1・2・3にふり直す）、
  // 絞り込まないときは、元の先頭3本に戻す。見えている本数（data-visible）と、メダルの色（data-place。見えている中で 1 金・2 銀・3 銅）も付け直す。
  // 全部が隠れるなら、見出しごと隠す（.rank-podium を囲む [data-rank-section]・#ranking）
  function updateRanking(s) {
    var active = s.hideVr || s.onlySolo;
    var note = filterNote(s.hideVr, s.onlySolo);
    var lists = document.querySelectorAll('.rank-podium');
    for (var i = 0; i < lists.length; i++) {
      var list = lists[i];
      var cells = list.querySelectorAll('.rank-cell');
      var flags = [];
      for (var j = 0; j < cells.length; j++) flags.push(isHiddenCell(cells[j], s));
      var show = parseInt(list.getAttribute('data-show'), 10) || 3;
      var layout = rankLayout(flags, active, show);
      list.setAttribute('data-visible', String(layout.visible));
      for (var k = 0; k < cells.length; k++) {
        var place = layout.shown.indexOf(k);
        cells[k].classList.toggle('rank-off', place < 0);
        if (place >= 0) cells[k].setAttribute('data-place', String(place + 1));
        else cells[k].removeAttribute('data-place');
        var badge = cells[k].querySelector('.rank-badge');
        if (badge && place >= 0) badge.textContent = (active ? place + 1 : cells[k].getAttribute('data-rank') || place + 1) + '位';
      }
      var section = list.closest ? list.closest('#ranking, [data-rank-section]') : null;
      if (section) {
        section.classList.toggle('vr-empty', layout.visible === 0);
        var vrNote = section.querySelector('.rank-vr-note');
        if (vrNote) {
          vrNote.hidden = !(active && flags.indexOf(true) >= 0);
          vrNote.textContent = '｜' + note.replace(/^（|）$/g, '');
        }
      }
    }
  }

  function apply(s) {
    root.classList.toggle(CLASS, s.hideVr);
    root.classList.toggle(SOLO_CLASS, s.onlySolo);
    updateButtons(s);
    updateFolds(s);
    updateDays(s);
    updateGroups(s);
    updateRanking(s);
  }

  function set(s) {
    writeStored(KEY, s.hideVr);
    writeStored(SOLO_KEY, s.onlySolo);
    apply(s);
    document.dispatchEvent(new Event('vrfilterchange')); // 検索ページ・運命の作品が、作り直すため
  }

  var now = state();
  apply({ hideVr: now.hideVr || readStored(KEY), onlySolo: now.onlySolo || readStored(SOLO_KEY) });
  document.addEventListener('click', function (event) {
    var target = event.target;
    if (!target || !target.closest) return;
    var s = state();
    if (target.closest('[data-vr-toggle]')) set({ hideVr: !s.hideVr, onlySolo: s.onlySolo });
    else if (target.closest('[data-solo-toggle]')) set({ hideVr: s.hideVr, onlySolo: !s.onlySolo });
    else if (target.closest('[data-fold-more]')) {
      // 「もっと見る」: たたんだ残りを出し、増えた分の先頭の作品へフォーカスを移す（ボタンが消えても、フォーカスがページの先頭に飛ばないように）
      var box = target.closest('[data-fold]');
      if (!box) return;
      var first = null;
      var cells = box.querySelectorAll('.shelf-cell.fold-off');
      for (var i = 0; i < cells.length && !first; i++) if (!isHiddenCell(cells[i], s)) first = cells[i];
      box.classList.add('is-open');
      apply(s);
      var link = first && first.querySelector('a');
      if (link) link.focus();
    }
  });
})();
