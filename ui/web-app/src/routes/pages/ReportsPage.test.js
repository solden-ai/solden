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

const agentPerformancePayload = {
  summary: {
    sample_size: 3,
    auto_resolution_rate: 0.3333,
    exception_rate: 0.6667,
    avg_confidence: 0.86,
    memory_completeness_score: 0.92,
    memory_event_coverage_rate: 1,
    agent_trace_rate: 0.667,
    evidence_link_rate: 1,
    outcome_traceability_rate: 0.5,
    learning_loop_release_gate: 'needs_work',
    top_learning_blocker: 'critical_field_low_confidence',
    top_learning_blocker_count: 2,
  },
  series: [
    {
      bucket: '2026-05-04',
      total_items: 3,
      auto_resolution_rate: 0.3333,
      exception_rate: 0.6667,
      avg_confidence: 0.86,
    },
  ],
  breakdown: [],
  learning_loop: {
    status: 'available',
    release_gate: { status: 'needs_work' },
    summary: {
      memory_event_coverage_rate: 1,
      evidence_link_rate: 1,
      agent_trace_rate: 0.667,
      outcome_traceability_rate: 0.5,
      average_memory_completeness_score: 0.92,
    },
    recurring_blockers: [
      { key: 'critical_field_low_confidence', label: 'critical_field_low_confidence', count: 2 },
    ],
    agent_improvement_candidates: [
      {
        key: 'route_agent_decisions_through_memory',
        title: 'Route AP agent decisions through agent memory',
        evidence: { failed_case_count: 1, sample_size: 3 },
        metric: { name: 'agent_trace_rate', value: 0.667, target: 0.8 },
      },
    ],
    agent_improvement_register: {
      summary: { total: 1, open: 1, resolved: 0, high_priority_open: 1 },
      items: [
        {
          key: 'route_agent_decisions_through_memory',
          title: 'Route AP agent decisions through agent memory',
          status: 'open',
          priority: 'high',
          evidence: { failed_case_count: 1, sample_size: 3 },
          metric: {
            name: 'agent_trace_rate',
            value: 0.667,
            target: 0.8,
            direction: 'higher_is_better',
            target_met: false,
          },
        },
      ],
    },
    company_memory_profile: {
      headline: 'AP company learning is forming from real traces',
      maturity: { level: 'forming', score: 0.8 },
      sample: { total_items: 3 },
      next_learning_objective: {
        title: 'Route AP agent decisions through agent memory',
      },
    },
  },
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
    if (route.startsWith('/api/workspace/reports/agent-performance')) {
      return apiOverrides.agentPerformance || agentPerformancePayload;
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

  it('renders report charts with readable axes and value labels', async () => {
    const { container } = renderReports();

    await screen.findByText('GBP 84,200.00');

    expect(screen.getByRole('img', { name: 'Invoice count time series' })).toBeTruthy();
    expect(container.querySelectorAll('.cl-reports-chart-grid span')).toHaveLength(3);
    expect(container.querySelectorAll('.cl-reports-chart-bar')).toHaveLength(2);
    expect(container.querySelectorAll('.cl-reports-chart-value')).toHaveLength(2);
    expect(screen.getByText('05/04')).toBeTruthy();
    expect(screen.getByText('05/11')).toBeTruthy();
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

  it('renders AP learning-loop metrics in the agent outcomes report', async () => {
    renderReports();

    fireEvent.click(screen.getByRole('tab', { name: 'Agent outcomes' }));

    await screen.findByText('Learning loop');
    expect(screen.getByText('Whether AP work carries enough memory, evidence, and outcomes for Solden to improve safely.')).toBeTruthy();
    expect(screen.getByText('Memory events')).toBeTruthy();
    expect(screen.getByText('Evidence linked')).toBeTruthy();
    expect(screen.getByText('Agent traces')).toBeTruthy();
    expect(screen.getByText('Outcomes recorded')).toBeTruthy();
    expect(screen.getByText('Memory completeness')).toBeTruthy();
    expect(screen.getByText('Top recurring blocker')).toBeTruthy();
    expect(screen.getByText('Critical Field Low Confidence')).toBeTruthy();
    expect(screen.getByText('2 records')).toBeTruthy();
    expect(screen.getByText('Company learning')).toBeTruthy();
    expect(screen.getByText('AP company learning is forming from real traces')).toBeTruthy();
    expect(screen.getByText('Forming maturity · 80.0% · 3 records')).toBeTruthy();
    expect(screen.getByText('Next objective')).toBeTruthy();
    expect(screen.getByText('Top improvement')).toBeTruthy();
    expect(screen.getAllByText('Route AP agent decisions through agent memory').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('1 of 3 records · agent trace rate 66.7% · 1 open')).toBeTruthy();
  });
});
