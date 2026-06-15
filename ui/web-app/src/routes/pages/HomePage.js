import { useEffect, useMemo, useState } from 'preact/hooks';
// `api` + `html` are imported below; the ImplementationChecklist
// component uses both. No new imports needed beyond the existing
// header — pre-existing.
import { useLocation } from 'wouter-preact';
import { html } from '../../utils/htm.js';
import { api } from '../../api/client.js';
import { useBootstrap, useOrgId } from '../../shell/BootstrapContext.js';
import { formatAmount, formatRelative, displayOrgName } from '../../utils/formatters.js';
import { accountsPayablePath, accountPayableRecordPath } from '../../utils/record-route.js';
import AskSoldenPanel from './AskSoldenPanel.js';

/**
 * Workspace Home — work-in-progress control center.
 *
 * DESIGN.md §Workspace Surface Pattern: this is the leader's daily
 * landing page. It shows live work in progress —
 * what the agent is doing across surfaces right now, what needs
 * judgment, what just shipped to ERP. Reference hierarchy: Linear
 * (real-time activity, dense lists), Vercel deployments (live stream
 * is the page), Datadog overview (professional density), Modal jobs
 * (running work primary). NOT BILL.com / Ramp / Mixmax.
 *
 * Page order:
 *   1. Welcome header + primary actions
 *   2. Onboarding banner (only if onboarding incomplete)
 *   3. Implementation checklist (only if setup incomplete)
 *   4. Live work-in-progress console: work types, selected open work,
 *      and operational context with evidence/activity
 *   5. Compact stat strip (4 dense tiles, live-pulse indicators)
 *   6. Approver workload
 *   7. System status footer
 *
 * Each panel fetches independently; one slow endpoint never gates
 * the rest. SSE keeps stats / workload / activity live within ~15s.
 */

// formatRelative lives in utils/formatters.js so the shared
// AgentActivityRibbon component can reuse it. Kept as a local alias so
// the existing call sites in this file (status footer, agent last
// action) don't churn.
const fmtRelative = formatRelative;

function fmtCurrency(amount, currency) {
  // Don't default to USD when currency is missing — that misrepresents
  // non-USD records (a GHS invoice rendered as "USD 5,000.00" is worse
  // than "5,000.00" with no code). The org's functional currency is
  // the right fallback if we ever need one, not USD.
  return formatAmount(amount, currency);
}

