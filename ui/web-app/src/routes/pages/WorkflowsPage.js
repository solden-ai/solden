/**
 * Workflows Page — the no-code builder for declarative Box types (Level 2).
 *
 * An admin defines a workflow type from data alone: states, transitions, and
 * actions. Validate against the backend, save a draft, activate a version.
 * Once active, create boxes of it and drive them through their declared
 * actions — all against /api/workspace/workflow-specs and
 * /api/workspace/workflows. Uses the shared workspace design language.
 */
import { h } from 'preact';
import { useEffect, useMemo, useState } from 'preact/hooks';
import htm from 'htm';
import { useAction } from '../route-helpers.js';
import { EmptyState, LoadingSkeleton, ErrorRetry } from '../../components/StatePrimitives.js';

const html = htm.bind(h);

const csv = (s) => String(s || '').split(',').map((x) => x.trim()).filter(Boolean);

const STATUS_TONE = {
  draft: { bg: '#F4F4F5', fg: '#52525B', bd: '#D4D4D8' },
  active: { bg: '#ECFDF5', fg: '#0A663E', bd: '#86EFAC' },
  archived: { bg: '#FEF2F2', fg: '#B91C1C', bd: '#FECACA' },
};

function statusChip(status) {
  const t = STATUS_TONE[status] || STATUS_TONE.draft;
  return html`<span class="secondary-chip" style=${`background:${t.bg};color:${t.fg};border-color:${t.bd}`}>${status}</span>`;
}

