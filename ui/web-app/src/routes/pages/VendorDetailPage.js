/**
 * Vendor detail — Module 4 §154.
 *
 * The leader's per-vendor screen: ERP data (name, address, tax ID,
 * terms) plus the Solden layer (verified IBANs, fraud flags,
 * custom routing, agent confidence) plus recent invoice history and
 * exception trend.
 *
 * Backed by GET /api/ap/items/vendors/{name} which returns a
 * comprehensive payload merged from vendor_profiles + ERP-side data
 * + recent invoice rollups + exception counts. The page is a thin
 * renderer over that payload.
 */
import { h } from 'preact';
import { useCallback, useEffect, useState } from 'preact/hooks';
import htm from 'htm';
import { fmtDate, fmtDateTime } from '../route-helpers.js';
import {
  formatAmount,
  getExceptionLabel,
  getStateLabel,
  humanizeSnakeText,
} from '../../utils/formatters.js';
import { accountPayableRecordPath } from '../../utils/record-route.js';

const html = htm.bind(h);

const VENDOR_SOURCE_LABELS = {
  attachment: 'Invoice attachment',
  bank_details: 'Bank details',
  bank_verification: 'Bank verification',
  companies_house: 'Companies House',
  email: 'Email',
  erp: 'ERP',
  invoice: 'Invoice',
  manual: 'Manual review',
  opencorporates: 'OpenCorporates',
  parser: 'Current invoice parse',
  vendor_portal: 'Vendor portal',
};

function formatVendorSourceLabel(source) {
  const token = String(source || '').trim().toLowerCase().replace(/[-\s]+/g, '_');
  if (!token) return '';
  return VENDOR_SOURCE_LABELS[token] || humanizeSnakeText(token);
}

function formatVendorStatusLabel(status) {
  const token = String(status || '').trim().toLowerCase();
  if (!token) return 'Active';
  if (token === 'active') return 'Active';
  if (token === 'blocked') return 'Blocked';
  if (token === 'archived') return 'Archived';
  if (token === 'verified') return 'Verified';
  if (token === 'unverified') return 'Unverified';
  if (token === 'pending') return 'Pending';
  if (token === 'frozen') return 'Frozen';
  return humanizeSnakeText(token);
}

function formatApStateLabel(state) {
  const token = String(state || '').trim().toLowerCase();
  if (!token) return 'Unknown';
  return token === 'received' || getStateLabel(token) !== 'Received'
    ? getStateLabel(token)
    : humanizeSnakeText(token);
}

function getFraudFlagToken(flag) {
  if (typeof flag === 'string') return flag;
  if (!flag || typeof flag !== 'object') return '';
  return flag.flag_type || flag.type || flag.code || '';
}

function getFraudFlagMessage(flag) {
  if (!flag || typeof flag !== 'object') return '';
  return String(flag.note || flag.message || flag.reason || '').trim();
}

function getFraudFlagDate(flag) {
  if (!flag || typeof flag !== 'object') return '';
  return flag.raised_at || flag.detected_at || flag.created_at || '';
}

function formatRoutingText(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  if (text.includes('@')) return text;
  return humanizeSnakeText(text);
}

