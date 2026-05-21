/**
 * Procurement Page — purchase-order approval workflow (BoxType #3).
 *
 * Lists POs, creates a draft, and drives the approval lifecycle
 * (submit -> approve / reject -> close / cancel) against the
 * /api/workspace/purchase-orders endpoints. Uses the shared workspace
 * design language (secondary-banner / secondary-card / btn-*).
 */
import { h } from 'preact';
import { useEffect, useMemo, useState } from 'preact/hooks';
import htm from 'htm';
import { useAction } from '../route-helpers.js';
import { formatAmount } from '../../utils/formatters.js';
import { EmptyState, LoadingSkeleton, ErrorRetry } from '../../components/StatePrimitives.js';

const html = htm.bind(h);

// Which lifecycle actions are offered for a PO in a given state.
// Each maps to a POST /purchase-orders/{id}/{action} endpoint.
const ACTIONS_BY_STATE = {
  draft: [['submit', 'Submit for approval'], ['cancel', 'Cancel']],
  pending_approval: [['approve', 'Approve'], ['reject', 'Reject'], ['cancel', 'Cancel']],
  approved: [['issue', 'Issue to ERP'], ['receive', 'Receive goods'], ['close', 'Close']],
  partially_received: [['receive', 'Receive more'], ['close', 'Close']],
  fully_received: [['close', 'Close']],
};

const STATUS_TONE = {
  draft: { bg: '#F4F4F5', fg: '#52525B', bd: '#D4D4D8' },
  pending_approval: { bg: '#FEF3C7', fg: '#92400E', bd: '#FDE68A' },
  approved: { bg: '#ECFDF5', fg: '#0A663E', bd: '#86EFAC' },
  partially_received: { bg: '#EFF6FF', fg: '#1E40AF', bd: '#BFDBFE' },
  fully_received: { bg: '#EFF6FF', fg: '#1E40AF', bd: '#BFDBFE' },
  closed: { bg: '#F4F4F5', fg: '#52525B', bd: '#D4D4D8' },
  cancelled: { bg: '#FEF2F2', fg: '#B91C1C', bd: '#FECACA' },
};

function statusChip(status) {
  const t = STATUS_TONE[status] || STATUS_TONE.draft;
  return html`<span class="secondary-chip" style=${`background:${t.bg};color:${t.fg};border-color:${t.bd}`}>
    ${String(status || '').replace(/_/g, ' ')}
  </span>`;
}

export default function ProcurementPage({ api, orgId, toast }) {
  const [pos, setPos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [search, setSearch] = useState('');
  const [vendorName, setVendorName] = useState('');
  const [amount, setAmount] = useState('');

  const load = async ({ silent = false } = {}) => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await api('/api/workspace/purchase-orders', { silent });
      setPos(Array.isArray(data?.purchase_orders) ? data.purchase_orders : []);
    } catch (exc) {
      setPos([]);
      setLoadError(exc?.message || 'Could not load purchase orders.');
      if (!silent) toast?.('Could not load purchase orders.', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load({ silent: true }); }, [api, orgId]);

  const [createPo, creating] = useAction(async () => {
    const name = String(vendorName || '').trim();
    if (!name) {
      toast?.('Vendor name is required.', 'error');
      return;
    }
    await api('/api/workspace/purchase-orders', {
      method: 'POST',
      body: { vendor_name: name, total_amount: Number(amount) || 0 },
    });
    setVendorName('');
    setAmount('');
    toast?.('Purchase order created.', 'success');
    await load();
  });

  const act = async (poId, action) => {
    try {
      await api(`/api/workspace/purchase-orders/${encodeURIComponent(poId)}/${action}`, {
        method: 'POST',
        body: { reason: '' },
      });
      toast?.(`PO ${action} done.`, 'success');
      await load();
    } catch (exc) {
      toast?.(exc?.message || `Could not ${action} the PO.`, 'error');
    }
  };

  const filtered = useMemo(() => {
    const q = String(search || '').trim().toLowerCase();
    if (!q) return pos;
    return pos.filter((p) => String(p.vendor_name || '').toLowerCase().includes(q)
      || String(p.po_number || '').toLowerCase().includes(q));
  }, [pos, search]);

  if (loading) {
    return html`<div class="panel"><${LoadingSkeleton} rows=${5} label="Loading purchase orders" /></div>`;
  }
  if (loadError) {
    return html`<div class="panel"><${ErrorRetry}
      message="Couldn't load purchase orders."
      detail=${loadError}
      onRetry=${() => load()}
    /></div>`;
  }

  return html`
    <div class="secondary-banner">
      <div class="secondary-banner-copy">
        <h3>Procurement</h3>
        <p class="muted">Purchase orders and their approval lifecycle. Create a PO, then drive it through approval, receipt, and close.</p>
      </div>
    </div>

    <div class="panel">
      <div class="secondary-form-grid po-create">
        <label>Vendor
          <input value=${vendorName} onInput=${(e) => setVendorName(e.target.value)} placeholder="e.g. Acme Supplies" />
        </label>
        <label>Amount
          <input type="number" value=${amount} onInput=${(e) => setAmount(e.target.value)} placeholder="0.00" />
        </label>
      </div>
      <div class="secondary-inline-actions" style="margin-top:14px">
        <button class="btn-primary" disabled=${creating} onClick=${createPo}>
          ${creating ? 'Creating…' : 'New PO'}
        </button>
      </div>
    </div>

    <div class="panel">
      <div class="secondary-search-row">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--ink-muted)" stroke-width="2" style="position:absolute;left:10px;top:50%;transform:translateY(-50%)"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <input placeholder="Search vendor or PO #" value=${search} onInput=${(e) => setSearch(e.target.value)} />
      </div>

      <div class="secondary-card-list" style="margin-top:14px">
        ${filtered.length === 0
          ? html`<${EmptyState} title="No purchase orders" description="Create one to start the approval workflow." />`
          : filtered.map((p) => html`
            <div key=${p.po_id} class="secondary-card">
              <div class="secondary-card-head">
                <div class="secondary-card-copy">
                  <strong class="secondary-card-title">${p.po_number || p.po_id}</strong>
                  <div class="secondary-card-meta">${p.vendor_name || 'Unknown vendor'}</div>
                  <div class="secondary-card-tags">${statusChip(p.status)}</div>
                </div>
                <div class="secondary-card-stat">
                  <strong>${formatAmount(p.total_amount, p.currency)}</strong>
                </div>
              </div>
              <div class="secondary-card-actions">
                ${(ACTIONS_BY_STATE[p.status] || []).map(([action, label]) => html`
                  <button class="btn-secondary btn-sm" onClick=${() => act(p.po_id, action)}>${label}</button>
                `)}
              </div>
            </div>
          `)}
      </div>
    </div>
  `;
}
