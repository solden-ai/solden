/* Solden panel — boots inside the Suitelet-served iframe.
   Reads bill id + account id + API base + auth token from <meta> tags
   in <head>, calls Solden's by-netsuite-bill endpoint, and renders
   the Box (state, timeline, exceptions) + action buttons.

   Vanilla JS, no build step. The Suitelet issues a short-lived JWT
   and embeds it as runtime config. */
(function () {
    'use strict';

    const meta = (name) => {
        const el = document.querySelector('meta[name="' + name + '"]');
        return el ? el.getAttribute('content') : '';
    };

    const config = {
        billId: meta('cl-bill-id'),
        accountId: meta('cl-account-id'),
        apiBase: meta('cl-api-base') || 'https://api.soldenai.com',
        appBase: meta('cl-app-base') || 'https://workspace.soldenai.com',
        setupState: meta('cl-setup-state') || 'configured',
        token: meta('cl-token') || '',
    };

    const $ = (id) => document.getElementById(id);
    const show = (id) => { const el = $(id); if (el) el.classList.remove('cl-hidden'); };
    const hide = (id) => { const el = $(id); if (el) el.classList.add('cl-hidden'); };

    function setState(stateValue) {
        const badge = $('cl-state-badge');
        if (!badge) return;
        const normalized = String(stateValue || '').toLowerCase().replace(/[^a-z_]/g, '');
        badge.textContent = normalized
            ? normalized.replace(/_/g, ' ')
            : 'unknown';
        badge.className = 'cl-badge cl-badge-state-' + (normalized || 'unknown');
    }

    function setText(id, value) {
        const el = $(id);
        if (el) el.textContent = value == null ? '—' : String(value);
    }

    function fmtMoney(amount, currency) {
        if (amount == null || amount === '') return '—';
        const num = Number(amount);
        if (!isFinite(num)) return String(amount);
        try {
            return new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: (currency || 'USD').toUpperCase(),
                maximumFractionDigits: 2,
            }).format(num);
        } catch (_) {
            return (currency || '') + ' ' + num.toFixed(2);
        }
    }

    function fmtDate(value) {
        if (!value) return '—';
        const d = new Date(value);
        if (isNaN(d.getTime())) return String(value);
        return d.toISOString().slice(0, 10);
    }

    function fmtDateTime(value) {
        if (!value) return '';
        const d = new Date(value);
        if (isNaN(d.getTime())) return String(value);
        return d.toLocaleString();
    }

    function renderTimeline(events) {
        const list = $('cl-timeline');
        if (!list) return;
        list.innerHTML = '';
        const sorted = (events || []).slice().sort((a, b) => {
            const at = a && a.created_at ? new Date(a.created_at).getTime() : 0;
            const bt = b && b.created_at ? new Date(b.created_at).getTime() : 0;
            return bt - at;  // newest first
        });
        if (!sorted.length) {
            hide('cl-timeline-section');
            return;
        }
        sorted.slice(0, 25).forEach((event) => {
            const li = document.createElement('li');
            const timeEl = document.createElement('span');
            timeEl.className = 'cl-time';
            timeEl.textContent = fmtDateTime(event.created_at);
            const eventEl = document.createElement('span');
            eventEl.className = 'cl-event';
            const verb = String(event.event_type || event.type || 'event').replace(/_/g, ' ');
            const summary = event.summary || event.message || '';
            eventEl.textContent = summary ? verb + ' — ' + summary : verb;
            li.appendChild(timeEl);
            li.appendChild(eventEl);
            list.appendChild(li);
        });
        show('cl-timeline-section');
    }

    function renderExceptions(exceptions) {
        const list = $('cl-exceptions');
        if (!list) return;
        list.innerHTML = '';
        if (!exceptions || !exceptions.length) {
            hide('cl-exceptions-section');
            return;
        }
        exceptions.forEach((exc) => {
            const li = document.createElement('li');
            const code = exc.code || exc.exception_code || 'exception';
            const detail = exc.detail || exc.message || exc.description || '';
            li.textContent = detail ? code + ' — ' + detail : code;
            if (String(exc.severity || '').toLowerCase() === 'warn') {
                li.className = 'cl-warn';
            }
            list.appendChild(li);
        });
        show('cl-exceptions-section');
    }

    function renderActions(state) {
        const actionable = state === 'needs_approval' || state === 'needs_info' || state === 'received' || state === 'validated';
        if (actionable) {
            show('cl-actions');
        } else {
            hide('cl-actions');
        }
    }

    function renderSummary(item) {
        const summary = item || {};
        setText('cl-vendor', summary.vendor_name);
        setText('cl-amount', fmtMoney(summary.amount, summary.currency));
        setText('cl-invoice-number', summary.invoice_number);
        setText('cl-due-date', fmtDate(summary.due_date));
        show('cl-summary');
    }

    function renderMemory(memory) {
        if (!memory) {
            hide('cl-memory');
            return;
        }
        const owner = memory.owner || {};
        setText('cl-owner', owner.email || memory.owner_label || 'Unassigned');
        setText('cl-waiting-on', memory.waiting_on || '—');
        setText('cl-waiting-reason', memory.waiting_reason || '—');
        setText('cl-next-step', memory.next_step || '—');
        show('cl-memory');
    }

    function renderDeeplink(apItemId) {
        const link = $('cl-deeplink');
        if (!link) return;
        const base = (config.appBase || 'https://workspace.soldenai.com').replace(/\/$/, '');
        link.href = base + '/accounts-payable/' + encodeURIComponent(apItemId);
    }

    function renderError(message) {
        $('cl-error-text').textContent = message || 'Something went wrong.';
        show('cl-error');
        hide('cl-summary');
        hide('cl-memory');
        hide('cl-exceptions-section');
        hide('cl-timeline-section');
        hide('cl-actions');
    }

    function renderEmpty() {
        show('cl-empty');
        hide('cl-summary');
        hide('cl-memory');
        hide('cl-exceptions-section');
        hide('cl-timeline-section');
        hide('cl-actions');
        const badge = $('cl-state-badge');
        if (badge) {
            badge.className = 'cl-badge cl-badge-loading';
            badge.textContent = 'Not in Solden';
        }
    }

    async function api(path, init) {
        const url = config.apiBase.replace(/\/$/, '') + path;
        const headers = (init && init.headers) || {};
        if (config.token) headers['Authorization'] = 'Bearer ' + config.token;
        headers['Accept'] = 'application/json';
        const res = await fetch(url, Object.assign({}, init, { headers: headers, credentials: 'omit' }));
        if (res.status === 404) {
            const err = new Error('not_found');
            err.code = 'not_found';
            throw err;
        }
        if (!res.ok) {
            let body = '';
            try { body = await res.text(); } catch (_) { /* swallow */ }
            const err = new Error('api_error_' + res.status);
            err.code = 'api_error';
            err.status = res.status;
            err.body = body;
            throw err;
        }
        return res.json();
    }

    async function load() {
        if (!config.billId) {
            renderError('Missing bill id — reload the page or contact support.');
            return;
        }
        if (config.setupState === 'missing_settings') {
            renderError('Solden settings are not configured in NetSuite.');
            return;
        }
        if (config.setupState === 'auth_error' || !config.token) {
            renderError('Solden panel authentication is not ready.');
            return;
        }
        try {
            const data = await api(
                '/extension/ap-items/by-netsuite-bill/' + encodeURIComponent(config.billId)
                    + '?account_id=' + encodeURIComponent(config.accountId)
            );
            // Expected shape from new endpoint:
            //   { ap_item_id, box_id, box_type, state, timeline, exceptions, outcome,
            //     summary: { vendor_name, amount, currency, invoice_number, due_date } }
            setState(data.state);
            renderSummary(data.summary || {});
            renderMemory(data.memory || null);
            renderExceptions(data.exceptions || []);
            renderTimeline(data.timeline || []);
            renderActions(data.state);
            renderDeeplink(data.ap_item_id);
            window.__clState = { apItemId: data.ap_item_id, state: data.state };
        } catch (err) {
            if (err.code === 'not_found') {
                renderEmpty();
                return;
            }
            // eslint-disable-next-line no-console
            console.error('[clearledgr] load failed', err);
            renderError('Could not reach Solden (' + (err.status || err.code || 'error') + ').');
        }
    }

    // Maps the panel button's `data-action` value to the path segment
    // on the backend's NetSuite-panel action endpoints. The NetSuite-
    // specific endpoints exist (vs reusing the gmail_extension routes)
    // so the dispatch carries source_channel="erp_native_netsuite" and
    // the audit chain records ui_surface="erp_native_netsuite" on the
    // resulting state_transition row — preserving the SoR claim that
    // the audit identifies *which surface* the operator approved from.
    const ACTION_PATH_SEGMENT = {
        approve: 'approve',
        reject: 'reject',
        needs_info: 'request-info',
    };

    async function dispatchAction(action) {
        if (!config.billId || !config.accountId) return;
        const segment = ACTION_PATH_SEGMENT[action];
        if (!segment) return;
        const buttons = document.querySelectorAll('#cl-actions .cl-btn');
        buttons.forEach((b) => { b.setAttribute('disabled', ''); });
        try {
            const path = '/extension/ap-items/by-netsuite-bill/'
                + encodeURIComponent(config.billId)
                + '/' + segment
                + '?account_id=' + encodeURIComponent(config.accountId);
            await api(path, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            await load();  // refresh the panel state
        } catch (err) {
            // eslint-disable-next-line no-console
            console.error('[clearledgr] action failed', action, err);
            renderError('Action failed (' + (err.status || err.code || 'error') + ').');
        } finally {
            buttons.forEach((b) => { b.removeAttribute('disabled'); });
        }
    }

    document.addEventListener('click', (e) => {
        const target = e.target.closest('[data-action]');
        if (!target) return;
        const action = target.getAttribute('data-action');
        if (action === 'retry') {
            hide('cl-error');
            load();
            return;
        }
        dispatchAction(action);
    });

    load();
})();
