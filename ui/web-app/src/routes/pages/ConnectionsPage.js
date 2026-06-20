/**
 * Connections Page — occasional setup surface for connected work surfaces.
 */
import { h } from 'preact';
import { useState, useEffect, useCallback } from 'preact/hooks';
import htm from 'htm';
import { hasCapability, integrationByName, humanizeStatus, humanizeMode, useAction, fmtDateTime } from '../route-helpers.js';
import { accountsPayablePath } from '../../utils/record-route.js';

const html = htm.bind(h);
const ERP_OPTIONS = [
  { value: 'quickbooks', label: 'QuickBooks' },
  { value: 'xero', label: 'Xero' },
  { value: 'netsuite', label: 'NetSuite' },
  { value: 'sap', label: 'SAP' },
  { value: 'sage_intacct', label: 'Sage Intacct' },
  { value: 'sage_accounting', label: 'Sage Accounting' },
];
const WEBHOOKS_PAGE_SIZE = 5;

function getErpOptionLabel(value) {
  const token = String(value || '').trim().toLowerCase();
  return ERP_OPTIONS.find((option) => option.value === token)?.label || 'ERP';
}

function getConnectedErpType(erp = {}) {
  const direct = erp.erp_type || erp.erp_kind || erp.type;
  const nested = Array.isArray(erp.connections)
    ? erp.connections.find((conn) => conn?.erp_type)?.erp_type
    : '';
  return String(direct || nested || '').trim().toLowerCase();
}

function normalizeConnectionStatus(status, connected = false) {
  const token = String(status || '').trim().toLowerCase();
  if (connected || token === 'connected') return 'connected';
  if (['reconnect_required', 'reauthorization_required', 'degraded', 'error'].includes(token)) return 'attention';
  if (token === 'disabled') return 'disabled';
  return 'disconnected';
}

function connectionToneClass(status, connected = false) {
  const normalized = normalizeConnectionStatus(status, connected);
  if (normalized === 'connected') return 'connected';
  if (normalized === 'attention') return 'warning';
  return '';
}

function ConnectionRow({ label, status, detail, actionLabel = '', onAction, pending = false, disabled = false }) {
  const toneClass = connectionToneClass(status);
  return html`<div class="cl-connection-row">
    <div class="cl-connection-row-copy">
      <div class="cl-connection-row-title">
        <span class=${`cl-connection-dot cl-connection-dot-${normalizeConnectionStatus(status)}`}></span>
        <strong>${label}</strong>
        <span class=${`status-badge ${toneClass}`}>${humanizeStatus(status || 'unknown')}</span>
      </div>
      <div class="cl-connection-row-detail">${detail}</div>
    </div>
    ${actionLabel
      ? html`<button class="btn-secondary btn-sm cl-connection-row-action" onClick=${onAction} disabled=${pending || disabled}>${pending ? 'Working…' : actionLabel}</button>`
      : null}
  </div>`;
}

function ApprovalSurfaceCard({ title, status, detail, children }) {
  return html`<div class="panel cl-connection-setup-panel">
    <div class="panel-head compact">
      <div class="cl-connection-panel-copy">
        <h3>${title}</h3>
        <p>${detail}</p>
      </div>
      <span class=${`status-badge ${connectionToneClass(status)}`}>${humanizeStatus(status || 'unknown')}</span>
    </div>
    ${children}
  </div>`;
}

function getApprovalSummary(slack = {}, teams = {}) {
  if (slack.connected && slack.requires_reauthorization) return 'Reconnect Slack';
  if (slack.connected) return 'Slack ready';
  if (teams.connected) return 'Teams ready';
  return 'Set up Slack or Teams';
}

function getSetupSummary({
  gmail,
  gmailReconnectRequired,
  outlook,
  outlookReconnectRequired,
  outlookEnabled,
  inboxConnected,
  inboxReconnectRequired,
  approvalConnected,
  slack,
  erp,
}) {
  const missing = [];
  // Inbox side: either Gmail or Outlook satisfies the intake-channel
  // requirement. Only surface the reconnect language when at least
  // one is connected but stale.
  if (!inboxConnected) {
    missing.push(outlookEnabled ? 'Gmail or Outlook' : 'Gmail');
  } else if (inboxReconnectRequired) {
    if (gmail.connected && gmailReconnectRequired) missing.push('Gmail (reconnect)');
    if (outlook.connected && outlookReconnectRequired) missing.push('Outlook (reconnect)');
  }
  if (!approvalConnected || slack?.requires_reauthorization) missing.push('Slack or Teams approvals');
  if (!erp.connected) missing.push('ERP');
  if (missing.length === 0) return 'Inbox, approvals, and ERP are ready for this workspace.';
  if (missing.length === 1) return `Finish ${missing[0]} before Solden can run the full workflow.`;
  return `Finish ${missing.slice(0, -1).join(', ')}, and ${missing[missing.length - 1]} before Solden can run the full workflow.`;
}

function getSlackConnectionDetail(slack = {}) {
  if (slack.connected && slack.requires_reauthorization) {
    return 'Reconnect Slack to restore approval actions and approver email matching.';
  }
  if (slack.connected && slack.approval_channel) {
    return `Approvals are ready in ${slack.approval_channel}.`;
  }
  if (slack.connected) {
    return 'Slack is connected. Pick the approval channel below.';
  }
  return 'Install Slack to send approval requests there.';
}

function ReadinessCard({ label, value, detail, tone = 'neutral' }) {
  return html`
    <div class=${`cl-connections-readiness-card cl-connections-readiness-${tone}`}>
      <span>${label}</span>
      <strong>${value}</strong>
      <small>${detail}</small>
    </div>
  `;
}

function surfaceStatusLabel(status) {
  const token = String(status || '').trim().toLowerCase();
  if (token === 'connected') return 'Connected';
  if (token === 'ready') return 'Ready';
  if (token === 'feature_gated') return 'Feature-gated';
  if (token === 'not_connected') return 'Not connected';
  if (token === 'disconnected') return 'Not connected';
  return token ? token.replace(/_/g, ' ') : 'Available';
}

function surfaceStatusTone(status) {
  const token = String(status || '').trim().toLowerCase();
  if (token === 'connected' || token === 'ready') return 'success';
  if (token === 'feature_gated') return 'warning';
  if (token === 'not_connected' || token === 'disconnected') return 'muted';
  return 'neutral';
}

function groupSurfaces(surfaces, family) {
  return (surfaces || []).filter((row) => String(row.family || '') === family);
}

function surfaceModelLabel(row = {}) {
  return row.surface_model_label || row.memory_surface || row.role || '';
}

function validationLabel(row = {}) {
  if (row.family !== 'erp') return '';
  const validation = row.validation_status || {};
  return validation.label || 'Evidence pending';
}

function capabilityConstraints(row = {}) {
  return Array.isArray(row.capability_constraints)
    ? row.capability_constraints.filter((item) => item && item.label)
    : [];
}

