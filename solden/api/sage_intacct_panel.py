"""Backend endpoint for the Sage Intacct Platform Services panel.

Sage Intacct's Platform Services can host custom pages. The hosted
Solden page under ``integrations/sage-intacct-platform-app/`` calls this
endpoint with the APBILL ``RECORDNO`` and a short-lived HMAC JWT minted
from the tenant's Sage Intacct connection secret.

This is intentionally separate from Sage Business Cloud Accounting. Sage
Accounting is an OAuth REST connector in this repo; it does not have an
equivalent in-record Platform Services host surface.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from solden.core.auth import TokenData
from solden.core.database import get_db as _get_db
from solden.core.org_utils import require_org
from solden.services.operational_memory import build_box_operational_memory_record

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extension", tags=["sage-intacct-panel"])
_security = HTTPBearer(auto_error=False)

SAGE_INTACCT_PANEL_SOURCE_CHANNEL = "erp_native_sage_intacct"


def _b64url_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def _verify_panel_jwt(token: str, secret: str) -> Optional[Dict[str, Any]]:
    """Verify a Sage Intacct panel JWT signed with HS256."""
    if not token or not secret:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        logger.warning("sage_intacct_panel_jwt: malformed")
        return None
    header_b64, payload_b64, signature_b64 = parts
    try:
        signing_input = (header_b64 + "." + payload_b64).encode("ascii")
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        signature = _b64url_decode(signature_b64)
        if not hmac.compare_digest(expected, signature):
            logger.warning("sage_intacct_panel_jwt: signature mismatch")
            return None
        header = json.loads(_b64url_decode(header_b64))
        if header.get("alg") != "HS256":
            logger.warning("sage_intacct_panel_jwt: unsupported alg=%r", header.get("alg"))
            return None
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as exc:  # noqa: BLE001
        logger.warning("sage_intacct_panel_jwt: decode failed (%s)", exc)
        return None
    if payload.get("iss") != "solden-sage-intacct-platform-app":
        logger.warning("sage_intacct_panel_jwt: invalid iss=%r", payload.get("iss"))
        return None
    if payload.get("aud") != "solden-sage-intacct-panel":
        logger.warning("sage_intacct_panel_jwt: invalid aud=%r", payload.get("aud"))
        return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        logger.warning("sage_intacct_panel_jwt: missing/invalid exp")
        return None
    if datetime.now(timezone.utc).timestamp() >= float(exp):
        logger.warning("sage_intacct_panel_jwt: expired")
        return None
    return payload


def _candidate_org_ids(db: Any) -> list[str]:
    try:
        rows = db.list_organizations()
    except Exception:
        return []
    return [
        rid
        for rid in (str(row.get("id") or "").strip() for row in (rows or []) if row)
        if rid
    ]


def _connection_credentials(row: Dict[str, Any]) -> Dict[str, Any]:
    creds = row.get("credentials") or {}
    if isinstance(creds, str):
        try:
            creds = json.loads(creds)
        except Exception:
            creds = {}
    return creds if isinstance(creds, dict) else {}


def _resolve_org_for_company_id(db: Any, company_id: str) -> Optional[str]:
    normalized = str(company_id or "").strip().lower()
    if not normalized:
        return None
    for org_id in _candidate_org_ids(db):
        try:
            connections = db.get_erp_connections(org_id)
        except Exception:
            continue
        for row in connections or []:
            if str(row.get("erp_type") or "").lower() != "sage_intacct":
                continue
            creds = _connection_credentials(row)
            candidate = str(
                creds.get("company_id")
                or row.get("company_id")
                or ""
            ).strip().lower()
            if candidate and candidate == normalized:
                return org_id
    return None


def _resolve_panel_user(
    credentials: Optional[HTTPAuthorizationCredentials],
    company_id: str,
    record_no: str,
) -> TokenData:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="sage_intacct_panel: missing bearer token")
    db = _get_db()
    org_id = _resolve_org_for_company_id(db, company_id)
    if not org_id:
        raise HTTPException(
            status_code=401,
            detail="sage_intacct_panel: company_id has no active Sage Intacct connection",
        )
    try:
        connections = db.get_erp_connections(org_id)
    except Exception:
        connections = []
    conn = next(
        (row for row in connections if str(row.get("erp_type") or "").lower() == "sage_intacct"),
        None,
    )
    creds = _connection_credentials(conn or {})
    panel_secret = str(
        creds.get("panel_secret")
        or creds.get("webhook_secret")
        or ""
    ).strip()
    if not panel_secret:
        raise HTTPException(
            status_code=401,
            detail="sage_intacct_panel: tenant has no panel_secret provisioned",
        )
    payload = _verify_panel_jwt(credentials.credentials.strip(), panel_secret)
    if not payload:
        raise HTTPException(status_code=401, detail="sage_intacct_panel: invalid or expired token")
    if str(payload.get("recordNo") or "") != str(record_no):
        raise HTTPException(status_code=401, detail="sage_intacct_panel: record_no mismatch in JWT")
    if str(payload.get("companyId") or "").strip().lower() != str(company_id or "").strip().lower():
        raise HTTPException(status_code=401, detail="sage_intacct_panel: company_id mismatch in JWT")
    if payload.get("organizationId") and str(payload.get("organizationId")) != org_id:
        raise HTTPException(status_code=401, detail="sage_intacct_panel: organization mismatch in JWT")

    user_email = str(payload.get("userEmail") or "").strip().lower()
    user_id = "sage_intacct_panel"
    if user_email:
        try:
            user_row = db.get_user_by_email(user_email)
            if user_row and str(user_row.get("organization_id") or "").strip() == org_id:
                user_id = str(user_row.get("id") or user_id)
        except Exception:
            pass
    return TokenData(
        user_id=user_id,
        email=user_email or f"sage-intacct-panel@{company_id}",
        organization_id=org_id,
        role="sage_intacct_panel",
        exp=datetime.now(timezone.utc),
    )


@router.get("/ap-items/by-sage-intacct-bill/{record_no}")
def get_ap_item_by_sage_intacct_bill(
    record_no: str,
    company_id: str = Query(..., min_length=1, description="Sage Intacct company ID"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> Dict[str, Any]:
    """Return the Solden Box linked to a Sage Intacct APBILL record."""
    user = _resolve_panel_user(credentials, company_id, record_no)
    db = _get_db()
    item = db.get_ap_item_by_erp_reference(user.organization_id, record_no)
    if not item:
        raise HTTPException(
            status_code=404,
            detail={"reason": "no_solden_item_for_sage_intacct_bill", "record_no": record_no},
        )
    require_org(user, requested=item.get("organization_id"))
    ap_item_id = str(item.get("id") or "").strip()

    timeline = []
    try:
        from solden.services.ap_operator_audit import normalize_operator_audit_events
        timeline = normalize_operator_audit_events(db.list_ap_audit_events(ap_item_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("sage_intacct_panel: timeline fetch failed for %s — %s", ap_item_id, exc)

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
        "decision_ledger": memory.get("decision_ledger") or [],
        "timeline": timeline,
        "exceptions": exceptions,
        "outcome": outcome,
        "record_no": record_no,
        "company_id": company_id,
    }


class SageIntacctPanelActionRequest(BaseModel):
    """Body for POST actions from the Sage Intacct APBILL panel."""

    reason: Optional[str] = Field(default=None, max_length=4000)
    idempotency_key: Optional[str] = Field(default=None, max_length=200)


async def _dispatch_sage_intacct_panel_action(
    *,
    intent: str,
    record_no: str,
    company_id: str,
    credentials: Optional[HTTPAuthorizationCredentials],
    request: SageIntacctPanelActionRequest,
    default_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Dispatch an AP action from inside the Sage Intacct panel."""
    from solden.services.agent_command_dispatch import (
        build_channel_runtime,
        dispatch_runtime_intent,
    )

    user = _resolve_panel_user(credentials, company_id, record_no)
    db = _get_db()
    item = db.get_ap_item_by_erp_reference(user.organization_id, record_no)
    if not item:
        raise HTTPException(
            status_code=404,
            detail={"reason": "no_solden_item_for_sage_intacct_bill", "record_no": record_no},
        )
    require_org(user, requested=item.get("organization_id"))
    ap_item_id = str(item.get("id") or "").strip()

    actor_id = user.user_id or user.email or "sage_intacct_panel"
    actor_email = user.email or actor_id
    runtime = build_channel_runtime(
        organization_id=user.organization_id,
        actor_id=actor_id,
        actor_email=actor_email,
        db=db,
        fallback_actor="sage_intacct_panel",
    )
    reason_text = (request.reason or default_reason or "").strip() or None
    payload = {
        "ap_item_id": ap_item_id,
        "email_id": str(item.get("thread_id") or item.get("message_id") or ap_item_id),
        "reason": reason_text,
        "source_channel": SAGE_INTACCT_PANEL_SOURCE_CHANNEL,
        "source_channel_id": company_id,
        "source_message_ref": record_no,
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
            "sage_intacct_panel_action_failed: intent=%s ap_item_id=%s err=%s",
            intent,
            ap_item_id,
            exc,
        )
        raise HTTPException(status_code=500, detail="sage_intacct_panel: action dispatch failed")

    return {
        "ap_item_id": ap_item_id,
        "record_no": record_no,
        "company_id": company_id,
        "intent": intent,
        "result": result,
    }


