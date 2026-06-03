import { Link, useLocation } from 'wouter-preact';
import { useEffect, useState } from 'preact/hooks';
import { html } from '../utils/htm.js';
import { BrandMark } from './BrandMark.js';
import { useBootstrap, useOrgId } from './BootstrapContext.js';
import { api } from '../api/client.js';
import { WORKSPACE_NAV_GROUPS, getSidebarNavItems } from './workspaceNavigation.js';

/**
 * Sidebar nav for the work-in-progress control center.
 *
 * Four groups, ordered by what the operator does here:
 *   primary   — live work in progress (Home, Activity, Exceptions)
 *   workTypes — the box types the operator works in (Accounts Payable; later gated surfaces)
 *   data      — reference + read-only surfaces (Vendors, Reports, Audit log)
 *   admin     — policy + render-target config (Connections, Rules, Settings)
 *
 * Accounts Payable / Procurement / Builder are the workflow surfaces (box types the
 * system tracks), so they group under WORK TYPES, not DATA. DATA is for the
 * reference surfaces: the vendor directory, reporting, and the audit log. API
 * keys stay in the command palette and settings surfaces; they are not daily
 * operator chrome.
 */

// Per-item line icons (Feather/Lucide grammar). Functions so each render gets
// a fresh vnode; stroke is currentColor so icons inherit the link color +
// active-state teal automatically.
const ICONS = {
  home: () => html`<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="M9 22V12h6v10" />`,
  activity: () => html`<path d="M22 12h-4l-3 9L9 3l-3 9H2" />`,
  alert: () => html`<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" /><path d="M12 9v4" /><path d="M12 17h.01" />`,
  file: () => html`<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z" /><path d="M14 2v5h5" /><path d="M16 13H8" /><path d="M16 17H8" />`,
  cart: () => html`<circle cx="8" cy="21" r="1" /><circle cx="19" cy="21" r="1" /><path d="M2 2h2l2.6 12.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H5.1" />`,
  workflow: () => html`<rect width="8" height="8" x="3" y="3" rx="2" /><path d="M7 11v4a2 2 0 0 0 2 2h4" /><rect width="8" height="8" x="13" y="13" rx="2" />`,
  users: () => html`<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />`,
  chart: () => html`<path d="M3 3v18h18" /><path d="M18 17V9" /><path d="M13 17V5" /><path d="M8 17v-3" />`,
  shield: () => html`<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" /><path d="m9 12 2 2 4-4" />`,
  sliders: () => html`<path d="M21 4h-7" /><path d="M10 4H3" /><path d="M21 12h-9" /><path d="M8 12H3" /><path d="M21 20h-5" /><path d="M12 20H3" /><path d="M14 2v4" /><path d="M8 10v4" /><path d="M16 18v4" />`,
  link: () => html`<path d="M9 17H7A5 5 0 0 1 7 7h2" /><path d="M15 7h2a5 5 0 1 1 0 10h-2" /><line x1="8" x2="16" y1="12" y2="12" />`,
  key: () => html`<circle cx="7.5" cy="15.5" r="5.5" /><path d="m21 2-9.6 9.6" /><path d="m15.5 7.5 3 3L22 7l-3-3" />`,
  card: () => html`<rect width="20" height="14" x="2" y="5" rx="2" /><path d="M2 10h20" />`,
  gear: () => html`<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" /><circle cx="12" cy="12" r="3" />`,
};

function safeCount(value) {
  const n = Number(value || 0);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

function formatBadge(value) {
  const count = safeCount(value);
  if (!count) return '';
  return count > 99 ? '99+' : String(count);
}

function badgeForItem(item, badges) {
  if (!item.badge) return '';
  return formatBadge(badges[item.badge]);
}

function useSidebarBadges(bootstrap, orgId) {
  const initialDashboard = bootstrap?.dashboard_stats || bootstrap?.dashboard || {};
  const [dashboard, setDashboard] = useState(initialDashboard);
  const [exceptionCount, setExceptionCount] = useState(0);
  const [streamConnected, setStreamConnected] = useState(false);

  useEffect(() => {
    setDashboard(bootstrap?.dashboard_stats || bootstrap?.dashboard || {});
  }, [bootstrap]);

  useEffect(() => {
    let cancelled = false;
    let timer = null;

    async function loadExceptionStats() {
      try {
        const stats = await api('/api/workspace/exceptions/stats', { retry: false });
        if (!cancelled) setExceptionCount(safeCount(stats?.total_unresolved));
      } catch {
        if (!cancelled) setExceptionCount(0);
      }
    }

    if (orgId) {
      void loadExceptionStats();
      timer = window.setInterval(loadExceptionStats, 60000);
    }
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [orgId]);

  useEffect(() => {
    if (typeof EventSource === 'undefined') return undefined;
    const source = new EventSource('/api/workspace/dashboard/stream', { withCredentials: true });
    source.onopen = () => setStreamConnected(true);
    source.onmessage = (event) => {
      try {
        const frame = JSON.parse(event.data);
        if (frame?.type === 'stats' && frame.data) setDashboard(frame.data);
        if (frame?.type === 'heartbeat') setStreamConnected(true);
      } catch { /* ignore bad frames */ }
    };
    source.onerror = () => setStreamConnected(false);
    return () => source.close();
  }, [orgId]);

  return {
    accountsPayableInFlight: safeCount(dashboard?.in_flight),
    exceptions: exceptionCount,
    activityLive: streamConnected,
  };
}

export function SidebarNav() {
  const [pathname] = useLocation();
  const bootstrap = useBootstrap();
  const orgId = useOrgId();
  const badges = useSidebarBadges(bootstrap, orgId);

  const visibleItems = getSidebarNavItems(bootstrap);

  return html`
    <nav class="cl-sidebar-nav" aria-label="Primary">
      <div class="cl-sidebar-brand">
        <${BrandMark} height=${32} tone="primary" />
      </div>
      ${WORKSPACE_NAV_GROUPS.map(
        (group) => html`
          <div class="cl-sidebar-group" key=${group.id}>
            ${group.label
              ? html`<div class="cl-sidebar-group-label">${group.label}</div>`
              : null}
            <ul class="cl-sidebar-list">
              ${visibleItems.filter((i) => i.group === group.id).map((item) => {
                const active =
                  item.path === '/'
                    ? pathname === '/'
                    : pathname === item.path || pathname.startsWith(`${item.path}/`);
                const badge = badgeForItem(item, badges);
                return html`
                  <li key=${item.path}>
                    <${Link} href=${item.path}
                      class=${`cl-sidebar-link ${active ? 'is-active' : ''}`}>
                      <svg class="cl-sidebar-icon" viewBox="0 0 24 24" fill="none"
                        stroke="currentColor" stroke-width="1.75"
                        stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        ${ICONS[item.icon] ? ICONS[item.icon]() : null}
                      </svg>
                      <span class="cl-sidebar-label">${item.label}</span>
                      ${item.indicator === 'activity' && badges.activityLive
                        ? html`<span class="cl-sidebar-live-dot" aria-label="Live activity stream"></span>`
                        : null}
                      ${badge
                        ? html`<span class="cl-sidebar-badge" aria-label=${`${badge} open`}>${badge}</span>`
                        : null}
                    <//>
                  </li>
                `;
              })}
            </ul>
          </div>
        `
      )}
    </nav>
  `;
}
