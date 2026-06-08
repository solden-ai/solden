# Cross-System Entity Graph — Scoping

Status: scoping (no code yet). Owner: Mo. Last updated: 2026-06-08.

## Problem

Solden resolves two kinds of identity today: **vendor** identity
(`solden/services/vendor_attribute_matcher.py`, fuzzy name + VAT/IBAN/domain) and
**work-item** linkage (`solden/services/operational_memory_capture.py`, the
observed-event to `ap_item` linker). It has no shared graph for the other
entities a back-office record touches. So when an email says "the Project Alpha
spend", Slack calls it "#alpha-rollout", and the ERP posts it to "Cost Center
402", nothing in Solden knows those are the same thing.

That gap caps the audit story. We can already answer "why was this invoice
approved" by linking the decision thread to the record. We cannot yet answer
"show everything charged to Cost Center 402 this close" or "this touches the
Alpha project, which is over budget", because the cross-system entity identity
is not captured.

This is the **semantic memory** tier: the relationships between people,
projects, cost centers, GL accounts, and the work items that reference them.

## What exists today (build on, do not duplicate)

- **The confirmation ladder.** `operational_memory_capture.py` already encodes
  the pattern we want: deterministic-first resolution, a `0.72` link threshold,
  a `0.90` auto-confirm threshold, and a human confirmation prompt when below.
  The entity graph reuses this exact ladder, not a new one.
- **Fuzzy name matching.** `vendor_name_similarity()` (token-set similarity) is
  now public and is the reusable primitive for fuzzy entity-name resolution.
- **Tenant isolation + two-axis auth.** `solden/core/auth.py`,
  `solden/core/stores/auth_store.py` (workspace_role + user_box_roles). Entity
  rows and resolution are org-scoped from day one.
- **Hash-chained audit.** `solden/core/database.py`. Alias confirmations are
  operational decisions and get the same provenance as state transitions.
- **Box + memory model.** `box_registry`, `box_lifecycle_store`,
  `memory_events`. Entities attach to the same records, they do not become a
  separate product surface.

## Model

Three tenant-scoped tables. Plain Postgres, no graph database.

**`entities`** — the canonical node.
`id, organization_id, entity_type, canonical_name, source, source_ref,
metadata(jsonb), created_at, updated_at`.
`entity_type ∈ {vendor, project, cost_center, gl_account, person, department,
contract}`. `source ∈ {erp_master, seeded, inferred}`. `source_ref` holds the
authoritative external id when there is one (the NetSuite/SAP cost-center id),
which is what makes deterministic resolution possible.

**`entity_aliases`** — the surface-specific labels.
`id, organization_id, entity_id, alias_text, alias_kind, surface, confidence,
status, provenance(jsonb), created_at`.
`alias_kind ∈ {slack_channel, email_label, erp_label, freeform}`.
`status ∈ {confirmed, proposed, rejected}`. A confirmed alias is the mechanism
by which the graph *learns*: once "#alpha-rollout = Project Alpha" is confirmed,
it resolves deterministically forever after.

**`entity_links`** — typed edges.
`id, organization_id, subject_kind, subject_ref, object_entity_id, relation,
confidence, status, provenance(jsonb)`.
`subject_kind ∈ {entity, box}` so an edge can be entity→entity (project
`maps_to` cost_center) or box→entity (an `ap_item` `charged_to` cost_center,
`belongs_to` project). `relation ∈ {belongs_to, maps_to, owned_by,
charged_to}`.

## Resolution ladder (reuses the capture-loop pattern)

Given a mention in an observed event ("Project Alpha", "CC 402", "#alpha"):

1. **Deterministic** — exact authoritative id (`mention == entity.source_ref`)
   or an exact confirmed alias. Confidence `1.0`.
2. **Fuzzy** — `vendor_name_similarity()` over candidate entity names/aliases of
   the plausible type, banded exactly like the linker (`≥0.92` strong, `0.75-
   0.92` partial).
3. **LLM-proposed** — only when 1 and 2 fail: an LLM proposes a candidate entity
   + alias. Never auto-applied. Emitted as a `confirmation_request`, same shape
   the capture loop already returns.

Apply the **same `0.72` / `0.90` thresholds and the same confirmation prompt**
("Is 'Project Alpha' the same as Cost Center 402?"). A confirmed alias drops to
the deterministic tier for next time. This is the "system of intent" applied to
identity: every alias confirmation is an auditable decision.

## Integration

- **Capture linker.** After resolving the work item, also resolve entity
  mentions in the observed context and enrich the memory candidate's
  `source_refs` with `entity_ids` (vendor is the first such entity; this
  generalizes it).
- **Memory record.** `build_box_operational_memory_record` surfaces linked
  entities ("touches Project Alpha, charged to CC 402").
- **Surfaces.** Render entity chips in the Gmail/Slack/ERP surfaces, gated by
  the viewer's scope.

## Permissions

Some entities are sensitive (a confidential project, a restructuring cost
center). Entity visibility rides the existing two-axis auth; the memory sidebar
must not leak entity context the viewer cannot otherwise see. Resolution and
rendering are both scoped to the viewer. For Phase 1 (cost_center / gl_account,
generally not secret) this can be org-level; per-entity ACLs are a Phase 2+
concern.

## Phasing

- **Phase 0** — this doc.
- **Phase 1 (recommended first slice): `cost_center` + `gl_account` from the ERP
  master.** Authoritative ids, deterministic resolution only (no fuzzy, no LLM),
  direct audit payoff ("why posted to CC 402"). Tables + deterministic resolver
  + capture-linker enrichment + record/surface rendering.
- **Phase 2** — fuzzy alias resolution (reuse `vendor_name_similarity`) with the
  confirmation ladder, for `project` / `department` / `person`. Confirmed aliases
  persist and become deterministic. Add per-entity ACLs here.
- **Phase 3** — LLM-proposed aliases (gated) for the long tail ("#alpha-rollout"
  → Project Alpha).
- **Phase 4** — cross-entity queries ("everything charged to CC 402 this close")
  and surface polish.

## Why cost-center/gl first

It is the only slice that is fully deterministic (authoritative ERP ids), needs
no fuzzy or LLM risk surface, and pays off the audit thesis immediately. It also
proves the table shape and the capture-linker enrichment path before we take on
the harder fuzzy/inferred entities.

## Open questions (for Mo)

1. **Source of canonical entities.** ERP-master sync first (NetSuite or SAP?),
   seeded lists, or inferred-then-confirmed? Recommendation: ERP master for
   cost_center/gl in Phase 1.
2. **Entity-level RBAC in Phase 1**, or defer to Phase 2? (cost_center/gl are
   usually not secret.)
3. **Alias decay.** Do inferred/confirmed aliases ever need re-confirmation?
   Likely no for ERP-id-backed entities; maybe a TTL for inferred ones.
4. **Entity scope.** Start finance-only (vendor / cost_center / gl / project) or
   include person/department in the model now even if unresolved until later?

## Out of scope (deliberate)

- No general-purpose graph database or new infrastructure. Postgres tables plus
  the existing patterns.
- No auto-applied aliases. Inference always proposes; humans confirm; the audit
  records it.
