"""Resolve the cross-system dimensions a record references (GL account, cost
center, project, department), and link them into the dimension graph.

Called best-effort from the operational-memory capture loop, so a record's
memory carries the accounting objects it touches ("everything charged to GL
5210 / CC 402"). See docs/ENTITY_GRAPH_SCOPING.md (H5).

Status by source authority:
* An AUTHORITATIVE value — a code the record is actually coded to (``gl_code``,
  ``cost_center``, ``posting_metadata.*``) — links ``confirmed``.
* An LLM SUGGESTION (``suggested_*``, pulled by invoice extraction) links
  ``proposed`` — it is a read of unstructured input, so it needs human confirm
  before it counts as the record's coding.

The resolver itself is deterministic: exact -> alias -> normalized, then (for
free-text labels only, never numeric codes — or "5211" would match "5210")
fuzzy against labels, then seed the value as a new canonical dimension. The LLM
only reads the input upstream (extraction); it never decides the link here.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from solden.services.vendor_attribute_matcher import vendor_name_similarity

logger = logging.getLogger(__name__)

# Same bands the operational-memory capture linker uses.
_FUZZY_CONFIRM = 0.90
_FUZZY_PROPOSE = 0.72

# Per dimension type: where the value lives. Authoritative fields (the record's
# actual coding) win and link confirmed; suggested_* fields are LLM reads and
# link proposed. posting_metadata.<posting key> is authoritative too.
_DIMENSION_SOURCES: Tuple[Dict[str, Any], ...] = (
    {"type": "gl_account", "authoritative": ("gl_code",), "posting": ("gl_account",),
     "suggested": ("suggested_gl_code",), "label": ("gl_account_name", "account_name")},
    {"type": "cost_center", "authoritative": ("cost_center",), "posting": ("cost_center",),
     "suggested": ("suggested_cost_center",), "label": ("cost_center_name",)},
    {"type": "project", "authoritative": ("project",), "posting": ("project",),
     "suggested": ("suggested_project",), "label": ("project_name",)},
    {"type": "department", "authoritative": ("department",), "posting": ("department",),
     "suggested": ("suggested_department",), "label": ("department_name",)},
)


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


def _posting(meta: Dict[str, Any]) -> Dict[str, Any]:
    p = meta.get("posting_metadata")
    return p if isinstance(p, dict) else {}


def _resolve_value(
    item: Dict[str, Any], meta: Dict[str, Any], spec: Dict[str, Any]
) -> Tuple[str, Optional[str]]:
    """The value to link for one dimension type + its intended status.

    Authoritative (the record's coding) -> 'confirmed'; an LLM suggestion ->
    'proposed'. Returns ('', None) when neither is present.
    """
    posting = _posting(meta)
    auth = _first_str(
        *[item.get(k) for k in spec["authoritative"]],
        *[meta.get(k) for k in spec["authoritative"]],
        *[posting.get(k) for k in spec.get("posting", ())],
    )
    if auth:
        return auth, "confirmed"
    sugg = _first_str(*[meta.get(k) for k in spec["suggested"]])
    if sugg:
        return sugg, "proposed"
    return "", None


def _label_for(item: Dict[str, Any], meta: Dict[str, Any], spec: Dict[str, Any]) -> Optional[str]:
    return _first_str(*[meta.get(k) for k in spec["label"]]) or None


def _link_for(
    db: Any,
    *,
    organization_id: str,
    box_type: str,
    box_id: str,
    dimension_type: str,
    raw_value: str,
    intended_status: str,
    label: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve one (type, value) to a dimension and link it.

    ``intended_status`` ('confirmed' for an authoritative code, 'proposed' for a
    suggestion) is the ceiling: a suggested value links 'proposed' even on a
    strong match. Ladder: deterministic -> fuzzy (free-text only) -> seed new.
    """
    raw = str(raw_value or "").strip()
    if not raw:
        return None
    confirmed = intended_status == "confirmed"
    conf_score = 1.0 if confirmed else 0.7

    hit = db.resolve_dimension(
        organization_id=organization_id, dimension_type=dimension_type, raw_code=raw
    )
    if hit:
        db.link_dimension(
            organization_id=organization_id, box_type=box_type, box_id=box_id,
            dimension_id=hit["id"], confidence=conf_score, status=intended_status,
            source="resolver",
        )
        return {"dimension_id": hit["id"], "status": intended_status, "match": hit.get("_match_kind")}

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
            # A strong match confirms only if the value itself is authoritative;
            # a suggestion stays proposed.
            status = intended_status
            db.link_dimension(
                organization_id=organization_id, box_type=box_type, box_id=box_id,
                dimension_id=best["id"], confidence=round(best_sim, 3),
                status=status, source="resolver_fuzzy",
            )
            return {"dimension_id": best["id"], "status": status, "match": "fuzzy"}
        if best and best_sim >= _FUZZY_PROPOSE:
            db.link_dimension(
                organization_id=organization_id, box_type=box_type, box_id=box_id,
                dimension_id=best["id"], confidence=round(best_sim, 3),
                status="proposed", source="resolver_fuzzy",
            )
            return {"dimension_id": best["id"], "status": "proposed", "match": "fuzzy"}

    # Brand-new value: seed it as a canonical dimension. An authoritative code is
    # the record's real coding (confirmed); a suggestion is provenance-tagged.
    seeded = db.upsert_dimension(
        organization_id=organization_id, dimension_type=dimension_type,
        code=raw, label=label, source="inferred" if confirmed else "suggested",
    )
    if not seeded:
        return None
    db.link_dimension(
        organization_id=organization_id, box_type=box_type, box_id=box_id,
        dimension_id=seeded["id"], confidence=conf_score, status=intended_status,
        source="resolver",
    )
    return {"dimension_id": seeded["id"], "status": intended_status, "match": "seeded"}


def resolve_dimensions_for_box(
    db: Any,
    *,
    box_type: str,
    box_id: str,
    item: Optional[Dict[str, Any]],
    organization_id: str,
) -> List[Dict[str, Any]]:
    """Resolve + link every dimension (GL / cost center / project / department) a
    record references.

    Returns the links created (for logging/tests). Callers invoke this
    best-effort (wrapped in try/except) so a resolution hiccup never breaks the
    memory write.
    """
    item = item or {}
    if not (organization_id and box_id):
        return []
    meta = _meta(item)
    links: List[Dict[str, Any]] = []

    for spec in _DIMENSION_SOURCES:
        value, status = _resolve_value(item, meta, spec)
        if not value or not status:
            continue
        r = _link_for(
            db, organization_id=organization_id, box_type=box_type, box_id=box_id,
            dimension_type=spec["type"], raw_value=value, intended_status=status,
            label=_label_for(item, meta, spec),
        )
        if r:
            links.append({**r, "dimension_type": spec["type"]})

    if not links:
        logger.debug(
            "[dimension_resolver] no dimensions resolved for %s/%s", box_type, box_id
        )
    return links
