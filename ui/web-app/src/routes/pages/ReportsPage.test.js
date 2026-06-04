import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/preact';
import ReportsPage from './ReportsPage.js';

const volumePayload = {
  summary: {
    total_invoices: 24,
    total_amount: 84200,
    distinct_vendors: 9,
    currency: 'GBP',
  },
  series: [
    { bucket: '2026-05-04', invoice_count: 8 },
    { bucket: '2026-05-11', invoice_count: 16 },
  ],
  breakdown: [
    { vendor_name: 'Northstar Logistics', invoice_count: 8, total_amount: 32000, currency: 'GBP' },
  ],
};

const exceptionPayload = {
  summary: {
    total_exceptions: 7,
    distinct_codes: 2,
    top_code: 'po_required_missing',
    top_code_count: 5,
  },
  series: [{ bucket: '2026-05-04', total_exceptions: 7 }],
  breakdown: [{ exception_code: 'po_required_missing', count: 5, share: 0.714 }],
};

function renderReports(apiOverrides = {}) {
  const api = vi.fn(async (path, opts = {}) => {
    const method = (opts.method || 'GET').toUpperCase();
    const route = String(path);

    if (route === '/api/workspace/reports/subscriptions' && method === 'GET') {
      return { subscriptions: [] };
    }
    if (route === '/api/workspace/reports/subscriptions' && method === 'POST') {
      return { id: 'sub-1' };
    }
    if (route.startsWith('/api/workspace/reports/exception-breakdown')) {
      return apiOverrides.exceptionBreakdown || exceptionPayload;
    }
    if (route.startsWith('/api/workspace/reports/volume')) {
      return apiOverrides.volume || volumePayload;
    }
    return { summary: {}, series: [], breakdown: [] };
  });

  const rendered = render(h(ReportsPage, {
    api,
    orgId: 'org-test',
    toast: () => {},
  }));

  return { ...rendered, api };
}

describe('ReportsPage', () => {
  afterEach(() => cleanup());

  it('uses operational report framing instead of stale internal copy', async () => {
    const { container } = renderReports();

    await screen.findByText('Operating reports for AP volume, cycle time, exceptions, vendor quality, and agent outcomes.');
    expect(screen.getByRole('tab', { name: 'Agent outcomes' })).toBeTruthy();
    expect(screen.getByText('Invoice count and spend by period, entity, and vendor.')).toBeTruthy();
    expect(screen.getByText('GBP 84,200.00')).toBeTruthy();

    await waitFor(() => {
      expect(container.textContent).not.toContain('Five designed reports');
      expect(container.textContent).not.toContain('tenant-isolated');
      expect(container.textContent).not.toContain('Agent Performance');
    });
  });

  it('treats zero-volume summaries with metadata as empty report data', async () => {
    renderReports({
      volume: {
        summary: {
          total_invoices: 0,
          total_amount: 0,
          distinct_vendors: 0,
          currency: 'GBP',
        },
        series: [],
        breakdown: [],
      },
    });

    await screen.findByText('No report data in this window');
    expect(screen.queryByText('Total invoices')).toBeNull();
  });

  it('humanizes exception report codes for operator review', async () => {
    const { container } = renderReports();

    fireEvent.click(screen.getByRole('tab', { name: 'Exceptions' }));

    await screen.findByText('Top blocker');
    expect(screen.getAllByText('PO Required Missing').length).toBeGreaterThan(0);
    expect(screen.getByText('Blockers ranked')).toBeTruthy();

    await waitFor(() => {
      expect(container.textContent).not.toContain('po_required_missing');
      expect(container.textContent).not.toContain('Exception code');
    });
  });

  it('does not render stale report data while a tab switch is loading', async () => {
    let resolveException;
    const pendingException = new Promise((resolve) => {
      resolveException = () => resolve(exceptionPayload);
    });
    const { api, container } = renderReports({
      exceptionBreakdown: pendingException,
    });

    expect((await screen.findAllByText('Northstar Logistics')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('tab', { name: 'Exceptions' }));

    await waitFor(() => {
      expect(api.mock.calls.some(([path]) => (
        String(path).startsWith('/api/workspace/reports/exception-breakdown')
      ))).toBe(true);
    });
    expect(screen.getByText('Where work is getting blocked and which blockers are rising.')).toBeTruthy();
    expect(container.textContent).not.toContain('Northstar Logistics');
    expect(container.textContent).not.toContain('GBP 84,200.00');

    resolveException();
    expect((await screen.findAllByText('PO Required Missing')).length).toBeGreaterThan(0);
  });

  it('schedules delivery with the currently selected report filters', async () => {
    const { api } = renderReports();

    await screen.findByText('GBP 84,200.00');

    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-05-01' } });
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-05-31' } });
    fireEvent.change(screen.getByLabelText('Entity'), { target: { value: 'emea' } });
    fireEvent.input(screen.getByLabelText('Recipient'), {
      target: { value: 'controller@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Subscribe' }));

    await waitFor(() => {
      const post = api.mock.calls.find(([path, opts = {}]) => (
        path === '/api/workspace/reports/subscriptions'
        && (opts.method || '').toUpperCase() === 'POST'
      ));
      expect(post).toBeTruthy();
      const body = JSON.parse(post[1].body);
      expect(body).toEqual({
        report_type: 'volume',
        cadence: 'weekly',
        recipient_email: 'controller@example.com',
        params: {
          period: 'weekly',
          from: '2026-05-01T00:00:00+00:00',
          to: '2026-05-31T23:59:59+00:00',
          entity_id: 'emea',
        },
      });
    });
  });
});
