# Workflow Platform — declarative Box types

Solden's runtime is Box-type-agnostic on its critical path (CoordinationEngine,
audit hash-chain, exception queue, `Plan.box_type`). The workflow platform lets
a new Box type be defined as **data** — a `WorkflowSpec` — instead of ~10
hand-written files. Two levels:

- **Level 1 (built-in)** — declare a `WorkflowSpec` in `solden/box_specs/` and
  call `register_spec`. Zero bespoke store/state-machine/route/migration code.
- **Level 2 (tenant)** — an org admin authors a versioned spec at runtime via
  the API / no-code builder; it is stored per-tenant in `workflow_specs` and
  resolved per request. Optional customer **hooks** run in a WASM sandbox.

Declared types ride a single generic `boxes` table (`id, organization_id,
box_type, state, spec_version, data JSONB`). Bespoke types (`ap_item`,
`bank_match`, `purchase_order`) keep their own tables, unchanged.

## WorkflowSpec

```python
WorkflowSpec(
    box_type="contract_review",          # snake_case, unique per org
    url_slug="contract-reviews",         # kebab-case
    states=("draft", "in_review", "approved", "rejected"),
    initial_state="draft",
    terminal_states=("approved", "rejected"),
    transitions={"draft": {"in_review"}, "in_review": {"approved", "rejected"}},
    action_states={"submit": "in_review", "approve": "approved", "reject": "rejected"},
    fields=("title", "counterparty", "value"),
    exception_state=None,                 # None -> a failed action raises a box_exception
    conditions={...},                     # Level 2 guards (see Hooks)
    hooks={...},                          # Level 2 customer code (see Hooks)
)
```

Validation (`validate_spec`) rejects: undeclared states, unreachable states,
dead-end non-terminal states, edges out of terminal states, action targets that
don't exist, reserved box-type names, and field names that collide with reserved
columns (`id/state/box_type/organization_id/spec_version/data/created_at/updated_at`).

## Authoring API (Level 2, admin-gated)

```
POST /api/workspace/workflow-specs                                 create draft
GET  /api/workspace/workflow-specs                                 list
POST /api/workspace/workflow-specs/validate                        validate only
GET  /api/workspace/workflow-specs/{box_type}                      active version
POST /api/workspace/workflow-specs/{box_type}/versions/{v}/activate
POST /api/workspace/workflow-specs/{box_type}/versions/{v}/archive
```

Versions are immutable once created; exactly one is `active` per
`(org, box_type)`. **Boxes pin `spec_version`** at creation, so activating a new
version never changes the legal transitions of in-flight boxes. Max
`MAX_WORKFLOW_TYPES_PER_ORG` (50) distinct types per tenant.

## Box data plane (any declared type)

```
GET  /api/workspace/workflows/{box_type}                 list boxes
POST /api/workspace/workflows/{box_type}                 create box (body: {data})
GET  /api/workspace/workflows/{box_type}/{box_id}        read
POST /api/workspace/workflows/{box_type}/{box_id}/{action}   transition (409 on illegal)
```

`{action}` is mapped to a target state via the box's pinned spec
`action_states`. The CoordinationEngine drives the same edges autonomously via
`move_box_stage`.

## Hooks (Level 2) — gated behind `FEATURE_WORKFLOW_HOOKS` (default off)

Two tiers of customer logic on a transition, keyed by `"{from}->{to}"` then
`"on_enter:{to}"`:

1. **Conditions** — a safe expression guard over the box's fields, e.g.
   `"amount <= 10000 and risk != 'high'"`. No code execution: a strict AST
   allowlist (no attribute access, no arbitrary calls, no comprehensions/lambdas).
   A false guard denies the transition.

2. **Code hooks** — customer code in a **WASM sandbox** (Wasmtime). Hooks are
   pure: they receive sanitized box data and return
   `{allow, deny_reason, data_patch, effects}`. They have **no ambient
   capabilities** (imports denied → no syscalls/network/filesystem), are bounded
   by **fuel** (CPU), an **epoch watchdog** (wall-clock), and a **memory cap**,
   and are **fail-closed** (any trap/limit/error → deny). A returned
   `data_patch` is applied with reserved keys filtered out; returned `effects`
   are applied by trusted host code.

### Effect catalog (the only side-effects a hook can request)

- `log` — structured note.
- `webhook` — POST JSON to a customer URL. **SSRF-guarded**: https/http only,
  ports 80/443, resolves once and connects to the pinned IP (no DNS-rebinding),
  `is_global` allowlist (IPv4-mapped/NAT64 unwrapped; CGNAT/metadata blocked).
- `notify` — best-effort operator notification.

Each hook run is recorded in `workflow_hook_runs`.

### Security posture

`FEATURE_WORKFLOW_HOOKS` must NOT be enabled for any tenant until the sandbox
has passed an adversarial security review (already applied once: DNS-rebinding
TOCTOU, IPv4-mapped/NAT64/CGNAT bypass, effect fan-out, fuel fail-closed). The
expression-condition tier is safe on its own but shares the same flag.

## Where things live

| Concern | File |
|---|---|
| Spec model + validation + registry + resolver seam | `solden/core/workflow_spec.py` |
| Generic box store | `solden/core/stores/generic_box_store.py` |
| Tenant spec store + resolver install | `solden/core/stores/workflow_spec_store.py` |
| Registry dispatch + dynamic resolver | `solden/core/box_registry.py` |
| Authoring API | `solden/api/workflow_spec_routes.py` |
| Box data-plane API | `solden/api/workflow_routes.py` |
| Expression conditions | `solden/core/hooks/expressions.py` |
| WASM sandbox | `solden/core/hooks/sandbox.py` |
| Transition dispatcher | `solden/core/hooks/dispatcher.py` |
| Effect catalog | `solden/core/effects/catalog.py` |
| Tables | migrations v92 (`boxes`), v93 (`workflow_specs`), v94 (`workflow_hook_runs`) |
| No-code builder UI | `ui/web-app/src/routes/pages/WorkflowsPage.js` |
