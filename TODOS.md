# Solden Final Review TODOs

Date: 2026-06-15
Source: live code review, release docs, and current product scope. This file replaces the old deferred-work backlog; old TODOs are not pending unless they are revalidated here.

## Backlog Rules

- Add a TODO only when it maps to a current code, test, release, or evidence gap.
- Mark a TODO done only with a commit, test run, release artifact, or signed evidence path.
- Do not copy old audit findings into this file without checking current code first.
- Internal compatibility names such as historical `clearledgr:*` keys are not TODOs by themselves.

## P0 - Release Evidence

### ERP sandbox and customer signoff matrix

Evidence:
- `docs/ERP_READINESS_CHECKLISTS.md`
- `solden/services/surface_readiness.py`
- `solden/services/erp_connector_strategy.py`

Gap:
The product has ERP surface and connector work across NetSuite, SAP, Sage Intacct, QuickBooks, Xero, and Sage Accounting, but the release evidence is not uniform. Several surfaces are correctly labelled as sandbox pending, API-memory ready, or native-panel ready rather than fully production-proven.

Done when:
- Each released ERP has signed evidence for auth/connectivity, sandbox post and readback, idempotency, error mapping, retry behavior, audit and memory capture, operator recovery, and rollback.
- Any ERP without that evidence remains explicitly labelled as pending or limited in the product UI and release docs.

### Production configuration freeze

Evidence:
- `docs/GA_LAUNCH_READINESS_TRACKER.md`
- `main.py` strict-profile allowlists

Gap:
The release tracker still leaves the deployment configuration checklist open. Strict-profile routing makes missing allowlist entries a production risk, so the final env var set and feature gates need an explicit freeze.

Done when:
- The approved production env var set is documented with secrets redacted.
- Runtime profile, feature flags, webhook endpoints, ERP posting mode, and rollback defaults are signed off.
- A route-registration check is recorded for any endpoint added after the freeze.

### GA signoff packet and post-launch ownership

Evidence:
- `docs/GA_LAUNCH_READINESS_TRACKER.md`

Gap:
The current tracker still leaves GA signoff and post-launch monitoring ownership open.

Done when:
- A GA signoff packet exists with scope, evidence summary, accepted risks, rollback plan, and go/no-go decision.
- Post-launch monitoring has named owners, alert thresholds, review cadence, and escalation path.

### Current-SHA release validation run

Evidence:
- Existing backend tests under `tests/`
- Workspace app under `ui/web-app/`
- Gmail extension under `ui/gmail-extension/`

Gap:
The handoff needs a current-sha validation record, not a collection of historical test runs.

Done when:
- Backend tests, workspace frontend build/tests, Gmail extension build/tests, and targeted browser QA are run against the same commit SHA.
- Failures are either fixed or logged in this file with owner and accepted risk.

## P1 - Operational Memory Correctness

### Executable memory coverage invariant

Evidence:
- `solden/services/memory_events.py`
- `solden/services/memory_invariants.py`
- `tests/test_memory_layer_invariants.py`

Gap:
The memory layer exists, but current coverage enforcement is still too static. The standard is that every state-changing action, human decision, agent action, ERP update, chat reply, email event, approval, exception, and evidence attachment must either call `commit_memory_event`, call `capture_operational_memory_event`, or go through a runtime path that does.

Progress:
- 2026-06-15: Added `PRIMARY_MEMORY_EXECUTION_COVERAGE` and a CI test that ties key memory write paths to concrete regression tests.
- 2026-06-15: Strengthened PO, bank-match, outcome, Teams, AP direct-action, and workspace-capture tests so they assert canonical memory payloads, not just audit rows.
- 2026-06-15: Replaced the Gmail extension capture route-presence check with a direct endpoint test that posts confirmed context and asserts a canonical memory payload.
- 2026-06-15: Removed dormant vendor onboarding from primary memory coverage. It remains documented option-value; if reactivated, it needs an executable transition regression before release.

Remaining:
- Expand executable coverage beyond the first tranche to every state-changing path listed above.

