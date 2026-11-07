// セールのカレンダー（/calendar/sale.ics。issue #239）。いま開いているセールと、これから始まるセールの始まり〜終わりを、カレンダーアプリで購読できる（lib/calendar.js）
import { saleCalendarSources, today } from '../../lib/data.js';
import { SITE_NAME } from '../../lib/items.js';
import { buildSaleIcs, jstNow, saleEvents } from '../../lib/calendar.js';

export function GET() {
  return new Response(buildSaleIcs({ calName: `${SITE_NAME}｜セール`, events: saleEvents(saleCalendarSources, jstNow()), today }), {
    headers: { 'Content-Type': 'text/calendar; charset=utf-8' },
  });
}
