// メーカーごとの発売日カレンダー（/calendar/maker/<slug>.ics）。メーカーのページと同じ「作品が2本以上」のメーカーだけ。
import { makerGroups, today } from '../../../lib/data.js';
import { SITE_NAME } from '../../../lib/items.js';
import { buildIcs } from '../../../lib/calendar.js';

export function getStaticPaths() {
  return makerGroups.map((group) => ({ params: { slug: group.slug }, props: { group } }));
}

export function GET({ props }) {
  const { group } = props;
  return new Response(buildIcs({ calName: `${group.name}の新作｜${SITE_NAME}`, items: group.items, today, subject: group.name }), {
    headers: { 'Content-Type': 'text/calendar; charset=utf-8' },
  });
}