Done when:
- There are executable regression tests proving memory capture for each primary write path.
- The tests cover workspace actions, Gmail, Outlook, Slack, Teams, ERP updates, approvals, exceptions, evidence attachments, and agent actions.
- A new state-changing path can fail CI if it bypasses memory capture.

### One surface memory contract

Evidence:
- `solden/services/memory_surface.py`
- `solden/api/gmail_extension.py`
- `solden/api/erp_memory.py`
- `ui/gmail-extension/src/utils/formatters.js`

Gap:
Surfaces are converging on operational memory, but the product needs one contract across workspace, Gmail, Outlook, Slack, Teams, and ERP surfaces.

Progress:
- 2026-06-15: Added a backend surface-memory projection test that locks the shared `solden_memory_surface.v1` fields and proves Slack text + adaptive-card facts use the same canonical projection.

Done when:
- A shared fixture asserts each surface can render: what the work item is, where it came from, current state, why, owner, blocker, decision, evidence, changed-since-last-step, next action, and conversation/action source.
- Surface-specific adapters are allowed, but they must consume the same canonical memory snapshot.

### Cross-surface Ask Solden convergence

Evidence:
- `solden/api/ask_solden.py`
- `ui/web-app/src/routes/pages/AskSoldenPanel.js`
- `ui/gmail-extension/src/components/SidebarApp.js`
- `solden/api/slack_invoices.py`

Gap:
Workspace Ask Solden has a stronger canonical service path than some shipped surface query handlers. The user should get the same memory-backed answer quality whether they ask from the workspace, Gmail, Slack, Teams, or an ERP panel.

Done when:
- Gmail, Slack, Teams, and workspace Q&A use the same core Ask Solden service or a documented adapter with the same citation and insufficiency contract.
- Tests prove that answers cite real memory/evidence sources and decline when context is insufficient.

### AP private outcome evals and company learning loop

Evidence:
- `solden/services/ap_learning_loop.py`
- `solden/services/agent_memory.py`
- `tests/test_ap_learning_loop.py`

Gap:
The AP wedge now has a backend private-eval snapshot over real AP items, memory events, agent traces, and Box outcomes. It also records org-level `company_ap_blocker` patterns. The remaining product requirement is to keep this loop running in release validation and customer pilots so trace-derived improvements continue to produce evidence.

Status:
Code-complete in the current branch; keep under release validation.

Progress:
- 2026-06-15: Added `APLearningLoopService.evaluate_private_outcomes()`, persisted `ap_private_outcome_eval` org snapshots through `AgentMemoryService`, and recorded recurring company-level AP blocker patterns.
- 2026-06-15: Added tests proving traceable AP outcomes produce org-level learning snapshots and that missing memory/agent/evidence signals are flagged instead of scored as healthy.
- 2026-06-15: Exposed read-only AP learning-loop metrics inside the workspace Agent outcomes report: memory coverage, evidence linkage, agent traces, outcome traceability, memory completeness, release gate, and recurring blocker.
- 2026-06-15: Scheduled AP learning-loop evals through Celery Beat and the in-process background fallback; empty orgs are skipped and pilot orgs can be scoped with `SOLDEN_AP_LEARNING_LOOP_ORG_IDS`.
- 2026-06-15: Policy proposals now cite the private-eval snapshot and recurring pattern that justified the proposed rule; accepted rules and proposal audit events carry the same citation.
- 2026-06-15: AP private-eval snapshots now emit structured agent-improvement candidates from failed real-trace cases, persist them as `agent_improvement_candidate` memory patterns, and expose the top candidate in workspace Reports.

Acceptance covered:
- Scheduled AP learning-loop evals for pilot workspaces.
- Workspace Reports show memory event coverage, evidence linkage, agent trace coverage, terminal outcome traceability, recurring company-level blockers, and the top trace-derived improvement candidate.
- Agent policy changes cite the private-eval snapshot or recurring pattern that justified the change.

### Semantic dimension and entity graph completion

Evidence:
- `solden/services/dimension_store.py`
- `solden/services/dimension_memory.py`
- `docs/ENTITY_GRAPH_SCOPING.md`

