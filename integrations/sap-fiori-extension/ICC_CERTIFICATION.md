# SAP Integration and Certification Center (ICC) — Solden Fiori Extension

SAP's Integration and Certification Center is the gatekeeper for
SAP Store listings. Without ICC certification, the Solden Fiori
extension can be sideloaded into a customer's BTP subaccount but
cannot be discovered or installed via the SAP Store.

This document is the prep checklist + test plan + security
questionnaire framing the Solden team needs before submitting.

| Phase | Owner | Time |
|---|---|---|
| **A. Submission package** — MTA archive, screenshots, listing copy, scenario doc | Solden ops + eng | 1 week |
| **B. Functional review** — ICC reviewer drives the Fiori app through scripted scenarios on a SAP-provisioned tenant | SAP ICC | 4–8 weeks |
| **C. Security review** — Static analysis, secret-handling audit, JWKS verification, CSP review | SAP ICC | 4–8 weeks (parallel with B) |
| **D. Cloud certification (S/4HANA Cloud only)** — extension passes SAP's CES (Continuous Evaluation Service) | SAP CES | 2–4 weeks |
| **E. Customer reference** — SAP interviews a deployed customer (Booking.com) | Solden + customer | 1–2 hours of customer time |

Allow **12–24 weeks total** between submission and approval. SAP's
review process is significantly longer than NetSuite's BFN — plan
accordingly.

---

## Phase A — Submission package

### A.1 MTA archive review

Before submission, walk the MTA project once to confirm SAP-compliant
patterns:

- [x] **No hard-coded secrets in the UI5 webapp.** All tenant config
      (XSUAA issuer, JWKS URL, audience, webhook secret) lives in
      Solden's backend, looked up per-org from
      ``erp_connections.credentials``. The Fiori app receives only a
      short-lived Clearledgr JWT (5-min TTL) minted server-side after
      XSUAA verification.
- [x] **XSUAA-signed JWT validation** uses asymmetric (RS256) keys
      fetched from BTP's JWKS endpoint and cached for 1h with stale-
      fallback. No symmetric secrets shared with the customer.
- [x] **Per-tenant XSUAA config** — every customer has their own
      BTP subaccount + XSUAA service. The exchange endpoint resolves
      ``iss`` claim → matching org via
      ``erp_connections.credentials.s4hana_xsuaa_issuer``. Cross-
      tenant isolation enforced (caller cannot override).