function formatCustomRouting(value) {
  if (!value) return '';
  if (typeof value !== 'object') return humanizeSnakeText(value);

  const label = value.label
    || value.name
    || value.route_name
    || value.approval_chain_name
    || value.approver_group
    || value.group
    || value.approver
    || value.approver_email
    || '';
  const approvers = Array.isArray(value.approvers)
    ? value.approvers
    : (Array.isArray(value.approver_emails) ? value.approver_emails : []);
  const channel = value.channel || value.surface || value.destination || '';
  const reason = value.reason || value.rule_name || value.policy || '';
  const parts = [
    label ? formatRoutingText(label) : '',
    !label && approvers.length ? `${approvers.length} approver${approvers.length === 1 ? '' : 's'}` : '',
    channel ? `via ${formatVendorSourceLabel(channel)}` : '',
    reason ? formatRoutingText(reason) : '',
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : 'Custom approval route configured';
}

function firstPresent(...values) {
  return values.find((value) => value !== null && value !== undefined && value !== '');
}

function coalesceArray(...values) {
  const nonEmpty = values.find((value) => Array.isArray(value) && value.length > 0);
  return nonEmpty || values.find((value) => Array.isArray(value)) || [];
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function integerOrZero(value) {
  const numeric = numberOrNull(value);
  return numeric === null ? 0 : Math.max(0, Math.round(numeric));
}

function formatCompactCount(value) {
  return integerOrZero(value).toLocaleString();
}

function formatRatioPercent(value) {
  const numeric = numberOrNull(value);
  if (numeric === null) return '';
  const percent = numeric <= 1 ? numeric * 100 : numeric;
  return `${percent.toFixed(percent >= 10 ? 0 : 1)}%`;
}

function formatExceptionRate(summary = {}, issueSummary = {}) {
  const explicit = formatRatioPercent(summary.exception_rate);
  if (explicit) return explicit;
  const invoiceCount = integerOrZero(firstPresent(summary.invoice_count, summary.total_invoices));
  const issueCount = integerOrZero(firstPresent(summary.issue_count, issueSummary.total));
  if (!invoiceCount) return '';
  return `${((issueCount / invoiceCount) * 100).toFixed(0)}%`;
}

function formatShortDateTime(value) {
  return value ? fmtDateTime(value) : '—';
}

function joinLimited(values, limit = 3) {
  const list = Array.isArray(values) ? values.filter(Boolean) : [];
  if (!list.length) return '';
  const shown = list.slice(0, limit);
  const extra = list.length - shown.length;
  return extra > 0 ? `${shown.join(', ')} +${extra}` : shown.join(', ');
}

function getVendorCurrency(summary = {}, profile = {}, invoices = []) {
  return firstPresent(
    summary.currency,
    profile.currency,
    invoices.find((invoice) => invoice?.currency)?.currency,
    '',
  );
}

function getInvoiceId(invoice) {
  return invoice?.id || invoice?.ap_item_id || invoice?.item_id || '';
}

function getInvoiceReference(invoice) {
  return invoice?.invoice_number || getInvoiceId(invoice) || 'Invoice';
}

function getInvoiceDate(invoice) {
  return firstPresent(invoice?.invoice_date, invoice?.updated_at, invoice?.created_at, invoice?.due_date);
}

function getInvoiceState(invoice) {
  return invoice?.state || invoice?.final_state || invoice?.status || '';
}

function getVendorInitials(name) {
  const text = String(name || '').trim();
  return text.split(/\s+/).slice(0, 2).map((word) => word[0] || '').join('').toUpperCase() || '?';
}

function getVendorHue(name) {
  return [...String(name || '')].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 6;
}

function getIssueSummaryRows(issueSummary = {}) {
  return [
    ['needs_info', 'Needs info'],
    ['field_review', 'Field review'],
    ['failed_post', 'Posting retry'],
    ['entity_route', 'Entity routing'],
    ['policy_exception', 'Policy exception'],
  ]
    .map(([key, label]) => ({ key, label, count: integerOrZero(issueSummary[key]) }))
    .filter((row) => row.count > 0);
}

function riskTone(score) {
  const numeric = integerOrZero(score);
  if (numeric >= 60) return 'error';
  if (numeric >= 25) return 'warning';
  return 'success';
}

function getCurrentFocus({ summary = {}, issueSummary = {}, risk = {}, invoices = [] }) {
  const issueCount = integerOrZero(firstPresent(issueSummary.total, summary.issue_count));
  const openCount = integerOrZero(summary.open_count);
  const invoiceCount = integerOrZero(firstPresent(summary.invoice_count, summary.total_invoices, invoices.length));
  const riskScore = numberOrNull(risk.score);

  if (issueCount > 0) {
    const recordNoun = `record${issueCount === 1 ? '' : 's'}`;
    const verb = issueCount === 1 ? 'needs' : 'need';
    return {
      tone: 'warning',
      label: 'Current focus',
      title: 'Review open vendor blockers',
      detail: `${formatCompactCount(issueCount)} ${recordNoun} ${verb} context before the agent can continue.`,
    };
  }
  if (openCount > 0) {
    return {
      tone: 'info',
      label: 'Current focus',
      title: 'Monitor open AP records',
      detail: `${formatCompactCount(openCount)} invoice${openCount === 1 ? '' : 's'} still moving through the connected surfaces.`,
    };
  }
  if (riskScore !== null && riskScore > 0) {
    return {
      tone: riskTone(riskScore),
      label: 'Current focus',
      title: 'Review vendor checks',
      detail: `Risk score ${riskScore}/100 based on registry, KYC, bank, and approval history signals.`,
    };
  }
  if (invoiceCount > 0) {
    return {
      tone: 'success',
      label: 'Current focus',
      title: 'No open vendor blockers',
      detail: 'Recent AP records are available below for audit and pattern review.',
    };
  }
  return {
    tone: 'info',
    label: 'Current focus',
    title: 'Waiting for AP activity',
    detail: 'The record will fill in as invoices, ERP syncs, and vendor checks run.',
  };
}

export default function VendorDetailPage({ api, orgId, navigate, toast, vendorName }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!vendorName) {
      setError('No vendor name supplied');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const resp = await api(
        `/api/ap/items/vendors/${encodeURIComponent(vendorName)}`
        + `?organization_id=${encodeURIComponent(orgId)}&days=180&invoice_limit=20`,
      );
      setData(resp);
    } catch (exc) {
      setError(String(exc?.message || exc || 'Failed to load vendor'));
    } finally {
      setLoading(false);
    }
  }, [api, orgId, vendorName]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) {
    return html`
      <div class="cl-vendor-detail" role="status" aria-live="polite">
        <div class="cl-vendor-skeleton cl-vendor-skeleton-head"></div>
        <div class="cl-vendor-skeleton cl-vendor-skeleton-grid"></div>
      </div>
    `;
  }

  if (error && !data) {
    return html`
      <div class="cl-vendor-detail cl-vendor-error" role="alert">
        <h2>Couldn't load this vendor</h2>
        <p>${error}</p>
        <div class="cl-vendor-error-actions">
          <button class="btn btn-primary" onClick=${load}>Try again</button>
          <button class="btn btn-secondary" onClick=${() => navigate('/vendors')}>
            Back to vendors
          </button>
        </div>
      </div>
    `;
  }

  if (!data) {
    return html`
      <div class="cl-vendor-detail cl-vendor-error">
        <h2>Vendor not found</h2>
        <button class="btn btn-secondary" onClick=${() => navigate('/vendors')}>
          Back to vendors
        </button>
      </div>
    `;
  }

  const profile = data.profile || data.vendor_profile || {};
  const erp = data.erp || {};
  const summary = data.summary || data.metrics || {};
  const recentItems = coalesceArray(data.recent_items, data.recent_invoices, data.recent);
  const history = coalesceArray(data.history, data.invoice_history);
  const invoices = recentItems.length ? recentItems : history;
  const fraudFlags = data.fraud_flags || profile.fraud_flags || [];
  const verifiedIbans = data.verified_ibans || profile.verified_ibans || [];
  const exceptionTrend = data.exception_trend || [];
  const openIssues = coalesceArray(data.open_issues, summary.open_issues);
  const issueSummary = data.issue_summary || summary.issue_summary || {};
  const topExceptionCodes = coalesceArray(data.top_exception_codes, summary.top_exception_codes);
  const risk = data.risk || data.risk_score || {};

  return html`
    <div class="cl-vendor-detail">
      <header class="cl-vendor-detail-topbar">
        <button class="cl-record-back" onClick=${() => navigate('/vendors')} aria-label="Back to vendors">
          ← Vendors
        </button>
      </header>

      <${VendorHeader}
        name=${vendorName}
        profile=${profile}
        summary=${summary}
        issueSummary=${issueSummary}
        risk=${risk}
        invoices=${invoices} />

      <div class="cl-vendor-profile-layout">
        <main class="cl-vendor-profile-main">
          <${VendorOpenWorkPanel}
            openIssues=${openIssues}
            issueSummary=${issueSummary}
            summary=${summary}
            invoices=${invoices}
            navigate=${navigate} />

          <${RecentInvoicesPanel} invoices=${invoices} navigate=${navigate} />
        </main>

        <aside class="cl-vendor-profile-aside" aria-label="Vendor trust profile">
          <${SoldenLayerPanel}
            api=${api}
            vendorName=${vendorName}
            profile=${profile}
            verifiedIbans=${verifiedIbans}
            fraudFlags=${fraudFlags}
            summary=${summary}
            issueSummary=${issueSummary}
            topExceptionCodes=${topExceptionCodes}
            risk=${risk}
            toast=${toast}
            onChanged=${load} />

          <${ExceptionPatternPanel}
            trend=${exceptionTrend}
            topExceptionCodes=${topExceptionCodes}
            issueSummary=${issueSummary}
            summary=${summary}
            invoices=${invoices} />

          <${VendorMasterPanel}
            erp=${erp}
            profile=${profile}
            summary=${summary}
            invoices=${invoices} />

          <${VendorTrustDetailsPanel}
            profile=${profile}
            verifiedIbans=${verifiedIbans}
            fraudFlags=${fraudFlags}
            summary=${summary}
            topExceptionCodes=${topExceptionCodes} />
        </aside>
      </div>
    </div>
  `;
}


