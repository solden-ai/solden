"""Workspace-native records and exception queue endpoints.

These routes are thin aliases over the canonical AP item and Box-exception
services. They exist so the workspace SPA speaks in workspace vocabulary
(`/api/workspace/records`, `/api/workspace/exceptions`) instead of reaching
back through the Gmail extension or admin route names.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from solden.api.box_exceptions_admin import (
    _SEVERITY_RANK,
    _VALID_SEVERITIES,
    _assert_org_match,
    _gather_unresolved,
)
from solden.api.gmail_extension_common import resolve_org_id_for_user
from solden.core.auth import (
    TokenData,
    get_current_user,
    get_user_ap_role,
    has_ap_approver,
    has_ap_viewer,
    has_workspace_member,
    has_workspace_read_only,
    normalize_ap_role,
    normalize_workspace_role,
)
from solden.core.database import get_db
from solden.services.ap_item_service import build_worklist_item, build_worklist_items


router = APIRouter(prefix="/api/workspace", tags=["workspace-records"])


def _workspace_role(user: TokenData) -> str:
    return (
        normalize_workspace_role(getattr(user, "workspace_role", None))
        or normalize_workspace_role(getattr(user, "role", None))
        or ""
    )


def _ap_role(user: TokenData) -> str:
    db_role = get_user_ap_role(
        getattr(user, "user_id", None),
        getattr(user, "organization_id", None),
    )
    return db_role or normalize_ap_role(getattr(user, "role", None)) or ""


def _require_workspace_record_read(user: TokenData) -> None:
    workspace_role = _workspace_role(user)
    ap_role = _ap_role(user)
    if not has_workspace_read_only(workspace_role):
        raise HTTPException(status_code=403, detail="workspace_access_required")
    if not (has_workspace_member(workspace_role) or has_ap_viewer(ap_role)):
        raise HTTPException(status_code=403, detail="ap_record_access_required")


def _require_workspace_exception_write(user: TokenData) -> None:
    if not has_ap_approver(_ap_role(user)):
        raise HTTPException(status_code=403, detail="ap_manager_role_required")


@router.get("/records")
async def list_workspace_records(
    request: Request,
    organization_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=1000),
    user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the workspace AP record directory payload."""
    _require_workspace_record_read(user)
    org_id = resolve_org_id_for_user(user, organization_id)

    try:
        from solden.services.gmail_autopilot import ensure_gmail_autopilot_progress

        await ensure_gmail_autopilot_progress(
            request.app,
            user_id=str(getattr(user, "user_id", "") or "").strip(),
        )
    except Exception:
        pass

    db = get_db()
    items = db.list_ap_items(org_id, entity_id=entity_id, limit=limit, prioritized=True)
    normalized = build_worklist_items(db, items, build_item=build_worklist_item)
    return {
        "organization_id": org_id,
        "items": normalized,
        "total": len(normalized),
    }


@router.get("/exceptions")
def list_workspace_exceptions(
    box_type: Optional[str] = Query(None, description="Filter by box type (e.g. ap_item)"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    limit: int = Query(200, ge=1, le=500),
    user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the workspace unresolved-exception queue."""
    _require_workspace_record_read(user)
    if severity and severity not in _VALID_SEVERITIES:
        raise HTTPException(status_code=400, detail="invalid_severity")

    db = get_db()
    items = _gather_unresolved(db, user.organization_id, box_type=box_type, limit=limit)
    if severity:
        items = [row for row in items if str(row.get("severity")) == severity]
    items.sort(key=lambda r: (
        _SEVERITY_RANK.get(str(r.get("severity")), 99),
        str(r.get("raised_at") or ""),
    ))
    return {"items": items, "count": len(items)}


@router.get("/exceptions/stats")
def workspace_exception_stats(
    user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return exception counts for the workspace exception queue."""
    _require_workspace_record_read(user)
    db = get_db()
    items = _gather_unresolved(db, user.organization_id, limit=500)

    by_severity: Dict[str, int] = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    by_type: Dict[str, int] = {}
    by_box_type: Dict[str, int] = {}
    for row in items:
        sev = str(row.get("severity") or "medium")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        exc_type = str(row.get("exception_type") or "unknown")
        by_type[exc_type] = by_type.get(exc_type, 0) + 1
        box_type = str(row.get("box_type") or "unknown")
        by_box_type[box_type] = by_box_type.get(box_type, 0) + 1

    return {
        "total_unresolved": len(items),
        "by_severity": by_severity,
        "by_type": by_type,
        "by_box_type": by_box_type,
    }


@router.post("/exceptions/{exception_id}/resolve")
def resolve_workspace_exception(
    exception_id: str,
    body: Dict[str, Any] = Body(default_factory=dict),
    user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """Resolve a workspace exception after AP-approver authorization."""
    _require_workspace_exception_write(user)
    if str(exception_id or "").startswith("vos:"):
        raise HTTPException(
            status_code=400,
            detail={
                "reason": "synthetic_exception",
                "message": (
                    "Vendor onboarding signals resolve via the vendor "
                    "surface, not the exception queue. Open the vendor "
                    "record to advance or close the session."
                ),
                "vendor_session_id": exception_id[4:],
            },
        )

    db = get_db()
    existing = db.get_box_exception(exception_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="exception_not_found")
    _assert_org_match(user, existing.get("organization_id") or "")

    if existing.get("resolved_at"):
        return {"status": "already_resolved", "exception": existing}

    note = str(body.get("resolution_note") or "").strip()
    resolved = db.resolve_box_exception(
        exception_id,
        resolved_by=str(user.email or user.user_id or "workspace"),
        resolved_actor_type="user",
        resolution_note=note,
    )
    return {"status": "resolved", "exception": resolved}