// Each panel resolves on its own timer; stuck panels fall through
// to a muted "Couldn't load — retry" instead of sitting on Loading.
function useEndpoint(path, deps = []) {
  const [state, setState] = useState({ status: 'loading', data: null, error: null });
  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading', data: null, error: null });
    api(path, { silent: true })
      .then((data) => { if (!cancelled) setState({ status: 'ready', data, error: null }); })
      .catch((err) => { if (!cancelled) setState({ status: 'error', data: null, error: err?.message || 'load_failed' }); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export function HomePage() {
  const bootstrap = useBootstrap();
  const orgId = useOrgId();
  const [, navigate] = useLocation();

  const orgQuery = `organization_id=${encodeURIComponent(orgId)}`;
  const metrics = useEndpoint(`/api/ap/items/metrics/aggregation?${orgQuery}&vendor_limit=5`, [orgId]);
  const records = useEndpoint(`/api/workspace/records?${orgQuery}&active_slice_id=all_open&limit=8&sort_col=queue_age&sort_dir=desc&include_memory=true`, [orgId]);
  const workload = useEndpoint('/api/workspace/dashboard/approver-workload', [orgId]);
  const exceptions = useEndpoint('/api/workspace/exceptions?limit=10', [orgId]);
  const exceptionStats = useEndpoint('/api/workspace/exceptions/stats', [orgId]);
  const activity = useEndpoint('/api/workspace/dashboard/recent-activity?limit=20', [orgId]);

  // SSE-pushed live updates: stats, workload, activity. Keeps the
  // control center honest within ~15s of the agent acting (per
  // Module 1 spec line 92, 30s ceiling).
  const [liveDashboard, setLiveDashboard] = useState(null);
  const [liveActivity, setLiveActivity] = useState(null);
  const [liveWorkload, setLiveWorkload] = useState(null);
  const [streamPulse, setStreamPulse] = useState(0);  // increments on every frame; powers the live-pulse dot
  const [selectedWorkId, setSelectedWorkId] = useState(null);
  const [workSearch, setWorkSearch] = useState('');

  useEffect(() => {
    if (typeof EventSource === 'undefined') return undefined;
    const source = new EventSource('/api/workspace/dashboard/stream', { withCredentials: true });
    source.onmessage = (event) => {
      try {
        const frame = JSON.parse(event.data);
        if (!frame?.type) return;
        if (frame.type === 'stats' && frame.data)    setLiveDashboard(frame.data);
        if (frame.type === 'workload' && frame.data) setLiveWorkload(frame.data);
        if (frame.type === 'activity' && frame.data) setLiveActivity(frame.data);
        setStreamPulse((p) => (p + 1) % 1_000_000);
      } catch { /* ignore bad frame */ }
    };
    source.onerror = () => { if (source.readyState === 2) source.close(); };
    return () => source.close();
  }, [orgId]);

  const orgName = displayOrgName(bootstrap?.organization?.name) || 'your workspace';
  const onboardingPending = bootstrap?.onboarding && bootstrap.onboarding.completed === false;

  const m = metrics.data?.metrics || metrics.data || {};

  const dash = liveDashboard || bootstrap?.dashboard_stats || bootstrap?.dashboard || {};
  const inFlight = Number(dash.in_flight || 0);
  const awaitingApproval = Number(dash.pending_approval || 0);
  const processedWeek = Number(dash.processed_this_week || 0);
  const exceptionCount = Number(
    exceptionStats.data?.total_unresolved
    ?? exceptions.data?.count
    ?? m.exceptions_count
    ?? m.exception_count
    ?? 0,
  );

  const exceptionItems = Array.isArray(exceptions.data?.items) ? exceptions.data.items : [];
  const recordItems = Array.isArray(records.data?.items) ? records.data.items : [];
  const recordsTotal = safeMetric(records.data?.total) ?? recordItems.length;

  // Activity ribbon: live SSE feed wins over the initial HTTP fetch.
  const activityItems = (liveActivity?.items)
    || (Array.isArray(activity.data?.items) ? activity.data.items : []);

  // Workload: live SSE wins.
  const workloadState = liveWorkload
    ? { status: 'ready', data: liveWorkload, error: null }
    : workload;
  const visibleWorkItems = useMemo(
    () => filterWorkItems(recordItems, workSearch),
    [recordItems, workSearch],
  );
  const firstVisibleWorkId = visibleWorkItems[0]?.id || recordItems[0]?.id || '';
  const selectedWorkItem = visibleWorkItems.find((item) => String(item.id || '') === String(selectedWorkId || ''))
    || recordItems.find((item) => String(item.id || '') === String(selectedWorkId || ''))
    || visibleWorkItems[0]
    || recordItems[0]
    || null;

  useEffect(() => {
    if (!firstVisibleWorkId) {
      if (selectedWorkId) setSelectedWorkId(null);
      return;
    }
    const selectedStillVisible = visibleWorkItems.some(
      (item) => String(item.id || '') === String(selectedWorkId || ''),
    );
    if (!selectedStillVisible) setSelectedWorkId(firstVisibleWorkId);
  }, [firstVisibleWorkId, selectedWorkId, visibleWorkItems]);

  const integrations = Array.isArray(bootstrap?.integrations) ? bootstrap.integrations : [];
  const agentLastAction = bootstrap?.dashboard_stats?.last_action_at
    || bootstrap?.dashboard?.last_action_at
    || dash.last_action_at
    || activityItems[0]?.ts
    || null;

  const now = useMemo(() => new Date(), []);
  const today = now.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });

  return html`
    <div class="cl-home">
      <header class="cl-home-header">
        <div class="cl-home-headline">
          <div class="cl-home-eyebrow">${today}</div>
          <h1 class="cl-home-title">Operational memory</h1>
          <p class="cl-home-sub">
            ${orgName} · owners, blockers, proof, and decisions across work in progress.
          </p>
        </div>
        <div class="cl-home-actions">
          <button class="btn btn-secondary" onClick=${() => navigate('/activity')}>
            Open activity
          </button>
          <button class="btn btn-primary" onClick=${() => navigate('/exceptions')}>
            Review exceptions
          </button>
        </div>
      </header>

      ${onboardingPending
        ? html`
            <aside class="cl-home-onboarding-banner">
              <div>
                <strong>Setup is in progress.</strong> Complete onboarding to start routing work across your connected surfaces.
              </div>
              <button class="btn btn-primary" onClick=${() => navigate('/onboarding')}>
                Resume setup
              </button>
            </aside>
          `
        : null}

      <${ImplementationChecklist} orgId=${orgId} navigate=${navigate} />

      <${HomeLiveConsole}
        recordsState=${records}
        recordsTotal=${recordsTotal}
        workItems=${visibleWorkItems}
        selectedItem=${selectedWorkItem}
        selectedWorkId=${selectedWorkId}
        onSelect=${setSelectedWorkId}
        search=${workSearch}
        onSearch=${setWorkSearch}
        exceptionCount=${exceptionCount}
        exceptionItems=${exceptionItems}
        activityState=${activity}
        activityItems=${activityItems}
        live=${!!liveActivity || streamPulse > 0}
        navigate=${navigate}
      />

      <section class="cl-home-stat-strip" aria-label="Work in progress at a glance">
        <${StatTile}
          label="In flight"
          value=${inFlight}
          sub=${inFlight === 0 ? 'No work in progress' : 'Across open work states'}
          tone="brand"
          live=${streamPulse > 0}
          onClick=${() => navigate(accountsPayablePath())}
        />
        <${StatTile}
          label="Awaiting approval"
          value=${awaitingApproval}
          sub=${awaitingApproval === 0 ? 'No approval bottleneck' : 'Waiting in approval queues'}
          tone=${awaitingApproval > 0 ? 'pending' : 'good'}
          live=${streamPulse > 0}
          onClick=${() => navigate(accountsPayablePath('?scope=approvals'))}
        />
        <${StatTile}
          label="Processed this week"
          value=${processedWeek}
          sub="Last 7 days · posted or closed"
          tone="neutral"
          live=${streamPulse > 0}
        />
        <${StatTile}
          label="Agent exceptions"
          value=${exceptionCount}
          sub=${exceptionCount > 0 ? 'Need judgment' : 'Clean'}
          tone=${exceptionCount > 0 ? 'warn' : 'good'}
          live=${streamPulse > 0}
          onClick=${exceptionCount > 0 ? () => navigate('/exceptions') : undefined}
        />
      </section>

      <${AskSoldenPanel} />

      <${PolicyProposalsPanel} />

      <${ApproverWorkloadStrip} state=${workloadState} navigate=${navigate} />

      <${SystemStatusFooter}
        integrations=${integrations}
        agentLastAction=${agentLastAction}
        navigate=${navigate} />
    </div>
  `;
}


// ─── Implementation checklist (moved here from SettingsPage) ─────
//
// First-time admins land on Home. Onboarding tasks belong here, not
// buried at the bottom of Settings where most users will never scroll.
// The component hides itself entirely once every step is complete so
// it stops taking visual real estate from veteran admins.

function ImplementationChecklist({ orgId, navigate }) {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    if (!orgId) return undefined;
    let cancelled = false;
    api(
      `/api/workspace/implementation/status?organization_id=${encodeURIComponent(orgId)}`,
      { silent: true },
    )
      .then((data) => { if (!cancelled) setStatus(data); })
      .catch(() => { /* hide quietly on error */ });
    return () => { cancelled = true; };
  }, [orgId]);

  if (!status || !Array.isArray(status.steps) || status.all_complete) {
    return null;
  }
  const steps = status.steps;
  const completedCount = steps.filter((s) => s.completed).length;
  const total = steps.length;

  return html`
    <section class="cl-home-checklist" aria-label="Implementation checklist">
      <header class="cl-home-checklist-head">
        <div>
          <strong>Finish setting up Solden</strong>
          <span class="cl-home-checklist-progress muted small">
            ${completedCount} of ${total} done
          </span>
        </div>
        <button class="btn btn-secondary" onClick=${() => navigate('/settings')}>
          Open settings
        </button>
      </header>
      <ol class="cl-home-checklist-list">
        ${steps.map((step) => html`
          <li
            key=${step.id}
            class=${`cl-home-checklist-item ${step.completed ? 'is-done' : ''}`}>
            <span class="cl-home-checklist-dot" aria-hidden="true">
              ${step.completed ? '✓' : ''}
            </span>
            <div class="cl-home-checklist-copy">
              <div class="cl-home-checklist-name">${step.name}</div>
              <div class="muted small">${step.description}</div>
            </div>
          </li>
        `)}
      </ol>
    </section>
  `;
}


