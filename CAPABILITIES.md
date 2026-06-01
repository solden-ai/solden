# Solden — Product Capabilities

Last verified against codebase: 2026-06-01

This document describes the current shipped product surface. The repo contains post-AP expansion code for purchase orders, bank match, and generic workflow specs; those surfaces are feature-gated off by default and are not listed here as live product.

---

## What Solden Is

Solden is operational memory for finance teams: one durable work record for each AP item, kept current across Gmail, Slack, ERP, and the workspace recovery surface. The system observes invoice context, validates it deterministically, advances safe work, and escalates exceptions with the owner, next step, context, and proof intact.

The first production skill runs accounts payable from Gmail: triage invoices, route approvals, validate against ERP, and write approved invoices back without manual approval chasing or duplicate data entry.

**Rules decide, model describes:**
- A deterministic validation layer handles PO matching, duplicate detection, policy checks, routing, and ERP write eligibility
- The model classifies, extracts, summarizes, and drafts operator-facing explanations
- Autonomy scoring determines when Solden can advance work and when it must defer to a human
- Every state change and external action is tied back to the AP work record and audit trail
- Corrections feed back into vendor context and extraction quality without letting the model decide financial writes

**Surfaces:**
- Gmail (operator surface — where finance works)
- Slack (approval surface — where approvers act)
- ERP (system of record — where invoices post)
- Workspace console (setup, exception recovery, audit, and admin surface)
- Teams, purchase orders, bank match, and the workflow builder are code-backed expansion surfaces, gated off by default

---

## AP Invoice Processing

### Invoice Intake
- Invoices detected from Gmail inbox automatically (poll or push mode)
- Email body and PDF attachment extraction via Claude multimodal LLM
- Fields extracted: vendor name, amount, currency, invoice number, invoice date, due date, PO number, line items
- Per-field confidence scores
- Multi-mailbox support (multiple Gmail accounts per organization)
- Gmail labels auto-applied: Invoices, Needs Approval, Approved, Posted, Exceptions, Rejected

### Decision Engine
- Deterministic rules evaluate each invoice with full vendor context
- Outcomes: approve path, needs_info, escalate, reject, or wait
- Each outcome includes reasoning summary and risk flags
- Confidence-gated routing: below threshold routes to human
- Vendor profile context: payment history, reliability score, past corrections, anomaly flags
- LLM unavailability degrades extraction/explanation, not the financial decision boundary

### Validation
- Deterministic validation gate (PO matching, budget checks, field completeness)
- Duplicate detection (vendor + amount + date matching)
- Amount anomaly detection (configurable standard deviation threshold)
- Three-way matching (invoice vs PO vs receipt)
- Policy compliance checks (approval thresholds, required fields, attachment requirements)

### AP State Machine
10 states with enforced transitions:
```
received → validated → needs_approval → approved → ready_to_post → posted_to_erp → closed
                     → needs_info (loops back to validated)
                     → rejected (terminal)
                     → failed_post (retryable → ready_to_post)
```
State transitions are atomic with audit events. Invalid transitions are blocked at the database level via triggers.

### GL Coding
- Auto-codes GL based on vendor history and past corrections
- Learns from every correction (correction_learning service)
- Per-vendor GL preferences stored in vendor profiles
- Custom GL mapping rules per organization
- Suggestions endpoint for real-time GL code recommendations

---

## Approval Routing

### Slack Integration
- Full approval cards with extracted invoice details
- Approve, Reject, Request Info buttons directly in Slack
- Approval reminders (automated nudges for stale approvals)
- Configurable approval channel per organization
- Request signature verification for webhook security
- OAuth installation flow for workspace-level bot

### Microsoft Teams Integration
- Built as a post-launch surface
- Gated off by default through `FEATURE_TEAMS_ENABLED`

### Approval Chains
- Hierarchical multi-step approval workflows
- Per-step approver lists with any/all approval types
- Chain status tracking (pending, approved, rejected per step)
- Escalation on timeout (configurable SLA)

### Approval Policies
- Amount-based thresholds (e.g., >$5,000 requires VP approval)
- Vendor-based rules (e.g., new vendors always require review)
- Policy versioning with full audit trail
- Override support with justification logging (budget, confidence, PO exception)

---

## ERP Integrations

Four ERPs fully integrated with posting, vendor management, and GL discovery:

### QuickBooks Online
- OAuth 2.0 authentication with token refresh
- Post vendor bills with line items
- Vendor lookup by name or email
- Vendor creation
- Journal entry posting
- Token auto-refresh on 401

### Xero
- OAuth 2.0 with tenant ID
- Post bills as ACCPAY type
- Line items with tax type support
- Vendor (contact) lookup and creation
- Account code mapping
- Token auto-refresh on 401

