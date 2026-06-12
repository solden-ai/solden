import { useEffect, useState } from 'preact/hooks';
import { useLocation } from 'wouter-preact';
import { html } from '../utils/htm.js';
import { SidebarNav } from './SidebarNav.js';
import { Topbar } from './Topbar.js';
import { ErrorBoundary } from './ErrorBoundary.js';
import { AppFooter } from './AppFooter.js';
import { CommandK } from './CommandK.js';
import { MobileShellProvider, useMobileShell } from './MobileShellContext.js';

const SIDEBAR_COLLAPSED_KEY = 'solden.workspace.sidebarCollapsed';

function readSidebarCollapsedPreference() {
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
  } catch {
    return false;
  }
}

function AppShellInner({ children }) {
  const [location] = useLocation();
  const { open, close } = useMobileShell();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readSidebarCollapsedPreference);

  // Close the drawer on route change so users navigating via the
  // sidebar nav don't end up with a leftover open drawer covering
  // the page they just landed on.
  useEffect(() => {
    if (open) close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location]);

  const toggleSidebarCollapsed = () => {
    setSidebarCollapsed((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? '1' : '0');
      } catch { /* localStorage can be unavailable in private contexts */ }
      return next;
    });
  };

  return html`
    <div class=${`cl-app${sidebarCollapsed ? ' cl-app-nav-collapsed' : ''}`}>
      <aside
        class=${`cl-app-sidebar${open ? ' cl-app-sidebar-open' : ''}${sidebarCollapsed ? ' cl-app-sidebar-collapsed' : ''}`}
        data-collapsed=${sidebarCollapsed ? 'true' : 'false'}>
        <${SidebarNav}
          collapsed=${sidebarCollapsed}
          onToggleCollapse=${toggleSidebarCollapsed}
        />
      </aside>
      ${open
        ? html`<div class="cl-sidebar-backdrop" onClick=${close} aria-hidden="true"></div>`
        : null}
      <div class="cl-app-main">
        <${Topbar} />
        <main class="cl-app-content">
          <${ErrorBoundary}>${children}<//>
        </main>
        <${AppFooter} />
      </div>
      <${CommandK} />
    </div>
  `;
}

export function AppShell({ children }) {
  return html`
    <${MobileShellProvider}>
      <${AppShellInner}>${children}<//>
    <//>
  `;
}
