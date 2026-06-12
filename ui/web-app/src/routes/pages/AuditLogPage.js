/**
 * Org-scoped, admin-gated audit search.
 *
 * The audit log is a read-only compliance surface. It presents readable
 * event labels for operators while keeping raw payloads available in detail.
 */
import { h } from 'preact';
import { useState, useEffect, useCallback } from 'preact/hooks';
import htm from 'htm';
import { fmtDateTime } from '../route-helpers.js';
import { EmptyState, ErrorRetry, LoadingSkeleton } from '../../components/StatePrimitives.js';
import { STATE_LABELS, humanizeSnakeText } from '../../utils/formatters.js';

const html = htm.bind(h);

const PAGE_SIZE = 20;

const COMMON_EVENT_TYPES = [
  { value: '', label: 'All event types' },
  { value: 'state_transition', label: 'State changes' },
  { value: 'invoice_approved,invoice_rejected,approval_requested', label: 'Approval decisions' },
  { value: 'erp_post_completed,erp_post_failed', label: 'ERP posting' },
  { value: 'organization_renamed,organization_domain_changed,organization_integration_mode_changed', label: 'Workspace configuration' },
  { value: 'audit_search_viewed,audit_event_viewed,audit_retention_updated,audit_export_started,audit_export_downloaded', label: 'Audit administration' },
  { value: 'plan_observed', label: 'Agent observations' },
  { value: 'illegal_transition_blocked,invoice_reverse_blocked,invoice_snooze_blocked', label: 'Blocked actions' },
];

const COMMON_RECORD_TYPES = [
  { value: '', label: 'All record types' },
  { value: 'ap_item', label: 'Accounts Payable' },
  { value: 'purchase_order', label: 'Procurement' },
  { value: 'vendor_onboarding_session', label: 'Vendor onboarding' },
  { value: 'bank_match', label: 'Bank reconciliation' },
  { value: 'organization', label: 'Organization' },
  { value: 'workspace_audit', label: 'Audit log' },
  { value: 'audit_export', label: 'Audit export' },
];

const EVENT_TYPE_LABELS = {
  state_transition: 'State change',
  invoice_approved: 'Invoice approved',
  invoice_rejected: 'Invoice rejected',
  invoice_auto_approved: 'Invoice auto-approved',
  approval_requested: 'Approval requested',
  invoice_created: 'Invoice created',
  decision_made: 'Decision recorded',
  enrichment_complete: 'Data extracted',
  erp_post_completed: 'Posted to ERP',
  erp_post_failed: 'ERP post failed',
  organization_renamed: 'Organization renamed',
  organization_domain_changed: 'Workspace domain changed',
  organization_integration_mode_changed: 'Integration mode changed',
  plan_observed: 'Agent observation',
  illegal_transition_blocked: 'State change blocked',
  invoice_reverse_blocked: 'Reverse action blocked',
  invoice_snooze_blocked: 'Snooze blocked',
  webhook_test: 'Webhook test sent',
  audit_search_viewed: 'Audit log searched',
  audit_event_viewed: 'Audit event viewed',
  audit_retention_updated: 'Audit retention updated',
  audit_export_started: 'Audit export started',
  audit_export_downloaded: 'Audit export downloaded',
};

const RECORD_TYPE_LABELS = {
  ap_item: 'Accounts Payable',
  purchase_order: 'Procurement',
  vendor_onboarding_session: 'Vendor onboarding',
  bank_match: 'Bank reconciliation',
  organization: 'Organization',
  user: 'User',
  workspace_audit: 'Audit log',
  audit_export: 'Audit export',
  webhook_subscription: 'SIEM webhook',
};

const ACTOR_TYPE_LABELS = {
  user: 'User',
  human: 'User',
  system: 'System',
  agent: 'Agent',
  api: 'API',
  webhook: 'Webhook',
};

const VERDICT_LABELS = {
  should_execute: { label: 'Allowed', cls: 'cl-audit-verdict-allowed' },
  allowed: { label: 'Allowed', cls: 'cl-audit-verdict-allowed' },
  vetoed: { label: 'Blocked', cls: 'cl-audit-verdict-blocked' },
  blocked: { label: 'Blocked', cls: 'cl-audit-verdict-blocked' },
  observe: { label: 'Observed', cls: 'cl-audit-verdict-observed' },
  observed: { label: 'Observed', cls: 'cl-audit-verdict-observed' },
};

const SOURCE_LABELS = {
  erp_native_netsuite: 'NetSuite panel',
  erp_native_sap: 'SAP Fiori panel',
  erp_native_sage_intacct: 'Sage Intacct panel',
  erp_native_sage_accounting: 'Sage Accounting connector',
  erp_native_sage_business_cloud: 'Sage Accounting connector',
  workspace: 'Workspace',
  workspace_audit: 'Audit log',
  gmail: 'Gmail',
  slack: 'Slack',
  teams: 'Microsoft Teams',
  test_seed: 'Test seed',
};

function normalizeToken(value) {
  return String(value || '').trim().toLowerCase();
}

function formatToken(value) {
  return humanizeSnakeText(String(value || '').trim());
}

function formatAuditEventType(value) {
  const token = normalizeToken(value);
  if (!token) return 'Audit event';
  return EVENT_TYPE_LABELS[token] || formatToken(token);
}

function formatRecordType(value) {
  const token = normalizeToken(value);
  if (!token) return 'Record';
  return RECORD_TYPE_LABELS[token] || formatToken(token);
}

function formatState(value) {
  const token = normalizeToken(value);
  if (!token) return '—';
  return STATE_LABELS[token] || formatToken(token);
}

function formatActor(actorId, actorType) {
  const id = String(actorId || '').trim();
  if (id && id.includes('@')) return id;
  if (id && id.includes('_')) return formatToken(id);
  if (id) return id;
  const type = normalizeToken(actorType);
  return ACTOR_TYPE_LABELS[type] || 'System';
}

function formatVerdict(value) {
  const token = normalizeToken(value);
  return VERDICT_LABELS[token] || {
    label: token ? formatToken(token) : '',
    cls: 'cl-audit-verdict-neutral',
  };
}

function formatSource(value) {
  const token = normalizeToken(value);
  if (!token) return '';
  return SOURCE_LABELS[token] || formatToken(token);
}

function formatConfidence(value, digits = 0) {
  return typeof value === 'number' ? `${(value * 100).toFixed(digits)}%` : '';
}

function formatActorType(value) {
  const token = normalizeToken(value);
  return ACTOR_TYPE_LABELS[token] || formatToken(token || 'system');
}

function shortId(value, length = 18) {
  const id = String(value || '').trim();
  if (!id) return '';
  return id.length > length ? `${id.slice(0, length)}…` : id;
}

