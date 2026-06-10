"""Dimension memory — "tell me about cost center 402" (H5 deepening).

Aggregates everything the memory layer knows about one dimension: the records
linked to it (and, by hierarchy, under it), their states and currency totals,
decision counts with the most recent real whys, open exceptions, the standing
rules that touch it, and its place in the hierarchy. The dimension becomes a
first-class memory object — the per-object grounding an agent (or a
controller) needs.

Bounded by design: IN-lists are capped and the response says when it was
capped — silent truncation reads as "covered everything" when it didn't.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from solden.services.rationale_distillation import is_thin_rationale

logger = logging.getLogger(__name__)

_MAX_BOXES = 500
_MAX_AUDIT_ROWS = 200
_RECENT_WHYS = 5


def _safe_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(value or "{}")
        return decoded if isinstance(decoded, dict) else {}
    except Exception:
        return {}


def _rule_clauses(rule: Dict[str, Any]) -> List[Dict[str, Any]]:
    conditions = rule.get("conditions") or rule.get("conditions_json") or {}
    if isinstance(conditions, str):
        conditions = _safe_json(conditions)
    clauses: List[Dict[str, Any]] = []
    for key in ("all_of", "any_of"):
        block = conditions.get(key)
        if isinstance(block, list):
            clauses.extend(c for c in block if isinstance(c, dict))
    return clauses

# Which rule-engine fields can reference which dimension types.
_RULE_FIELDS_BY_TYPE = {
    "gl_account": {"gl_code"},
    "department": {"department"},
    "vendor": {"vendor_name", "vendor_id"},
}


def _standing_rules_for_dimension(
    db: Any, organization_id: str, dimension: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Active rules whose conditions reference this dimension's code.
    conditions_json isn't SQL-queryable, so this is a bounded code-side
    filter over list_rules."""
    fields = _RULE_FIELDS_BY_TYPE.get(str(dimension.get("dimension_type") or ""))
    if not fields:
        return []
    code = str(dimension.get("code") or "").strip().lower()
    if not code:
        return []
    matched: List[Dict[str, Any]] = []
    try:
        rules = db.list_rules(organization_id, workflow="ap") or []
    except Exception:
        return []
    for rule in rules:
        for clause in _rule_clauses(rule):
            if (
                str(clause.get("field") or "") in fields
                and str(clause.get("value") or "").strip().lower() == code
            ):
                matched.append({
                    "id": rule.get("id"),
                    "name": rule.get("name"),
                    "actions": rule.get("actions") or rule.get("actions_json"),
                })
                break
    return matched


def build_dimension_memory(
    db: Any,
    *,
    organization_id: str,
    dimension_id: str,
    include_descendants: bool = True,
) -> Optional[Dict[str, Any]]:
    """The memory rollup for one dimension. None if not in this org."""
    dimension = db.get_dimension(
        organization_id=organization_id, dimension_id=dimension_id
    )
    if not dimension:
        return None

    boxes = db.list_boxes_for_dimension(
        organization_id=organization_id,
        dimension_id=dimension_id,
        include_descendants=include_descendants,
    )
    capped = len(boxes) > _MAX_BOXES
    boxes = boxes[:_MAX_BOXES]

    by_box_type: Dict[str, int] = {}
    ap_ids: List[str] = []
    for box in boxes:
        bt = str(box.get("box_type") or "")
        by_box_type[bt] = by_box_type.get(bt, 0) + 1
        if bt == "ap_item":
            ap_ids.append(str(box.get("box_id")))

    states: Dict[str, int] = {}
    totals_by_currency: Dict[str, float] = {}
    decisions = 0
    recent_whys: List[Dict[str, Any]] = []
    open_exceptions = 0

    if ap_ids:
        placeholders = ",".join("%s" for _ in ap_ids)
        with db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT state, amount, currency FROM ap_items "
                f"WHERE organization_id=%s AND id IN ({placeholders})",
                (organization_id, *ap_ids),
            )
            for row in cur.fetchall() or []:
                d = dict(row)
                state = str(d.get("state") or "unknown")
                states[state] = states.get(state, 0) + 1
                try:
                    amount = float(d.get("amount"))
                except (TypeError, ValueError):
                    continue
                currency = str(d.get("currency") or "").strip().upper() or "?"
                totals_by_currency[currency] = round(
                    totals_by_currency.get(currency, 0.0) + amount, 2
                )

    # Decisions + the whys, across ALL linked box ids (not just ap_item).
    all_box_ids = [str(b.get("box_id")) for b in boxes if b.get("box_id")]
    if all_box_ids:
        placeholders = ",".join("%s" for _ in all_box_ids)
        with db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT event_type, decision_reason, actor_id, ts, payload_json "
                f"FROM audit_events "
                f"WHERE organization_id=%s AND box_id IN ({placeholders}) "
                f"AND (decision_reason IS NOT NULL OR event_type LIKE 'memory_event:%%') "
                f"ORDER BY ts DESC LIMIT %s",
                (organization_id, *all_box_ids, _MAX_AUDIT_ROWS),
            )
            for row in cur.fetchall() or []:
                d = dict(row)
                decisions += 1
                if len(recent_whys) >= _RECENT_WHYS:
                    continue
                payload = _safe_json(d.get("payload_json"))
                memory_event = payload.get("memory_event")
                memory_event = memory_event if isinstance(memory_event, dict) else {}
                why = str(
                    payload.get("human_rationale")
                    or memory_event.get("rationale")
                    or d.get("decision_reason")
                    or ""
                ).strip()
                if why and not is_thin_rationale(why):
                    recent_whys.append({
                        "why": why[:500],
                        "actor_id": d.get("actor_id"),
                        "ts": d.get("ts"),
                    })
            cur.execute(
                f"SELECT COUNT(*) AS n FROM box_exceptions "
                f"WHERE organization_id=%s AND box_id IN ({placeholders}) "
                f"AND resolved_at IS NULL",
                (organization_id, *all_box_ids),
            )
            row = cur.fetchone()
            open_exceptions = int(dict(row).get("n") or 0) if row else 0

    return {
        "dimension": {
            "dimension_id": dimension.get("id"),
            "dimension_type": dimension.get("dimension_type"),
            "code": dimension.get("code"),
            "label": dimension.get("label"),
            "source": dimension.get("source"),
        },
        "hierarchy": {
            "parents": [
                {"dimension_id": p.get("id"), "code": p.get("code"), "dimension_type": p.get("dimension_type")}
                for p in db.list_dimension_parents(
                    organization_id=organization_id, dimension_id=dimension_id
                )
            ],
            "children": [
                {"dimension_id": c.get("id"), "code": c.get("code"), "dimension_type": c.get("dimension_type")}
                for c in db.list_dimension_children(
                    organization_id=organization_id, dimension_id=dimension_id
                )
            ],
        },
        "records": {
            "count": len(boxes),
            "by_box_type": by_box_type,
            "states": states,
            "totals_by_currency": totals_by_currency,
            "capped": capped,
            "include_descendants": include_descendants,
        },
        "decisions": {
            "count": decisions,
            "recent_whys": recent_whys,
        },
        "open_exceptions": open_exceptions,
        "standing_rules": _standing_rules_for_dimension(db, organization_id, dimension),
    }