// ─── Header ─────────────────────────────────────────────────────────

function VendorHeader({
  name, profile, summary, issueSummary, risk, invoices,
}) {
  const totalInvoices = integerOrZero(firstPresent(
    summary.invoice_count,
    summary.total_invoices,
    profile.invoice_count,
    invoices.length,
  ));
  const openCount = integerOrZero(summary.open_count);
  const postedCount = integerOrZero(summary.posted_count);
  const issueCount = integerOrZero(firstPresent(issueSummary.total, summary.issue_count));
  const exceptionRate = formatExceptionRate(summary, issueSummary);
  const totalAmount = numberOrNull(summary.total_amount);
  const avgAmount = numberOrNull(firstPresent(summary.avg_invoice_amount, profile.avg_invoice_amount));
  const currency = getVendorCurrency(summary, profile, invoices);
  const status = profile.status || 'active';
  const focus = getCurrentFocus({ summary, issueSummary, risk, invoices });

  return html`
    <section class="cl-vendor-header">
      <div class="cl-vendor-header-primary">
        <div class="cl-vendor-identity">
          <span class="cl-avatar cl-vendor-header-avatar" data-hue=${getVendorHue(name)} aria-hidden="true">
            ${getVendorInitials(name)}
          </span>
          <div>
          <span class="cl-record-header-eyebrow">Vendor record</span>
          <h1 class="cl-record-header-vendor-name">${name}</h1>
          <p class="cl-vendor-header-sub">
            ${firstPresent(summary.primary_email, profile.primary_contact_email, 'No primary sender on file')}
            ${summary.last_activity_at ? ` · last activity ${fmtDateTime(summary.last_activity_at)}` : ''}
          </p>
          </div>
        </div>
        <div class="cl-vendor-header-chips">
          <span class=${`cl-record-chip cl-record-chip-${vendorStatusTone(status)}`}>
            ${formatVendorStatusLabel(status)}
          </span>
          ${typeof risk.score === 'number' ? html`
            <span class=${`cl-record-chip cl-record-chip-${riskTone(risk.score)}`}>
              Risk ${risk.score}
            </span>` : null}
        </div>
      </div>
      <div class=${`cl-vendor-focus cl-vendor-focus-${focus.tone}`}>
        <span>${focus.label}</span>
        <strong>${focus.title}</strong>
        <p>${focus.detail}</p>
      </div>
      <dl class="cl-record-header-meta">
        <div class="cl-record-header-meta-cell">
          <dt>Invoices</dt>
          <dd>${formatCompactCount(totalInvoices)}</dd>
        </div>
        <div class="cl-record-header-meta-cell">
          <dt>Open</dt>
          <dd>${formatCompactCount(openCount)}</dd>
        </div>
        <div class="cl-record-header-meta-cell">
          <dt>Open issues</dt>
          <dd>${formatCompactCount(issueCount)}</dd>
        </div>
        <div class="cl-record-header-meta-cell">
          <dt>Posted</dt>
          <dd>${formatCompactCount(postedCount)}</dd>
        </div>
        ${totalAmount !== null ? html`
          <div class="cl-record-header-meta-cell">
            <dt>Total amount</dt>
            <dd>${formatAmount(totalAmount, currency, { decimals: 0 })}</dd>
          </div>` : null}
        ${avgAmount !== null ? html`
          <div class="cl-record-header-meta-cell">
            <dt>Avg amount</dt>
            <dd>${formatAmount(avgAmount, currency)}</dd>
          </div>` : null}
        ${exceptionRate ? html`
          <div class="cl-record-header-meta-cell">
            <dt>Exception rate</dt>
            <dd>${exceptionRate}</dd>
          </div>` : null}
        ${profile.always_approved !== undefined ? html`
          <div class="cl-record-header-meta-cell">
            <dt>Always approved</dt>
            <dd>${profile.always_approved ? 'Yes' : 'No'}</dd>
          </div>` : null}
      </dl>
    </section>
  `;
}

