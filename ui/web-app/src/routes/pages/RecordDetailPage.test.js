import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, render, screen, waitFor } from '@testing-library/preact';
import RecordDetailPage from './RecordDetailPage.js';

describe('RecordDetailPage', () => {
  afterEach(() => cleanup());

  it('surfaces operator rationale on timeline events', async () => {
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/ap-items/AP-1/detail')) {
        return {
          item: {
            id: 'AP-1',
            vendor_name: 'Acme Supplies',
            amount: 100,
            currency: 'USD',
            invoice_number: 'INV-1',
            status: 'approved',
            state: 'approved',
            due_date: '2026-06-10',
          },
          reasoning: {},
          match: {},
          actions: [],
          timeline: [{
            id: 'evt-1',
            operator_title: 'Invoice approved',
            occurred_at: '2026-06-01T17:20:00Z',
            operator_human_rationale: 'Vendor confirmed the PO out-of-band.',
          }],
        };
      }
      return {};
    });

    render(h(RecordDetailPage, {
      api,
      orgId: 'org-test',
      recordId: 'AP-1',
      bootstrap: {},
      navigate: () => {},
      toast: () => {},
    }));

    await waitFor(() => {
      expect(screen.getByText('Invoice approved')).toBeTruthy();
      expect(screen.getByText('Vendor confirmed the PO out-of-band.')).toBeTruthy();
    });
  });
});
