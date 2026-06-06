"""Audit-event to operational-memory promotion.

The audit log is Solden's append-only write journal. Operational memory is the
product-level projection over that journal, so every canonical audit row must
carry enough structured context to rebuild the live memory record.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def _audit_text(value: Any) -> str:
    return str(value or "").strip()


def _audit_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _audit_float(*values: Any) -> Optional[float]:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _audit_payload_dict(payload_json: Any) -> Dict[str, Any]:
    if isinstance(payload_json, dict):
        return dict(payload_json)
    if payload_json in (None, "", [], {}):
        return {}
    return {"raw_payload": payload_json}


def _audit_decision(payload: Dict[str, Any], payload_json: Dict[str, Any]) -> Dict[str, Any]:
    decision = _audit_dict(payload_json.get("decision"))
    context = _audit_dict(payload_json.get("decision_context"))
    if not decision:
        decision = {
            "type": (
                _audit_text(context.get("intent"))
                or _audit_text(payload_json.get("action"))
                or _audit_text(payload.get("event_type"))
                or "audit_event"
            ),
        }
    if context and "context_snapshot" not in decision:
        decision["context_snapshot"] = context
    return {key: value for key, value in decision.items() if value not in (None, "", [], {})}


def _audit_rationale(payload: Dict[str, Any], payload_json: Dict[str, Any]) -> str:
    context = _audit_dict(payload_json.get("decision_context"))
    for value in (
        payload.get("decision_reason"),
        payload.get("reason"),
        payload_json.get("reason"),
        context.get("decision_reason"),
        payload_json.get("rationale"),
        payload_json.get("message"),
        payload_json.get("summary"),
    ):
        text = _audit_text(value)
        if text:
            return text
    return _audit_text(payload.get("event_type")) or "audit event recorded"


def _audit_evidence(
    payload: Dict[str, Any],
    payload_json: Dict[str, Any],
    external_refs: Dict[str, Any],
) -> Any:
    explicit_evidence = payload_json.get("evidence")
    if explicit_evidence not in (None, "", [], {}):
        return explicit_evidence
    context = _audit_dict(payload_json.get("decision_context"))
    evidence = {
        "event_type": payload.get("event_type"),
        "source": payload.get("source"),
        "external_refs": external_refs,
        "correlation_id": payload.get("correlation_id"),
        "workflow_id": payload.get("workflow_id"),
        "run_id": payload.get("run_id"),
        "idempotency_key": payload.get("idempotency_key"),
        "column_updates": payload_json.get("column_updates"),
        "field_confidences": payload_json.get("field_confidences"),
        "source_conflicts": payload_json.get("source_conflicts"),
        "attachment_url": payload_json.get("attachment_url"),
        "attachment_content_hash": payload_json.get("attachment_content_hash"),
        "decision_context": context,
    }
    return {key: value for key, value in evidence.items() if value not in (None, "", [], {})}


def _audit_changes(payload: Dict[str, Any], payload_json: Dict[str, Any]) -> Dict[str, Any]:
    changes = {
        "event_type": payload.get("event_type"),
        "previous_state": payload.get("from_state") or payload.get("prev_state"),
        "resulting_state": payload.get("to_state") or payload.get("new_state"),
        "field_updates": payload_json.get("column_updates") or payload_json.get("field_updates"),
    }
    return {key: value for key, value in changes.items() if value not in (None, "", [], {})}


def _audit_owner(payload_json: Dict[str, Any]) -> Any:
    for key in ("owner", "assigned_owner", "approval_sent_to"):
        value = payload_json.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _audit_dependency(payload_json: Dict[str, Any]) -> Any:
    for key in ("dependency", "waiting_condition", "blocker", "exception"):
        value = payload_json.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def ensure_memory_payload_for_audit_event(
    payload: Dict[str, Any],
    *,
    box_type: str,
    box_id: str,
    payload_json: Any,
    external_refs: Dict[str, Any],
    now: str,
) -> Dict[str, Any]:
    """Return ``payload_json`` with canonical operational-memory context.

    Explicit memory events are validated and preserved. Legacy or thin audit
    rows are promoted here, which makes ``audit_events`` the required write
    boundary for operational memory instead of asking every caller to remember
    a parallel write.
    """
    resolved_payload = _audit_payload_dict(payload_json)
    existing_memory_event = _audit_dict(resolved_payload.get("memory_event"))
    if existing_memory_event:
        from solden.services.memory_invariants import assert_memory_event_payload

        assert_memory_event_payload(resolved_payload)
        return resolved_payload

    from solden.services.memory_events import build_memory_event_payload
    from solden.services.memory_invariants import assert_memory_event_payload

    context = _audit_dict(resolved_payload.get("decision_context"))
    source = (
        _audit_text(payload.get("source"))
        or _audit_text(context.get("ui_surface"))
        or "audit_events"
    )
    rationale = _audit_rationale(payload, resolved_payload)
    memory_payload = build_memory_event_payload(
        box_type=box_type,
        box_id=box_id,
        organization_id=payload.get("organization_id"),
        event_type=_audit_text(payload.get("event_type")) or "audit_event",
        source=source,
        actor_type=_audit_text(payload.get("actor_type")) or "system",
        actor_id=_audit_text(payload.get("actor_id")) or None,
        actor_label=_audit_text(context.get("actor_label")) or None,
        actor_role=_audit_text(context.get("actor_role")) or None,
        actor_team=_audit_text(context.get("actor_team")) or None,
        department=_audit_text(context.get("department")) or None,
        previous_state=payload.get("from_state") or payload.get("prev_state"),
        resulting_state=payload.get("to_state") or payload.get("new_state"),
        owner=_audit_owner(resolved_payload),
        dependency=_audit_dependency(resolved_payload),
        decision=_audit_decision(payload, resolved_payload),
        rationale=rationale,
        evidence=_audit_evidence(payload, resolved_payload, external_refs),
        confidence=_audit_float(
            payload.get("agent_confidence"),
            resolved_payload.get("agent_confidence"),
            resolved_payload.get("confidence_score"),
            resolved_payload.get("confidence"),
            context.get("confidence_at_decision"),
        ),
        human_confirmation_status=(
            _audit_text(resolved_payload.get("human_confirmation_status"))
            or _audit_text(context.get("human_confirmation_status"))
            or "system_observed"
        ),
        next_action=(
            _audit_text(resolved_payload.get("next_action"))
            or _audit_text(resolved_payload.get("recommended_next_action"))
            or None
        ),
        summary=(
            _audit_text(resolved_payload.get("summary"))
            or _audit_text(context.get("memory_line"))
            or _audit_text(payload.get("summary"))
            or None
        ),
        source_refs=external_refs,
        external_refs=external_refs,
        occurred_at=payload.get("ts") or now,
    )
    changes = _audit_changes(payload, resolved_payload)
    if changes:
        memory_payload["memory_event"]["changes"] = changes

    merged = dict(resolved_payload)
    merged["memory_event"] = memory_payload["memory_event"]
    merged["decision_context"] = {
        **_audit_dict(memory_payload.get("decision_context")),
        **_audit_dict(merged.get("decision_context")),
    }
    merged.setdefault("summary", memory_payload.get("summary"))
    merged.setdefault("reason", memory_payload.get("reason"))
    assert_memory_event_payload(merged)
    return merged