// ─── Compact stat tile (control-center idiom) ─────────────────────
//
// Smaller / denser than a Bill / Ramp KPI tile. Live-pulse dot in the
// corner indicates the SSE stream is connected. Tabular numerals.
// Click navigates to the relevant slice.

function StatTile({ label, value, sub, tone = 'neutral', live = false, onClick }) {
  const clickable = typeof onClick === 'function';
  return html`
    <div
      class=${`cl-home-stat cl-home-stat-${tone} ${clickable ? 'cl-home-stat-clickable' : ''}`}
      onClick=${clickable ? onClick : undefined}
      onKeyDown=${clickable ? (event) => activateOnKey(event, onClick) : undefined}
      role=${clickable ? 'button' : undefined}
      tabindex=${clickable ? 0 : undefined}>
      <div class="cl-home-stat-head">
        <span class="cl-home-stat-label">${label}</span>
        ${live ? html`<span class="cl-home-stat-pulse" aria-label="Live"></span>` : null}
      </div>
      <div class="cl-home-stat-value">${value}</div>
      ${sub ? html`<div class="cl-home-stat-sub">${sub}</div>` : null}
    </div>
  `;
}

// ─── Live work-in-progress console ───────────────────────────────

function HomeLiveConsole({
  recordsState,
  recordsTotal,
  workItems,
  selectedItem,
  selectedWorkId,
  onSelect,
  search,
  onSearch,
  exceptionCount,
  exceptionItems,
  activityState,
  activityItems,
  live,
  navigate,
}) {
  const selectedActivity = activityForSelectedItem(activityItems, selectedItem);
  const hasWorkItems = Array.isArray(workItems) && workItems.length > 0;
  const totalLabel = recordsTotal === 1 ? '1 item' : `${recordsTotal || 0} items`;

  return html`
    <section class="cl-home-console" aria-label="Live work in progress">
      <header class="cl-home-console-bar">
        <div class="cl-home-console-title-block">
          <span class="cl-home-console-live">
            ${live ? html`<span class="cl-home-console-pulse" aria-hidden="true"></span>` : null}
            ${live ? 'Context updated live' : 'Recent context'}
          </span>
          <h2>Work in progress</h2>
          <p>Operational memory across inbox, chat, ERP, approvals, and agent actions.</p>
          <div class="cl-home-console-meta" aria-label="Work context summary">
            <span><strong>${recordsTotal || 0}</strong> open</span>
            <span><strong>${exceptionCount || 0}</strong> blocked</span>
            <button type="button" onClick=${() => navigate('/activity')}>Live context</button>
          </div>
        </div>
        <label class="cl-home-console-search">
          <span class="sr-only">Search work in progress</span>
          <input
            type="search"
            value=${search}
            placeholder="Search context, owners, decisions..."
            onInput=${(event) => onSearch?.(event.target.value)}
          />
        </label>
      </header>

      <div class="cl-home-workstream">
        <header class="cl-home-workstream-head">
          <div>
            <h3>Open work <span>· ${totalLabel}</span></h3>
            <p>Sorted by time waiting in queue.</p>
          </div>
          <button type="button" class="cl-home-link" onClick=${() => navigate(accountsPayablePath())}>
            View records →
          </button>
        </header>

        ${recordsState.status === 'loading'
          ? html`<div class="cl-home-skeleton">Loading open work…</div>`
          : recordsState.status === 'error'
            ? html`
                <div class="cl-home-empty">
                  <div class="cl-home-empty-title cl-home-empty-error">Couldn't load open work.</div>
                  <div class="cl-home-empty-sub">${recordsState.error || 'Try again in a moment.'}</div>
                </div>
              `
            : !hasWorkItems
              ? html`
                  <div class="cl-home-empty">
                    <div class="cl-home-empty-title">${search ? 'No work matches that search.' : 'No open work right now.'}</div>
                    <div class="cl-home-empty-sub">
                      ${search
                        ? 'Try another vendor, owner, invoice, blocker, or next step.'
                        : 'Connected surfaces will populate this list as the agent tracks work in progress.'}
                    </div>
                  </div>
                `
              : html`
                  <ul class="cl-home-workstream-list">
                    ${workItems.map((item) => {
                      const isSelected = String(item.id || '') === String(selectedWorkId || selectedItem?.id || '');
                      return html`
                        <li key=${item.id}>
                          <button
                            type="button"
                            class=${`cl-home-workstream-row ${isSelected ? 'is-selected' : ''}`}
                            onClick=${() => onSelect?.(item.id)}
                            aria-pressed=${isSelected}>
                            <span class=${`cl-home-work-dot is-${workStateTone(item.state, item)}`} aria-hidden="true"></span>
                            <span class="cl-home-workstream-main">
                              <span class="cl-home-workstream-title">${workItemTitle(item)}</span>
                              <span class="cl-home-workstream-sub">${workItemSubline(item)}</span>
                            </span>
                            <span class="cl-home-workstream-side">
                              <span class=${`cl-home-state-pill is-${workStateTone(item.state, item)}`}>
                                ${workStateLabel(item.state)}
                              </span>
                              ${ownerInitials(item) ? html`
                                <span class="cl-home-owner-avatar" title=${workOwnerTitle(item)}>
                                  ${ownerInitials(item)}
                                </span>
                              ` : null}
                            </span>
                          </button>
                        </li>
                      `;
                    })}
                  </ul>
                `}
      </div>

      <aside class="cl-home-context-panel" aria-label="Selected work context">
        ${selectedItem
          ? html`
              <header class="cl-home-context-head">
                <div>
                  <h3>${workItemTitle(selectedItem)}</h3>
                  <p>${humanizeWorkType('ap_item')} · ${workItemSurface(selectedItem)}</p>
                </div>
                <span class=${`cl-home-context-live is-${workStateTone(selectedItem.state, selectedItem)}`}>
                  ${workStateLabel(selectedItem.state)}
                </span>
              </header>

              <div class="cl-home-context-section-label">Operational context</div>
              <dl class="cl-home-context-list">
                <${ContextRow} label="Status" value=${workStateLabel(selectedItem.state)} tone=${workStateTone(selectedItem.state, selectedItem)} />
                <${ContextRow} label="Owner" value=${workOwnerLabel(selectedItem)} strong=${true} />
                <${ContextRow} label="Blocker" value=${workBlockerLabel(selectedItem) || 'None blocking'} muted=${!workBlockerLabel(selectedItem)} />
                <${ContextRow} label="Next" value=${workNextStepLabel(selectedItem)} strong=${true} />
                <${ContextRow} label="Evidence" value=${workEvidenceLabel(selectedItem)} />
                <${ContextRow} label="Changed" value=${workChangedLabel(selectedItem)} />
                <${ContextRow} label="ERP" value=${erpStatusLabel(selectedItem)} />
              </dl>

              ${fieldReviewSummary(selectedItem) ? html`
                <div class="cl-home-context-callout">
                  <div class="cl-home-context-callout-label">Field review</div>
                  <div>${fieldReviewSummary(selectedItem)}</div>
                </div>
              ` : null}

              <div class="cl-home-context-actions">
                <button
                  type="button"
                  class="btn btn-primary"
                  onClick=${() => navigate(accountPayableRecordPath(selectedItem.id))}>
                  Open record
                </button>
                ${exceptionItems.some((row) => String(row.box_id || '') === String(selectedItem.id || '')) ? html`
                  <button type="button" class="btn btn-secondary" onClick=${() => navigate('/exceptions')}>
                    Review blocker
                  </button>
                ` : null}
              </div>

              <section class="cl-home-context-activity" aria-label="Recent activity for selected work">
                <header>
                  <span>Recent activity</span>
                  <button type="button" class="cl-home-link" onClick=${() => navigate('/activity')}>Full stream →</button>
                </header>
                ${renderContextActivity({
                  state: activityState,
                  items: selectedActivity,
                  selectedItem,
                  navigate,
                })}
              </section>
            `
          : html`
              <div class="cl-home-empty cl-home-context-empty">
                <div class="cl-home-empty-title">Select a work item.</div>
                <div class="cl-home-empty-sub">The owner, blocker, next step, evidence, and recent decisions appear here.</div>
              </div>
            `}
      </aside>
    </section>
  `;
}

