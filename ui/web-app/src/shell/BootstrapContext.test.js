import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, render, screen, waitFor } from '@testing-library/preact';
import { api } from '../api/client.js';
import { BootstrapProvider, useBootstrap, workspaceFaviconBadgeCount } from './BootstrapContext.js';
import { setFaviconBadge } from '../lib/faviconBadge.js';

vi.mock('../api/client.js', () => ({
  api: vi.fn(),
}));

vi.mock('../lib/faviconBadge.js', () => ({
  setFaviconBadge: vi.fn(),
}));

function Probe() {
  const bootstrap = useBootstrap();
  return h('div', {}, `Loaded ${bootstrap.organization.id}`);
}

describe('BootstrapProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders children after a valid workspace bootstrap loads', async () => {
    api.mockResolvedValue({
      organization: { id: 'org-test', name: 'Solden Test' },
      current_user: { email: 'ops@soldenai.com', organization_id: 'org-test' },
    });

    render(h(BootstrapProvider, {}, h(Probe, {})));

    await waitFor(() => {
      expect(screen.getByText('Loaded org-test')).toBeTruthy();
    });
  });

  it('badges the favicon from the canonical dashboard payload', async () => {
    api.mockResolvedValue({
      organization: { id: 'org-test', name: 'Solden Test' },
      current_user: { email: 'ops@soldenai.com', organization_id: 'org-test' },
      dashboard: { pending_approval: 7 },
    });

    render(h(BootstrapProvider, {}, h(Probe, {})));

    await waitFor(() => {
      expect(screen.getByText('Loaded org-test')).toBeTruthy();
    });
    await waitFor(() => {
      expect(setFaviconBadge).toHaveBeenLastCalledWith(7);
    });
  });

  it('stops the shell when bootstrap is missing an organization', async () => {
    api.mockResolvedValue({
      organization: {},
      current_user: { email: 'ops@soldenai.com' },
    });

    render(h(BootstrapProvider, {}, h(Probe, {})));

    await waitFor(() => {
      expect(screen.getByText("We couldn't load your workspace.")).toBeTruthy();
    });
    expect(screen.queryByText(/Loaded/)).toBeNull();
  });

  it('stops the shell when bootstrap cannot be loaded', async () => {
    api.mockRejectedValue(new Error('backend unavailable'));

    render(h(BootstrapProvider, {}, h(Probe, {})));

    await waitFor(() => {
      expect(screen.getByText("We couldn't load your workspace.")).toBeTruthy();
    });
    expect(screen.queryByText(/Loaded/)).toBeNull();
  });
});

describe('workspaceFaviconBadgeCount', () => {
  it('uses pending approval from the canonical dashboard payload', () => {
    expect(workspaceFaviconBadgeCount({ dashboard_stats: { pending_approval: 7 } })).toBe(7);
  });

  it('falls back only when pending approval is absent', () => {
    expect(workspaceFaviconBadgeCount({ dashboard_stats: { awaiting_approval: 4 } })).toBe(4);
    expect(workspaceFaviconBadgeCount({ dashboard_stats: { pending_approval: 0, awaiting_approval: 4 } })).toBe(0);
  });
});
