"""Dimension rollup read API — the cross-system query surface (H5).

Lists the canonical dimensions an org has (GL accounts, cost centers, projects,
departments) and, for any one, every record linked to it: the "everything
charged to GL 5210 / CC 402" view. Read-only; the graph is written by the
capture loop via ``dimension_resolver``. Tenant-scoped: a dimension in another
org returns 404 (no existence leak).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from solden.core.auth import get_current_user, require_workspace_admin
from solden.core.database import get_db

router = APIRouter(prefix="/api/workspace", tags=["dimensions"])


def _session_org(user: Any) -> str:
    org = str(getattr(user, "organization_id", "") or "").strip()
    if not org:
        raise HTTPException(status_code=403, detail="user_missing_organization_id")
    return org


@router.get("/dimensions")
def list_dimensions(
    dimension_type: Optional[str] = Query(default=None, alias="type"),
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """List the org's canonical dimensions, optionally filtered by ``?type=``
    (gl_account / cost_center / project / department)."""
    organization_id = _session_org(_user)
    db = get_db()
    dims = db.list_dimensions(
        organization_id=organization_id, dimension_type=dimension_type or None
    )
    return {
        "organization_id": organization_id,
        "type": dimension_type or None,
        "dimensions": dims,
        "count": len(dims),
    }


@router.get("/dimensions/{dimension_id}/records")
def list_dimension_records(
    dimension_id: str,
    include_descendants: bool = Query(default=False),
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Every record linked to one dimension — the "everything on CC 402" view.
    With ``include_descendants``, also every record anywhere under it in the
    hierarchy ("all records under EMEA"). 404 if the dimension is not in the
    caller's org (no existence leak)."""
    organization_id = _session_org(_user)
    db = get_db()
    dim = db.get_dimension(organization_id=organization_id, dimension_id=dimension_id)
    if not dim:
        raise HTTPException(status_code=404, detail="dimension_not_found")
    descendant_ids = (
        db.list_descendant_dimension_ids(
            organization_id=organization_id, dimension_id=dimension_id
        )
        if include_descendants else []
    )
    records = db.list_boxes_for_dimension(
        organization_id=organization_id,
        dimension_id=dimension_id,
        include_descendants=include_descendants,
    )
    return {
        "organization_id": organization_id,
        "dimension": {
            "dimension_id": dim.get("id"),
            "dimension_type": dim.get("dimension_type"),
            "code": dim.get("code"),
            "label": dim.get("label"),
        },
        "include_descendants": include_descendants,
        "descendant_dimension_ids": descendant_ids,
        "records": records,
        "count": len(records),
    }


@router.get("/dimensions/{dimension_id}/memory")
def get_dimension_memory(
    dimension_id: str,
    include_descendants: bool = Query(default=True),
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """The dimension as a memory object — "tell me about CC 402": linked
    records (states, currency totals), decision counts with the recent real
    whys, open exceptions, the standing rules that touch it, and its place in
    the hierarchy."""
    from solden.services.dimension_memory import build_dimension_memory

    organization_id = _session_org(_user)
    db = get_db()
    memory = build_dimension_memory(
        db,
        organization_id=organization_id,
        dimension_id=dimension_id,
        include_descendants=include_descendants,
    )
    if memory is None:
        raise HTTPException(status_code=404, detail="dimension_not_found")
    return {"organization_id": organization_id, **memory}


@router.post("/dimensions/sync-erp")
async def sync_dimensions_erp(
    _user=Depends(require_workspace_admin),
) -> Dict[str, Any]:
    """Import the org's ERP dimension masters (departments / classes /
    locations / tracking categories) as canonical dimensions + hierarchy
    edges. Admin-gated: writes org-wide reference data. Idempotent."""
    from solden.services.dimension_sync import sync_dimensions_from_erp

    organization_id = _session_org(_user)
    db = get_db()
    result = await sync_dimensions_from_erp(db, organization_id)
    return {"organization_id": organization_id, **result}