function ContextRow({ label, value, strong = false, muted = false, tone = '' }) {
  return html`
    <div class="cl-home-context-row">
      <dt>${label}</dt>
      <dd class=${`${strong ? 'is-strong' : ''} ${muted ? 'is-muted' : ''} ${tone ? `is-${tone}` : ''}`}>
        ${value || '—'}
      </dd>
    </div>
  `;
}

function renderContextActivity({ state, items, selectedItem, navigate }) {
  if ((!items || items.length === 0) && state?.status === 'loading') {
    return html`<div class="cl-home-skeleton">Loading activity…</div>`;
  }
  if ((!items || items.length === 0) && state?.status === 'error') {
    return html`
      <div class="cl-home-empty cl-home-context-activity-empty">
        <div class="cl-home-empty-title cl-home-empty-error">Couldn't load activity.</div>
        <div class="cl-home-empty-sub">${state?.error || 'Try again in a moment.'}</div>
      </div>
    `;
  }
  if (!items || items.length === 0) {
    return html`
      <div class="cl-home-empty cl-home-context-activity-empty">
        <div class="cl-home-empty-title">No recent changes for this item.</div>
        <div class="cl-home-empty-sub">New decisions, messages, and ERP changes will attach here.</div>
      </div>
    `;
  }
  return html`
    <ol class="cl-home-context-timeline">
      ${items.slice(0, 4).map((row) => {
        const target = activityTarget(row) || (selectedItem?.id ? accountPayableRecordPath(selectedItem.id) : '');
        return html`
          <li key=${row.id || `${row.ts}-${row.event_type}`}>
            <button
              type="button"
              class="cl-home-context-event"
              onClick=${() => target && navigate(target)}>
              <span class=${`cl-home-context-event-dot is-${row.tone || 'info'}`} aria-hidden="true"></span>
              <span class="cl-home-context-event-main">
                <span class="cl-home-context-event-meta">
                  ${row.ts ? fmtRelative(row.ts) : 'Recently'}
                  ${row.surface ? html` · ${surfaceLabel(row.surface)}` : null}
                </span>
                <span class="cl-home-context-event-title">${row.action || 'Updated context'}</span>
                ${row.subject ? html`<span class="cl-home-context-event-sub">${row.subject}</span>` : null}
              </span>
            </button>
          </li>
        `;
      })}
    </ol>
  `;
}