function vendorStatusTone(status) {
  const s = String(status || '').toLowerCase();
  if (s === 'active' || s === 'verified') return 'success';
  if (s === 'pending' || s === 'unverified') return 'warning';
  if (s === 'blocked' || s === 'frozen') return 'error';
  return 'info';
}


// ─── Open vendor work ───────────────────────────────────────────────

function VendorOpenWorkPanel({
  openIssues, issueSummary, summary, invoices, navigate,
}) {
  const issueCount = integerOrZero(firstPresent(issueSummary.total, summary.issue_count, openIssues.length));
  const invoiceCount = integerOrZero(firstPresent(summary.invoice_count, summary.total_invoices, invoices.length));
  const summaryRows = getIssueSummaryRows({ ...summary.issue_summary, ...issueSummary });

  return html`
    <section class="cl-record-panel cl-vendor-open-work">
      <header class="cl-record-panel-head">
        <h2>Open work</h2>
        <span class="cl-record-panel-eyebrow">${formatCompactCount(issueCount)} unresolved</span>
      </header>

      ${summaryRows.length ? html`
        <div class="cl-vendor-issue-summary">
          ${summaryRows.map((row) => html`
            <span key=${row.key} class="secondary-chip">${row.label} ${row.count}</span>
          `)}
        </div>
      ` : null}

      ${openIssues.length === 0 ? html`
        <div class="cl-vendor-empty-state">
          <strong>${invoiceCount ? 'No open vendor blockers' : 'No AP work for this vendor yet'}</strong>
          <p>
            ${invoiceCount
              ? 'Recent records are available below for review, audit, and pattern checks.'
              : 'New records appear here once invoices are processed or the ERP sync links vendor activity.'}
          </p>
        </div>
      ` : html`
        <ul class="cl-vendor-work-list">
          ${openIssues.slice(0, 8).map((issue) => {
            const id = getInvoiceId(issue);
            const canOpen = !!id;
            return html`
              <li
                key=${id || issue.invoice_number || issue.issue_summary}
                class=${`cl-vendor-work-row ${canOpen ? 'cl-vendor-work-row-clickable' : ''}`}
                onClick=${canOpen ? () => navigate(accountPayableRecordPath(id)) : undefined}>
                <div class="cl-vendor-work-main">
                  <span class=${`cl-record-chip cl-record-chip-${issueTone(issue.issue_kind, issue.state)}`}>
                    ${issue.issue_label || 'Review'}
                  </span>
                  <strong>${getInvoiceReference(issue)}</strong>
                  <p>${issue.issue_summary || issue.next_action || 'Review this record before the agent continues.'}</p>
                </div>
                <div class="cl-vendor-work-meta">
                  <span>${formatAmount(issue.amount, issue.currency)}</span>
                  <span>${formatApStateLabel(getInvoiceState(issue))}</span>
                  <span>${formatShortDateTime(getInvoiceDate(issue))}</span>
                </div>
              </li>
            `;
          })}
        </ul>
      `}
    </section>
  `;
}

