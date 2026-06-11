import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/preact';
import { html } from '../../utils/htm.js';
import AskSoldenPanel from './AskSoldenPanel.js';
import { api } from '../../api/client.js';

const navigateMock = vi.fn();
vi.mock('wouter-preact', () => ({ useLocation: () => ['/', navigateMock] }));
vi.mock('../../api/client.js', () => ({ api: vi.fn() }));

function mockApi({ suggestions = ['What\'s blocked right now and why?'], askResponse, askError } = {}) {
  api.mockImplementation(async (path, opts = {}) => {
    const url = String(path || '');
    if (url.startsWith('/api/workspace/ask/suggestions')) {
      return { suggestions };
    }
    if (url === '/api/workspace/ask' && (opts.method || '') === 'POST') {
      if (askError) throw askError;
      return askResponse;
    }
    throw new Error(`unmocked: ${url}`);
  });
}

const CITED_RESPONSE = {
  answer: 'Approved per the quarterly true-up Dana signed off on. [s1]',
  sources: [{
    id: 's1', type: 'record',
    summary: 'Record INV-777: Northwind Traders',
    link: { kind: 'record', ref: 'AP-777' },
  }, {
    id: 's2', type: 'dimension',
    summary: 'Dimension cost_center 402',
    link: { kind: 'none', ref: null },
  }],
  retrieval: { matched_entities: [] },
  model: 'claude-sonnet-test', latency_ms: 42, fallback: false,
};

describe('AskSoldenPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders suggestion chips and submits on chip click', async () => {
    mockApi({ askResponse: CITED_RESPONSE });
    render(html`<${AskSoldenPanel} />`);
    const chip = await screen.findByText("What's blocked right now and why?");
    fireEvent.click(chip);
    await waitFor(() => {
      expect(api).toHaveBeenCalledWith('/api/workspace/ask', expect.objectContaining({ method: 'POST' }));
    });
    await screen.findByText(/Dana signed off/);
  });

  it('renders citation chips; record chip navigates, dimension chip is inert', async () => {
    mockApi({ askResponse: CITED_RESPONSE });
    render(html`<${AskSoldenPanel} />`);
    const input = await screen.findByPlaceholderText(/Ask about a record/);
    fireEvent.input(input, { target: { value: 'Why did we approve INV-777?' } });
    fireEvent.submit(input.closest('form'));
    const recordChip = await screen.findByText('s1');
    fireEvent.click(recordChip);
    expect(navigateMock).toHaveBeenCalledWith(expect.stringContaining('AP-777'));
    // Hard guard on the UI side of the contract: kind "none" renders inert.
    const dimChip = screen.queryByText('s2');
    if (dimChip) {
      navigateMock.mockClear();
      fireEvent.click(dimChip);
      expect(navigateMock).not.toHaveBeenCalled();
    }
  });

  it('blocks double-submit while a question is in flight', async () => {
    let resolveAsk;
    api.mockImplementation(async (path, opts = {}) => {
      const url = String(path || '');
      if (url.startsWith('/api/workspace/ask/suggestions')) return { suggestions: [] };
      if (url === '/api/workspace/ask') {
        return new Promise((resolve) => { resolveAsk = () => resolve(CITED_RESPONSE); });
      }
      throw new Error(`unmocked: ${url}`);
    });
    render(html`<${AskSoldenPanel} />`);
    const input = await screen.findByPlaceholderText(/Ask about a record/);
    fireEvent.input(input, { target: { value: 'first question here' } });
    const form = input.closest('form');
    fireEvent.submit(form);
    fireEvent.submit(form);
    fireEvent.submit(form);
    const askCalls = api.mock.calls.filter(([p]) => p === '/api/workspace/ask');
    expect(askCalls.length).toBe(1);
    resolveAsk();
  });

  it('renders the quota message on 429 with reset time', async () => {
    const err = new Error('quota');
    err.status = 429;
    err.payload = { detail: { message: 'Daily Ask Solden questions quota exceeded', reset_after_seconds: 7200 } };
    mockApi({ askError: err });
    render(html`<${AskSoldenPanel} />`);
    const input = await screen.findByPlaceholderText(/Ask about a record/);
    fireEvent.input(input, { target: { value: 'anything at all' } });
    fireEvent.submit(input.closest('form'));
    await screen.findByText(/Daily question limit reached — resets in ~2h/);
  });

  it('shows the deterministic-summary hint on fallback answers', async () => {
    mockApi({
      askResponse: {
        ...CITED_RESPONSE,
        answer: 'Record INV-777: Northwind Traders. [s1] (Deterministic summary…)',
        fallback: true, model: null,
      },
    });
    render(html`<${AskSoldenPanel} />`);
    const input = await screen.findByPlaceholderText(/Ask about a record/);
    fireEvent.input(input, { target: { value: 'Why did we approve INV-777?' } });
    fireEvent.submit(input.closest('form'));
    await screen.findByText('deterministic summary');
  });

  it('still renders the input when the suggestions fetch fails', async () => {
    api.mockImplementation(async (path) => {
      if (String(path).startsWith('/api/workspace/ask/suggestions')) {
        throw new Error('boom');
      }
      throw new Error('unmocked');
    });
    render(html`<${AskSoldenPanel} />`);
    await screen.findByPlaceholderText(/Ask about a record/);
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