- [x] **CSP-compliant assets** — the UI5 webapp imports only from
      ``sapui5.hana.ondemand.com`` (the SAP-hosted UI5 CDN),
      ``ui5.sap.com``, and the same-origin Approuter prefix
      ``/clearledgr-api/*``. No inline scripts, no ``eval()``, no
      ``new Function()``.
- [x] **No DOM XSS surface** — every panel field rendering uses
      UI5's standard binding (which auto-escapes). Custom HTML is
      generated only for amount formatting via ``Intl.NumberFormat``.
- [x] **MTA descriptor uses approved service plans** — `xsuaa`
      (`application` plan), `html5-apps-repo` (`app-host` +
      `app-runtime` plans), `destination` (`lite` plan). No paid-tier
      services that customers would be unexpectedly billed for.
- [x] **MTA archive signature verified** — the .mtar file produced
      by ``mbt build`` is signed; signature passes
      ``cf check-mtar-signature`` before submission.

### A.2 Screenshots

SAP requires 6–10 screenshots showing the Fiori app's UX. Take each
in a clean BTP trial subaccount with realistic test data:

1. **Standard Manage Supplier Invoices Fiori app showing the
   "Open in Solden" button on a single supplier invoice row**.
   Demonstrates the cross-navigation entry point.
2. **Solden BoxPanel rendered** — state badge "needs_approval",
   summary section (vendor, amount, currency, invoice number),
   exception list, timeline.
3. **Solden BoxPanel after Approve clicked** — state badge advanced
   to `approved`, action buttons disabled, audit timeline shows the
   transition with the operator's email + the agent's recommendation.
4. **Empty state panel** ("This Supplier Invoice was not processed
   through Solden") for a SAP-arrived invoice that bypassed Solden
   entirely. Demonstrates graceful degradation.
5. **Reject confirmation dialog** — the MessageBox warning shown
   before reject ("This will cancel the supplier invoice in
   S/4HANA. Continue?"). Demonstrates the safety guard.
6. **BTP cockpit Destination configuration** — showing
   `clearledgr-api` Destination pointing at
   `https://api.solden.com` with `HTML5.ForwardAuthToken=true`.
   Used by the ICC reviewer to validate the install instructions.
7. **Slack approval card** for an SAP-native invoice — write-
   direction evidence demonstrating the bidirectional integration.
8. **Optional: SAP Build Work Zone tile** for the standalone
   Solden Inbox view if Phase 4 ships the Launchpad-tile UX.

Save as PNG, 1920×1080 minimum (SAP's higher resolution requirement
than NetSuite). Use Solden's own BTP demo subaccount or a sanitised
Booking.com sandbox with no real PII or production financial data.

### A.3 Listing copy

SAP Store listing has these character budgets. Drafts:

#### Tagline (max 100 chars)

> Coordination layer for AP — approve, exception-triage, and audit-trace from your SAP Vendor Invoice

#### Short description (max 300 chars)

> Solden brings the coordination layer for finance teams into SAP
> S/4HANA. The Vendor Invoice panel surfaces the agent's reasoning,
> the validation gate verdict, vendor history, and one-click
> approval — every decision lands in the audit chain with the
> operator's surface captured (`ui_surface=erp_native_sap`).

#### Long description (no hard cap, but keep under 2000 chars for the listing summary box)

> Solden is the embedded coordination layer for finance teams. The
> SAP Fiori extension closes the loop between SAP S/4HANA (the
> system of record for the General Ledger) and Solden (the system
> of record for finance work-in-progress).
>
> On every Vendor Invoice, the Solden BoxPanel surfaces the Box
> state, the agent's reasoning, the validation gate verdict, the
> timeline, and one-click action buttons (Approve / Reject /
> Request info). For SAP-native invoices that arrive into S/4HANA
> via EDI, vendor portal, or AP-clerk-typed entry, Solden's
> webhook receiver consumes BTP Event Mesh CloudEvents (or ABAP
> BAdI-pushed payloads for on-premise) so the invoice becomes a
> Box, runs through validation + exception detection, and routes to
> Slack approval — without leaving SAP as the source of truth for
> the GL.
>
> Every approval landed from inside the Fiori panel records
> `ui_surface=erp_native_sap` on the audit chain, so an auditor can
> prove which surface every decision came from. For SAP-native
> invoices held by a payment block, Approve clears the block via
> `A_SupplierInvoice` PATCH; Reject cancels via the
> `SupplierInvoiceCancellation` action — keeping S/4HANA as the
> system of record while Solden coordinates the workflow.
>
> One Box. Many windows.

Pricing: **"Talk to sales for enterprise pricing"** — no specific
dollar figures unless the public pricing page has them. (CLAUDE.md
rule: no fabricated pricing on marketing surfaces.)

### A.4 Demo video

SAP Store strongly weights demo videos in discovery rank. Plan
120–180 seconds:

1. (0–15s) Open Manage Supplier Invoices Fiori app. Click into a
   specific invoice. Click "Open in Solden" cross-navigation.
2. (15–45s) BoxPanel loads, show state badge + summary + exceptions
   + timeline + agent reasoning section.
3. (45–70s) Click Approve. Confirmation. Panel updates to "approved"
   state. SAP-side payment block cleared (show the API response
   in browser dev tools).
4. (70–100s) Switch to Slack — show the corresponding approval card
   updated. Same workflow, two windows.
5. (100–130s) Show an invoice that originated in S/4HANA (SAP-
   native) — Solden auto-created the Box, routed approval to Slack
   with the right approver pinged.
6. (130–160s) Cut to Solden's audit-trail UI showing the
   `state_transition` audit row with `ui_surface=erp_native_sap`,
   actor email, agent recommendation, validation gate verdict.
7. (160–180s) Closing: "One Box, many windows. Solden on
   SAP Store."

Hosted on SAP-approved video CDN: YouTube, Vimeo, or SAP's own
content network. Submit URL with the listing.

---

## Phase B — Functional review (test scenarios)

SAP ICC's reviewer drives the Fiori extension through these
scenarios in a BTP subaccount Solden provisions and grants reviewer
access to. Each scenario should pass without manual intervention.

### B.1 Read direction (BoxPanel)

| # | Scenario | Expected | Pass |
|---|---|---|---|
| B1 | Open a Supplier Invoice **created via Solden's email-arrival flow** (i.e., posted to S/4HANA by Solden). Open Solden via cross-nav. | Panel loads in <3s. State badge shows current Solden state. Vendor + amount + currency + invoice number match SAP's fields. Timeline shows >=1 audit event. Action buttons hidden (post-approval state). | ☐ |
| B2 | Open a Supplier Invoice that was **NOT processed through Solden** (a manually-entered invoice from before installation). | Panel renders the empty state: *"This Supplier Invoice was not processed through Solden."* No errors in the browser console. No 500 in the Solden API logs. | ☐ |
| B3 | Open a Supplier Invoice where the underlying AP item is at `needs_approval` (SAP payment block was set). | Action buttons visible: Approve / Reject. | ☐ |
| B4 | Click **Approve**. | Buttons disabled during dispatch. State badge updates to `approved` within 5s. Solden audit log records `state_transition` with `ui_surface=erp_native_sap`. SAP payment block cleared via `A_SupplierInvoice` PATCH. | ☐ |
| B5 | Click **Reject**. Confirm in the warning dialog. | State badge → `rejected`. Audit row records the reason + `ui_surface=erp_native_sap`. Invoice cancelled via `SupplierInvoiceCancellation` action; falls back to PATCH `ReverseDocument=True` on accounts that don't expose the action. | ☐ |
| B6 | Toggle to **dark mode** in BTP Work Zone. | Panel respects SAP Horizon dark theme tokens. State badge contrast meets WCAG AA. | ☐ |
| B7 | Toggle to **English (en-US)**, then **Deutsch (de-DE)**, then **Português (pt-BR)** — all locales in `i18n.properties`. | All translatable strings render in the selected language. Currency formatting uses the locale's conventions (e.g., `€ 12.500,00` in pt-BR vs `EUR 12,500.00` in en-US). | ☐ |
| B8 | Wait for the Clearledgr JWT to expire (5-minute TTL). Click Approve. | Panel surfaces the auth error gracefully. Refreshing the iframe re-runs `_bootstrapSession` and mints a new JWT. | ☐ |
| B9 | Open the panel directly via the Approuter URL with composite key in the query string (deep-link entry). | Same render as via cross-nav. The Launchpad-tile UX (Phase 4) follows this same direct-load path. | ☐ |

### B.2 Write direction (webhook)

| # | Scenario | Expected | Pass |
|---|---|---|---|
| W1 | **Post a new Supplier Invoice** in S/4HANA. (S/4HANA Cloud: BTP Event Mesh fires `sap.s4.beh.supplierinvoice.v1.SupplierInvoice.Posted`. On-premise: BAdI fires the equivalent shape.) | Solden receives webhook with HMAC signature. New AP item created in `ap_items` with `state=posted_to_erp` (no payment block) or `needs_approval` (payment block set). Audit row carries `source=erp_native_sap`. | ☐ |
| W2 | **Set a payment block** on an existing invoice in S/4HANA. | Solden receives `…Blocked` event. AP item state → `needs_approval`. Slack approval card posted with the per-amount approver pinged. | ☐ |
| W3 | **Clear payment by posting a Vendor Payment** in S/4HANA. | Solden receives `…Paid` event. AP item state → `paid` / `closed` per the Box state machine. | ☐ |
| W4 | **Cancel an invoice** in S/4HANA (Set ReverseDocument=True). | Solden receives `…Cancelled` event. AP item state → `closed` with rejection reason. | ☐ |
| W5 | Trigger webhook when Solden's API is **unreachable** (simulate 502). | BTP Event Mesh retries per its policy; ABAP BAdI logs + queues for retry. Customer's S/4HANA save still completes — webhook failures must not roll back. | ☐ |

### B.3 BTP / install scenarios

| # | Scenario | Expected | Pass |
|---|---|---|---|
| C1 | Deploy the MTA to a **fresh BTP trial subaccount**. Open the Approuter URL. | BTP login → BoxPanel renders in <5s after auth. Phase 1-3 deploy works without any backend config beyond the Destination. | ☐ |
| C2 | Deploy to **a customer subaccount with their corporate IDP federated** via SAP IAS (Identity Authentication Service). | Login goes through customer's IDP. JWT carries customer's user identity (email + groups). Solden resolves the Clearledgr user via email match. | ☐ |
| C3 | Rotate the per-tenant `webhook_secret` in `erp_connections.credentials` AND on the BTP Event Mesh subscription side simultaneously. | Subsequent events still validate. Previous-secret-signed events are rejected with a clear error. | ☐ |
| C4 | Assign a user to **only the "Reader" role collection** (not "Approver"). | Panel loads. Approve / Reject buttons are hidden or disabled. (Phase 4 — role-based UX gate; Phase 1-3 may show buttons that 403 server-side.) | ☐ |

---

## Phase C — Security review

SAP ICC reviewers run static analysis tools (Checkmarx,
SonarQube/SAP equivalent) against the MTA archive + interview the
team on operational security. Pre-fill the answers below.

### C.1 Authentication + authorization

| Question | Solden's answer |
|---|---|
| How is the BTP user authenticated to the Fiori app? | Via SAP Approuter using XSUAA's standard OAuth 2.0 / OIDC flow against the BTP subaccount's configured IDP (BTP IAS by default; customer's corporate IDP via IAS federation). The Fiori app sees the user's identity via `/user-api/attributes` provided by Approuter; the raw XSUAA JWT is forwarded to the backend `Authorization` header. |
| How is the user authenticated to Solden's API? | The Fiori app POSTs the XSUAA JWT to `/extension/sap/exchange`. Solden verifies the JWT against the per-tenant XSUAA JWKS (asymmetric RS256), validates the `iss`/`aud`/`exp` claims, looks up the matching Clearledgr user via the `email` claim, and mints a 5-minute Clearledgr JWT. The Fiori app caches that token in memory + uses it as Bearer for action endpoints. |
| What's the per-tenant cross-tenant guard? | The exchange endpoint resolves the `iss` claim → matching org via `erp_connections.credentials.s4hana_xsuaa_issuer`. Once resolved, the org_id is pinned for the duration of the request — the caller cannot override. A leaked Clearledgr token is bound to the org it was minted for; cross-org access via JWT is impossible. |
| What happens if the XSUAA secret/JWKS rotates? | Solden's JWKS cache (1h + stale-fallback) auto-refreshes on a kid miss. The exchange endpoint verifies against the freshly-fetched keys. Customers don't notify Solden on key rotation; the system handles it. |

### C.2 Data handling

| Question | Solden's answer |
|---|---|
| What customer data leaves the SAP tenant? | The webhook payload contains the supplier invoice's structured fields (supplier, amount, currency, invoice number, posting date, due date, payment block status, fiscal year, company code). No attachments, no narrative notes, no PII beyond what's already on the invoice. |
| Is data encrypted in transit? | **Yes.** All API calls use TLS 1.2+. BTP Event Mesh enforces TLS. Solden's API enforces HSTS. |
| Is data encrypted at rest? | **Yes** on Solden's side: bank details are Fernet-encrypted before persistence; the per-tenant `webhook_secret` is encrypted via `_encrypt_secret`. SAP-side: BTP HTML5 Apps Repo + customer's S/4HANA standard at-rest encryption applies. |
| Does the Fiori extension store data outside SAP? | **No** records are written outside SAP by the Fiori extension itself. Solden's coordination layer stores the AP item Box record + audit chain on Solden's infrastructure. |
| GDPR? | Solden honours data-subject delete + export requests on the AP item layer. Vendor identities embedded in `vendor_intelligence` can be redacted via the platform admin tools. Solden's DPA covers BTP-deployed extensions explicitly. |
| Multi-region? | Solden's data residency follows the customer's contracted region. EU customers run on EU-hosted Solden infrastructure to meet GDPR data-localisation. |

### C.3 Operational

| Question | Solden's answer |
|---|---|
| What's the failure mode if Solden's API is down? | The BoxPanel renders the error state ("Could not load Solden Box"). The Vendor Invoice is fully usable in S/4HANA — Solden's read panel is purely additive. Webhook delivery is queued by BTP Event Mesh's standard retry policy on the customer side. |
| Audit chain shape? | Every state transition produces an immutable `audit_events` row capturing: actor (user / agent), source channel (slack / teams / gmail / **erp_native_sap** for Fiori panel decisions), decision context (validation gate verdict, agent recommendation, vendor profile snapshot), timestamp, correlation id. Append-only enforced by DB trigger. |
| Rate limits / throttling? | Solden's API enforces per-org rate limits (1000 req/min default, configurable). Bursts above that return 429 with `Retry-After`. The Fiori panel's caching (5-min Clearledgr JWT TTL + 30s Box-data refresh) keeps it well under the limit in normal use. |

### C.4 Incident response + SLA

| Question | Solden's answer |
|---|---|
| Disclosure timeline? | Solden notifies affected customers within 24 hours of confirming an incident affecting their tenant, per Solden's standard MSA. |
| Security mailbox? | `security@soldenai.com` — monitored 24/7 by the Solden security oncall. |
| Pentest cadence? | Annual third-party pentest; report available under NDA. |
| Public SLA? | Solden publishes uptime + latency SLA at <https://soldenai.com/sla>. The Fiori extension SLA inherits from the underlying Solden API SLA. |

---

## Phase D — Cloud certification (S/4HANA Cloud only)

For listings on S/4HANA **Cloud** (not on-premise), SAP additionally
runs the extension through CES (Continuous Evaluation Service):

- Static analysis on every release.
- Quarterly compatibility checks against new S/4HANA Cloud versions.
- Automated regression tests on the `i18n` strings, the OData
  consumption (the `A_SupplierInvoice` calls Solden makes for
  payment-block management), and the cross-nav intent shape.

CES findings come as patch tickets on Solden's SAP partner portal.
Solden's eng team is on the hook to address within 30 days for
critical, 90 days for major, 180 days for minor.

---

## Phase E — Customer reference

SAP interviews one deployed customer for 30–60 minutes. The
reviewer asks the customer:

- How long has the Fiori extension been in production?
- Deployment scope (single subaccount, multi-tenant, on-premise vs
  cloud, OneWorld-equivalent multi-company)?
- How many supplier invoices/month flow through the extension?
- Has the extension caused any S/4HANA-side performance issues?
- How was Solden's support during install + day-to-day?
- Are you a public reference customer SAP can list?

Booking.com is the launch design partner per the README. Brief them
1 week before the call:
- Send the question list.
- Offer a dry-run with Solden's CSM.
- Confirm whether they're willing to be listed publicly.

---

## After approval

1. SAP Store listing is live → marketing announces it on
   soldenai.com + LinkedIn + the customer newsletter.
2. Update Solden's marketing site with the "Available on SAP Store"
   badge.
3. Move the Phase 4 follow-ups (Manifest Extension on standard
   Display Supplier Invoice app, OneWorld-equivalent multi-company
   subaccount UX) into the next milestone.
