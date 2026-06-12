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

// Solden-specific rail icons. They keep the same 24px line grammar, but the
// shapes map to the actual workspace surfaces instead of generic app chrome.
const ICONS = {
  home: () => html`<path d="M4 10.5 12 4l8 6.5" /><path d="M6.5 10.5V20h11v-9.5" /><path d="M10 20v-5h4v5" /><circle cx="17" cy="8.5" r="1.3" fill="currentColor" stroke="none" />`,
  activity: () => html`<path d="M4 6.5h10" /><path d="M4 12h6" /><path d="M4 17.5h8" /><path d="M15 17.5c2.2 0 4-1.8 4-4 0-1.6-.9-3-2.3-3.6" /><path d="m16 6 3.5 3.5L16 13" />`,
  alert: () => html`<path d="M12 3.5 20.5 12 12 20.5 3.5 12 12 3.5Z" /><path d="M12 8.5v4.2" /><circle cx="12" cy="16" r=".8" fill="currentColor" stroke="none" />`,
  file: () => html`<path d="M7 3.5h7l4 4V20a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 20V5a1.5 1.5 0 0 1 1.5-1.5Z" /><path d="M14 3.5V8h4" /><path d="M9 12h6" /><path d="M9 15.5h4" /><circle cx="16.5" cy="16" r="1.4" fill="currentColor" stroke="none" />`,
  cart: () => html`<path d="M5 8h14l-1.1 10.1a2 2 0 0 1-2 1.8H8.1a2 2 0 0 1-2-1.8L5 8Z" /><path d="M8.5 8a3.5 3.5 0 0 1 7 0" /><path d="M9 13h6" /><path d="M9 16h4" />`,
  workflow: () => html`<circle cx="6" cy="7" r="2.5" /><circle cx="18" cy="7" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M8.4 8.3 11 11a3 3 0 0 1 .9 2.1v2.4" /><path d="M15.6 8.3 13 11a3 3 0 0 0-.9 2.1v2.4" />`,
  users: () => html`<rect x="4" y="4.5" width="16" height="15" rx="3" /><circle cx="9" cy="10" r="2" /><path d="M6.5 16c.7-1.6 1.9-2.4 3.5-2.4s2.8.8 3.5 2.4" /><path d="M14.5 9h2.5" /><path d="M14.5 12.5H18" /><path d="M14.5 16H17" />`,
  chart: () => html`<path d="M4 20V5" /><path d="M4 20h16" /><rect x="7" y="12" width="2.5" height="5" rx=".6" /><rect x="11" y="8" width="2.5" height="9" rx=".6" /><rect x="15" y="10" width="2.5" height="7" rx=".6" /><path d="m7.5 8.5 4-3 3 2 4-4" />`,
  shield: () => html`<path d="M12 3.2c1.9 1.5 4.2 2.4 6.5 2.6v5.5c0 4.5-2.6 7.6-6.5 9.5-3.9-1.9-6.5-5-6.5-9.5V5.8c2.3-.2 4.6-1.1 6.5-2.6Z" /><path d="M9 12.3 11.1 14.5 15.5 10" />`,
  sliders: () => html`<circle cx="6" cy="6" r="2" /><path d="M8 6h4a3 3 0 0 1 3 3v1.5" /><path d="M15 10.5 18 13.5 15 16.5 12 13.5Z" /><path d="M6 8v5a4 4 0 0 0 4 4h2.5" /><path d="m16.7 13.5.8.8 1.6-1.9" />`,
  link: () => html`<path d="M7.5 8.5 5.7 6.7a3.3 3.3 0 0 1 4.6-4.7l2.4 2.4" /><path d="M16.5 15.5l1.8 1.8a3.3 3.3 0 0 1-4.6 4.7l-2.4-2.4" /><path d="m8.8 15.2 6.4-6.4" /><path d="M9.3 5.7 18.3 14.7" /><path d="M5.7 9.3 14.7 18.3" />`,
  key: () => html`<circle cx="8" cy="15" r="4.5" /><path d="m11.5 11.5 8-8" /><path d="M17 6h3v3" /><path d="M14.5 8.5 17 11" />`,
  card: () => html`<rect x="3" y="5.5" width="18" height="13" rx="2.5" /><path d="M3 10h18" /><path d="M7 14.5h4" /><path d="M15 14.5h2" />`,
  gear: () => html`<path d="M12 2.8 13.6 5.1l2.8.4.8 2.7 2.2 1.7-1.1 2.6 1.1 2.6-2.2 1.7-.8 2.7-2.8.4L12 21.2l-1.6-2.3-2.8-.4-.8-2.7-2.2-1.7 1.1-2.6-1.1-2.6 2.2-1.7.8-2.7 2.8-.4L12 2.8Z" /><circle cx="12" cy="12" r="3.2" />`,
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

function collapsedLabelForItem(item, badge, badges) {
  const details = [];
  if (badge) details.push(`${badge} open`);
  if (item.indicator === 'activity' && badges.activityLive) details.push('live');
  return details.length ? `${item.label}: ${details.join(', ')}` : item.label;
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

export function SidebarNav({ collapsed = false, onToggleCollapse = () => {} } = {}) {
  const [pathname] = useLocation();
  const bootstrap = useBootstrap();
  const orgId = useOrgId();
  const badges = useSidebarBadges(bootstrap, orgId);

  const visibleItems = getSidebarNavItems(bootstrap);

  return html`
    <nav class="cl-sidebar-nav" aria-label="Primary">
      <div class="cl-sidebar-brand">
        <div class="cl-sidebar-brand-lockup">
          <img class="cl-sidebar-brand-mark" src="/favicon.png" alt="" aria-hidden="true" />
          <span class="cl-sidebar-brand-full">
            <${BrandMark} height=${32} tone="primary" />
          </span>
        </div>
        <button
          class="cl-sidebar-collapse-toggle"
          type="button"
          onClick=${onToggleCollapse}
          aria-label=${collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded=${collapsed ? 'false' : 'true'}
          title=${collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            ${collapsed
              ? html`<path d="m9 6 6 6-6 6" />`
              : html`<path d="m15 6-6 6 6 6" />`}
          </svg>
        </button>
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
                const collapsedLabel = collapsed
                  ? collapsedLabelForItem(item, badge, badges)
                  : undefined;
                return html`
                  <li key=${item.path}>
                    <${Link} href=${item.path}
                      class=${`cl-sidebar-link ${active ? 'is-active' : ''}`}
                      aria-label=${collapsedLabel}
                      title=${collapsedLabel}>
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