### NetSuite
- OAuth 1.0a Token-Based Authentication
- Vendor bill posting with expense line items
- Async posting with polling (202 response handling)
- Vendor lookup via SuiteQL
- Vendor creation with payment terms

### SAP S/4HANA (Service Layer)
- Session-based authentication
- A/P Invoice posting (PurchaseInvoices endpoint)
- Pre-flight validation before posting
- Company code support
- Business partner (vendor) search via OData
- GL account discovery
- Open invoice lookup
- OData filter injection prevention
- Dry-run mode for testing

### Shared ERP Capabilities
- Automatic ERP type detection and routing per organization
- Retry on recoverable failures (timeout, rate limit, transient errors)
- Non-recoverable failure detection (validation errors, duplicates, permission issues)
- All credentials Fernet-encrypted at rest
- Idempotent posting (prevents double-posts)

---

## Multi-Currency

- Currency field on every AP item (default USD)
- Supported in Trial, Pro, and Enterprise tiers
- Currency preserved through extraction, approval, and ERP posting
- Per-invoice currency (not per-organization)

---

## Vendor Intelligence

- Vendor profiles built automatically from invoice history
- Fields tracked: aliases, sender domains, typical GL code, PO requirements, contract amount, payment terms
- Invoice count, average amount, amount standard deviation
- Anomaly flags (unusual amount, frequency change, bank detail changes)
- Approval override rate tracking
- Vendor compliance event logging
- Vendor directory with search (exposed in Gmail extension and API)
- Bulk vendor profile lookup for batch operations

---

## Agent Runtime

### Planning Engine
- Deterministic planning loop with durable execution
- Skills registry (register skills, dispatch by task type)
- Max 10 steps per task, 600-second timeout (configurable)
- Checkpointing before and after each step (crash-resumable)
- Human-in-the-loop pause (awaiting_human status)
- Idempotency support (same key = same result)
- Model: claude-sonnet-4-6 (configurable via AGENT_RUNTIME_MODEL)

### Finance Skills
- **AP Skill** — 5 tools: enrich_with_context (now includes cross-invoice analysis), run_validation_gate, get_ap_decision, execute_routing, request_vendor_info (creates Gmail draft for missing info)
- **Compound Skill** — Cross-skill execution wrapper for AP tools + vendor compliance context under deterministic policy gates.
- **Reconciliation Skill** — post-AP expansion code; not part of the current shipped surface.
- **Vendor Compliance Skill** — vendor compliance checks (exposed as planning tool via CompoundSkill adapter)
- **Workflow Health Skill** — workflow health monitoring

### Cross-Invoice Memory
- Duplicate detection results fed into the AP planning prompt
- Anomaly warnings (amount deviation, frequency spikes) visible to Claude during decision-making
- Vendor stats (invoice count, average amount, current vs average) included in enrichment
- Solden surfaces signals such as "duplicate risk: score 85%" and deterministic policy decides whether to escalate

### Vendor Outreach
- Agent creates Gmail draft requesting missing information from vendors (PO number, amount clarification, due date)
- Draft is NOT auto-sent — operator reviews and sends from Gmail
- Triggered when AP decision returns "needs_info" with a specific question
- Integrated into the planning loop as a tool Claude can call before routing

### Finance Agent Runtime
- Intent-based dispatch (preview before execute)
- Policy prechecks before every action
- Audit trail per action
- Autonomy scoring and shadow decisions
- Per-organization autonomy threshold overrides via org settings
- Background agent tasks and retry jobs
- Agent anomaly detection and performance monitoring

### Autonomy Levels
- **Level 1 (manual)**: Agent extracts and enriches, human does everything else
- **Level 2 (assisted)**: Agent routes low-risk invoices for approval, human approves
- **Level 3 (directed)**: Rules decide approve/escalate/reject, human confirms when required
- **Level 4 (autonomous with guardrails)**: Solden advances trusted, policy-cleared work; humans review exceptions
- Autonomy earned per-vendor based on drift scoring, shadow decision accuracy, and post-verification rate
- Thresholds configurable per organization via `settings_json.autonomy_thresholds`

### ERP Posting Strategy
- API-first: tries native ERP API (QuickBooks, Xero, NetSuite, SAP)
- Browser fallback: if API fails, dispatches Playwright-based browser agent to post via ERP UI
- Reconciliation on completion: browser results feed back into AP state machine

### Browser Agent
- Playwright-based browser automation sessions
- Command execution with preview
- Predefined macros
- Policy-gated actions (requires_confirmation for sensitive operations)
- Full action event audit trail

---

## Gmail Extension

### Sidebar Capabilities
- Invoice triage and classification
- Real-time extraction with field display
- One-click approval routing
- Evidence checklist (email linked, attachment present, approval status, ERP connected)
- Open in pipeline, open email, open vendor record, reject
- Vendor and GL code suggestions
- Field correction recording (feeds learning system)
- Multiple mailbox support

