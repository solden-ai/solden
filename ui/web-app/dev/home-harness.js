// DEV-ONLY visual harness for the real workspace Home shell. It mocks
// authenticated workspace endpoints so design QA can screenshot the full
// AppShell + Sidebar + Topbar + Home console without the backend stack.
import { render } from 'preact';
import { html } from '../src/utils/htm.js';
import { App } from '../src/App.js';
import '../src/styles/shell.css';
import '../src/styles/components.css';
import '../src/styles/onboarding.css';
import '../src/styles/home.css';
import '../src/styles/canvas.css';
import '../src/styles/legal.css';
import '../src/styles/footer.css';
import '../src/styles/entity.css';
import '../src/styles/cmdk.css';
import '../src/styles/pages.css';
import '../src/styles/vendors.css';
import '../src/styles/records.css';
import '../src/styles/billing.css';
import '../src/styles/mobile.css';

const route = new URLSearchParams(window.location.search).get('route') || '/';
window.history.replaceState({}, '', route.startsWith('/') ? route : `/${route}`);

const now = Date.now();
const minute = 60000;
const isoAgo = (minutes) => new Date(now - minutes * minute).toISOString();

const bootstrap = {
  current_user: {
    id: 'usr-mo',
    name: 'Mo Mbalam',
    email: 'mo@soldenai.com',
    role: 'owner',
    workspace_role: 'owner',
  },
  organization: { id: 'org-dev', name: 'Solden', domain: 'soldenai.com' },
  capabilities: {
    manage_company: true,
    manage_plan: true,
    manage_team: true,
    view_procurement: true,
    view_workflow_builder: true,
  },
  onboarding: { completed: true },
  dashboard_stats: {
    in_flight: 45,
    pending_approval: 7,
    processed_this_week: 128,
    last_action_at: isoAgo(8),
  },
  integrations: [
    { name: 'gmail', connected: true, status: 'connected' },
    { name: 'slack', connected: true, status: 'connected' },
    { name: 'teams', connected: true, status: 'connected' },
    { name: 'erp', connected: true, status: 'connected', connections: [{ erp_type: 'netsuite' }] },
  ],
};

