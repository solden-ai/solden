"""Resolve the cross-system dimensions (GL account / cost center) a record
references, and link them into the dimension graph.

Called best-effort from the operational-memory capture loop, so a record's
memory carries the accounting objects it touches ("everything charged to GL
5210"). See docs/ENTITY_GRAPH_SCOPING.md (H5).

Data reality (Phase 1): the per-record GL value is a *code*
(`ap_items.metadata.gl_code` etc.), which is authoritative — a known code links
``confirmed``, an unknown code seeds a new dimension + links ``confirmed`` (the
record IS coded to it). Fuzzy matching runs ONLY on free-text labels (values
with a space), never on numeric codes, or "5211" would fuzzy-match "5210".
Cost center is usually absent on ap_items today, so its links stay sparse until
extraction populates it.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from solden.services.vendor_attribute_matcher import vendor_name_similarity

logger = logging.getLogger(__name__)

# Same bands the operational-memory capture linker uses.
_FUZZY_CONFIRM = 0.90
_FUZZY_PROPOSE = 0.72


def _first_str(*vals: Any) -> str:
    for v in vals:
        s = str(v or "").strip()
        if s:
            return s
    return ""


def _meta(item: Dict[str, Any]) -> Dict[str, Any]:
    m = item.get("metadata")
    if isinstance(m, str):
        try:
            m = json.loads(m or "{}")
        except Exception:
            m = {}
    return m if isinstance(m, dict) else {}


def _gl_value(item: Dict[str, Any], meta: Dict[str, Any]) -> str:
    posting = meta.get("posting_metadata") if isinstance(meta.get("posting_metadata"), dict) else {}
    return _first_str(
        item.get("gl_code"), meta.get("gl_code"),
        meta.get("suggested_gl_code"), posting.get("gl_account"),
    )


def _gl_label(item: Dict[str, Any], meta: Dict[str, Any]) -> Optional[str]:
    posting = meta.get("posting_metadata") if isinstance(meta.get("posting_metadata"), dict) else {}
    return _first_str(
        meta.get("gl_account_name"), meta.get("account_name"), posting.get("gl_account_name"),
    ) or None


def _cost_center_value(item: Dict[str, Any], meta: Dict[str, Any]) -> str:
    return _first_str(item.get("cost_center"), meta.get("cost_center"))


def _link_for(
    db: Any,
    *,
    organization_id: str,
    box_type: str,
    box_id: str,
    dimension_type: str,
    raw_value: str,
    label: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve one (type, value) to a dimension and link it.

    Ladder: deterministic (exact/alias/normalized) -> for free-text values only,
    fuzzy against labels with the propose/confirm bands -> else seed a new
    canonical dimension (the record's own coding is authoritative) + confirm.
    """
    raw = str(raw_value or "").strip()
    if not raw:
        return None

    hit = db.resolve_dimension(
        organization_id=organization_id, dimension_type=dimension_type, raw_code=raw
    )
    if hit:
        db.link_dimension(
            organization_id=organization_id, box_type=box_type, box_id=box_id,
            dimension_id=hit["id"], confidence=1.0, status="confirmed", source="resolver",
        )
        return {"dimension_id": hit["id"], "status": "confirmed", "match": hit.get("_match_kind")}

    # Fuzzy only for free-text labels (a value with a space). Numeric/short codes
    # are matched deterministically above; fuzzing them mis-links near-codes.
    if " " in raw:
        best: Optional[Dict[str, Any]] = None
        best_sim = 0.0
        for cand in db.list_dimensions(organization_id=organization_id, dimension_type=dimension_type):
            for target in (cand.get("label"), cand.get("code")):
                if not target:
                    continue
                sim = vendor_name_similarity(raw, str(target))
                if sim > best_sim:
                    best, best_sim = cand, sim
        if best and best_sim >= _FUZZY_CONFIRM:
            db.link_dimension(
                organization_id=organization_id, box_type=box_type, box_id=box_id,
                dimension_id=best["id"], confidence=round(best_sim, 3),
                status="confirmed", source="resolver_fuzzy",
            )
            return {"dimension_id": best["id"], "status": "confirmed", "match": "fuzzy"}
        if best and best_sim >= _FUZZY_PROPOSE:
            db.link_dimension(
                organization_id=organization_id, box_type=box_type, box_id=box_id,
                dimension_id=best["id"], confidence=round(best_sim, 3),
                status="proposed", source="resolver_fuzzy",
            )
            return {"dimension_id": best["id"], "status": "proposed", "match": "fuzzy"}

    # Brand-new value: the record's own coding is authoritative, so seed + confirm.
    seeded = db.upsert_dimension(
        organization_id=organization_id, dimension_type=dimension_type,
        code=raw, label=label, source="inferred",
    )
    if not seeded:
        return None
    db.link_dimension(
        organization_id=organization_id, box_type=box_type, box_id=box_id,
        dimension_id=seeded["id"], confidence=1.0, status="confirmed", source="resolver",
    )
    return {"dimension_id": seeded["id"], "status": "confirmed", "match": "seeded"}


def resolve_dimensions_for_box(
    db: Any,
    *,
    box_type: str,
    box_id: str,
    item: Optional[Dict[str, Any]],
    organization_id: str,
) -> List[Dict[str, Any]]:
    """Resolve + link the GL account and cost center a record references.

    Returns the links created (for logging/tests). Callers invoke this
    best-effort (wrapped in try/except) so a resolution hiccup never breaks the
    memory write.
    """
    item = item or {}
    if not (organization_id and box_id):
        return []
    meta = _meta(item)
    links: List[Dict[str, Any]] = []

    gl = _gl_value(item, meta)
    if gl:
        r = _link_for(
            db, organization_id=organization_id, box_type=box_type, box_id=box_id,
            dimension_type="gl_account", raw_value=gl, label=_gl_label(item, meta),
        )
        if r:
            links.append({**r, "dimension_type": "gl_account"})

    cc = _cost_center_value(item, meta)
    if cc:
        r = _link_for(
            db, organization_id=organization_id, box_type=box_type, box_id=box_id,
            dimension_type="cost_center", raw_value=cc, label=None,
        )
        if r:
            links.append({**r, "dimension_type": "cost_center"})
    else:
        logger.debug(
            "[dimension_resolver] no cost_center on %s/%s "
            "(sparse until extraction populates it)", box_type, box_id,
        )

    return links
