// すべての発売予定のカレンダー（/calendar/upcoming.ics）。カレンダーアプリで購読すると、発売日が自動で入ります。
// 予定のリンク先は作品ページなので、作品ページがある作品だけを入れる。
import { all, paged, today } from '../../lib/data.js';
import { SITE_NAME } from '../../lib/items.js';
import { buildIcs } from '../../lib/calendar.js';

export function GET() {
  return new Response(buildIcs({ calName: `${SITE_NAME}｜発売日`, items: all.filter((i) => paged.has(i.cid)), today }), {
    headers: { 'Content-Type': 'text/calendar; charset=utf-8' },
  });
}
