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
    owner_email: 'jane.finance@acme.com',
    next_action: 'approve_or_reject',
    erp_status: 'connected',
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
      expect(url.searchParams.get('limit')).toBe('15');
      expect(url.searchParams.get('offset')).toBe('0');
      expect(url.searchParams.get('active_slice_id')).toBe('all_open');
      expect(url.searchParams.get('sort_col')).toBe('queue_age');
      expect(url.searchParams.get('sort_dir')).toBe('desc');
    });
  });

  it('pages through AP records with server offsets', async () => {
    const firstPage = Array.from({ length: 15 }, (_, index) => item(`A-${index + 1}`));
    const secondPage = Array.from({ length: 15 }, (_, index) => item(`B-${index + 1}`));
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/records')) {
        const url = parseUrl(path);
        const offset = Number(url.searchParams.get('offset') || 0);
        return {
          items: offset === 15 ? secondPage : firstPage,
          total: 46,
          limit: 15,
          offset,
          has_more: offset === 0,
          slice_counts: { all: 46, all_open: 46, blocked_exception: 0, overdue: 0 },
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

    await screen.findByText('1-15');
    fireEvent.click(screen.getByRole('button', { name: 'Next records page' }));

    await screen.findByText('16-30');
    const offsets = recordsCallUrls(api).map((path) => parseUrl(path).searchParams.get('offset'));
    expect(offsets).toContain('0');
    expect(offsets).toContain('15');
  });

  it('sends search to the workspace records API', async () => {
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/records')) {
        return {
          items: [],
          total: 0,
          limit: 15,
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

  it('renders owner, next step, blocker, age, due, and ERP status in rows', async () => {
    const row = {
      ...item('ERP-1', 'Acme Recovery'),
      state: 'failed_post',
      next_action: 'retry_post',
      erp_status: 'failed',
      pipeline_blockers: [{ kind: 'erp', type: 'posting_failed', title: 'ERP issue' }],
    };
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/records')) {
        return {
          items: [row],
          total: 1,
          limit: 15,
          offset: 0,
          has_more: false,
          slice_counts: { all: 1, all_open: 1, blocked_exception: 1, overdue: 0 },
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

    await screen.findByText('Acme Recovery');
    expect(screen.getByText('jane finance')).toBeTruthy();
    expect(screen.getByText('Recover ERP post')).toBeTruthy();
    expect(screen.getByText('ERP not connected')).toBeTruthy();
    expect(screen.getByText('Failed')).toBeTruthy();
  });

  it('applies operational starter views through server query params', async () => {
    const api = vi.fn(async (path) => {
      if (String(path).startsWith('/api/workspace/records')) {
        return {
          items: [],
          total: 0,
          limit: 15,
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

    await screen.findByText('No records');
    fireEvent.click(screen.getByRole('button', { name: /^Views/ }));
    fireEvent.click(screen.getByText('High-value blocked'));

    await waitFor(() => {
      const matching = recordsCallUrls(api).some((path) => {
        const url = parseUrl(path);
        return (
          url.searchParams.get('active_slice_id') === 'blocked_exception'
          && url.searchParams.get('amount') === 'over_10k'
          && url.searchParams.get('sort_col') === 'amount'
          && url.searchParams.get('sort_dir') === 'desc'
        );
      });
      expect(matching).toBe(true);
    });
  });
});
