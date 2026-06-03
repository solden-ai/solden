# Solden Embedded Ecosystem (Operational Memory, AP Wedge)

## Status

- **Role:** Product-surface and ecosystem reference
- **Canonical doctrine:** [../PLAN.md](../PLAN.md)
- **Scope here:** AP v1 embedded ecosystem and the broader back-office operational-memory expansion model

## Ecosystem Summary

Solden is embedded operational memory for back-office work in progress:

1. Finance is the entry point.
2. AP is the first production wedge.
3. Gmail is the primary AP operator surface.
4. Slack/Teams are approval decision surfaces.
5. ERP is the system of record for posted transactions.
6. Solden keeps the owner, next step, context, blocker, proof, and audit together until the work is done.

The product is designed to execute work in-place, not move operators into a new daily dashboard.

## Surface Map

### 1. Gmail (operator execution context)

Primary responsibilities:

1. show AP status, exceptions, and next action
2. support in-thread operator decisions
3. display progressive disclosure for context/audit details

### 2. Slack / Teams (decision context)

Primary responsibilities:

1. present approval/rejection/request-info actions
2. provide concise validation and risk context
3. capture idempotent, auditable callback decisions

### 3. ERP systems (record context)

Primary responsibilities:

1. receive approved AP postings
2. return ERP references and posting outcomes
3. remain source of truth for posted financial records

Implementation by ERP:

1. NetSuite: SuiteApp panel renders Solden operational memory inside the ERP record context.
2. SAP: Fiori extension renders Solden operational memory inside the ERP record context.
3. Xero: public APIs do not provide an equivalent in-record embedded panel, so posted ACCPAY invoices carry a `Url` back to the Solden AP record plus `solden:` workflow markers in `Reference` when tenant field mappings request workflow context.
4. QuickBooks Online: public APIs do not provide an equivalent in-bill embedded panel, so posted Bills carry the Solden AP record link in `PrivateNote` while configured QBO `CustomField` `DefinitionId`s remain tenant-controlled.

### 4. Admin/Ops surfaces (configuration context)

Primary responsibilities:

1. integration setup and health diagnostics
2. policy and routing configuration
3. rollout controls and evidence operations

## Operational Memory Model

```text
Embedded surfaces (Gmail + Slack/Teams)
      |
      v
Solden work-in-progress memory (single execution core)
      |
      +-> AP skill (production)
      +-> health/read-only skill(s)
      +-> future finance/back-office skills (post-AP)
      |
      v
ERP and external system adapters
```

## AP v1 Lifecycle Across Surfaces

1. AP email arrives in Gmail.
2. Solden classifies/extracts and validates.
3. Gmail shows operator summary and next action.
4. If required, approval is routed to Slack/Teams.
5. On approval + eligibility, Solden posts to ERP.
6. All transitions and outcomes are audited.

## Expansion Doctrine (Post AP)

Future workflow expansion should happen by adding new skills to the same operational-memory system, not by introducing disconnected execution stacks.

Examples:

1. disputes/vendor issue handling
2. collections/cash-application support
3. close-task orchestration support

All new skills must inherit:

1. policy gates
2. HITL controls where required
3. idempotent mutation contracts
4. end-to-end auditability
5. truthful durability semantics

## Non-Goals for AP v1 Ecosystem

1. Generic no-code automation-builder UX as core product model.
2. Dashboard-first AP workflow model.
3. New consumer messaging surfaces as AP execution channels.

## Related Docs

1. [../PLAN.md](../PLAN.md)
2. [HOW_IT_WORKS.md](HOW_IT_WORKS.md)
3. [V1_EMBEDDED_WORKER_EXPERIENCE.md](V1_EMBEDDED_WORKER_EXPERIENCE.md)
4. [V1_BACKEND_CONTRACTS.md](V1_BACKEND_CONTRACTS.md)
5. [API_REFERENCE.md](API_REFERENCE.md)
6. [AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md)