const CUSTOMER_SURFACE_COPY = {
  netsuite: {
    description: 'Connect NetSuite bills, vendors, and posting status.',
    where: 'Inside NetSuite bill records',
    actions: 'Review context, request info, approve, and post after checks pass.',
  },
  sap: {
    description: 'Connect SAP supplier invoices and vendor context.',
    where: 'Inside SAP supplier invoice screens',
    actions: 'Review context, request info, approve, and post after checks pass.',
  },
  sage_intacct: {
    description: 'Connect Sage Intacct bills and approval context.',
    where: 'Inside Sage Intacct bill records',
    actions: 'Review context, request info, approve, and prepare AP posting.',
  },
  quickbooks: {
    description: 'Connect QuickBooks bills, vendors, and ERP references.',
    where: 'Linked to QuickBooks bills',
    actions: 'Sync bills, keep Solden context attached, and post approved work.',
  },
  xero: {
    description: 'Connect Xero bills, vendors, and payment status.',
    where: 'Linked to Xero bills',
    actions: 'Sync bills, keep Solden context attached, and post approved work.',
  },
  sage_accounting: {
    description: 'Connect Sage Accounting purchases and vendor records.',
    where: 'Linked to Sage Accounting purchases',
    actions: 'Sync bills, keep Solden context attached, and prepare posting.',
  },
  gmail: {
    description: 'Capture work and evidence from Gmail threads.',
    where: 'Gmail thread panel',
    actions: 'Attach source emails, review missing context, and keep the record current.',
    readiness: 'Ready to use',
  },
  outlook: {
    description: 'Capture work and evidence from Outlook mail.',
    where: 'Outlook mail add-in',
    actions: 'Attach source emails, review missing context, and keep the record current.',
    readiness: 'Ready to use',
  },
  slack: {
    description: 'Send approval requests and exceptions to Slack.',
    where: 'Slack approval cards',
    actions: 'Approve, reject, request info, and save the decision to the record.',
    readiness: 'Ready to use',
  },
  teams: {
    description: 'Send approval requests and exceptions to Microsoft Teams.',
    where: 'Teams adaptive cards',
    actions: 'Approve, reject, request info, and save the decision to the record.',
    readiness: 'Ready to use',
  },
  workspace: {
    description: 'Monitor work, exceptions, connections, and audit from one place.',
    where: 'Workspace control center',
    actions: 'Configure surfaces, investigate stuck work, and intervene when the agent escalates.',
    readiness: 'Ready to use',
  },
};

function customerSurfaceCopy(row = {}) {
  const copy = CUSTOMER_SURFACE_COPY[row.key] || {
    description: row.role,
    where: row.memory_surface,
    actions: row.decision_actions,
  };
  const readiness = row.family === 'erp'
    ? row.solden_standard_label || row.maturity_label || 'AP operational memory standard'
    : copy.readiness || row.solden_standard_label || row.maturity_label || 'Ready to use';
  return {
    ...copy,
    readiness,
  };
}

function SurfaceCoveragePanel({ api, orgId }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (!api || !orgId) return;
    let cancelled = false;
    async function load() {
      setErr('');
      try {
        const resp = await api(`/api/workspace/surface-readiness?organization_id=${encodeURIComponent(orgId)}`);
        if (!cancelled) setData(resp || null);
      } catch (exc) {
        if (!cancelled) setErr(String(exc?.message || exc));
      }
    }
    load();
    return () => { cancelled = true; };
  }, [api, orgId]);

  const surfaces = Array.isArray(data?.surfaces) ? data.surfaces : [];
  const erpSurfaces = groupSurfaces(surfaces, 'erp');
  const operatingSurfaces = surfaces.filter((row) => row.family !== 'erp');
  const summary = data?.summary || {};

  return html`
    <div class="panel cl-surface-maturity-panel">
      <div class="panel-head compact">
        <div class="cl-connection-panel-copy">
          <h3>Connector coverage</h3>
          <p>Every supported ERP targets the same AP memory standard. Differences here are surface model, connector constraints, and validation proof.</p>
        </div>
        ${data ? html`
          <span class="secondary-chip">
            ${summary.connected || 0}/${summary.total || surfaces.length} active
          </span>
        ` : null}
      </div>
      ${err ? html`<div class="form-error">${err}</div>` : null}
      ${!err && !data ? html`<div class="secondary-empty cl-connection-empty">Loading connector coverage…</div>` : null}
      ${data && html`
        <div class="cl-surface-maturity-sections">
          <${SurfaceCoverageTable}
            title="ERP systems"
            rows=${erpSurfaces}
          />
          <${SurfaceCoverageTable}
            title="Inbox, chat, and workspace"
            rows=${operatingSurfaces}
          />
        </div>
      `}
    </div>
  `;
}

function SurfaceCoverageTable({ title, rows = [] }) {
  return html`
    <section class="cl-surface-maturity-section">
      <div class="cl-surface-maturity-title">
        <strong>${title}</strong>
        <span>${rows.length} surface${rows.length === 1 ? '' : 's'}</span>
      </div>
      <div class="cl-surface-maturity-table">
        ${rows.map((row) => {
          const copy = customerSurfaceCopy(row);
          const tone = surfaceStatusTone(row.connection_status);
          const constraints = capabilityConstraints(row);
          const proofLabel = validationLabel(row);
          return html`
            <div class="cl-surface-maturity-row" key=${row.key}>
              <div class="cl-surface-maturity-name">
                <strong>${row.label}</strong>
                <span>${copy.description}</span>
              </div>
              <div>
                <span class="cl-surface-maturity-label">Surface model</span>
                <strong>${copy.where}</strong>
                <span>${surfaceModelLabel(row)}</span>
              </div>
              <div>
                <span class="cl-surface-maturity-label">What users can do</span>
                <span>${copy.actions}</span>
                ${constraints.length ? html`
                  <div class="cl-surface-constraints" aria-label=${`${row.label} connector constraints`}>
                    ${constraints.map((constraint) => html`
                      <span key=${constraint.key}>${constraint.label}</span>
                    `)}
                  </div>
                ` : null}
              </div>
              <div class="cl-surface-maturity-stage">
                <span class=${`cl-surface-chip cl-surface-chip-${tone}`}>${copy.readiness}</span>
                <small>${surfaceStatusLabel(row.connection_status)}</small>
                ${proofLabel ? html`<small>Validation: ${proofLabel}</small>` : null}
              </div>
            </div>
          `;
        })}
      </div>
    </section>
  `;
}

