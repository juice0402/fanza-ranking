// /robots.txt を、ビルド時に自動で作ります（URLは src/config.js の SITE_URL を使います）。
import { buildRobots } from '../lib/items.js';

export function GET() {
  return new Response(buildRobots(), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
