import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, render, waitFor } from '@testing-library/preact';
import RecordsPage from './RecordsPage.js';

describe('RecordsPage', () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('loads AP records from the workspace records endpoint', async () => {
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/records')) {
        return { items: [] };
      }
      return {};
    });

    render(h(RecordsPage, {
      api,
      bootstrap: {},
      orgId: 'org-test',
      userEmail: 'ops@soldenai.com',
      toast: () => {},
      navigate: () => {},
    }));

    await waitFor(() => {
      expect(api.mock.calls.some(
        ([path]) => path === '/api/workspace/records?organization_id=org-test&limit=500',
      )).toBe(true);
    });
  });
});