const HOME_STATE_LABELS = {
  approved: 'Approved',
  closed: 'Closed',
  failed_post: 'Failed post',
  needs_approval: 'Needs approval',
  needs_info: 'Needs info',
  needs_second_approval: 'Second approval',
  pending_approval: 'Needs approval',
  posted_to_erp: 'Posted',
  ready_to_post: 'Ready to post',
  received: 'Received',
  rejected: 'Rejected',
  reversed: 'Reversed',
  snoozed: 'Snoozed',
  validated: 'Validated',
};

const HOME_NEXT_STEP_LABELS = {
  approve_or_reject: 'Awaiting approver',
  budget_decision: 'Budget decision',
  escalate_approval: 'Escalate approval',
  needs_non_invoice_followup: 'Follow up',
  none: 'No open step',
  post_to_erp: 'Post to ERP',
  request_info: 'Ask for context',
  resolve_entity_route: 'Choose entity',
  resolve_non_invoice: 'Classify document',
  resubmit: 'Review resubmission',
  retry_post: 'Recover ERP post',
  review: 'Review record',
  review_exception: 'Review exception',
  review_fields: 'Check fields',
  review_finance_effects: 'Review accounting',
  route_for_approval: 'Route approval',
};

const HOME_ERP_STATUS_LABELS = {
  connected: 'Connected',
  failed: 'Failed',
  not_connected: 'No ERP',
  posted: 'Posted',
  ready: 'Ready',
};

function filterWorkItems(items, query) {
  const rows = Array.isArray(items) ? items : [];
  const q = String(query || '').trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((item) => [
    item?.vendor_name,
    item?.vendor,
    item?.invoice_number,
    item?.po_number,
    item?.owner_email,
    item?.owner,
    item?.assigned_to_email,
    workStateLabel(item?.state),
    workNextStepLabel(item),
    workBlockerLabel(item),
    workEvidenceLabel(item),
  ].some((value) => String(value || '').toLowerCase().includes(q)));
}

function workItemTitle(item = {}) {
  return String(item.vendor_name || item.vendor || item.sender || 'Unknown vendor').trim();
}

function workItemSubline(item = {}) {
  const amount = item.amount != null ? fmtCurrency(item.amount, item.currency) : '';
  const parts = [
    documentLabel(item),
    amount,
    workBlockerLabel(item) || workNextStepLabel(item),
    queueAgeLabel(item),
  ].filter(Boolean);
  return parts.join(' · ');
}

function documentLabel(item = {}) {
  const reference = String(item.invoice_number || item.reference || item.po_number || '').trim();
  if (reference) return `Invoice ${reference}`;
  const type = String(item.document_type || '').trim();
  return type ? humanizeToken(type) : 'Work item';
}

function workStateLabel(state) {
  const token = String(state || '').trim().toLowerCase();
  return HOME_STATE_LABELS[token] || humanizeToken(token || 'unknown');
}

function workStateTone(state, item = {}) {
  const token = String(state || '').trim().toLowerCase();
  if (workBlockerLabel(item) || ['failed_post', 'rejected', 'reversed'].includes(token)) return 'blocked';
  if (['needs_approval', 'needs_second_approval', 'pending_approval', 'needs_info'].includes(token)) return 'pending';
  if (['approved', 'ready_to_post', 'posted_to_erp', 'closed'].includes(token)) return 'live';
  return 'neutral';
}

function compactPersonLabel(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (!raw.includes('@')) return raw;
  return raw.split('@')[0].replace(/[._-]+/g, ' ').trim() || raw;
}

function displayMemoryText(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  return /[_-]/.test(raw) ? humanizeSentence(raw) : raw;
}

function memoryRecord(item = {}) {
  return item?.memory && typeof item.memory === 'object' ? item.memory : {};
}

function memoryExecution(item = {}) {
  const execution = memoryRecord(item).execution_state;
  return execution && typeof execution === 'object' ? execution : {};
}

function memoryContext(item = {}) {
  const context = memoryRecord(item).context_summary;
  return context && typeof context === 'object' ? context : {};
}

function latestMemoryDecision(item = {}) {
  const latest = memoryContext(item).latest_decision;
  return latest && typeof latest === 'object' ? latest : {};
}

function workOwnerLabel(item = {}) {
  const execution = memoryExecution(item);
  const context = memoryContext(item);
  const memoryOwner = execution.owner_label || context.who_owns_it || execution.owner?.label || execution.owner?.email || '';
  if (memoryOwner) return compactPersonLabel(memoryOwner) || memoryOwner;
  const pending = Array.isArray(item.approval_pending_assignees) ? item.approval_pending_assignees : [];
  const owner = item.owner_email || item.owner || item.assigned_to_email || pending[0] || '';
  return compactPersonLabel(owner) || 'Unassigned';
}

function workOwnerTitle(item = {}) {
  const execution = memoryExecution(item);
  const context = memoryContext(item);
  const memoryOwner = execution.owner_label || context.who_owns_it || execution.owner?.email || '';
  if (memoryOwner) return String(memoryOwner);
  const pending = Array.isArray(item.approval_pending_assignees) ? item.approval_pending_assignees : [];
  return String(item.owner_email || item.owner || item.assigned_to_email || pending[0] || 'Unassigned');
}

function ownerInitials(item = {}) {
  const label = workOwnerLabel(item);
  if (!label || label === 'Unassigned') return '';
  const parts = label.split(/\s+/).filter(Boolean);
  const letters = parts.length > 1
    ? `${parts[0][0] || ''}${parts[parts.length - 1][0] || ''}`
    : label.slice(0, 2);
  return letters.toUpperCase();
}

function workNextStepLabel(item = {}) {
  const memoryNext = String(memoryContext(item).next_action || memoryExecution(item).next_action || '').trim();
  if (memoryNext) return displayMemoryText(memoryNext);
  const action = String(item.next_action || '').trim().toLowerCase();
  if (HOME_NEXT_STEP_LABELS[action]) return HOME_NEXT_STEP_LABELS[action];
  if (item.workflow_paused_reason) return 'Resolve blocker';
  const state = String(item.state || '').trim().toLowerCase();
  if (state === 'needs_info') return 'Ask for context';
  if (state === 'failed_post') return 'Recover ERP post';
  if (state === 'needs_approval' || state === 'pending_approval') return 'Awaiting approver';
  if (state === 'ready_to_post' || state === 'approved') return 'Post to ERP';
  if (state === 'posted_to_erp' || state === 'closed') return 'No open step';
  return 'Inspect record';
}

