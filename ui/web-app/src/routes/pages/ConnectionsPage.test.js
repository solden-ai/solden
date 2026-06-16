import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/preact';
import ConnectionsPage from './ConnectionsPage.js';

function makeBootstrap() {
  return {
    current_user: { role: 'owner', workspace_role: 'owner' },
    capabilities: { manage_connections: true },
    integrations: [
      { name: 'gmail', status: 'connected', connected: true },
      { name: 'outlook', status: 'disconnected', connected: false },
      { name: 'erp', status: 'connected', connected: true, connections: [{ erp_type: 'netsuite' }] },
      { name: 'slack', status: 'connected', connected: true, approval_channel: '#approvals' },
      { name: 'teams', status: 'disconnected', connected: false },
    ],
  };
}

function makeWebhooks(count = 6) {
  return Array.from({ length: count }, (_, idx) => ({
    id: `wh-${idx + 1}`,
    url: `https://hooks.example.com/${idx + 1}`,
    event_types: ['*'],
  }));
}

function renderConnectionsPage({ webhooks = makeWebhooks() } = {}) {
  const api = vi.fn(async (path) => {
    const route = String(path);
    if (route.startsWith('/api/workspace/connections/health')) {
      return {
        computed_at: '2026-06-04T10:00:00Z',
        integrations: [],
        webhooks: { delivered: 0, retrying: 0, failed: 0 },
      };
    }
    if (route.startsWith('/api/workspace/surface-readiness')) {
      return {
        summary: { connected: 5, total: 11 },
        surfaces: [
          {
            key: 'netsuite',
            label: 'NetSuite',
            family: 'erp',
            role: 'ERP native + API connector',
            memory_surface: 'SuiteApp panel',
            maturity: 'native_panel_ready',
            maturity_label: 'Native panel ready',
            decision_actions: 'Approve, reject, request info from vendor bill context',
            connection_status: 'connected',
          },
          {
            key: 'quickbooks',
            label: 'QuickBooks',
            family: 'erp',
            role: 'API connector',
            memory_surface: 'Provider-neutral ERP memory API',
            maturity: 'api_memory_ready',
            maturity_label: 'API memory ready',
            decision_actions: 'Resolve ERP reference to Solden memory',
            connection_status: 'not_connected',
          },
          {
            key: 'slack',
            label: 'Slack',
            family: 'approval',
            role: 'Chat decision surface',
            memory_surface: 'Approval cards and reply sync',
            maturity: 'production_ready',
            maturity_label: 'Production-ready',
            decision_actions: 'Approve, reject, request info',
            connection_status: 'connected',
          },
        ],
      };
    }
    if (route === '/api/workspace/webhooks') {
      return { webhooks };
    }
    return {};
  });

  const navigate = vi.fn();
  const rendered = render(h(ConnectionsPage, {
    bootstrap: makeBootstrap(),
    api,
    toast: vi.fn(),
    orgId: 'org-test',
    onRefresh: vi.fn(),
    oauthBridge: { open: vi.fn() },
    navigate,
  }));

  return { ...rendered, api, navigate };
}

describe('ConnectionsPage', () => {
  afterEach(() => cleanup());

  it('frames connections as a readiness control surface', async () => {
    renderConnectionsPage();

    await screen.findByText('Connections');
    expect(screen.getByText('Connected surfaces')).toBeTruthy();
    expect(screen.getByText('Where Solden works')).toBeTruthy();
    expect(screen.getByText('Embedded app available')).toBeTruthy();
    expect(screen.getByText('API connection available')).toBeTruthy();
    expect(screen.getByText('Linked to QuickBooks bills')).toBeTruthy();
    expect(screen.getAllByText('What users can do').length).toBeGreaterThan(0);
    expect(screen.queryByText('Provider-neutral ERP memory API')).toBeNull();
    expect(screen.getByText('Connection health')).toBeTruthy();
    expect(screen.getByText('Setup order')).toBeTruthy();
    expect(screen.getByText('Inbox')).toBeTruthy();
    expect(screen.getByText('Approvals')).toBeTruthy();
    expect(screen.getAllByText('ERP').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/NetSuite/).length).toBeGreaterThan(0);
    expect(screen.getByText('Admin access')).toBeTruthy();
    expect(screen.getByLabelText('Approval channel')).toBeTruthy();
    expect(screen.queryByText(/FEATURE_/)).toBeNull();
    expect(screen.queryByText(/api\/worker\/beat/)).toBeNull();
    expect(screen.queryByText('Setup and reconnects live here')).toBeNull();
    expect(screen.queryByText('At a glance')).toBeNull();
  });

  it('paginates outgoing webhooks instead of rendering an unbounded stack', async () => {
    renderConnectionsPage();

    await screen.findByText('https://hooks.example.com/1');
    expect(screen.getByText('https://hooks.example.com/5')).toBeTruthy();
    expect(screen.queryByText('https://hooks.example.com/6')).toBeNull();
    expect(screen.getByText('Page 1 of 2 · 5 of 6 webhooks shown')).toBeTruthy();

    fireEvent.click(screen.getByLabelText('Next webhook page'));

    await waitFor(() => {
      expect(screen.getByText('https://hooks.example.com/6')).toBeTruthy();
    });
    expect(screen.queryByText('https://hooks.example.com/1')).toBeNull();
    expect(screen.getByText('Page 2 of 2 · 1 of 6 webhooks shown')).toBeTruthy();

    fireEvent.click(screen.getByLabelText('Previous webhook page'));

    await waitFor(() => {
      expect(screen.getByText('https://hooks.example.com/1')).toBeTruthy();
    });
    expect(screen.queryByText('https://hooks.example.com/6')).toBeNull();
  });

  it('opens the workspace status page instead of the raw health probe', async () => {
    const { navigate } = renderConnectionsPage();

    fireEvent.click(await screen.findByText('Open system status'));

    expect(navigate).toHaveBeenCalledWith('/status');
    expect(navigate).not.toHaveBeenCalledWith('/health');
  });
});