function issueTone(issueKind, state) {
  const kind = String(issueKind || '').toLowerCase();
  const s = String(state || '').toLowerCase();
  if (kind === 'failed_post' || s === 'failed_post') return 'error';
  if (kind === 'needs_info' || kind === 'field_review' || kind === 'entity_route') return 'warning';
  return 'info';
}


// ─── Vendor master panel ───────────────────────────────────────────

function VendorMasterPanel({ erp, profile, summary, invoices }) {
  const senderDomains = joinLimited(profile.sender_domains);
  const aliases = joinLimited(profile.vendor_aliases);
  const currency = getVendorCurrency(summary, profile, invoices);
  const masterFields = [
    ['ERP vendor ID', erp.vendor_id || profile.vendor_id || profile.erp_vendor_id],
    ['Tax ID', erp.tax_id || profile.tax_id],
    ['Registration no.', erp.registration_number || profile.registration_number],
    ['Jurisdiction', erp.jurisdiction || profile.jurisdiction],
    ['Payment terms', erp.payment_terms || profile.payment_terms || profile.terms],
    ['Address', erp.address || profile.address],
    ['Contact', erp.primary_contact_email || profile.primary_contact_email],
    ['Sender domains', senderDomains],
    ['Known aliases', aliases],
    ['Status reason', profile.status_reason],
  ].filter(([, v]) => v !== null && v !== undefined && v !== '');
  const fields = [
    ...masterFields,
    ['Currency', currency],
  ].filter(([, v]) => v !== null && v !== undefined && v !== '');

  if (masterFields.length === 0) return null;

  return html`
    <section class="cl-record-panel">
      <header class="cl-record-panel-head">
        <h2>Vendor master</h2>
        <span class="cl-record-panel-eyebrow">ERP and profile fields</span>
      </header>
      <dl class="cl-record-bill-grid">
        ${fields.map(([label, value]) => html`
          <div class="cl-record-bill-cell" key=${label}>
            <dt>${label}</dt>
            <dd>${value}</dd>
          </div>`)}
      </dl>
    </section>
  `;
}


// ─── Solden-layer panel ────────────────────────────────────────

function SoldenLayerPanel({
  api, vendorName, profile, verifiedIbans, fraudFlags, summary, issueSummary, topExceptionCodes, risk, toast, onChanged,
}) {
  const agentConfidence = summary.agent_confidence ?? profile.agent_confidence;
  const requiresPo = profile.requires_po;
  const customRouting = profile.custom_routing;
  const riskScore = numberOrNull(risk.score);
  const riskComponents = coalesceArray(risk.components);
  const issueCount = integerOrZero(firstPresent(issueSummary.total, summary.issue_count));

  return html`
    <section class="cl-record-panel">
      <header class="cl-record-panel-head">
        <h2>Trust checks</h2>
        <span class="cl-record-panel-eyebrow">Payment and risk context</span>
      </header>

      <div class="cl-vendor-check-grid">
        <${RegistryCheckTile}
          api=${api}
          vendorName=${vendorName}
          profile=${profile}
          toast=${toast}
          onChanged=${onChanged} />
        <${VendorCheck}
          label="Bank account"
          tone=${verifiedIbans.length ? 'success' : 'warning'}
          value=${verifiedIbans.length ? `${verifiedIbans.length} verified` : 'Verification needed'}
          detail=${verifiedIbans.length
            ? 'At least one payment account has been verified.'
            : 'First payment to a new account triggers IBAN verification.'} />
        <${VendorCheck}
          label="Fraud signals"
          tone=${fraudFlags.length ? 'error' : 'success'}
          value=${fraudFlags.length ? `${fraudFlags.length} active` : 'Clear'}
          detail=${fraudFlags.length
            ? 'Review the active signals before payment.'
            : 'No active fraud signals on the profile.'} />
        <${VendorCheck}
          label="Open issues"
          tone=${issueCount ? 'warning' : 'success'}
          value=${issueCount ? `${issueCount} unresolved` : 'None open'}
          detail=${issueCount
            ? 'Records need context before the agent can continue.'
            : 'No current vendor blockers in this window.'} />
        ${riskScore !== null ? html`
          <${VendorCheck}
            label="Risk"
            tone=${riskTone(riskScore)}
            value=${`${riskScore}/100`}
            detail=${riskComponents.length
              ? riskComponents.slice(0, 2).map((entry) => entry.label).join(' · ')
              : 'No risk components detected.'} />` : null}
      </div>
    </section>
  `;
}