function workBlockerLabel(item = {}) {
  const fieldSummary = fieldReviewSummary(item);
  if (fieldSummary) return fieldSummary;
  const context = memoryContext(item);
  const execution = memoryExecution(item);
  const blockedOn = Array.isArray(context.blocked_on) ? context.blocked_on : [];
  if (blockedOn.length) return displayMemoryText(blockedOn[0]);
  const dependencies = Array.isArray(execution.dependencies) ? execution.dependencies : [];
  const activeDependency = dependencies.find((dep) => dep && (dep.type === 'open_exception' || dep.type === 'memory_dependency'));
  if (activeDependency) {
    const detail = activeDependency.detail && typeof activeDependency.detail === 'object'
      ? activeDependency.detail
      : activeDependency;
    return displayMemoryText(detail.reason || detail.exception_type || detail.type || 'Blocked');
  }
  const paused = String(item.workflow_paused_reason || '').trim();
  if (paused) return humanizeSentence(paused);
  const exception = String(item.exception_code || '').trim();
  if (exception) return humanizeToken(exception);
  if (item.budget_requires_decision) return 'Budget decision required';
  if (item.requires_extraction_review) return 'Extraction review required';
  if (item.non_invoice_review_required) return 'Non-invoice review required';
  return '';
}

function fieldReviewSummary(item = {}) {
  const blockers = Array.isArray(item.field_review_blockers) ? item.field_review_blockers : [];
  if (!blockers.length && !item.requires_field_review) return '';
  const fields = blockers
    .map((blocker) => blocker?.field || blocker?.field_name || blocker?.name || blocker?.label)
    .map((field) => humanizeToken(field))
    .filter(Boolean);
  const uniqueFields = [...new Set(fields)];
  if (uniqueFields.length) {
    const shown = uniqueFields.slice(0, 3);
    const extra = uniqueFields.length - shown.length;
    return `Field review: ${shown.join(', ')}${extra > 0 ? ` +${extra}` : ''}`;
  }
  return 'Field review required';
}

function workEvidenceLabel(item = {}) {
  const context = memoryContext(item);
  const evidence = context.evidence && typeof context.evidence === 'object' ? context.evidence : {};
  const decisionRefs = Array.isArray(evidence.decision_refs) ? evidence.decision_refs.filter(Boolean) : [];
  const memoryEvidence = memoryRecord(item).proof?.memory_evidence;
  if (decisionRefs.length || memoryEvidence || evidence.attachment_url || evidence.attachment_content_hash) {
    const surfaces = Array.isArray(context.where_it_happened) ? context.where_it_happened.filter(Boolean) : [];
    const surface = surfaces.length ? surfaces.map(surfaceLabel).join(', ') : workItemSurface(item);
    return `Evidence linked · ${surface}`;
  }
  const count = safeMetric(item.source_count);
  const source = workItemSurface(item);
  if (count && count > 0) {
    return `${count} source${count === 1 ? '' : 's'} linked · ${source}`;
  }
  if (item.primary_source || item.thread_id || item.message_id) return `Source linked · ${source}`;
  return 'Evidence not linked yet';
}

function workItemSurface(item = {}) {
  const context = memoryContext(item);
  const surfaces = Array.isArray(context.where_it_happened) ? context.where_it_happened.filter(Boolean) : [];
  if (surfaces.length) return surfaceLabel(surfaces[surfaces.length - 1]);
  const source = item.primary_source || {};
  return surfaceLabel(source.source_type || source.type || item.source_type || item.surface || item.erp_type || 'workspace');
}

function workChangedLabel(item = {}) {
  const latest = latestMemoryDecision(item);
  if (latest.decided_at) return fmtRelative(latest.decided_at);
  const stamp = item.updated_at || item.queue_entered_at || item.received_at || item.created_at;
  return stamp ? fmtRelative(stamp) : 'No timestamp';
}

function queueAgeLabel(item = {}) {
  const minutes = Number(item.queue_age_minutes || item.approval_wait_minutes || 0);
  if (!Number.isFinite(minutes) || minutes <= 0) return '';
  if (minutes < 60) return `${Math.round(minutes)}m waiting`;
  if (minutes < 1440) return `${Math.round(minutes / 60)}h waiting`;
  return `${Math.round(minutes / 1440)}d waiting`;
}

function erpStatusLabel(item = {}) {
  const status = String(item.erp_status || '').trim().toLowerCase();
  return HOME_ERP_STATUS_LABELS[status] || humanizeToken(status || 'Unknown');
}

function surfaceLabel(value) {
  const token = String(value || '').trim().toLowerCase();
  if (!token) return 'Workspace';
  if (token.includes('gmail')) return 'Gmail';
  if (token.includes('slack')) return 'Slack';
  if (token.includes('teams')) return 'Teams';
  if (token.includes('netsuite')) return 'NetSuite';
  if (token.includes('sap')) return 'SAP';
  if (token.includes('sage_intacct') || token.includes('sage-intacct')) return 'Sage Intacct';
  if (token.includes('sage')) return 'Sage';
  if (token.includes('erp')) return 'ERP';
  if (token === 'agent') return 'Agent';
  return humanizeToken(token);
}

function activityForSelectedItem(items, selectedItem) {
  const rows = Array.isArray(items) ? items : [];
  const selectedId = String(selectedItem?.id || '').trim();
  if (!selectedId) return rows.slice(0, 4);
  const matched = rows.filter((row) => [
    row?.box_id,
    row?.record_id,
    row?.ap_item_id,
    row?.subject_id,
  ].some((value) => String(value || '').trim() === selectedId));
  return (matched.length ? matched : rows).slice(0, 4);
}

