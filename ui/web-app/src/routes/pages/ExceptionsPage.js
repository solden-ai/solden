import { useState, useEffect, useCallback, useMemo } from 'preact/hooks';
import { html } from '../../utils/htm.js';
import { formatAmount } from '../../utils/formatters.js';
import { hasBoxCapability } from '../../utils/capabilities.js';
import { accountPayableRecordPath } from '../../utils/record-route.js';

const SEVERITIES = ['critical', 'high', 'medium', 'low'];
const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };
const PAGE_SIZE = 12;

function humanizeExceptionType(code) {
  if (!code) return 'Exception raised';
  return String(code).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function humanizeWorkType(code) {
  const token = String(code || '').trim().toLowerCase();
  const labels = {
    ap_item: 'Accounts Payable',
    purchase_order: 'Procurement',
    vendor_onboarding_session: 'Vendor Onboarding',
    bank_match: 'Bank Reconciliation',
  };
  if (!token) return 'Record';
  return labels[token] || token.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatTimeAgo(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const hours = Math.floor((Date.now() - d.getTime()) / 3600000);
    if (hours < 1) return 'just now';
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    return `${days}d`;
  } catch { return ''; }
}

function rowHeadline(row = {}) {
  const summary = row.box_summary || {};
  const metadata = row.metadata || {};
  const vendor = row.vendor_name || row.vendor || summary.vendor_name || metadata.vendor_name;
  const reference = summary.invoice_number || summary.reference || summary.po_number || summary.bill_number || row.box_id;
  if (vendor && reference) return `${vendor} - ${reference}`;
  if (vendor) return vendor;
  if (reference) return `${humanizeWorkType(row.box_type)} - ${String(reference).slice(0, 18)}`;
  return 'Record not summarized';
}

function rowDetail(row = {}) {
  const summary = row.box_summary || {};
  const amountLabel = (summary.amount != null && summary.amount !== '')
    ? formatAmount(summary.amount, summary.currency)
    : '';
  return {
    workType: humanizeWorkType(row.box_type),
    type: humanizeExceptionType(row.exception_type),
    age: formatTimeAgo(row.raised_at),
    amount: amountLabel,
  };
}

function rowReason(row = {}) {
  const reason = String(row.reason || '').trim();
  const suggested = String(row.metadata?.suggested_action || '').trim();
  const code = String(row.exception_type || '').toLowerCase();
  if (suggested) return suggested;
  if (reason && reason.toLowerCase() !== code) return reason;
  return '';
}

function exceptionTarget(row = {}) {
  if (row.box_type === 'ap_item' && row.box_id) {
    return { path: accountPayableRecordPath(row.box_id), label: 'Open record' };
  }
  if ((row.synthetic || row.box_type === 'vendor_onboarding_session') && row.metadata?.vendor_name) {
    return { path: `/vendors/${encodeURIComponent(row.metadata.vendor_name)}`, label: 'Open vendor' };
  }
  if (row.box_type === 'purchase_order') {
    return { path: '/procurement', label: 'Open procurement' };
  }
  return null;
}

function canResolveException(row, bootstrap) {
  if (!row || row.synthetic || row.box_type !== 'ap_item') return false;
  return hasBoxCapability(bootstrap, 'ap_item', 'approve_invoice');
}

function optionCount(stats, bucket, key, fallbackItems, fallbackSelector) {
  const value = stats?.[bucket]?.[key];
  if (value !== undefined && value !== null) return Number(value) || 0;
  return fallbackItems.filter((row) => fallbackSelector(row) === key).length;
}

function buildOptions(stats, items, bucket, selector, humanize) {
  const keys = new Set(Object.keys(stats?.[bucket] || {}));
  for (const row of items) {
    const key = selector(row);
    if (key) keys.add(key);
  }
  return Array.from(keys)
    .filter(Boolean)
    .map((key) => ({
      key,
      label: humanize(key),
      count: optionCount(stats, bucket, key, items, selector),
    }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

function oldestWait(items) {
  let oldestMs = 0;
  let oldestIso = '';
  for (const row of items || []) {
    const t = new Date(row.raised_at || '').getTime();
    if (!Number.isFinite(t)) continue;
    const ageMs = Date.now() - t;
    if (ageMs > oldestMs) {
      oldestMs = ageMs;
      oldestIso = row.raised_at;
    }
  }
  return oldestIso ? formatTimeAgo(oldestIso) : '';
}

function activateOnKey(event, activate) {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  event.preventDefault();
  activate?.();
}

export default function ExceptionsPage({ api, navigate, bootstrap }) {
  const [items, setItems] = useState(null);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [resolvingId, setResolvingId] = useState(null);
  const [severityFilter, setSeverityFilter] = useState('');
  const [workTypeFilter, setWorkTypeFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [query, setQuery] = useState('');
  const [pageOffset, setPageOffset] = useState(0);
  const [pageMeta, setPageMeta] = useState({
    total: 0,
    limit: PAGE_SIZE,
    offset: 0,
    hasMore: false,
  });
  const [resolveDialog, setResolveDialog] = useState(null);

  const load = useCallback(async () => {
    if (!api) return;
    try {
      const params = new URLSearchParams();
      params.set('limit', String(PAGE_SIZE));
      params.set('offset', String(pageOffset));
      if (severityFilter) params.set('severity', severityFilter);
      if (workTypeFilter) params.set('box_type', workTypeFilter);
      if (typeFilter) params.set('exception_type', typeFilter);
      if (query.trim()) params.set('q', query.trim());
      const suffix = params.toString();
      const [listRes, statsRes] = await Promise.all([
        api(`/api/workspace/exceptions${suffix ? `?${suffix}` : ''}`),
        api('/api/workspace/exceptions/stats'),
      ]);
      const nextItems = Array.isArray(listRes?.items) ? listRes.items : [];
      const nextTotal = Number(listRes?.total ?? listRes?.count ?? nextItems.length) || 0;
      if (pageOffset > 0 && nextTotal > 0 && nextItems.length === 0) {
        setPageOffset(Math.max(0, pageOffset - PAGE_SIZE));
        return;
      }
      setItems(nextItems);
      setPageMeta({
        total: nextTotal,
        limit: Number(listRes?.limit || PAGE_SIZE),
        offset: Number(listRes?.offset || pageOffset),
        hasMore: Boolean(listRes?.has_more),
      });
      setStats(statsRes || null);
      setError(null);
    } catch (exc) {
      setError(String(exc?.message || exc));
    }
  }, [api, pageOffset, query, severityFilter, typeFilter, workTypeFilter]);

  useEffect(() => { load(); }, [load]);

  const allItems = Array.isArray(items) ? items : [];
  const workTypeOptions = useMemo(
    () => buildOptions(stats, allItems, 'by_box_type', (row) => String(row.box_type || ''), humanizeWorkType),
    [stats, allItems],
  );
  const typeOptions = useMemo(
    () => buildOptions(stats, allItems, 'by_type', (row) => String(row.exception_type || ''), humanizeExceptionType),
    [stats, allItems],
  );

  const visibleItems = useMemo(() => (
    allItems.slice().sort((a, b) => {
      const sa = SEVERITY_ORDER[a.severity] ?? 99;
      const sb = SEVERITY_ORDER[b.severity] ?? 99;
      if (sa !== sb) return sa - sb;
      const raised = String(a.raised_at || '').localeCompare(String(b.raised_at || ''));
      if (raised !== 0) return raised;
      return String(a.id || '').localeCompare(String(b.id || ''));
    })
  ), [allItems]);

  const totalUnresolved = Number(stats?.total_unresolved ?? allItems.length ?? 0);
  const highPressure = Number(stats?.by_severity?.critical || 0) + Number(stats?.by_severity?.high || 0);
  const workTypesAffected = workTypeOptions.filter((item) => item.count > 0).length;
  const oldest = oldestWait(allItems);
  const activeFilterCount = [severityFilter, workTypeFilter, typeFilter, query.trim()].filter(Boolean).length;
  const isLoading = items === null;
  const totalMatching = Number(pageMeta.total || 0);
  const pageStart = totalMatching && visibleItems.length ? Number(pageMeta.offset || 0) + 1 : 0;
  const pageEnd = totalMatching && visibleItems.length ? Number(pageMeta.offset || 0) + visibleItems.length : 0;
  const hasPreviousPage = Number(pageMeta.offset || 0) > 0;
  const hasNextPage = Boolean(pageMeta.hasMore) || pageEnd < totalMatching;

  const resetFilters = () => {
    setSeverityFilter('');
    setWorkTypeFilter('');
    setTypeFilter('');
    setQuery('');
    setPageOffset(0);
  };

  const updateSeverityFilter = (value) => {
    setSeverityFilter(value);
    setPageOffset(0);
  };

  const updateWorkTypeFilter = (value) => {
    setWorkTypeFilter(value);
    setPageOffset(0);
  };

  const updateTypeFilter = (value) => {
    setTypeFilter(value);
    setPageOffset(0);
  };

  const updateQuery = (value) => {
    setQuery(value);
    setPageOffset(0);
  };

  const goPreviousPage = () => {
    setPageOffset((current) => Math.max(0, current - PAGE_SIZE));
  };

  const goNextPage = () => {
    if (!hasNextPage) return;
    setPageOffset((current) => current + PAGE_SIZE);
  };

  const openResolveDialog = (exceptionId) => setResolveDialog({ id: exceptionId, note: '' });
  const cancelResolveDialog = () => setResolveDialog(null);

  const submitResolveDialog = async () => {
    if (!api || !resolveDialog?.id) return;
    const note = String(resolveDialog.note || '').trim();
    if (!note) return;
    const exceptionId = resolveDialog.id;
    setResolveDialog(null);
    setResolvingId(exceptionId);
    try {
      await api(`/api/workspace/exceptions/${exceptionId}/resolve`, {
        method: 'POST',
        body: { resolution_note: note },
      });
      await load();
    } catch (exc) {
      setError(String(exc?.message || exc));
    } finally {
      setResolvingId(null);
    }
  };

  const navigateTo = (target) => {
    if (!target?.path || !navigate) return;
    navigate(target.path);
  };

  return html`
    <div class="cl-exceptions-page">
      <header class="cl-exceptions-head">
        <div>
          <div class="cl-exceptions-eyebrow">Exception queue</div>
          <h1 class="cl-exceptions-title">Work waiting on judgment</h1>
          <p class="cl-exceptions-sub">
            Exceptions across every work type that need context, owner action, or proof before the agent can continue.
          </p>
        </div>
        <div class="cl-exceptions-actions">
          <button class="btn-secondary btn-sm" onClick=${load}>Refresh</button>
          <button class="btn-primary btn-sm" onClick=${() => navigate?.('/activity')}>Open activity</button>
        </div>
      </header>

      ${error ? html`
        <div class="cl-exceptions-alert" role="alert">
          ${error}
        </div>
      ` : null}

      <section class="cl-exceptions-summary" aria-label="Exception summary">
        <${SummaryCell} label="Unresolved" value=${totalUnresolved} sub=${totalUnresolved === 1 ? 'Open exception' : 'Open exceptions'} tone="brand" />
        <${SummaryCell} label="Critical / high" value=${highPressure} sub=${highPressure ? 'Needs first attention' : 'No severe pressure'} tone=${highPressure ? 'warn' : 'good'} />
        <${SummaryCell} label="Work types" value=${workTypesAffected || '—'} sub=${workTypesAffected ? 'Affected queues' : 'No affected queues'} />
        <${SummaryCell} label="Oldest wait" value=${oldest || '—'} sub=${oldest ? 'Waiting for action' : 'No wait'} />
      </section>

      <section class="cl-exceptions-layout">
        <div class="cl-exceptions-main">
          <div class="cl-exceptions-panel">
            <div class="cl-exceptions-toolbar">
              <div class="cl-exceptions-toolbar-main">
                <label class="cl-exceptions-filter">
                  <span>Severity</span>
                  <select value=${severityFilter} onChange=${(event) => updateSeverityFilter(event.target.value)}>
                    <option value="">All</option>
                    ${SEVERITIES.map((severity) => html`
                      <option key=${severity} value=${severity}>${severity}</option>
                    `)}
                  </select>
                </label>
                <label class="cl-exceptions-filter">
                  <span>Work type</span>
                  <select value=${workTypeFilter} onChange=${(event) => updateWorkTypeFilter(event.target.value)}>
                    <option value="">All</option>
                    ${workTypeOptions.map((option) => html`
                      <option key=${option.key} value=${option.key}>${option.label}</option>
                    `)}
                  </select>
                </label>
                <label class="cl-exceptions-filter">
                  <span>Exception</span>
                  <select value=${typeFilter} onChange=${(event) => updateTypeFilter(event.target.value)}>
                    <option value="">All</option>
                    ${typeOptions.map((option) => html`
                      <option key=${option.key} value=${option.key}>${option.label}</option>
                    `)}
                  </select>
                </label>
              </div>
              <label class="cl-exceptions-search">
                <span>Search</span>
                <input
                  value=${query}
                  onInput=${(event) => updateQuery(event.target.value)}
                  placeholder="Vendor, reference, reason"
                />
              </label>
            </div>

            <div class="cl-exceptions-list-head">
              <h2>Open exceptions</h2>
              <div class="cl-exceptions-list-meta">
                ${isLoading
                  ? 'Loading'
                  : totalMatching
                    ? `Showing ${pageStart}-${pageEnd} of ${totalMatching}`
                    : '0 shown'}
                ${activeFilterCount ? html`
                  <button class="cl-exceptions-reset" onClick=${resetFilters}>Reset filters</button>
                ` : null}
              </div>
            </div>

            ${isLoading
              ? html`<div class="cl-exceptions-empty">Loading exceptions...</div>`
              : visibleItems.length === 0
                ? html`
                    <div class="cl-exceptions-empty">
                      <div class="cl-exceptions-empty-title">No exceptions match the current filters.</div>
                      <button class="btn-secondary btn-sm" onClick=${resetFilters}>Reset filters</button>
                    </div>
                  `
                : html`
                    <ul class="cl-exceptions-list">
                      ${visibleItems.map((row) => {
                        const detail = rowDetail(row);
                        const reason = rowReason(row);
                        const target = exceptionTarget(row);
                        const canResolve = canResolveException(row, bootstrap);
                        const activate = () => navigateTo(target);
                        return html`
                          <li
                            key=${row.id || row.exception_id || row.box_id}
                            class=${`cl-exceptions-row cl-exceptions-row-${row.severity || 'medium'} ${target ? 'cl-exceptions-row-clickable' : ''}`}
                            onClick=${target ? activate : undefined}
                            onKeyDown=${target ? (event) => activateOnKey(event, activate) : undefined}
                            role=${target ? 'button' : undefined}
                            tabindex=${target ? 0 : undefined}
                          >
                            <div class="cl-exceptions-row-main">
                              <div class="cl-exceptions-row-line">
                                <span class=${`cl-exceptions-severity-dot cl-exceptions-severity-dot-${row.severity || 'medium'}`} aria-hidden="true"></span>
                                <div class="cl-exceptions-row-copy">
                                  <div class="cl-exceptions-row-title">${rowHeadline(row)}</div>
                                  <div class="cl-exceptions-row-meta">
                                    ${detail.workType} · ${detail.type}
                                    ${detail.age ? html` · ${detail.age} waiting` : null}
                                  </div>
                                </div>
                              </div>
                              ${reason ? html`<div class="cl-exceptions-row-reason">${reason}</div>` : null}
                            </div>
                            <div class="cl-exceptions-row-side" onClick=${(event) => event.stopPropagation()}>
                              ${detail.amount ? html`<div class="cl-exceptions-row-amount">${detail.amount}</div>` : null}
                              <span class=${`cl-exceptions-pill cl-exceptions-pill-${row.severity || 'medium'}`}>
                                ${row.severity || 'medium'}
                              </span>
                              <div class="cl-exceptions-row-actions">
                                ${canResolve ? html`
                                  <button
                                    class="btn-primary btn-sm"
                                    disabled=${resolvingId === row.id}
                                    onClick=${() => openResolveDialog(row.id)}
                                  >
                                    ${resolvingId === row.id ? 'Resolving...' : 'Resolve'}
                                  </button>
                                ` : null}
                                ${target ? html`
                                  <button class="btn-secondary btn-sm" onClick=${() => navigateTo(target)}>
                                    ${target.label}
                                  </button>
                                ` : null}
                              </div>
                            </div>
                          </li>
                        `;
                      })}
                    </ul>
                  `}

            ${!isLoading && totalMatching > Number(pageMeta.limit || PAGE_SIZE) ? html`
              <div class="cl-exceptions-pagination" aria-label="Exceptions pagination">
                <div class="cl-exceptions-page-count">
                  ${pageStart}-${pageEnd} of ${totalMatching}
                </div>
                <div class="cl-exceptions-page-controls">
                  <button
                    class="btn-secondary btn-sm"
                    disabled=${!hasPreviousPage}
                    onClick=${goPreviousPage}
                  >Previous</button>
                  <button
                    class="btn-secondary btn-sm"
                    disabled=${!hasNextPage}
                    onClick=${goNextPage}
                  >Next</button>
                </div>
              </div>
            ` : null}
          </div>
        </div>

        <aside class="cl-exceptions-side">
          <${BreakdownPanel}
            title="By severity"
            items=${SEVERITIES.map((severity) => ({
              key: severity,
              label: severity,
              count: Number(stats?.by_severity?.[severity] || 0),
            }))}
            active=${severityFilter}
            onSelect=${(key) => updateSeverityFilter(key === severityFilter ? '' : key)}
            tone="severity"
          />
          <${BreakdownPanel}
            title="By work type"
            items=${workTypeOptions}
            active=${workTypeFilter}
            onSelect=${(key) => updateWorkTypeFilter(key === workTypeFilter ? '' : key)}
          />
          <${BreakdownPanel}
            title="By exception"
            items=${typeOptions.slice(0, 8)}
            active=${typeFilter}
            onSelect=${(key) => updateTypeFilter(key === typeFilter ? '' : key)}
          />
        </aside>
      </section>

      ${resolveDialog ? html`
        <div class="cl-modal-overlay" onClick=${cancelResolveDialog}>
          <div
            class="cl-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="cl-resolve-title"
            onClick=${(event) => event.stopPropagation()}
          >
            <h3 id="cl-resolve-title" class="cl-modal-title">Resolve exception</h3>
            <div class="cl-modal-body">
              Add the note that explains why this can leave the queue.
            </div>
            <div class="field-row">
              <label for="cl-resolve-note">Resolution note</label>
              <textarea
                id="cl-resolve-note"
                autofocus
                value=${resolveDialog.note}
                onInput=${(event) => setResolveDialog((prev) => ({ ...prev, note: event.target.value }))}
                placeholder="Vendor confirmed the corrected bank detail."
              ></textarea>
            </div>
            <div class="cl-modal-actions">
              <button class="btn-secondary btn-sm" onClick=${cancelResolveDialog}>Cancel</button>
              <button
                class="btn-primary btn-sm"
                disabled=${!String(resolveDialog.note || '').trim()}
                onClick=${submitResolveDialog}
              >Resolve</button>
            </div>
          </div>
        </div>
      ` : null}
    </div>
  `;
}

function SummaryCell({ label, value, sub, tone = 'neutral' }) {
  return html`
    <div class=${`cl-exceptions-summary-cell cl-exceptions-summary-cell-${tone}`}>
      <div class="cl-exceptions-summary-label">${label}</div>
      <div class="cl-exceptions-summary-value">${value}</div>
      <div class="cl-exceptions-summary-sub">${sub}</div>
    </div>
  `;
}

function BreakdownPanel({ title, items, active, onSelect, tone = 'neutral' }) {
  const visible = (items || []).filter((item) => Number(item.count || 0) > 0);
  return html`
    <div class="cl-exceptions-breakdown">
      <h2>${title}</h2>
      ${visible.length
        ? html`
            <ul class="cl-exceptions-breakdown-list">
              ${visible.map((item) => html`
                <li key=${item.key}>
                  <button
                    class=${`cl-exceptions-breakdown-row ${active === item.key ? 'is-active' : ''}`}
                    onClick=${() => onSelect?.(item.key)}
                  >
                    <span class="cl-exceptions-breakdown-label">
                      ${tone === 'severity' ? html`
                        <span class=${`cl-exceptions-severity-dot cl-exceptions-severity-dot-${item.key}`} aria-hidden="true"></span>
                      ` : null}
                      ${item.label}
                    </span>
                    <span class="cl-exceptions-breakdown-count">${item.count}</span>
                  </button>
                </li>
              `)}
            </ul>
          `
        : html`<div class="cl-exceptions-breakdown-empty">No data.</div>`}
    </div>
  `;
}
