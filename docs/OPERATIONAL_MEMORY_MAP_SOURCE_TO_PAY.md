# Operational Memory Map: Source-to-Pay

Date: 2026-06-05

Status: active product-discovery artifact

Related doctrine: [OPERATIONAL_MEMORY_OBJECT.md](OPERATIONAL_MEMORY_OBJECT.md)

## Purpose

This document defines the workflow Solden should learn from while validating the product with design partners.

The conclusion is precise:

Solden is not trying to automate every step of Source-to-Pay. Solden captures and maintains the operational memory that Source-to-Pay workflows lose as work moves across inbox, chat, approvals, ERP, agents, and audit.

Accounts Payable remains the first built wedge. Source-to-Pay is the larger process context that explains why AP matters and where Solden can expand after the first proof point.

## Operational-Memory Object

The smallest durable unit is a work item in flight.

The decision is not the atomic object. Decisions are ledger entries attached to the work item. That distinction matters because Source-to-Pay work often spends long periods waiting, escalating, being investigated, or collecting evidence when no new decision is being made.

For Source-to-Pay, the work item may be a requisition, approval request, purchase order, invoice, or payment. Solden's job is to keep the execution state and decision ledger attached as that item moves across systems.

```text
Work Item in Flight
  + Execution State
  + Decision Ledger
  + Context, Dependencies, Ownership, Proof
```

## Product Thesis

At every Source-to-Pay stage:

1. The ERP or procurement system knows the transaction state.
2. Humans know the context behind that state.
3. Solden should keep that context attached to the work until the work is done.

The test question for every workflow is:

If we followed one request from beginning to end, where would someone have to ask a human, "what is going on?"

That answer is where Solden lives.

## Source-to-Pay Memory Map

| Step | System Knows | Human Knows | Solden Should Remember | Measurable Outcome |
|---|---|---|---|---|
| Requisition | Request ID, requester, category, amount, cost center, draft or submitted status | Why it is urgent, whether budget is real, whether a similar purchase exists, why this vendor is being considered, who can unblock it | Business reason, source conversation, accountable owner, budget/duplicate checks, next approval, blocking question | Less time reconstructing why a request exists |
| Approval | Pending approver, approval status, timestamp, approval policy | Why it is waiting, whether the approver is unavailable, what exception was discussed, who already gave informal approval | Waiting reason, current owner, escalation path, approval evidence, exception summary, stale-age signal | Fewer manual chasers and faster approval turnaround |
| Purchase Order | PO number, vendor, amount, line items, status, change history | What changed after approval, whether the vendor was notified, whether scope/pricing changed, why the PO does not match later documents | PO context, change rationale, vendor communication, mismatch risk, owner of correction | Fewer PO/invoice mismatch loops |
| Invoice | Invoice received, vendor, amount, due date, PO match, posting status | What has already been investigated, why it is disputed, who contacted the vendor, what evidence is missing, which policy exception applies | Exception dossier, source facts, consulted systems, confidence blockers, approval state, ERP writeback state, audit trail | Faster exception resolution and fewer duplicate investigations |
| Payment | Payment scheduled, payment released or rejected, payment reference, payment date | Whether payment is being held, what the vendor expects, whether treasury changed timing, who approved release, why payment failed | Payment intent, hold reason, vendor expectation, release owner, failure reason, final proof | Fewer vendor follow-ups and clearer payment accountability |

## Transaction State vs Execution State

Transaction state tells the team what the system of record currently says.

Execution state tells the team what is actually happening.

Example:

```text
ERP:
Invoice #123
Status = Pending approval

Solden:
Invoice #123
Waiting for Sarah
Sarah requested additional documentation
Procurement supplied partial information
Controller granted a policy exception
Vendor expects a response by Friday
Escalation recommended in 24 hours
```

That second answer is the operational memory customers lose today.

## First Validation Boundary

Do not expand the product into a full Source-to-Pay suite before proof.

The first validation boundary should be:

1. Start with invoice-to-payment inside the Source-to-Pay chain.
2. Pull requisition, PO, vendor, approval, and payment context only when needed to explain the AP work item.
3. Use NetSuite as the first enterprise-grade ERP environment for end-to-end proof.
4. Prove that a finance team can open one live AP item and see the full operational state without asking another human.

