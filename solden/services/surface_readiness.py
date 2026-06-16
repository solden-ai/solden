"""Surface and connector maturity catalog for Solden.

This is the product-facing readiness contract. It separates three ideas that
were previously collapsed into "supported":

* connection method: how the customer connects it
* memory surface: where Solden can render or expose operational memory
* maturity: how far that surface has been validated
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional

from solden.core.database import SoldenDB
from solden.services.erp_connector_strategy import get_erp_connector_strategy


@dataclass(frozen=True)
class SurfaceCapability:
    key: str
    label: str
    family: str
    role: str
    connection_method: str
    memory_surface: str
    maturity: str
    maturity_label: str
    decision_actions: str
    write_capability: str
    notes: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


SURFACE_CATALOG: tuple[SurfaceCapability, ...] = (
    SurfaceCapability(
        key="gmail",
        label="Gmail",
        family="intake",
        role="Inbox render target",
        connection_method="Google OAuth / extension",
        memory_surface="Thread panel",
        maturity="production_ready",
        maturity_label="Production-ready",
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
        maturity="production_ready",
        maturity_label="Production-ready",
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
        maturity="production_ready",
        maturity_label="Production-ready",
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
        maturity="production_ready",
        maturity_label="Production-ready",
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
        maturity="production_ready",
        maturity_label="Production-ready",
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
        maturity="native_panel_ready",
        maturity_label="Native panel ready",
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
        maturity="native_panel_ready",
        maturity_label="Native panel ready",
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
        maturity="sandbox_pending",
        maturity_label="Sandbox pending",
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
        maturity="api_memory_ready",
        maturity_label="API memory ready",
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
        maturity="api_memory_ready",
        maturity_label="API memory ready",
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
        maturity="sandbox_pending",
        maturity_label="Sandbox pending",
        decision_actions="Resolve ERP reference to Solden memory; approve/reject/request info via API",
        write_capability="Purchase-invoice posting and read-side status; credits/payments manual for now",
        notes="Sage Business Cloud Accounting API path exists; production claims need sandbox validation.",
    ),
)


def _safe_status_map(statuses: Optional[Iterable[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in statuses or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("name") or row.get("integration_type") or "").strip().lower()
        if key:
            out[key] = row
    return out


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
            base.update({
                "api_supported": bool(capability.supports_api_post_bill),
                "credit_supported": bool(capability.supports_api_apply_credit),
                "settlement_supported": bool(capability.supports_api_apply_settlement),
                "rollout_stage": capability.rollout_stage,
                "deep_link_id": conn.get("deep_link_id"),
                "last_sync_at": conn.get("last_sync_at"),
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
        "native_erp_surfaces": sum(
            1 for row in rows
            if row.get("family") == "erp" and "native" in str(row.get("maturity") or "")
        ),
        "api_memory_erp_surfaces": sum(
            1 for row in rows
            if row.get("family") == "erp" and row.get("memory_surface") == "Provider-neutral ERP memory API"
        ),
        "sandbox_pending": sum(1 for row in rows if row.get("maturity") == "sandbox_pending"),
        "memory_ready": int((memory_contract.get("summary") or {}).get("ready") or 0),
        "memory_needs_work": int((memory_contract.get("summary") or {}).get("needs_work") or 0),
        "memory_recent_events": int((memory_contract.get("summary") or {}).get("recent_memory_events") or 0),
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
    }
