"""Provider-neutral ERP memory surface.

NetSuite, SAP, and Sage Intacct have host-native panels in this repo. API-first
ERPs such as QuickBooks, Xero, and Sage Accounting do not expose the same
in-record iframe surface, but they still need the same Solden memory contract:
resolve an ERP record to a work item, return the live operational memory, and
dispatch decisions with a provider-specific source surface.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from solden.core.auth import get_current_user
from solden.core.database import get_db as _get_db
from solden.core.org_utils import require_org
from solden.services.operational_memory import build_box_operational_memory_record

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extension", tags=["erp-memory-surface"])

_ERP_SURFACE_ALIASES = {
    "quickbooks": "quickbooks",
    "qbo": "quickbooks",
    "xero": "xero",
    "sage-accounting": "sage_accounting",
    "sage_accounting": "sage_accounting",
    "sage-business-cloud-accounting": "sage_accounting",
    "sage_intacct": "sage_intacct",
    "sage-intacct": "sage_intacct",
    "netsuite": "netsuite",
    "sap": "sap",
    "sap-b1": "sap",
    "sap_s4hana": "sap",
    "sap-s4hana": "sap",
}

_SOURCE_CHANNELS = {
    "quickbooks": "erp_native_quickbooks",
    "xero": "erp_native_xero",
    "sage_accounting": "erp_native_sage_accounting",
    "sage_intacct": "erp_native_sage_intacct",
    "netsuite": "erp_native_netsuite",
    "sap": "erp_native_sap",
}


class ErpMemorySurfaceActionRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=4000)
    idempotency_key: Optional[str] = Field(default=None, max_length=200)
    organization_id: Optional[str] = Field(default=None, max_length=120)


def _normalize_erp_type(erp_type: str) -> str:
    normalized = str(erp_type or "").strip().lower()
    normalized = normalized.replace(" ", "-")
    resolved = _ERP_SURFACE_ALIASES.get(normalized)
    if not resolved:
        raise HTTPException(
            status_code=404,
            detail={"reason": "unsupported_erp_memory_surface", "erp_type": erp_type},
        )
    return resolved


def _session_org(user: Any, requested_org_id: Optional[str] = None) -> str:
    org_id = str(requested_org_id or getattr(user, "organization_id", "") or "").strip()
    user_org = str(getattr(user, "organization_id", "") or "").strip()
    if not user_org:
        raise HTTPException(status_code=403, detail="user_missing_organization_id")
    if org_id != user_org:
        raise HTTPException(status_code=403, detail="org_mismatch")
    return org_id


def _dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _item_erp_type(item: Dict[str, Any]) -> str:
    metadata = _dict(item.get("metadata"))
    for value in (
        item.get("erp_type"),
        item.get("erp_connection_type"),
        metadata.get("erp_type"),
        metadata.get("posted_erp_type"),
        metadata.get("source_erp_type"),
    ):
        text = str(value or "").strip().lower()
        if text:
            return _ERP_SURFACE_ALIASES.get(text.replace(" ", "-"), text)
    return ""


def _require_item_for_erp_reference(
    *,
    db: Any,
    organization_id: str,
    erp_type: str,
    erp_reference: str,
) -> Dict[str, Any]:
    reference = str(erp_reference or "").strip()
    if not reference:
        raise HTTPException(status_code=400, detail="erp_reference_required")
    item = None
    if hasattr(db, "get_ap_item_by_erp_reference"):
        item = db.get_ap_item_by_erp_reference(organization_id, reference)
    if not item:
        raise HTTPException(
            status_code=404,
            detail={
                "reason": "no_solden_item_for_erp_reference",
                "erp_type": erp_type,
                "erp_reference": reference,
            },
        )
    item_erp_type = _item_erp_type(item)
    if item_erp_type and item_erp_type != erp_type:
        raise HTTPException(
            status_code=404,
            detail={
                "reason": "erp_reference_belongs_to_different_erp",
                "erp_type": erp_type,
                "record_erp_type": item_erp_type,
            },
        )
    return item


def _build_memory_response(
    *,
    db: Any,
    item: Dict[str, Any],
    erp_type: str,
    erp_reference: str,
) -> Dict[str, Any]:
    ap_item_id = str(item.get("id") or "").strip()
    timeline: list = []
    try:
        from solden.services.ap_operator_audit import normalize_operator_audit_events

        timeline = normalize_operator_audit_events(db.list_ap_audit_events(ap_item_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("erp_memory_surface: timeline fetch failed for %s: %s", ap_item_id, exc)

    exceptions: list = []
    if hasattr(db, "list_box_exceptions"):
        try:
            exceptions = db.list_box_exceptions(box_type="ap_item", box_id=ap_item_id)
        except Exception:
            exceptions = []

    outcome = None
    if hasattr(db, "get_box_outcome"):
        try:
            outcome = db.get_box_outcome(box_type="ap_item", box_id=ap_item_id)
        except Exception:
            outcome = None

    memory = build_box_operational_memory_record(
        db=db,
        box_type="ap_item",
        box_id=ap_item_id,
        item=item,
        timeline=timeline,
        exceptions=exceptions,
        outcome=outcome,
    )
    return {
        "ap_item_id": ap_item_id,
        "box_id": ap_item_id,
        "box_type": "ap_item",
        "state": item.get("state"),
        "summary": {
            "vendor_name": item.get("vendor_name"),
            "amount": item.get("amount"),
            "currency": item.get("currency"),
            "invoice_number": item.get("invoice_number"),
            "due_date": item.get("due_date"),
        },
        "memory": memory,
        "operational_memory": memory,
        "decision_ledger": memory.get("decision_ledger") or [],
        "timeline": timeline,
        "exceptions": exceptions,
        "outcome": outcome,
        "erp_type": erp_type,
        "erp_reference": erp_reference,
        "surface": {
            "source_channel": _SOURCE_CHANNELS[erp_type],
            "contract": "erp_memory_surface.v1",
        },
    }


@router.get("/ap-items/by-erp-reference/{erp_type}/{erp_reference}")
def get_ap_item_by_erp_reference_surface(
    erp_type: str,
    erp_reference: str,
    user=Depends(get_current_user),
) -> Dict[str, Any]:
    resolved_erp_type = _normalize_erp_type(erp_type)
    organization_id = _session_org(user)
    db = _get_db()
    item = _require_item_for_erp_reference(
        db=db,
        organization_id=organization_id,
        erp_type=resolved_erp_type,
        erp_reference=erp_reference,
    )
    require_org(user, requested=item.get("organization_id"))
    return _build_memory_response(
        db=db,
        item=item,
        erp_type=resolved_erp_type,
        erp_reference=erp_reference,
    )


async def _dispatch_erp_memory_surface_action(
    *,
    intent: str,
    erp_type: str,
    erp_reference: str,
    request: ErpMemorySurfaceActionRequest,
    user: Any,
    default_reason: str,
) -> Dict[str, Any]:
    from solden.services.agent_command_dispatch import (
        build_channel_runtime,
        dispatch_runtime_intent,
    )

    resolved_erp_type = _normalize_erp_type(erp_type)
    organization_id = _session_org(user, request.organization_id)
    db = _get_db()
    item = _require_item_for_erp_reference(
        db=db,
        organization_id=organization_id,
        erp_type=resolved_erp_type,
        erp_reference=erp_reference,
    )
    require_org(user, requested=item.get("organization_id"))

    ap_item_id = str(item.get("id") or "").strip()
    actor_id = str(getattr(user, "user_id", "") or getattr(user, "email", "") or "erp_memory_surface")
    actor_email = str(getattr(user, "email", "") or actor_id)
    source_channel = _SOURCE_CHANNELS[resolved_erp_type]
    runtime = build_channel_runtime(
        organization_id=organization_id,
        actor_id=actor_id,
        actor_email=actor_email,
        db=db,
        fallback_actor="erp_memory_surface",
    )
    reason_text = (request.reason or default_reason or "").strip() or None
    payload = {
        "ap_item_id": ap_item_id,
        "email_id": str(item.get("thread_id") or item.get("message_id") or ap_item_id),
        "reason": reason_text,
        "source_channel": source_channel,
        "source_channel_id": resolved_erp_type,
        "source_message_ref": erp_reference,
        "actor_id": actor_id,
        "actor_email": actor_email,
        "actor_display": actor_email,
    }
    try:
        result = await dispatch_runtime_intent(
            runtime,
            intent,
            payload,
            idempotency_key=request.idempotency_key,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "erp_memory_surface_action_failed: erp=%s ref=%s intent=%s err=%s",
            resolved_erp_type,
            erp_reference,
            intent,
            exc,
        )
        raise HTTPException(status_code=500, detail="erp_memory_surface: action dispatch failed")

    return {
        "ap_item_id": ap_item_id,
        "erp_type": resolved_erp_type,
        "erp_reference": erp_reference,
        "source_channel": source_channel,
        "intent": intent,
        "result": result,
    }


@router.post("/ap-items/by-erp-reference/{erp_type}/{erp_reference}/approve")
async def approve_erp_reference(
    erp_type: str,
    erp_reference: str,
    body: ErpMemorySurfaceActionRequest = Body(default_factory=ErpMemorySurfaceActionRequest),
    user=Depends(get_current_user),
) -> Dict[str, Any]:
    return await _dispatch_erp_memory_surface_action(
        intent="approve_invoice",
        erp_type=erp_type,
        erp_reference=erp_reference,
        request=body,
        user=user,
        default_reason=f"approved_in_{_normalize_erp_type(erp_type)}_surface",
    )


@router.post("/ap-items/by-erp-reference/{erp_type}/{erp_reference}/reject")
async def reject_erp_reference(
    erp_type: str,
    erp_reference: str,
    body: ErpMemorySurfaceActionRequest = Body(default_factory=ErpMemorySurfaceActionRequest),
    user=Depends(get_current_user),
) -> Dict[str, Any]:
    return await _dispatch_erp_memory_surface_action(
        intent="reject_invoice",
        erp_type=erp_type,
        erp_reference=erp_reference,
        request=body,
        user=user,
        default_reason=f"rejected_in_{_normalize_erp_type(erp_type)}_surface",
    )


@router.post("/ap-items/by-erp-reference/{erp_type}/{erp_reference}/request-info")
async def request_info_erp_reference(
    erp_type: str,
    erp_reference: str,
    body: ErpMemorySurfaceActionRequest = Body(default_factory=ErpMemorySurfaceActionRequest),
    user=Depends(get_current_user),
) -> Dict[str, Any]:
    return await _dispatch_erp_memory_surface_action(
        intent="request_info",
        erp_type=erp_type,
        erp_reference=erp_reference,
        request=body,
        user=user,
        default_reason=f"info_requested_from_{_normalize_erp_type(erp_type)}_surface",
    )