### Gmail Autopilot
- Background email processing (poll or push mode)
- Configurable poll concurrency and seed hours
- Gmail push notification support (Pub/Sub)
- Auto-labeling of processed emails
- Label management (Solden parent label with sub-labels)

### Gmail Authentication
- Google OAuth flow (extension uses google-identity endpoint)
- Durable auth code exchange cache
- 7-day session token TTL

---

## Workspace Console (Admin)

### Pipeline View
- All AP items with status, amount, vendor, dates, approval state
- Filter by state, vendor, date range
- Batch operations (bulk field review resolution, up to 50 items)

### Views
- Pipeline (main work queue)
- Review (items needing attention)
- Upcoming (overdue blockers, approval waits, vendor replies)
- Home (quick access hub)

### Integrations Management
- Connect/disconnect Gmail mailboxes
- Connect/disconnect Slack workspace
- Connect/disconnect Teams webhook
- Connect/disconnect ERP (QuickBooks, Xero, NetSuite, SAP)
- Connection health status

### Onboarding
- Step-by-step onboarding flow
- Status tracking (persisted in organization settings)
- GA readiness assessment

### Settings
- Approval thresholds
- GL account mappings
- Auto-approve rules
- AP policies with versioning
- Organization settings
- User preferences
- Rollback controls (feature flags)
- Data residency configuration
- GDPR data export and deletion requests

---

## Audit Trail

22 event types covering the full invoice lifecycle:

**Lifecycle:** received, classified, extracted, validated
**Analysis:** analyzed, duplicate_check, anomaly_check, policy_check
**Decisions:** decision_made, auto_approved, flagged, routed
**Human:** approval_requested, approved, rejected, modified, comment_added
**Actions:** posted, payment_scheduled, payment_sent
**System:** error, retry, notification_sent

All audit events are append-only (database triggers prevent UPDATE/DELETE). Each event records: actor, timestamp, reasoning, confidence, duration, correlation ID.

---

## Reconciliation

- Import transactions from Google Sheets
- Match against AP items by amount + date
- Exception flagging for unmatched items
- Resolution tracking
- Session-based workflow (created → importing → matching → reviewing → complete)

---

## Subscription Tiers

| Capability | Free | Trial | Pro | Enterprise |
|---|---|---|---|---|
| Invoices/month | 25 | 500 | 500 | Unlimited |
| Vendors | 10 | 100 | 100 | Unlimited |
| Users | 1 | 5 | 5 | Unlimited |
| ERP connections | 1 | 3 | 3 | Unlimited |
| AI extractions/month | 50 | 1,000 | 1,000 | Unlimited |
| Multi-currency | No | Yes | Yes | Yes |
| Three-way matching | No | Yes | Yes | Yes |
| Advanced analytics | No | Yes | Yes | Yes |
| Custom integrations | No | No | No | Yes |
| SLA support | No | No | No | Yes |

---

## Security

- JWT authentication (access + refresh tokens)
- Google OAuth for Gmail extension
- Role-based access control (admin, member, viewer)
- HttpOnly session cookies (SameSite)
- API key management with hashed storage
- Fernet encryption for all secrets at rest (OAuth tokens, ERP credentials, Slack bot tokens)
- Prompt injection detection (prompt_guard)
- SQL injection prevention (column whitelists, parameterized queries, OData value escaping)
- Slack request signature verification
- Teams webhook signature verification
- Rate limiting (100 requests/60 seconds default)
- CORS configuration
- Data residency controls
- GDPR data export and deletion support

---

## Infrastructure

- FastAPI backend
- SQLite (dev) / PostgreSQL (prod)
- Dual database support with connection pooling
- Lazy table initialization
- Durable retry queue for failed operations
- Notification retry queue (Slack/Teams) with exponential backoff
- Feature flags and rollback controls
- Structured logging with correlation IDs
- Health check endpoints
- Cloudflare tunnel support for webhook testing

---

## Test Coverage

79 test modules covering:
- End-to-end AP flow
- Agent runtime and planning
- ERP posting and query safety
- Gmail classification and activities
- Session security
- Prompt injection detection
- Invoice extraction evaluation harness
- Learning calibration
- Browser agent dispatch
- Pipeline hardening
- State observers

---

## What Is NOT Built Yet

For honesty, these are mentioned in docs or UI but not fully implemented:

- **SSO/SAML** — Gated in Enterprise tier, not implemented
- **Multi-entity within one org** — Org-level isolation exists, but not subsidiary/division routing from one inbox
- **Oracle ERP** — Not implemented (only NetSuite, which Oracle owns)
- **SOC 2 compliance** — No certification process started
- **Dedicated infrastructure** — Enterprise tier feature, not built
