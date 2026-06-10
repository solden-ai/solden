"""Sync ERP dimension masters into the dimension graph (H5 deepening).

The ERP's own masters (departments, classes, locations, tracking categories)
are the authoritative source for dimension reference data — importing them
makes dimensions confirmed-by-authority instead of inferred from per-record
values, and their parent refs build the hierarchy edges that power "all
records under EMEA" rollups.

Mapping is ERP-NATIVE: a NetSuite ``department`` becomes dimension_type
``department``, a ``classification``/QB ``Class`` becomes ``class``, a Xero
tracking category becomes ``tracking:<name>`` — we never guess that a "class"
is a cost center. Idempotent: re-sync upserts in place (UNIQUE constraints).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

_KIND_TO_DIMENSION_TYPE = {
    "department": "department",
    "classification": "class",
    "class": "class",
    "location": "location",
    "project": "project",
    # SAP B1 calls its cost-accounting centers "profit centers" — keep the
    # ERP-native name rather than guessing it means cost_center.
    "profit_center": "profit_center",
    # tracking:<name> kinds pass through verbatim.
}


def _dimension_type_for(kind: str) -> str:
    kind = str(kind or "").strip().lower()
    if kind.startswith("tracking:"):
        return kind
    return _KIND_TO_DIMENSION_TYPE.get(kind, kind or "unknown")


async def sync_dimensions_from_erp(db: Any, organization_id: str) -> Dict[str, Any]:
    """Two-pass import: upsert every master as a canonical dimension (pass 1,
    building an external-id -> dimension-id map), then build hierarchy edges
    from parent refs (pass 2). Returns counts for the operator."""
    from solden.integrations.erp_router import get_dimension_masters

    org_id = str(organization_id or "").strip()
    if not org_id:
        return {"erp_type": None, "fetched": 0, "upserted": 0, "edges": 0, "by_type": {}}

    result = await get_dimension_masters(org_id)
    masters = result.get("masters") or []
    erp_type = result.get("erp_type")

    upserted = 0
    edges = 0
    by_type: Dict[str, int] = {}
    # external-id map is per kind — different masters can reuse numeric ids.
    id_map: Dict[str, str] = {}

    for row in masters:
        kind = str(row.get("kind") or "")
        dimension_type = _dimension_type_for(kind)
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        dim = db.upsert_dimension(
            organization_id=org_id,
            dimension_type=dimension_type,
            code=code,
            label=str(row.get("name") or "") or None,
            source="erp_master",
            metadata={"external_id": str(row.get("external_id") or ""), "erp_type": erp_type},
        )
        if not dim:
            continue
        upserted += 1
        by_type[dimension_type] = by_type.get(dimension_type, 0) + 1
        external_id = str(row.get("external_id") or "")
        if external_id:
            id_map[f"{kind}:{external_id}"] = dim["id"]
        name = str(row.get("name") or "").strip()
        if name and name != code:
            db.add_dimension_alias(
                organization_id=org_id, dimension_id=dim["id"], alias=name
            )

    for row in masters:
        parent_external = str(row.get("parent_external_id") or "")
        external_id = str(row.get("external_id") or "")
        if not (parent_external and external_id):
            continue
        kind = str(row.get("kind") or "")
        child_id = id_map.get(f"{kind}:{external_id}")
        parent_id = id_map.get(f"{kind}:{parent_external}")
        if not (child_id and parent_id) or child_id == parent_id:
            continue
        try:
            if db.add_dimension_edge(
                organization_id=org_id,
                parent_dimension_id=parent_id,
                child_dimension_id=child_id,
                edge_type="hierarchy",
                source="erp_master",
            ):
                edges += 1
        except ValueError as exc:
            # Self-edge / cycle from a malformed master — skip, never fail the sync.
            logger.warning(
                "[dimension_sync] edge skipped for %s: %s", code_or(row), exc
            )

    return {
        "erp_type": erp_type,
        "fetched": len(masters),
        "upserted": upserted,
        "edges": edges,
        "by_type": by_type,
    }


def code_or(row: Dict[str, Any]) -> str:
    return str((row or {}).get("code") or (row or {}).get("external_id") or "?")
