import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/preact';
import ExceptionsPage from './ExceptionsPage.js';

describe('ExceptionsPage', () => {
  afterEach(() => cleanup());

  it('loads exceptions from workspace endpoints and navigates with the SPA router', async () => {
    const navigate = vi.fn();
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/exceptions/stats')) {
        return {
          total_unresolved: 1,
          by_severity: { critical: 1 },
          by_type: { amount_anomaly: 1 },
          by_box_type: { ap_item: 1 },
        };
      }
      if (String(path).startsWith('/api/workspace/exceptions')) {
        return {
          items: [{
            id: 'exc-1',
            box_type: 'ap_item',
            box_id: 'AP-1',
            severity: 'critical',
            exception_type: 'amount_anomaly',
            box_summary: {
              vendor_name: 'Acme',
              invoice_number: 'INV-1',
              amount: 100,
              currency: 'USD',
            },
          }],
        };
      }
      return {};
    });

    render(h(ExceptionsPage, { api, navigate }));

    await waitFor(() => {
      expect(screen.getByText(/Acme/)).toBeTruthy();
    });
    expect(api.mock.calls.some(([path]) => path === '/api/workspace/exceptions')).toBe(true);
    expect(api.mock.calls.some(([path]) => path === '/api/workspace/exceptions/stats')).toBe(true);

    fireEvent.click(screen.getByText(/Acme/));
    expect(navigate).toHaveBeenCalledWith('/accounts-payable/AP-1');
  });

  it('surfaces cross-work-type exceptions and filters them without AP-only framing', async () => {
    const navigate = vi.fn();
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/exceptions/stats')) {
        return {
          total_unresolved: 3,
          by_severity: { high: 1, medium: 2 },
          by_type: { po_mismatch: 1, bank_detail_review: 1, approval_wait: 1 },
          by_box_type: { ap_item: 1, purchase_order: 1, vendor_onboarding_session: 1 },
        };
      }
      if (String(path).startsWith('/api/workspace/exceptions')) {
        return {
          items: [
            {
              id: 'exc-ap',
              box_type: 'ap_item',
              box_id: 'AP-1',
              severity: 'high',
              exception_type: 'po_mismatch',
              box_summary: { vendor_name: 'Northstar', invoice_number: 'INV-1' },
            },
            {
              id: 'exc-po',
              box_type: 'purchase_order',
              box_id: 'PO-8',
              severity: 'medium',
              exception_type: 'approval_wait',
              box_summary: { vendor_name: 'Atlas', po_number: 'PO-8' },
            },
            {
              id: 'exc-vendor',
              box_type: 'vendor_onboarding_session',
              box_id: 'VOS-1',
              severity: 'medium',
              exception_type: 'bank_detail_review',
              metadata: { vendor_name: 'Aurora Systems' },
            },
          ],
        };
      }
      return {};
    });

    render(h(ExceptionsPage, { api, navigate }));

    await waitFor(() => expect(screen.getByText('Work waiting on judgment')).toBeTruthy());
    expect(screen.getByText('Exceptions across every work type that need context, owner action, or proof before the agent can continue.')).toBeTruthy();
    expect(screen.queryByText(/AP records/)).toBeNull();
    expect(screen.getAllByText('Procurement').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Vendor Onboarding').length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText('Work type'), { target: { value: 'purchase_order' } });
    expect(screen.getByText(/Atlas/)).toBeTruthy();
    expect(screen.queryByText(/Northstar/)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Open procurement' }));
    expect(navigate).toHaveBeenCalledWith('/procurement');
  });

  it('posts resolves through the workspace exception endpoint when authorized', async () => {
    const api = vi.fn(async (path, opts = {}) => {
      if (String(path).startsWith('/api/workspace/exceptions/stats')) {
        return { total_unresolved: 1, by_severity: {}, by_type: {}, by_box_type: {} };
      }
      if (String(path).endsWith('/resolve') && (opts.method || '').toUpperCase() === 'POST') {
        return { status: 'resolved' };
      }
      if (String(path).startsWith('/api/workspace/exceptions')) {
        return {
          items: [{
            id: 'exc-1',
            box_type: 'ap_item',
            box_id: 'AP-1',
            severity: 'high',
            exception_type: 'amount_anomaly',
            box_summary: { vendor_name: 'Acme' },
          }],
        };
      }
      return {};
    });

    render(h(ExceptionsPage, {
      api,
      navigate: () => {},
      bootstrap: {
        capabilities_tree: {
          ap_item: { approve_invoice: true },
        },
      },
    }));

    await waitFor(() => screen.getByText('Resolve'));
    fireEvent.click(screen.getByText('Resolve'));
    const dialog = await waitFor(() => screen.getByRole('dialog'));

    // The resolve button is gated until a rationale is entered; the
    // human "why" is required before an exception can be cleared.
    const resolveBtn = within(dialog).getByRole('button', { name: 'Resolve' });
    expect(resolveBtn.disabled).toBe(true);

    fireEvent.input(within(dialog).getByLabelText('Resolution note'), {
      target: { value: 'Vendor confirmed corrected IBAN' },
    });
    expect(resolveBtn.disabled).toBe(false);
    fireEvent.click(resolveBtn);

    await waitFor(() => {
      expect(api.mock.calls.some(([path, opts]) => (
        path === '/api/workspace/exceptions/exc-1/resolve'
        && (opts.method || '').toUpperCase() === 'POST'
        && opts.body?.resolution_note === 'Vendor confirmed corrected IBAN'
      ))).toBe(true);
    });
  });

  it('hides resolve actions when the user lacks AP approval authority', async () => {
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/exceptions/stats')) {
        return { total_unresolved: 1, by_severity: {}, by_type: {}, by_box_type: {} };
      }
      if (String(path).startsWith('/api/workspace/exceptions')) {
        return {
          items: [{
            id: 'exc-1',
            box_type: 'ap_item',
            box_id: 'AP-1',
            severity: 'high',
            exception_type: 'amount_anomaly',
            box_summary: { vendor_name: 'Acme' },
          }],
        };
      }
      return {};
    });

    render(h(ExceptionsPage, {
      api,
      navigate: () => {},
      bootstrap: {
        capabilities_tree: {
          ap_item: { approve_invoice: false },
        },
      },
    }));

    await waitFor(() => screen.getByText(/Acme/));
    expect(screen.queryByRole('button', { name: 'Resolve' })).toBeNull();
  });
});
