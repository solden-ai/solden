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

from solden.core.auth import get_current_user
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
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Every record linked to one dimension — the "everything on CC 402" view.
    404 if the dimension is not in the caller's org (no existence leak)."""
    organization_id = _session_org(_user)
    db = get_db()
    dim = db.get_dimension(organization_id=organization_id, dimension_id=dimension_id)
    if not dim:
        raise HTTPException(status_code=404, detail="dimension_not_found")
    records = db.list_boxes_for_dimension(
        organization_id=organization_id, dimension_id=dimension_id
    )
    return {
        "organization_id": organization_id,
        "dimension": {
            "dimension_id": dim.get("id"),
            "dimension_type": dim.get("dimension_type"),
            "code": dim.get("code"),
            "label": dim.get("label"),
        },
        "records": records,
        "count": len(records),
    }
