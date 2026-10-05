// public/ のスクリプト（/vr-filter.js など）の URL に、中身から作った印（?v=…）を付ける（画面に依存しない。tests/test_items.mjs）。
// 中身が変わると URL も変わるので、ブラウザに長く置いておける（_headers で /*.js を1年。毎回「新しくなっていないか」を確かめに行かなくなり、
// 2ページ目からの表示が速くなる。運営者の「読み込みのストレスをフリーに」。2026-10-05）
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';

const cache = new Map();

/** "/vr-filter.js" → "/vr-filter.js?v=1a2b3c4d"（ファイルが見つからなければ、そのまま） */
export function assetUrl(publicPath, roots = [path.join(process.cwd(), 'public'), path.join(process.cwd(), 'site', 'public')]) {
  const key = `${publicPath}\n${roots.join('\n')}`;
  if (cache.has(key)) return cache.get(key);
  let url = publicPath;
  for (const root of roots) {
    const file = path.join(root, publicPath);
    if (fs.existsSync(file)) {
      url = `${publicPath}?v=${createHash('sha1').update(fs.readFileSync(file)).digest('hex').slice(0, 8)}`;
      break;
    }
  }
  cache.set(key, url);
  return url;
}