function parseMaybeJson(value) {
  if (!value) return {};
  if (typeof value === 'object') return value;
  try {
    const parsed = JSON.parse(String(value));
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function getEventCategory(event) {
  const eventType = normalizeToken(event?.event_type);
  const boxType = normalizeToken(event?.box_type);
  const verdict = normalizeToken(event?.governance_verdict);
  const source = normalizeToken(event?.source);
  if (eventType.startsWith('audit_') || boxType === 'workspace_audit' || boxType === 'audit_export') {
    return { label: 'Access', cls: 'cl-audit-type-access' };
  }
  if (eventType.includes('blocked') || eventType.includes('failed') || eventType.includes('rejected') || verdict === 'blocked' || verdict === 'vetoed') {
    return { label: 'Control', cls: 'cl-audit-type-control' };
  }
  if (eventType.includes('approval')) {
    return { label: 'Approval', cls: 'cl-audit-type-approval' };
  }
  if (eventType.includes('erp') || source.includes('erp') || source.includes('netsuite') || source.includes('sage') || source.includes('sap')) {
    return { label: 'ERP', cls: 'cl-audit-type-erp' };
  }
  if (eventType.includes('organization') || eventType.includes('config') || boxType === 'organization' || boxType === 'user') {
    return { label: 'Admin', cls: 'cl-audit-type-admin' };
  }
  if (eventType.includes('plan') || eventType.includes('agent') || eventType.includes('memory')) {
    return { label: 'Agent', cls: 'cl-audit-type-agent' };
  }
  return { label: 'Workflow', cls: 'cl-audit-type-workflow' };
}

function getEventSource(event) {
  const payload = parseMaybeJson(event?.payload_json);
  return formatSource(event?.source || payload.source || payload.surface || payload.channel || '');
}

function getEventContextLine(event) {
  if (event?.decision_reason) return event.decision_reason;
  const payload = parseMaybeJson(event?.payload_json);
  if (payload.reason) return payload.reason;
  if (payload.message) return payload.message;
  if (payload.filters) return 'Search filters recorded for audit access review.';
  if (event?.prev_state || event?.new_state) {
    return `${formatState(event.prev_state)} changed to ${formatState(event.new_state)}.`;
  }
  const source = getEventSource(event);
  if (source) return `Recorded from ${source}.`;
  return 'Immutable event recorded.';
}

function getOutcomeMeta(event) {
  if (event?.governance_verdict) return formatVerdict(event.governance_verdict);
  const eventType = normalizeToken(event?.event_type);
  if (eventType.includes('failed') || eventType.includes('blocked') || eventType.includes('rejected')) {
    return { label: 'Needs review', cls: 'cl-audit-verdict-blocked' };
  }
  if (eventType.includes('viewed') || eventType.includes('searched')) {
    return { label: 'Viewed', cls: 'cl-audit-verdict-neutral' };
  }
  return { label: 'Recorded', cls: 'cl-audit-verdict-neutral' };
}

function eventHasIntegrityMeta(event) {
  return Boolean(
    event?.policy_version ||
    event?.chain_seq ||
    event?.hash ||
    event?.hash_prefix ||
    event?.prev_hash ||
    typeof event?.agent_confidence === 'number'
  );
}

function auditStats(events) {
  const rows = Array.isArray(events) ? events : [];
  let controlEvents = 0;
  let accessEvents = 0;
  let workflowEvents = 0;
  let sourceCount = 0;
  for (const event of rows) {
    const category = getEventCategory(event).label;
    if (category === 'Control') controlEvents += 1;
    if (category === 'Access') accessEvents += 1;
    if (['Workflow', 'Approval', 'ERP', 'Agent'].includes(category)) workflowEvents += 1;
    if (getEventSource(event)) sourceCount += 1;
  }
  return { shown: rows.length, controlEvents, accessEvents, workflowEvents, sourceCount };
}

function eventAriaLabel(event) {
  const eventLabel = formatAuditEventType(event?.event_type);
  const recordType = formatRecordType(event?.box_type);
  const recordId = event?.box_id ? ` ${event.box_id}` : '';
  return `${eventLabel} for ${recordType}${recordId}`;
}


function FilterBar({ filters, setFilters, onApply, onReset, onExport, exportState, busy }) {
  const setField = (key, value) => setFilters({ ...filters, [key]: value });
  const fmt = (exportState?.export_format || exportState?.format || 'csv').toUpperCase();
  const exportLabel = (() => {
    if (!exportState) return 'Export CSV';
    switch (exportState.status) {
      case 'queued': return `Queued ${fmt}…`;
      case 'running': return `Building ${fmt}…`;
      case 'done': return `Download ${fmt}`;
      case 'failed': return 'Export failed';
      default: return 'Export CSV';
    }
  })();
  const exportBusy = exportState && (exportState.status === 'queued' || exportState.status === 'running');

  return html`
    <section class="cl-audit-query-card" aria-label="Audit query">
      <div class="cl-audit-query-head">
        <div>
          <h2>Search the trail</h2>
          <p>Newest events first. Filters and exports are logged back into the same tamper-evident chain.</p>
        </div>
        <div class="cl-audit-export-actions">
          <button
            class=${`btn btn-sm ${exportState?.status === 'failed' ? 'btn-danger' : 'btn-secondary'}`}
            onClick=${() => onExport('csv')}
            disabled=${busy || exportBusy}
            title=${exportState?.status === 'failed' && exportState?.error_message
              ? exportState.error_message
              : 'Download the current filter set as CSV'}>
            ${(exportState?.export_format || exportState?.format || 'csv') === 'csv' ? exportLabel : 'Export CSV'}
          </button>
          <button
            class="btn btn-sm btn-secondary"
            onClick=${() => onExport('pdf')}
            disabled=${busy || exportBusy}
            title="Download the current filter set as PDF (capped at 5K rows; CSV is unbounded)">
            ${(exportState?.export_format || exportState?.format) === 'pdf' ? exportLabel : 'Export PDF'}
          </button>
          <button class="btn btn-sm btn-tertiary" onClick=${onReset} disabled=${busy}>
            Reset
          </button>
        </div>
      </div>
      <div class="cl-audit-filters">
        <label class="cl-audit-filter-field">
          <span>From</span>
          <input
            type="datetime-local"
            value=${filters.from_ts}
            onChange=${(e) => setField('from_ts', e.target.value)}
            disabled=${busy} />
        </label>
        <label class="cl-audit-filter-field">
          <span>To</span>
          <input
            type="datetime-local"
            value=${filters.to_ts}
            onChange=${(e) => setField('to_ts', e.target.value)}
            disabled=${busy} />
        </label>
        <label class="cl-audit-filter-field">
          <span>Event type</span>
          <select
            value=${filters.event_type_preset}
            onChange=${(e) => setField('event_type_preset', e.target.value)}
            disabled=${busy}>
            ${COMMON_EVENT_TYPES.map((opt) => html`
              <option value=${opt.value}>${opt.label}</option>
            `)}
          </select>
        </label>
        <label class="cl-audit-filter-field">
          <span>Record type</span>
          <select
            value=${filters.box_type}
            onChange=${(e) => setField('box_type', e.target.value)}
            disabled=${busy}>
            ${COMMON_RECORD_TYPES.map((opt) => html`
              <option value=${opt.value}>${opt.label}</option>
            `)}
          </select>
        </label>
        <label class="cl-audit-filter-field">
          <span>Actor</span>
          <input
            type="text"
            placeholder="email, user ID, or system"
            value=${filters.actor_id}
            onInput=${(e) => setField('actor_id', e.target.value)}
            disabled=${busy} />
        </label>
        <label class="cl-audit-filter-field">
          <span>Record ID</span>
          <input
            type="text"
            placeholder="ap-12345"
            value=${filters.box_id}
            onInput=${(e) => setField('box_id', e.target.value)}
            disabled=${busy} />
        </label>
        <div class="cl-audit-filter-actions">
          <button class="btn btn-sm btn-primary" onClick=${onApply} disabled=${busy}>
            ${busy ? 'Searching…' : 'Search'}
          </button>
        </div>
      </div>
    </section>`;
}


function EventRow({ event, isActive, onSelect }) {
  const ts = fmtDateTime(event.ts);
  const summary = formatAuditEventType(event.event_type);
  const actor = formatActor(event.actor_id, event.actor_type);
  const outcomeMeta = getOutcomeMeta(event);
  const confidence = event.agent_confidence;
  const category = getEventCategory(event);
  const source = getEventSource(event);
  const contextLine = getEventContextLine(event);
  const hasIntegrity = eventHasIntegrityMeta(event);
  const select = () => onSelect(event);
  const onKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      select();
    }
  };

  return html`
    <tr
      class=${`cl-audit-row${isActive ? ' is-active' : ''}`}
      onClick=${select}
      onKeyDown=${onKeyDown}
      tabIndex="0"
      aria-label=${eventAriaLabel(event)}>
      <td class="cl-audit-cell-ts">${ts}</td>
      <td class="cl-audit-cell-type">
        <span class=${`cl-audit-type-pill ${category.cls}`}>${category.label}</span>
        ${source ? html`<span class="cl-audit-source">${source}</span>` : null}
      </td>
      <td class="cl-audit-cell-event">
        <span class="cl-audit-event-name">${summary}</span>
        <span class="cl-audit-event-context">${contextLine}</span>
        ${event.prev_state || event.new_state
          ? html`<span class="cl-audit-state-pair">
              <span>${formatState(event.prev_state)}</span>
              <span class="cl-audit-state-arrow">→</span>
              <span>${formatState(event.new_state)}</span>
            </span>`
          : null}
      </td>
      <td class="cl-audit-cell-actor">
        <span>${actor}</span>
        <small>${formatActorType(event.actor_type)}</small>
      </td>
      <td class="cl-audit-cell-box">
        <span class="cl-audit-box-type">${formatRecordType(event.box_type)}</span>
        <span class="cl-audit-box-id">${shortId(event.box_id, 28) || '—'}</span>
      </td>
      <td class="cl-audit-cell-integrity">
        <span class=${`cl-audit-chip ${outcomeMeta.cls}`}>${outcomeMeta.label}</span>
        ${typeof confidence === 'number'
          ? html`<span class="cl-audit-confidence">${formatConfidence(confidence)}</span>`
          : null}
        ${event.policy_version ? html`<span class="cl-audit-integrity-token">Policy ${event.policy_version}</span>` : null}
        ${event.chain_seq ? html`<span class="cl-audit-integrity-token">Seq ${event.chain_seq}</span>` : null}
        ${!hasIntegrity ? html`<span class="cl-audit-integrity-muted">Trace stored</span>` : null}
      </td>
    </tr>`;
}