This keeps the wedge honest:

1. AP is the entry point.
2. Source-to-Pay is the context.
3. Operational memory is the product.

## NetSuite Proof Path

The NetSuite validation should prove the following end-to-end flow:

1. Invoice arrives through Gmail or another intake path.
2. Solden creates or updates the AP work item.
3. Solden reads vendor, PO, subsidiary, account, and policy context from NetSuite.
4. Solden routes human judgment through Slack or Teams when required.
5. Solden writes the approved bill or state update back to NetSuite.
6. Solden renders the work memory in the NetSuite SuiteApp panel.
7. Solden records the full audit trail: source, owner, blocker, decision, proof, ERP outcome, and agent action.

The milestone is not "NetSuite integration works."

The milestone is:

A NetSuite finance team can open an invoice and immediately understand the complete operational state without asking another human.

## Design Partner Discovery Package

The design-partner ask should be narrow and operational:

We would like to spend four weeks mapping one Source-to-Pay workflow, identifying where operational memory is carried manually, and deploying Solden into a limited invoice-to-payment process to measure the impact.

### What We Need From The Design Partner

1. One named day-to-day finance or procurement operator.
2. One executive sponsor.
3. Access to a small number of real AP examples.
4. ERP sandbox or controlled production access appropriate for validation.
5. Approval-surface access: Slack, Teams, or the current approval channel.
6. One weekly review of exceptions, misses, and operational-memory gaps.

### Four-Week Discovery Structure

| Week | Goal | Output |
|---|---|---|
| 1 | Follow one request/invoice path from intake to ERP outcome | Current-state memory map with all human-held context points |
| 2 | Configure the limited AP proof path | Intake, approval, ERP context, and audit surfaces connected |
| 3 | Run real examples through Solden | Exception log, owner/waiting reasons, manual-chasing baseline |
| 4 | Measure and decide | Before/after outcome summary and expansion recommendation |

## Outcome Metrics

Design partners should not be asked to validate "operational memory" as language. They should validate outcomes.

Use these measures:

1. Approval turnaround time before vs after.
2. Number of manual follow-ups per invoice or request.
3. Exception resolution time before vs after.
4. Percentage of AP items where owner and next step are visible without asking a human.
5. Percentage of approved invoices written back to ERP without duplicate manual entry.
6. Number of repeated investigations avoided because the prior context was already on the record.

## Companion Maps To Build Next

Source-to-Pay is the first map because it contains the AP wedge and the strongest enterprise buying language.

Use the same memory-map method for:

| Workflow | System Knows | Human Knows | Solden Opportunity |
|---|---|---|---|
| Accounts Payable | Invoice, vendor, PO match, approval state, ERP posting status | Why it is blocked, what has been checked, who owns the next step, whether vendor follow-up happened | Make every open AP item explain itself |
| Accounts Receivable | Invoice sent, payment status, customer account, dunning status | Why payment is late, what customer promised, who owns follow-up, whether there is a dispute | Carry collections context across inbox, CRM, ERP, and customer conversations |
| Bank Reconciliation | Bank feed, matched/unmatched transactions, ledger entries | Why an item is unmatched, what evidence was checked, who can classify it, whether it is duplicate or timing-related | Preserve investigation state until each transaction is explained |
| Close Management | Task status, due dates, reconciliations, sign-offs | Why close tasks are late, what dependency is missing, who owns the blocker, what evidence supports sign-off | Turn close from status chasing into accountable work-in-progress memory |

## Product Guardrails

1. Do not position Solden as a generic automation builder.
2. Do not position Solden as a full procurement suite before proof.
3. Do not reduce Solden to AP approvals or invoice extraction.
4. Do not move decisions into the workspace when the embedded surface is where the decision naturally happens.
5. Do not claim broad Source-to-Pay automation until the product can prove the memory layer across real examples.

## Immediate Next Actions

1. Use this map to qualify design partners before building a 200-account target list.
2. Prioritize companies where finance/procurement work crosses inbox, chat, ERP, and human approvals.
3. Use NetSuite access to prove the end-to-end AP memory loop first.
4. Convert each design-partner conversation into a before/after memory map.
5. Raise on evidence: real workflows, measured outcomes, and design partners actively using Solden.