function VendorTrustDetailsPanel({
  profile, verifiedIbans, fraudFlags, summary, topExceptionCodes,
}) {
  const agentConfidence = summary.agent_confidence ?? profile.agent_confidence;
  const requiresPo = profile.requires_po;
  const customRouting = profile.custom_routing;

  return html`
    <section class="cl-record-panel cl-vendor-trust-details">
      <header class="cl-record-panel-head">
        <h2>Trust detail</h2>
        <span class="cl-record-panel-eyebrow">Bank, fraud, and routing context</span>
      </header>
      <div class="cl-vendor-trust-detail-grid">
        <div class="cl-vendor-section">
          <h3 class="cl-vendor-subhead">Verified IBANs</h3>
          ${verifiedIbans.length === 0 ? html`
            <div class="cl-vendor-note-row">
              <strong>Verification will run before first payment</strong>
              <span>Solden has not recorded a verified IBAN for this vendor yet.</span>
            </div>
          ` : html`
            <ul class="cl-vendor-list">
              ${verifiedIbans.map((entry, idx) => html`
                <li key=${idx} class="cl-vendor-list-row">
                  <code>${entry.iban_masked || entry.iban || '—'}</code>
                  <span class="cl-record-muted">
                    ${entry.verified_at ? `verified ${fmtDate(entry.verified_at)}` : 'pending'}
                    ${entry.source ? ` · ${formatVendorSourceLabel(entry.source)}` : ''}
                  </span>
                </li>`)}
            </ul>
          `}
        </div>

        <div class="cl-vendor-section">
          <h3 class="cl-vendor-subhead">Fraud signals</h3>
          ${fraudFlags.length === 0 ? html`
            <div class="cl-vendor-note-row">
              <strong>No active fraud signals</strong>
              <span>Bank changes, domain changes, and anomaly flags are clear for this profile.</span>
            </div>
          ` : html`
            <ul class="cl-vendor-list">
              ${fraudFlags.map((flag, idx) => html`
                <li key=${idx} class="cl-vendor-list-row">
                  <span class=${`cl-record-chip cl-record-chip-${fraudTone(flag.severity)}`}>
                    ${humanizeSnakeText(getFraudFlagToken(flag) || 'review')}
                  </span>
                  ${getFraudFlagMessage(flag) ? html`<span>${getFraudFlagMessage(flag)}</span>` : null}
                  ${getFraudFlagDate(flag) ? html`
                    <span class="cl-record-muted">${fmtDate(getFraudFlagDate(flag))}</span>` : null}
                </li>`)}
            </ul>
          `}
        </div>

        <div class="cl-vendor-section">
          <h3 class="cl-vendor-subhead">Agent context</h3>
          <dl class="cl-record-bill-grid cl-vendor-context-grid">
            ${typeof agentConfidence === 'number' ? html`
              <div class="cl-record-bill-cell">
                <dt>Agent confidence</dt>
                <dd>${(agentConfidence * 100).toFixed(0)}%</dd>
              </div>` : null}
            ${requiresPo !== undefined ? html`
              <div class="cl-record-bill-cell">
                <dt>PO required</dt>
                <dd>${requiresPo ? 'Yes' : 'No'}</dd>
              </div>` : null}
            ${customRouting ? html`
              <div class="cl-record-bill-cell">
                <dt>Custom routing</dt>
                <dd>${formatCustomRouting(customRouting)}</dd>
              </div>` : null}
            ${profile.bank_details_changed_at ? html`
              <div class="cl-record-bill-cell">
                <dt>Bank details changed</dt>
                <dd>${fmtDate(profile.bank_details_changed_at)}</dd>
              </div>` : null}
            ${topExceptionCodes.length ? html`
              <div class="cl-record-bill-cell">
                <dt>Most common blocker</dt>
                <dd>${getExceptionLabel(topExceptionCodes[0].exception_code)} · ${topExceptionCodes[0].count}</dd>
              </div>` : null}
          </dl>
        </div>
      </div>
    </section>
  `;
}

