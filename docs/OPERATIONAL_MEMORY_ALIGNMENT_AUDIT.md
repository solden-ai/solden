# Operational Memory Alignment Audit

Date: 2026-06-08. Method: five grounded code audits (every audit/memory boundary,
surface by surface, box type by box type, ingestion paths, primitives + cross-system
+ intent), each reading the actual files and citing `file:line`. Thesis under test:
Solden is the operational memory layer for the back office — per work item it captures
State, Ownership, Dependencies, Exceptions, Decisions, Rationale, Evidence, History,
Next action; every audit boundary is a memory boundary; state lives once and surfaces
render it; memory spans systems; it is a system of intent (full attribution).

## Verdict

The core is substantially aligned, not aspirational. The single audit→memory funnel,
the write-time invariant, the nine primitives, all five render targets, the `ap_item`
box, and most ingestion paths genuinely implement the thesis. The drift is at the
edges: one live attribution bug, the deepest workspace view diverging, one intake that
bypasses memory entirely, the canonical decision row dropping attribution, the
secondary box types memory-incomplete, policy versioning stubbed, and the cross-system
entity graph unbuilt. Count: **5 High, 6 Med, 6 Low.**

## The aligned spine (credit where due)

- **Single funnel:** every `append_audit_event` routes through
  `_ensure_memory_payload_for_audit_event` (`solden/core/stores/ap_store.py:2506`), so
  audit-is-memory is structural, not per-caller opt-in.
- **Write-time invariant:** `assert_memory_event_payload` enforces State/Decision/
  Rationale/Evidence/Quality on every committed memory event
  (`solden/services/memory_invariants.py:260`); evidence + quality are mandatory.
- **Tamper-evident history:** per-org hash chain (`solden/core/database.py:516-586`).
- **All five render targets render the one record:** Gmail
  (`gmail_extension.py:222`), Slack (`approval_card_builder.py:402`), Teams
  (`teams_api.py:108`), NetSuite (`netsuite_panel.py:303`), SAP
  (`sap_extension.py:444`), plus Sage/ERP-first (`erp_memory_surface.py:144`) and the
  workspace Home (`HomePage.js:74`).
- **`ap_item` is fully coherent** across all nine primitives end to end (`box_registry.py:317`).
- **Most ingestion links + writes memory:** ERP-native (`intake_adapter.py:361`),
  Outlook (`outlook_email_processor.py:170`), Gmail webhook/extension, Slack.
- **The entity-graph gap is honestly scoped, not faked** (`docs/ENTITY_GRAPH_SCOPING.md`).
- **`period_close` + `bank_reconciliation` services are read-only/gates** — they do not
  side-write box state.

## Drift ledger

### High
- **H1. A live audit observer records the actor as NULL.**
  `solden/services/state_observers.py:285-299` passes `"actor"` but the funnel reads
  `payload.get("actor_id")` (`ap_store.py:2627`). Registered at
  `invoice_workflow.py:106`, so every AP state transition writes a memory row with
  `actor_id=NULL`. Violates full attribution. Fix: rename the key to `actor_id` (move
  `details`→`metadata`).
- **H2. The canonical state-transition row drops `agent_version` and `policy_version`.**
  The atomic INSERT in `update_ap_item` (`ap_store.py:436-526`) omits `policy_version`
  entirely and `agent_version` is `None` for every non-/v1 caller; the
  coordination-engine writes (`coordination_engine.py:1015,1194,2206,3035`) pass
  neither. The decision-defining rows get NULL attribution. This is the root cause of
  the failing `test_v1_integration` agent_version test, the tip of a structural gap.
  Fix: add `policy_version` (default `CURRENT_AP_POLICY_VERSION`) + thread
  `agent_version` into the atomic INSERT and the coordination payloads.
- **H3. The workspace Record Detail page does not read the single record.**
  `solden/api/ap_item_detail.py:563-626` never calls
  `build_box_operational_memory_record`; `RecordDetailPage.js:715-749` recomputes
  Owner/Waiting/Decision/History from raw columns. The Box's deepest home view
  diverges from Home and every embedded surface. Violates "state lives once." Fix:
  attach the canonical record to `/detail` and render it.
- **H4. PEPPOL/UBL import bypasses the memory layer entirely.**
  `solden/api/peppol.py:218,236` mints an AP item via raw `create_ap_item` (a bare
  INSERT) then `update_ap_item` with no `state`, so no audit/memory/link event ever
  fires; it is not in the coverage invariant. An inbound e-invoice lands with no
  operational-memory trace. Fix: `capture_operational_memory_event` after create + add
  `peppol.py` to `memory_invariants.py`.
