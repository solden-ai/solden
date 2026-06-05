# Operational Memory Object

Date: 2026-06-05

Status: active product doctrine

## Answer

The smallest durable unit of operational memory in Solden is a work item in flight.

It is not the workflow. The workflow is the process definition.

It is not the decision. A decision is one of the most important ledger entries attached to the work item, but the work item also spends time waiting, escalating, gathering evidence, and being investigated when no new decision is being made.

The product object is:

```text
Work Item in Flight
  + Execution State
  + Decision Ledger
  + Context, Dependencies, Ownership, Proof
```

Operational memory is the durable metadata that explains what is happening to the work item, why it got there, who owns it, what is blocking it, what decisions were made, what proof exists, and what should happen next.

## Why This Matches The Codebase

The current architecture already points to this model.

| Evidence | What It Means |
|---|---|
| `ap_items` is the AP work item table | The AP invoice is the first production work item in flight. |
| Generic `boxes` exists for declared workflow types | The architecture generalizes from AP items to other work-item types. |
| `ap_items.state` and generic `boxes.state` carry lifecycle position | State belongs to the work item, not to a standalone decision. |
| `owner_id`, `owner_email`, `owner_assigned_at`, `owner_source` sit on `ap_items` | Ownership is part of current execution state. |
| `pending_plan`, `waiting_condition`, `exception_code`, `exception_severity`, `confidence`, and `field_confidences` sit on or around the item | Waiting, blockers, confidence, and exception state are work-item memory. |
| `audit_events` is keyed by `box_id` and `box_type` | The timeline is attached to the work item. |
| `DecisionContext` is captured inside `audit_events.payload_json.decision_context` | Decisions already behave like contextual ledger entries, not as the root object. |
| `box_exceptions` and `box_outcomes` are first-class lifecycle records | Exceptions and outcomes are durable primitives attached to the work item. |

The code therefore supports this conclusion:

1. Work item is the atomic object.
2. Execution state is the current position of that object.
3. Decision ledger is the memory of why the object reached that position.

## Object Model

### 1. Work Item

The business object being advanced.

Examples:

1. AP invoice
2. purchase request
3. purchase order
4. vendor onboarding request
5. AR dispute
6. bank reconciliation item
7. close task

The work item is what a customer would point to and ask:

"What is going on with this?"

### 2. Execution State

Where the work item is now.

Execution state should answer:

1. What state is it in?
2. Who owns the next move?
3. What is it waiting on?
4. What exception is blocking it?
5. What system has the latest transaction state?
6. What should happen next?
7. How confident is the agent?

This is what makes Solden more than a transaction-status mirror.

### 3. Decision Ledger

Why the work item got there.

Decision ledger entries should answer:

1. Who or what made the decision?
2. What was decided?
3. Why was it decided?
4. What context was visible at decision time?
5. What evidence supported the decision?
6. What policy or rule applied?
7. What state changed because of the decision?
8. Which surface did the decision happen in: Gmail, Slack, Teams, ERP, workspace, or agent?

The decision ledger is what separates operational memory from ordinary workflow state.

An ERP can say:

```text
Invoice #123: Pending approval
```

Solden should be able to say:

```text
Invoice #123 is waiting for Sarah.
Sarah paused approval because Procurement challenged the vendor selection.
The Controller granted an exception after reviewing the PO mismatch.
The vendor expects a response by Friday.
Escalation is recommended in 24 hours.
```

The second answer is operational memory.

## Canonical Memory Record Shape

This is the conceptual product shape. It does not require a new database table by default; today most of it can be projected from `ap_items`, `boxes`, `audit_events`, `box_exceptions`, and `box_outcomes`.

```text
MemoryRecord
  id
  organization_id
  box_type
  work_item_ref
  current_state
  owner
  waiting_condition
  next_action
  dependencies
  open_exceptions
  confidence
  evidence_refs
  latest_system_state
  timeline
  decision_ledger
  outcome
```

```text
DecisionLedgerEntry
  event_id
  decision_type
  decided_by
  decided_at
  source_surface
  previous_state
  resulting_state
  rationale
  context_snapshot
  evidence_refs
  policy_version
  confidence
  external_refs
```

## Product Implications

1. Solden should not be described as only tracking approvals.
2. Solden should not be described as only automating workflows.
3. Solden should not be described as only storing transaction state.
4. The workspace should show work items in flight, with owner, waiting reason, next action, exception, and decision history.
5. Embedded surfaces should show the current record and the decision context needed to act safely.
6. The landing page visual should represent a work item carrying execution state and a decision ledger across systems.

## Engineering Implications

1. Keep `box_id` and `box_type` as the universal memory key.
2. Treat `audit_events` as the raw decision/timeline ledger.
3. Treat `DecisionContext` as a product-critical shape, not just audit metadata.
4. Prefer a read projection for `decision_ledger` before adding a new table.
5. Any new workflow type must define the work item first, then the execution-state fields, then the decision-ledger events worth preserving.
6. For NetSuite validation, prove the AP item can be reconstructed as one complete memory record inside the SuiteApp panel.

## Test Question

For any candidate workflow, ask:

If this work item is stuck for 30 days and the operator who understood it leaves the company, can Solden still explain:

1. what it is,
2. where it is,
3. who owns it,
4. why it is waiting,
5. what decisions got it here,
6. what evidence supports those decisions,
7. and what should happen next?

If yes, Solden is maintaining operational memory.
