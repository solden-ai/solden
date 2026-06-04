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
      { name: 'erp', status: 'disconnected', connected: false, erp_type: 'quickbooks' },
      { name: 'slack', status: 'connected', connected: true, approval_channel: '#approvals' },
      { name: 'teams', status: 'disabled_in_v1', connected: false },
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
    if (route === '/api/workspace/webhooks') {
      return { webhooks };
    }
    return {};
  });

  const rendered = render(h(ConnectionsPage, {
    bootstrap: makeBootstrap(),
    api,
    toast: vi.fn(),
    orgId: 'org-test',
    onRefresh: vi.fn(),
    oauthBridge: { open: vi.fn() },
    navigate: vi.fn(),
  }));

  return { ...rendered, api };
}

describe('ConnectionsPage', () => {
  afterEach(() => cleanup());

  it('frames connections as a readiness control surface', async () => {
    renderConnectionsPage();

    await screen.findByText('Connections');
    expect(screen.getByText('Integration matrix')).toBeTruthy();
    expect(screen.getByText('Inbox')).toBeTruthy();
    expect(screen.getByText('Approvals')).toBeTruthy();
    expect(screen.getAllByText('ERP').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Access').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('Approval channel')).toBeTruthy();
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
});
