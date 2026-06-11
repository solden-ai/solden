// DEV-ONLY visual harness for RecordsPage — sample-shaped records covering
// the state/pill/blocker/due variants so the table shows its full range.
import { h, render } from 'preact';
import { html } from '../src/utils/htm.js';
import RecordsPage from '../src/routes/pages/RecordsPage.js';
import '../src/styles/shell.css';
import '../src/styles/components.css';
import '../src/styles/pages.css';
import '../src/styles/records.css';

const now = Date.now();
const day = 86400000;
const mk = (i, over = {}) => ({
  id: `AP-${1000 + i}`,
  vendor_name: ['Northwind Traders', 'Acme Coffee Supplies', 'Cisco Systems', 'AWS Cloud Services', 'Café Paris', 'Booking Holdings BV'][i % 6],
  invoice_number: `INV-${7000 + i}`,
  amount: [12400, 240, 4500, 1240.5, 320, 78000][i % 6],
  currency: i % 5 === 4 ? 'EUR' : 'USD',
  state: ['needs_approval', 'posted_to_erp', 'needs_info', 'validated', 'closed', 'needs_second_approval'][i % 6],
  owner_email: ['maya@soldenai.com', '', 'ben@soldenai.com', 'jane.finance@acme.com', '', 'mo@soldenai.com'][i % 6],
  next_action: ['approve_or_reject', '', 'await_vendor_response', 'review_fields', '', 'second_approval'][i % 6],
  blockers: i % 3 === 0 ? [{ type: 'po_required_missing' }] : [],
  due_date: new Date(now + (i % 4 === 0 ? -3 : i % 4) * day).toISOString(),
  erp_status: ['connected', 'posted', 'connected', 'failed', 'posted', 'connected'][i % 6],
  queue_age_minutes: 60 * (i + 3),
  created_at: new Date(now - (i + 2) * day).toISOString(),
  updated_at: new Date(now - i * day).toISOString(),
});

const items = Array.from({ length: 14 }, (_, i) => mk(i));

const api = async (path) => {
  const route = String(path);
  if (route.startsWith('/api/workspace/records')) {
    return { items, total_count: items.length, filtered_count: items.length };
  }
  if (route.startsWith('/api/ap/items/metrics')) return {};
  return {};
};

function Harness() {
  return html`
    <div class="cl-app" style="grid-template-columns: 0 1fr;">
      <div></div>
      <div class="cl-app-main">
        <main class="cl-app-content">
          <${RecordsPage}
            api=${api}
            bootstrap=${{ organization: { name: 'Solden' } }}
            orgId="org-dev"
            userEmail="mo@soldenai.com"
            toast=${() => {}}
            navigate=${() => {}}
          />
        </main>
      </div>
    </div>
  `;
}

render(h(Harness, {}), document.getElementById('app'));