const records = [
  {
    id: 'AP-1001',
    vendor_name: 'Cisco Systems',
    invoice_number: 'CIS-INV-4482',
    amount: 12400,
    currency: 'USD',
    state: 'needs_info',
    owner_email: 'maya@soldenai.com',
    next_action: 'await_vendor_response',
    queue_age_minutes: 290,
    erp_status: 'connected',
    updated_at: isoAgo(12),
    primary_source: { source_type: 'gmail' },
    field_review_blockers: [{ field: 'vendor' }, { field: 'amount' }],
    memory: {
      execution_state: { owner_label: 'Maya R.', next_action: 'Ask vendor to confirm PO coverage' },
      context_summary: {
        who_owns_it: 'Maya R.',
        next_action: 'Ask vendor to confirm PO coverage',
        blocked_on: ['PO coverage not confirmed'],
        where_it_happened: ['gmail', 'slack'],
        evidence: { decision_refs: ['s1'], attachment_content_hash: 'hash-cisco' },
        latest_decision: { decided_at: isoAgo(12) },
      },
    },
  },
  {
    id: 'AP-1002',
    vendor_name: 'AWS Cloud Services',
    invoice_number: 'AWS-77421',
    amount: 1240.5,
    currency: 'USD',
    state: 'validated',
    owner_email: 'dana@soldenai.com',
    next_action: 'post_to_erp',
    queue_age_minutes: 84,
    erp_status: 'ready',
    updated_at: isoAgo(18),
    primary_source: { source_type: 'netsuite' },
    memory: {
      execution_state: { owner_label: 'Dana O.', next_action: 'Post to NetSuite after close lock lifts' },
      context_summary: {
        who_owns_it: 'Dana O.',
        next_action: 'Post to NetSuite after close lock lifts',
        where_it_happened: ['netsuite', 'agent'],
        evidence: { decision_refs: ['s2'] },
        latest_decision: { decided_at: isoAgo(18) },
      },
    },
  },
  {
    id: 'AP-1003',
    vendor_name: 'Booking Holdings BV',
    invoice_number: 'BOOK-2026-112',
    amount: 78000,
    currency: 'USD',
    state: 'needs_second_approval',
    owner_email: 'jane.finance@soldenai.com',
    next_action: 'second_approval',
    queue_age_minutes: 2160,
    erp_status: 'connected',
    updated_at: isoAgo(44),
    primary_source: { source_type: 'teams' },
    memory: {
      execution_state: { owner_label: 'Jane Finance', next_action: 'CFO approval for dual-control threshold' },
      context_summary: {
        who_owns_it: 'Jane Finance',
        next_action: 'CFO approval for dual-control threshold',
        blocked_on: ['Second approval required'],
        where_it_happened: ['teams'],
        evidence: { decision_refs: ['s3'] },
        latest_decision: { decided_at: isoAgo(44) },
      },
    },
  },
  {
    id: 'AP-1004',
    vendor_name: 'Google Cloud EMEA Limited',
    invoice_number: 'GCP-5527387118',
    amount: 40.5,
    currency: 'EUR',
    state: 'received',
    owner_email: '',
    next_action: 'review_fields',
    queue_age_minutes: 66,
    erp_status: 'connected',
    updated_at: isoAgo(66),
    primary_source: { source_type: 'gmail' },
    requires_field_review: true,
    memory: {
      execution_state: { next_action: 'Review extracted amount confidence' },
      context_summary: {
        next_action: 'Review extracted amount confidence',
        blocked_on: ['Amount confidence below threshold'],
        where_it_happened: ['gmail'],
        latest_decision: { decided_at: isoAgo(66) },
      },
    },
  },
  {
    id: 'AP-1005',
    vendor_name: 'Northwind Traders',
    invoice_number: 'NW-8901',
    amount: 6180,
    currency: 'USD',
    state: 'posted_to_erp',
    owner_email: 'ben@soldenai.com',
    next_action: '',
    queue_age_minutes: 33,
    erp_status: 'posted',
    updated_at: isoAgo(33),
    primary_source: { source_type: 'sage_intacct' },
    memory: {
      execution_state: { owner_label: 'Ben A.', next_action: 'Monitor payment confirmation' },
      context_summary: {
        who_owns_it: 'Ben A.',
        next_action: 'Monitor payment confirmation',
        where_it_happened: ['sage_intacct'],
        evidence: { decision_refs: ['s4'] },
        latest_decision: { decided_at: isoAgo(33) },
      },
    },
  },
  {
    id: 'AP-1006',
    vendor_name: 'Acme Coffee Supplies',
    invoice_number: 'ACM-2119',
    amount: 240,
    currency: 'USD',
    state: 'needs_approval',
    owner_email: 'maya@soldenai.com',
    next_action: 'approve_or_reject',
    queue_age_minutes: 480,
    erp_status: 'connected',
    updated_at: isoAgo(91),
    primary_source: { source_type: 'slack' },
    memory: {
      execution_state: { owner_label: 'Maya R.', next_action: 'Manager approval in Slack' },
      context_summary: {
        who_owns_it: 'Maya R.',
        next_action: 'Manager approval in Slack',
        where_it_happened: ['slack'],
        evidence: { decision_refs: ['s5'] },
        latest_decision: { decided_at: isoAgo(91) },
      },
    },
  },
];

const activityItems = [
  { id: 'act-1', box_type: 'ap_item', box_id: 'AP-1001', action: 'Asked vendor for missing PO context', subject: 'Cisco Systems - CIS-INV-4482', actor_label: 'Solden agent', surface: 'Gmail', tone: 'warning', ts: isoAgo(12) },
  { id: 'act-2', box_type: 'ap_item', box_id: 'AP-1002', action: 'Validated account coding', subject: 'AWS Cloud Services - AWS-77421', actor_label: 'Dana O.', surface: 'NetSuite', tone: 'success', ts: isoAgo(18) },
  { id: 'act-3', box_type: 'ap_item', box_id: 'AP-1003', action: 'Routed for second approval', subject: 'Booking Holdings BV - BOOK-2026-112', actor_label: 'Solden agent', surface: 'Teams', tone: 'warning', ts: isoAgo(44) },
  { id: 'act-4', box_type: 'ap_item', box_id: 'AP-1005', action: 'Posted bill to ERP', subject: 'Northwind Traders - NW-8901', actor_label: 'Solden agent', surface: 'Sage Intacct', tone: 'success', ts: isoAgo(33) },
  { id: 'act-5', box_type: 'ap_item', box_id: 'AP-1006', action: 'Slack approval card delivered', subject: 'Acme Coffee Supplies - ACM-2119', actor_label: 'Solden agent', surface: 'Slack', tone: 'info', ts: isoAgo(91) },
];