- **H5. Cross-system entity resolution is unbuilt.** Only vendor identity exists
  (`vendor_attribute_matcher.py`); project / cost_center / gl_account / person /
  department (5 of 6 types) are unresolvable, so "Project Alpha == Cost Center 402"
  cannot be made. Violates "memory spans systems." Fix: ship Phase 1 of
  `docs/ENTITY_GRAPH_SCOPING.md` (deterministic cost_center + gl_account from ERP master).

### Med
- **M1. The runtime memory-event row omits `agent_version`/`tool_scope`/`policy_version`.**
  `commit_runtime_memory_event`/`commit_memory_event` (`memory_events.py:543-574`)
  build a thinner payload than the sibling runtime audit row. Fix: thread attribution
  through `commit_runtime_memory_event`.
- **M2. A silent payment-state change.** `update_ap_item_metadata_merge`
  (`ap_store.py:765-805`) writes `payment_status`/`payment_completed_at`/etc. with no
  audit or memory; called on the autonomous payment poll
  (`agent_background.py:1412-1485`). Payment/Next-action moves between audited closes.
  Fix: emit an audit event on payment merges.
- **M3. `purchase_order` records no terminal Outcome.** `purchase_order_store.py:339`
  reaches CLOSED/CANCELLED but never calls `record_box_outcome`. Fix: record an outcome
  on terminal transition.
- **M4. `purchase_order` is reachable by zero memory read/export surface.** No PO export
  route in `box_export.py`; `erp_memory_surface.py:163` hardcodes `ap_item`. PO memory
  is captured but never surfaced. Fix: a generic `box/{type}/{id}` memory + export route.
- **M5. `policy_version` is a hardcoded constant.** `ap_states.py:291`
  `CURRENT_AP_POLICY_VERSION = "v1"` never reflects the org's edited rules;
  `ap_items.approval_policy_version` (`database.py:949`) is read but never written. Fix:
  resolve the live policy version at decision time and stamp `approval_policy_version`.
- **M6. The routing decision carries no policy_version.** `ap_decision.APDecision`
  (`ap_decision.py:32-44`) returns `model`/`risk_flags` but no policy version, so the
  core rationale is not tied to the rule revision that produced it. Fix: add
  `policy_version` to `APDecision` and propagate to the audit row.

### Low
- **L1. Box-less governance rows are still mis-typed `ap_item` with empty `box_id`.**
  Today's fix stops the phantom memory event, but `threshold_policy.py:64` /
  `fraud_controls.py:244` (+ siblings) pass `ap_item_id: ""`, persisted as
  `box_type="ap_item"`, `box_id=""`. Fix: pass an explicit `organization`/`vendor` box
  type + real id.
- **L2. `bank_match` records no terminal Outcome** (`bank_match_store.py:162`).
- **L3. `bank_match`/`purchase_order` summaries are memory-thin** (`box_summary.py:143`)
  and not materialized (`box_projection.py:275` is `ap_item`-only).
- **L4. The memory narrative vocabulary is AP-specific** (`operational_memory.py:111-183`
  hardcodes AP states), degrading Next-action/Rationale for PO/bank_match.
- **L5. Human-vs-agent provenance is heuristic** — `finance_agent_runtime.py:1236` sets
  `actor="human" if actor_email else "system"`, so agent/service actions can be
  mislabeled "human" on the canonical event. Fix: derive `actor` from `actor_type`.
- **L6. Org-level events synthesize an `organization` memory record**
  (`llm_gateway.py:642-655`) — mild tension with the box-scoped memory contract.

## Recommended remediation order

1. **Attribution on the canonical row (H2 + M1 + M6 + H1).** One coherent pass that
   threads `agent_version`/`policy_version`/`actor_id` through the atomic
   state-transition INSERT, the coordination-engine writes, the runtime memory row, and
   the audit observer. Also turns the failing `test_v1_integration` test green and makes
   the "system of intent" promise true on the rows that define decisions.
2. **PEPPOL into the memory layer (H4)** + add it to the coverage invariant so it cannot
   regress.
3. **Record Detail reads the one record (H3).**
4. **Real policy versioning (M5)** — needs a small policy registry behind
   `CURRENT_AP_POLICY_VERSION`.
5. **Make `purchase_order`/`bank_match` first-class (M3, M4, L2, L3, L4).**
6. **Entity graph Phase 1 (H5)** — the largest, per the scoping doc.
