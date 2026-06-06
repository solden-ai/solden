(function () {
    'use strict';

    const params = new URLSearchParams(window.location.search);
    const config = {
        recordNo: params.get('record_no') || params.get('RECORDNO') || params.get('recordNo') || '',
        companyId: params.get('company_id') || params.get('companyId') || '',
        apiBase: params.get('api_base') || 'https://api.soldenai.com',
        appBase: params.get('app_base') || 'https://workspace.soldenai.com',
        token: params.get('token') || '',
    };
    let actionInFlight = false;

    const $ = (id) => document.getElementById(id);
    const show = (id) => { const el = $(id); if (el) el.classList.remove('cl-hidden'); };
    const hide = (id) => { const el = $(id); if (el) el.classList.add('cl-hidden'); };

    function setText(id, value) {
        const el = $(id);
        if (el) el.textContent = value == null || value === '' ? '-' : String(value);
    }

    function setState(stateValue) {
        const badge = $('cl-state-badge');
        if (!badge) return;
        const normalized = String(stateValue || 'unknown').toLowerCase().replace(/[^a-z_]/g, '');
        badge.textContent = normalized.replace(/_/g, ' ');
        badge.className = 'cl-badge cl-badge-state-' + normalized;
    }

    function fmtMoney(amount, currency) {
        if (amount == null || amount === '') return '-';
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
        if (!value) return '-';
        const parsed = new Date(value);
        if (isNaN(parsed.getTime())) return String(value);
        return parsed.toISOString().slice(0, 10);
    }

    function fmtDateTime(value) {
        if (!value) return '';
        const parsed = new Date(value);
        if (isNaN(parsed.getTime())) return String(value);
        return parsed.toLocaleString();
    }

    function renderSummary(summary) {
        setText('cl-vendor', summary.vendor_name);
        setText('cl-amount', fmtMoney(summary.amount, summary.currency));
        setText('cl-invoice-number', summary.invoice_number);
        setText('cl-due-date', fmtDate(summary.due_date));
        show('cl-summary');
    }

    function displayMemoryValue(value) {
        if (!value) return '';
        if (Array.isArray(value)) {
            return value.map(displayMemoryValue).filter(Boolean).join(', ');
        }
        if (typeof value === 'object') {
            return String(
                value.summary
                || value.label
                || value.name
                || value.email
                || value.id
                || ''
            ).trim();
        }
        return String(value || '').trim();
    }

    function evidenceFallback(memory) {
        const context = (memory && memory.context_summary) || {};
        const evidence = context.evidence || {};
        const proof = (memory && memory.proof) || {};
        const direct = displayMemoryValue(evidence.memory_evidence || proof.memory_evidence || memory.evidence);
        if (direct) return direct;
        if (Array.isArray(evidence.decision_refs) && evidence.decision_refs.length) return 'Decision evidence linked';
        if (evidence.attachment_url || proof.attachment_url) return 'Attachment linked';
        if (evidence.attachment_content_hash || proof.attachment_content_hash) return 'Attachment hash verified';
        if (evidence.field_confidences || proof.field_confidences) return 'Field evidence linked';
        return '';
    }

    function renderMemory(memory, surfaceMemory) {
        if (!memory) {
            hide('cl-memory');
            return;
        }
        surfaceMemory = surfaceMemory || {};
        const owner = memory.owner || {};
        const execution = memory.execution_state || {};
        const context = memory.context_summary || {};
        const latestDecision = context.latest_decision || (Array.isArray(memory.decision_ledger) ? memory.decision_ledger[memory.decision_ledger.length - 1] : {}) || {};
        setText('cl-owner', surfaceMemory.owner || memory.owner_label || execution.owner_label || owner.email || 'Unassigned');
        setText('cl-waiting-on', memory.waiting_on || execution.waiting_on || surfaceMemory.owner);
        setText('cl-waiting-reason', surfaceMemory.why || memory.waiting_reason || execution.waiting_reason);
        setText('cl-decision', surfaceMemory.decision || latestDecision.summary || latestDecision.decision_type || 'No decision recorded');
        setText('cl-evidence', surfaceMemory.evidence || evidenceFallback(memory) || 'No evidence linked');
        setText('cl-next-step', surfaceMemory.next || memory.next_step || execution.next_action);
        setText('cl-changed', surfaceMemory.changed || context.what_changed_since_last_step || 'No change recorded');
        const auditLink = $('cl-audit-link');
        if (auditLink && surfaceMemory.full_memory_url) {
            auditLink.href = surfaceMemory.full_memory_url;
        }

        const list = $('cl-memory-narrative');
        if (list) {
            list.innerHTML = '';
            (memory.memory_narrative || []).slice(0, 4).forEach((line) => {
                const li = document.createElement('li');
                li.textContent = String(line || '');
                list.appendChild(li);
            });
        }
        show('cl-memory');
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
            const code = exc.code || exc.exception_code || exc.exception_type || 'exception';
            const detail = exc.detail || exc.message || exc.reason || exc.description || '';
            li.textContent = detail ? code + ' - ' + detail : code;
            list.appendChild(li);
        });
        show('cl-exceptions-section');
    }

    function renderTimeline(events) {
        const list = $('cl-timeline');
        if (!list) return;
        list.innerHTML = '';
        const rows = (events || []).slice().sort((a, b) => {
            const at = a && a.created_at ? new Date(a.created_at).getTime() : 0;
            const bt = b && b.created_at ? new Date(b.created_at).getTime() : 0;
            return bt - at;
        });
        if (!rows.length) {
            hide('cl-timeline-section');
            return;
        }
        rows.slice(0, 20).forEach((event) => {
            const li = document.createElement('li');
            const time = document.createElement('span');
            time.className = 'cl-time';
            time.textContent = fmtDateTime(event.created_at);
            const body = document.createElement('span');
            body.textContent = String(event.summary || event.message || event.event_type || 'event').replace(/_/g, ' ');
            li.appendChild(time);
            li.appendChild(body);
            list.appendChild(li);
        });
        show('cl-timeline-section');
    }

    function renderDeeplink(apItemId) {
        const link = $('cl-deeplink');
        if (!link || !apItemId) return;
        link.href = config.appBase.replace(/\/$/, '') + '/accounts-payable/' + encodeURIComponent(apItemId);
    }

    function setActionStatus(message, isError) {
        const el = $('cl-action-status');
        if (!el) return;
        el.textContent = message || '';
        el.style.color = isError ? 'var(--cl-error)' : 'var(--cl-ink-secondary)';
    }

    function setActionButtonsDisabled(disabled) {
        document.querySelectorAll('[data-cl-action]').forEach((button) => {
            button.disabled = disabled;
        });
    }

    function renderActions(data) {
        if (!data || !data.ap_item_id) {
            hide('cl-actions');
            return;
        }
        const state = String(data.state || '').toLowerCase();
        const terminal = ['closed', 'rejected', 'posted_to_erp'].includes(state);
        setActionButtonsDisabled(terminal || actionInFlight);
        show('cl-actions');
    }

    function renderError(message) {
        setText('cl-error-text', message || 'Could not load Solden.');
        show('cl-error');
        hide('cl-summary');
        hide('cl-memory');
        hide('cl-actions');
        hide('cl-exceptions-section');
        hide('cl-timeline-section');
    }

    function renderEmpty() {
        show('cl-empty');
        hide('cl-summary');
        hide('cl-memory');
        hide('cl-actions');
        hide('cl-exceptions-section');
        hide('cl-timeline-section');
        const badge = $('cl-state-badge');
        if (badge) {
            badge.className = 'cl-badge cl-badge-loading';
            badge.textContent = 'Not in Solden';
        }
    }

    function actionPath(action) {
        return '/extension/ap-items/by-sage-intacct-bill/'
            + encodeURIComponent(config.recordNo)
            + '/' + action
            + '?company_id=' + encodeURIComponent(config.companyId);
    }

    async function postAction(action) {
        if (actionInFlight) return;
        if (!config.recordNo || !config.companyId || !config.token) {
            setActionStatus('Missing Sage Intacct context.', true);
            return;
        }
        actionInFlight = true;
        setActionButtonsDisabled(true);
        setActionStatus('Recording action...', false);
        const reasonEl = $('cl-action-reason');
        const reason = reasonEl ? String(reasonEl.value || '').trim() : '';
        const url = config.apiBase.replace(/\/$/, '') + actionPath(action);
        try {
            const res = await fetch(url, {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Authorization': 'Bearer ' + config.token,
                    'Content-Type': 'application/json',
                },
                credentials: 'omit',
                body: JSON.stringify({
                    reason: reason || null,
                    idempotency_key: [
                        'sage-intacct-panel',
                        config.companyId,
                        config.recordNo,
                        action,
                        Date.now(),
                    ].join(':'),
                }),
            });
            if (!res.ok) {
                setActionStatus('Solden returned ' + res.status + '.', true);
                return;
            }
            setActionStatus('Action recorded.', false);
            if (reasonEl) reasonEl.value = '';
            actionInFlight = false;
            await load();
            return;
        } catch (err) {
            setActionStatus(err && err.message ? err.message : 'Could not reach Solden.', true);
        } finally {
            if (actionInFlight) {
                actionInFlight = false;
                setActionButtonsDisabled(false);
            }
        }
    }

    async function load() {
        hide('cl-error');
        hide('cl-empty');
        if (!config.recordNo || !config.companyId) {
            renderError('Missing Sage Intacct record or company context.');
            return;
        }
        if (!config.token) {
            renderError('Missing Solden panel token.');
            return;
        }
        const path = '/extension/ap-items/by-sage-intacct-bill/'
            + encodeURIComponent(config.recordNo)
            + '?company_id=' + encodeURIComponent(config.companyId);
        const url = config.apiBase.replace(/\/$/, '') + path;
        try {
            const res = await fetch(url, {
                headers: {
                    'Accept': 'application/json',
                    'Authorization': 'Bearer ' + config.token,
                },
                credentials: 'omit',
            });
            if (res.status === 404) {
                renderEmpty();
                return;
            }
            if (!res.ok) {
                renderError('Solden returned ' + res.status + '.');
                return;
            }
            const data = await res.json();
            setState(data.state);
            renderSummary(data.summary || {});
            renderMemory(data.memory, data.surface_memory || null);
            renderActions(data);
            renderExceptions(data.exceptions || []);
            renderTimeline(data.timeline || []);
            renderDeeplink(data.ap_item_id);
        } catch (err) {
            renderError(err && err.message ? err.message : 'Could not reach Solden.');
        }
    }

    const retry = $('cl-retry');
    if (retry) retry.addEventListener('click', load);
    document.querySelectorAll('[data-cl-action]').forEach((button) => {
        button.addEventListener('click', () => {
            postAction(button.getAttribute('data-cl-action'));
        });
    });
    load();
})();
