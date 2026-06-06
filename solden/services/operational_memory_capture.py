"""Operational-memory capture loop.

This is the write-side contract for turning observed finance traces into
durable memory. It does not render the MemoryRecord; it decides whether an
observed event is linked and confirmed enough to commit, or whether Solden
should ask a small confirmation question in the surface where the work is
happening.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from solden.core.ap_item_resolution import resolve_ap_item_reference
from solden.core.box_registry import get_box
from solden.services.memory_events import commit_memory_event


DEFAULT_LINK_CONFIDENCE_THRESHOLD = 0.72
DEFAULT_AUTO_COMMIT_CONFIDENCE_THRESHOLD = 0.90


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
        if vendor and vendor == _text(row.get("vendor_name") or row.get("vendor")).lower():
            score += 0.20
            evidence.append("vendor")
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
        if score > best_score:
            best = row
            best_score = min(score, 1.0)
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
    confidence = float(candidate.get("confidence") or 0.0)
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
        if not auto_commit or confidence < DEFAULT_AUTO_COMMIT_CONFIDENCE_THRESHOLD:
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
    return {
        "status": "committed",
        "link": link,
        "candidate": candidate,
        "event": row,
    }
