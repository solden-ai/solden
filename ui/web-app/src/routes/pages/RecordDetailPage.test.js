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

  it('humanizes field review blockers in the agent evidence panel', async () => {
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/ap-items/AP-2/detail')) {
        return {
          item: {
            id: 'AP-2',
            vendor_name: 'Acme Supplies',
            amount: 100,
            currency: 'USD',
            invoice_number: 'INV-2',
            state: 'needs_info',
            due_date: '2026-06-10',
          },
          reasoning: {
            sources: {
              confidence_gate: {
                confidence_blockers: [
                  { field: 'vendor', reason: 'critical_field_low_confidence' },
                  { field: 'amount', reason: 'critical_field_low_confidence' },
                ],
              },
            },
          },
          match: {},
          actions: [],
          timeline: [],
        };
      }
      return {};
    });

    const { container } = render(h(RecordDetailPage, {
      api,
      orgId: 'org-test',
      recordId: 'AP-2',
      bootstrap: {},
      navigate: () => {},
      toast: () => {},
    }));

    await screen.findByText('Evidence and checks');
    expect(screen.getByText('Fields needing review')).toBeTruthy();
    expect(screen.getAllByText('Vendor').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Amount').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Solden is not confident enough in this critical field; a person needs to confirm it.')).toHaveLength(2);
    expect(container.textContent).not.toContain('critical_field_low_confidence');
    expect(container.textContent).not.toContain('Field review blockers');
  });

  it('renders the Record state panel from the canonical surface_memory', async () => {
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/ap-items/AP-3/detail')) {
        return {
          item: {
            id: 'AP-3',
            vendor_name: 'Acme Supplies',
            amount: 100,
            currency: 'USD',
            invoice_number: 'INV-3',
            state: 'needs_approval',
          },
          reasoning: {},
          match: {},
          actions: [],
          timeline: [],
          memory: { execution_state: {} },
          // The one record. Owner is NOT on item.owner_email, so if the panel
          // rendered "Maya R." it read the record, not raw columns.
          surface_memory: {
            contract: 'solden_memory_surface.v1',
            full_memory_url: '/records/AP-3',
            fields: [
              { label: 'Owner', value: 'Maya R.' },
              { label: 'Waiting on', value: 'CFO delegate' },
              { label: 'Next', value: 'Route to CFO delegate' },
            ],
          },
        };
      }
      return {};
    });

    render(h(RecordDetailPage, {
      api,
      orgId: 'org-test',
      recordId: 'AP-3',
      bootstrap: {},
      navigate: () => {},
      toast: () => {},
    }));

    await waitFor(() => {
      expect(screen.getByText('Record state')).toBeTruthy();
      expect(screen.getByText('Maya R.')).toBeTruthy();
      expect(screen.getByText('CFO delegate')).toBeTruthy();
      expect(screen.getByText('Route to CFO delegate')).toBeTruthy();
    });
  });
});
