"""Surface and connector coverage catalog for Solden.

This is the product-facing readiness contract. It separates three ideas that
were previously collapsed into "supported":

* connection method: how the customer connects it
* memory surface: where Solden can render or expose operational memory
* capability constraints: ERP-specific limits without weakening the Solden standard
* validation status: proof from sandbox, customer, governance, and failure-mode evidence
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional

from solden.core.database import SoldenDB
from solden.services.erp_evidence_contract import build_erp_evidence_contract
from solden.services.erp_connector_strategy import get_erp_connector_strategy
from solden.services.erp_lifecycle_parity import build_lifecycle_parity_for_erp


SOLDEN_AP_STANDARD_STATUS = "ap_operational_memory_standard"
SOLDEN_AP_STANDARD_LABEL = "AP operational memory standard"

SURFACE_MODEL_LABELS: Dict[str, str] = {
    "gmail_thread_panel": "Gmail thread panel",
    "outlook_mail_add_in": "Outlook mail add-in",
    "slack_approval_cards": "Slack approval cards",
    "teams_adaptive_cards": "Teams adaptive cards",
    "workspace_control_center": "Workspace control center",
    "native_panel": "Native panel",
    "fiori_extension": "Fiori extension",
    "platform_services_panel": "Platform Services panel",
    "provider_neutral_memory_api": "Provider-neutral memory API",
}

CONSTRAINT_COPY: Dict[str, Dict[str, str]] = {
    "no_native_panel": {
        "label": "No native ERP panel",
        "detail": "Solden links the ERP reference to the memory API instead of embedding a panel in this ERP.",
    },
    "manual_credits": {
        "label": "Credits remain manual",
        "detail": "AP bills can post through the connector; credit application still needs an operator path.",
    },
    "manual_settlement": {
        "label": "Settlement remains manual",
        "detail": "Payment settlement still needs an operator path until this ERP write is validated.",
    },
    "sandbox_validation_pending": {
        "label": "Sandbox validation pending",
        "detail": "The connector path exists, but sandbox/customer proof is still tracked under validation status.",
    },
}

VALIDATION_LABELS: Dict[str, str] = {
    "evidence_backed": "Evidence backed",
    "proof_pending_governance": "Governance proof pending",
    "sandbox_only": "Sandbox evidence only",
    "customer_only": "Customer evidence only",
    "sandbox_validation_pending": "Sandbox validation pending",
    "missing_evidence": "Evidence pending",
    "evidence_pending": "Evidence pending",
    "not_applicable": "Not ERP validated",
}


@dataclass(frozen=True)
class SurfaceCapability:
    key: str
    label: str
    family: str
    role: str
    connection_method: str
    memory_surface: str
    surface_model: str
    decision_actions: str
    write_capability: str
    notes: str
    solden_standard_status: str = SOLDEN_AP_STANDARD_STATUS
    solden_standard_label: str = SOLDEN_AP_STANDARD_LABEL

    def as_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["surface_model_label"] = SURFACE_MODEL_LABELS.get(self.surface_model, self.surface_model.replace("_", " ").title())
        out["capability_constraints"] = []
        out["validation_status"] = {
            "status": "not_applicable",
            "label": VALIDATION_LABELS["not_applicable"],
            "ready_for_claim": None,
        }
        # Deprecated compatibility aliases. Use solden_standard_status,
        # surface_model, capability_constraints, and validation_status instead.
        out["maturity"] = self.solden_standard_status
        out["maturity_label"] = self.solden_standard_label
        out["deprecated_fields"] = {
            "maturity": "Use solden_standard_status; ERP differences are not maturity tiers.",
            "maturity_label": "Use solden_standard_label; show validation_status for proof.",
        }
        return out


SURFACE_CATALOG: tuple[SurfaceCapability, ...] = (
    SurfaceCapability(
        key="gmail",
        label="Gmail",
        family="intake",
        role="Inbox render target",
        connection_method="Google OAuth / extension",
        memory_surface="Thread panel",
        surface_model="gmail_thread_panel",
        decision_actions="Context capture, source linking, missing-context review, operator actions",
        write_capability="Email thread and source-link actions",
        notes="Primary inbox surface for AP intake and thread-level operational memory.",
    ),
    SurfaceCapability(
        key="outlook",
        label="Outlook",
        family="intake",
        role="Inbox render target",
        connection_method="Microsoft OAuth / add-in",
        memory_surface="Mail add-in panel",
        surface_model="outlook_mail_add_in",
        decision_actions="Context capture, source linking, intake context, operator actions",
        write_capability="Mailbox actions through Microsoft Graph and add-in context",
        notes="Microsoft 365 peer to Gmail for teams that live in Outlook.",
    ),
    SurfaceCapability(
        key="slack",
        label="Slack",
        family="approval",
        role="Chat decision surface",
        connection_method="Slack OAuth app",
        memory_surface="Approval cards and reply sync",
        surface_model="slack_approval_cards",
        decision_actions="Approve, reject, request info, exception review",
        write_capability="Decision callbacks and card updates",
        notes="Primary chat decision surface. Decisions write back to the record timeline.",
    ),
    SurfaceCapability(
        key="teams",
        label="Teams",
        family="approval",
        role="Chat decision surface",
        connection_method="Teams app package / webhook",
        memory_surface="Adaptive cards and webhook notifications",
        surface_model="teams_adaptive_cards",
        decision_actions="Approve, reject, request info, exception review",
        write_capability="Bot callbacks, card updates, and webhook notifications",
        notes="Microsoft Teams peer to Slack for approval decisions and memory sync.",
    ),
    SurfaceCapability(
        key="workspace",
        label="Workspace",
        family="control_center",
        role="Control center",
        connection_method="Solden authenticated app",
        memory_surface="Cross-surface work-in-progress view",
        surface_model="workspace_control_center",
        decision_actions="Intervention, audit, governance, setup, investigation",
        write_capability="Admin/config and escalated record actions",
        notes="Not the daily approval surface; it watches render targets and handles intervention.",
    ),
    SurfaceCapability(
        key="netsuite",
        label="NetSuite",
        family="erp",
        role="ERP native + API connector",
        connection_method="Token-Based Authentication",
        memory_surface="SuiteApp panel",
        surface_model="native_panel",
        decision_actions="Approve, reject, request info from vendor bill context",
        write_capability="Bill posting, vendor credits, standard payments",
        notes="Highest-leverage enterprise ERP surface; SDN/customer sandbox validation is the next proof point.",
    ),
    SurfaceCapability(
        key="sap",
        label="SAP",
        family="erp",
        role="ERP native + API connector",
        connection_method="OData/API credentials",
        memory_surface="Fiori extension",
        surface_model="fiori_extension",
        decision_actions="Approve, reject, request info from supplier-invoice context",
        write_capability="Bill posting, purchase credits, standard payments",
        notes="Supports SAP B1/S/4HANA style API paths; customer landscape validation is still required.",
    ),
    SurfaceCapability(
        key="sage_intacct",
        label="Sage Intacct",
        family="erp",
        role="ERP native + API connector",
        connection_method="XML gateway credentials",
        memory_surface="Platform Services panel",
        surface_model="platform_services_panel",
        decision_actions="Approve, reject, request info from bill context",
        write_capability="AP bill posting and read-side AP status; credits/payments manual for now",
        notes="Native panel route exists; AP bill flow needs customer sandbox validation before GA claims.",
    ),
    SurfaceCapability(
        key="quickbooks",
        label="QuickBooks",
        family="erp",
        role="API connector",
        connection_method="OAuth 2.0",
        memory_surface="Provider-neutral ERP memory API",
        surface_model="provider_neutral_memory_api",
        decision_actions="Resolve ERP reference to Solden memory; approve/reject/request info via API",
        write_capability="Bill posting, vendor credits, standard payments",
        notes="QuickBooks does not provide the same embedded panel model; Solden exposes memory through the ERP-reference API.",
    ),
    SurfaceCapability(
        key="xero",
        label="Xero",
        family="erp",
        role="API connector",
        connection_method="OAuth 2.0",
        memory_surface="Provider-neutral ERP memory API",
        surface_model="provider_neutral_memory_api",
        decision_actions="Resolve ERP reference to Solden memory; approve/reject/request info via API",
        write_capability="ACCPAY bill posting, credit allocations, standard bill payments",
        notes="Xero is API-first, not iframe/native-panel first.",
    ),
    SurfaceCapability(
        key="sage_accounting",
        label="Sage Accounting",
        family="erp",
        role="API connector",
        connection_method="OAuth 2.0",
        memory_surface="Provider-neutral ERP memory API",
        surface_model="provider_neutral_memory_api",
        decision_actions="Resolve ERP reference to Solden memory; approve/reject/request info via API",
        write_capability="Purchase-invoice posting and read-side status; credits/payments manual for now",
        notes="Sage Business Cloud Accounting API path exists; production claims need sandbox validation.",
    ),
)


def _constraint(key: str) -> Dict[str, str]:
    copy = CONSTRAINT_COPY.get(key, {})
    return {
        "key": key,
        "label": copy.get("label", key.replace("_", " ").title()),
        "detail": copy.get("detail", ""),
    }


def _validation_status(
    evidence_contract: Dict[str, Any],
    *,
    rollout_stage: str = "",
) -> Dict[str, Any]:
    evidence = evidence_contract if isinstance(evidence_contract, dict) else {}
    raw_status = str(evidence.get("evidence_status") or "").strip().lower()
    status = raw_status or "evidence_pending"
    if status in {"missing_evidence", "evidence_pending"} and "sandbox_pending" in str(rollout_stage or ""):
        status = "sandbox_validation_pending"

    return {
        "status": status,
        "label": VALIDATION_LABELS.get(status, status.replace("_", " ").title()),
        "ready_for_claim": bool(evidence.get("ready_for_claim")),
        "sandbox_evidence_status": evidence.get("sandbox_evidence_status") or "missing",
        "customer_evidence_status": evidence.get("customer_evidence_status") or "missing",
        "failure_mode_evidence_status": evidence.get("failure_mode_evidence_status") or "missing",
        "checklist_status": evidence.get("checklist_status") or "not_started",
        "signoff_status": evidence.get("signoff_status") or "missing",
        "known_gaps": list(evidence.get("known_gaps") or []),
    }


def _erp_capability_constraints(surface: SurfaceCapability, capability: Any) -> List[Dict[str, str]]:
    constraints: List[Dict[str, str]] = []
    if surface.surface_model == "provider_neutral_memory_api":
        constraints.append(_constraint("no_native_panel"))
    if not bool(getattr(capability, "supports_api_apply_credit", False)):
        constraints.append(_constraint("manual_credits"))
    if not bool(getattr(capability, "supports_api_apply_settlement", False)):
        constraints.append(_constraint("manual_settlement"))
    if "sandbox_pending" in str(getattr(capability, "rollout_stage", "") or ""):
        constraints.append(_constraint("sandbox_validation_pending"))
    return constraints


def _safe_status_map(statuses: Optional[Iterable[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in statuses or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("name") or row.get("integration_type") or "").strip().lower()
        if key:
            out[key] = row
    return out


def _declared_lifecycle_constraint_count(row: Dict[str, Any]) -> int:
    lifecycle_summary = ((row.get("lifecycle_parity") or {}).get("summary") or {})
    return int(lifecycle_summary.get("declared_constraint_actions") or 0)


def _connection_by_erp(db: SoldenDB, organization_id: str) -> Dict[str, Dict[str, Any]]:
    try:
        rows = db.get_erp_connections(organization_id)
    except Exception:
        rows = []
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("erp_type") or "").strip().lower()
        if key and key not in out:
            out[key] = row
    return out


def build_surface_readiness(
    organization_id: str,
    *,
    db: Optional[SoldenDB] = None,
    integration_statuses: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return the canonical readiness catalog with org connection state."""

    org_id = str(organization_id or "").strip()
    from solden.services.surface_memory_contract import build_surface_memory_contract

    memory_contract = build_surface_memory_contract(org_id, db=db)
    memory_by_key = {
        str(row.get("key") or ""): row
        for row in memory_contract.get("surfaces", [])
        if isinstance(row, dict)
    }
    erp_evidence_contract = build_erp_evidence_contract(org_id, db=db)
    erp_evidence_by_key = {
        str(row.get("erp_type") or ""): row
        for row in erp_evidence_contract.get("connectors", [])
        if isinstance(row, dict)
    }
    status_by_name = _safe_status_map(integration_statuses)
    erp_connections = _connection_by_erp(db, org_id) if db is not None and org_id else {}
    strategy = get_erp_connector_strategy()

    rows: List[Dict[str, Any]] = []
    for surface in SURFACE_CATALOG:
        base = surface.as_dict()
        status_row = status_by_name.get(surface.key) or {}
        connected = False
        connection_status = "available"

        if surface.family == "erp":
            conn = erp_connections.get(surface.key) or {}
            connected = bool(conn) and bool(conn.get("is_active", True))
            connection_status = "connected" if connected else "not_connected"
            capability = strategy.resolve(surface.key)
            evidence_contract = erp_evidence_by_key.get(surface.key) or {}
            capability_constraints = _erp_capability_constraints(surface, capability)
            base.update({
                "api_supported": bool(capability.supports_api_post_bill),
                "credit_supported": bool(capability.supports_api_apply_credit),
                "settlement_supported": bool(capability.supports_api_apply_settlement),
                "rollout_stage": capability.rollout_stage,
                "connector_notes": capability.notes,
                "deep_link_id": conn.get("deep_link_id"),
                "last_sync_at": conn.get("last_sync_at"),
                "evidence_contract": evidence_contract,
                "capability_constraints": capability_constraints,
                "lifecycle_parity": build_lifecycle_parity_for_erp(
                    surface.key,
                    capability=capability,
                    capability_constraints=capability_constraints,
                ),
                "validation_status": _validation_status(
                    evidence_contract,
                    rollout_stage=capability.rollout_stage,
                ),
            })
        elif surface.key == "workspace":
            connected = True
            connection_status = "ready"
        else:
            connected = bool(status_row.get("connected"))
            raw_status = str(status_row.get("status") or "").strip().lower()
            if raw_status == "disabled":
                connection_status = "disabled"
            elif connected or raw_status in {"connected", "ready", "active"}:
                connection_status = "connected"
            else:
                connection_status = raw_status or "not_connected"
            base.update({
                "requires_reauthorization": bool(status_row.get("requires_reauthorization") or status_row.get("requires_reconnect")),
                "last_sync_at": status_row.get("last_sync_at"),
            })

        base.update({
            "connected": connected,
            "connection_status": connection_status,
            "memory_contract": memory_by_key.get(surface.key) or {},
        })
        rows.append(base)

    summary = {
        "total": len(rows),
        "connected": sum(1 for row in rows if row.get("connected")),
        "erp_total": sum(1 for row in rows if row.get("family") == "erp"),
        "erp_connected": sum(1 for row in rows if row.get("family") == "erp" and row.get("connected")),
        "erp_solden_standard_status": SOLDEN_AP_STANDARD_STATUS,
        "erp_solden_standard_surfaces": sum(
            1 for row in rows
            if row.get("family") == "erp" and row.get("solden_standard_status") == SOLDEN_AP_STANDARD_STATUS
        ),
        "embedded_erp_surfaces": sum(
            1 for row in rows
            if row.get("family") == "erp"
            and row.get("surface_model") in {"native_panel", "fiori_extension", "platform_services_panel"}
        ),
        "provider_neutral_erp_surfaces": sum(
            1 for row in rows
            if row.get("family") == "erp" and row.get("surface_model") == "provider_neutral_memory_api"
        ),
        "erp_validation_pending": sum(
            1 for row in rows
            if row.get("family") == "erp"
            and ((row.get("validation_status") or {}).get("status") not in {"evidence_backed"})
        ),
        "erp_lifecycle_gap": sum(
            1 for row in rows
            if row.get("family") == "erp"
            and ((row.get("lifecycle_parity") or {}).get("status") == "gap")
        ),
        "erp_lifecycle_constrained": sum(
            1 for row in rows
            if row.get("family") == "erp"
            and _declared_lifecycle_constraint_count(row) > 0
        ),
        "native_erp_surfaces": sum(
            1 for row in rows
            if row.get("family") == "erp"
            and row.get("surface_model") in {"native_panel", "fiori_extension", "platform_services_panel"}
        ),
        "api_memory_erp_surfaces": sum(
            1 for row in rows
            if row.get("family") == "erp" and row.get("surface_model") == "provider_neutral_memory_api"
        ),
        "sandbox_pending": sum(
            1 for row in rows
            if row.get("family") == "erp"
            and ((row.get("validation_status") or {}).get("status") == "sandbox_validation_pending")
        ),
        "memory_ready": int((memory_contract.get("summary") or {}).get("ready") or 0),
        "memory_needs_work": int((memory_contract.get("summary") or {}).get("needs_work") or 0),
        "memory_recent_events": int((memory_contract.get("summary") or {}).get("recent_memory_events") or 0),
        "erp_evidence_backed": int((erp_evidence_contract.get("summary") or {}).get("evidence_backed") or 0),
        "erp_sandbox_observed": int((erp_evidence_contract.get("summary") or {}).get("sandbox_observed") or 0),
        "erp_customer_observed": int((erp_evidence_contract.get("summary") or {}).get("customer_observed") or 0),
        "erp_missing_customer_evidence": int((erp_evidence_contract.get("summary") or {}).get("missing_customer_evidence") or 0),
        "deprecated_summary_fields": {
            "native_erp_surfaces": "Use embedded_erp_surfaces.",
            "api_memory_erp_surfaces": "Use provider_neutral_erp_surfaces.",
            "sandbox_pending": "Use erp_validation_pending or row.validation_status.",
        },
    }

    return {
        "organization_id": org_id,
        "contract": "surface_readiness.v1",
        "surfaces": rows,
        "summary": summary,
        "memory_contract": {
            "contract": memory_contract.get("contract"),
            "computed_at": memory_contract.get("computed_at"),
            "summary": memory_contract.get("summary") or {},
        },
        "erp_evidence_contract": {
            "contract": erp_evidence_contract.get("contract"),
            "computed_at": erp_evidence_contract.get("computed_at"),
            "summary": erp_evidence_contract.get("summary") or {},
        },
    }
