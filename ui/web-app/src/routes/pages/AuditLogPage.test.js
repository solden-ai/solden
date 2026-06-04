import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/preact';
import AuditLogPage from './AuditLogPage.js';

const auditEvent = {
  id: 'evt-1',
  ts: '2026-06-03T12:00:00Z',
  event_type: 'state_transition',
  actor_id: 'agent_runtime',
  actor_type: 'system',
  box_type: 'ap_item',
  box_id: 'AP-42',
  prev_state: 'needs_info',
  new_state: 'posted_to_erp',
  governance_verdict: 'should_execute',
  agent_confidence: 0.91,
  decision_reason: 'Vendor confirmed the invoice.',
  source: 'erp_native_netsuite',
  payload_json: { transition: 'approved_for_posting' },
};

function renderAuditPage({ events = [auditEvent], detailErrorOnce = false } = {}) {
  let detailFailures = detailErrorOnce ? 1 : 0;
  const api = vi.fn(async (path, opts = {}) => {
    const route = String(path);
    const method = (opts.method || 'GET').toUpperCase();

    if (route.startsWith('/api/workspace/audit/retention')) {
      return {
        effective_days: 365,
        tier_ceiling_days: 365,
        configured_days: null,
      };
    }
    if (route.startsWith('/api/workspace/audit/chain-status')) {
      return {
        chain_intact: true,
        chain_length: 3,
        verified_at: '2026-06-03T12:05:00Z',
      };
    }
    if (route.startsWith('/api/workspace/audit/search')) {
      return { events, next_cursor: null, count: events.length };
    }
    if (route.startsWith('/api/workspace/audit/event/') && method === 'GET') {
      if (detailFailures > 0) {
        detailFailures -= 1;
        throw new Error('detail unavailable');
      }
      return { event: auditEvent };
    }
    if (route === '/api/workspace/audit/export' && method === 'POST') {
      return { job_id: 'export-1', status: 'queued' };
    }
    return {};
  });

  const rendered = render(h(AuditLogPage, {
    api,
    orgId: 'org-test',
    bootstrap: {},
  }));

  return { ...rendered, api };
}

describe('AuditLogPage', () => {
  afterEach(() => cleanup());

  it('renders audit records with operator-readable labels instead of raw backend tokens', async () => {
    const { container } = renderAuditPage();

    await screen.findByText('Tamper-evident record of workflow actions, policy decisions, exports, and configuration changes.');
    expect((await screen.findAllByText('State change')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Accounts Payable').length).toBeGreaterThan(0);
    expect(screen.getByText('Needs info')).toBeTruthy();
    expect(screen.getByText('Posted to ERP')).toBeTruthy();
    expect(screen.getAllByText('Allowed').length).toBeGreaterThan(0);
    expect(screen.getAllByText('91%').length).toBeGreaterThan(0);

    await waitFor(() => {
      expect(container.textContent).not.toContain('Module 7');
      expect(container.textContent).not.toContain('Pass 1');
      expect(container.textContent).not.toContain('state_transition');
      expect(container.textContent).not.toContain('ap_item');
      expect(container.textContent).not.toContain('needs_info');
      expect(container.textContent).not.toContain('posted_to_erp');
      expect(container.textContent).not.toContain('should_execute');
      expect(container.textContent).not.toContain('Plan-observed');
    });
  });

  it('loads detail through the canonical event endpoint and retries real failures', async () => {
    const { api } = renderAuditPage({ detailErrorOnce: true });

    await waitFor(() => expect(screen.getAllByText('State change').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByLabelText('State change for Accounts Payable AP-42'));

    await screen.findByText('detail unavailable');
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    await screen.findByText('Vendor confirmed the invoice.');
    expect(screen.getByText('NetSuite panel')).toBeTruthy();
    expect(api.mock.calls.filter(([path]) => String(path).startsWith('/api/workspace/audit/event/evt-1')).length).toBe(2);
  });

  it('renders audit administration rows without exposing raw event tokens', async () => {
    renderAuditPage({
      events: [{
        ...auditEvent,
        id: 'evt-export-download',
        event_type: 'audit_export_downloaded',
        box_type: 'audit_export',
        box_id: 'AEX-123',
        prev_state: null,
        new_state: null,
      }],
    });

    await waitFor(() => {
      expect(screen.getAllByText('Audit export downloaded').length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText('Audit export').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('Event type').textContent).toContain('Audit administration');
    expect(screen.queryByText('audit_export_downloaded')).toBeNull();
    expect(screen.queryByText('audit_export')).toBeNull();
  });

  it('submits export filters against the same audit query fields', async () => {
    const { api } = renderAuditPage();

    await waitFor(() => expect(screen.getAllByText('State change').length).toBeGreaterThan(0));
    fireEvent.change(screen.getByLabelText('Event type'), {
      target: { value: 'erp_post_completed,erp_post_failed' },
    });
    fireEvent.change(screen.getByLabelText('Record type'), {
      target: { value: 'ap_item' },
    });
    fireEvent.input(screen.getByLabelText('Actor'), {
      target: { value: 'controller@example.com' },
    });
    fireEvent.input(screen.getByLabelText('Record ID'), {
      target: { value: 'AP-42' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));

    await waitFor(() => {
      const post = api.mock.calls.find(([path, opts = {}]) => (
        path === '/api/workspace/audit/export'
        && (opts.method || '').toUpperCase() === 'POST'
      ));
      expect(post).toBeTruthy();
      expect(JSON.parse(post[1].body)).toMatchObject({
        organization_id: 'org-test',
        event_types: ['erp_post_completed', 'erp_post_failed'],
        actor_id: 'controller@example.com',
        box_type: 'ap_item',
        box_id: 'AP-42',
        format: 'csv',
      });
    });
  });
});
