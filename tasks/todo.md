# Task Log

Ongoing work log for Solden v1. Each session appends completed + open items.

---

## Completed (2026-02-26)

### Extraction Accuracy + Correction Loop
- [x] `field_confidences TEXT` column on `ap_items` — `database.py` + `ap_store.py`
- [x] Populate `field_confidences` in `approve_invoice()` after confidence gate fires
- [x] `build_worklist_item()` exposes `field_confidences` map in API response
- [x] `POST /extension/record-field-correction` endpoint — wires Gmail corrections to `CorrectionLearningService`
- [x] `GET /api/ops/extraction-quality` — added `by_field` per-field confidence breakdown
- [x] `handleFixInvoice()` in content-script.js — now calls backend for every corrected field (fire-and-forget)
- [x] Gmail card: per-field confidence collapsible (`Vendor ✓ 99%`, `Amount ⚠ 81%`)
- [x] Gmail card: PO field in header row (`· PO 12345` or `· No PO`)
- [x] Gmail card: exception root-cause one-liner banner (`⚠ PO reference required for this vendor/category`)

### GA Gaps (all 18 resolved — see docs/GA_GAPS_AND_FIXES.md)
- [x] Gap #1 — Teams security + card update
- [x] Gap #2 — SAP GL account lookup
- [x] Gap #3 — SAP status polling
- [x] Gap #5 — Workflow crash recovery (resume_workflow + retry drain loop)
- [x] Gap #6 — Correlation ID middleware
- [x] Gap #7 — Extraction correction rate metric
- [x] Gap #9 — Post-GA monitoring thresholds
- [x] Gap #10 — exception_code/severity first-class columns
- [x] Gap #11 — Teams channel_threads table
- [x] Gap #13 — Resubmission flow verified
- [x] Gap #14 — Gmail worklist auth
- [x] Gap #15 — OverrideContext structured override object
- [x] Gap #16 — Browser fallback E2E test
- [x] Gap #17 — Gmail watch expiry health check
- [x] Gap #18 — Dead-letter queue ops surface

---

## Open / Next

### Unified Workflow Engine (AR expansion)
- [ ] Design `workflow_items` table schema with `workflow_type: "ap" | "ar"` discriminator
- [ ] `WorkflowEngine` base class for shared infrastructure (state machine, audit trail, retry queue, browser fallback)
- [ ] AR state machine: `draft → sent → acknowledged → partial_payment → paid → closed`
- [ ] Migrate existing AP items to new unified schema

### Extraction Accuracy Follow-up
- [ ] Per-field confidence thresholds (vendor at 0.95, amount at 0.99, invoice_number at 0.90, due_date at 0.85)
- [ ] Correction → confidence boost feedback loop (re-evaluate gate after correction)
- [ ] Extraction quality dashboard view in the workspace shell

### E2E Staging Drill (completed 2026-02-26)
- [x] `tests/test_admin_launch_controls.py` — 2 API-level tests for rollback controls + GA readiness (verified passing)
- [x] `tests/test_e2e_rollback_controls.py` — 5 tests proving rollback kill-switches work: ERP block, per-connector block, per-channel block, browser fallback block, expired control no-op
- [x] `docs/STAGING_DRILL_RUNBOOK.md` — 10-section live staging runbook: happy path, needs_info/vendor reply, rollback controls, ERP fallback, cross-tenant, monitoring, GA sign-off
- [x] Test count: 193 → 198 passed (net +7, all pre-existing failures unchanged)

### Correction Loop Output + Extension UX (completed 2026-02-26)
- [x] Rebuild `dist/inboxsdk-layer.js` from `src/inboxsdk-layer.js` — stale dist updated
- [x] `build_worklist_item()` — now calls `CorrectionLearningService.suggest()` and includes `gl_suggestion`, `vendor_suggestion` in worklist payload
- [x] `GET /extension/needs-info-draft/{ap_item_id}` — generates pre-filled vendor reply template (to/subject/body)
- [x] Gmail card (`src/inboxsdk-layer.js`): "Suggested GL" + "Prior corrections" rows in technical details
- [x] Gmail card: "Draft vendor reply" button when `state === 'needs_info'` — opens Gmail compose with pre-filled fields
- [x] `docs/POST_GA_MONITORING.md` — thresholds, cadence, ownership, escalation, rollback triggers