Gap:
Dimension memory exists, but the broader operational entity graph is not finished. Solden needs reliable cross-system identity for dimensions, vendors, departments, people, projects, contracts, and ERP masters.

Done when:
- ERP dimension masters are reconciled safely, including stale-master retirement without mass-deactivation on partial fetch failure.
- Aliases and conflicts have an audited confirmation flow.
- Workspace and surface chips can link users from a memory event to the relevant entity or dimension record.

## P1 - Engineering Quality

### Typed contracts for critical runtime payloads

Evidence:
- `solden/services/ap_store.py`
- `solden/services/erp_router.py`
- `solden/api/gmail_extension.py`
- `solden/services/finance_runtime_invoice_processing.py`

Gap:
Several critical AP, ERP, and surface paths still pass dict-shaped payloads across trust boundaries. That makes field drift easy and test failures less precise.

Done when:
- TypedDict, dataclass, or Pydantic models cover AP item creation/update, ERP bill posting, Gmail/Outlook intake, surface memory snapshots, and runtime agent outputs.
- Tests fail on misspelled or missing required fields.

### Canonical docs cleanup

Evidence:
- `docs/OPERATIONAL_MEMORY_ALIGNMENT_AUDIT.md`
- `docs/GA_LAUNCH_READINESS_TRACKER.md`
- `docs/ERP_READINESS_CHECKLISTS.md`
- historical docs that still use old product language

Gap:
Some historical docs and audits are useful context but no longer describe the current product state. Engineering handoff needs fewer canonical docs and clear superseded banners on stale ones.

Done when:
- Canonical handoff docs are limited to README, this TODO file, launch readiness, ERP readiness, architecture notes, and active runbooks.
- Historical audits are archived or marked superseded with a date and replacement link.
- Old user-facing product language is removed from active docs, while internal compatibility keys are documented as intentional.

### Dead code and legacy audit by import graph

Evidence:
- Full repo source tree
- Current tests and route allowlists

Gap:
The final handoff should distinguish true dead code from compatibility code, unused experiments, and test fixtures. Guessing from filenames is not enough.

Done when:
- A dead-code report is generated using import graph analysis plus targeted searches.
- Each deletion is backed by tests or an explicit compatibility decision.
- Remaining legacy modules have comments or docs explaining why they are still needed.

## P2 - Product Hardening

### Pilot scorecard instrumentation

Evidence:
- `docs/WEDGE_QUALITY_SCORECARD.md`
- AP metrics and workspace reporting code
- `solden/services/ap_learning_loop.py`

Gap:
The product promise needs a measurable pilot scorecard: not just whether work is visible, but whether Solden reduces manual chasing and keeps operational context alive.

Progress:
- 2026-06-15: Added backend AP private outcome eval metrics for memory completeness, memory-event coverage, agent-trace coverage, evidence linkage, terminal outcome traceability, and recurring company-level blockers.
- 2026-06-15: Surfaced the AP learning-loop metrics in workspace reporting without adding a sixth report type.
- 2026-06-15: Added a daily AP learning-loop eval schedule so pilot scorecards can review persisted snapshots instead of ad hoc report reads.

Done when:
- The workspace reports intake volume, blocked work, owner latency, approval completion, ERP posting success, duplicate prevention, manual touch count, and memory completeness.
- The scorecard is reviewed weekly during pilots.

### Readiness matrix honesty in UI and docs

Evidence:
- `solden/services/surface_readiness.py`
- Connections page surface copy
- ERP readiness docs

Gap:
The UI should never imply that a surface is fully released when the evidence only supports sandbox, API-memory, native-panel, or connector-ready status.

Done when:
- Every surface status shown in the workspace maps to a documented readiness level.
- The action copy says what the customer can do today, what is pending, and what evidence is missing.

## Retired From The Old TODO File

These are not pending unless revalidated in current code:

- Completed March security/reliability items.
- Completed workspace visual redesign waves.
- Old strict-profile route complaints that current tests already cover.
- Old AP memory gaps now covered by `state_observers`, AP transition memory, PO outcomes, bank-match outcomes, Peppol memory capture, and generic box memory routes.
- Broad "polish" items without a current failing screen, test, or release gap.