function DetailPanel({ event, onClose, api, orgId }) {
  const [full, setFull] = useState(event);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const loadDetail = useCallback(async () => {
    if (!event?.id) return;
    setFull(event);
    setLoading(true);
    setErr(null);
    try {
      const resp = await api(
        `/api/workspace/audit/event/${encodeURIComponent(event.id)}?organization_id=${encodeURIComponent(orgId)}`
      );
      setFull(resp?.event || event);
    } catch (exc) {
      setErr(String(exc?.message || exc));
    } finally {
      setLoading(false);
    }
  }, [api, orgId, event]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const payload = full?.payload_json || {};
  const payloadJson = typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2);
  const externalRefs = full?.external_refs;
  const externalRefsJson = externalRefs
    ? (typeof externalRefs === 'string' ? externalRefs : JSON.stringify(externalRefs, null, 2))
    : null;
  const category = getEventCategory(full || {});
  const outcomeMeta = getOutcomeMeta(full || {});
  const source = getEventSource(full || {});
  const contextLine = getEventContextLine(full || {});

  return html`
    <aside class="cl-audit-detail">
      <div class="cl-audit-detail-head">
        <div>
          <span class=${`cl-audit-type-pill ${category.cls}`}>${category.label}</span>
          <h3>${formatAuditEventType(full?.event_type)}</h3>
        </div>
        <button class="btn btn-sm btn-tertiary" onClick=${onClose} aria-label="Close detail">Close</button>
      </div>
      ${err ? html`<${ErrorRetry} message=${err} onRetry=${loadDetail} />` : null}
      ${loading ? html`<${LoadingSkeleton} rows=${4} />` : null}
      ${!loading && !err ? html`
        <section class="cl-audit-detail-summary" aria-label="Audit event context">
          <div>
            <span>Outcome</span>
            <strong><span class=${`cl-audit-chip ${outcomeMeta.cls}`}>${outcomeMeta.label}</span></strong>
          </div>
          <div>
            <span>Context</span>
            <p>${contextLine}</p>
          </div>
          ${source ? html`
            <div>
              <span>Surface</span>
              <strong>${source}</strong>
            </div>
          ` : null}
        </section>
        <dl class="cl-audit-detail-grid">
          <dt>Event ID</dt><dd><code>${full?.id}</code></dd>
          <dt>Timestamp</dt><dd>${fmtDateTime(full?.ts)}</dd>
          <dt>Record</dt><dd>${formatRecordType(full?.box_type)} <code>${full?.box_id || '—'}</code></dd>
          <dt>Actor</dt><dd>${formatActor(full?.actor_id, full?.actor_type)}</dd>
          <dt>Actor type</dt><dd>${formatActorType(full?.actor_type)}</dd>
          ${full?.prev_state || full?.new_state ? html`
            <dt>State</dt>
            <dd>${formatState(full.prev_state)} → ${formatState(full.new_state)}</dd>
          ` : null}
          ${full?.governance_verdict ? html`
            <dt>Governance verdict</dt>
            <dd>
              <span class=${`cl-audit-chip ${formatVerdict(full.governance_verdict).cls}`}>
                ${formatVerdict(full.governance_verdict).label}
              </span>
            </dd>
          ` : null}
          ${typeof full?.agent_confidence === 'number' ? html`
            <dt>Agent confidence</dt>
            <dd>${formatConfidence(full.agent_confidence, 1)}</dd>
          ` : null}
          ${full?.decision_reason ? html`
            <dt>Decision reason</dt><dd>${full.decision_reason}</dd>
          ` : null}
          ${full?.correlation_id ? html`
            <dt>Correlation</dt><dd><code>${full.correlation_id}</code></dd>
          ` : null}
          ${full?.source ? html`
            <dt>Source</dt><dd>${formatSource(full.source)}</dd>
          ` : null}
          ${full?.policy_version ? html`
            <dt>Policy version</dt><dd>${full.policy_version}</dd>
          ` : null}
          ${full?.capability_id ? html`
            <dt>Capability</dt><dd><code>${full.capability_id}</code></dd>
          ` : null}
          ${full?.chain_seq ? html`
            <dt>Chain seq</dt><dd>${full.chain_seq}</dd>
          ` : null}
          ${full?.hash || full?.hash_prefix ? html`
            <dt>Hash</dt><dd><code>${full.hash || `${full.hash_prefix}…`}</code></dd>
          ` : null}
          ${full?.prev_hash ? html`
            <dt>Previous hash</dt><dd><code>${full.prev_hash}</code></dd>
          ` : null}
        </dl>
        ${payload && Object.keys(payload).length > 0 ? html`
          <details class="cl-audit-detail-payload">
            <summary>Payload and before/after data</summary>
            <pre><code>${payloadJson}</code></pre>
          </details>
        ` : null}
        ${externalRefsJson && externalRefsJson !== '{}' ? html`
          <details class="cl-audit-detail-payload">
            <summary>External refs</summary>
            <pre><code>${externalRefsJson}</code></pre>
          </details>
        ` : null}
      ` : null}
    </aside>`;
}


