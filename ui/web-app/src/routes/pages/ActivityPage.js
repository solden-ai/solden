/**
 * Activity page.
 *
 * The dedicated /activity route. Renders the same agent activity
 * ribbon shown on workspace Home, but taller (last ~50 events) and
 * with the ribbon as the page itself rather than one panel of many.
 *
 * Replaces the earlier AP-shaped stream. This is the full cross-work
 * log for the workspace: what moved, where it moved, and through
 * which surface. Home owns the compact control-center stats; Activity
 * owns the high-signal event trail.
 */
import { useEffect, useMemo, useState } from 'preact/hooks';
import { html } from '../../utils/htm.js';
import { useAction } from '../route-helpers.js';
import { AgentActivityRibbon } from '../../components/AgentActivityRibbon.js';
import { formatRelative } from '../../utils/formatters.js';

const ACTIVITY_LIMIT = 50;

export default function ActivityPage({ api, orgId, onRefresh, navigate }) {
  const [state, setState] = useState({ status: 'loading', data: null, error: null });
  const [liveActivity, setLiveActivity] = useState(null);

  // Initial fetch from the same endpoint Home uses, with a wider limit.
  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading', data: null, error: null });
    api(`/api/workspace/dashboard/recent-activity?limit=${ACTIVITY_LIMIT}`)
      .then((data) => { if (!cancelled) setState({ status: 'ready', data, error: null }); })
      .catch((err) => { if (!cancelled) setState({ status: 'error', data: null, error: err?.message || 'load_failed' }); });
    return () => { cancelled = true; };
  }, [api, orgId, onRefresh]);

  // SSE for live frames. Same stream Home subscribes to; we only
  // care about the 'activity' frame type here.
  useEffect(() => {
    if (typeof EventSource === 'undefined') return undefined;
    const source = new EventSource('/api/workspace/dashboard/stream', { withCredentials: true });
    source.onmessage = (event) => {
      try {
        const frame = JSON.parse(event.data);
        if (frame?.type === 'activity' && frame.data) setLiveActivity(frame.data);
      } catch { /* ignore bad frame */ }
    };
    source.onerror = () => { if (source.readyState === 2) source.close(); };
    return () => source.close();
  }, [orgId]);

  const items = (liveActivity?.items)
    || (Array.isArray(state.data?.items) ? state.data.items : []);
  const summary = useMemo(() => summarizeActivity(items), [items]);

  const [refresh, refreshing] = useAction(onRefresh);

  return html`
    <div class="cl-activity-page">
      <header class="cl-activity-page-head">
        <div>
          <h1 class="cl-activity-page-title">Activity stream</h1>
          <p class="cl-activity-page-sub">Every agent and operator action across work types and connected surfaces.</p>
        </div>
        <div class="cl-activity-page-actions">
          <button class="btn-secondary btn-sm" onClick=${refresh} disabled=${refreshing}>
            ${refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
          <button class="btn-primary btn-sm" onClick=${() => navigate?.('/exceptions')}>
            Review exceptions
          </button>
        </div>
      </header>

      <section class="cl-activity-summary" aria-label="Activity stream summary">
        <${ActivitySummaryCell}
          label="Actions"
          value=${items.length}
          sub=${liveActivity ? 'Live stream connected' : `Last ${ACTIVITY_LIMIT} events`}
          tone="brand"
        />
        <${ActivitySummaryCell}
          label="Work types"
          value=${summary.workTypeCount || '—'}
          sub=${summary.workTypeLabel || 'No work types yet'}
        />
        <${ActivitySummaryCell}
          label="Surfaces"
          value=${summary.surfaceCount || '—'}
          sub=${summary.surfaceLabel || 'No surfaces yet'}
        />
        <${ActivitySummaryCell}
          label="Last action"
          value=${summary.lastAction}
          sub=${summary.lastSubject}
        />
      </section>

      <${AgentActivityRibbon}
        state=${state}
        items=${items}
        live=${!!liveActivity}
        navigate=${navigate}
        title="Activity stream"
        emptyTitle="Nothing has happened yet."
        emptyDescription="As Solden watches inboxes, chat approvals, ERP events, and work-type records, every material action lands here."
      />
    </div>
  `;
}

function ActivitySummaryCell({ label, value, sub, tone = 'neutral' }) {
  return html`
    <div class=${`cl-activity-summary-cell cl-activity-summary-cell-${tone}`}>
      <div class="cl-activity-summary-label">${label}</div>
      <div class="cl-activity-summary-value">${value}</div>
      <div class="cl-activity-summary-sub">${sub}</div>
    </div>
  `;
}

function summarizeActivity(items = []) {
  const workTypes = new Set();
  const surfaces = new Set();

  for (const item of items) {
    const workType = humanizeWorkType(item?.box_type);
    if (workType) workTypes.add(workType);
    const surface = humanizeSurface(item?.surface);
    if (surface) surfaces.add(surface);
  }

  const first = items[0] || {};
  return {
    workTypeCount: workTypes.size,
    workTypeLabel: summarizeSet(workTypes),
    surfaceCount: surfaces.size,
    surfaceLabel: summarizeSet(surfaces),
    lastAction: first.ts ? formatRelative(first.ts) : '—',
    lastSubject: first.subject || 'No actions recorded yet',
  };
}

function summarizeSet(values) {
  const list = Array.from(values);
  if (list.length <= 2) return list.join(', ');
  return `${list.slice(0, 2).join(', ')} +${list.length - 2}`;
}

function humanizeWorkType(value) {
  const token = String(value || '').trim().toLowerCase();
  if (!token) return '';
  const labels = {
    ap_item: 'Accounts Payable',
    purchase_order: 'Procurement',
    vendor_onboarding_session: 'Vendor Onboarding',
    bank_match: 'Bank Reconciliation',
  };
  return labels[token] || token.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function humanizeSurface(value) {
  const token = String(value || '').trim().toLowerCase();
  if (!token || token === 'agent') return '';
  const labels = {
    gmail: 'Gmail',
    slack: 'Slack',
    teams: 'Teams',
    netsuite: 'NetSuite',
    sap: 'SAP',
    xero: 'Xero',
    quickbooks: 'QuickBooks',
    sage_intacct: 'Sage Intacct',
    sage_business_cloud: 'Sage Business Cloud',
  };
  return labels[token] || token.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
