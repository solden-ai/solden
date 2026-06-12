import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, render, screen, waitFor } from '@testing-library/preact';
import VendorDetailPage from './VendorDetailPage.js';

describe('VendorDetailPage', () => {
  afterEach(() => cleanup());

  it('humanizes vendor source, flag, routing, state, and exception copy', async () => {
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/ap/items/vendors/Acme%20Supplies')) {
        return {
          profile: {
            status: 'active',
            currency: 'USD',
            custom_routing: {
              approver_group: 'controller_team',
              channel: 'slack',
              reason: 'high_value_vendor',
            },
          },
          summary: { total_invoices: 4, avg_invoice_amount: 1200 },
          verified_ibans: [{
            iban_masked: 'GB29 **** 3000',
            source: 'bank_verification',
            verified_at: '2026-06-01T10:00:00Z',
          }],
          fraud_flags: [{
            flag_type: 'bank_details_changed',
            severity: 'high',
            reason: 'IBAN changed after approval.',
            raised_at: '2026-06-02T10:00:00Z',
          }],
          recent_invoices: [{
            id: 'AP-1',
            invoice_number: 'INV-1',
            amount: 100,
            currency: 'USD',
            state: 'needs_info',
            exception_code: 'policy_validation_failed',
            invoice_date: '2026-06-03',
          }],
          exception_trend: [],
        };
      }
      return {};
    });

    const { container } = render(h(VendorDetailPage, {
      api,
      orgId: 'org-test',
      vendorName: 'Acme Supplies',
      navigate: () => {},
      toast: () => {},
    }));

    await screen.findByText('Acme Supplies');
    expect(screen.getByText(/Bank verification/)).toBeTruthy();
    expect(screen.getByText('Bank Details Changed')).toBeTruthy();
    expect(screen.getByText('Controller Team · via Slack · High Value Vendor')).toBeTruthy();
    expect(screen.getAllByText('Needs info').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Policy review').length).toBeGreaterThan(0);

    await waitFor(() => {
      expect(container.textContent).not.toContain('bank_verification');
      expect(container.textContent).not.toContain('bank_details_changed');
      expect(container.textContent).not.toContain('controller_team');
      expect(container.textContent).not.toContain('policy_validation_failed');
    });
  });

  it('renders the real vendor detail payload instead of empty placeholders', async () => {
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/ap/items/vendors/Google%20Cloud%20EMEA%20Limited')) {
        return {
          vendor_name: 'Google Cloud EMEA Limited',
          profile: { status: 'active' },
          summary: {
            invoice_count: 3,
            open_count: 1,
            posted_count: 1,
            issue_count: 1,
            total_amount: 12400,
            currency: 'EUR',
            primary_email: 'billing@cloud.google.com',
            last_activity_at: '2026-06-03T12:00:00Z',
          },
          risk: {
            score: 30,
            components: [{ label: 'KYC has never been completed for this vendor' }],
          },
          issue_summary: { total: 1, needs_info: 1 },
          open_issues: [{
            id: 'AP-22',
            invoice_number: 'GC-22',
            amount: 2400,
            currency: 'EUR',
            state: 'needs_info',
            issue_kind: 'needs_info',
            issue_label: 'Needs info',
            issue_summary: 'Ask the vendor for a corrected PO number.',
            updated_at: '2026-06-03T12:00:00Z',
          }],
          recent_items: [{
            id: 'AP-22',
            invoice_number: 'GC-22',
            amount: 2400,
            currency: 'EUR',
            state: 'needs_info',
            exception_code: 'po_missing_reference',
            updated_at: '2026-06-03T12:00:00Z',
          }, {
            id: 'AP-21',
            invoice_number: 'GC-21',
            amount: 10000,
            currency: 'EUR',
            state: 'posted_to_erp',
            erp_reference: 'ERP-21',
            updated_at: '2026-06-01T12:00:00Z',
          }],
          history: [{
            ap_item_id: 'AP-20',
            invoice_number: 'GC-20',
            amount: 8000,
            currency: 'EUR',
            final_state: 'posted_to_erp',
            created_at: '2026-05-15T12:00:00Z',
          }],
          top_exception_codes: [{ exception_code: 'po_missing_reference', count: 1 }],
        };
      }
      return {};
    });

    const { container } = render(h(VendorDetailPage, {
      api,
      orgId: 'org-test',
      vendorName: 'Google Cloud EMEA Limited',
      navigate: () => {},
      toast: () => {},
    }));

    await screen.findByText('Google Cloud EMEA Limited');
    expect(screen.getByText('Vendor record')).toBeTruthy();
    expect(screen.getByText('Review open vendor blockers')).toBeTruthy();
    expect(screen.getByText('Open work')).toBeTruthy();
    expect(screen.getAllByText('GC-22').length).toBeGreaterThan(0);
    expect(screen.getByText('Ask the vendor for a corrected PO number.')).toBeTruthy();
    expect(screen.getByText('EUR 12,400')).toBeTruthy();
    expect(screen.getByText('Risk 30')).toBeTruthy();
    expect(screen.getByText('Recent AP records')).toBeTruthy();
    expect(screen.getByText('PO required 1')).toBeTruthy();

    await waitFor(() => {
      expect(container.textContent).not.toContain('Invoices (180d)');
      expect(container.textContent).not.toContain('No ERP-side data yet');
      expect(container.textContent).not.toContain('No invoices in the last 180 days');
      expect(container.textContent).not.toContain('What the agent knows');
      expect(container.textContent).not.toContain('po_missing_reference');
    });
  });

  it('does not render a vendor master card when currency is the only available master field', async () => {
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/ap/items/vendors/Sparse%20Vendor')) {
        return {
          vendor_name: 'Sparse Vendor',
          profile: { status: 'active' },
          summary: {
            invoice_count: 2,
            open_count: 2,
            issue_count: 2,
            currency: 'EUR',
            primary_email: 'billing@sparse.example',
          },
          issue_summary: { total: 2, field_review: 2 },
          top_exception_codes: [{ exception_code: 'critical_field_low_confidence', count: 2 }],
          recent_items: [{
            id: 'AP-SPARSE-1',
            invoice_number: 'SP-1',
            amount: 10,
            currency: 'EUR',
            state: 'received',
            exception_code: 'critical_field_low_confidence',
            updated_at: '2026-06-03T12:00:00Z',
          }],
        };
      }
      return {};
    });

    render(h(VendorDetailPage, {
      api,
      orgId: 'org-test',
      vendorName: 'Sparse Vendor',
      navigate: () => {},
      toast: () => {},
    }));

    await screen.findByText('Sparse Vendor');
    expect(screen.queryByText('Vendor master')).toBeNull();
    expect(screen.queryByText('ERP and profile fields')).toBeNull();
  });
});
