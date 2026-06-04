import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, render, screen, waitFor } from '@testing-library/preact';
import RulesPage from './RulesPage.js';

const rules = [
  {
    id: 'rule-low',
    name: 'Low amount auto-approval',
    description: 'Fast path small, low-risk records.',
    priority: 100,
    workflow: 'ap',
    entity_id: null,
    conditions: {
      all_of: [
        { field: 'amount', op: 'lt', value: 1000 },
        { field: 'currency', op: 'eq', value: 'USD' },
      ],
    },
    actions: [{ type: 'auto_approve' }],
    status: 'active',
    updated_at: '2026-06-01T10:00:00Z',
  },
  {
    id: 'rule-mid',
    name: 'Manager approval',
    description: 'Route the middle band to the AP manager.',
    priority: 200,
    workflow: 'ap',
    entity_id: 'entity-emea',
    conditions: {
      all_of: [{ field: 'amount', op: 'gte', value: 1000 }],
      any_of: [{ field: 'department', op: 'eq', value: 'ops' }],
    },
    actions: [{ type: 'route_to_role', role: 'ap_manager' }],
    status: 'paused',
    updated_at: '2026-06-02T10:00:00Z',
  },
];

const templates = [
  {
    id: 'tpl-1',
    name: 'Large invoices require dual approval',
    description: 'High-value records require two approvers.',
    priority: 400,
    conditions: { all_of: [{ field: 'amount', op: 'gte', value: 50000 }] },
    actions: [{ type: 'require_dual_approval' }],
  },
];

function renderRulesPage({ responseRules = rules, responseTemplates = templates } = {}) {
  const api = vi.fn(async (path) => {
    const route = String(path);
    if (route.startsWith('/api/workspace/rules/templates')) {
      return { templates: responseTemplates };
    }
    if (route.startsWith('/api/workspace/rules?')) {
      return { rules: responseRules };
    }
    return {};
  });

  const rendered = render(h(RulesPage, {
    api,
    toast: vi.fn(),
  }));

  return { ...rendered, api };
}

describe('RulesPage', () => {
  afterEach(() => cleanup());

  it('frames approval rules as a workspace policy control surface', async () => {
    const { container } = renderRulesPage();

    await screen.findByText('Set who receives approval requests before work posts to ERP. Solden applies these rules, records the outcome, and keeps decisions in the surfaces your team already uses.');
    expect(screen.getByText('Policy inventory')).toBeTruthy();
    expect(screen.getByText('Routing order')).toBeTruthy();
    expect(screen.getByText('Policy guardrails')).toBeTruthy();
    expect(screen.getAllByText('Templates').length).toBeGreaterThan(0);
    expect(screen.getByText('2 required clauses')).toBeTruthy();
    expect(screen.getByText('1 required clause · 1 one-of clause')).toBeTruthy();
    expect(screen.getByText('Auto-approve')).toBeTruthy();
    expect(screen.getByText('Route to AP Manager')).toBeTruthy();
    expect(screen.getByText('Accounts Payable · All entities')).toBeTruthy();
    expect(screen.getByText('Accounts Payable · entity-emea')).toBeTruthy();

    await waitFor(() => {
      expect(container.textContent).not.toContain('Teach the agent how to route AP invoices');
      expect(container.textContent).not.toContain('all_of');
      expect(container.textContent).not.toContain('route_to_role');
      expect(container.textContent).not.toContain('AP invoices');
    });
  });

  it('uses a calm empty state when no policy exists yet', async () => {
    renderRulesPage({ responseRules: [], responseTemplates: [] });

    await screen.findByText('No approval rules yet');
    expect(screen.getByText('Create a rule or use a starter template to define who receives approval requests.')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'New rule' }).length).toBeGreaterThan(0);
  });
});
