import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/preact';
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
  it("renders Solden's distilled rationale with a confirm affordance", async () => {
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/ap-items/AP-4/detail')) {
        return {
          item: {
            id: 'AP-4',
            vendor_name: 'Acme Supplies',
            amount: 100,
            currency: 'USD',
            invoice_number: 'INV-4',
            state: 'approved',
          },
          reasoning: {},
          match: {},
          actions: [],
          timeline: [{
            id: 'evt-distilled-1',
            operator_title: 'Rationale distilled',
            occurred_at: '2026-06-09T10:00:00Z',
            operator_distilled_rationale: 'Approved because it covers the Q3 true-up Dana signed off on.',
            operator_distilled_status: 'machine_distilled',
          }],
        };
      }
      return {};
    });

    render(h(RecordDetailPage, {
      api,
      orgId: 'org-test',
      recordId: 'AP-4',
      bootstrap: {},
      navigate: () => {},
      toast: () => {},
    }));

    await waitFor(() => {
      expect(screen.getByText("Solden's read")).toBeTruthy();
      expect(screen.getByText('Approved because it covers the Q3 true-up Dana signed off on.')).toBeTruthy();
      expect(screen.getByText('Confirm')).toBeTruthy();
    });
  });

  it('asks the contextual question when an intent is blocked high-signal, then retries with the answer', async () => {
    const calls = [];
    const api = vi.fn(async (path, opts) => {
      if (String(path).startsWith('/api/workspace/ap-items/AP-5/detail')) {
        return {
          item: {
            id: 'AP-5',
            vendor_name: 'Acme Supplies',
            amount: 3200,
            currency: 'EUR',
            invoice_number: 'INV-5',
            state: 'needs_approval',
          },
          reasoning: {},
          match: {},
          actions: { available: ['escalate_approval'], primary: 'escalate_approval' },
          timeline: [],
        };
      }
      if (String(path).startsWith('/api/agent/intents/execute')) {
        calls.push(JSON.parse(opts.body));
        if (calls.length === 1) {
          return {
            status: 'blocked',
            reason: 'high_signal_rationale_required',
            question: "This is 3.2x Acme's typical amount - what makes it OK?",
          };
        }
        return { status: 'ok' };
      }
      return {};
    });

    render(h(RecordDetailPage, {
      api,
      orgId: 'org-test',
      recordId: 'AP-5',
      bootstrap: {},
      navigate: () => {},
      toast: () => {},
    }));

    const btn = await screen.findByText('Escalate to controller');
    btn.click();

    // The blocked response opens the elicitation dialog with the question.
    await screen.findByText("This is 3.2x Acme's typical amount - what makes it OK?");
    const textarea = document.querySelector('.cl-record-dialog textarea');
    fireEvent.input(textarea, { target: { value: 'Contract true-up Dana signed off.' } });
    fireEvent.click(screen.getByText('Confirm'));

    await waitFor(() => {
      expect(calls.length).toBe(2);
      expect(calls[1].input.reason).toBe('Contract true-up Dana signed off.');
    });
  });
});
