// 見つからないページ（404）から、作品ページの新しい住所へ送る（2026-11-10。案A）。
// 作品ページは、コメントのある作品が /item/<作品ID>/（売り場は /doujin/item/<作品ID>/ など）、コメントの無い作品が /w/<作品ID>/（/doujin/w/<作品ID>/）。
// コメントが付くと /w/ から /item/ に移るので、古い住所（ブックマーク・お気に入り・前に読んだ索引）から開いた人を、もう一方の住所へ1回だけ送る。
// 送った先にも無ければ（掲載が終わった作品）、#nf の印があるので、もう送らない（行ったり来たりしない）。検索エンジンには 404 のまま
(function (root) {
  var ITEM = /^\/(?:([a-z]{2,10})\/)?(item|w)\/([A-Za-z0-9_-]+)\/?$/;
  function lostForward(pathname, hash) {
    if (hash === '#nf') return '';
    var m = ITEM.exec(String(pathname || ''));
    if (!m || m[1] === 'item' || m[1] === 'w') return '';
    return '/' + (m[1] ? m[1] + '/' : '') + (m[2] === 'item' ? 'w' : 'item') + '/' + m[3] + '/#nf';
  }
  root.lostForward = lostForward;
  if (typeof location !== 'undefined' && location && typeof location.replace === 'function') {
    var to = lostForward(location.pathname, location.hash);
    if (to) location.replace(to);
  }
})(this);
