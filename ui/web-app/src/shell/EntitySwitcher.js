import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../utils/htm.js';
import { useEntities } from './EntityContext.js';

/**
 * Topbar entity switcher dropdown.
 *
 * This is a workspace-global scope control. It stays visible even
 * when an org has not configured legal entities yet, because the
 * current scope still matters: "All entities" is the default,
 * explicit aggregate view.
 */
export function EntitySwitcher() {
  const { entities, activeEntityId, setActiveEntityId, loading } = useEntities();
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);
  const list = Array.isArray(entities) ? entities : [];

  useEffect(() => {
    if (!open) return;
    function onDocClick(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  if (loading) {
    return html`
      <div class="cl-entity-switcher">
        <button class="cl-entity-trigger is-loading" type="button" disabled aria-busy="true">
          <span class="cl-entity-label">Entity</span>
          <span class="cl-entity-name">All entities</span>
          <span class="cl-entity-chevron" aria-hidden="true">▾</span>
        </button>
      </div>
    `;
  }

  const active = list.find((e) => String(e.id) === String(activeEntityId));
  const activeName = active ? (active.name || active.code || 'Entity') : 'All entities';

  return html`
    <div class="cl-entity-switcher" ref=${wrapperRef}>
      <button
        class=${`cl-entity-trigger ${open ? 'is-open' : ''}`}
        type="button"
        onClick=${() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded=${open}>
        <span class="cl-entity-label">Entity</span>
        <span class="cl-entity-name">${activeName}</span>
        <span class="cl-entity-chevron" aria-hidden="true">▾</span>
      </button>
      ${open
        ? html`
            <div class="cl-entity-menu" role="menu">
              <button
                class=${`cl-entity-item ${!activeEntityId ? 'is-active' : ''}`}
                type="button"
                onClick=${() => { setActiveEntityId(null); setOpen(false); }}>
                <span class="cl-entity-item-name">All entities</span>
                <span class="cl-entity-item-meta">Aggregate view</span>
              </button>
              ${list.length
                ? html`
                    <div class="cl-entity-divider" aria-hidden="true"></div>
                    ${list.map((entity) => html`
                      <button
                        key=${entity.id}
                        class=${`cl-entity-item ${String(entity.id) === String(activeEntityId) ? 'is-active' : ''}`}
                        type="button"
                        onClick=${() => { setActiveEntityId(entity.id); setOpen(false); }}>
                        <span class="cl-entity-item-name">${entity.name || entity.code || 'Entity'}</span>
                        ${entity.code && entity.name && entity.code !== entity.name
                          ? html`<span class="cl-entity-item-meta">${entity.code}</span>`
                          : null}
                      </button>
                    `)}
                  `
                : html`<div class="cl-entity-empty">No legal entities configured</div>`}
            </div>
          `
        : null}
    </div>
  `;
}
