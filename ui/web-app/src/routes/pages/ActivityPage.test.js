import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/preact';
import ActivityPage from './ActivityPage.js';

describe('ActivityPage', () => {
  afterEach(() => cleanup());

  it('renders a cross-work-type stream instead of an AP-only log', async () => {
    const navigate = vi.fn();
    const api = vi.fn(async (path) => {
      if (path === '/api/workspace/dashboard/recent-activity?limit=50') {
        return {
          items: [
            {
              id: 'act-1',
              ts: '2026-06-03T12:00:00Z',
              action: 'Posted to ERP',
              subject: '#INV-100 from Northstar',
              surface: 'netsuite',
              tone: 'success',
              box_type: 'ap_item',
              box_id: 'AP-1',
            },
            {
              id: 'act-2',
              ts: '2026-06-03T11:55:00Z',
              action: 'Sent for approval',
              subject: 'Procurement record PO-8',
              surface: 'slack',
              tone: 'info',
              box_type: 'purchase_order',
              box_id: 'PO-8',
              record_path: '/procurement',
            },
          ],
        };
      }
      return {};
    });

    render(h(ActivityPage, {
      api,
      orgId: 'org',
      onRefresh: vi.fn(async () => {}),
      navigate,
    }));

    await waitFor(() => expect(screen.getAllByRole('heading', { name: 'Activity stream' }).length).toBeGreaterThan(0));

    expect(api).toHaveBeenCalledWith('/api/workspace/dashboard/recent-activity?limit=50');
    expect(screen.getByText('Every agent and operator action across work types and connected surfaces.')).toBeTruthy();
    expect(screen.getByText('Accounts Payable, Procurement')).toBeTruthy();
    expect(screen.getByText('NetSuite, Slack')).toBeTruthy();
    expect(screen.getByText('Posted to ERP')).toBeTruthy();
    expect(screen.getByText('Sent for approval')).toBeTruthy();
    expect(screen.queryByText(/AP records/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Open Accounts Payable' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Review exceptions' }));
    expect(navigate).toHaveBeenCalledWith('/exceptions');
  });
});