export default function WorkflowsPage({ api, orgId, toast }) {
  const [specs, setSpecs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  // Builder state.
  const [boxType, setBoxType] = useState('');
  const [urlSlug, setUrlSlug] = useState('');
  const [statesText, setStatesText] = useState('');
  const [initialState, setInitialState] = useState('');
  const [terminal, setTerminal] = useState({});
  const [transText, setTransText] = useState({});
  const [actions, setActions] = useState([{ action: '', target: '' }]);
  const [errors, setErrors] = useState([]);

  // Boxes panel.
  const [selectedType, setSelectedType] = useState('');
  const [boxes, setBoxes] = useState([]);

  const states = useMemo(() => csv(statesText), [statesText]);

  const loadSpecs = async ({ silent = false } = {}) => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await api('/api/workspace/workflow-specs', { silent });
      setSpecs(Array.isArray(data?.workflow_specs) ? data.workflow_specs : []);
    } catch (exc) {
      setSpecs([]);
      setLoadError(exc?.message || 'Could not load workflows.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void loadSpecs({ silent: true }); }, [api, orgId]);

  const buildSpec = () => {
    const transitions = {};
    for (const s of states) {
      const t = csv(transText[s]);
      if (t.length) transitions[s] = t;
    }
    const action_states = {};
    for (const { action, target } of actions) {
      if (action && target) action_states[action.trim()] = target;
    }
    return {
      box_type: boxType.trim(),
      url_slug: (urlSlug.trim() || boxType.trim().replace(/_/g, '-')),
      states,
      initial_state: initialState,
      terminal_states: states.filter((s) => terminal[s]),
      transitions,
      action_states,
      fields: [],
    };
  };

  const [validateSpec, validating] = useAction(async () => {
    const res = await api('/api/workspace/workflow-specs/validate', { method: 'POST', body: buildSpec() });
    setErrors(res?.errors || []);
    toast?.(res?.valid ? 'Spec is valid.' : 'Spec has errors.', res?.valid ? 'success' : 'error');
  });

  const [saveDraft, saving] = useAction(async () => {
    try {
      const row = await api('/api/workspace/workflow-specs', { method: 'POST', body: buildSpec() });
      setErrors([]);
      toast?.(`Saved ${row.box_type} v${row.version} (draft).`, 'success');
      await loadSpecs();
    } catch (exc) {
      toast?.(exc?.message || 'Could not save spec.', 'error');
    }
  });

  const activate = async (bt, version) => {
    try {
      await api(`/api/workspace/workflow-specs/${encodeURIComponent(bt)}/versions/${version}/activate`, { method: 'POST', body: {} });
      toast?.(`Activated ${bt} v${version}.`, 'success');
      await loadSpecs();
    } catch (exc) {
      toast?.(exc?.message || 'Could not activate.', 'error');
    }
  };

  const activeSpecFor = (bt) => specs.find((s) => s.box_type === bt && s.status === 'active');

  const viewBoxes = async (bt) => {
    setSelectedType(bt);
    try {
      const data = await api(`/api/workspace/workflows/${encodeURIComponent(bt)}`, { silent: true });
      setBoxes(Array.isArray(data?.boxes) ? data.boxes : []);
    } catch (exc) {
      setBoxes([]);
      toast?.(exc?.message || 'Could not load boxes.', 'error');
    }
  };

  const createBox = async () => {
    try {
      await api(`/api/workspace/workflows/${encodeURIComponent(selectedType)}`, { method: 'POST', body: { data: {} } });
      toast?.('Box created.', 'success');
      await viewBoxes(selectedType);
    } catch (exc) {
      toast?.(exc?.message || 'Could not create box.', 'error');
    }
  };

  const actOnBox = async (boxId, action) => {
    try {
      await api(`/api/workspace/workflows/${encodeURIComponent(selectedType)}/${encodeURIComponent(boxId)}/${encodeURIComponent(action)}`, { method: 'POST', body: { reason: '' } });
      toast?.(`${action} done.`, 'success');
      await viewBoxes(selectedType);
    } catch (exc) {
      toast?.(exc?.message || `Could not ${action}.`, 'error');
    }
  };

  if (loading) {
    return html`<div class="panel"><${LoadingSkeleton} rows=${5} label="Loading workflows" /></div>`;
  }
  if (loadError) {
    return html`<div class="panel"><${ErrorRetry} message="Couldn't load workflows." detail=${loadError} onRetry=${() => loadSpecs()} /></div>`;
  }

  const selectedActions = selectedType
    ? Object.entries(activeSpecFor(selectedType)?.spec_json?.action_states || {})
    : [];

  return html`
    <div class="secondary-banner">
      <div class="secondary-banner-copy">
        <h3>Workflows</h3>
        <p class="muted">Define custom workflow types — states, transitions, and actions — with no code. Activate one, then run boxes through it on the same runtime as AP and Procurement.</p>
      </div>
    </div>

    <div class="panel wf-builder">
      <div class="panel-head compact"><h3>New workflow type</h3></div>

      <div class="secondary-form-grid">
        <label>Type name (snake_case)
          <input value=${boxType} onInput=${(e) => setBoxType(e.target.value)} placeholder="contract_review" />
        </label>
        <label>URL slug
          <input value=${urlSlug} onInput=${(e) => setUrlSlug(e.target.value)} placeholder="contract-reviews" />
        </label>
      </div>
      <div class="secondary-form-stack" style="margin-top:14px">
        <label>States (comma-separated)
          <input class="wf-states" value=${statesText} onInput=${(e) => setStatesText(e.target.value)} placeholder="draft, in_review, approved, rejected" />
        </label>
      </div>

      ${states.length > 0 && html`
        <div style="margin-top:18px; display:grid; gap:16px;">
          <div class="secondary-form-grid">
            <label>Initial state
              <select value=${initialState} onChange=${(e) => setInitialState(e.target.value)}>
                <option value="">— pick —</option>
                ${states.map((s) => html`<option value=${s}>${s}</option>`)}
              </select>
            </label>
          </div>

          <div>
            <div class="muted" style="font-weight:500; margin-bottom:8px">Terminal states</div>
            <div class="secondary-card-tags">
              ${states.map((s) => html`
                <label key=${s} class="secondary-chip" style="cursor:pointer; gap:6px; display:inline-flex; align-items:center">
                  <input type="checkbox" checked=${!!terminal[s]} onChange=${(e) => setTerminal({ ...terminal, [s]: e.target.checked })} /> ${s}
                </label>`)}
            </div>
          </div>

          <div>
            <div class="muted" style="font-weight:500; margin-bottom:8px">Transitions</div>
            <div class="secondary-form-stack">
              ${states.map((s) => html`
                <label key=${s}>${s} →
                  <input placeholder="next states (comma-separated)" value=${transText[s] || ''} onInput=${(e) => setTransText({ ...transText, [s]: e.target.value })} />
                </label>`)}
            </div>
          </div>

          <div>
            <div class="muted" style="font-weight:500; margin-bottom:8px">Actions (button → target state)</div>
            <div class="secondary-form-stack">
              ${actions.map((a, i) => html`
                <div key=${i} class="secondary-form-grid" style="gap:8px">
                  <label>Action name
                    <input placeholder="approve" value=${a.action} onInput=${(e) => setActions(actions.map((x, j) => j === i ? { ...x, action: e.target.value } : x))} />
                  </label>
                  <label>Target state
                    <select value=${a.target} onChange=${(e) => setActions(actions.map((x, j) => j === i ? { ...x, target: e.target.value } : x))}>
                      <option value="">— pick —</option>
                      ${states.map((s) => html`<option value=${s}>${s}</option>`)}
                    </select>
                  </label>
                </div>`)}
              <div><button class="btn-ghost btn-sm" onClick=${() => setActions([...actions, { action: '', target: '' }])}>+ Add action</button></div>
            </div>
          </div>
        </div>`}

      ${errors.length > 0 && html`
        <ul class="wf-errors" style="margin:14px 0 0; padding-left:18px">
          ${errors.map((e) => html`<li key=${e} class="form-error" style="list-style:disc">${e}</li>`)}
        </ul>`}

      <div class="secondary-inline-actions" style="margin-top:18px">
        <button class="btn-secondary" disabled=${validating} onClick=${validateSpec}>${validating ? 'Validating…' : 'Validate'}</button>
        <button class="btn-primary" disabled=${saving} onClick=${saveDraft}>${saving ? 'Saving…' : 'Save draft'}</button>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head compact"><h3>Your workflow types</h3></div>
      ${specs.length === 0
        ? html`<${EmptyState} title="No workflow types yet" description="Define one above to get started." />`
        : html`
          <div class="secondary-card-list">
            ${specs.map((s) => html`
              <div key=${s.box_type + ':' + s.version} class="secondary-card">
                <div class="secondary-card-head">
                  <div class="secondary-card-copy">
                    <strong class="secondary-card-title">${s.box_type}</strong>
                    <div class="secondary-card-meta">version ${s.version}</div>
                    <div class="secondary-card-tags">${statusChip(s.status)}</div>
                  </div>
                </div>
                <div class="secondary-card-actions">
                  ${s.status === 'draft' && html`<button class="btn-primary btn-sm" onClick=${() => activate(s.box_type, s.version)}>Activate</button>`}
                  ${s.status === 'active' && html`<button class="btn-secondary btn-sm" onClick=${() => viewBoxes(s.box_type)}>View boxes</button>`}
                </div>
              </div>`)}
          </div>`}
    </div>

    ${selectedType && html`
      <div class="panel">
        <div class="panel-head compact" style="display:flex; justify-content:space-between; align-items:center">
          <h3>${selectedType} boxes</h3>
          <button class="btn-primary btn-sm" onClick=${createBox}>New box</button>
        </div>
        ${boxes.length === 0
          ? html`<${EmptyState} title="No boxes" description="Create one to start." />`
          : html`
            <div class="secondary-card-list">
              ${boxes.map((b) => html`
                <div key=${b.id} class="secondary-card">
                  <div class="secondary-card-head">
                    <div class="secondary-card-copy">
                      <strong class="secondary-card-title">${b.id}</strong>
                      <div class="secondary-card-tags"><span class="secondary-chip">${b.state}</span></div>
                    </div>
                  </div>
                  <div class="secondary-card-actions">
                    ${selectedActions.map(([action]) => html`
                      <button class="btn-secondary btn-sm" onClick=${() => actOnBox(b.id, action)}>${action}</button>`)}
                  </div>
                </div>`)}
            </div>`}
      </div>`}
  `;
}
