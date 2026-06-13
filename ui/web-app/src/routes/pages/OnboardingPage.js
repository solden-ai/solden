import { useCallback, useEffect, useMemo, useState } from 'preact/hooks';
import { useLocation } from 'wouter-preact';
import { html } from '../../utils/htm.js';
import { api } from '../../api/client.js';
import { useBootstrap, useBootstrapRefresh, useOrgId } from '../../shell/BootstrapContext.js';
import { useToast } from '../../shell/Toast.js';

/**
 * Workspace setup for the first customer-side admin in a new org.
 *
 * The flow is role-neutral: Controller, AP Manager, VP Finance,
 * operations owner, CEO, or any department lead can complete it. It
 * does not assume a founder is signing up, and it does not treat AP as
 * the whole product. AP is the first live work type; the setup path
 * wires the surfaces that make Solden useful:
 *   1. Connect inbox intake       (Gmail or Outlook)
 *   2. Connect decision surface   (Slack or Teams)
 *   3. Connect ERP context/posting destination
 *   4. Set work policy and routing
 *
 * The wizard does NOT embed OAuth or ERP credential flows itself. Each
 * step links to the existing configuration surface, then bootstrap
 * refresh detects the connected integration or saved policy. Decoupling
 * keeps each deep flow in one place rather than duplicating it here.
 *
 * Steps surface:
 *   - Status pill: ✓ done / → next / ○ pending
 *   - "Set up" button → routes to /connections, /settings, etc.
 *   - "Mark done" button → POST /api/workspace/onboarding/step (admin
 *     can self-attest if integration state isn't auto-detected)
 *
 * Exit conditions:
 *   - All required steps (1-4) complete → onboarding.completed=true
 *     → AuthGate stops redirecting here, user lands on the workspace.
 *   - Admin clicks "Finish later" → marks current step persisted and
 *     drops the user at / for free exploration. Wizard remains in
 *     primary nav until completed.
 */
