import { hasCapability } from '../utils/capabilities.js';
import { ACCOUNTS_PAYABLE_ROUTE } from '../utils/record-route.js';

export const WORKSPACE_NAV_GROUPS = [
  { id: 'primary', label: '' },
  { id: 'workTypes', label: 'WORK TYPES' },
  { id: 'data', label: 'DATA' },
  { id: 'admin', label: 'ADMIN' },
];

export const WORKSPACE_NAV_ITEMS = [
  {
    path: '/',
    label: 'Home',
    group: 'primary',
    icon: 'home',
    sidebar: true,
    command: true,
    commandSub: 'Workspace control center',
    tokens: ['home', 'overview', 'dashboard', 'control', 'center'],
  },
  {
    path: '/activity',
    label: 'Activity',
    group: 'primary',
    icon: 'activity',
    sidebar: true,
    command: true,
    indicator: 'activity',
    commandSub: 'Live work activity',
    tokens: ['activity', 'live', 'feed', 'agent'],
  },
  {
    path: '/exceptions',
    label: 'Exceptions',
    group: 'primary',
    icon: 'alert',
    sidebar: true,
    command: true,
    badge: 'exceptions',
    commandSub: 'Records the agent escalated for human judgment',
    tokens: ['exceptions', 'errors', 'blockers', 'review', 'queue', 'attention'],
  },
  {
    path: ACCOUNTS_PAYABLE_ROUTE,
    label: 'Accounts Payable',
    group: 'workTypes',
    icon: 'file',
    sidebar: true,
    command: true,
    badge: 'accountsPayableInFlight',
    commandSub: 'Search and inspect AP records',
    tokens: ['accounts', 'payable', 'records', 'invoices', 'ap', 'work', 'type'],
  },
  {
    path: '/procurement',
    label: 'Procurement',
    group: 'workTypes',
    icon: 'cart',
    sidebar: true,
    command: true,
    capability: 'view_procurement',
    commandSub: 'Purchase orders and approval workflow',
    tokens: ['procurement', 'purchase', 'po', 'orders', 'work', 'type'],
  },
  {
    path: '/workflows',
    label: 'Builder',
    group: 'workTypes',
    icon: 'workflow',
    sidebar: true,
    command: true,
    capability: 'view_workflow_builder',
    commandSub: 'Create custom work types',
    tokens: ['workflows', 'builder', 'custom', 'box', 'types', 'spec', 'no-code'],
  },
  {
    path: '/vendors',
    label: 'Vendors',
    group: 'data',
    icon: 'users',
    sidebar: true,
    command: true,
    commandSub: 'Vendor directory',
    tokens: ['vendors', 'suppliers'],
  },
  {
    path: '/reports',
    label: 'Reports',
    group: 'data',
    icon: 'chart',
    sidebar: true,
    command: true,
    commandSub: 'Volume, agent performance, cycle, exceptions, vendor quality',
    tokens: ['reports', 'analytics', 'metrics'],
  },
  {
    path: '/audit',
    label: 'Audit log',
    group: 'data',
    icon: 'shield',
    sidebar: true,
    command: true,
    commandSub: 'Append-only governance trail',
    tokens: ['audit', 'history', 'governance'],
  },
  {
    path: '/connections',
    label: 'Connections',
    group: 'admin',
    icon: 'link',
    sidebar: true,
    command: true,
    commandSub: 'ERP, Slack, Teams, Gmail',
    tokens: ['connections', 'integrations', 'erp', 'slack', 'teams', 'gmail'],
  },
  {
    path: '/rules',
    label: 'Approval rules',
    group: 'admin',
    icon: 'sliders',
    sidebar: true,
    command: true,
    commandSub: 'Configure approval routing',
    tokens: ['rules', 'policy', 'approval'],
  },
  {
    path: '/settings',
    label: 'Settings',
    group: 'admin',
    icon: 'gear',
    sidebar: true,
    command: true,
    commandSub: 'Company, users, policies, billing',
    tokens: ['settings', 'config', 'preferences', 'billing', 'team'],
  },
  {
    path: '/api-keys',
    label: 'API keys',
    icon: 'key',
    sidebar: false,
    command: true,
    capability: 'manage_admin_pages',
    commandSub: 'Service account access and rotation',
    tokens: ['api', 'keys', 'tokens', 'agent', 'identity'],
  },
  {
    path: '/plan',
    label: 'Plan',
    icon: 'card',
    sidebar: false,
    command: true,
    commandSub: 'Subscription, usage, billing',
    tokens: ['plan', 'billing', 'subscription'],
  },
  {
    path: '/status',
    label: 'Status',
    icon: 'activity',
    sidebar: false,
    command: true,
    commandSub: 'Operational health',
    tokens: ['status', 'health', 'uptime', 'incidents'],
  },
  {
    path: '/onboarding',
    label: 'Onboarding',
    icon: 'workflow',
    sidebar: false,
    command: true,
    commandSub: 'Setup wizard',
    tokens: ['onboarding', 'setup', 'wizard'],
  },
];

function canShowItem(item, bootstrap) {
  return !item.capability || hasCapability(bootstrap, item.capability);
}

export function getSidebarNavItems(bootstrap) {
  return WORKSPACE_NAV_ITEMS.filter((item) => item.sidebar && canShowItem(item, bootstrap));
}

export function getCommandNavEntries(bootstrap) {
  return WORKSPACE_NAV_ITEMS
    .filter((item) => item.command && canShowItem(item, bootstrap))
    .map((item) => ({
      kind: 'nav',
      label: item.label,
      sub: item.commandSub,
      path: item.path,
      tokens: item.tokens || [],
    }));
}