export default function ConnectionsPage({ bootstrap, api, toast, orgId, onRefresh, oauthBridge, navigate }) {
  const gmail = integrationByName(bootstrap, 'gmail');
  const outlook = integrationByName(bootstrap, 'outlook');
  const erp = integrationByName(bootstrap, 'erp');
  const slack = integrationByName(bootstrap, 'slack');
  const teams = integrationByName(bootstrap, 'teams');
  const gmailReconnectRequired = Boolean(gmail.requires_reconnect);
  const outlookReconnectRequired = Boolean(outlook.requires_reconnect);
  // The Outlook + Teams surfaces ship with the product. Backend flags
  // are kill switches only; when explicitly off, the bootstrap status
  // reports disabled and the SPA avoids rendering a dead Connect CTA.
  const outlookEnabled = String(outlook.status || '').toLowerCase() !== 'disabled';
  const teamsEnabled = String(teams.status || '').toLowerCase() !== 'disabled';
  // Capability comes directly from the authenticated bootstrap response
  // (workspace_shell._workspace_capabilities).  The previous code probed
  // /api/workspace/team/invites with silent:true to infer admin status
  // from a 200 vs 403 — that conflated "not admin" with "permission
  // denied / auth expired / network error" and hid real errors.
  const canEditConnections = hasCapability(bootstrap, 'manage_connections');

  const [connectGmail, gmailPending] = useAction(async () => {
    if (!canEditConnections) return;
    const payload = await api('/api/workspace/integrations/gmail/connect/start', {
      method: 'POST',
      body: JSON.stringify({ organization_id: orgId, redirect_path: '/workspace' }),
    });
    if (payload?.auth_url) {
      oauthBridge.open(payload.auth_url);
      return;
    }
    navigate?.(accountsPayablePath());
  });

  const [connectOutlook, outlookPending] = useAction(async () => {
    if (!canEditConnections || !outlookEnabled) return;
    const payload = await api('/api/workspace/integrations/outlook/connect/start', {
      method: 'POST',
      body: JSON.stringify({ organization_id: orgId, redirect_path: '/connections' }),
    });
    if (payload?.auth_url) {
      oauthBridge.open(payload.auth_url);
      return;
    }
    navigate?.(accountsPayablePath());
  });

  const [disconnectOutlook, outlookDisconnectPending] = useAction(async () => {
    if (!canEditConnections) return;
    await api('/api/workspace/integrations/outlook/disconnect', {
      method: 'POST',
      body: JSON.stringify({ organization_id: orgId }),
    });
    toast('Outlook disconnected.');
    onRefresh?.();
  });

  const [connectSlack, slackPending] = useAction(async () => {
    if (!canEditConnections) return;
    const p = await api('/api/workspace/integrations/slack/install/start', { method: 'POST', body: JSON.stringify({ organization_id: orgId, mode: 'per_org', redirect_path: '/workspace' }) });
    oauthBridge.open(p.auth_url);
  });
  const [saveChannel, saveChannelPending] = useAction(async () => {
    if (!canEditConnections) return;
    await api('/api/workspace/integrations/slack/channel', { method: 'POST', body: JSON.stringify({ organization_id: orgId, channel_id: document.getElementById('cl-slack-channel')?.value?.trim() }) });
    toast('Channel saved.'); onRefresh();
  });
  const [testSlackMsg, testSlackPending] = useAction(async () => {
    if (!canEditConnections) return;
    await api('/api/workspace/integrations/slack/test', { method: 'POST', body: JSON.stringify({ organization_id: orgId, channel_id: document.getElementById('cl-slack-channel')?.value?.trim() }) });
    toast('Slack connection verified.');
  });
  const [saveWebhook, saveWebhookPending] = useAction(async () => {
    if (!canEditConnections) return;
    const wh = document.getElementById('cl-teams-webhook')?.value?.trim();
    if (!wh) { toast('Webhook URL required.', 'error'); return; }
    await api('/api/workspace/integrations/teams/webhook', { method: 'POST', body: JSON.stringify({ organization_id: orgId, webhook_url: wh }) });
    toast('Teams webhook saved.'); onRefresh();
  });
  const [testTeamsMsg, testTeamsPending] = useAction(async () => {
    if (!canEditConnections) return;
    await api('/api/workspace/integrations/teams/test', { method: 'POST', body: JSON.stringify({ organization_id: orgId }) });
    toast('Test sent to Teams.');
  });

  const approvalConnected = Boolean(slack.connected || teams.connected);
  // Gmail or Outlook satisfies the intake-channel side of onboarding.
  // ``setupMode`` reports whichever is missing or needs a reconnect.
  const inboxConnected = Boolean(gmail.connected || outlook.connected);
  const inboxReconnectRequired = (gmail.connected && gmailReconnectRequired)
    || (outlook.connected && outlookReconnectRequired);
  const setupMode = getSetupSummary({
    gmail,
    gmailReconnectRequired,
    outlook,
    outlookReconnectRequired,
    outlookEnabled,
    inboxConnected,
    inboxReconnectRequired,
    approvalConnected,
    slack,
    erp,
  });
  const connectedErpType = getConnectedErpType(erp);
  const [erpType, setErpType] = useState(connectedErpType || 'quickbooks');
  const [erpFormSpec, setErpFormSpec] = useState(null);
  const [erpFormValues, setErpFormValues] = useState({});

  useEffect(() => {
    if (connectedErpType) setErpType(connectedErpType);
  }, [connectedErpType]);

  const readiness = [
    {
      label: 'Inbox',
      value: !inboxConnected
        ? 'Not connected'
        : (inboxReconnectRequired ? 'Reconnect' : 'Ready'),
      detail: inboxConnected
        ? (outlook.connected ? 'Gmail or Outlook intake is available.' : 'Gmail intake is available.')
        : (outlookEnabled ? 'Connect Gmail or Outlook.' : 'Connect Gmail.'),
      tone: !inboxConnected ? 'danger' : (inboxReconnectRequired ? 'warning' : 'success'),
    },
    {
      label: 'Approvals',
      value: approvalConnected && !slack?.requires_reauthorization ? 'Ready' : 'Needs setup',
      detail: approvalConnected ? getApprovalSummary(slack, teams) : 'Connect Slack or Teams.',
      tone: approvalConnected && !slack?.requires_reauthorization ? 'success' : 'warning',
    },
    {
      label: 'ERP',
      value: erp.connected ? 'Ready' : 'Not connected',
      detail: erp.connected ? `${getErpOptionLabel(connectedErpType || erpType)} is connected.` : `Connect ${getErpOptionLabel(erpType)} or another ERP.`,
      tone: erp.connected ? 'success' : 'danger',
    },
  ];

  return html`
    <div class="cl-connections-page">
      <div class=${`cl-connections-hero ${canEditConnections ? '' : 'is-readonly'}`}>
        <div class="cl-connections-hero-copy">
          <span>Admin</span>
          <h1>Connections</h1>
          <p>${canEditConnections ? setupMode : 'Connection status is visible here. Admins manage inbox, approval, and ERP setup.'}</p>
        </div>
        <div class="cl-connections-hero-actions">
          <span class=${`cl-connections-access-pill ${canEditConnections ? '' : 'is-readonly'}`}>
            ${canEditConnections ? 'Admin access' : 'Read-only'}
          </span>
          ${gmail.connected || gmailReconnectRequired
            ? html`<button class="btn-primary btn-sm" onClick=${connectGmail} disabled=${gmailPending || !canEditConnections}>${gmailPending ? 'Working…' : (gmailReconnectRequired ? 'Reconnect Gmail' : 'Refresh Gmail auth')}</button>`
            : html`<button class="btn-primary btn-sm" onClick=${connectGmail} disabled=${gmailPending || !canEditConnections}>${gmailPending ? 'Working…' : 'Connect Gmail'}</button>`}
          <button class="btn-secondary btn-sm" onClick=${() => navigate?.('/status')}>Open system status</button>
        </div>
      </div>

      <div class="cl-connections-readiness-grid">
        ${readiness.map((item) => html`
          <${ReadinessCard}
            key=${item.label}
            label=${item.label}
            value=${item.value}
            detail=${item.detail}
            tone=${item.tone} />
        `)}
      </div>

      <${ConnectionHealthPanel} api=${api} orgId=${orgId} />

    <div class="secondary-shell cl-connections-shell">
      <div class="secondary-main">
        <div class="panel cl-connections-matrix-panel">
          <div class="panel-head compact">
            <div class="cl-connection-panel-copy">
              <h3>Connected surfaces</h3>
              <p>Where Solden reads work, asks for decisions, posts to ERP, and sends event updates.</p>
            </div>
          </div>
          <div class="cl-connections-matrix">
            <${ConnectionRow}
              label="Gmail"
              status=${gmail.status || (gmail.connected ? 'connected' : 'disconnected')}
              detail=${gmail.connected
                ? (gmailReconnectRequired
                  ? 'Reconnect Gmail to keep this inbox connected.'
                  : 'Gmail is connected for this workspace.')
                : 'Connect Gmail from the prompt in Gmail.'}
              actionLabel=${gmail.connected ? (gmailReconnectRequired ? 'Reconnect Gmail' : '') : 'Connect Gmail'}
              onAction=${connectGmail}
              pending=${gmailPending}
              disabled=${!canEditConnections}
            />
            <${ConnectionRow}
              label="Outlook"
              status=${outlook.status || (outlook.connected ? 'connected' : 'disconnected')}
              detail=${!outlookEnabled
                ? 'Outlook intake is not enabled for this workspace yet.'
                : outlook.connected
                  ? (outlookReconnectRequired
                    ? 'Reconnect Outlook to keep this inbox connected.'
                    : `Outlook is connected${outlook.email ? ` as ${outlook.email}` : ''}.`)
                  : 'Connect Outlook to ingest documents and requests arriving in your Microsoft 365 mailbox.'}
              actionLabel=${!outlookEnabled
                ? ''
                : outlook.connected
                  ? (outlookReconnectRequired ? 'Reconnect Outlook' : 'Disconnect Outlook')
                  : 'Connect Outlook'}
              onAction=${outlook.connected && !outlookReconnectRequired ? disconnectOutlook : connectOutlook}
              pending=${outlookPending || outlookDisconnectPending}
              disabled=${!canEditConnections || !outlookEnabled}
            />
            <${ConnectionRow}
              label="Slack"
              status=${slack.status || (slack.connected ? 'connected' : 'disconnected')}
              detail=${getSlackConnectionDetail(slack)}
              actionLabel=${slack.connected ? (slack.requires_reauthorization ? 'Reconnect Slack' : '') : 'Install Slack'}
              onAction=${connectSlack}
              pending=${slackPending}
              disabled=${!canEditConnections}
            />
            <${ConnectionRow}
              label="Teams"
              status=${teams.status || (teams.connected ? 'connected' : 'disconnected')}
              detail=${!teamsEnabled
                ? 'Teams approvals are not enabled for this workspace yet.'
                : teams.connected
                  ? `Teams approvals are connected${teams.webhook_configured ? ' via webhook' : ' via bot'}.`
                  : 'Configure Teams for approval notifications or interactive approve and reject cards.'}
            />
            <${ConnectionRow}
              label="ERP"
              status=${erp.status || (erp.connected ? 'connected' : 'disconnected')}
              detail=${erp.connected
                ? `${getErpOptionLabel(connectedErpType || erpType)} is connected.`
                : `Choose ${getErpOptionLabel(erpType)} or another ERP below before posting approved records.`}
              actionLabel=${erp.connected ? '' : 'Connect ERP'}
              onAction=${() => document.getElementById('cl-erp-connect-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
              disabled=${!canEditConnections}
            />
          </div>
        </div>

        <${ERPConnectionCard}
          id="cl-erp-connect-card"
          erp=${erp}
          erpType=${erpType}
          setErpType=${setErpType}
          erpFormSpec=${erpFormSpec}
          erpFormValues=${erpFormValues}
          setErpFormValues=${setErpFormValues}
          api=${api}
          toast=${toast}
          orgId=${orgId}
          onRefresh=${onRefresh}
          oauthBridge=${oauthBridge}
          canManageConnections=${canEditConnections}
        />

        <${SurfaceCoveragePanel} api=${api} orgId=${orgId} />

        <${FieldMappingPanel}
          api=${api}
          orgId=${orgId}
          erpType=${erpType}
          erpConnected=${erp.connected}
          canManage=${canEditConnections}
          toast=${toast}
        />

        <${ApprovalSurfaceCard}
          title="Slack approval routing"
          status=${slack.status || (slack.connected ? 'connected' : 'disconnected')}
          detail="Pick the Slack channel that should receive approval requests."
        >
          <div class="secondary-inline-actions cl-connection-control-row">
            <button class="btn-primary btn-sm" onClick=${connectSlack} disabled=${slackPending || !canEditConnections}>${slackPending ? 'Working…' : (slack.connected ? 'Reconnect Slack' : 'Install Slack')}</button>
            <div class="field-row cl-connection-control-field">
              <label for="cl-slack-channel">Approval channel</label>
              <input id="cl-slack-channel" placeholder="#approvals" value=${slack.approval_channel || ''} disabled=${!canEditConnections || !slack.connected} />
            </div>
            <button class="btn-secondary btn-sm" onClick=${saveChannel} disabled=${saveChannelPending || !canEditConnections || !slack.connected}>${saveChannelPending ? 'Saving…' : 'Save channel'}</button>
            <button class="btn-ghost btn-sm" onClick=${testSlackMsg} disabled=${testSlackPending || !slack.connected || !canEditConnections}>${testSlackPending ? 'Verifying…' : 'Verify Slack'}</button>
          </div>
          <div class="secondary-note" style="margin-top:12px">
            ${slack.connected
              ? `Mode: ${humanizeMode(slack.mode || '-')} · Verification sends a private test instead of posting a live approval request.`
              : 'Install Slack first, then choose the approval channel and run a private verification test.'}
          </div>
        </${ApprovalSurfaceCard}>

        <${ApprovalSurfaceCard}
          title="Teams approval routing"
          status=${teams.status || (teams.connected ? 'connected' : 'disconnected')}
          detail=${teamsEnabled
            ? 'Two install paths. Pick interactive bot for full Approve / Reject cards, or webhook for notification-only.'
            : 'Teams approvals are not enabled for this workspace yet.'}
        >
          ${!teamsEnabled ? html`
            <div class="secondary-note">
              Use Slack approvals now. Teams can be added when the Microsoft approval app is ready for this workspace.
            </div>
          ` : html`
            <div class="secondary-section" style="margin-top:6px">
              <strong style="font-size:13px">Interactive bot (Approve / Reject cards)</strong>
              <p class="muted" style="margin:4px 0 8px;font-size:12px">
                Best for teams that want decisions to happen directly inside Microsoft Teams,
                with approve and reject actions written back to the audit trail.
              </p>
              <div class="secondary-inline-actions">
                <a class="btn-secondary btn-sm" href="/api/workspace/integrations/teams/manifest?organization_id=${encodeURIComponent(orgId)}" target="_blank" rel="noreferrer">Download Teams app package</a>
                <span class="secondary-chip">${teams.bot_configured ? 'Bot configured' : 'Bot not configured'}</span>
              </div>
            </div>
            <div class="secondary-section" style="margin-top:14px">
              <strong style="font-size:13px">Webhook (notifications only)</strong>
              <p class="muted" style="margin:4px 0 8px;font-size:12px">
                Send approval notifications into a Teams channel while interactive actions are still being set up.
              </p>
              <div class="secondary-inline-actions cl-connection-control-row">
                <div class="field-row cl-connection-control-field cl-connection-control-field-wide">
                  <label for="cl-teams-webhook">Incoming webhook URL</label>
                  <input id="cl-teams-webhook" placeholder="https://.../incomingwebhook/..." value=${teams.webhook_url || ''} disabled=${!canEditConnections} />
                </div>
                <button class="btn-primary btn-sm" onClick=${saveWebhook} disabled=${saveWebhookPending || !canEditConnections}>${saveWebhookPending ? 'Saving…' : 'Save webhook'}</button>
                <button class="btn-ghost btn-sm" onClick=${testTeamsMsg} disabled=${testTeamsPending || !teams.connected || !canEditConnections}>${testTeamsPending ? 'Sending…' : 'Send test'}</button>
              </div>
              <div class="secondary-note" style="margin-top:8px;font-size:12px">Mode: ${humanizeMode(teams.mode || '-')}</div>
            </div>
          `}
        </${ApprovalSurfaceCard}>
      </div>

      <div class="secondary-side cl-connections-side">
        <div class="panel cl-connections-setup-panel">
          <div class="panel-head compact">
            <div class="cl-connection-panel-copy">
              <h3>Setup order</h3>
              <p>The minimum path for a workspace that can ingest, decide, and post work.</p>
            </div>
          </div>
          <div class="cl-connections-setup-list">
            <div class=${`cl-connections-setup-step ${inboxConnected && !inboxReconnectRequired ? 'is-done' : 'is-open'}`}>
              <span>1</span>
              <div>
                <strong>Connect intake</strong>
                <small>${inboxConnected ? 'Gmail or Outlook is available.' : 'Connect the inbox where work arrives.'}</small>
              </div>
            </div>
            <div class=${`cl-connections-setup-step ${approvalConnected && !slack?.requires_reauthorization ? 'is-done' : 'is-open'}`}>
              <span>2</span>
              <div>
                <strong>Connect approvals</strong>
                <small>${approvalConnected ? getApprovalSummary(slack, teams) : 'Use Slack or Teams for decisions.'}</small>
              </div>
            </div>
            <div class=${`cl-connections-setup-step ${erp.connected ? 'is-done' : 'is-open'}`}>
              <span>3</span>
              <div>
                <strong>Connect ERP</strong>
                <small>${erp.connected ? `${getErpOptionLabel(connectedErpType || erpType)} is ready.` : 'Connect the posting destination.'}</small>
              </div>
            </div>
            <div class="cl-connections-setup-step">
              <span>4</span>
              <div>
                <strong>Add event webhooks</strong>
                <small>Optional outbound events for downstream systems.</small>
              </div>
            </div>
          </div>
        </div>

        <${WebhooksPanel} api=${api} canManage=${canEditConnections} toast=${toast} />
      </div>
    </div>
    </div>
  `;
}

