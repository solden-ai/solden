"""Purchase-order BoxType endpoints — the third Box surface.

Procurement is the first AP-*peer* workflow (bank_match was
AP-subordinate). These endpoints follow the same shape as the AP and
bank_match surfaces — read / list / create / typed action — on top of
the same audit + state-machine primitives, via the generic box-aware
store writers (``create_purchase_order_box`` /
``update_purchase_order_state``).

Endpoints:

    GET  /api/workspace/purchase-orders
    GET  /api/workspace/purchase-orders/{po_id}
    POST /api/workspace/purchase-orders
    POST /api/workspace/purchase-orders/{po_id}/{action}
         action in: submit | approve | reject | cancel | close

NOTE: any new path here MUST also be added to the strict-profile
allowlist in main.py or it 404s silently in production.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from solden.core.auth import get_current_user
from solden.core.database import get_db
from solden.core.purchase_order_states import (
    IllegalPurchaseOrderTransitionError,
)
from solden.services.purchase_orders import POStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspace", tags=["purchase-order"])


# Human approval-lifecycle transitions exposed on the API surface.
# The generic move_box_stage engine action covers the same edges for
# the autonomous path; these are the operator-driven entry points.
_PO_ACTIONS: Dict[str, str] = {
    "submit": POStatus.PENDING_APPROVAL.value,
    "approve": POStatus.APPROVED.value,
    "reject": POStatus.DRAFT.value,      # send back to the requester to revise
    "cancel": POStatus.CANCELLED.value,
    "close": POStatus.CLOSED.value,
}


def _session_org(user: Any) -> str:
    org = str(getattr(user, "organization_id", "") or "").strip()
    if not org:
        raise HTTPException(status_code=403, detail="user_missing_organization_id")
    return org


def _actor_id(user: Any) -> str:
    return str(getattr(user, "email", "") or getattr(user, "user_id", "") or "")


def _require_po(db: Any, po_id: str, organization_id: str) -> Dict[str, Any]:
    item = db.get_purchase_order(po_id) if hasattr(db, "get_purchase_order") else None
    if not item or str(item.get("organization_id") or "") != organization_id:
        raise HTTPException(status_code=404, detail="purchase_order_not_found")
    return item


class DecisionRequest(BaseModel):
    reason: str = Field("", max_length=2000)


class POCreateRequest(BaseModel):
    vendor_name: str = Field(..., max_length=512)
    vendor_id: str = Field("", max_length=256)
    po_number: str = Field("", max_length=128)
    total_amount: float = 0.0
    subtotal: float = 0.0
    tax_amount: float = 0.0
    currency: str = Field("", max_length=8)
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    notes: str = Field("", max_length=4000)
    department: str = Field("", max_length=256)
    project: str = Field("", max_length=256)
    expected_delivery: str = Field("", max_length=64)
    order_date: str = Field("", max_length=64)


@router.get("/purchase-orders")
def list_purchase_orders(_user=Depends(get_current_user)) -> Dict[str, Any]:
    organization_id = _session_org(_user)
    db = get_db()
    rows = db.list_purchase_orders(organization_id) if hasattr(db, "list_purchase_orders") else []
    return {"count": len(rows), "purchase_orders": rows}


@router.get("/purchase-orders/{po_id}")
def get_purchase_order(po_id: str, _user=Depends(get_current_user)) -> Dict[str, Any]:
    organization_id = _session_org(_user)
    db = get_db()
    return _require_po(db, po_id, organization_id)


@router.post("/purchase-orders")
def create_purchase_order(
    body: POCreateRequest,
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Create a PO Box in DRAFT, attributed to the requesting user."""
    organization_id = _session_org(_user)
    actor_id = _actor_id(_user)
    db = get_db()
    payload = {
        "po_id": f"PO-{uuid.uuid4().hex[:16]}",
        "organization_id": organization_id,
        "po_number": body.po_number,
        "vendor_id": body.vendor_id,
        "vendor_name": body.vendor_name,
        "order_date": body.order_date,
        "expected_delivery": body.expected_delivery,
        "line_items": body.line_items,
        "subtotal": body.subtotal,
        "tax_amount": body.tax_amount,
        "total_amount": body.total_amount,
        "currency": body.currency,
        "status": POStatus.DRAFT.value,
        "requested_by": actor_id,
        "notes": body.notes,
        "department": body.department,
        "project": body.project,
    }
    return db.create_purchase_order_box(payload)