function activityTarget(row = {}) {
  const explicitPath = String(row.record_path || row.path || '').trim();
  if (explicitPath.startsWith('/')) return explicitPath;
  const boxType = String(row.box_type || '').trim().toLowerCase();
  if ((!boxType || boxType === 'ap_item') && row.box_id) {
    return accountPayableRecordPath(row.box_id);
  }
  return '';
}

function humanizeToken(value) {
  const s = String(value || '').trim();
  if (!s) return '';
  return s
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function humanizeSentence(value) {
  const s = humanizeToken(value);
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}


// ─── Module 1 — Approver workload strip ───────────────────────────

function ApproverWorkloadStrip({ state, navigate }) {
  if (!state || state.status === 'loading') {
    return html`
      <section class="cl-home-workload">
        <header class="cl-home-workload-head">
          <h2>Approver workload</h2>
        </header>
        <div class="cl-home-skeleton">Loading…</div>
      </section>
    `;
  }
  if (state.status === 'error') {
    return html`
      <section class="cl-home-workload">
        <header class="cl-home-workload-head">
          <h2>Approver workload</h2>
        </header>
        <div class="cl-home-empty">
          <div class="cl-home-empty-title cl-home-empty-error">Couldn't load workload.</div>
          <div class="cl-home-empty-sub">${state.error || 'Try again in a moment.'}</div>
        </div>
      </section>
    `;
  }

  const approvers = (state.data && state.data.approvers) || [];

  if (approvers.length === 0) {
    return html`
      <section class="cl-home-workload">
        <header class="cl-home-workload-head">
          <h2>Approver workload</h2>
          <span class="cl-home-workload-meta">Logistics, not scoring</span>
        </header>
          <div class="cl-home-empty">
            <div class="cl-home-empty-title">Nothing waiting on anyone right now.</div>
            <div class="cl-home-empty-sub">
            When work routes to approval, you'll see who has what on their
            plate so you can re-route if someone is out.
          </div>
        </div>
      </section>
    `;
  }

  return html`
    <section class="cl-home-workload">
      <header class="cl-home-workload-head">
        <h2>Approver workload</h2>
        <span class="cl-home-workload-meta">
          ${approvers.length} approver${approvers.length === 1 ? '' : 's'} ·
          logistics, not scoring
        </span>
      </header>
      <ul class="cl-home-workload-list">
        ${approvers.slice(0, 8).map((a) => html`
          <li class="cl-home-workload-row" key=${a.approver_id}
            onClick=${() => navigate(accountsPayablePath(`?approver=${encodeURIComponent(a.email || a.approver_id)}`))}
            onKeyDown=${(event) => activateOnKey(event, () => navigate(accountsPayablePath(`?approver=${encodeURIComponent(a.email || a.approver_id)}`)))}
            role="button"
            tabindex="0">
            <div class="cl-home-workload-main">
              <div class="cl-home-workload-name">${a.name || a.email || a.approver_id}</div>
              ${a.email && a.email !== a.name ? html`
                <div class="cl-home-workload-email"><code>${a.email}</code></div>
              ` : null}
            </div>
            <div class="cl-home-workload-stats">
              <span class="cl-home-workload-count">${a.pending_count}</span>
              <span class="cl-home-workload-count-label">pending</span>
              ${a.oldest_pending_age_days != null ? html`
                <span class=${`cl-home-workload-age cl-home-workload-age-${ageTone(a.oldest_pending_age_days)}`}>
                  oldest ${a.oldest_pending_age_days}d
                </span>
              ` : null}
            </div>
          </li>
        `)}
      </ul>
      ${approvers.length > 8 ? html`
        <div class="cl-home-workload-more">+ ${approvers.length - 8} more approvers</div>
      ` : null}
    </section>
  `;
}

function ageTone(days) {
  if (days >= 5) return 'alert';
  if (days >= 2) return 'warn';
  return 'ok';
}

function activateOnKey(event, activate) {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  event.preventDefault();
  activate?.();
}


// ─── System status footer ─────────────────────────────────────────

function SystemStatusFooter({ integrations, agentLastAction, navigate }) {
  const watch = integrations.find((i) => i.name === 'gmail') || {};
  const slack = integrations.find((i) => i.name === 'slack') || {};
  const teams = integrations.find((i) => i.name === 'teams') || {};
  const erp = integrations.find((i) => i.name === 'erp') || {};

  const allConnected = [watch, slack, teams, erp].every((i) => i.connected || i.name === 'teams');
  const agentTone = allConnected ? 'good' : 'warn';
  const agentLabel = allConnected ? 'Agent active' : 'Agent partially configured';

  return html`
    <section class="cl-home-status" aria-label="System status">
      <header class="cl-home-status-head">
        <h3>System status</h3>
        <button class="cl-home-link" onClick=${() => navigate('/connections')}>
          Manage connections →
        </button>
      </header>
      <div class="cl-home-status-grid">
        <div class=${`cl-home-status-cell cl-home-status-cell-${agentTone}`}>
          <span class=${`cl-home-status-dot cl-home-status-dot-${agentTone}`}></span>
          <div>
            <div class="cl-home-status-label">${agentLabel}</div>
            <div class="cl-home-status-sub">
              ${agentLastAction
                ? `Last action ${fmtRelative(agentLastAction)}`
                : 'No actions recorded yet'}
            </div>
          </div>
        </div>
        <${StatusCell} label="Gmail" integration=${watch} fallbackLabel="Inbox not connected" />
        <${StatusCell} label="Approvals" integration=${slack.connected ? slack : teams} fallbackLabel="No Slack/Teams approval channel" />
        <${StatusCell} label="ERP" integration=${erp} fallbackLabel="ERP not connected" />
      </div>
    </section>
  `;
}

function StatusCell({ label, integration, fallbackLabel }) {
  const connected = !!integration?.connected;
  const reauth = !!integration?.requires_reconnect || !!integration?.requires_reauthorization;
  const tone = !connected ? 'off' : reauth ? 'warn' : 'good';
  const stamp = integration?.last_sync_at || integration?.connected_at;
  return html`
    <div class=${`cl-home-status-cell cl-home-status-cell-${tone}`}>
      <span class=${`cl-home-status-dot cl-home-status-dot-${tone}`}></span>
      <div>
        <div class="cl-home-status-label">${label}</div>
        <div class="cl-home-status-sub">
          ${connected
            ? (reauth ? 'Reconnect required' : (stamp ? `Synced ${fmtRelative(stamp)}` : 'Connected'))
            : fallbackLabel}
        </div>
      </div>
    </div>
  `;
}


// ─── Exception queue helpers ──────────────────────────────────────

function humanizeWorkType(t) {
  const s = String(t || '').toLowerCase();
  if (s === 'ap_item') return 'Accounts Payable';
  if (s === 'purchase_order') return 'Procurement';
  if (s === 'vendor_onboarding_session') return 'Vendor Onboarding';
  if (s === 'bank_match') return 'Bank Reconciliation';
  if (!s) return 'Record';
  return s
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function safeMetric(value) {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}


// ─── Policy proposals (tribal-knowledge Build 3) ─────────────────────
// The agent plays enacted behavior back as a proposed standing rule.
// Accept lands the bounded rule (versioned, attributed); decline records
// the deliberate non-rule — its reason is required because "we handle
// these case-by-case because..." is itself knowledge worth keeping.

function policyLearningCitation(proposal) {
  const evidence = proposal && typeof proposal.evidence === 'object' ? proposal.evidence : null;
  const citation = evidence && typeof evidence.learning_citation === 'object'
    ? evidence.learning_citation
    : null;
  return citation;
}

function policyLabel(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatPolicyLearningCitation(citation) {
  if (!citation) return null;
  const snapshot = citation.private_eval_snapshot &&
    typeof citation.private_eval_snapshot === 'object'
    ? citation.private_eval_snapshot
    : {};
  const pattern = citation.recurring_pattern &&
    typeof citation.recurring_pattern === 'object'
    ? citation.recurring_pattern
    : {};

  const snapshotParts = ['AP snapshot'];
  const totalItems = safeMetric(snapshot.total_items);
  if (totalItems !== null) snapshotParts.push(`${totalItems} items`);
  const gate = String(snapshot.release_gate_status || '').replace(/_/g, ' ').trim();
  if (gate) snapshotParts.push(`gate ${gate}`);

  const patternLabel = policyLabel(pattern.label || pattern.pattern_key);
  const patternCount = safeMetric(pattern.vendor_count ?? pattern.count);
  const patternLine = patternLabel
    ? `Pattern: ${patternLabel}${patternCount !== null ? ` · ${patternCount} cases` : ''}`
    : '';

  return {
    snapshotLine: snapshotParts.length > 1 ? snapshotParts.join(' · ') : '',
    patternLine,
  };
}

function PolicyProposalsPanel() {
  const [proposals, setProposals] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [declining, setDeclining] = useState(null); // {id, reason}

  const load = () => {
    api('/api/workspace/policy-proposals?status=pending', { silent: true })
      .then((resp) => setProposals(Array.isArray(resp?.proposals) ? resp.proposals : []))
      .catch(() => setProposals([]));
  };
  useEffect(() => { load(); }, []);

  const resolve = async (id, action, reason) => {
    setBusyId(id);
    try {
      await api(`/api/workspace/policy-proposals/${encodeURIComponent(id)}/${action}`, {
        method: 'POST',
        body: JSON.stringify(action === 'decline' ? { reason } : {}),
      });
      setDeclining(null);
      load();
    } catch (_) {
      // Leave the proposal visible; the operator can retry.
    } finally {
      setBusyId(null);
    }
  };

  if (!proposals || proposals.length === 0) return null;

  return html`
    <section class="cl-home-proposals" aria-label="Proposed standing rules">
      <header class="cl-home-proposals-head">
        <h2>Solden noticed a pattern</h2>
        <span class="cl-home-proposals-count">${proposals.length}</span>
      </header>
      <ul class="cl-home-proposals-list">
        ${proposals.map((p) => {
          const citation = formatPolicyLearningCitation(policyLearningCitation(p));
          return html`
          <li key=${p.id} class="cl-home-proposal">
            <p class="cl-home-proposal-summary">${p.behavior_summary}</p>
            ${citation ? html`
              <div class="cl-home-proposal-citation">
                <span>Learning evidence</span>
                ${citation.snapshotLine ? html`
                  <strong>${citation.snapshotLine}</strong>
                ` : null}
                ${citation.patternLine ? html`
                  <small>${citation.patternLine}</small>
                ` : null}
              </div>
            ` : null}
            ${declining?.id === p.id ? html`
              <div class="cl-home-proposal-decline">
                <textarea
                  rows="2"
                  placeholder="Why keep handling these case-by-case? (recorded as a deliberate non-rule)"
                  value=${declining.reason}
                  onInput=${(e) => setDeclining({ id: p.id, reason: e.target.value })}></textarea>
                <div class="cl-home-proposal-actions">
                  <button type="button" class="btn btn-tertiary"
                          onClick=${() => setDeclining(null)} disabled=${busyId === p.id}>Cancel</button>
                  <button type="button" class="btn btn-primary"
                          disabled=${busyId === p.id || !declining.reason.trim()}
                          onClick=${() => resolve(p.id, 'decline', declining.reason.trim())}>
                    Record non-rule
                  </button>
                </div>
              </div>
            ` : html`
              <div class="cl-home-proposal-actions">
                <button type="button" class="btn btn-tertiary"
                        onClick=${() => setDeclining({ id: p.id, reason: '' })}
                        disabled=${busyId === p.id}>Decline</button>
                <button type="button" class="btn btn-primary"
                        onClick=${() => resolve(p.id, 'accept')}
                        disabled=${busyId === p.id}>
                  ${busyId === p.id ? 'Working…' : 'Make it a rule'}
                </button>
              </div>
            `}
          </li>`;
        })}
      </ul>
    </section>
  `;
}
