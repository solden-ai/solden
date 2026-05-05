import { html } from '../utils/htm.js';
import { formatRelative } from '../utils/formatters.js';

/**
 * Agent activity ribbon.
 *
 * Live stream of the last N agent / operator actions across surfaces.
 * Modeled on Vercel deployments + Linear inbox: tone dot, verb,
 * subject, then a meta row with time, actor, and optional surface
 * tag. Click navigates to the underlying record.
 *
 * Used by:
 *   - HomePage (compact, last ~20 events, shares the page with stats
 *     and panels)
 *   - ActivityPage (taller, last ~50 events, ribbon is the page)
 *
 * The styling lives in styles/home.css under the `cl-home-activity-*`
 * prefix. The prefix is historical from when this was inlined in
 * HomePage; renaming is a follow-up, not blocking.
 *
 * Props:
 *   state          { status: 'loading' | 'ready' | 'error', error? }
 *   items          shaped rows from /api/workspace/dashboard/recent-activity
 *   live           true while SSE is delivering frames; flips the meta
 *                  label between "Live" and "Recent"
 *   navigate       wouter setter; called with `/records/{box_id}` on
 *                  row click
 *   title          optional override for the section h2 (default
 *                  "Agent activity")
 *   metaSuffix     optional override for the right-hand meta line.
 *                  Defaults to "last N" where N is items.length.
 *   emptyTitle     optional override for the empty-state title
 *   emptyDescription optional override for the empty-state body
 */
export function AgentActivityRibbon({
  state,
  items,
  live,
  navigate,
  title = 'Agent activity',
  metaSuffix,
  emptyTitle = 'Nothing to show yet.',
  emptyDescription = "Once invoices flow through, every agent and operator action shows up here in real time. What was decided, where, and when.",
}) {
  if ((!items || items.length === 0) && state?.status === 'loading') {
    return html`
      <section class="cl-home-activity">
        <header class="cl-home-activity-head">
          <h2>${title}</h2>
        </header>
        <div class="cl-home-skeleton">Loading activity…</div>
      </section>
    `;
  }

  if ((!items || items.length === 0) && state?.status === 'error') {
    return html`
      <section class="cl-home-activity">
        <header class="cl-home-activity-head">
          <h2>${title}</h2>
        </header>
        <div class="cl-home-empty">
          <div class="cl-home-empty-title cl-home-empty-error">Couldn't load activity.</div>
          <div class="cl-home-empty-sub">${state?.error || 'Try again in a moment.'}</div>
        </div>
      </section>
    `;
  }

  if (!items || items.length === 0) {
    return html`
      <section class="cl-home-activity">
        <header class="cl-home-activity-head">
          <h2>${title}</h2>
          <span class="cl-home-activity-meta">No actions yet.</span>
        </header>
        <div class="cl-home-empty">
          <div class="cl-home-empty-title">${emptyTitle}</div>
          <div class="cl-home-empty-sub">${emptyDescription}</div>
        </div>
      </section>
    `;
  }

  const tail = metaSuffix || `last ${items.length}`;

  return html`
    <section class="cl-home-activity">
      <header class="cl-home-activity-head">
        <h2>${title}</h2>
        <span class="cl-home-activity-meta">
          ${live ? html`<span class="cl-home-activity-pulse" aria-hidden="true"></span> Live` : 'Recent'}
          · ${tail}
        </span>
      </header>
      <ul class="cl-home-activity-list">
        ${items.map((row) => html`
          <li class=${`cl-home-activity-row cl-home-activity-tone-${row.tone || 'info'}`}
            key=${row.id || `${row.ts}-${row.event_type}`}
            onClick=${() => row.box_id && navigate?.(`/records/${encodeURIComponent(row.box_id)}`)}
            role=${row.box_id ? 'button' : undefined}
            tabindex=${row.box_id ? 0 : undefined}>
            <span class=${`cl-home-activity-dot cl-home-activity-dot-${row.tone || 'info'}`} aria-hidden="true"></span>
            <div class="cl-home-activity-body">
              <div class="cl-home-activity-line">
                <span class="cl-home-activity-action">${row.action}</span>
                <span class="cl-home-activity-subject">${row.subject}</span>
              </div>
              <div class="cl-home-activity-meta-row">
                <span class="cl-home-activity-time">${formatRelative(row.ts)}</span>
                <span class="cl-home-activity-sep">·</span>
                <span class="cl-home-activity-actor">${row.actor_label || 'Agent'}</span>
                ${row.surface && row.surface !== 'agent' ? html`
                  <span class="cl-home-activity-sep">·</span>
                  <span class="cl-home-activity-surface">via ${row.surface}</span>
                ` : null}
              </div>
            </div>
          </li>
        `)}
      </ul>
    </section>
  `;
}