function ERPConnectionCard({
  id = '',
  erp,
  erpType,
  setErpType,
  erpFormSpec,
  erpFormValues,
  setErpFormValues,
  api,
  toast,
  orgId,
  onRefresh,
  oauthBridge,
  canManageConnections,
}) {
  const [startErpConnect, erpConnectPending] = useAction(async () => {
    if (!canManageConnections) return;
    const payload = await api('/api/workspace/integrations/erp/connect/start', {
      method: 'POST',
      body: JSON.stringify({ organization_id: orgId, erp_type: erpType }),
    });
    if (payload?.method === 'oauth' && payload?.auth_url) {
      setErpFormValues({});
      oauthBridge.open(payload.auth_url);
      return;
    }
    if (payload?.method === 'form' && Array.isArray(payload?.fields)) {
      setErpFormValues(Object.fromEntries(payload.fields.map((field) => [field.name, ''])));
      setErpFormSpec(payload);
      toast?.(`Enter your ${getErpOptionLabel(erpType)} connection details below.`, 'info');
      return;
    }
    toast?.('Could not start the ERP connection flow.', 'error');
  });

  const [submitErpForm, erpSubmitPending] = useAction(async () => {
    if (!canManageConnections || !erpFormSpec?.submit_url) return;
    const payload = await api(erpFormSpec.submit_url, {
      method: 'POST',
      body: JSON.stringify({ organization_id: orgId, ...erpFormValues }),
    });
    if (payload?.success) {
      setErpFormSpec(null);
      setErpFormValues({});
      toast?.(`${getErpOptionLabel(payload?.erp_type || erpType)} connected.`, 'success');
      onRefresh?.();
      return;
    }
    toast?.('Could not finish the ERP connection.', 'error');
  });

  return html`<div id=${id}>
    <${ApprovalSurfaceCard}
      title="ERP posting connection"
      status=${erp.status || (erp.connected ? 'connected' : 'disconnected')}
      detail="Choose the ERP Solden should post into. OAuth ERPs open a connect flow; credential-based ERPs finish here with credentials."
    >
      <div class="secondary-inline-actions cl-connection-control-row">
        <div class="field-row cl-connection-control-field cl-connection-control-field-compact">
          <label for="cl-erp-type">ERP</label>
          <select id="cl-erp-type" value=${erpType} onChange=${(event) => setErpType(event.target.value)} disabled=${!canManageConnections || erpConnectPending || erpSubmitPending}>
            ${ERP_OPTIONS.map((option) => html`<option key=${option.value} value=${option.value}>${option.label}</option>`)}
          </select>
        </div>
        <button class="btn-primary btn-sm" onClick=${startErpConnect} disabled=${erpConnectPending || !canManageConnections}>
          ${erpConnectPending ? 'Working…' : `${erp.connected ? 'Reconnect' : 'Connect'} ${getErpOptionLabel(erpType)}`}
        </button>
        ${erp.connected && html`<span class="secondary-chip">${getErpOptionLabel(erp.erp_type || erpType)} connected</span>`}
      </div>
      ${erpFormSpec?.help_text && html`<div class="secondary-note" style="margin-top:12px">${erpFormSpec.help_text}</div>`}
      ${Array.isArray(erpFormSpec?.fields) && erpFormSpec.fields.length > 0 && html`
        <div class="secondary-card" style="margin-top:14px">
          <div class="secondary-card-head">
            <div class="secondary-card-copy">
              <strong class="secondary-card-title">Finish ${getErpOptionLabel(erpType)} setup</strong>
              <div class="secondary-card-meta">Solden will test the connection before saving it for this workspace.</div>
            </div>
          </div>
          <div class="secondary-card-body" style="display:grid;gap:12px">
            ${erpFormSpec.fields.map((field) => html`
              <div class="field-row cl-connection-credential-field" key=${field.name}>
                <label>${field.label}</label>
                <input
                  type=${field.type === 'password' ? 'password' : 'text'}
                  placeholder=${field.placeholder || ''}
                  value=${erpFormValues?.[field.name] || ''}
                  onInput=${(event) => setErpFormValues((current) => ({ ...current, [field.name]: event.target.value }))}
                  disabled=${erpSubmitPending || !canManageConnections}
                />
              </div>
            `)}
            <div class="secondary-inline-actions">
              <button class="btn-primary btn-sm" onClick=${submitErpForm} disabled=${erpSubmitPending || !canManageConnections}>
                ${erpSubmitPending ? 'Connecting…' : `Save ${getErpOptionLabel(erpType)} connection`}
              </button>
              <button class="btn-ghost btn-sm" onClick=${() => { setErpFormSpec(null); setErpFormValues({}); }} disabled=${erpSubmitPending}>Cancel</button>
            </div>
          </div>
        </div>
      `}
    </${ApprovalSurfaceCard}>
  </div>`;
}

