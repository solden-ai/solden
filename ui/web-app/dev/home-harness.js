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

const vendorDirectory = [
  {
    vendor_name: 'Google Cloud EMEA Limited',
    primary_email: 'payments-noreply@google.com',
    currency: 'EUR',
    currency_mixed: true,
    total_amount: 439,
    invoice_count: 21,
    open_count: 21,
    issue_count: 21,
    approval_count: 0,
    last_activity_at: isoAgo(42),
    top_states: [{ state: 'received', count: 21 }],
    top_exception_codes: [
      { exception_code: 'critical_field_low_confidence', count: 19 },
      { exception_code: 'field_conflict', count: 1 },
    ],
    profile: { status: 'active' },
  },
  {
    vendor_name: 'Account Name: | MICROSOFT',
    primary_email: 'microsoft-noreply@microsoft.com',
    currency: 'ZAR',
    total_amount: 0,
    invoice_count: 11,
    open_count: 11,
    issue_count: 11,
    approval_count: 0,
    last_activity_at: isoAgo(33000),
    top_states: [{ state: 'received', count: 11 }],
    top_exception_codes: [{ exception_code: 'critical_field_low_confidence', count: 11 }],
    profile: { status: 'active' },
  },
  {
    vendor_name: 'Google Payments',
    primary_email: 'payments-noreply@google.com',
    currency: 'USD',
    total_amount: 0,
    invoice_count: 4,
    open_count: 4,
    issue_count: 4,
    approval_count: 0,
    last_activity_at: isoAgo(1380),
    top_states: [{ state: 'received', count: 4 }],
    top_exception_codes: [{ exception_code: 'critical_field_low_confidence', count: 4 }],
    profile: { status: 'active' },
  },
  {
    vendor_name: 'Cisco Systems',
    primary_email: 'billing@cisco.example',
    currency: 'USD',
    total_amount: 12400,
    invoice_count: 6,
    open_count: 2,
    issue_count: 2,
    approval_count: 1,
    last_activity_at: isoAgo(12),
    top_states: [{ state: 'needs_info', count: 2 }, { state: 'validated', count: 4 }],
    top_exception_codes: [{ exception_code: 'po_context_missing', count: 2 }],
    profile: { terms: 'Net 30', status: 'active', requires_po: true },
  },
];

const googleCloudVendorDetail = {
  vendor_name: 'Google Cloud EMEA Limited',
  profile: {
    status: 'active',
    currency: 'EUR',
    terms: 'Net 30',
    registry_verified: true,
    registry_verification_provider: 'OpenCorporates',
    registry_verification_at: isoAgo(7200),
    registry_verification_payload: {
      company_number: 'IE551887',
      jurisdiction: 'ie',
      match_score: 0.94,
    },
    sender_domains: ['google.com', 'googlepayments.com'],
    vendor_aliases: ['Google Payments', 'Google Cloud'],
    custom_routing: {
      approver_group: 'finance_ops',
      channel: 'slack',
      reason: 'cloud_infrastructure',
    },
    requires_po: true,
    agent_confidence: 0.86,
  },
  erp: {
    vendor_id: 'NS-VEND-00482',
    tax_id: 'IE6388047V',
    registration_number: '551887',
    jurisdiction: 'IE',
    payment_terms: 'Net 30',
    address: '70 Sir John Rogerson Quay, Dublin',
    primary_contact_email: 'payments-noreply@google.com',
  },
  summary: {
    invoice_count: 21,
    open_count: 21,
    posted_count: 0,
    issue_count: 21,
    total_amount: 439,
    currency: 'EUR',
    primary_email: 'payments-noreply@google.com',
    last_activity_at: isoAgo(42),
    agent_confidence: 0.86,
  },
  risk: {
    score: 32,
    components: [
      { label: 'Field extraction confidence below threshold' },
      { label: 'Vendor aliases require review' },
    ],
  },
  issue_summary: {
    total: 21,
    needs_info: 2,
    field_review: 19,
  },
  top_exception_codes: [
    { exception_code: 'critical_field_low_confidence', count: 19 },
    { exception_code: 'field_conflict', count: 1 },
  ],
  verified_ibans: [
    { iban_masked: 'IE29 **** 8310', source: 'bank_verification', verified_at: isoAgo(12000) },
  ],
  fraud_flags: [],
  open_issues: [
    {
      id: 'AP-1004',
      invoice_number: 'GCP-5527387118',
      amount: 40.5,
      currency: 'EUR',
      state: 'received',
      issue_kind: 'field_review',
      issue_label: 'Field review',
      issue_summary: 'Vendor and amount confidence need confirmation before ERP follow-up.',
      updated_at: isoAgo(42),
      exception_code: 'critical_field_low_confidence',
    },
    {
      id: 'AP-1011',
      invoice_number: 'GCP-5541991049',
      amount: 0,
      currency: 'USD',
      state: 'received',
      issue_kind: 'field_review',
      issue_label: 'Field review',
      issue_summary: 'Zero-value invoice needs operator confirmation.',
      updated_at: isoAgo(220),
      exception_code: 'field_conflict',
    },
  ],
  recent_items: [
    {
      id: 'AP-1004',
      invoice_number: 'GCP-5527387118',
      amount: 40.5,
      currency: 'EUR',
      state: 'received',
      exception_code: 'critical_field_low_confidence',
      updated_at: isoAgo(42),
    },
    {
      id: 'AP-1011',
      invoice_number: 'GCP-5541991049',
      amount: 0,
      currency: 'USD',
      state: 'received',
      exception_code: 'field_conflict',
      updated_at: isoAgo(220),
    },
    {
      id: 'AP-1012',
      invoice_number: 'GCP-5499678906',
      amount: 38.46,
      currency: 'EUR',
      state: 'received',
      exception_code: 'critical_field_low_confidence',
      updated_at: isoAgo(480),
    },
  ],
  exception_trend: [
    { bucket: 'Mar', exception_count: 3 },
    { bucket: 'Apr', exception_count: 5 },
    { bucket: 'May', exception_count: 8 },
    { bucket: 'Jun', exception_count: 5 },
  ],
};