function VendorCheck({
  label, value, detail, tone,
}) {
  return html`
    <div class=${`cl-vendor-check cl-vendor-check-${tone}`}>
      <span>${label}</span>
      <strong>${value}</strong>
      <p>${detail}</p>
    </div>
  `;
}

function fraudTone(severity) {
  const s = String(severity || '').toLowerCase();
  if (s === 'high' || s === 'critical') return 'error';
  if (s === 'medium') return 'warning';
  return 'info';
}


// ─── Exception pattern ─────────────────────────────────────────────

function ExceptionPatternPanel({
  trend, topExceptionCodes, issueSummary, summary, invoices,
}) {
  const safeTrend = Array.isArray(trend) ? trend : [];
  const safeTopCodes = Array.isArray(topExceptionCodes) ? topExceptionCodes : [];
  const invoiceCount = integerOrZero(firstPresent(summary.invoice_count, summary.total_invoices, invoices.length));
  const issueCount = integerOrZero(firstPresent(issueSummary.total, summary.issue_count));

  if (safeTrend.length === 0 && safeTopCodes.length === 0) {
    return html`
      <section class="cl-record-panel">
        <header class="cl-record-panel-head">
          <h2>Exception pattern</h2>
        </header>
        <div class="cl-vendor-empty-state">
          <strong>${invoiceCount ? 'No recurring exception pattern' : 'No exception pattern yet'}</strong>
          <p>
            ${invoiceCount
              ? `${formatCompactCount(invoiceCount)} invoice${invoiceCount === 1 ? '' : 's'} in the current window and ${formatCompactCount(issueCount)} open issue${issueCount === 1 ? '' : 's'}.`
              : 'Patterns appear once AP records are processed for this vendor.'}
          </p>
        </div>
      </section>
    `;
  }

  const max = Math.max(...safeTrend.map((p) => Number(p.exception_count || 0)), 1);

  return html`
    <section class="cl-record-panel">
      <header class="cl-record-panel-head">
        <h2>Exception pattern</h2>
        <span class="cl-record-panel-eyebrow">${safeTopCodes.length ? `${safeTopCodes.length} blockers` : `${safeTrend.length} buckets`}</span>
      </header>
      ${safeTopCodes.length ? html`
        <div class="cl-vendor-exception-chips">
          ${safeTopCodes.map((row) => html`
            <span key=${row.exception_code} class="secondary-chip">
              ${getExceptionLabel(row.exception_code)} ${row.count}
            </span>
          `)}
        </div>
      ` : null}
      ${safeTrend.length ? html`
        <svg class="cl-vendor-chart" viewBox="0 0 100 30" preserveAspectRatio="none"
          role="img" aria-label="Exception count over time">
          <line x1="0" y1="30" x2="100" y2="30" stroke="var(--cl-border)" stroke-width="0.2" />
          ${safeTrend.map((p, idx) => {
            const v = Number(p.exception_count || 0);
            const heightPct = (v / max) * 26;
            const w = (100 / safeTrend.length) * 0.8;
            const x = (idx / safeTrend.length) * 100 + (100 / safeTrend.length) * 0.1;
            const y = 30 - heightPct;
            return html`
              <rect key=${idx} x=${x} y=${y} width=${w} height=${heightPct}
                fill="var(--cl-warning)" opacity="0.85">
                <title>${p.bucket || p.period}: ${v} exceptions</title>
              </rect>`;
          })}
        </svg>
        <div class="cl-vendor-chart-axis">
          <span>${safeTrend[0]?.bucket || safeTrend[0]?.period || ''}</span>
          <span>${safeTrend[safeTrend.length - 1]?.bucket || safeTrend[safeTrend.length - 1]?.period || ''}</span>
        </div>
      ` : null}
    </section>
  `;
}


// ─── Recent invoices ───────────────────────────────────────────────

