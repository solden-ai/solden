# Design Partner Validation Playbook

This playbook is the bridge between a working AP wedge and a proven Solden
claim. It should be used with `docs/WEDGE_QUALITY_SCORECARD.md`.

## Claim Being Tested

A finance manager can run AP from inbox and decision surfaces with less context
switching, less approval chasing, and less ERP re-entry.

This is not validated by demo data, implementation coverage, or internal QA.
It is validated by live design-partner traffic clearing the claim gates exposed
at:

```text
GET /api/ops/design-partner-validation?organization_id=<org_id>
```

## Who Participates

- Customer sponsor: controller, AP manager, VP finance, or operations owner.
- Daily operator: the person handling invoices, approvals, and exceptions.
- Solden owner: the person responsible for setup, weekly review, and gap closure.
- Engineering owner: the person responsible for root-causing failed gates.

## Minimum Pilot Loop

1. Activate the customer workspace through first-owner activation.
2. Connect one inbox intake surface: Gmail or Outlook.
3. Connect one decision surface: Slack or Teams.
4. Connect the ERP destination or run in ERP-sandbox mode until writeback is safe.
5. Run real AP work through Solden for the agreed scope.
6. Review the validation gate at least weekly.
7. Fix the highest-severity failed or insufficient gate before widening scope.

## Validation Gates

The live endpoint evaluates:

- Completed AP sample size.
- AP triage correctness against operator truth.
- Critical field accuracy.
- Entity routing clear rate.
- Approvals completed without follow-up pressure.
- ERP writeback success.
- Silent failure count.
- Duplicate side-effect count.
- Touchless completion rate.

The endpoint returns one of four statuses:

- `no_live_signal`: the customer has not run enough live AP work yet.
- `collecting_evidence`: work exists, but one or more gates lacks enough evidence.
- `needs_work`: live evidence exists and at least one gate fails.
- `validated`: every gate has enough evidence and passes the threshold.

## Weekly Review

Every design-partner review should capture:

- Current validation status.
- Failed or insufficient gates.
- Top customer-observed friction.
- Top repeated blocker by count.
- Whether any operator manually chased approvals or manually re-entered ERP data.
- Whether any Solden action created a duplicate side effect or silent mismatch.
- One owner and due date for the next fix.

## Claim Discipline

Do not call the AP wedge validated until a real customer reaches `validated` on
the live gate. Before that point, the accurate claim is:

Solden has the operational-memory foundation and AP wedge implemented. The next
proof step is design-partner usage that validates the workflow under live
customer conditions.
