// Ask Solden — org-wide Q&A over the earned memory, on the Home page.
//
// One input box over everything the memory layer has captured: records and
// their decision ledgers, the dimension graph, vendors, standing rules,
// exceptions. Answers come back with [sN] citations rendered as chips that
// deep-link to the cited surface; the backend's hard guard means an answer
// with no citations is replaced server-side by a deterministic summary.
//
// History is client-held (last 6 turns) and treated as UNTRUSTED by the
// backend — it is context, never a source.
import { useEffect, useRef, useState } from 'preact/hooks';
import { useLocation } from 'wouter-preact';
import { html } from '../../utils/htm.js';
import { api } from '../../api/client.js';
import { accountPayableRecordPath } from '../../utils/record-route.js';

const LINK_ROUTES = {
  rules: '/rules',
  exceptions: '/exceptions',
  audit: '/audit',
};

function chipTarget(link) {
  if (!link || link.kind === 'none') return null;
  if (link.kind === 'record' && link.ref) return accountPayableRecordPath(link.ref);
  if (link.kind === 'vendor' && link.ref) return `/vendors/${encodeURIComponent(link.ref)}`;
  return LINK_ROUTES[link.kind] || null;
}

// Split "Approved per the true-up. [s1] More text [s2]" into text + chip parts.
function renderAnswer(answer, sources, navigate) {
  const byId = Object.fromEntries((sources || []).map((s) => [s.id, s]));
  const parts = String(answer || '').split(/(\[s\d+\])/g);
  return parts.map((part) => {
    const m = /^\[(s\d+)\]$/.exec(part);
    if (!m) return part;
    const source = byId[m[1]];
    if (!source) return part;
    const target = chipTarget(source.link);
    return html`<button
      class="cl-home-ask-chip ${target ? '' : 'is-inert'}"
      type="button"
      title=${source.summary}
      data-source-id=${source.id}
      onClick=${target ? () => navigate(target) : undefined}
    >${source.id}</button>`;
  });
}

export default function AskSoldenPanel() {
  const [, navigate] = useLocation();
  const [suggestions, setSuggestions] = useState([]);
  const [question, setQuestion] = useState('');
  const [turns, setTurns] = useState([]); // [{q, a, sources, fallback}]
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  useEffect(() => {
    // Silent: the panel renders fine without starter chips.
    api('/api/workspace/ask/suggestions', { silent: true })
      .then((resp) => setSuggestions(Array.isArray(resp?.suggestions) ? resp.suggestions : []))
      .catch(() => setSuggestions([]));
  }, []);

  const submit = async (text) => {
    const q = String(text || '').trim();
    if (!q || loading) return;
    setLoading(true);
    setError(null);
    try {
      const history = turns.slice(-6).map((t) => ({
        q: String(t.q).slice(0, 2000),
        a: String(t.a).slice(0, 2000),
      }));
      const resp = await api('/api/workspace/ask', {
        method: 'POST',
        body: JSON.stringify({ question: q, history: history.length ? history : undefined }),
      });
      setTurns((prev) => [...prev.slice(-5), {
        q,
        a: resp?.answer || '',
        sources: resp?.sources || [],
        fallback: Boolean(resp?.fallback),
      }]);
      setQuestion('');
    } catch (err) {
      const detail = err?.payload?.detail;
      if (err?.status === 429 && detail?.reset_after_seconds) {
        const hours = Math.max(1, Math.round(detail.reset_after_seconds / 3600));
        setError(`Daily question limit reached — resets in ~${hours}h.`);
      } else {
        setError('Could not reach Solden — try again.');
      }
    } finally {
      setLoading(false);
      if (inputRef.current) inputRef.current.focus();
    }
  };

  return html`
    <section class="cl-home-ask" aria-label="Ask Solden">
      <header class="cl-home-ask-head">
        <h2>Ask Solden</h2>
        <p>Questions answered only from the record — every claim cites its source.</p>
        ${turns.length > 0 ? html`
          <button class="cl-home-ask-clear" type="button" onClick=${() => setTurns([])}>
            Clear
          </button>
        ` : ''}
      </header>

      ${turns.length > 0 ? html`
        <div class="cl-home-ask-thread">
          ${turns.map((turn) => html`
            <div class="cl-home-ask-turn">
              <div class="cl-home-ask-q">${turn.q}</div>
              <div class="cl-home-ask-a">
                ${renderAnswer(turn.a, turn.sources, navigate)}
                ${turn.fallback ? html`
                  <span class="cl-home-ask-fallback">deterministic summary</span>
                ` : ''}
              </div>
            </div>
          `)}
        </div>
      ` : ''}

      ${turns.length === 0 && suggestions.length > 0 ? html`
        <div class="cl-home-ask-suggestions">
          ${suggestions.map((s) => html`
            <button class="cl-home-ask-suggestion" type="button"
                    disabled=${loading} onClick=${() => submit(s)}>${s}</button>
          `)}
        </div>
      ` : ''}

      <form class="cl-home-ask-form" onSubmit=${(e) => { e.preventDefault(); submit(question); }}>
        <input
          ref=${inputRef}
          type="text"
          placeholder=${'Ask about a record, vendor, cost center, or policy…'}
          value=${question}
          disabled=${loading}
          maxlength="1000"
          onInput=${(e) => setQuestion(e.target.value)}
        />
        <button class="cl-home-btn cl-home-btn-primary" type="submit"
                disabled=${loading || !question.trim()}>
          ${loading ? 'Checking the record…' : 'Ask'}
        </button>
      </form>

      ${error ? html`<p class="cl-home-ask-error" role="alert">${error}</p>` : ''}
    </section>
  `;
}
