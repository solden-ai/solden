# Solden — Deferred Work

This file tracks deferred or follow-on work only.
It does not describe overall AP v1 implementation completeness or current launch posture.

The codebase already includes the core AP v1 product loop: Gmail-first intake/autopilot, Gmail-native work surfaces, Slack/Teams approvals, ERP posting and standard follow-on operations, audit trails, and ops/readiness APIs.

Use these documents for current status instead:
- `README.md`
- `docs/GA_LAUNCH_READINESS_TRACKER.md`
- `docs/ga-evidence/releases/ap-v1-2026-02-25-pilot-rc1/MANIFEST.md`

## P1 — Security & Reliability

### ~~Auth refresh circuit breaker (workspace shell)~~ ✓
- **Status:** Done (2026-03-13) — circuit breaker flags in `refreshAdminSession()`, 401 interceptor in `api()`

### ~~Claude API retry with backoff (agent runtime)~~ ✓
- **Status:** Done (2026-03-13) — exponential backoff for 429/500/502/503 + network errors, 3 retries

### ~~DB checkpoint error handling (agent runtime)~~ ✓
- **Status:** Done (2026-03-13) — try/except around both pre-exec and post-exec `update_task_run_step()` calls

### ~~Stable dev secret~~ ✓
- **Status:** Done (2026-03-13) — `require_secret()` uses `sha256(hostname:name)` instead of random

## P2 — Feature Completion

### ~~Wire NotificationObserver into workflow~~ ✓
- **Status:** Done (2026-03-13) — registered in `InvoiceWorkflowService.__init__`; DB table, `enqueue_notification()`, and retry queue already existed

## P1 — Design & UX

### ~~Workspace shell visual redesign — Wave 1~~ ✓
- **Status:** Wave 1 DONE (2026-06-11) — warm neutral system ratified from a rendered style guide (cream canvas, stone borders, umber shadows; brand navy+teal unchanged), Instrument Sans/DM Sans/Geist Mono loaded, shared vocabulary shipped (`.cl-avatar`, `.cl-pill`, `.cl-progress`, unified `.btn-*`), shell rail + demo path + low-risk pages swept. See DESIGN.md decision 2026-06-11.

### ~~Workspace shell visual redesign — Wave 2~~ ✓
- **Status:** DONE (2026-06-11) — test-first: Rules/Settings structural class assertions → data-testids, Workflows builder tests → placeholder/testid queries; then Rules support cards, Settings nav/summary cards, and the global `.panel` onto the Wave-1 card system. The full redesign TODO is closed.

### Gmail extension sidebar visual polish
- **What:** Apply same visual redesign to extension sidebar — match the workspace shell quality bar
- **Effort:** M
- **Depends on:** Workspace shell redesign (establish patterns first)

## P2 — Operational

### Operational health dashboard
- **What:** `/ops/health` page in the workspace shell — AP pipeline latency p50/p95, agent task success rate, Claude API error rate, notification delivery rate
- **Why:** No real-time visibility into system health; operators rely on logs to detect degradation
- **Effort:** M
- **Depends on:** Metrics already collected via `_ap_ops_metrics` table; needs frontend rendering

### Pre-commit hook for secret prevention
- **What:** Git pre-commit hook that blocks commits containing patterns matching API keys, tokens, or credentials
- **Why:** `.env` and token files are gitignored but accidental inline secrets in source code have no guardrail
- **Effort:** S
- **Depends on:** Nothing — standalone hook script

## P1 — ERP Follow-On Hardening

### ~~Reconciliation check for split-brain follow-on state~~ ✓
- **Status:** Done (2026-03-22) — `erp_follow_on_reconciliation.py` runs at startup via `_deferred_startup()`, scans all AP items with follow-on status, auto-repairs mismatches between source and related item metadata