const SIEM_EVENT_BUNDLES = [
  { value: '*', label: 'All audit events (compliance feed)' },
  {
    value: 'state_transition,invoice_approved,invoice_rejected,erp_post_completed,erp_post_failed',
    label: 'Accounts payable workflow',
  },
  {
    value: 'organization_renamed,organization_domain_changed,organization_integration_mode_changed',
    label: 'Workspace configuration',
  },
  {
    value: 'illegal_transition_blocked,invoice_reverse_blocked,invoice_snooze_blocked',
    label: 'Blocked governance actions',
  },
];

const DELIVERY_STATUS_LABELS = {
  success: { label: 'Delivered', cls: 'cl-audit-delivery-ok' },
  failed: { label: 'Failed', cls: 'cl-audit-delivery-fail' },
  retrying: { label: 'Retrying', cls: 'cl-audit-delivery-retry' },
};


function SiemWebhookForm({ onSubmit, onCancel, busy }) {
  const [url, setUrl] = useState('');
  const [secret, setSecret] = useState('');
  const [bundlePreset, setBundlePreset] = useState(SIEM_EVENT_BUNDLES[0].value);
  const [customEvents, setCustomEvents] = useState('');
  const [description, setDescription] = useState('');
  const [err, setErr] = useState(null);

  const submit = useCallback(async (e) => {
    e?.preventDefault?.();
    setErr(null);
    const trimmedUrl = url.trim();
    if (!trimmedUrl.startsWith('https://') && !trimmedUrl.startsWith('http://')) {
      setErr('URL must start with https:// (or http:// for local testing).');
      return;
    }
    const eventTypesString = customEvents.trim() || bundlePreset;
    const eventTypes = eventTypesString
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    if (eventTypes.length === 0) {
      setErr('Pick a bundle or enter at least one event type.');
      return;
    }
    try {
      await onSubmit({
        url: trimmedUrl,
        secret: secret.trim(),
        event_types: eventTypes,
        description: description.trim(),
      });
    } catch (exc) {
      setErr(String(exc?.message || exc));
    }
  }, [url, secret, bundlePreset, customEvents, description, onSubmit]);

  return html`
    <form class="cl-siem-form" onSubmit=${submit}>
      <label class="cl-audit-filter-field">
        <span>Endpoint URL</span>
        <input
          type="url"
          placeholder="https://siem.example.com/solden/ingest"
          value=${url}
          onInput=${(e) => setUrl(e.target.value)}
          disabled=${busy}
          required />
      </label>
      <label class="cl-audit-filter-field">
        <span>HMAC secret (optional)</span>
        <input
          type="text"
          placeholder="leave blank for no signing"
          value=${secret}
          onInput=${(e) => setSecret(e.target.value)}
          disabled=${busy} />
      </label>
      <label class="cl-audit-filter-field">
        <span>Event bundle</span>
        <select
          value=${bundlePreset}
          onChange=${(e) => setBundlePreset(e.target.value)}
          disabled=${busy || customEvents.trim().length > 0}>
          ${SIEM_EVENT_BUNDLES.map((opt) => html`
            <option value=${opt.value}>${opt.label}</option>
          `)}
        </select>
      </label>
      <label class="cl-audit-filter-field cl-siem-form-wide">
        <span>Custom event types (comma-separated, overrides bundle)</span>
        <input
          type="text"
          placeholder="state_transition, plan_observed, ..."
          value=${customEvents}
          onInput=${(e) => setCustomEvents(e.target.value)}
          disabled=${busy} />
      </label>
      <label class="cl-audit-filter-field cl-siem-form-wide">
        <span>Description (optional)</span>
        <input
          type="text"
          placeholder="Splunk HEC — production"
          value=${description}
          onInput=${(e) => setDescription(e.target.value)}
          disabled=${busy} />
      </label>
      ${err ? html`<div class="cl-siem-form-error">${err}</div>` : null}
      <div class="cl-siem-form-actions">
        <button type="submit" class="btn btn-sm btn-primary" disabled=${busy}>
          ${busy ? 'Saving…' : 'Register webhook'}
        </button>
        <button type="button" class="btn btn-sm btn-tertiary" onClick=${onCancel} disabled=${busy}>
          Cancel
        </button>
      </div>
    </form>`;
}