function RecentInvoicesPanel({ invoices, navigate }) {
  if (!Array.isArray(invoices) || invoices.length === 0) {
    return html`
      <section class="cl-record-panel">
        <header class="cl-record-panel-head">
          <h2>Recent AP records</h2>
        </header>
        <div class="cl-vendor-empty-state">
          <strong>No AP records in this window</strong>
          <p>Invoices will appear here once the vendor has activity in the workspace.</p>
        </div>
      </section>
    `;
  }

  return html`
    <section class="cl-record-panel cl-vendor-recent-panel">
      <header class="cl-record-panel-head">
        <h2>Recent AP records</h2>
        <span class="cl-record-panel-eyebrow">${invoices.length} shown</span>
      </header>
      <div class="cl-vendor-record-cards" role="list">
        ${invoices.slice(0, 25).map((inv) => {
          const id = getInvoiceId(inv);
          const canOpen = !!id;
          return html`
            <div
              key=${id || inv.invoice_number}
              role="listitem"
              class=${`cl-vendor-record-card ${canOpen ? 'cl-vendor-record-card-clickable' : ''}`}
              onClick=${canOpen ? () => navigate(accountPayableRecordPath(id)) : undefined}>
              <div class="cl-vendor-record-card-head">
                <code>${getInvoiceReference(inv)}</code>
                <span>${formatApStateLabel(getInvoiceState(inv))}</span>
              </div>
              <div class="cl-vendor-record-card-meta">
                <span>${getInvoiceDate(inv) ? formatShortDateTime(getInvoiceDate(inv)) : '—'}</span>
                <span>${formatAmount(inv.amount, inv.currency)}</span>
              </div>
              <div class="cl-vendor-record-card-exception">
                ${getExceptionLabel(inv.exception_code) || 'No exception'}
              </div>
            </div>
          `;
        })}
      </div>
      <div class="cl-vendor-table-wrap">
        <table class="cl-record-bill-line-table">
          <thead>
            <tr>
              <th>Invoice no.</th>
              <th>Date</th>
              <th class="cl-record-num">Amount</th>
              <th>State</th>
              <th>Exception</th>
            </tr>
          </thead>
          <tbody>
            ${invoices.slice(0, 25).map((inv) => html`
              <tr key=${getInvoiceId(inv) || inv.invoice_number} class=${`cl-vendor-invoice-row ${getInvoiceId(inv) ? 'cl-vendor-invoice-row-clickable' : ''}`}
                onClick=${getInvoiceId(inv) ? () => navigate(accountPayableRecordPath(getInvoiceId(inv))) : undefined}>
                <td><code>${getInvoiceReference(inv)}</code></td>
                <td class="cl-record-muted">
                  ${getInvoiceDate(inv) ? formatShortDateTime(getInvoiceDate(inv)) : '—'}
                </td>
                <td class="cl-record-num">
                  ${formatAmount(inv.amount, inv.currency)}
                </td>
                <td>${formatApStateLabel(getInvoiceState(inv))}</td>
                <td class="cl-record-muted">${getExceptionLabel(inv.exception_code) || '—'}</td>
              </tr>
            `)}
          </tbody>
        </table>
      </div>
    </section>
  `;
}


// ─── Module 4 — Business registry verification ───────────────────
//
// Spec line 158: "Verification: agent attempts auto-verification on
// creation (IBAN check, business registry lookup, prior payment
// match)." The Trust checks panel exposes the registry lookup verb
// with a click-to-verify button. Persists the result on the vendor
// profile so subsequent views show the verified state without re-querying.

function RegistryCheckTile({ api, vendorName, profile, toast, onChanged }) {
  const [busy, setBusy] = useState(false);
  const verified = !!profile?.registry_verified;
  const provider = profile?.registry_verification_provider;
  const verifiedAt = profile?.registry_verification_at;
  const payload = profile?.registry_verification_payload || {};

  const onVerify = async () => {
    setBusy(true);
    try {
      const params = new URLSearchParams();
      if (profile?.registration_number) params.set('registration_number', profile.registration_number);
      if (profile?.jurisdiction) params.set('jurisdiction', profile.jurisdiction);
      const resp = await api(
        `/api/vendors/${encodeURIComponent(vendorName)}/verify-registration${params.toString() ? `?${params.toString()}` : ''}`,
        { method: 'POST' },
      );
      if (resp?.status === 'verified') {
        toast?.(`Verified at ${resp.registry || 'registry'}: ${resp.company_name || vendorName}`, 'success');
      } else if (resp?.status === 'not_found') {
        toast?.('Not found in the registry. Add a registration number on the vendor profile and try again.', 'info');
      } else if (resp?.status === 'ambiguous') {
        toast?.(`Ambiguous match. ${(resp.candidates || []).length} candidates returned.`, 'info');
      } else {
        toast?.(resp?.error || 'Verification failed.', 'error');
      }
      onChanged?.();
    } catch (exc) {
      toast?.(`Verification failed: ${exc?.message || exc}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  return html`
    <div class=${`cl-vendor-check cl-vendor-check-${verified ? 'success' : 'info'} cl-vendor-registry-check-tile`}>
      <span>Registry</span>
      <strong>${verified ? 'Verified' : 'Not checked'}</strong>
      <p>
        ${verified
          ? `Via ${provider || 'registry'}${verifiedAt ? ` on ${fmtDate(verifiedAt)}` : ''}${payload.company_number ? ` · ${payload.company_number}` : ''}${payload.jurisdiction ? ` · ${String(payload.jurisdiction).toUpperCase()}` : ''}${typeof payload.match_score === 'number' ? ` · match ${Math.round(payload.match_score * 100)}%` : ''}`
          : 'Check the legal entity before first payment, bank-detail changes, or onboarding review.'}
      </p>
      <button class="btn btn-secondary btn-sm" onClick=${onVerify} disabled=${busy}>
        ${busy ? 'Checking…' : (verified ? 'Re-check' : 'Run registry check')}
      </button>
    </div>
  `;
}
