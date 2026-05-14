"""Box export endpoint — the sovereignty primitive.

The manifesto promises: "Components should remain whole if you ever
take it out. The bond should be strong but not destructive."

This module backs that promise. Every Box (workflow instance) can be
exported as a single self-contained JSON document containing:

  * the Box's current state and raw fields
  * the complete audit history (every transition, every override,
    every reversal) with the hash-chain links preserved
  * any open exceptions
  * the terminal outcome if the Box has closed
  * parent/child Box links (for child Box types like ``bank_match``)

The output is a stable, versioned schema (``box_schema_version``)
documented at ``docs/BOX_SCHEMA.md``. A third party reading the export
can reconstruct the workflow record without any Solden runtime
present — that's what "removable" means.

This is also the read primitive operators use to satisfy regulator
"give me everything you have on workflow X" requests.

Path::

    GET /api/workspace/ap-items/{ap_item_id}/export

Future: a generic ``GET /api/workspace/box/{box_type}/{box_id}/export``
will replace this thin wrapper once a second BoxType ships
(``bank_match`` is on the roadmap). The current shape is already
generic; only the route prefix is AP-specific.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from clearledgr.core.auth import get_current_user
from clearledgr.core.database import get_db

logger = logging.getLogger(__name__)


# Bumped whenever the export shape changes in a non-additive way.
# Additive fields are fine without a version bump; consumers must
# tolerate unknown keys. See docs/BOX_SCHEMA.md for the contract.
BOX_SCHEMA_VERSION = "1.0"


router = APIRouter(prefix="/api/workspace", tags=["box-export"])


def _session_org(user: Any) -> str:
    org = str(getattr(user, "organization_id", "") or "").strip()
    if not org:
        raise HTTPException(
            status_code=403, detail="user_missing_organization_id"
        )
    return org


def _normalize_audit_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Shape one audit_events row for export.

    Unlike ``normalize_operator_audit_events``, this preserves every
    column — including the hash chain — because the export is the
    forensic record, not a UI feed. Consumers verifying chain
    integrity need ``prev_hash``, ``hash``, ``chain_seq`` intact.
    """
    return {
        "id": raw.get("id"),
        "ts": raw.get("ts"),
        "event_type": raw.get("event_type"),
        "prev_state": raw.get("prev_state"),
        "new_state": raw.get("new_state"),
        "actor_type": raw.get("actor_type"),
        "actor_id": raw.get("actor_id"),
        "decision_reason": raw.get("decision_reason"),
        "policy_version": raw.get("policy_version"),
        "governance_verdict": raw.get("governance_verdict"),
        "agent_confidence": raw.get("agent_confidence"),
        "source": raw.get("source"),
        "correlation_id": raw.get("correlation_id"),
        "workflow_id": raw.get("workflow_id"),
        "run_id": raw.get("run_id"),
        "payload": raw.get("payload_json") or {},
        "external_refs": raw.get("external_refs") or {},
        "idempotency_key": raw.get("idempotency_key"),
        "entity_id": raw.get("entity_id"),
        # Hash chain — preserved so an offline verifier can
        # reconstruct the chain and prove the export hasn't been
        # tampered with after extraction.
        "prev_hash": raw.get("prev_hash"),
        "hash": raw.get("hash"),
        "chain_seq": raw.get("chain_seq"),
    }


def _normalize_exception(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": raw.get("id"),
        "exception_type": raw.get("exception_type"),
        "severity": raw.get("severity"),
        "reason": raw.get("reason"),
        "metadata": raw.get("metadata") or {},
        "raised_at": raw.get("raised_at") or raw.get("created_at"),
        "resolved_at": raw.get("resolved_at"),
        "resolved_by": raw.get("resolved_by"),
        "resolution_note": raw.get("resolution_note"),
    }


def _box_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """Project a raw row into the portable ``fields`` block.

    Drops nothing — every persisted column on the source row lands
    here so the export is genuinely complete. Internal SQL columns
    (``state``, ``id``, ``organization_id``) are surfaced at the
    parent ``box`` level instead, not duplicated.
    """
    return {
        k: v for k, v in item.items()
        if k not in {"id", "state", "organization_id"}
    }


def _bank_match_export_links(db: Any, ap_item_id: str, organization_id: str) -> Dict[str, Any]:
    """Build the ``links`` block for an ap_item export — enumerates
    child bank_match Boxes (the second BoxType, Phase 4.2).

    Empty ``child_boxes`` is the universal default; populated only
    when the underlying store mixin is available and reports at
    least one match Box for the parent.
    """
    children = []
    if hasattr(db, "list_bank_matches_for_ap"):
        try:
            for match in db.list_bank_matches_for_ap(
                ap_item_id, organization_id=organization_id,
            ) or []:
                children.append({"type": "bank_match", "id": match["id"]})
        except Exception as exc:
            logger.warning(
                "[box_export] list_bank_matches_for_ap failed for %s: %s",
                ap_item_id, exc,
            )
    return {"parent_box": None, "child_boxes": children}


