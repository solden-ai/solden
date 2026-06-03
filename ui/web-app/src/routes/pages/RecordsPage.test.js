import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/preact';
import RecordsPage from './RecordsPage.js';

function recordsCallUrls(api) {
  return api.mock.calls
    .map(([path]) => String(path || ''))
    .filter((path) => path.startsWith('/api/workspace/records'));
}

function parseUrl(path) {
  return new URL(path, 'http://solden.test');
}

function item(id, vendor = `Vendor ${id}`) {
  return {
    id,
    vendor_name: vendor,
    invoice_number: `INV-${id}`,
    amount: 1200,
    currency: 'USD',
    state: 'needs_approval',
    created_at: '2026-06-01T10:00:00Z',
    updated_at: '2026-06-01T10:00:00Z',
  };
}

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
      const url = parseUrl(recordsCallUrls(api)[0]);
      expect(url.searchParams.get('organization_id')).toBe('org-test');
      expect(url.searchParams.get('limit')).toBe('50');
      expect(url.searchParams.get('offset')).toBe('0');
      expect(url.searchParams.get('active_slice_id')).toBe('all_open');
      expect(url.searchParams.get('sort_col')).toBe('queue_age');
      expect(url.searchParams.get('sort_dir')).toBe('desc');
    });
  });

  it('pages through AP records with server offsets', async () => {
    const firstPage = Array.from({ length: 50 }, (_, index) => item(`A-${index + 1}`));
    const secondPage = Array.from({ length: 25 }, (_, index) => item(`B-${index + 1}`));
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/records')) {
        const url = parseUrl(path);
        const offset = Number(url.searchParams.get('offset') || 0);
        return {
          items: offset === 50 ? secondPage : firstPage,
          total: 75,
          limit: 50,
          offset,
          has_more: offset === 0,
          slice_counts: { all: 75, all_open: 75, blocked_exception: 0, overdue: 0 },
        };
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

    await screen.findByText('1-50');
    fireEvent.click(screen.getByRole('button', { name: 'Next records page' }));

    await screen.findByText('51-75');
    const offsets = recordsCallUrls(api).map((path) => parseUrl(path).searchParams.get('offset'));
    expect(offsets).toContain('0');
    expect(offsets).toContain('50');
  });

  it('sends search to the workspace records API', async () => {
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/records')) {
        return {
          items: [],
          total: 0,
          limit: 50,
          offset: Number(parseUrl(path).searchParams.get('offset') || 0),
          has_more: false,
          slice_counts: { all: 0, all_open: 0, blocked_exception: 0, overdue: 0 },
        };
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

    const input = await screen.findByLabelText('Search records');
    fireEvent.input(input, { target: { value: 'Acme' } });

    await waitFor(() => {
      const matching = recordsCallUrls(api).some((path) => {
        const url = parseUrl(path);
        return url.searchParams.get('q') === 'Acme' && url.searchParams.get('offset') === '0';
      });
      expect(matching).toBe(true);
    });
  });
});