export function OnboardingPage() {
  const bootstrap = useBootstrap();
  const refreshBootstrap = useBootstrapRefresh();
  const orgId = useOrgId();
  const toast = useToast();
  const [, navigate] = useLocation();
  const [busy, setBusy] = useState(false);

  const onboarding = bootstrap?.onboarding || {};
  const integrations = bootstrap?.integrations || [];
  const integrationsByName = useMemo(() => {
    const map = {};
    for (const i of integrations) {
      const name = String(i?.name || '').toLowerCase();
      if (name) map[name] = i;
    }
    return map;
  }, [integrations]);

  const isConnected = (...names) => {
    for (const n of names) {
      const info = integrationsByName[n.toLowerCase()];
      if (!info) continue;
      if (info.connected) return true;
      const status = String(info.status || '').toLowerCase();
      if (['connected', 'active', 'ready'].includes(status)) return true;
    }
    return false;
  };

  const stepComplete = (id) => {
    if (onboarding.step >= id) return true;
    if (id === 1) return isConnected('gmail', 'outlook');
    if (id === 2) return isConnected('slack', 'teams');
    if (id === 3) {
      return isConnected('erp', 'netsuite', 'sap', 'sage_intacct', 'sage_accounting', 'xero', 'quickbooks');
    }
    if (id === 4) {
      const settings = bootstrap?.organization?.settings || {};
      return !!(settings.ap_policy || settings.workflow_controls);
    }
    return false;
  };

  const stepStatus = (id) => {
    if (stepComplete(id)) return 'done';
    if (id === 1 || stepComplete(id - 1)) return 'next';
    return 'pending';
  };

  const markStepDone = async (stepId) => {
    if (busy) return;
    setBusy(true);
    try {
      await api('/api/workspace/onboarding/step', {
        method: 'POST',
        body: { organization_id: orgId, step: stepId },
        retry: false,
      });
      await refreshBootstrap();
      toast(`Step ${stepId} marked complete.`, 'success');
    } catch (err) {
      toast(err?.message || 'Could not mark step complete.', 'error');
    } finally {
      setBusy(false);
    }
  };

  const finishLater = () => navigate('/');

  // Module 10 spec line 321 — pre-go-live integration health gate.
  // Runs the test-tx probe + inbox / approval status checks and
  // returns a per-check result. Surfaced as a banner above the
  // step list so the leader sees blockers before clicking
  // "Finish setup".
  const [healthGate, setHealthGate] = useState(null);
  const [probingHealth, setProbingHealth] = useState(false);
  const runHealthGate = async () => {
    setProbingHealth(true);
    try {
      const resp = await api(
        `/api/workspace/onboarding/integration-health-gate?organization_id=${encodeURIComponent(orgId)}`,
        { method: 'POST' },
      );
      setHealthGate(resp);
    } catch (err) {
      toast(err?.message || 'Health check failed', 'error');
    } finally {
      setProbingHealth(false);
    }
  };

  const completed = onboarding.completed === true;
  const steps = onboarding.steps || [];

  const STEP_DESTINATIONS = {
    1: '/connections',
    2: '/connections',
    3: '/connections',
    4: '/rules',
  };

  return html`
    <div class="cl-onb-shell">
      <header class="cl-onb-header">
        <div class="cl-onb-eyebrow">Workspace setup</div>
        <h1 class="cl-onb-title">${completed ? 'Setup complete.' : 'Finish workspace setup.'}</h1>
        <p class="cl-onb-sub">
          ${completed
            ? 'Required surfaces and policies are ready. You can revisit any step from this page; nothing here is destructive.'
            : 'Connect the surfaces where work enters, decisions happen, and records are posted. Then set the policy Solden should follow.'}
        </p>
        ${steps.length > 0 ? (() => {
          const doneCount = steps.filter((step) => stepStatus(step.id) === 'done').length;
          const pct = Math.round((doneCount / steps.length) * 100);
          return html`
            <div class="cl-onb-progress-row">
              <div class="cl-progress" role="progressbar"
                   aria-valuenow=${pct} aria-valuemin="0" aria-valuemax="100"
                   aria-label="Setup progress">
                <span class="cl-progress-fill" style=${`width: ${pct}%`}></span>
              </div>
              <span class="cl-onb-progress-count">${doneCount} of ${steps.length} steps</span>
            </div>
          `;
        })() : ''}
      </header>

      ${!completed ? html`
        <div class="cl-onb-health-gate">
          <div class="cl-onb-health-gate-head">
            <div>
              <strong>Pre-go-live health check</strong>
              <p class="muted">
                Runs an actual test transaction against your ERP and checks inbox plus approval surfaces.
                Catches expired tokens or misconfigured connections before work starts flowing.
              </p>
            </div>
            <button class="btn btn-secondary" onClick=${runHealthGate} disabled=${probingHealth}>
              ${probingHealth ? 'Running…' : 'Run health check'}
            </button>
          </div>
          ${healthGate ? html`
            <ul class="cl-onb-health-gate-results">
              ${(healthGate.checks || []).map((c) => html`
                <li key=${c.name} class=${`cl-onb-health-row cl-onb-health-row-${c.status}`}>
                  <span class=${`cl-onb-health-dot cl-onb-health-dot-${c.status}`}></span>
                  <strong>${c.label}</strong>
                  ${c.detail ? html`<span class="muted"> · ${c.detail}</span>` : null}
                </li>
              `)}
            </ul>
            <p class=${`cl-onb-health-verdict cl-onb-health-verdict-${healthGate.status}`}>
              ${healthGate.ready_for_go_live
                ? 'All required integrations responded. Ready to go live.'
                : 'One or more integrations need attention before go-live.'}
            </p>
          ` : null}
        </div>
      ` : null}

      <ol class="cl-onb-steps">
        ${steps.map((step) => {
          const status = stepStatus(step.id);
          const destination = STEP_DESTINATIONS[step.id];
          return html`
            <li class=${`cl-onb-step cl-onb-step-${status}`} key=${step.id}>
              <div class="cl-onb-step-rail">
                <span class=${`cl-onb-step-pip cl-onb-step-pip-${status}`} aria-hidden="true">
                  ${status === 'done' ? '✓' : (status === 'next' ? '→' : '○')}
                </span>
              </div>
              <div class="cl-onb-step-body">
                <div class="cl-onb-step-head">
                  <h2 class="cl-onb-step-name">
                    ${step.id}. ${step.name}
                    ${step.required === false ? html`<span class="cl-onb-step-tag">optional</span>` : null}
                  </h2>
                  <span class=${`cl-onb-step-status cl-onb-step-status-${status}`}>
                    ${status === 'done' ? 'Ready'
                      : status === 'next' ? 'Up next'
                      : 'Pending'}
                  </span>
                </div>
                <p class="cl-onb-step-desc">${step.description}</p>
                <div class="cl-onb-step-actions">
                  <button
                    class="btn btn-primary"
                    disabled=${busy}
                    onClick=${() => navigate(destination)}>
                    ${status === 'done' ? 'Review setup' : 'Set up'}
                  </button>
                  ${status !== 'done'
                    ? html`
                        <button
                          class="btn btn-ghost"
                          disabled=${busy}
                          onClick=${() => markStepDone(step.id)}>
                          Mark done manually
                        </button>
                      `
                    : null}
                </div>
                ${step.time_estimate
                  ? html`<div class="cl-onb-step-time">≈ ${step.time_estimate}</div>`
                  : null}
              </div>
            </li>
          `;
        })}
      </ol>

      <${SampleDataSection} />

      <footer class="cl-onb-footer">
        ${completed
          ? html`
              <button class="btn btn-primary" onClick=${() => navigate('/')}>
                Open workspace
              </button>
            `
          : html`
              <button class="btn btn-ghost" onClick=${finishLater}>
                Finish later
              </button>
              <span class="cl-onb-footer-hint">
                Required steps must be complete before Solden auto-routes live work.
              </span>
            `}
      </footer>
    </div>
  `;
}


