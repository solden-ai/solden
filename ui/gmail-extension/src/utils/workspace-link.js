/**
 * Hub deep-links — the Gmail extension is the contextual companion;
 * the workspace SPA at WORKSPACE_URL is the system of record.
 * "Open in Console" buttons across the extension funnel through here
 * so we have one place to swap the host if workspace.soldenai.com
 * ever moves.
 */

export const WORKSPACE_URL = (() => {
  const fromConfig =
    (typeof self !== 'undefined' && self.SOLDEN_CONFIG?.WORKSPACE_URL) ||
    (typeof globalThis !== 'undefined' && globalThis.SOLDEN_CONFIG?.WORKSPACE_URL);
  return String(fromConfig || 'https://workspace.soldenai.com').replace(/\/+$/, '');
})();

export function workspaceItemUrl(itemId) {
  const id = String(itemId || '').trim();
  if (!id) return WORKSPACE_URL;
  return `${WORKSPACE_URL}/records/${encodeURIComponent(id)}`;
}

export function workspaceVendorUrl(vendorName) {
  const name = String(vendorName || '').trim();
  if (!name) return `${WORKSPACE_URL}/vendors`;
  return `${WORKSPACE_URL}/vendors/${encodeURIComponent(name)}`;
}

export function workspaceRecordsUrl() {
  return `${WORKSPACE_URL}/records`;
}
