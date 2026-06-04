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
    expect(screen.getByText('Needs info')).toBeTruthy();
    expect(screen.getByText('Policy review')).toBeTruthy();

    await waitFor(() => {
      expect(container.textContent).not.toContain('bank_verification');
      expect(container.textContent).not.toContain('bank_details_changed');
      expect(container.textContent).not.toContain('controller_team');
      expect(container.textContent).not.toContain('policy_validation_failed');
    });
  });
});
