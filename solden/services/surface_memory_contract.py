"""Operational-memory parity contract for release surfaces.

Surface readiness answers whether a customer can connect or render a surface.
This module answers the stricter engineering question: if work changes on that
surface, does Solden preserve the operational-memory contract instead of merely
logging a UI action?
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence


MEMORY_CONTRACT_VERSION = "surface_memory_contract.v1"
MEMORY_EVENT_PREFIX = "memory_event:"


@dataclass(frozen=True)
class SurfaceMemoryContract:
    key: str
    label: str
    family: str
    write_contracts: tuple[str, ...]
    read_contracts: tuple[str, ...]
    write_paths: tuple[str, ...]
    read_paths: tuple[str, ...]
    state_changing_actions: tuple[str, ...]
    accepted_event_surfaces: tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, tuple):
                data[key] = list(value)
        return data


SURFACE_MEMORY_CONTRACTS: tuple[SurfaceMemoryContract, ...] = (
    SurfaceMemoryContract(
        key="gmail",
        label="Gmail",
        family="intake",
        write_contracts=("capture_operational_memory_event", "commit_runtime_memory_event"),
        read_contracts=("solden_memory_surface.v1",),
        write_paths=(
            "solden.api.gmail_extension.capture_extension_memory_event",
            "solden.services.finance_agent_runtime.FinanceAgentRuntime.execute_intent",
        ),
        read_paths=(
            "solden.api.gmail_extension._build_worklist_item_with_memory",
            "solden.services.memory_surface.build_surface_memory_snapshot(surface=gmail)",
        ),
        state_changing_actions=(
            "capture thread context",
            "verify confidence",
            "submit for approval",
            "reject invoice",
            "request budget decision",
            "record field correction",
            "post to ERP",
        ),
        accepted_event_surfaces=("gmail", "gmail_extension", "gmail_extension_bulk", "gmail_route"),
    ),
    SurfaceMemoryContract(
        key="outlook",
        label="Outlook",
        family="intake",
        write_contracts=("capture_operational_memory_event",),
        read_contracts=("solden_memory_surface.v1",),
        write_paths=("solden.services.outlook_email_processor._capture_outlook_memory_event",),
        read_paths=(
            "ui/outlook-addin/src/outlook-entry.js MemoryPanel",
            "solden.api.box_export.get_box_memory",
        ),
        state_changing_actions=(
            "capture mailbox context",
            "link source message",
            "ingest invoice",
            "surface operator action context",
        ),
        accepted_event_surfaces=("outlook", "microsoft_outlook", "outlook_addin"),
    ),
    SurfaceMemoryContract(
        key="slack",
        label="Slack",
        family="approval",
        write_contracts=("commit_runtime_memory_event", "capture_operational_memory_event"),
        read_contracts=("solden_memory_surface.v1", "slack_memory_summary"),
        write_paths=(
            "solden.api.slack_invoices._dispatch_slack_action",
            "solden.api.slack_invoices.handle_slack_events",
            "solden.api.slack_invoices._handle_mention_reply_sync",
        ),
        read_paths=(
            "solden.services.memory_surface.render_slack_memory_summary",
            "solden.services.procurement_chat.build_po_approval_blocks",
        ),
        state_changing_actions=("approve", "reject", "request info", "sync reply", "review exception"),
        accepted_event_surfaces=("slack", "slack_callback", "slack_reply"),
    ),
    SurfaceMemoryContract(
        key="teams",
        label="Teams",
        family="approval",
        write_contracts=("commit_runtime_memory_event",),
        read_contracts=("solden_memory_surface.v1", "adaptive_card_memory_facts"),
        write_paths=("solden.api.teams_invoices._dispatch_teams_action",),
        read_paths=(
            "solden.services.memory_surface.adaptive_card_memory_facts",
            "solden.services.procurement_chat.build_po_teams_card",
        ),
        state_changing_actions=("approve", "reject", "request info", "review exception"),
        accepted_event_surfaces=("teams", "microsoft_teams", "teams_callback"),
    ),
    SurfaceMemoryContract(
        key="workspace",
        label="Workspace",
        family="control_center",
        write_contracts=("capture_operational_memory_event", "commit_runtime_memory_event"),
        read_contracts=("solden_memory_surface.v1",),
        write_paths=(
            "solden.api.workspace_records.capture_workspace_memory_event",
            "solden.services.finance_agent_runtime.FinanceAgentRuntime.execute_intent",
        ),
        read_paths=(
            "solden.api.workspace_records.list_workspace_records",
            "solden.api.box_export.get_box_memory",
        ),
        state_changing_actions=(
            "capture decision",
            "resolve exception",
            "confirm rationale",
            "assign owner",
            "intervene in workflow",
        ),
        accepted_event_surfaces=("workspace", "workspace_spa", "workspace_records", "workspace_payments"),
    ),
    SurfaceMemoryContract(
        key="netsuite",
        label="NetSuite",
        family="erp",
        write_contracts=("commit_runtime_memory_event",),
        read_contracts=("solden_memory_surface.v1", "erp_native_panel"),
        write_paths=("solden.api.netsuite_panel._dispatch_netsuite_panel_action",),
        read_paths=("solden.api.netsuite_panel.get_ap_item_by_netsuite_bill",),
        state_changing_actions=("approve bill", "reject bill", "request info"),
        accepted_event_surfaces=("erp_native_netsuite", "netsuite", "netsuite_panel"),
    ),
    SurfaceMemoryContract(
        key="sap",
        label="SAP",
        family="erp",
        write_contracts=("commit_runtime_memory_event",),
        read_contracts=("solden_memory_surface.v1", "erp_native_panel"),
        write_paths=("solden.api.sap_extension._dispatch_sap_panel_action",),
        read_paths=("solden.api.sap_extension.get_ap_item_by_sap_invoice",),
        state_changing_actions=("approve supplier invoice", "reject supplier invoice", "request info"),
        accepted_event_surfaces=("erp_native_sap", "sap", "sap_fiori"),
    ),
    SurfaceMemoryContract(
        key="sage_intacct",
        label="Sage Intacct",
        family="erp",
        write_contracts=("commit_runtime_memory_event",),
        read_contracts=("solden_memory_surface.v1", "erp_native_panel"),
        write_paths=("solden.api.sage_intacct_panel._dispatch_sage_intacct_panel_action",),
        read_paths=("solden.api.sage_intacct_panel.get_ap_item_by_sage_intacct_bill",),
        state_changing_actions=("approve bill", "reject bill", "request info"),
        accepted_event_surfaces=("erp_native_sage_intacct", "sage_intacct", "sage_intacct_panel"),
    ),
    SurfaceMemoryContract(
        key="quickbooks",
        label="QuickBooks",
        family="erp",
        write_contracts=("commit_runtime_memory_event",),
        read_contracts=("solden_memory_surface.v1", "erp_memory_surface.v1"),
        write_paths=("solden.api.erp_memory_surface._dispatch_erp_memory_surface_action",),
        read_paths=("solden.api.erp_memory_surface.get_ap_item_by_erp_reference_surface",),
        state_changing_actions=("approve ERP-linked bill", "reject ERP-linked bill", "request info"),
        accepted_event_surfaces=("erp_native_quickbooks", "quickbooks"),
    ),
    SurfaceMemoryContract(
        key="xero",
        label="Xero",
        family="erp",
        write_contracts=("commit_runtime_memory_event",),
        read_contracts=("solden_memory_surface.v1", "erp_memory_surface.v1"),
        write_paths=("solden.api.erp_memory_surface._dispatch_erp_memory_surface_action",),
        read_paths=("solden.api.erp_memory_surface.get_ap_item_by_erp_reference_surface",),
        state_changing_actions=("approve ERP-linked bill", "reject ERP-linked bill", "request info"),
        accepted_event_surfaces=("erp_native_xero", "xero"),
    ),
    SurfaceMemoryContract(
        key="sage_accounting",
        label="Sage Accounting",
        family="erp",
        write_contracts=("commit_runtime_memory_event",),
        read_contracts=("solden_memory_surface.v1", "erp_memory_surface.v1"),
        write_paths=("solden.api.erp_memory_surface._dispatch_erp_memory_surface_action",),
        read_paths=("solden.api.erp_memory_surface.get_ap_item_by_erp_reference_surface",),
        state_changing_actions=("approve ERP-linked bill", "reject ERP-linked bill", "request info"),
        accepted_event_surfaces=("erp_native_sage_accounting", "sage_accounting", "sage_business_cloud_accounting"),
    ),
)


def _dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _memory_event_surface(event: Dict[str, Any]) -> str:
    payload = _dict(event.get("payload_json"))
    memory_event = _dict(payload.get("memory_event"))
    source = _dict(memory_event.get("source"))
    evidence = _dict(memory_event.get("evidence"))
    return str(
        source.get("surface")
        or evidence.get("captured_from")
        or event.get("source")
        or ""
    ).strip().lower()


def _recent_memory_events(
    db: Any,
    organization_id: str,
    *,
    window_hours: int,
    limit: int,
) -> List[Dict[str, Any]]:
    if db is None or not organization_id or not hasattr(db, "list_audit_events"):
        return []
    safe_limit = max(1, min(int(limit or 1000), 10000))
    try:
        rows = list(db.list_audit_events(organization_id, limit=safe_limit) or [])
    except TypeError:
        rows = list(db.list_audit_events(organization_id) or [])
    except Exception:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, int(window_hours or 24)))
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not str(row.get("event_type") or "").startswith(MEMORY_EVENT_PREFIX):
            continue
        ts = _parse_dt(row.get("ts") or row.get("created_at"))
        if ts is not None and ts < cutoff:
            continue
        out.append(row)
    return out


def _event_stats(events: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by_surface: Dict[str, Dict[str, Any]] = {}
    for event in events:
        surface = _memory_event_surface(event)
        if not surface:
            continue
        bucket = by_surface.setdefault(surface, {"count": 0, "last_event_at": None})
        bucket["count"] += 1
        ts = _parse_dt(event.get("ts") or event.get("created_at"))
        if ts is None:
            continue
        current = _parse_dt(bucket.get("last_event_at"))
        if current is None or ts > current:
            bucket["last_event_at"] = ts.isoformat()
    return by_surface


def _coverage_for_contract(
    contract: SurfaceMemoryContract,
    by_surface: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    accepted = {s.lower() for s in contract.accepted_event_surfaces}
    matching = [
        stats for surface, stats in by_surface.items()
        if surface in accepted
    ]
    recent_count = sum(int(stats.get("count") or 0) for stats in matching)
    last_seen: Optional[datetime] = None
    for stats in matching:
        ts = _parse_dt(stats.get("last_event_at"))
        if ts is not None and (last_seen is None or ts > last_seen):
            last_seen = ts
    return {
        "recent_memory_events": recent_count,
        "last_memory_event_at": last_seen.isoformat() if last_seen else None,
        "tenant_evidence_status": "observed" if recent_count > 0 else "not_observed",
    }


def build_surface_memory_contract(
    organization_id: str,
    *,
    db: Any = None,
    window_hours: int = 24,
    limit: int = 1000,
    contracts: Iterable[SurfaceMemoryContract] = SURFACE_MEMORY_CONTRACTS,
) -> Dict[str, Any]:
    """Return per-surface proof that memory is not second-class.

    ``status`` is a code-contract status: all release surfaces must have a
    write contract and a read contract. ``tenant_evidence_status`` is separate
    because an unused tenant should not make a correctly wired surface look
    broken.
    """
    org_id = str(organization_id or "").strip()
    recent_events = _recent_memory_events(
        db,
        org_id,
        window_hours=int(window_hours or 24),
        limit=int(limit or 1000),
    )
    by_surface = _event_stats(recent_events)

    rows: List[Dict[str, Any]] = []
    for contract in contracts:
        base = contract.as_dict()
        code_ready = bool(contract.write_contracts and contract.read_contracts and contract.write_paths and contract.read_paths)
        coverage = _coverage_for_contract(contract, by_surface)
        base.update({
            "code_ready": code_ready,
            "status": "ready" if code_ready else "needs_work",
            "missing": {
                "write_contracts": not bool(contract.write_contracts),
                "read_contracts": not bool(contract.read_contracts),
                "write_paths": not bool(contract.write_paths),
                "read_paths": not bool(contract.read_paths),
            },
            **coverage,
        })
        rows.append(base)

    summary = {
        "total": len(rows),
        "ready": sum(1 for row in rows if row.get("status") == "ready"),
        "needs_work": sum(1 for row in rows if row.get("status") != "ready"),
        "with_recent_memory": sum(1 for row in rows if int(row.get("recent_memory_events") or 0) > 0),
        "recent_memory_events": len(recent_events),
        "window_hours": int(window_hours or 24),
    }

    return {
        "organization_id": org_id,
        "contract": MEMORY_CONTRACT_VERSION,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "surfaces": rows,
    }
