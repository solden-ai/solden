import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/preact';
import SettingsPage from './SettingsPage.js';

function makeBootstrap() {
  return {
    current_user: {
      email: 'owner@acme.test',
      role: 'owner',
      workspace_role: 'owner',
    },
    capabilities: {
      manage_company: true,
      manage_plan: true,
      manage_team: true,
    },
    organization: {
      id: 'org-test',
      name: 'Acme Operations',
      domain: 'acme.test',
      integration_mode: 'per_org',
      settings: {},
    },
    subscription: {
      plan: 'professional',
      status: 'active',
      billing_cycle: 'monthly',
      usage: {
        users_count: 2,
        invoices_this_month: 42,
        ai_credits_this_month: 120,
      },
    },
    integrations: [
      { name: 'gmail', connected: true, status: 'connected' },
      { name: 'erp', connected: true, status: 'connected', connections: [{ erp_type: 'netsuite' }] },
      { name: 'slack', connected: false, status: 'disconnected' },
      { name: 'teams', connected: true, status: 'connected' },
    ],
  };
}

function renderSettingsPage({ routeId = '' } = {}) {
  const api = vi.fn(async (path) => {
    const route = String(path);
    if (route.startsWith('/api/workspace/team/invites')) {
      return {
        invites: [
          { id: 'invite-1', email: 'pending@acme.test', status: 'pending', role: 'ap_clerk' },
        ],
      };
    }
    if (route.startsWith('/erp/gl-map')) {
      return { gl_account_map: { expenses: '6100' } };
    }
    if (route.startsWith('/api/workspace/subscription/billing-summary')) {
      return {
        active_seats: 2,
        read_only_seats: 0,
        invoices_this_month: 42,
        invoice_volume_band: 'starter',
        ai_credits_used: 120,
        ai_credits_remaining: 880,
        estimated_total: 149,
      };
    }
    if (route.startsWith('/settings/org-test')) {
      return {
        approval_thresholds: [
          {
            min_amount: 0,
            max_amount: 1000,
            approver_channel: 'slack',
            approvers: ['approver@acme.test'],
          },
        ],
      };
    }
    if (route.startsWith('/api/workspace/entities')) {
      return { entities: [] };
    }
    if (route.startsWith('/api/workspace/team/users')) {
      return {
        users: [
          { id: 'user-1', name: 'Owner', email: 'owner@acme.test', role: 'owner', is_active: true },
          { id: 'user-2', name: 'Clerk', email: 'clerk@acme.test', role: 'ap_clerk', is_active: true },
        ],
      };
    }
    return {};
  });
  const navigate = vi.fn();
  const rendered = render(h(SettingsPage, {
    bootstrap: makeBootstrap(),
    api,
    toast: vi.fn(),
    orgId: 'org-test',
    onRefresh: vi.fn(),
    routeId,
    navigate,
  }));
  return { ...rendered, api, navigate };
}

describe('SettingsPage', () => {
  afterEach(() => cleanup());

  it('uses grouped settings navigation instead of the old tab strip', async () => {
    const { container, navigate } = renderSettingsPage();

    await screen.findByRole('heading', { name: 'Settings' });
    expect(screen.getByRole('navigation', { name: 'Settings sections' })).toBeTruthy();
    expect(screen.getAllByText('Workspace and systems').length).toBeGreaterThan(0);
    expect(screen.getByText('Policy controls')).toBeTruthy();
    expect(screen.getAllByText('Access').length).toBeGreaterThan(0);
    expect(screen.getByText('Operations')).toBeTruthy();
    expect(container.querySelector('.settings-tabs-strip')).toBeNull();
    expect(container.querySelector('.cl-settings-layout')).toBeTruthy();
    expect(screen.getByRole('heading', { level: 2, name: 'Workspace' })).toBeTruthy();

    fireEvent.click(screen.getByText('Team').closest('button'));

    expect(navigate).toHaveBeenCalledWith('/settings/team');
    await screen.findByRole('heading', { level: 2, name: 'Team' });
  });

  it('opens the requested section from the settings route id', async () => {
    renderSettingsPage({ routeId: 'team' });

    await screen.findByRole('heading', { level: 2, name: 'Team' });
    expect(screen.getByText('Invite the people who need to work, monitor, or manage back-office operations.')).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText('owner@acme.test')).toBeTruthy();
    });
  });
});