@router.post("/ap-items/by-sage-intacct-bill/{record_no}/approve")
async def approve_sage_intacct_bill(
    record_no: str,
    company_id: str = Query(..., min_length=1, description="Sage Intacct company ID"),
    body: SageIntacctPanelActionRequest = Body(default_factory=SageIntacctPanelActionRequest),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> Dict[str, Any]:
    return await _dispatch_sage_intacct_panel_action(
        intent="approve_invoice",
        record_no=record_no,
        company_id=company_id,
        credentials=credentials,
        request=body,
        default_reason="approved_in_sage_intacct_panel",
    )


@router.post("/ap-items/by-sage-intacct-bill/{record_no}/reject")
async def reject_sage_intacct_bill(
    record_no: str,
    company_id: str = Query(..., min_length=1, description="Sage Intacct company ID"),
    body: SageIntacctPanelActionRequest = Body(default_factory=SageIntacctPanelActionRequest),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> Dict[str, Any]:
    return await _dispatch_sage_intacct_panel_action(
        intent="reject_invoice",
        record_no=record_no,
        company_id=company_id,
        credentials=credentials,
        request=body,
        default_reason="rejected_in_sage_intacct_panel",
    )


@router.post("/ap-items/by-sage-intacct-bill/{record_no}/request-info")
async def request_info_sage_intacct_bill(
    record_no: str,
    company_id: str = Query(..., min_length=1, description="Sage Intacct company ID"),
    body: SageIntacctPanelActionRequest = Body(default_factory=SageIntacctPanelActionRequest),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> Dict[str, Any]:
    return await _dispatch_sage_intacct_panel_action(
        intent="request_info",
        record_no=record_no,
        company_id=company_id,
        credentials=credentials,
        request=body,
        default_reason="info_requested_from_sage_intacct_panel",
    )