def _advance(po_id: str, action: str, body: DecisionRequest, user: Any) -> Dict[str, Any]:
    """Shared driver for a PO approval-lifecycle transition.

    409 on an illegal edge (e.g. approving a draft, or any move out of
    a terminal state).

    NOTE: each transition is its own explicit endpoint below rather than
    a single ``/{action}`` route, because the strict-profile allowlist
    matches route *templates* — a ``/{action}`` template would not match
    the per-action regex and would be dropped in production.
    """
    organization_id = _session_org(user)
    target = _PO_ACTIONS[action]
    actor_id = _actor_id(user)
    db = get_db()
    _require_po(db, po_id, organization_id)
    try:
        return db.update_purchase_order_state(
            po_id, target, actor_id=actor_id, reason=body.reason.strip(),
        )
    except IllegalPurchaseOrderTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/purchase-orders/{po_id}/submit")
def submit_purchase_order(po_id: str, body: DecisionRequest, _user=Depends(get_current_user)) -> Dict[str, Any]:
    """DRAFT -> PENDING_APPROVAL."""
    return _advance(po_id, "submit", body, _user)


@router.post("/purchase-orders/{po_id}/approve")
def approve_purchase_order(po_id: str, body: DecisionRequest, _user=Depends(get_current_user)) -> Dict[str, Any]:
    """PENDING_APPROVAL -> APPROVED."""
    return _advance(po_id, "approve", body, _user)


@router.post("/purchase-orders/{po_id}/reject")
def reject_purchase_order(po_id: str, body: DecisionRequest, _user=Depends(get_current_user)) -> Dict[str, Any]:
    """PENDING_APPROVAL -> DRAFT (back to the requester to revise)."""
    return _advance(po_id, "reject", body, _user)


@router.post("/purchase-orders/{po_id}/cancel")
def cancel_purchase_order(po_id: str, body: DecisionRequest, _user=Depends(get_current_user)) -> Dict[str, Any]:
    """-> CANCELLED (terminal)."""
    return _advance(po_id, "cancel", body, _user)


@router.post("/purchase-orders/{po_id}/close")
def close_purchase_order(po_id: str, body: DecisionRequest, _user=Depends(get_current_user)) -> Dict[str, Any]:
    """-> CLOSED (terminal)."""
    return _advance(po_id, "close", body, _user)


# --- Non-transition actions (receive / issue / amend) -----------------
# These route through ProcurementFinanceSkill so they reuse the exact
# validated logic the agent uses (precheck, thresholds, ERP write,
# receipt reconciliation, audit) rather than duplicating it.

class ReceiveRequest(BaseModel):
    received_lines: Optional[List[Dict[str, Any]]] = None
    partial: bool = False
    reason: str = Field("", max_length=2000)


class AmendRequest(BaseModel):
    fields: Dict[str, Any] = Field(default_factory=dict)


async def _skill_action(po_id: str, intent: str, payload: Dict[str, Any], user: Any) -> Dict[str, Any]:
    organization_id = _session_org(user)
    actor_id = _actor_id(user)
    db = get_db()
    _require_po(db, po_id, organization_id)
    from solden.services.agent_command_dispatch import build_channel_runtime
    from solden.services.finance_skills.procurement_skill import ProcurementFinanceSkill

    runtime = build_channel_runtime(
        organization_id=organization_id,
        actor_id=actor_id,
        actor_email=str(getattr(user, "email", "") or actor_id),
        fallback_actor="user",
        actor_type="user",
    )
    result = await ProcurementFinanceSkill().execute(
        runtime, intent, {"po_id": po_id, **payload},
    )
    if str(result.get("status") or "") == "blocked":
        raise HTTPException(
            status_code=409,
            detail=result.get("policy_precheck") or result.get("error") or "blocked",
        )
    return result


@router.post("/purchase-orders/{po_id}/receive")
async def receive_purchase_order_route(po_id: str, body: ReceiveRequest, _user=Depends(get_current_user)) -> Dict[str, Any]:
    """Record a goods receipt -> partially/fully_received (per-line reconciliation)."""
    return await _skill_action(
        po_id, "receive_purchase_order",
        {"received_lines": body.received_lines, "partial": body.partial, "reason": body.reason.strip()},
        _user,
    )


@router.post("/purchase-orders/{po_id}/issue")
async def issue_purchase_order_route(po_id: str, body: DecisionRequest, _user=Depends(get_current_user)) -> Dict[str, Any]:
    """Issue an APPROVED PO to the ERP (stamps erp_po_id). Behind FEATURE_PROCUREMENT_ERP_WRITE."""
    return await _skill_action(po_id, "issue_purchase_order", {"reason": body.reason.strip()}, _user)


@router.post("/purchase-orders/{po_id}/amend")
async def amend_purchase_order_route(po_id: str, body: AmendRequest, _user=Depends(get_current_user)) -> Dict[str, Any]:
    """Edit a DRAFT PO's master-data fields."""
    return await _skill_action(po_id, "amend_purchase_order", {"fields": body.fields}, _user)