const microsoftVendorInvoices = [
  ['E0100YIZ24', 33000],
  ['E0100WKD65', 47647],
  ['E0100W9CTC', 47647],
  ['E0100WUUI4', 47647],
  ['E0100X6DAA', 47647],
  ['E0100XH23J', 47647],
  ['E0100XQE15', 47648],
  ['E0100XZ07W', 47648],
  ['E0100Y8WQR', 47648],
  ['E0100YRABT', 47648],
  ['E0100Z0BRY', 47649],
];

const microsoftVendorDetail = {
  vendor_name: 'Account Name: | MICROSOFT',
  profile: {
    status: 'active',
    currency: 'ZAR',
    primary_contact_email: 'microsoft-noreply@microsoft.com',
    requires_po: false,
    agent_confidence: 0.72,
  },
  erp: {
    primary_contact_email: 'microsoft-noreply@microsoft.com',
    currency: 'ZAR',
  },
  summary: {
    invoice_count: 11,
    open_count: 11,
    posted_count: 0,
    issue_count: 11,
    total_amount: 0,
    currency: 'ZAR',
    primary_email: 'microsoft-noreply@microsoft.com',
    last_activity_at: isoAgo(33000),
    agent_confidence: 0.72,
  },
  risk: {
    score: 0,
    components: [],
  },
  issue_summary: {
    total: 11,
    field_review: 11,
  },
  top_exception_codes: [
    { exception_code: 'critical_field_low_confidence', count: 11 },
  ],
  verified_ibans: [],
  fraud_flags: [],
  open_issues: microsoftVendorInvoices.map(([invoiceNumber, age], idx) => ({
    id: `AP-MS-${idx + 1}`,
    invoice_number: invoiceNumber,
    amount: 0,
    currency: 'ZAR',
    state: 'received',
    issue_kind: 'field_review',
    issue_label: 'Field review',
    issue_summary: 'Review amount before this invoice moves forward.',
    updated_at: isoAgo(age),
    exception_code: 'critical_field_low_confidence',
  })),
  recent_items: microsoftVendorInvoices.map(([invoiceNumber, age], idx) => ({
    id: `AP-MS-${idx + 1}`,
    invoice_number: invoiceNumber,
    amount: 0,
    currency: 'ZAR',
    state: 'received',
    exception_code: 'critical_field_low_confidence',
    updated_at: isoAgo(age),
  })),
  exception_trend: [],
};

