import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, render, screen, waitFor } from '@testing-library/preact';
import { api } from '../../api/client.js';
import { BootstrapProvider } from '../../shell/BootstrapContext.js';
import { HomePage } from './HomePage.js';

const navigateMock = vi.hoisted(() => vi.fn());

vi.mock('wouter-preact', () => ({
  useLocation: () => ['/', navigateMock],
}));

vi.mock('../../api/client.js', () => ({
  api: vi.fn(),
}));

vi.mock('../../lib/faviconBadge.js', () => ({
  setFaviconBadge: vi.fn(),
}));

function renderHome() {
  return render(h(BootstrapProvider, {}, h(HomePage, {})));
}

describe('HomePage', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders open work as operational context instead of raw blocker codes', async () => {
    api.mockImplementation(async (path) => {
      const url = String(path || '');
      if (url === '/api/workspace/bootstrap') {
        return {
          organization: { id: 'org-test', name: 'Acme Finance' },
          current_user: {
            email: 'maya.rivera@acme.com',
            name: 'Maya Rivera',
            organization_id: 'org-test',
          },
          dashboard: { in_flight: 3, pending_approval: 1, processed_this_week: 9 },
          integrations: [],
          capabilities: ['view_procurement', 'view_workflow_builder'],
        };
      }
      if (url.startsWith('/api/workspace/records')) {
        return {
          total: 2,
          items: [
            {
              id: 'AP-1',
              vendor_name: 'Northstar Systems',
              invoice_number: 'INV-100',
              amount: 361500,
              currency: 'USD',
              state: 'needs_info',
              owner_email: 'maya.rivera@acme.com',
              next_action: 'request_info',
              source_count: 2,
              primary_source: { source_type: 'gmail_thread' },
              field_review_blockers: [
                { field: 'vendor', reason: 'critical_field_low_confidence' },
                { field: 'amount', reason: 'critical_field_low_confidence' },
              ],
              erp_status: 'connected',
              queue_age_minutes: 180,
              updated_at: '2026-06-05T12:00:00Z',
            },
            {
              id: 'AP-2',
              vendor_name: 'Atlas Legal',
              invoice_number: 'INV-200',
              amount: 4200,
              currency: 'USD',
              state: 'ready_to_post',
              owner_email: 'finance.ops@acme.com',
              next_action: 'post_to_erp',
              source_count: 1,
              primary_source: { source_type: 'netsuite' },
              erp_status: 'ready',
              updated_at: '2026-06-05T11:00:00Z',
            },
          ],
        };
      }
      if (url.startsWith('/api/workspace/dashboard/recent-activity')) {
        return {
          items: [
            {
              id: 'act-1',
              ts: '2026-06-05T12:05:00Z',
              action: 'Requested context',
              subject: 'Northstar Systems · INV-100',
              surface: 'gmail',
              tone: 'warning',
              box_type: 'ap_item',
              box_id: 'AP-1',
            },
          ],
        };
      }
      if (url.startsWith('/api/workspace/exceptions/stats')) {
        return { total_unresolved: 1, by_box_type: { ap_item: 1 } };
      }
      if (url.startsWith('/api/workspace/exceptions')) {
        return {
          count: 1,
          items: [{ id: 'ex-1', box_type: 'ap_item', box_id: 'AP-1', exception_type: 'field_review' }],
        };
      }
      if (url.startsWith('/api/ap/items/metrics/aggregation')) {
        return { metrics: { exception_count: 1 } };
      }
      if (url === '/api/workspace/dashboard/approver-workload') {
        return { approvers: [] };
      }
      if (url.startsWith('/api/workspace/implementation/status')) {
        return { all_complete: true, steps: [] };
      }
      return {};
    });

    renderHome();

    await waitFor(() => {
      expect(screen.getAllByText('Northstar Systems').length).toBeGreaterThan(0);
    });

    expect(screen.getAllByText('Work in progress').length).toBeGreaterThan(0);
    expect(screen.getByText('Operational context')).toBeTruthy();
    expect(screen.getAllByText('Field review: Vendor, Amount').length).toBeGreaterThan(0);
    expect(screen.getByText('2 sources linked · Gmail')).toBeTruthy();
    expect(screen.getByText('Requested context')).toBeTruthy();
    expect(document.body.textContent).not.toContain('critical_field_low_confidence');
  });
});