function WebhooksPanel({ api, canManage, toast }) {
  const [webhooks, setWebhooks] = useState([]);
  const [url, setUrl] = useState('');
  const [events, setEvents] = useState('*');
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState('');
  const [webhookPage, setWebhookPage] = useState(0);
  // Module 5 spec line 184 — surface the delivery log in the UI.
  const [deliveriesByWebhook, setDeliveriesByWebhook] = useState({});
  const [openDeliveryFor, setOpenDeliveryFor] = useState(null);

  useEffect(() => {
    api('/api/workspace/webhooks').then((d) => setWebhooks(d?.webhooks || [])).catch(() => {});
  }, []);

  const loadDeliveries = async (webhookId) => {
    if (deliveriesByWebhook[webhookId]) return; // cache once per session
    try {
      const resp = await api(`/api/workspace/webhooks/${webhookId}/deliveries?limit=20`);
      setDeliveriesByWebhook((prev) => ({ ...prev, [webhookId]: resp?.deliveries || [] }));
    } catch (e) {
      setDeliveriesByWebhook((prev) => ({ ...prev, [webhookId]: [] }));
    }
  };

  const toggleDeliveryLog = async (webhookId) => {
    if (openDeliveryFor === webhookId) {
      setOpenDeliveryFor(null);
      return;
    }
    setOpenDeliveryFor(webhookId);
    await loadDeliveries(webhookId);
  };

  const isValidUrl = (raw) => {
    try {
      const u = new URL(String(raw || '').trim());
      return u.protocol === 'https:' || u.protocol === 'http:';
    } catch {
      return false;
    }
  };

  const addWebhook = async () => {
    setError('');
    const trimmed = url.trim();
    if (!trimmed) {
      setError('Webhook URL is required.');
      return;
    }
    if (!isValidUrl(trimmed)) {
      setError('Enter a valid http(s):// URL.');
      return;
    }
    setAdding(true);
    try {
      const result = await api('/api/workspace/webhooks', {
        method: 'POST',
        body: JSON.stringify({ url: trimmed, event_types: events.split(',').map((e) => e.trim()).filter(Boolean) }),
      });
      if (result?.id) {
        setWebhooks((prev) => [...prev, result]);
        setWebhookPage(Math.max(0, Math.ceil((webhooks.length + 1) / WEBHOOKS_PAGE_SIZE) - 1));
      }
      setUrl('');
    } catch (e) {
      setError(e?.message || 'Could not add webhook. Check the URL and try again.');
    }
    setAdding(false);
  };
  const removeWebhook = async (id) => {
    try {
      await api(`/api/workspace/webhooks/${id}`, { method: 'DELETE' });
      setWebhooks((prev) => prev.filter((w) => w.id !== id));
    } catch (e) {
      toast?.(e?.message || 'Could not remove webhook.', 'error');
    }
  };

  const webhookPageCount = Math.max(1, Math.ceil(webhooks.length / WEBHOOKS_PAGE_SIZE));
  const safeWebhookPage = Math.min(webhookPage, webhookPageCount - 1);
  const visibleWebhooks = webhooks.slice(
    safeWebhookPage * WEBHOOKS_PAGE_SIZE,
    safeWebhookPage * WEBHOOKS_PAGE_SIZE + WEBHOOKS_PAGE_SIZE,
  );

  useEffect(() => {
    if (safeWebhookPage !== webhookPage) {
      setWebhookPage(safeWebhookPage);
    }
  }, [safeWebhookPage, webhookPage]);

  return html`
    <div class="panel cl-connection-webhooks-panel">
      <div class="panel-head compact">
        <div class="cl-connection-panel-copy">
          <h3>Outgoing webhooks</h3>
          <p>Notify external systems when work events happen, including approvals, retries, and posting outcomes.</p>
        </div>
      </div>
      ${webhooks.length === 0 && html`<div class="secondary-empty cl-connection-empty">No webhooks configured</div>`}
      ${webhooks.length > 0 && html`
        <div class="secondary-card-list">
          ${visibleWebhooks.map((wh) => {
            const open = openDeliveryFor === wh.id;
            const deliveries = deliveriesByWebhook[wh.id] || [];
            return html`
              <div key=${wh.id} class="secondary-card">
                <div class="secondary-card-head">
                  <div class="secondary-card-copy">
                    <span class="secondary-card-title">${wh.url}</span>
                    <div class="secondary-card-meta">${Array.isArray(wh.event_types) && wh.event_types.length ? wh.event_types.join(', ') : '*'}</div>
                  </div>
                  <div class="secondary-inline-actions">
                    <button class="btn-secondary btn-sm" onClick=${() => toggleDeliveryLog(wh.id)}>
                      ${open ? 'Hide log' : 'Delivery log'}
                    </button>
                    ${canManage && html`<button class="btn-secondary btn-sm" onClick=${() => removeWebhook(wh.id)}>Remove</button>`}
                  </div>
                </div>
                ${open ? html`
                  <div class="cl-webhook-deliveries">
                    ${deliveries.length === 0 ? html`<div class="muted" style="padding:8px 0">No deliveries yet for this webhook.</div>` : html`
                      <div class="muted cl-webhook-deliveries-caption">Latest 20 delivery attempts.</div>
                      <table class="cl-settings-table">
                        <thead>
                          <tr><th>Event</th><th>Status</th><th>HTTP</th><th>Attempts</th><th>Sent</th></tr>
                        </thead>
                        <tbody>
                          ${deliveries.map((d) => {
                            const tone = d.status === 'delivered' ? 'success'
                              : d.status === 'failed' ? 'danger'
                              : d.status === 'pending' ? 'warning' : 'muted';
                            return html`
                              <tr key=${d.id}>
                                <td><code>${d.event_type || '—'}</code></td>
                                <td><span class=${`cl-record-chip cl-record-chip-${tone}`}>${d.status || 'unknown'}</span></td>
                                <td>${d.last_response_status_code ?? '—'}</td>
                                <td>${d.attempt_count ?? d.attempts ?? '—'}</td>
                                <td class="muted">${d.last_attempted_at || d.created_at ? fmtDateTime(d.last_attempted_at || d.created_at) : '—'}</td>
                              </tr>`;
                          })}
                        </tbody>
                      </table>
                    `}
                  </div>
                ` : null}
              </div>
            `;
          })}
        </div>
        <div class="cl-webhook-pagination">
          <span class="muted">
            Page ${safeWebhookPage + 1} of ${webhookPageCount} · ${visibleWebhooks.length} of ${webhooks.length} webhook${webhooks.length === 1 ? '' : 's'} shown
          </span>
          <div class="cl-webhook-page-controls" aria-label="Outgoing webhook pagination">
            <button
              class="btn-secondary btn-sm"
              aria-label="Previous webhook page"
              onClick=${() => setWebhookPage((page) => Math.max(0, page - 1))}
              disabled=${safeWebhookPage === 0}>
              Previous
            </button>
            <button
              class="btn-secondary btn-sm"
              aria-label="Next webhook page"
              onClick=${() => setWebhookPage((page) => Math.min(webhookPageCount - 1, page + 1))}
              disabled=${safeWebhookPage >= webhookPageCount - 1}>
              Next
            </button>
          </div>
        </div>
      `}
      ${canManage && html`
        <div class="secondary-form-stack" style="margin-top:12px">
          <label>
            <span class="templates-field-label">Webhook URL</span>
            <input type="text" placeholder="https://..." value=${url} onInput=${(e) => setUrl(e.target.value)} />
          </label>
          <label>
            <span class="templates-field-label">Events</span>
            <input type="text" placeholder="* or invoice.approved, invoice.posted_to_erp" value=${events} onInput=${(e) => setEvents(e.target.value)} />
          </label>
          ${error && html`<div class="form-error">${error}</div>`}
          <div class="secondary-inline-actions">
            <button class="btn-secondary btn-sm" onClick=${addWebhook} disabled=${adding || !url.trim()}>${adding ? 'Adding…' : 'Add webhook'}</button>
          </div>
        </div>
        <div class="secondary-note cl-connection-form-note">Events can be "*" for all audit events, or a comma-separated list like "invoice.approved, invoice.posted_to_erp".</div>
      `}
    </div>
  `;
}