function SiemDeliveriesPanel({ api, orgId, webhook, onClose }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');

  const load = useCallback(async () => {
    if (!api || !orgId || !webhook?.id) return;
    setLoading(true);
    setErr(null);
    try {
      const params = new URLSearchParams();
      params.set('organization_id', orgId);
      params.set('limit', '50');
      if (statusFilter) params.set('status', statusFilter);
      const resp = await api(
        `/api/workspace/webhooks/${encodeURIComponent(webhook.id)}/deliveries?${params.toString()}`
      );
      setRows(Array.isArray(resp?.deliveries) ? resp.deliveries : []);
    } catch (exc) {
      setErr(String(exc?.message || exc));
    } finally {
      setLoading(false);
    }
  }, [api, orgId, webhook?.id, statusFilter]);

  useEffect(() => { load(); }, [load]);

  // Failures-last-24h counter — derived from the rows we already have.
  // For >50 attempts this is a lower bound (newest 50 only); we annotate
  // the UI accordingly so an SRE doesn't read it as canonical.
  const failuresLast24h = (() => {
    const cutoff = Date.now() - 24 * 60 * 60 * 1000;
    return rows.filter((r) => {
      if (r.status !== 'failed') return false;
      const ts = r.attempted_at ? new Date(r.attempted_at).getTime() : 0;
      return ts >= cutoff;
    }).length;
  })();

  return html`
    <section class="cl-siem-deliveries">
      <header class="cl-siem-deliveries-head">
        <div>
          <h4>Deliveries — <code>${webhook.url}</code></h4>
          <p class="muted">
            Latest 50 attempts (newest first). Retries appear as separate rows.
            ${rows.length === 50 ? ' Showing the most recent 50; older attempts may exist.' : ''}
          </p>
        </div>
        <div class="cl-siem-deliveries-actions">
          <label class="cl-audit-filter-field">
            <span>Status</span>
            <select
              value=${statusFilter}
              onChange=${(e) => setStatusFilter(e.target.value)}
              disabled=${loading}>
              <option value="">All</option>
              <option value="success">Delivered</option>
              <option value="retrying">Retrying</option>
              <option value="failed">Failed</option>
            </select>
          </label>
          <button class="btn btn-sm btn-tertiary" onClick=${load} disabled=${loading}>
            ${loading ? 'Loading…' : 'Refresh'}
          </button>
          <button class="btn btn-sm btn-tertiary" onClick=${onClose}>Close</button>
        </div>
      </header>

      <div class="cl-siem-deliveries-summary">
        <span class=${`cl-audit-chip ${failuresLast24h > 0 ? 'cl-audit-delivery-fail' : 'cl-audit-delivery-ok'}`}>
          ${failuresLast24h} failure${failuresLast24h === 1 ? '' : 's'} (last 24h, in window)
        </span>
        <span class="muted">${rows.length} attempt${rows.length === 1 ? '' : 's'} loaded.</span>
      </div>

      ${err ? html`<${ErrorRetry} message=${err} onRetry=${load} />` : null}
      ${loading && rows.length === 0 ? html`<${LoadingSkeleton} rows=${5} />` : null}
      ${!loading && !err && rows.length === 0 ? html`
        <${EmptyState}
          title="No delivery attempts yet"
          body="Deliveries appear here once matching audit events are emitted." />
      ` : null}
      ${rows.length > 0 ? html`
        <table class="cl-audit-table cl-siem-deliveries-table">
          <thead>
            <tr>
              <th>When</th>
              <th>Event</th>
              <th>Attempt</th>
              <th>Status</th>
              <th>HTTP</th>
              <th>Duration</th>
              <th>Error / signature</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((d) => {
              const meta = DELIVERY_STATUS_LABELS[d.status] || { label: d.status, cls: '' };
              return html`
                <tr key=${d.id}>
                  <td class="cl-audit-cell-ts">${fmtDateTime(d.attempted_at)}</td>
                  <td>
                    <span class="cl-audit-event-name">${formatAuditEventType(d.event_type)}</span>
                    ${d.audit_event_id
                      ? html`<div class="cl-audit-box-id">${d.audit_event_id}</div>`
                      : null}
                  </td>
                  <td class="cl-audit-confidence">#${d.attempt_number ?? 1}</td>
                  <td>
                    <span class=${`cl-audit-chip ${meta.cls}`}>${meta.label}</span>
                  </td>
                  <td class="cl-audit-confidence">${d.http_status_code ?? '—'}</td>
                  <td class="cl-audit-confidence">${d.duration_ms != null ? `${d.duration_ms}ms` : '—'}</td>
                  <td class="cl-audit-cell-error">
                    ${d.error_message
                      ? html`<span class="cl-siem-error">${d.error_message}</span>`
                      : (d.request_signature_prefix
                          ? html`<code class="cl-audit-box-id">${d.request_signature_prefix}…</code>`
                          : html`<span class="muted">—</span>`)}
                  </td>
                </tr>`;
            })}
          </tbody>
        </table>
      ` : null}
    </section>`;
}


