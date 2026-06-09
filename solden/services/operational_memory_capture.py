"""Operational-memory capture loop.

This is the write-side contract for turning observed finance traces into
durable memory. It does not render the MemoryRecord; it decides whether an
observed event is linked and confirmed enough to commit, or whether Solden
should ask a small confirmation question in the surface where the work is
happening.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from solden.core.ap_item_resolution import resolve_ap_item_reference
from solden.core.box_registry import get_box
from solden.services.dimension_resolver import resolve_dimensions_for_box
from solden.services.memory_events import commit_memory_event
from solden.services.vendor_attribute_matcher import vendor_name_similarity

logger = logging.getLogger(__name__)


DEFAULT_LINK_CONFIDENCE_THRESHOLD = 0.72
DEFAULT_AUTO_COMMIT_CONFIDENCE_THRESHOLD = 0.90
# Vendor inference is fuzzy (token-set similarity), not exact-string equality.
DEFAULT_VENDOR_STRONG_SIMILARITY = 0.92
DEFAULT_VENDOR_PARTIAL_SIMILARITY = 0.75
# Recency only modulates weak/fuzzy matches: 1.0 within _FULL days, decaying to
# _FLOOR by _FLOOR days. A fresh work item outranks a stale one of equal evidence.
_RECENCY_FULL_DAYS = 7.0
_RECENCY_FLOOR_DAYS = 60.0
_RECENCY_FLOOR = 0.9


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_amount(a: Any, b: Any) -> bool:
    left = _float(a)
    right = _float(b)
    if left is None or right is None:
        return False
    return abs(left - right) < 0.01


def _parse_dt(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _recency_factor(created_at: Any, *, now: Optional[datetime] = None) -> float:
    """Gentle decay (1.0 -> _RECENCY_FLOOR) by work-item age. Returns 1.0 when
    the timestamp is missing or unparseable, so it is a no-op on bad data."""
    dt = _parse_dt(created_at)
    if dt is None:
        return 1.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ref = now or datetime.now(timezone.utc)
    age_days = (ref - dt).total_seconds() / 86400.0
    if age_days <= _RECENCY_FULL_DAYS:
        return 1.0
    if age_days >= _RECENCY_FLOOR_DAYS:
        return _RECENCY_FLOOR
    span = _RECENCY_FLOOR_DAYS - _RECENCY_FULL_DAYS
    return round(1.0 - (1.0 - _RECENCY_FLOOR) * (age_days - _RECENCY_FULL_DAYS) / span, 4)


def _row_org(row: Dict[str, Any]) -> str:
    return _text(row.get("organization_id"))


def _compact_work_item(row: Dict[str, Any], box_type: str) -> Dict[str, Any]:
    data = _dict(row.get("data"))
    return {
        "box_type": box_type,
        "box_id": _text(row.get("id") or row.get("box_id")),
        "label": _text(
            row.get("invoice_number")
            or row.get("po_number")
            or row.get("reference")
            or row.get("title")
            or row.get("subject")
            or row.get("vendor_name")
            or data.get("title")
            or data.get("reference")
            or row.get("id")
        ),
        "state": _text(row.get("state") or row.get("status")),
        "organization_id": _row_org(row),
    }


def _verify_explicit_box(
    db: Any,
    *,
    organization_id: str,
    box_type: str,
    box_id: str,
) -> Optional[Dict[str, Any]]:
    try:
        row = get_box(box_type, box_id, db)
    except Exception:
        row = None
    if not isinstance(row, dict):
        return None
    if _row_org(row) != organization_id:
        return None
    return row


def _candidate_refs(observed: Dict[str, Any]) -> Dict[str, Any]:
    refs = {}
    for block in (
        _dict(observed.get("source_refs")),
        _dict(observed.get("external_refs")),
        _dict(_dict(observed.get("evidence")).get("source_refs")),
        _dict(_dict(observed.get("evidence")).get("refs")),
    ):
        refs.update({str(k): v for k, v in block.items() if v not in (None, "", [], {})})
    return refs


def _resolve_ap_by_refs(
    db: Any,
    *,
    organization_id: str,
    observed: Dict[str, Any],
    refs: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], float, list[str]]:
    direct_refs = [
        observed.get("box_id"),
        observed.get("ap_item_id"),
        refs.get("ap_item_id"),
        refs.get("box_id") if _text(refs.get("box_type")) in {"", "ap_item"} else None,
        refs.get("thread_id"),
        refs.get("gmail_thread_id"),
        refs.get("email_thread_id"),
        refs.get("message_id"),
        refs.get("gmail_message_id"),
        refs.get("email_message_id"),
    ]
    for ref in direct_refs:
        item = resolve_ap_item_reference(db, organization_id, _text(ref))
        if item:
            return item, 1.0, [f"direct_ref:{_text(ref)}"]

    invoice_number = _text(observed.get("invoice_number") or refs.get("invoice_number"))
    po_number = _text(observed.get("po_number") or refs.get("po_number"))
    vendor = _text(observed.get("vendor_name") or observed.get("vendor") or refs.get("vendor_name")).lower()
    amount = observed.get("amount") if observed.get("amount") not in (None, "") else refs.get("amount")
    erp_record_id = _text(refs.get("erp_record_id") or refs.get("erp_bill_id") or observed.get("erp_record_id"))
    if not any([invoice_number, po_number, vendor, amount not in (None, ""), erp_record_id]):
        return None, 0.0, []

    rows = []
    if hasattr(db, "list_ap_items"):
        try:
            rows = list(db.list_ap_items(organization_id, limit=1000) or [])
        except Exception:
            rows = []
    best: Optional[Dict[str, Any]] = None
    best_score = 0.0
    best_evidence: list[str] = []
    for row in rows:
        if _row_org(row) != organization_id:
            continue
        score = 0.0
        evidence: list[str] = []
        if invoice_number and invoice_number == _text(row.get("invoice_number")):
            score += 0.45
            evidence.append("invoice_number")
        if po_number and po_number == _text(row.get("po_number")):
            score += 0.25
            evidence.append("po_number")
        if vendor:
            sim = vendor_name_similarity(
                vendor, _text(row.get("vendor_name") or row.get("vendor")).lower()
            )
            if sim >= DEFAULT_VENDOR_STRONG_SIMILARITY:
                score += 0.20
                evidence.append("vendor")
            elif sim >= DEFAULT_VENDOR_PARTIAL_SIMILARITY:
                score += 0.12
                evidence.append("vendor~")
        if _same_amount(amount, row.get("amount")):
            score += 0.20
            evidence.append("amount")
        if erp_record_id and erp_record_id in {
            _text(row.get("erp_reference")),
            _text(row.get("erp_bill_id")),
            _text(row.get("external_id")),
        }:
            score += 0.45
            evidence.append("erp_record_id")
        # Recency modulates weak/fuzzy matches only. A strong structured id
        # (invoice / po / erp) stays at full confidence regardless of age, since
        # an old invoice with an exact id match is still the right one.
        strong = any(e in evidence for e in ("invoice_number", "po_number", "erp_record_id"))
        capped = min(score, 1.0)
        ranked = capped if strong else capped * _recency_factor(row.get("created_at"))
        if ranked > best_score:
            best = row
            best_score = ranked
            best_evidence = evidence
    return best, best_score, best_evidence


def link_observed_event_to_work_item(
    db: Any,
    *,
    organization_id: str,
    observed: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve which work item an observed event belongs to."""
    refs = _candidate_refs(observed)
    explicit_box_type = _text(observed.get("box_type") or refs.get("box_type"))
    explicit_box_id = _text(observed.get("box_id") or refs.get("box_id"))
    if not explicit_box_type and _text(observed.get("ap_item_id") or refs.get("ap_item_id")):
        explicit_box_type = "ap_item"
        explicit_box_id = _text(observed.get("ap_item_id") or refs.get("ap_item_id"))

    if explicit_box_type and explicit_box_id:
        row = _verify_explicit_box(
            db,
            organization_id=organization_id,
            box_type=explicit_box_type,
            box_id=explicit_box_id,
        )
        if row:
            return {
                "status": "linked",
                "confidence": 1.0,
                "match_evidence": ["explicit_box_ref"],
                "work_item": _compact_work_item(row, explicit_box_type),
            }
        return {
            "status": "unlinked",
            "confidence": 0.0,
            "reason": "explicit_work_item_not_found",
            "match_evidence": [],
            "work_item": None,
        }

    ap_item, score, evidence = _resolve_ap_by_refs(
        db,
        organization_id=organization_id,
        observed=observed,
        refs=refs,
    )
    if ap_item and score >= DEFAULT_LINK_CONFIDENCE_THRESHOLD:
        return {
            "status": "linked",
            "confidence": score,
            "match_evidence": evidence,
            "work_item": _compact_work_item(ap_item, "ap_item"),
        }
    if ap_item:
        return {
            "status": "needs_confirmation",
            "confidence": score,
            "reason": "low_confidence_work_item_match",
            "match_evidence": evidence,
            "work_item": _compact_work_item(ap_item, "ap_item"),
        }
    return {
        "status": "unlinked",
        "confidence": 0.0,
        "reason": "no_work_item_match",
        "match_evidence": [],
        "work_item": None,
    }