def export_ap_item_box(db: Any, ap_item_id: str, organization_id: str, actor: str) -> Dict[str, Any]:
    """Build the full export document for one AP item Box.

    Pure function over DB reads — no side effects, no audit write.
    The export itself is a read action; callers that want it audited
    should record their own ``box_exported`` event.
    """
    item = db.get_ap_item(ap_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="ap_item_not_found")
    if str(item.get("organization_id") or "") != organization_id:
        # Don't disclose cross-tenant existence — 404 looks the same
        # as "no such item" to a caller without access.
        raise HTTPException(status_code=404, detail="ap_item_not_found")

    raw_events = db.list_ap_audit_events(ap_item_id) or []
    history = [_normalize_audit_event(e) for e in raw_events]

    exceptions: List[Dict[str, Any]] = []
    if hasattr(db, "list_box_exceptions"):
        try:
            exceptions = [
                _normalize_exception(e)
                for e in db.list_box_exceptions(
                    box_type="ap_item", box_id=ap_item_id,
                )
            ]
        except Exception as exc:
            logger.warning(
                "[box_export] list_box_exceptions failed for %s: %s",
                ap_item_id, exc,
            )

    outcome: Optional[Dict[str, Any]] = None
    if hasattr(db, "get_box_outcome"):
        try:
            outcome = db.get_box_outcome(
                box_type="ap_item", box_id=ap_item_id,
            )
        except Exception as exc:
            logger.warning(
                "[box_export] get_box_outcome failed for %s: %s",
                ap_item_id, exc,
            )

    return {
        "box_schema_version": BOX_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by": actor,
        "box": {
            "type": "ap_item",
            "id": ap_item_id,
            "organization_id": organization_id,
            "entity_id": item.get("entity_id"),
            "state": item.get("state"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "fields": _box_fields(item),
        },
        "history": history,
        "exceptions": exceptions,
        "outcome": outcome,
        "links": _bank_match_export_links(db, ap_item_id, organization_id),
    }


def export_bank_match_box(db: Any, box_id: str, organization_id: str, actor: str) -> Dict[str, Any]:
    """Build the full export document for one bank_match Box.

    Same shape as :func:`export_ap_item_box` so a consumer that knows
    the BoxType doesn't have to vary its parser per type — only the
    ``box.type`` discriminator and ``fields`` shape differ.
    """
    if not hasattr(db, "get_bank_match"):
        raise HTTPException(status_code=500, detail="bank_match_store_unavailable")
    item = db.get_bank_match(box_id)
    if not item:
        raise HTTPException(status_code=404, detail="bank_match_not_found")
    if str(item.get("organization_id") or "") != organization_id:
        raise HTTPException(status_code=404, detail="bank_match_not_found")

    raw_events: List[Dict[str, Any]] = []
    # bank_match audit events live in audit_events keyed on
    # box_type='bank_match'. There's no dedicated reader yet; use the
    # generic helper if available, otherwise filter from the AP list
    # by parent.
    if hasattr(db, "list_audit_events_for_box"):
        try:
            raw_events = db.list_audit_events_for_box(
                box_type="bank_match", box_id=box_id,
            ) or []
        except Exception as exc:
            logger.warning(
                "[box_export] list_audit_events_for_box failed for %s: %s",
                box_id, exc,
            )
    else:
        # Fallback path — direct SQL via the canonical store.
        try:
            with db.connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM audit_events "
                    "WHERE box_id = %s AND box_type = %s "
                    "ORDER BY ts ASC",
                    (box_id, "bank_match"),
                )
                rows = [dict(r) for r in cur.fetchall()]
            # Deserialize JSON columns the same way the canonical
            # reader does.
            if hasattr(db, "_deserialize_audit_event"):
                raw_events = [db._deserialize_audit_event(r) for r in rows]
            else:
                raw_events = rows
        except Exception as exc:
            logger.warning(
                "[box_export] fallback audit fetch failed for %s: %s",
                box_id, exc,
            )

    history = [_normalize_audit_event(e) for e in raw_events]

    return {
        "box_schema_version": BOX_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by": actor,
        "box": {
            "type": "bank_match",
            "id": box_id,
            "organization_id": organization_id,
            "entity_id": None,
            "state": item.get("state"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "fields": _box_fields(item),
        },
        "history": history,
        "exceptions": [],
        "outcome": (
            None
            if item.get("state") == "proposed"
            else {
                "outcome": item.get("state"),
                "completed_at": item.get("decided_at"),
                "completed_by": item.get("decided_by"),
                "metadata": {
                    "rejection_reason": item.get("rejection_reason"),
                },
            }
        ),
        "links": {
            "parent_box": {
                "type": "ap_item",
                "id": item.get("parent_ap_item_id"),
            },
            "child_boxes": [],
        },
    }


@router.get("/ap-items/{ap_item_id}/export")
def get_ap_item_export(
    ap_item_id: str,
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the full, portable, self-contained Box export.

    The shape is documented at ``docs/BOX_SCHEMA.md`` and versioned
    via ``box_schema_version``. Consumers should treat unknown keys
    as additive and version-gate any breaking-change handling on the
    ``box_schema_version`` field.
    """
    organization_id = _session_org(_user)
    actor = str(getattr(_user, "email", "") or getattr(_user, "user_id", "") or "")
    db = get_db()
    return export_ap_item_box(
        db=db,
        ap_item_id=ap_item_id,
        organization_id=organization_id,
        actor=actor,
    )


@router.get("/bank-matches/{box_id}/export")
def get_bank_match_export(
    box_id: str,
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the full, portable, self-contained Box export for a bank_match.

    Same schema-versioned shape as the ap_item export, with
    ``box.type='bank_match'`` and ``links.parent_box`` pointing back
    to the AP item this match reconciles.
    """
    organization_id = _session_org(_user)
    actor = str(getattr(_user, "email", "") or getattr(_user, "user_id", "") or "")
    db = get_db()
    return export_bank_match_box(
        db=db,
        box_id=box_id,
        organization_id=organization_id,
        actor=actor,
    )