// ─── Module 10 — Sample Data section ──────────────────────────────
//
// Lets the leader load a curated set of sample invoices and practice
// the workflow before going live with real data. Sample rows are
// tagged is_sample=true on the backend; production reads filter them
// out so they never contaminate live aggregates (spec §329).

function SampleDataSection() {
  const [count, setCount] = useState(0);
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [showItems, setShowItems] = useState(false);
  const toast = useToast();

  const load = useCallback(async () => {
    try {
      const status = await api(
        '/api/workspace/onboarding/sample-data/status',
      );
      setCount((status && status.sample_count) || 0);
    } catch {
      // Non-fatal — leave count at the previous value.
    }
  }, []);

  const loadPreview = useCallback(async () => {
    try {
      const resp = await api(
        '/api/workspace/onboarding/sample-data/preview',
      );
      setItems((resp && resp.items) || []);
    } catch {
      setItems([]);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onLoad = useCallback(async () => {
    setBusy(true);
    try {
      const resp = await api(
        '/api/workspace/onboarding/sample-data/load',
        { method: 'POST' },
      );
      const loaded = (resp && resp.loaded) || 0;
      const already = (resp && resp.already_present) || 0;
      if (loaded > 0) {
        toast(`Loaded ${loaded} sample invoices.`, 'success');
      } else if (already > 0) {
        toast(`${already} sample invoices already loaded.`, 'info');
      }
      await load();
      if (showItems) await loadPreview();
    } catch (exc) {
      toast(`Load failed: ${String(exc?.message || exc)}`, 'error');
    } finally {
      setBusy(false);
    }
  }, [load, loadPreview, showItems, toast]);

  const onClear = useCallback(async () => {
    if (!window.confirm(
      'Clear all sample invoices? Production data is unaffected. ' +
      'You can reload the sample set any time.',
    )) return;
    setBusy(true);
    try {
      const resp = await api(
        '/api/workspace/onboarding/sample-data/clear',
        { method: 'POST' },
      );
      const deleted = (resp && resp.deleted) || 0;
      toast(`Cleared ${deleted} sample invoices.`, 'success');
      await load();
      setItems([]);
    } catch (exc) {
      toast(`Clear failed: ${String(exc?.message || exc)}`, 'error');
    } finally {
      setBusy(false);
    }
  }, [load, toast]);

  const togglePreview = useCallback(async () => {
    if (!showItems) {
      await loadPreview();
    }
    setShowItems((v) => !v);
  }, [loadPreview, showItems]);

  return html`
    <section class="cl-sample-section">
      <header class="cl-sample-head">
        <div>
          <h2>Practice with sample invoices</h2>
          <p class="cl-sample-sub">
            Run a set of realistic invoices through the system so you can
            see exceptions, approvals, and reports light up before going
            live with real data. Sample data is kept separate from production
            and never appears in your live reports.
          </p>
        </div>
        <div class="cl-sample-actions">
          ${count > 0
            ? html`
                <button class="btn btn-ghost"
                  onClick=${togglePreview} disabled=${busy}>
                  ${showItems ? 'Hide' : 'View'} (${count})
                </button>
                <button class="btn btn-ghost"
                  onClick=${onClear} disabled=${busy}>
                  Clear
                </button>
              `
            : html`
                <button class="btn btn-primary"
                  onClick=${onLoad} disabled=${busy}>
                  ${busy ? 'Loading…' : 'Load sample invoices'}
                </button>
              `}
        </div>
      </header>

      ${showItems && items.length > 0 ? html`
        <table class="cl-sample-table">
          <thead>
            <tr>
              <th>Vendor</th>
              <th>Invoice no.</th>
              <th class="cl-sample-num">Amount</th>
              <th>State</th>
              <th>Exception</th>
            </tr>
          </thead>
          <tbody>
            ${items.map((it) => html`
              <tr key=${it.id}>
                <td><strong>${it.vendor_name}</strong></td>
                <td><code>${it.invoice_number}</code></td>
                <td class="cl-sample-num">
                  ${it.currency} ${Number(it.amount).toLocaleString(undefined, {
                    minimumFractionDigits: 2, maximumFractionDigits: 2,
                  })}
                </td>
                <td>${(it.state || '').replace(/_/g, ' ')}</td>
                <td class="cl-sample-muted">${it.exception_code || '—'}</td>
              </tr>
            `)}
          </tbody>
        </table>
      ` : null}
    </section>
  `;
}
