// メーカーごとの発売日カレンダー（/calendar/maker/<slug>.ics）。メーカーのページがあるメーカー（作品が2本以上）のうち、新作・予約が載っているメーカーだけ（lib/plan.js の hasCalendar）。予定のリンク先は作品ページなので、作品ページがある作品だけを入れる。
import { calendarMakerGroups, paged, today } from '../../../lib/data.js';
import { SITE_NAME } from '../../../lib/items.js';
import { buildIcs } from '../../../lib/calendar.js';

export function getStaticPaths() {
  return calendarMakerGroups.map((group) => ({ params: { slug: group.slug }, props: { group } }));
}

export function GET({ props }) {
  const { group } = props;
  return new Response(buildIcs({ calName: `${group.name}の新作｜${SITE_NAME}`, items: group.items.filter((i) => paged.has(i.cid)), today, subject: group.name }), {
    headers: { 'Content-Type': 'text/calendar; charset=utf-8' },
  });
}