// ─── Module 5 Pass A — Custom field mapping panel ────────────────────
// Sits below the ERP connection card on the Connections page. Reads
// the bounded catalog from the workspace shell, renders one input per
// catalog entry, persists user-supplied overrides on save. The catalog
// is per-ERP — switching the ERP picker above re-fetches.
//
// Backed by:
//   GET /api/workspace/erp/field-mappings?erp_type=&organization_id=
//   PUT /api/workspace/erp/field-mappings?organization_id=  body={erp_type, mappings}
//
// The default field id is rendered as the input placeholder so the
// operator sees what Solden will fall back to if they don't
// override. A "Reset" link reverts a single field to the default.
function FieldMappingPanel({ api, orgId, erpType, erpConnected, canManage, toast }) {
  const [catalog, setCatalog] = useState(null);
  const [supportedErps, setSupportedErps] = useState([]);
  const [mappings, setMappings] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [dirty, setDirty] = useState(false);

  const erpKey = String(erpType || '').trim().toLowerCase();

  // Reload the catalog + persisted mapping whenever the ERP picker
  // above changes. Catalog is per-ERP (NetSuite custom-bodies vs
  // SAP Z-fields) so we can't render a single combined view.
  useEffect(() => {
    if (!api || !orgId || !erpKey) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const resp = await api(
          `/api/workspace/erp/field-mappings?erp_type=${encodeURIComponent(erpKey)}&organization_id=${encodeURIComponent(orgId)}`
        );
        if (cancelled) return;
        setCatalog(Array.isArray(resp?.catalog) ? resp.catalog : []);
        setSupportedErps(Array.isArray(resp?.supported_erps) ? resp.supported_erps : []);
        setMappings(resp?.mappings || {});
        setDirty(false);
      } catch (exc) {
        if (cancelled) return;
        // Treat 400 unsupported_erp as "no catalog for this ERP" rather
        // than an error — the panel renders an empty-state hint instead
        // of a red banner. Anything else is a real error.
        const msg = String(exc?.message || exc);
        if (msg.includes('unsupported_erp_type')) {
          setCatalog([]);
          setMappings({});
        } else {
          setError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [api, orgId, erpKey]);

  const setField = (key, value) => {
    setMappings((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  const resetField = (key) => {
    setMappings((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    setDirty(true);
  };

  const validateClientSide = () => {
    // Match the regex the server enforces. Client-side check exists to
    // give immediate feedback; the server is still the source of truth.
    const errors = [];
    for (const entry of catalog || []) {
      const value = String(mappings[entry.key] || '').trim();
      if (!value) continue;
      try {
        const re = new RegExp(entry.pattern);
        if (!re.test(value)) {
          errors.push(`${entry.label}: '${value}' doesn't match ${entry.pattern}`);
        }
      } catch (exc) {
        // If the pattern itself fails to compile (shouldn't happen),
        // skip — server validation will catch any real issue.
      }
    }
    return errors;
  };

  const onSave = async () => {
    if (!canManage) return;
    setError(null);
    const clientErrors = validateClientSide();
    if (clientErrors.length > 0) {
      setError(clientErrors.join('  •  '));
      return;
    }
    // Only send non-empty values. The server treats empty == revert
    // to default, but sending fewer keys is a cleaner audit diff.
    const payloadMappings = Object.fromEntries(
      Object.entries(mappings)
        .map(([k, v]) => [k, String(v || '').trim()])
        .filter(([, v]) => v.length > 0)
    );
    setSaving(true);
    try {
      const resp = await api(
        `/api/workspace/erp/field-mappings?organization_id=${encodeURIComponent(orgId)}`,
        {
          method: 'PUT',
          body: JSON.stringify({ erp_type: erpKey, mappings: payloadMappings }),
        }
      );
      setMappings(resp?.mappings || {});
      setDirty(false);
      toast?.('Custom field mappings saved.', 'success');
    } catch (exc) {
      const msg = String(exc?.message || exc);
      // The 422 detail surfaces the server-side validation list.
      // Surface it raw so the operator sees the exact field violation.
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  const erpLabel = (() => {
    const map = {
      netsuite: 'NetSuite',
      sap: 'SAP',
      quickbooks: 'QuickBooks',
      xero: 'Xero',
      sage_intacct: 'Sage Intacct',
      sage_accounting: 'Sage Accounting',
    };
    return map[erpKey] || (erpKey ? erpKey.charAt(0).toUpperCase() + erpKey.slice(1) : 'ERP');
  })();

  // Group catalog entries by category for the UI grouping headers.
  const grouped = (() => {
    const buckets = {};
    for (const entry of catalog || []) {
      const cat = entry.category || 'other';
      if (!buckets[cat]) buckets[cat] = [];
      buckets[cat].push(entry);
    }
    return buckets;
  })();

  const CATEGORY_LABELS = {
    identity: 'Identity fields',
    workflow: 'Workflow fields',
    dimension: 'Dimension fields',
    other: 'Other fields',
  };

  return html`
    <div class="panel cl-field-mapping-panel">
      <div class="panel-head compact">
        <div class="cl-connection-panel-copy">
          <h3>Custom field mapping</h3>
          <p>
            Override the default ${erpLabel} field IDs that Solden writes
            to. Leave a field blank to use the default.
          </p>
        </div>
        ${supportedErps.length > 0 && !supportedErps.includes(erpKey) ? html`
          <span class="secondary-chip">Not configurable for ${erpLabel}</span>
        ` : null}
      </div>

      ${loading ? html`<div class="muted" style="padding:8px 0">Loading catalog…</div>` : null}

      ${!loading && (catalog?.length || 0) === 0 ? html`
        <div class="secondary-empty" style="padding:8px 0">
          ${supportedErps.includes(erpKey)
            ? `No custom fields are mapped for ${erpLabel} yet.`
            : `Custom field mapping is not available for ${erpLabel}. Switch ERP above to configure a supported ERP.`}
        </div>
      ` : null}

      ${(catalog?.length || 0) > 0 ? html`
        <div class="cl-field-mapping-body">
          ${Object.keys(CATEGORY_LABELS).map((cat) => {
            const entries = grouped[cat];
            if (!entries || entries.length === 0) return null;
            return html`
              <fieldset class="cl-field-mapping-group" key=${cat}>
                <legend>${CATEGORY_LABELS[cat]}</legend>
                <div class="cl-field-mapping-rows">
                  ${entries.map((entry) => {
                    const value = mappings[entry.key] || '';
                    const usingDefault = !value;
                    return html`
                      <div class="cl-field-mapping-row" key=${entry.key}>
                        <div class="cl-field-mapping-meta">
                          <strong>${entry.label}</strong>
                          <span class="muted">${entry.description}</span>
                          ${entry.default ? html`
                            <span class="cl-field-mapping-default">
                              Default: <code>${entry.default}</code>
                            </span>
                          ` : null}
                        </div>
                        <div class="cl-field-mapping-input">
                          <input
                            type="text"
                            placeholder=${entry.default || `${erpLabel} field id`}
                            value=${value}
                            onInput=${(e) => setField(entry.key, e.target.value)}
                            disabled=${!canManage || saving} />
                          ${!usingDefault ? html`
                            <button
                              class="btn-ghost btn-sm"
                              type="button"
                              onClick=${() => resetField(entry.key)}
                              disabled=${!canManage || saving}>
                              Reset
                            </button>
                          ` : null}
                        </div>
                      </div>`;
                  })}
                </div>
              </fieldset>`;
          })}
        </div>
        ${error ? html`<div class="form-error">${error}</div>` : null}
        ${canManage ? html`
          <div class="secondary-inline-actions" style="margin-top:12px">
            <button
              class="btn-primary btn-sm"
              onClick=${onSave}
              disabled=${saving || !dirty}>
              ${saving ? 'Saving…' : (dirty ? 'Save mappings' : 'No changes')}
            </button>
            ${!erpConnected ? html`
              <span class="muted" style="font-size:12px">
                ${erpLabel} is not connected yet — mappings will apply once you connect.
              </span>
            ` : null}
          </div>
        ` : html`
          <div class="secondary-note" style="margin-top:10px">
            Only admins can change custom field mappings.
          </div>
        `}
      ` : null}
    </div>
  `;
}


// ─── Module 5 Pass B — Connection health panel ───────────────────────
// Lives at the top of secondary-main on the Connections page so a
// leader landing here gets the live signal first, before the static
// connect/disconnect rows below.
//
// Backed by:
//   GET /api/workspace/connections/health?organization_id=&window_hours=
//
// Auto-refreshes every 30s. The 30s cadence is a tradeoff between
// "leader sees breakage in 10 min" (the scope's acceptance criterion)
// and not hammering the api endpoint for an open tab.
function ConnectionHealthPanel({ api, orgId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [windowHours, setWindowHours] = useState(24);
  const [expandedKey, setExpandedKey] = useState(null);
  // Module 5 spec line 183 — test transaction probe + line 181 latency.
  // Probe results live here keyed by erp_type, surfaced inline on
  // the integration tile.
  const [probesByErp, setProbesByErp] = useState({});
  const [probingErp, setProbingErp] = useState(null);
  const onTestErp = useCallback(async (erpType) => {
    setProbingErp(erpType);
    try {
      const resp = await api(
        `/api/workspace/integrations/erp/test?organization_id=${encodeURIComponent(orgId)}&erp_type=${encodeURIComponent(erpType)}`,
        { method: 'POST' },
      );
      setProbesByErp((prev) => ({ ...prev, [erpType]: resp }));
    } catch (exc) {
      setProbesByErp((prev) => ({
        ...prev,
        [erpType]: { status: 'failed', error: String(exc?.message || exc), latency_ms: null },
      }));
    } finally {
      setProbingErp(null);
    }
  }, [api, orgId]);

  const load = useCallback(async () => {
    if (!api || !orgId) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set('organization_id', orgId);
      params.set('window_hours', String(windowHours));
      const resp = await api(`/api/workspace/connections/health?${params.toString()}`);
      setData(resp);
    } catch (exc) {
      setError(String(exc?.message || exc));
    } finally {
      setLoading(false);
    }
  }, [api, orgId, windowHours]);

  // Auto-refresh loop. Cleans up on unmount + on window-hours change
  // (the new request fires immediately via the load() in the deps).
  useEffect(() => {
    let cancelled = false;
    load();
    const id = setInterval(() => {
      if (!cancelled) load();
    }, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, [load]);

  const integrations = data?.integrations || [];
  const webhooks = data?.webhooks || { delivered: 0, failed: 0, retrying: 0 };
  const computedAt = data?.computed_at;

  // Derive the rollup status — the worst per-integration status
  // wins so the panel header tells the leader the overall picture
  // without making them scan every tile.
  const rollup = (() => {
    if (integrations.some((i) => i.status === 'down')) return 'down';
    if (integrations.some((i) => i.status === 'degraded')) return 'degraded';
    if (integrations.some((i) => i.status === 'healthy')) return 'healthy';
    return 'not_configured';
  })();

  return html`
    <div class="panel cl-conn-health-panel">
      <div class="panel-head compact">
        <div class="cl-connection-panel-copy">
          <h3>Connection health</h3>
          <p>
            Live signal from the agent's audit log. Refreshes every 30 seconds.
            ${computedAt ? html` Last update <span class="cl-conn-health-ts">${fmtDateTime(computedAt)}</span>.` : null}
          </p>
        </div>
        <div class="cl-conn-health-controls">
          <span class=${`cl-conn-health-chip cl-conn-health-${rollup}`}>
            ${rollup === 'down' ? 'Action needed'
              : rollup === 'degraded' ? 'Investigating'
              : rollup === 'healthy' ? 'All systems go'
              : 'Not configured'}
          </span>
          <select
            value=${windowHours}
            onChange=${(e) => setWindowHours(parseInt(e.target.value, 10))}
            disabled=${loading}>
            <option value="1">Last 1h</option>
            <option value="24">Last 24h</option>
            <option value="72">Last 72h</option>
            <option value="168">Last 7d</option>
          </select>
          <button
            class="btn-ghost btn-sm"
            onClick=${load}
            disabled=${loading}>
            ${loading ? '…' : 'Refresh'}
          </button>
        </div>
      </div>

      ${error ? html`<div class="form-error" style="margin-top:8px">${error}</div>` : null}

      ${integrations.length > 0 ? html`
        <div class="cl-conn-health-grid">
          ${integrations.map((row) => {
            const expanded = expandedKey === row.integration_type;
            const hasError = !!row.latest_error;
            return html`
              <div
                class=${`cl-conn-health-tile cl-conn-health-${row.status}`}
                key=${row.integration_type}>
                <div class="cl-conn-health-tile-head">
                  <div class="cl-conn-health-tile-meta">
                    <strong>${row.label}</strong>
                    <span class=${`cl-conn-health-chip cl-conn-health-${row.status}`}>
                      ${row.status === 'healthy' ? 'Healthy'
                        : row.status === 'degraded' ? 'Degraded'
                        : row.status === 'down' ? 'Down'
                        : 'Not configured'}
                    </span>
                  </div>
                  ${hasError ? html`
                    <button
                      class="btn-ghost btn-sm"
                      onClick=${() => setExpandedKey(expanded ? null : row.integration_type)}>
                      ${expanded ? 'Hide error' : 'View error'}
                    </button>
                  ` : null}
                </div>
                <div class="cl-conn-health-tile-stats">
                  <div>
                    <span class="muted">Last sync</span>
                    <span>${row.last_sync_at ? fmtDateTime(row.last_sync_at) : '—'}</span>
                  </div>
                  <div>
                    <span class="muted">Events</span>
                    <span>${row.events_24h.toLocaleString()}</span>
                  </div>
                  <div>
                    <span class="muted">Errors</span>
                    <span class=${row.errors_24h > 0 ? 'cl-conn-health-errors' : ''}>
                      ${row.errors_24h.toLocaleString()}
                    </span>
                  </div>
                  ${(() => {
                    // Latency from the most recent probe of this
                    // integration type. Empty when not yet probed.
                    const erpProbeKey = String(row.integration_type || '').toLowerCase();
                    const probe = probesByErp[erpProbeKey];
                    if (!probe || probe.latency_ms == null) return null;
                    return html`<div>
                      <span class="muted">Last probe</span>
                      <span class=${probe.status === 'ok' ? '' : 'cl-conn-health-errors'}>
                        ${probe.latency_ms} ms
                      </span>
                    </div>`;
                  })()}
                </div>
                ${(['quickbooks', 'xero', 'netsuite', 'sap', 'sage_intacct', 'sage_accounting']).includes(String(row.integration_type || '').toLowerCase()) ? html`
                  <div class="cl-conn-health-tile-actions">
                    <button class="btn-ghost btn-sm"
                      onClick=${() => onTestErp(String(row.integration_type).toLowerCase())}
                      disabled=${probingErp === String(row.integration_type).toLowerCase()}>
                      ${probingErp === String(row.integration_type).toLowerCase() ? 'Probing…' : 'Run test transaction'}
                    </button>
                    ${probesByErp[String(row.integration_type).toLowerCase()]?.error ? html`
                      <span class="cl-conn-health-errors" style="font-size:11px">
                        ${probesByErp[String(row.integration_type).toLowerCase()].error}
                      </span>
                    ` : null}
                  </div>
                ` : null}
                ${expanded && hasError ? html`
                  <div class="cl-conn-health-error-detail">
                    <div class="cl-conn-health-error-head">
                      <code>${row.latest_error.event_type}</code>
                      <span class="muted">${fmtDateTime(row.latest_error.ts)}</span>
                    </div>
                    ${row.latest_error.message ? html`
                      <div class="cl-conn-health-error-msg">${row.latest_error.message}</div>
                    ` : null}
                  </div>
                ` : null}
              </div>`;
          })}

          <div class="cl-conn-health-tile cl-conn-health-webhooks">
            <div class="cl-conn-health-tile-head">
              <div class="cl-conn-health-tile-meta">
                <strong>Outgoing webhooks</strong>
                <span class=${`cl-conn-health-chip ${webhooks.failed > 0 ? 'cl-conn-health-degraded' : 'cl-conn-health-healthy'}`}>
                  ${webhooks.failed > 0 ? 'Failures' : 'OK'}
                </span>
              </div>
            </div>
            <div class="cl-conn-health-tile-stats">
              <div>
                <span class="muted">Delivered</span>
                <span>${webhooks.delivered.toLocaleString()}</span>
              </div>
              <div>
                <span class="muted">Retrying</span>
                <span>${webhooks.retrying.toLocaleString()}</span>
              </div>
              <div>
                <span class="muted">Failed</span>
                <span class=${webhooks.failed > 0 ? 'cl-conn-health-errors' : ''}>
                  ${webhooks.failed.toLocaleString()}
                </span>
              </div>
            </div>
          </div>
        </div>
      ` : (loading ? null : html`
        <div class="secondary-empty cl-connection-empty">No integrations to summarise yet.</div>
      `)}
    </div>
  `;
}