const activityItems = [
  { id: 'act-1', box_type: 'ap_item', box_id: 'AP-1001', action: 'Asked vendor for missing PO context', subject: 'Cisco Systems - CIS-INV-4482', actor_label: 'Solden agent', surface: 'Gmail', tone: 'warning', ts: isoAgo(12) },
  { id: 'act-2', box_type: 'ap_item', box_id: 'AP-1002', action: 'Validated account coding', subject: 'AWS Cloud Services - AWS-77421', actor_label: 'Dana O.', surface: 'NetSuite', tone: 'success', ts: isoAgo(18) },
  { id: 'act-3', box_type: 'ap_item', box_id: 'AP-1003', action: 'Routed for second approval', subject: 'Booking Holdings BV - BOOK-2026-112', actor_label: 'Solden agent', surface: 'Teams', tone: 'warning', ts: isoAgo(44) },
  { id: 'act-4', box_type: 'ap_item', box_id: 'AP-1005', action: 'Posted bill to ERP', subject: 'Northwind Traders - NW-8901', actor_label: 'Solden agent', surface: 'Sage Intacct', tone: 'success', ts: isoAgo(33) },
  { id: 'act-5', box_type: 'ap_item', box_id: 'AP-1006', action: 'Slack approval card delivered', subject: 'Acme Coffee Supplies - ACM-2119', actor_label: 'Solden agent', surface: 'Slack', tone: 'info', ts: isoAgo(91) },
];

const auditEvents = [
  {
    id: 'evt-audit-1',
    ts: isoAgo(8),
    event_type: 'state_transition',
    actor_id: 'agent_runtime',
    actor_type: 'system',
    box_type: 'ap_item',
    box_id: 'AP-1004',
    prev_state: 'received',
    new_state: 'needs_info',
    governance_verdict: 'observed',
    agent_confidence: 0.86,
    decision_reason: 'Field confidence below threshold; operator review required.',
    source: 'gmail',
    policy_version: 'ap-policy-2026.06',
    capability: 'field_review',
    chain_seq: 39,
    hash: 'hash_evt_audit_1',
    prev_hash: 'hash_evt_audit_0',
    payload_json: {
      work_item: 'AP-1004',
      blocker: 'Amount confidence below threshold',
      evidence_ref: 'gmail:thread:gcp-5527387118',
      next_action: 'Operator review required before ERP follow-up',
    },
  },
  {
    id: 'evt-audit-2',
    ts: isoAgo(18),
    event_type: 'approval_requested',
    actor_id: 'maya@soldenai.com',
    actor_type: 'human',
    box_type: 'ap_item',
    box_id: 'AP-1006',
    prev_state: 'validated',
    new_state: 'pending_approval',
    governance_verdict: 'allowed',
    agent_confidence: 0.91,
    decision_reason: 'Manager approval required by policy.',
    source: 'slack',
    policy_version: 'ap-policy-2026.06',
    capability: 'approval_routing',
    chain_seq: 40,
    hash: 'hash_evt_audit_2',
    prev_hash: 'hash_evt_audit_1',
    payload_json: {
      approver: 'maya@soldenai.com',
      approval_surface: 'slack',
      threshold: 'manager approval',
    },
  },
  {
    id: 'evt-audit-3',
    ts: isoAgo(33),
    event_type: 'erp_post_completed',
    actor_id: 'agent_runtime',
    actor_type: 'system',
    box_type: 'ap_item',
    box_id: 'AP-1005',
    prev_state: 'validated',
    new_state: 'posted_to_erp',
    governance_verdict: 'allowed',
    agent_confidence: 0.94,
    decision_reason: 'Invoice passed validation and posted to Sage Intacct.',
    source: 'sage_intacct',
    policy_version: 'ap-policy-2026.06',
    capability: 'erp_post',
    chain_seq: 41,
    hash: 'hash_evt_audit_3',
    prev_hash: 'hash_evt_audit_2',
    payload_json: {
      erp: 'sage_intacct',
      erp_record_id: 'SI-BILL-1005',
      posted_amount: 6180,
      currency: 'USD',
    },
  },
];

const approvalRules = [
  {
    id: 'rule-low-risk',
    name: 'Low-risk invoices auto-approve',
    description: 'Small matched invoices can move forward without human review.',
    priority: 100,
    workflow: 'ap',
    entity_id: null,
    conditions: {
      all_of: [
        { field: 'amount', op: 'lt', value: 500 },
        { field: 'exception_count', op: 'eq', value: 0 },
      ],
    },
    actions: [{ type: 'auto_approve' }],
    status: 'active',
    updated_at: isoAgo(1400),
  },
  {
    id: 'rule-manager',
    name: 'Manager approval above threshold',
    description: 'Route mid-value AP records to the owning department manager.',
    priority: 200,
    workflow: 'ap',
    entity_id: 'ent-uk',
    conditions: { all_of: [{ field: 'amount', op: 'gte', value: 5000 }] },
    actions: [{ type: 'route_to_role', role: 'department_manager' }],
    status: 'active',
    updated_at: isoAgo(940),
  },
  {
    id: 'rule-dual',
    name: 'Dual approval for high-value spend',
    description: 'Large invoices require a second approver before ERP posting.',
    priority: 300,
    workflow: 'ap',
    entity_id: null,
    conditions: { all_of: [{ field: 'amount', op: 'gte', value: 50000 }] },
    actions: [{ type: 'require_dual_approval' }],
    status: 'active',
    updated_at: isoAgo(240),
  },
  {
    id: 'rule-field-review',
    name: 'Hold low-confidence extraction',
    description: 'When vendor or amount confidence drops below threshold, hold for finance review.',
    priority: 400,
    workflow: 'ap',
    entity_id: null,
    conditions: {
      any_of: [
        { field: 'vendor_confidence', op: 'lt', value: 0.8 },
        { field: 'amount_confidence', op: 'lt', value: 0.85 },
      ],
    },
    actions: [{ type: 'hold_for_finance_review' }],
    status: 'paused',
    updated_at: isoAgo(70),
  },
];

