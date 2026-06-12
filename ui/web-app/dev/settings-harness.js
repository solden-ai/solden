// DEV-ONLY visual harness: mounts the real SettingsPage with mocked props so
// the page can be SEEN (and screenshotted) without the auth stack. Never part
// of the production build (vite build inputs only index.html).
import { h, render } from 'preact';
import { html } from '../src/utils/htm.js';
import SettingsPage from '../src/routes/pages/SettingsPage.js';
import '../src/styles/shell.css';
import '../src/styles/components.css';
import '../src/styles/pages.css';

const bootstrap = {
  current_user: { email: 'mo@soldenai.com', role: 'owner', workspace_role: 'owner' },
  capabilities: { manage_company: true, manage_plan: true, manage_team: true },
  organization: {
    id: 'org-dev', name: 'Solden', domain: 'soldenai.com',
    integration_mode: 'per_org', settings: {},
  },
  subscription: {
    plan: 'free', status: 'active', billing_cycle: 'monthly',
    usage: { users_count: 2, invoices_this_month: 42, ai_credits_this_month: 120 },
  },
  integrations: [
    { name: 'gmail', connected: true, status: 'connected' },
    { name: 'erp', connected: true, status: 'connected', connections: [{ erp_type: 'netsuite' }] },
    { name: 'slack', connected: false, status: 'disconnected' },
    { name: 'teams', connected: false, status: 'disconnected' },
  ],
};

const api = async (path) => {
  const route = String(path);
  if (route.startsWith('/api/workspace/team/invites')) {
    return { invites: [{ id: 'i1', email: 'pending@soldenai.com', status: 'pending', role: 'ap_clerk' }] };
  }
  if (route.startsWith('/erp/gl-map')) return { gl_account_map: { expenses: '6100' } };
  if (route.startsWith('/api/workspace/subscription/billing-summary')) {
    return { active_seats: 2, read_only_seats: 0, invoices_this_month: 42,
             invoice_volume_band: 'starter', ai_credits_used: 120,
             ai_credits_remaining: 880, estimated_total: 0 };
  }
  if (route.startsWith('/api/workspace/settings/match-config')) {
    return {
      mode: 'two_way_fallback',
      mode_version_number: 3,
      tolerances_version_number: 2,
      tolerances: {
        price_tolerance_percent: 2,
        quantity_tolerance_percent: 5,
        amount_tolerance: 10,
      },
    };
  }
  if (route.startsWith('/settings/org-dev')) {
    return { approval_thresholds: [{ min_amount: 0, max_amount: 1000, approver_channel: 'slack', approvers: ['maya@soldenai.com'] }] };
  }
  if (route.startsWith('/api/workspace/entities')) return { entities: [] };
  if (route.startsWith('/api/workspace/permissions/catalog')) {
    return {
      permissions: [
        { key: 'settings.manage', description: 'Manage workspace settings' },
        { key: 'ap.approve', description: 'Approve AP records' },
        { key: 'audit.export', description: 'Export audit logs' },
      ],
      standard_roles: {
        owner: ['settings.manage', 'ap.approve', 'audit.export'],
        ap_clerk: ['ap.approve'],
        read_only: [],
      },
    };
  }
  if (route.startsWith('/api/workspace/roles/custom')) return { custom_roles: [], limit: 10 };
  if (route.startsWith('/api/workspace/saml/config')) return { configured: false, config: null };
  if (route.startsWith('/api/workspace/api-keys/scopes/catalog')) {
    return { scopes: ['read:ap_items', 'read:vendors', 'read:reports', 'write:ap_items'] };
  }
  if (route.startsWith('/api/workspace/api-keys')) {
    return { api_keys: [{ id: 'key_1', label: 'Finance export', key_prefix: 'sk_live_abc', scopes: ['read:ap_items', 'read:reports'], created_at: '2026-06-10T09:00:00Z', last_used_at: null }] };
  }
  if (route.startsWith('/api/workspace/fraud-thresholds')) {
    return {
      defaults: {
        bank_change_alert_days: 7,
        bank_change_warn_days: 30,
        low_frequency_invoice_count_threshold: 3,
        low_frequency_invoice_multiplier: 3,
        new_vendor_days: 30,
        new_vendor_first_invoice_max: 5000,
      },
      configured: {},
    };
  }
  if (route.startsWith('/api/workspace/escalation-policies')) {
    return {
      policies: [
        { id: 'esc-1', name: 'Blocked AP over 24h', threshold_hours: 24, recipients: ['finance@soldenai.com'], is_active: true },
      ],
    };
  }
  if (route.startsWith('/api/workspace/notification-preferences/schema')) {
    return {
      defaults: {
        email: { exception_raised: true, approval_requested: true, weekly_digest: true },
        slack: { exception_raised: true, approval_requested: true },
        in_app: { exception_raised: true, approval_decided: true, weekly_digest: false },
      },
    };
  }
  if (route.startsWith('/api/workspace/notification-preferences')) {
    return {
      preferences: {
        email: { exception_raised: true, approval_requested: true, weekly_digest: true },
        slack: { exception_raised: true, approval_requested: true },
        in_app: { exception_raised: true, approval_decided: true, weekly_digest: false },
      },
    };
  }
  if (route.startsWith('/api/workspace/fx-rates/functional-currency')) {
    return { functional_currency: 'GBP' };
  }
  if (route.startsWith('/api/workspace/fx-rates')) {
    return {
      rates: [
        { id: 'fx-1', from_currency: 'EUR', to_currency: 'GBP', rate: 0.84, as_of_date: '2026-06-01', source: 'manual', note: 'Month close rate' },
      ],
    };
  }
  if (route.startsWith('/api/workspace/team/users')) {
    return { users: [
      { id: 'u1', name: 'Mo Mbalam', email: 'mo@soldenai.com', role: 'owner', is_active: true },
      { id: 'u2', name: 'Maya', email: 'maya@soldenai.com', role: 'ap_clerk', is_active: true },
    ] };
  }
  return {};
};

function Harness() {
  return html`
    <div class="cl-app" style="grid-template-columns: 0 1fr;">
      <div></div>
      <div class="cl-app-main">
        <main class="cl-app-content">
          <${SettingsPage}
            bootstrap=${bootstrap}
            api=${api}
            toast=${() => {}}
            orgId="org-dev"
            onRefresh=${() => {}}
            routeId=""
            navigate=${() => {}}
          />
        </main>
      </div>
    </div>
  `;
}

render(h(Harness, {}), document.getElementById('app'));
