import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, render, screen, waitFor } from '@testing-library/preact';
import VendorsPage from './VendorsPage.js';

describe('VendorsPage', () => {
  afterEach(() => cleanup());

  it('humanizes vendor directory state, exception, anomaly, and status labels', async () => {
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/ap/items/vendors?')) {
        return {
          vendors: [{
            vendor_name: 'Acme Supplies',
            primary_email: 'ap@acme.example',
            currency: 'USD',
            total_amount: 1800,
            invoice_count: 4,
            open_count: 2,
            issue_count: 1,
            approval_count: 1,
            top_states: [{ state: 'needs_info', count: 2 }],
            top_exception_codes: [{ exception_code: 'policy_validation_failed', count: 1 }],
            profile: {
              status: 'archived',
              anomaly_flags: ['bank_details_changed'],
            },
          }],
        };
      }
      if (String(path).startsWith('/api/workspace/vendor-intelligence/duplicates')) {
        return { clusters: [] };
      }
      return {};
    });

    const { container } = render(h(VendorsPage, {
      api,
      orgId: 'org-test',
      navigate: () => {},
      toast: () => {},
    }));

    await screen.findByText('Acme Supplies');
    expect(screen.getByText('Needs info 2')).toBeTruthy();
    expect(screen.getByText('Policy review 1')).toBeTruthy();
    expect(screen.getByText('Bank Details Changed')).toBeTruthy();
    expect(screen.getByText('Archived')).toBeTruthy();

    await waitFor(() => {
      expect(container.textContent).not.toContain('needs_info');
      expect(container.textContent).not.toContain('policy_validation_failed');
      expect(container.textContent).not.toContain('bank_details_changed');
    });
  });
});