### ~~Session TTL reaper for stale browser fallback sessions~~ ✓
- **Status:** Done (2026-03-22) — `erp_follow_on_session_reaper.py` sweeps stale ERP follow-on browser fallback sessions from the background loop, uses `dispatched_at` + a configurable TTL (`ERP_FOLLOW_ON_BROWSER_FALLBACK_TTL_SECONDS`, default 4 hours), marks sessions `timed_out`, and reconciles related AP metadata through the canonical fallback completion path

## P2 — ERP Follow-On Refactoring

### ~~Extract circular import into shared module~~ ✓
- **Status:** Done (2026-03-22) — `_apply_erp_follow_on_result()` and `_refresh_linked_finance_metadata()` now live in `solden/services/erp_follow_on_result.py`, and `erp_api_first.py` imports them directly without the runtime import workaround

## P3 — Operational

### Staging E2E drill automation
- **What:** Automated end-to-end test: Gmail webhook → parse → route → approve → ERP post → verify
- **Why:** Manual staging drills don't catch integration regressions; needed before broader launch claims
- **Effort:** L
- **Depends on:** Real ERP sandbox credentials, staging environment provisioned

## P2 — Memory layer follow-ons (from the Ask Solden eng review, 2026-06-10)

### Postgres FTS / pg_trgm over rationales + exception narratives
- **What:** tsvector or trigram indexes + a relevance-ranked `search_rationales` read over decision whys and exception reasons.
- **Why:** Ask Solden v1's whys channel is ILIKE constrained to memory-event rows — real fuzzy recall ("why were we cautious about X?") needs FTS.
- **Pros:** relevance-ranked memory search; the deepest moat feature of the memory layer.
- **Cons:** index migrations + query tuning (~1 day).
- **Context:** `ap_store.search_decision_reasons` is the v1 stand-in; its docstring points here.
- **Depends on:** Ask Solden shipped (proves demand).

### Dimensions surface in the workspace SPA
- **What:** a `/dimensions` route — list + per-dimension memory view over the existing `GET /api/workspace/dimensions*` APIs.
- **Why:** Ask Solden dimension citation chips render inert today (`link.kind: "none"`); the backend rollups already exist.
- **Pros:** "tell me about CC 402" becomes clickable end-to-end.
- **Cons:** a page + route + tests (~half day with CC).
- **Depends on:** nothing — APIs live since 5f708d49.

### Converge Slack + Gmail Q&A onto the ask_solden service
- **What:** route SLACK_QUERY's conversational handler and the Gmail sidebar query through `solden/services/ask_solden.py`.
- **Why:** those surfaces use a weaker context (500-item dump, no dimensions/rules/whys, no citations); one Q&A brain, three surfaces.
- **Cons:** touches two shipped surfaces (regression risk); Slack-side citation formatting needed.
- **Depends on:** ask_solden proving itself in the workspace; service signature is already surface-agnostic.

## P3 — Memory layer follow-ons

### LLM eval suite for the Ask Solden citation/insufficiency contract
- **What:** a small eval harness (seeded org, ~20 question/expected-behavior pairs) asserting answers cite real sources and decline on insufficiency. First eval pattern in the repo.
- **Why:** the runtime hard-guard catches uncited answers in production; prompt/model regressions need pre-deploy detection.
- **Cons:** new infra pattern; eval runs cost real LLM calls.
- **Depends on:** a few weeks of real Ask Solden questions to seed from.

### ERP dimension-master reconciliation (disappeared masters)
- **What:** a reconciliation pass in `dimension_sync` that retires org dimensions whose `source=erp_master` external_id no longer appears in the fetch — with per-kind guards so a partial/failed fetch never mass-deactivates.
- **Why:** upsert-only sync means masters deleted in the ERP stay `is_active=1` forever (explicit `active=false` is handled since the Ask Solden build's pre-step).
- **Cons:** the partial-fetch guard is the hard part; fetchers return `[]` on error, which must never be read as "everything was deleted".
- **Depends on:** live-sandbox validation of the dimension-master fetchers.