const responses = {
  '/auth/me': {
    email: 'mo@soldenai.com',
    name: 'Mo Mbalam',
    organization_id: 'org-dev',
    role: 'owner',
    workspace_role: 'owner',
  },
  '/api/workspace/bootstrap': bootstrap,
  '/api/workspace/entities': {
    entities: [
      { id: 'ent-all', name: 'Solden Group', code: 'GROUP' },
      { id: 'ent-us', name: 'Solden US', code: 'US' },
      { id: 'ent-uk', name: 'Solden UK', code: 'UK' },
    ],
  },
  '/api/ap/items/metrics/aggregation': { metrics: { exceptions_count: 7 } },
  '/api/workspace/records': {
    items: records,
    total: 45,
    limit: 15,
    offset: 0,
    has_more: false,
    total_count: 45,
    filtered_count: 45,
    slice_counts: { all_open: 45, blocked_exception: 7, overdue: 4 },
  },
  '/api/workspace/dashboard/approver-workload': {
    approvers: [
      { approver_id: 'maya', name: 'Maya R.', email: 'maya@soldenai.com', pending_count: 4, oldest_pending_age_days: 2 },
      { approver_id: 'jane', name: 'Jane Finance', email: 'jane.finance@soldenai.com', pending_count: 2, oldest_pending_age_days: 1 },
      { approver_id: 'ben', name: 'Ben A.', email: 'ben@soldenai.com', pending_count: 1, oldest_pending_age_days: 0 },
    ],
  },
  '/api/workspace/exceptions': {
    count: 7,
    total: 7,
    limit: 12,
    offset: 0,
    has_more: false,
    items: [
      {
        id: 'ex-1',
        box_type: 'ap_item',
        box_id: 'AP-1001',
        exception_type: 'po_context_missing',
        severity: 'medium',
        reason: 'Vendor has not confirmed the PO coverage for the Cisco renewal.',
        raised_at: isoAgo(12),
        box_summary: {
          vendor_name: 'Cisco Systems',
          invoice_number: 'CIS-INV-4482',
          amount: 12400,
          currency: 'USD',
        },
      },
      {
        id: 'ex-2',
        box_type: 'ap_item',
        box_id: 'AP-1003',
        exception_type: 'second_approval_required',
        severity: 'high',
        reason: 'Dual-control threshold requires CFO approval before posting.',
        raised_at: isoAgo(44),
        box_summary: {
          vendor_name: 'Booking Holdings BV',
          invoice_number: 'BOOK-2026-112',
          amount: 78000,
          currency: 'USD',
        },
      },
      {
        id: 'ex-3',
        box_type: 'vendor_onboarding_session',
        box_id: 'VOS-1007',
        exception_type: 'bank_detail_review',
        severity: 'medium',
        reason: 'New beneficiary details need registry and IBAN proof before first payment.',
        raised_at: isoAgo(66),
        metadata: { vendor_name: 'Google Cloud EMEA Limited' },
      },
    ],
  },
  '/api/workspace/exceptions/stats': {
    total_unresolved: 7,
    by_severity: { critical: 0, high: 2, medium: 5, low: 0 },
    by_type: { po_context_missing: 3, second_approval_required: 2, bank_detail_review: 2 },
    by_box_type: { ap_item: 5, vendor_onboarding_session: 2 },
  },
  '/api/workspace/dashboard/recent-activity': { items: activityItems },
  '/api/workspace/implementation/status': { all_complete: true, steps: [] },
  '/api/workspace/policy-proposals': { proposals: [] },
  '/api/workspace/ask/suggestions': {
    suggestions: [
      'What is blocked right now?',
      'Which invoices changed since yesterday?',
      'Which records need human judgment?',
    ],
  },
  '/health': { status: 'ok' },
};

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

window.fetch = async (input) => {
  const raw = typeof input === 'string' ? input : input?.url || '';
  const url = new URL(raw, window.location.origin);
  const path = url.pathname;
  if (path === '/api/workspace/ask') {
    return jsonResponse({
      answer: 'Seven records need judgment. Cisco is blocked on PO context, Booking needs second approval, and Google Cloud needs field review. [s1] [s2]',
      sources: [
        { id: 's1', summary: 'Cisco open blocker', link: { kind: 'record', ref: 'AP-1001' } },
        { id: 's2', summary: 'Booking approval route', link: { kind: 'record', ref: 'AP-1003' } },
      ],
    });
  }
  const direct = responses[path];
  if (direct) return jsonResponse(direct);
  return jsonResponse({ detail: `No dev harness response for ${path}` }, 404);
};

class DevEventSource {
  constructor() {
    setTimeout(() => {
      this.onopen?.({});
      this.onmessage?.({
        data: JSON.stringify({
          type: 'activity',
          data: { items: activityItems },
        }),
      });
      this.onmessage?.({
        data: JSON.stringify({
          type: 'stats',
          data: bootstrap.dashboard_stats,
        }),
      });
    }, 120);
  }
  close() {}
}
window.EventSource = DevEventSource;

render(html`<${App} />`, document.getElementById('app'));