function SiemSection({ api, orgId, refreshTrigger }) {
  const [expanded, setExpanded] = useState(false);
  const [webhooks, setWebhooks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [activeWebhookId, setActiveWebhookId] = useState(null);
  const [testStatus, setTestStatus] = useState({}); // { [webhookId]: 'ok' | 'failed' | 'sending' }

  const load = useCallback(async () => {
    if (!api || !orgId) return;
    setLoading(true);
    setErr(null);
    try {
      const resp = await api(
        `/api/workspace/webhooks?organization_id=${encodeURIComponent(orgId)}&active_only=false`
      );
      setWebhooks(Array.isArray(resp?.webhooks) ? resp.webhooks : []);
    } catch (exc) {
      setErr(String(exc?.message || exc));
    } finally {
      setLoading(false);
    }
  }, [api, orgId]);

  // Initial load only when expanded — keeps the audit page snappy for
  // the common case (operator opening to search, not to manage SIEM).
  useEffect(() => {
    if (expanded) load();
  }, [expanded, load, refreshTrigger]);

  const handleCreate = useCallback(async (payload) => {
    setSubmitting(true);
    try {
      await api(
        `/api/workspace/webhooks?organization_id=${encodeURIComponent(orgId)}`,
        { method: 'POST', body: JSON.stringify(payload) }
      );
      setShowForm(false);
      await load();
    } finally {
      setSubmitting(false);
    }
  }, [api, orgId, load]);

  const handleDelete = useCallback(async (webhook) => {
    if (!window.confirm(`Delete webhook ${webhook.url}?\n\nDelivery history is preserved.`)) return;
    try {
      await api(`/api/workspace/webhooks/${encodeURIComponent(webhook.id)}`, { method: 'DELETE' });
      if (activeWebhookId === webhook.id) setActiveWebhookId(null);
      await load();
    } catch (exc) {
      setErr(String(exc?.message || exc));
    }
  }, [api, activeWebhookId, load]);

  const handleTest = useCallback(async (webhook) => {
    setTestStatus((s) => ({ ...s, [webhook.id]: 'sending' }));
    try {
      const resp = await api(
        `/api/workspace/webhooks/${encodeURIComponent(webhook.id)}/test`,
        { method: 'POST' }
      );
      setTestStatus((s) => ({ ...s, [webhook.id]: resp?.delivered ? 'ok' : 'failed' }));
    } catch (exc) {
      setTestStatus((s) => ({ ...s, [webhook.id]: 'failed' }));
    } finally {
      // Auto-clear the chip after 6s so it doesn't linger.
      setTimeout(() => setTestStatus((s) => {
        const next = { ...s };
        delete next[webhook.id];
        return next;
      }), 6000);
    }
  }, [api]);

  const activeWebhook = webhooks.find((w) => w.id === activeWebhookId);

  return html`
    <section class=${`cl-siem-section${expanded ? ' is-expanded' : ''}`}>
      <header class="cl-siem-head">
        <button
          type="button"
          class="cl-siem-toggle"
          onClick=${() => setExpanded((v) => !v)}
          aria-expanded=${expanded}>
          <span class="cl-siem-chevron">${expanded ? '▾' : '▸'}</span>
          <span class="cl-siem-title">SIEM webhooks</span>
          <span class="muted">
            ${expanded ? '' : (webhooks.length > 0
                ? `${webhooks.length} configured`
                : 'forward audit events to Splunk, Datadog, Sumo, etc.')}
          </span>
        </button>
        ${expanded ? html`
          <div class="cl-siem-head-actions">
            <button
              class="btn btn-sm btn-primary"
              onClick=${() => setShowForm((v) => !v)}
              disabled=${submitting}>
              ${showForm ? 'Hide form' : '+ Add webhook'}
            </button>
            <button class="btn btn-sm btn-tertiary" onClick=${load} disabled=${loading}>
              ${loading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
        ` : null}
      </header>

      ${expanded ? html`
        <div class="cl-siem-body">
          ${showForm ? html`
            <${SiemWebhookForm}
              onSubmit=${handleCreate}
              onCancel=${() => setShowForm(false)}
              busy=${submitting} />
          ` : null}

          ${err ? html`<${ErrorRetry} message=${err} onRetry=${load} />` : null}
          ${loading && webhooks.length === 0 ? html`<${LoadingSkeleton} rows=${3} />` : null}
          ${!loading && !err && webhooks.length === 0 ? html`
            <${EmptyState}
              title="No SIEM webhooks configured"
              body="Add one to forward audit events to your security pipeline." />
          ` : null}

          ${webhooks.length > 0 ? html`
            <table class="cl-audit-table cl-siem-table">
              <thead>
                <tr>
                  <th>URL</th>
                  <th>Events</th>
                  <th>Status</th>
                  <th>Description</th>
                  <th class="cl-siem-actions-col">Actions</th>
                </tr>
              </thead>
              <tbody>
                ${webhooks.map((w) => {
                  const eventTypes = Array.isArray(w.event_types) ? w.event_types : [];
                  const eventLabel = eventTypes.includes('*')
                    ? 'All events'
                    : (eventTypes.length <= 2 ? eventTypes.map(formatAuditEventType).join(', ') : `${eventTypes.length} types`);
                  const status = testStatus[w.id];
                  return html`
                    <tr key=${w.id} class=${activeWebhookId === w.id ? 'is-active' : ''}>
                      <td><code class="cl-siem-url">${w.url}</code></td>
                      <td title=${eventTypes.join(', ')}>${eventLabel}</td>
                      <td>
                        <span class=${`cl-audit-chip ${w.is_active ? 'cl-audit-delivery-ok' : ''}`}>
                          ${w.is_active ? 'Active' : 'Inactive'}
                        </span>
                        ${status === 'sending' ? html`<span class="cl-audit-chip">Testing…</span>` : null}
                        ${status === 'ok' ? html`<span class="cl-audit-chip cl-audit-delivery-ok">Test OK</span>` : null}
                        ${status === 'failed' ? html`<span class="cl-audit-chip cl-audit-delivery-fail">Test failed</span>` : null}
                      </td>
                      <td class="cl-audit-cell-actor">${w.description || '—'}</td>
                      <td class="cl-siem-actions-col">
                        <button
                          class="btn btn-sm btn-tertiary"
                          onClick=${() => handleTest(w)}
                          disabled=${status === 'sending'}>
                          Test
                        </button>
                        <button
                          class="btn btn-sm btn-tertiary"
                          onClick=${() => setActiveWebhookId(activeWebhookId === w.id ? null : w.id)}>
                          ${activeWebhookId === w.id ? 'Hide log' : 'View log'}
                        </button>
                        <button
                          class="btn btn-sm btn-danger"
                          onClick=${() => handleDelete(w)}>
                          Delete
                        </button>
                      </td>
                    </tr>`;
                })}
              </tbody>
            </table>
          ` : null}

          ${activeWebhook ? html`
            <${SiemDeliveriesPanel}
              api=${api}
              orgId=${orgId}
              webhook=${activeWebhook}
              onClose=${() => setActiveWebhookId(null)} />
          ` : null}
        </div>
      ` : null}
    </section>`;
}


function ChainStatusBadge({ status, loading, onRefresh }) {
  const [open, setOpen] = useState(false);
  if (loading && !status) {
    return html`<span class="cl-chain-badge cl-chain-badge--loading">
      <span class="cl-chain-dot cl-chain-dot--loading"></span>
      Verifying chain…
    </span>`;
  }
  if (!status) return null;
  const isIntact = status.chain_intact === true;
  const isError = status.error || status.chain_intact === null;
  const dotClass = isError
    ? 'cl-chain-dot--error'
    : (isIntact ? 'cl-chain-dot--intact' : 'cl-chain-dot--broken');
  const label = isError
    ? 'Chain status unavailable'
    : (isIntact
        ? `Chain intact${status.chain_length ? ` · ${status.chain_length} events` : ''}`
        : 'Chain broken');
  const verifiedAt = status.verified_at
    ? new Date(status.verified_at).toLocaleTimeString()
    : null;
  return html`
    <span class="cl-chain-badge">
      <button
        class="cl-chain-badge-button"
        onClick=${() => setOpen((v) => !v)}
        title="Click for details"
      >
        <span class="cl-chain-dot ${dotClass}"></span>
        ${label}
      </button>
      ${open ? html`
        <div class="cl-chain-popover">
          <div class="cl-chain-popover-row">
            <span class="muted">Status</span>
            <strong>${isIntact ? 'Intact' : (isError ? 'Unavailable' : 'Broken')}</strong>
          </div>
          ${status.chain_length != null ? html`
            <div class="cl-chain-popover-row">
              <span class="muted">Chain length</span>
              <strong>${status.chain_length}</strong>
            </div>
          ` : null}
          ${status.verified_rows != null ? html`
            <div class="cl-chain-popover-row">
              <span class="muted">Verified rows</span>
              <strong>${status.verified_rows}</strong>
            </div>
          ` : null}
          ${verifiedAt ? html`
            <div class="cl-chain-popover-row">
              <span class="muted">Verified at</span>
              <strong>${verifiedAt}</strong>
            </div>
          ` : null}
          ${status.head_chain_seq ? html`
            <div class="cl-chain-popover-row">
              <span class="muted">Head seq</span>
              <strong>${status.head_chain_seq}</strong>
            </div>
          ` : null}
          ${status.head_hash_prefix ? html`
            <div class="cl-chain-popover-row">
              <span class="muted">Head hash</span>
              <code>${status.head_hash_prefix}…</code>
            </div>
          ` : null}
          ${status.genesis_hash_prefix ? html`
            <div class="cl-chain-popover-row">
              <span class="muted">Genesis</span>
              <code>${status.genesis_hash_prefix}…</code>
            </div>
          ` : null}
          ${!isIntact && !isError ? html`
            <div class="cl-chain-popover-row cl-chain-popover-row--break">
              <span class="muted">Broken at</span>
              <strong>seq ${status.broken_at_chain_seq}</strong>
            </div>
            <div class="cl-chain-popover-row cl-chain-popover-row--break">
              <span class="muted">Break kind</span>
              <strong>${formatToken(status.break_kind)}</strong>
            </div>
          ` : null}
          <div class="cl-chain-popover-actions">
            <button class="btn-secondary btn-sm" onClick=${onRefresh}>
              Re-verify
            </button>
          </div>
        </div>
      ` : null}
    </span>
  `;
}

function AuditHero({ events, pageIndex, chainStatus, chainLoading, refreshChainStatus, retention, onChangeRetention }) {
  const stats = auditStats(events);
  const retentionLabel = retention
    ? `${retention.effective_days} days`
    : 'Loading';
  const chainLabel = chainStatus?.chain_intact === false
    ? 'Broken'
    : (chainStatus?.chain_intact === true ? 'Intact' : 'Checking');

  return html`
    <section class="cl-audit-hero">
      <div class="cl-audit-hero-main">
        <div class="cl-audit-hero-copy">
          <span class="cl-audit-eyebrow">Governance trail</span>
          <h1>Audit log</h1>
          <p>
            Immutable record of workflow actions, policy decisions, exports, configuration changes,
            and the evidence trail behind work in progress.
          </p>
        </div>
        <div class="cl-audit-hero-actions">
          <${ChainStatusBadge}
            status=${chainStatus}
            loading=${chainLoading}
            onRefresh=${refreshChainStatus} />
          ${retention ? html`
            <span class="cl-audit-retention">
              <span>Retention</span>
              <strong>${retentionLabel}</strong>
              <span class="muted">(plan ceiling ${retention.tier_ceiling_days})</span>
            </span>
            <button class="btn-secondary btn-sm" onClick=${onChangeRetention}>Configure</button>
          ` : null}
        </div>
      </div>
      <div class="cl-audit-status-strip" aria-label="Current audit page summary">
        <div>
          <span>Shown</span>
          <strong>${stats.shown}</strong>
          <small>page ${pageIndex + 1}</small>
        </div>
        <div>
          <span>Work events</span>
          <strong>${stats.workflowEvents}</strong>
          <small>workflow, agent, ERP</small>
        </div>
        <div>
          <span>Control events</span>
          <strong>${stats.controlEvents}</strong>
          <small>blocked or failed</small>
        </div>
        <div>
          <span>Access events</span>
          <strong>${stats.accessEvents}</strong>
          <small>audit surface use</small>
        </div>
        <div>
          <span>Chain</span>
          <strong>${chainLabel}</strong>
          <small>${chainStatus?.chain_length ? `${chainStatus.chain_length} events` : 'tamper evidence'}</small>
        </div>
      </div>
    </section>
  `;
}


export default function AuditLogPage({ api, orgId, bootstrap }) {
  const [filters, setFilters] = useState({
    from_ts: '',
    to_ts: '',
    event_type_preset: '',
    box_type: '',
    actor_id: '',
    box_id: '',
  });
  const [events, setEvents] = useState([]);
  const [nextCursor, setNextCursor] = useState(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageCursors, setPageCursors] = useState([null]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [selected, setSelected] = useState(null);
  const [exportState, setExportState] = useState(null);
  const [retention, setRetention] = useState(null);
  useEffect(() => {
    let cancelled = false;
    api(`/api/workspace/audit/retention?organization_id=${encodeURIComponent(orgId)}`)
      .then((r) => { if (!cancelled) setRetention(r); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [api, orgId]);

  const [chainStatus, setChainStatus] = useState(null);
  const [chainLoading, setChainLoading] = useState(true);
  const refreshChainStatus = useCallback(() => {
    setChainLoading(true);
    api(`/api/workspace/audit/chain-status`)
      .then((r) => setChainStatus(r))
      .catch(() => setChainStatus({ chain_intact: null, error: true }))
      .finally(() => setChainLoading(false));
  }, [api]);
  useEffect(() => { refreshChainStatus(); }, [refreshChainStatus]);
  const onChangeRetention = useCallback(async () => {
    if (!retention) return;
    const current = retention.configured_days || retention.tier_ceiling_days;
    const raw = window.prompt(
      `Audit retention (days). Plan ceiling: ${retention.tier_ceiling_days} days. Min 30.`,
      String(current),
    );
    if (raw === null) return;
    const days = parseInt(raw, 10);
    if (!Number.isFinite(days) || days < 30) {
      window.alert('Retention must be at least 30 days.');
      return;
    }
    try {
      const next = await api(`/api/workspace/audit/retention`, {
        method: 'PATCH',
        body: { organization_id: orgId, days },
      });
      setRetention(next);
    } catch (exc) {
      const detail = exc?.payload?.detail;
      const msg = (detail && detail.message) || exc?.message || 'Update failed';
      window.alert(msg);
    }
  }, [api, orgId, retention]);

  const buildQuery = useCallback((cur) => {
    const params = new URLSearchParams();
    params.set('organization_id', orgId);
    params.set('limit', String(PAGE_SIZE));
    if (filters.from_ts) {
      params.set('from_ts', new Date(filters.from_ts).toISOString());
    }
    if (filters.to_ts) {
      params.set('to_ts', new Date(filters.to_ts).toISOString());
    }
    if (filters.event_type_preset) {
      params.set('event_type', filters.event_type_preset);
    }
    if (filters.actor_id) params.set('actor_id', filters.actor_id.trim());
    if (filters.box_type) params.set('box_type', filters.box_type);
    if (filters.box_id) params.set('box_id', filters.box_id.trim());
    if (cur) params.set('cursor', cur);
    return params.toString();
  }, [filters, orgId]);

  const fetchPage = useCallback(async ({ useCursor = null, targetPage = 0, cursorTrail = null } = {}) => {
    if (!api || !orgId) return;
    setLoading(true);
    setErr(null);
    try {
      const resp = await api(`/api/workspace/audit/search?${buildQuery(useCursor)}`);
      const pageEvents = Array.isArray(resp?.events) ? resp.events : [];
      setEvents(pageEvents);
      setNextCursor(resp?.next_cursor || null);
      setPageIndex(targetPage);
      if (Array.isArray(cursorTrail)) {
        setPageCursors(cursorTrail);
      }
    } catch (exc) {
      setErr(String(exc?.message || exc));
    } finally {
      setLoading(false);
    }
  }, [api, orgId, buildQuery]);

  const onApply = useCallback(() => {
    setSelected(null);
    const cursorTrail = [null];
    setNextCursor(null);
    setPageCursors(cursorTrail);
    fetchPage({ useCursor: null, targetPage: 0, cursorTrail });
  }, [fetchPage]);

  const onReset = useCallback(() => {
    setFilters({
      from_ts: '',
      to_ts: '',
      event_type_preset: '',
      box_type: '',
      actor_id: '',
      box_id: '',
    });
    setSelected(null);
    setNextCursor(null);
    setPageIndex(0);
    setPageCursors([null]);
  }, []);

  const onPreviousPage = useCallback(() => {
    if (pageIndex <= 0 || loading) return;
    const targetPage = pageIndex - 1;
    const cursorTrail = pageCursors.slice(0, targetPage + 1);
    setSelected(null);
    fetchPage({
      useCursor: cursorTrail[targetPage] || null,
      targetPage,
      cursorTrail,
    });
  }, [pageIndex, pageCursors, loading, fetchPage]);

  const onNextPage = useCallback(() => {
    if (!nextCursor || loading) return;
    const targetPage = pageIndex + 1;
    const cursorTrail = pageCursors.slice(0, targetPage);
    cursorTrail[targetPage] = nextCursor;
    setSelected(null);
    fetchPage({
      useCursor: nextCursor,
      targetPage,
      cursorTrail,
    });
  }, [nextCursor, pageIndex, pageCursors, loading, fetchPage]);

  useEffect(() => {
    fetchPage({ useCursor: null, targetPage: 0, cursorTrail: [null] });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onExport = useCallback(async (format) => {
    if (!api || !orgId) return;

    // Already done? Trigger the download.
    if (exportState && exportState.status === 'done' && exportState.job_id) {
      const url = `/api/workspace/audit/exports/${encodeURIComponent(exportState.job_id)}?organization_id=${encodeURIComponent(orgId)}&download=true`;
      try {
        const resp = await fetch(url, { credentials: 'same-origin' });
        if (!resp.ok) {
          throw new Error(`download failed: ${resp.status}`);
        }
        const blob = await resp.blob();
        const objUrl = URL.createObjectURL(blob);
        const ext = exportState.export_format || exportState.format || 'csv';
        const filename = exportState.content_filename || `audit-${orgId}-${Date.now()}.${ext}`;
        const a = document.createElement('a');
        a.href = objUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(objUrl);
      } catch (exc) {
        setExportState({ ...exportState, status: 'failed', error_message: String(exc?.message || exc) });
      }
      return;
    }

    const exportFormat = format === 'pdf' ? 'pdf' : 'csv';
    const filtersPayload = {
      organization_id: orgId,
      from_ts: filters.from_ts ? new Date(filters.from_ts).toISOString() : null,
      to_ts: filters.to_ts ? new Date(filters.to_ts).toISOString() : null,
      event_types: filters.event_type_preset
        ? filters.event_type_preset.split(',').map((s) => s.trim()).filter(Boolean)
        : null,
      actor_id: filters.actor_id?.trim() || null,
      box_type: filters.box_type || null,
      box_id: filters.box_id?.trim() || null,
      format: exportFormat,
    };
    try {
      const resp = await api('/api/workspace/audit/export', {
        method: 'POST',
        body: JSON.stringify(filtersPayload),
      });
      setExportState({
        job_id: resp.job_id,
        status: resp.status || 'queued',
        export_format: exportFormat,
      });
    } catch (exc) {
      setExportState({ status: 'failed', error_message: String(exc?.message || exc), export_format: exportFormat });
    }
  }, [api, orgId, exportState, filters]);

  useEffect(() => {
    if (!exportState || !exportState.job_id) return undefined;
    if (exportState.status !== 'queued' && exportState.status !== 'running') return undefined;

    let cancelled = false;
    const tick = async () => {
      try {
        const resp = await api(
          `/api/workspace/audit/exports/${encodeURIComponent(exportState.job_id)}?organization_id=${encodeURIComponent(orgId)}`
        );
        if (cancelled) return;
        setExportState((prev) => {
          if (!prev || prev.job_id !== exportState.job_id) return prev;
          return { ...prev, ...resp };
        });
      } catch (exc) {
        if (cancelled) return;
        setExportState((prev) => prev && prev.job_id === exportState.job_id
          ? { ...prev, status: 'failed', error_message: String(exc?.message || exc) }
          : prev,
        );
      }
    };
    const id = setInterval(tick, 2000);
    // Fire once immediately so a fast 'done' flip isn't waiting 2s.
    tick();
    return () => { cancelled = true; clearInterval(id); };
  }, [api, orgId, exportState?.job_id, exportState?.status]);

  const empty = !loading && !err && events.length === 0;

  return html`
    <div class="cl-audit-page">
      <${AuditHero}
        events=${events}
        pageIndex=${pageIndex}
        chainStatus=${chainStatus}
        chainLoading=${chainLoading}
        refreshChainStatus=${refreshChainStatus}
        retention=${retention}
        onChangeRetention=${onChangeRetention} />

      <${SiemSection} api=${api} orgId=${orgId} />

      <${FilterBar}
        filters=${filters}
        setFilters=${setFilters}
        onApply=${onApply}
        onReset=${onReset}
        onExport=${onExport}
        exportState=${exportState}
        busy=${loading} />

      <div class=${`cl-audit-layout${selected ? ' has-detail' : ''}`}>
        <div class="cl-audit-table-wrap">
          ${err ? html`<${ErrorRetry} message=${err} onRetry=${onApply} />` : null}
          ${loading && events.length === 0 ? html`<${LoadingSkeleton} rows=${10} />` : null}
          ${empty ? html`
            <${EmptyState}
              title="No matching events"
              body="Adjust filters or expand the date range." />
          ` : null}
          ${events.length > 0 ? html`
            <table class="cl-audit-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Type</th>
                  <th>Event</th>
                  <th>Actor</th>
                  <th>Record</th>
                  <th>Integrity</th>
                </tr>
              </thead>
              <tbody>
                ${events.map((event) => html`
                  <${EventRow}
                    key=${event.id}
                    event=${event}
                    isActive=${selected?.id === event.id}
                    onSelect=${setSelected} />
                `)}
              </tbody>
            </table>
            <div class="cl-audit-mobile-list">
              ${events.map((event) => {
                const outcomeMeta = getOutcomeMeta(event);
                const category = getEventCategory(event);
                const source = getEventSource(event);
                return html`
                  <button
                    type="button"
                    key=${event.id}
                    class=${`cl-audit-mobile-card${selected?.id === event.id ? ' is-active' : ''}`}
                    onClick=${() => setSelected(event)}>
                    <span class="cl-audit-mobile-card-head">
                      <span>
                        <strong>${formatAuditEventType(event.event_type)}</strong>
                        <small>${fmtDateTime(event.ts)}</small>
                      </span>
                      <span class=${`cl-audit-type-pill ${category.cls}`}>${category.label}</span>
                    </span>
                    <span class="cl-audit-mobile-context">${getEventContextLine(event)}</span>
                    ${source ? html`
                      <span class="cl-audit-mobile-card-row">
                        <span>Surface</span>
                        <strong>${source}</strong>
                      </span>
                    ` : null}
                    <span class="cl-audit-mobile-card-row">
                      <span>Record</span>
                      <strong>${formatRecordType(event.box_type)} ${event.box_id || ''}</strong>
                    </span>
                    <span class="cl-audit-mobile-card-row">
                      <span>Actor</span>
                      <strong>${formatActor(event.actor_id, event.actor_type)}</strong>
                    </span>
                    ${event.prev_state || event.new_state ? html`
                      <span class="cl-audit-mobile-card-row">
                        <span>State</span>
                        <strong>${formatState(event.prev_state)} → ${formatState(event.new_state)}</strong>
                      </span>
                    ` : null}
                    ${typeof event.agent_confidence === 'number' ? html`
                      <span class="cl-audit-mobile-card-row">
                        <span>Confidence</span>
                        <strong>${formatConfidence(event.agent_confidence)}</strong>
                      </span>
                    ` : null}
                    <span class="cl-audit-mobile-card-row">
                      <span>Outcome</span>
                      <strong><span class=${`cl-audit-chip ${outcomeMeta.cls}`}>${outcomeMeta.label}</span></strong>
                    </span>
                  </button>`;
              })}
            </div>
            <div class="cl-audit-pagination">
              <span class="muted">
                Page ${pageIndex + 1} · ${events.length} event${events.length === 1 ? '' : 's'} shown · ${PAGE_SIZE} per page
              </span>
              <div class="cl-audit-page-controls" aria-label="Audit log pagination">
                <button class="btn btn-sm btn-tertiary" onClick=${onPreviousPage} disabled=${loading || pageIndex === 0}>
                  Previous
                </button>
                <button class="btn btn-sm btn-tertiary" onClick=${onNextPage} disabled=${loading || !nextCursor}>
                  ${loading ? 'Loading…' : 'Next'}
                </button>
              </div>
              ${!nextCursor ? html`<span class="muted">End of results.</span>` : null}
            </div>
          ` : null}
        </div>
        ${selected ? html`
          <${DetailPanel}
            event=${selected}
            api=${api}
            orgId=${orgId}
            onClose=${() => setSelected(null)} />
        ` : null}
      </div>
    </div>`;
}
