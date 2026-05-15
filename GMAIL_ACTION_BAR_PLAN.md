# Gmail extension — ActionBar parity with workspace

**Status:** planned, not started. Authored 2026-05-15.

## Goal

Make the Gmail extension's ThreadSidebar a fully functional approval
surface. Today it renders five data sections (invoice, 3-way match,
vendor, linked records, agent actions) but exposes no canonical action
affordances. An approver can read the box from inside Gmail; they
can't approve, reject, request info, escalate, reassign, post to ERP,
or any of the other intents the runtime supports.

This makes the Gmail extension functionally inferior to the workspace
RecordDetailPage and inconsistent with the manifesto's "render
target" claim. The thesis says decisions land where the approver
already lives. Today the Gmail render is read-only; the decision
still requires a context switch.

## Current state

### Backend (done)
- `clearledgr/api/ap_item_detail.py:86` — `_available_intents(current_state)`
  computes which intents are legal for a Box's current state.
- `clearledgr/api/ap_item_detail.py:605` — the `/api/workspace/ap-items/{id}/detail`
  payload includes `actions.available`.
- `/api/agent/intents/execute` — canonical intent dispatcher. Same path
  Slack and the workspace use. Surface-agnostic.

### Workspace (done)
- `ui/web-app/src/routes/pages/RecordDetailPage.js:300` — `ActionBar`
  component renders one button per intent in `actions.available`,
  using the `INTENT_LABELS` map (line 34) for human-readable copy.
- `ui/web-app/src/routes/pages/RecordDetailPage.js:137` — `onIntent`
  handler POSTs to `/api/agent/intents/execute` with `{intent, values}`.
- `ui/web-app/src/routes/pages/RecordDetailPage.js:376` — `ActionDialog`
  for reason-sheet inputs (reject reasons, reassign target, snooze
  duration, etc.).

### Gmail extension (partial)
- `ui/gmail-extension/src/components/ThreadSidebar.js` — 1487 lines, 5
  data sections, conditional banners, no action bar. Props expose
  one-off callbacks only:
  `onSnooze, onQuery, onUndoOverride, onSubmitFeedback, onBudgetOverride`.
- `ui/gmail-extension/src/components/ActionDialog.js` + `useActionDialog()`
  hook — exists, used by SidebarApp for snooze / budget override /
  vendor invite flows. Compatible with the workspace reason-sheet
  pattern.
- `ui/gmail-extension/src/components/SidebarApp.js` — owns the data
  fetch, queue manager, dialog state. Already calls one-off backend
  routes (`/api/ap/items/{id}/snooze`, etc.). Does not call
  `/api/agent/intents/execute`.

## Contract

ThreadSidebar gains two new props:

| Prop | Type | Meaning |
|---|---|---|
| `actions` | `string[]` | The list of intent names legal for the current Box state. Source: `detail.actions.available` from the detail endpoint. |
| `onIntent` | `(intent: string, values?: Record<string, any>) => Promise<void>` | Generic dispatcher. SidebarApp implements as `POST /api/agent/intents/execute`. |

The existing one-off callbacks (`onSnooze`, `onUndoOverride`,
`onBudgetOverride`) stay for now. They cover snooze + override windows
+ budget rails — different code paths from the canonical intent set.
Migration to a single `onIntent` for everything is a separate cleanup.

## Implementation steps

### Step 1 — confirm or extend the Gmail data fetch
The Gmail extension reads from `/api/extension/...` endpoints (need
to verify the exact route the queueManager uses). Confirm whether
`actions.available` is already in the response payload. If not, add
it to the response, mirroring the workspace detail endpoint. Pure
additive change; no breakage.

**Files:** `clearledgr/api/extension_*.py` (whichever route serves
ThreadSidebar data), `ui/gmail-extension/src/queue/queueManager.js`
(if the field needs to surface through the queue manager's normalized
item shape).

### Step 2 — extract INTENT_LABELS to a shared module
Today `INTENT_LABELS` lives only in `RecordDetailPage.js`. Move it to
`ui/shared/intent-labels.js` (new) so both surfaces import the same
human-readable copy. Single source of truth for label strings;
prevents Gmail drifting from the workspace.

**File:** new `ui/shared/intent-labels.js`. Both
`RecordDetailPage.js` and the new ThreadSidebar ActionBar import it.