const approvalRuleTemplates = [
  {
    id: 'tpl-small-auto',
    name: 'Small matched work auto-approves',
    description: 'Let low-risk records move after match and duplicate checks pass.',
    priority: 100,
    conditions: { all_of: [{ field: 'amount', op: 'lt', value: 500 }] },
    actions: [{ type: 'auto_approve' }],
  },
  {
    id: 'tpl-manager-route',
    name: 'Route by department owner',
    description: 'Send approval requests to the role responsible for the owning department.',
    priority: 200,
    conditions: { all_of: [{ field: 'amount', op: 'gte', value: 5000 }] },
    actions: [{ type: 'route_to_role', role: 'department_manager' }],
  },
  {
    id: 'tpl-dual-approval',
    name: 'Dual approval threshold',
    description: 'Require two approvers for high-value or high-risk records.',
    priority: 300,
    conditions: { all_of: [{ field: 'amount', op: 'gte', value: 50000 }] },
    actions: [{ type: 'require_dual_approval' }],
  },
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
  '/api/ap/items/vendors': {
    vendors: vendorDirectory,
  },
  '/api/ap/items/vendors/Google%20Cloud%20EMEA%20Limited': googleCloudVendorDetail,
  '/api/ap/items/vendors/Account%20Name%3A%20%7C%20MICROSOFT': microsoftVendorDetail,
  '/api/workspace/vendor-intelligence/duplicates': {
    clusters: [],
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
  '/api/workspace/connections/health': {
    computed_at: isoAgo(1),
    integrations: [
      {
        integration_type: 'gmail',
        label: 'Gmail',
        status: 'healthy',
        last_sync_at: isoAgo(8),
        events_24h: 34,
        errors_24h: 0,
      },
      {
        integration_type: 'slack',
        label: 'Slack',
        status: 'healthy',
        last_sync_at: isoAgo(12),
        events_24h: 11,
        errors_24h: 0,
      },
      {
        integration_type: 'netsuite',
        label: 'NetSuite',
        status: 'healthy',
        last_sync_at: isoAgo(18),
        events_24h: 9,
        errors_24h: 0,
      },
    ],
    webhooks: { delivered: 18, retrying: 0, failed: 0 },
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
  '/api/workspace/reports/subscriptions': { subscriptions: [] },
  '/api/workspace/reports/volume': {
    summary: {
      total_invoices: 40,
      total_amount: 8.39,
      distinct_vendors: 7,
      currency: 'USD',
    },
    series: [
      { bucket: '2026-W17', invoice_count: 3 },
      { bucket: '2026-W18', invoice_count: 17 },
      { bucket: '2026-W19', invoice_count: 13 },
      { bucket: '2026-W20', invoice_count: 4 },
      { bucket: '2026-W24', invoice_count: 2 },
    ],
    breakdown: [
      { vendor_name: 'Google Cloud EMEA Limited', invoice_count: 21, total_amount: 8.39, currency: 'USD' },
      { vendor_name: 'Account Name: | MICROSOFT', invoice_count: 11, total_amount: 0, currency: 'ZAR' },
      { vendor_name: 'Google Payments', invoice_count: 4, total_amount: 0, currency: 'USD' },
    ],
  },
  '/api/workspace/reports/agent-performance': {
    summary: {
      total_items: 40,
      auto_resolved_count: 28,
      exception_count: 7,
      avg_confidence: 0.86,
    },
    series: [
      { bucket: '2026-W17', auto_resolution_rate: 0.62 },
      { bucket: '2026-W18', auto_resolution_rate: 0.71 },
      { bucket: '2026-W19', auto_resolution_rate: 0.76 },
      { bucket: '2026-W20', auto_resolution_rate: 0.69 },
      { bucket: '2026-W24', auto_resolution_rate: 0.8 },
    ],
    breakdown: [],
  },
  '/api/workspace/reports/cycle-time': {
    summary: {
      avg_cycle_days: 1.8,
      p50_cycle_days: 1.1,
      p90_cycle_days: 3.4,
      posted_count: 23,
    },
    series: [
      { bucket: '2026-W17', avg_cycle_days: 2.6 },
      { bucket: '2026-W18', avg_cycle_days: 2.1 },
      { bucket: '2026-W19', avg_cycle_days: 1.7 },
      { bucket: '2026-W20', avg_cycle_days: 1.4 },
      { bucket: '2026-W24', avg_cycle_days: 1.2 },
    ],
    breakdown: [
      { entity_name: 'Solden Group', posted_count: 23, avg_cycle_days: 1.8, p90_cycle_days: 3.4 },
    ],
  },
  '/api/workspace/reports/exception-breakdown': {
    summary: {
      total_exceptions: 30,
      distinct_codes: 3,
      top_code: 'critical_field_low_confidence',
      top_code_count: 18,
    },
    series: [
      { bucket: '2026-W17', total_exceptions: 4 },
      { bucket: '2026-W18', total_exceptions: 9 },
      { bucket: '2026-W19', total_exceptions: 7 },
      { bucket: '2026-W20', total_exceptions: 6 },
      { bucket: '2026-W24', total_exceptions: 4 },
    ],
    breakdown: [
      { exception_code: 'critical_field_low_confidence', count: 18, share: 0.6 },
      { exception_code: 'field_conflict', count: 7, share: 0.23 },
      { exception_code: 'invalid_amount', count: 5, share: 0.17 },
    ],
  },
  '/api/workspace/reports/vendor-quality': {
    summary: {
      ranked_vendor_count: 7,
      avg_exception_rate: 0.44,
      worst_vendor: 'Google Cloud EMEA Limited',
      worst_exception_rate: 1,
      min_invoices_floor: 3,
    },
    series: [],
    breakdown: [
      { vendor_name: 'Google Cloud EMEA Limited', invoice_count: 21, exception_count: 21, exception_rate: 1 },
      { vendor_name: 'Account Name: | MICROSOFT', invoice_count: 11, exception_count: 11, exception_rate: 1 },
      { vendor_name: 'Cisco Systems', invoice_count: 6, exception_count: 2, exception_rate: 0.33 },
    ],
  },
  '/api/workspace/audit/retention': {
    effective_days: 7,
    tier_ceiling_days: 7,
    configured_days: null,
  },
  '/api/workspace/audit/chain-status': {
    chain_intact: true,
    chain_length: 41,
    verified_at: isoAgo(2),
  },
  '/api/workspace/audit/search': {
    count: 3,
    next_cursor: null,
    events: auditEvents,
  },
  '/api/workspace/rules': {
    rules: approvalRules,
  },
  '/api/workspace/rules/templates': {
    templates: approvalRuleTemplates,
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
  if (path === '/api/workspace/rules/test') {
    return jsonResponse({
      result: {
        matched_rule_id: 'rule-manager',
        matched_rule_name: 'Manager approval above threshold',
        actions: [{ type: 'route_to_role', role: 'department_manager' }],
        trace: approvalRules.map((rule) => ({
          rule_id: rule.id,
          rule_name: rule.name,
          priority: rule.priority,
          matched: rule.id === 'rule-manager',
          skipped_reason: rule.id === 'rule-manager' ? null : 'conditions did not match',
          all_of: rule.conditions?.all_of || [],
        })),
      },
    });
  }
  if (path.startsWith('/api/workspace/rules/') && path.endsWith('/versions')) {
    const ruleId = decodeURIComponent(path.split('/').slice(-2)[0] || '');
    const rule = approvalRules.find((item) => item.id === ruleId);
    return rule
      ? jsonResponse({
        versions: [
          {
            ...rule,
            version_number: 2,
            changed_at: rule.updated_at,
            changed_by: 'mo@soldenai.com',
            change_note: 'Adjusted threshold after finance review.',
          },
          {
            ...rule,
            version_number: 1,
            changed_at: isoAgo(3200),
            changed_by: 'system@solden.local',
            change_note: 'Initial policy draft.',
          },
        ],
      })
      : jsonResponse({ detail: `No dev harness rule for ${ruleId}` }, 404);
  }
  if (path.startsWith('/api/workspace/audit/event/')) {
    const eventId = decodeURIComponent(path.split('/').pop() || '');
    const event = auditEvents.find((item) => item.id === eventId);
    return event
      ? jsonResponse({ event })
      : jsonResponse({ detail: `No dev harness audit event for ${eventId}` }, 404);
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
