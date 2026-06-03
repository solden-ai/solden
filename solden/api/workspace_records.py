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
    _attach_box_summaries,
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

_WORKSPACE_EXCEPTION_PAGE_SIZE = 50


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


def _sort_exception_rows(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return sorted(
        rows,
        key=lambda r: (
            _SEVERITY_RANK.get(str(r.get("severity")), 99),
            str(r.get("raised_at") or ""),
            str(r.get("id") or ""),
        ),
    )


def _row_matches_exception_filters(
    row: Dict[str, Any],
    *,
    severity: Optional[str] = None,
    exception_type: Optional[str] = None,
    q: Optional[str] = None,
) -> bool:
    if severity and str(row.get("severity") or "") != severity:
        return False
    if exception_type and str(row.get("exception_type") or "") != exception_type:
        return False

    query = str(q or "").strip().lower()
    if not query:
        return True
    summary = row.get("box_summary") or {}
    metadata = row.get("metadata") or {}
    haystack = " ".join(
        str(part or "")
        for part in (
            row.get("box_id"),
            row.get("box_type"),
            row.get("exception_type"),
            row.get("reason"),
            row.get("severity"),
            row.get("vendor_name"),
            summary.get("vendor_name"),
            summary.get("invoice_number"),
            summary.get("reference"),
            summary.get("po_number"),
            summary.get("bill_number"),
            metadata.get("vendor_name"),
            metadata.get("suggested_action"),
        )
    ).lower()
    return query in haystack


def _synthetic_workspace_exceptions(
    db,
    organization_id: str,
    *,
    box_type: Optional[str],
    severity: Optional[str],
    exception_type: Optional[str],
    q: Optional[str],
) -> list[Dict[str, Any]]:
    include_synthetic = box_type is None or box_type == "vendor_onboarding_session"
    if not include_synthetic:
        return []
    from solden.services.vendor_onboarding_exceptions import (
        synthesize_onboarding_exceptions,
    )

    rows = synthesize_onboarding_exceptions(db, organization_id)
    rows = [
        row for row in rows
        if _row_matches_exception_filters(
            row,
            severity=severity,
            exception_type=exception_type,
            q=q,
        )
    ]
    _attach_box_summaries(db, rows)
    return rows


_VALID_RECORD_SLICES = {
    "all",
    "all_open",
    "waiting_on_approval",
    "ready_to_post",
    "needs_info",
    "failed_post",
    "blocked_exception",
    "due_soon",
    "overdue",
}
_VALID_RECORD_SORTS = {
    "queue_age",
    "due_date",
    "amount",
    "updated_at",
    "approval_wait",
    "priority",
    "vendor",
    "state",
    "invoice",
}
_VALID_RECORD_DUE_FILTERS = {"all", "overdue", "due_7d", "no_due"}
_VALID_RECORD_BLOCKER_FILTERS = {
    "all",
    "entity",
    "approval",
    "info",
    "erp",
    "exception",
    "confidence",
    "budget",
    "po",
    "processing",
}
_VALID_RECORD_AMOUNT_FILTERS = {"all", "under_1k", "1k_10k", "over_10k"}
_VALID_RECORD_APPROVAL_AGE_FILTERS = {
    "all",
    "under_24h",
    "1d_3d",
    "over_3d",
}
_VALID_RECORD_ERP_STATUS_FILTERS = {
    "all",
    "ready",
    "failed",
    "connected",
    "posted",
    "not_connected",
}


def _normalize_record_param(value: Optional[str], default: str, valid: set[str]) -> str:
    normalized = str(value or default).strip().lower() or default
    return normalized if normalized in valid else default


@router.get("/records")
async def list_workspace_records(
    request: Request,
    organization_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    active_slice_id: str = Query(default="all_open"),
    q: Optional[str] = Query(None, description="Search vendor, reference, sender, PO, or record id"),
    vendor: Optional[str] = Query(None, description="Vendor name filter"),
    due: str = Query(default="all"),
    blocker: str = Query(default="all"),
    amount: str = Query(default="all"),
    approval_age: str = Query(default="all"),
    erp_status: str = Query(default="all"),
    sort_col: str = Query(default="queue_age"),
    sort_dir: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
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
    normalized_slice = _normalize_record_param(
        active_slice_id,
        "all_open",
        _VALID_RECORD_SLICES,
    )
    normalized_due = _normalize_record_param(due, "all", _VALID_RECORD_DUE_FILTERS)
    normalized_blocker = _normalize_record_param(
        blocker,
        "all",
        _VALID_RECORD_BLOCKER_FILTERS,
    )
    normalized_amount = _normalize_record_param(amount, "all", _VALID_RECORD_AMOUNT_FILTERS)
    normalized_approval_age = _normalize_record_param(
        approval_age,
        "all",
        _VALID_RECORD_APPROVAL_AGE_FILTERS,
    )
    normalized_erp_status = _normalize_record_param(
        erp_status,
        "all",
        _VALID_RECORD_ERP_STATUS_FILTERS,
    )
    normalized_sort_col = _normalize_record_param(
        sort_col,
        "queue_age",
        _VALID_RECORD_SORTS,
    )
    normalized_sort_dir = "asc" if str(sort_dir or "").strip().lower() == "asc" else "desc"

    if hasattr(db, "list_ap_items_page"):
        page = db.list_ap_items_page(
            org_id,
            entity_id=entity_id,
            active_slice_id=normalized_slice,
            q=q,
            vendor=vendor,
            due=normalized_due,
            blocker=normalized_blocker,
            amount=normalized_amount,
            approval_age=normalized_approval_age,
            erp_status=normalized_erp_status,
            sort_col=normalized_sort_col,
            sort_dir=normalized_sort_dir,
            limit=limit,
            offset=offset,
        )
        raw_items = list(page.get("items") or [])
        total = int(page.get("total") or 0)
        has_more = bool(page.get("has_more"))
    else:
        raw_items = db.list_ap_items(org_id, entity_id=entity_id, limit=limit, prioritized=True)
        total = len(raw_items)
        has_more = False

    items = raw_items
    normalized = build_worklist_items(db, items, build_item=build_worklist_item)
    if hasattr(db, "ap_record_slice_counts"):
        slice_counts = db.ap_record_slice_counts(org_id, entity_id=entity_id)
    else:
        slice_counts = {}
    return {
        "organization_id": org_id,
        "items": normalized,
        "total": total,
        "count": len(normalized),
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "slice_counts": slice_counts,
    }


@router.get("/exceptions")
def list_workspace_exceptions(
    box_type: Optional[str] = Query(None, description="Filter by box type (e.g. ap_item)"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    exception_type: Optional[str] = Query(None, description="Filter by exception type"),
    q: Optional[str] = Query(None, description="Search vendor, reference, reason, or record"),
    limit: int = Query(_WORKSPACE_EXCEPTION_PAGE_SIZE, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
    user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the workspace unresolved-exception queue."""
    _require_workspace_record_read(user)
    if severity and severity not in _VALID_SEVERITIES:
        raise HTTPException(status_code=400, detail="invalid_severity")

    db = get_db()
    synthetic_rows = _synthetic_workspace_exceptions(
        db,
        user.organization_id,
        box_type=box_type,
        severity=severity,
        exception_type=exception_type,
        q=q,
    )
    include_synthetic = bool(synthetic_rows)

    if hasattr(db, "list_unresolved_exceptions_page"):
        canonical_limit = limit
        canonical_offset = offset
        if include_synthetic:
            # Synthetic onboarding rows are few and not persisted in
            # box_exceptions. Fetch the canonical prefix needed to sort
            # a truthful combined slice, then apply the public offset
            # after merging synthetic + canonical rows.
            canonical_limit = max(limit, offset + limit)
            canonical_offset = 0
        page = db.list_unresolved_exceptions_page(
            user.organization_id,
            box_type=box_type,
            severity=severity,
            exception_type=exception_type,
            q=q,
            limit=canonical_limit,
            offset=canonical_offset,
        )
        canonical_items = list(page.get("items") or [])
        _attach_box_summaries(db, canonical_items)
        if include_synthetic:
            combined = _sort_exception_rows([*canonical_items, *synthetic_rows])
            total = int(page.get("total") or 0) + len(synthetic_rows)
            items = combined[offset:offset + limit]
        else:
            total = int(page.get("total") or 0)
            items = canonical_items
        return {
            "items": items,
            "count": len(items),
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < total,
        }

    # Compatibility fallback for test doubles that have not implemented
    # the paginated store method.
    items = _gather_unresolved(db, user.organization_id, box_type=box_type, limit=500)
    items = [
        row for row in items
        if _row_matches_exception_filters(
            row,
            severity=severity,
            exception_type=exception_type,
            q=q,
        )
    ]
    items = _sort_exception_rows(items)
    total = len(items)
    page_items = items[offset:offset + limit]
    return {
        "items": page_items,
        "count": len(page_items),
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(page_items) < total,
    }


@router.get("/exceptions/stats")
def workspace_exception_stats(
    user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return exception counts for the workspace exception queue."""
    _require_workspace_record_read(user)
    db = get_db()
    if hasattr(db, "unresolved_exception_stats"):
        stats = db.unresolved_exception_stats(user.organization_id)
    else:
        items = _gather_unresolved(db, user.organization_id, limit=500)
        stats = {
            "total_unresolved": 0,
            "by_severity": {"low": 0, "medium": 0, "high": 0, "critical": 0},
            "by_type": {},
            "by_box_type": {},
        }
        for row in items:
            sev = str(row.get("severity") or "medium")
            exc_type = str(row.get("exception_type") or "unknown")
            row_box_type = str(row.get("box_type") or "unknown")
            stats["total_unresolved"] += 1
            stats["by_severity"][sev] = stats["by_severity"].get(sev, 0) + 1
            stats["by_type"][exc_type] = stats["by_type"].get(exc_type, 0) + 1
            stats["by_box_type"][row_box_type] = stats["by_box_type"].get(row_box_type, 0) + 1

    synthetic_rows = _synthetic_workspace_exceptions(
        db,
        user.organization_id,
        box_type=None,
        severity=None,
        exception_type=None,
        q=None,
    )
    if synthetic_rows:
        stats = {
            "total_unresolved": int(stats.get("total_unresolved") or 0),
            "by_severity": dict(stats.get("by_severity") or {}),
            "by_type": dict(stats.get("by_type") or {}),
            "by_box_type": dict(stats.get("by_box_type") or {}),
        }
        for row in synthetic_rows:
            sev = str(row.get("severity") or "medium")
            exc_type = str(row.get("exception_type") or "unknown")
            row_box_type = str(row.get("box_type") or "unknown")
            stats["total_unresolved"] += 1
            stats["by_severity"][sev] = stats["by_severity"].get(sev, 0) + 1
            stats["by_type"][exc_type] = stats["by_type"].get(exc_type, 0) + 1
            stats["by_box_type"][row_box_type] = stats["by_box_type"].get(row_box_type, 0) + 1
    return stats


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

    # Same human-rationale gate as the admin route. System/agent auto-clears
    # bypass this route and call the store directly.
    note = str(body.get("resolution_note") or "").strip()
    if not note:
        raise HTTPException(
            status_code=400,
            detail={
                "reason": "resolution_rationale_required",
                "message": (
                    "Add a short note explaining how this exception was "
                    "resolved before clearing it."
                ),
            },
        )
    resolved = db.resolve_box_exception(
        exception_id,
        resolved_by=str(user.email or user.user_id or "workspace"),
        resolved_actor_type="user",
        resolution_note=note,
    )
    return {"status": "resolved", "exception": resolved}