### Step 3 — port ActionBar to a shared component
The ActionBar component in `RecordDetailPage.js:300` is tightly
coupled to that file (uses `actions`, `onIntent`, `item`, `busy`
props). Either:
- **3a.** Lift it to `ui/shared/ActionBar.js`. Both surfaces import.
- **3b.** Re-implement a Gmail-styled equivalent in ThreadSidebar.
  Justified if the visual treatment must differ (Gmail sidebar is
  narrow, workspace is wide).

Decision: prefer **3a** unless Gmail's narrow width forces a
different layout. The intent vocabulary, dialog flows, and busy-state
behavior should be identical.

### Step 4 — render ActionBar in ThreadSidebar
Insert as a new section immediately after the conditional banners
(`ResubmissionBanner`, `OverrideWindowBanner`, `WaitingBanner`,
`FraudFlagsBanner`) and before section 1 (`Invoice`). Visible whenever
`actions.length > 0`.

**File:** `ui/gmail-extension/src/components/ThreadSidebar.js`.

### Step 5 — wire `onIntent` in SidebarApp
SidebarApp consumes `useActionDialog()` already. New handler:

```js
async function handleIntent(intent, values) {
  // Look up which intents need a reason-sheet dialog (reject,
  // request_info, reassign, snooze) and open the dialog. Otherwise
  // dispatch directly. Identical logic to RecordDetailPage.js:137.
  const payload = { ap_item_id: item.id, intent, values };
  await api('/api/agent/intents/execute', { method: 'POST', body: JSON.stringify(payload) });
  await refreshItem();
  toast(`${INTENT_LABELS[intent] || intent} recorded.`, 'success');
}
```

Pass `handleIntent` as `onIntent` and `detailPayload.actions.available`
as `actions` into ThreadSidebar.

**File:** `ui/gmail-extension/src/components/SidebarApp.js`.

### Step 6 — tests
- ThreadSidebar.test.js — three new tests:
  - renders ActionBar when `actions.length > 0`
  - hides ActionBar when `actions` is empty (e.g. closed Boxes)
  - clicking a button calls `onIntent` with the right intent name
- SidebarApp.test.js — one new test:
  - `handleIntent` posts to `/api/agent/intents/execute` with the
    correct payload shape, then refreshes the item
- ActionDialog.test.js — existing tests cover the dialog flows.
  Reuse without changes.

## Open questions

1. **Which Gmail endpoint is the actual data source for ThreadSidebar?**
   The queueManager fetches from one of `/api/extension/*` routes.
   Need to read `ui/gmail-extension/src/queue/queueManager.js` to find
   the exact route, then confirm `actions.available` is present.

2. **Should the existing one-off callbacks (`onSnooze`,
   `onUndoOverride`, `onBudgetOverride`) migrate to `onIntent` too?**
   For consistency, yes, but it's a follow-up. Out of scope for this
   PR. The new actions ship alongside; legacy stays.

3. **Does the Gmail-side queue manager normalize the item shape in a
   way that would strip the `actions` field?** Need to check. If yes,
   plumb the field through.

4. **Width constraint.** Gmail sidebar is ~340px wide. The workspace
   ActionBar lays out horizontally with up to 6 buttons. In Gmail,
   may need a primary action + overflow menu pattern.

## Out of scope

- Migrating `onSnooze` / `onUndoOverride` / `onBudgetOverride` to
  `onIntent` (separate cleanup).
- Adding new intents not already in `INTENT_LABELS`.
- Slack/Teams parity (Slack already uses `/api/agent/intents/execute`
  via slack_invoices.py; Teams is at lower readiness — separate plan).
- Visual redesign of ThreadSidebar's existing 5 sections.

## Test plan

1. Local: load the Gmail extension against a dev workspace with at
   least one Box in `needs_approval` state. ActionBar appears with
   Approve / Reject / Request info / Send to person.
2. Click Approve → no dialog (direct dispatch) → Box transitions to
   `approved` → ActionBar updates to show `Post to ERP` /
   `Reverse approval` / etc.
3. Click Reject → ActionDialog opens with reason input → submit
   reason → Box transitions to `rejected` → audit chain records the
   reason verbatim.
4. Click Reassign → ActionDialog opens with email input → submit
   target → owner_email updates, Slack/Gmail notification fires.
5. Repeat against a `posted_to_erp` Box → ActionBar shows
   `Reverse posting` only (or empty if outside the override window).
6. Backend audit: every action above writes one event to
   `audit_events` with the correct `policy_version` and
   `actor_email`.

## Estimated effort

Half a day clean, including tests. Most of the work is plumbing
(Step 1 confirm + Step 5 wiring); the React rendering is small.
