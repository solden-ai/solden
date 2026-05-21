import { describe, it, expect, vi } from 'vitest';
import { h } from 'preact';
import { render, screen, fireEvent, waitFor } from '@testing-library/preact';
import ProcurementPage from './ProcurementPage.js';

function makeApi(pos) {
  const calls = [];
  const api = vi.fn(async (path, opts = {}) => {
    calls.push({ path, opts });
    const method = (opts.method || 'GET').toUpperCase();
    if (path === '/api/workspace/purchase-orders' && method === 'GET') {
      return { purchase_orders: pos };
    }
    if (path === '/api/workspace/purchase-orders' && method === 'POST') {
      return { po_id: 'PO-new', state: 'draft' };
    }
    return {}; // action POSTs
  });
  return { api, calls };
}

function mountPage(api) {
  return render(h(ProcurementPage, { api, orgId: 'org', toast: () => {} }));
}

describe('ProcurementPage', () => {
  it('renders POs with state-appropriate actions', async () => {
    const { api } = makeApi([
      { po_id: 'PO-1', po_number: 'PO-1', vendor_name: 'Acme', total_amount: 500, currency: 'GBP', status: 'pending_approval' },
    ]);
    mountPage(api);
    await waitFor(() => expect(screen.getByText('Acme')).toBeTruthy());
    expect(screen.getByText('Approve')).toBeTruthy();
    expect(screen.getByText('Reject')).toBeTruthy();
  });

  it('approve button POSTs to the approve endpoint and reloads', async () => {
    const { api, calls } = makeApi([
      { po_id: 'PO-1', po_number: 'PO-1', vendor_name: 'Acme', total_amount: 500, currency: 'GBP', status: 'pending_approval' },
    ]);
    mountPage(api);
    await waitFor(() => screen.getByText('Approve'));
    fireEvent.click(screen.getByText('Approve'));
    await waitFor(() => {
      expect(calls.some(
        (c) => c.path === '/api/workspace/purchase-orders/PO-1/approve'
          && (c.opts.method || '').toUpperCase() === 'POST',
      )).toBe(true);
    });
  });

  it('approved PO offers issue + receive actions', async () => {
    const { api } = makeApi([
      { po_id: 'PO-2', po_number: 'PO-2', vendor_name: 'Globex', total_amount: 1000, currency: 'USD', status: 'approved' },
    ]);
    mountPage(api);
    await waitFor(() => screen.getByText('Globex'));
    expect(screen.getByText('Issue to ERP')).toBeTruthy();
    expect(screen.getByText('Receive goods')).toBeTruthy();
  });

  it('shows the empty state when there are no POs', async () => {
    const { api } = makeApi([]);
    mountPage(api);
    await waitFor(() => expect(screen.getByText('No purchase orders')).toBeTruthy());
  });

  it('create button POSTs a new PO', async () => {
    const { api, calls } = makeApi([]);
    mountPage(api);
    await waitFor(() => screen.getByText('No purchase orders'));
    const vendorInput = document.querySelector('.po-create input');
    fireEvent.input(vendorInput, { target: { value: 'NewVendor' } });
    fireEvent.click(screen.getByText('New PO'));
    await waitFor(() => {
      expect(calls.some(
        (c) => c.path === '/api/workspace/purchase-orders'
          && (c.opts.method || '').toUpperCase() === 'POST'
          && c.opts.body?.vendor_name === 'NewVendor',
      )).toBe(true);
    });
  });
});