def _observed_summary(observed: Dict[str, Any]) -> str:
    for value in (
        observed.get("summary"),
        observed.get("rationale"),
        _dict(observed.get("decision")).get("summary"),
        observed.get("raw_text"),
        observed.get("message"),
    ):
        text = _text(value)
        if text:
            return text[:500]
    event_type = _text(observed.get("event_type")) or "context_recorded"
    return event_type.replace("_", " ")


def _confirmation_question(link: Dict[str, Any], candidate: Dict[str, Any]) -> str:
    work_item = _dict(link.get("work_item"))
    label = _text(work_item.get("label") or work_item.get("box_id") or "this work item")
    summary = _text(candidate.get("summary") or "this operational context")
    if link.get("status") == "unlinked":
        return f"Which work item should Solden attach this context to: {summary}?"
    return f"Should Solden record this on {label}: {summary}?"


def build_capture_candidate(
    *,
    organization_id: str,
    observed: Dict[str, Any],
    link: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the structured memory candidate from an observed event."""
    work_item = _dict(link.get("work_item"))
    refs = _candidate_refs(observed)
    event_type = _text(observed.get("event_type")) or (
        "decision_confirmed" if observed.get("decision") else "context_recorded"
    )
    confidence = _float(observed.get("confidence"))
    if confidence is None:
        confidence = float(link.get("confidence") or 0.0)
    return {
        "organization_id": organization_id,
        "box_type": _text(work_item.get("box_type")),
        "box_id": _text(work_item.get("box_id")),
        "event_type": event_type,
        "source": _text(observed.get("source")) or "operational_memory_capture",
        "previous_state": _text(observed.get("previous_state") or observed.get("state_before")) or None,
        "resulting_state": _text(observed.get("resulting_state") or observed.get("state_after")) or None,
        "owner": observed.get("owner"),
        "dependency": observed.get("dependency"),
        "decision": observed.get("decision"),
        "rationale": _text(observed.get("rationale")) or _observed_summary(observed),
        "evidence": observed.get("evidence") if observed.get("evidence") not in (None, "", [], {}) else None,
        "confidence": confidence,
        "human_confirmation_status": _text(observed.get("human_confirmation_status")) or None,
        "next_action": _text(observed.get("next_action")) or None,
        "summary": _observed_summary(observed),
        "source_refs": refs,
        "external_refs": _dict(observed.get("external_refs")) or None,
        "idempotency_key": _text(observed.get("idempotency_key")) or None,
        "correlation_id": _text(observed.get("correlation_id")) or None,
        "occurred_at": _text(observed.get("occurred_at")) or None,
    }


def capture_operational_memory_event(
    db: Any,
    *,
    organization_id: str,
    observed: Dict[str, Any],
    actor_type: str = "user",
    actor_id: Optional[str] = None,
    actor_label: Optional[str] = None,
) -> Dict[str, Any]:
    """Observe → link → ask/commit one operational-memory event.

    Unconfirmed context returns a confirmation request. Confirmed or explicitly
    auto-committed context writes a canonical memory event.
    """
    org_id = _text(organization_id)
    if not org_id:
        raise ValueError("organization_id is required")
    payload = dict(observed or {})
    link = link_observed_event_to_work_item(
        db,
        organization_id=org_id,
        observed=payload,
    )
    candidate = build_capture_candidate(
        organization_id=org_id,
        observed=payload,
        link=link,
    )
    confirmation_status = _text(candidate.get("human_confirmation_status")).lower()
    auto_commit = bool(payload.get("auto_commit"))
    # Auto-commit must be gated on the VERIFIED link score, never the caller's
    # self-reported confidence (the public capture endpoints accept it in the
    # request body). Legitimate auto-commit callers link via explicit/direct
    # refs at 1.0, so this does not regress them; it closes the bypass where a
    # weak fuzzy link (0.72-0.89) would auto-commit on a payload-supplied 0.99.
    link_confidence = float(link.get("confidence") or 0.0)
    if link.get("status") != "linked":
        return {
            "status": "needs_link",
            "link": link,
            "candidate": candidate,
            "confirmation_request": {
                "kind": "link_work_item",
                "question": _confirmation_question(link, candidate),
            },
        }
    if confirmation_status not in {"confirmed", "human_confirmed"}:
        if not auto_commit or link_confidence < DEFAULT_AUTO_COMMIT_CONFIDENCE_THRESHOLD:
            return {
                "status": "needs_confirmation",
                "link": link,
                "candidate": candidate,
                "confirmation_request": {
                    "kind": "confirm_memory_event",
                    "question": _confirmation_question(link, candidate),
                    "suggested_action": "record_memory_event",
                },
            }

    row = commit_memory_event(
        db,
        box_type=candidate["box_type"],
        box_id=candidate["box_id"],
        organization_id=org_id,
        event_type=candidate["event_type"],
        source=candidate["source"],
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label or actor_id,
        previous_state=candidate.get("previous_state"),
        resulting_state=candidate.get("resulting_state"),
        owner=candidate.get("owner"),
        dependency=candidate.get("dependency"),
        decision=candidate.get("decision"),
        rationale=candidate.get("rationale"),
        evidence=candidate.get("evidence"),
        confidence=candidate.get("confidence"),
        human_confirmation_status=(
            "confirmed"
            if confirmation_status in {"confirmed", "human_confirmed"}
            else "system_observed"
        ),
        next_action=candidate.get("next_action"),
        summary=candidate.get("summary"),
        source_refs=candidate.get("source_refs"),
        external_refs=candidate.get("external_refs"),
        idempotency_key=candidate.get("idempotency_key"),
        correlation_id=candidate.get("correlation_id"),
        occurred_at=candidate.get("occurred_at"),
    )

    # Link the cross-system dimensions (GL account / cost center) this record
    # references into the dimension graph, so memory spans systems (H5).
    # Best-effort: a resolution hiccup must never fail the memory write.
    try:
        box_item = get_box(candidate["box_type"], candidate["box_id"], db)
        if isinstance(box_item, dict):
            resolve_dimensions_for_box(
                db,
                box_type=candidate["box_type"],
                box_id=candidate["box_id"],
                item=box_item,
                organization_id=org_id,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[operational_memory_capture] dimension resolution failed for %s/%s: %s",
            candidate.get("box_type"), candidate.get("box_id"), exc,
        )

    return {
        "status": "committed",
        "link": link,
        "candidate": candidate,
        "event": row,
    }
