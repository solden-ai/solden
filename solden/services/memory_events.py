"""Operational-memory event capture.

This module is the write side of Solden's operational memory object. It
normalizes facts collected from ERP panels, Slack/Teams, Gmail, agents, and
workspace actions into a single append-only audit event shape keyed by
``(box_type, box_id)``.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional


MEMORY_EVENT_SCHEMA_VERSION = "1.0"
MEMORY_EVENT_PREFIX = "memory_event:"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _clean_optional_dict(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items() if v not in (None, "", [], {})}
    text = _text(value)
    if not text:
        return None
    return {"label": text}


def _clean_dict(value: Any) -> Dict[str, Any]:
    cleaned = _clean_optional_dict(value)
    return cleaned if cleaned is not None else {}


def _normalize_event_type(event_type: str) -> str:
    token = _text(event_type).lower().replace("-", "_").replace(" ", "_")
    while "__" in token:
        token = token.replace("__", "_")
    return token.strip("_") or "context_recorded"


def _normalize_decision(
    *,
    decision: Any,
    event_type: str,
    rationale: Optional[str],
    actor_type: str,
    actor_id: Optional[str],
) -> Dict[str, Any]:
    if isinstance(decision, dict):
        normalized = {
            str(k): v for k, v in decision.items()
            if v not in (None, "", [], {})
        }
    elif _text(decision):
        normalized = {"type": _text(decision)}
    else:
        normalized = {}
    normalized.setdefault("type", event_type)
    if rationale and "rationale" not in normalized:
        normalized["rationale"] = rationale
    if actor_type or actor_id:
        normalized.setdefault("made_by", {
            "type": actor_type or None,
            "id": actor_id,
        })
    return normalized


def _normalize_source_refs(
    *,
    source_refs: Optional[Dict[str, Any]],
    external_refs: Optional[Dict[str, Any]],
    evidence: Any,
) -> Dict[str, Any]:
    refs: Dict[str, Any] = {}
    for block in (source_refs, external_refs):
        if isinstance(block, dict):
            refs.update({str(k): v for k, v in block.items() if v not in (None, "", [], {})})
    if isinstance(evidence, dict):
        nested_refs = evidence.get("refs") or evidence.get("source_refs")
        if isinstance(nested_refs, dict):
            refs.update({str(k): v for k, v in nested_refs.items() if v not in (None, "", [], {})})
        for key in (
            "email_message_id",
            "gmail_message_id",
            "slack_message_ts",
            "slack_thread_ts",
            "teams_message_id",
            "erp_record_id",
            "erp_event_id",
            "webhook_event_id",
            "attachment_content_hash",
        ):
            if evidence.get(key) not in (None, "", [], {}):
                refs[key] = evidence[key]
    return refs


def _idempotency_key(
    *,
    explicit: Optional[str],
    box_type: str,
    box_id: str,
    event_type: str,
    source: str,
    refs: Dict[str, Any],
) -> Optional[str]:
    if _text(explicit):
        return _text(explicit)
    stable_ref = None
    for key in (
        "source_event_id",
        "webhook_event_id",
        "slack_message_ts",
        "teams_message_id",
        "gmail_message_id",
        "email_message_id",
        "erp_event_id",
        "erp_record_id",
    ):
        if _text(refs.get(key)):
            stable_ref = f"{key}:{refs[key]}"
            break
    if not stable_ref:
        return None
    digest = hashlib.sha256(
        f"{box_type}:{box_id}:{event_type}:{source}:{stable_ref}".encode("utf-8")
    ).hexdigest()[:24]
    return f"memory-event:{digest}"


def build_memory_event_payload(
    *,
    box_type: str,
    box_id: str,
    organization_id: Optional[str],
    event_type: str,
    source: str,
    actor_type: str = "system",
    actor_id: Optional[str] = None,
    actor_label: Optional[str] = None,
    actor_role: Optional[str] = None,
    actor_team: Optional[str] = None,
    department: Optional[str] = None,
    previous_state: Optional[str] = None,
    resulting_state: Optional[str] = None,
    owner: Any = None,
    dependency: Any = None,
    decision: Any = None,
    rationale: Optional[str] = None,
    evidence: Any = None,
    confidence: Optional[float] = None,
    human_confirmation_status: Optional[str] = None,
    next_action: Optional[str] = None,
    summary: Optional[str] = None,
    source_refs: Optional[Dict[str, Any]] = None,
    external_refs: Optional[Dict[str, Any]] = None,
    occurred_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the structured payload committed into ``audit_events``."""
    normalized_event_type = _normalize_event_type(event_type)
    captured_at = _utc_now()
    refs = _normalize_source_refs(
        source_refs=source_refs,
        external_refs=external_refs,
        evidence=evidence,
    )
    decision_payload = _normalize_decision(
        decision=decision,
        event_type=normalized_event_type,
        rationale=_text(rationale) or None,
        actor_type=actor_type,
        actor_id=actor_id,
    )
    owner_payload = _clean_optional_dict(owner)
    dependency_payload = _clean_optional_dict(dependency)
    memory_summary = _text(summary) or _text(rationale) or normalized_event_type.replace("_", " ")
    execution_state = {
        "owner": owner_payload,
        "dependency": dependency_payload,
        "next_action": _text(next_action) or None,
        "blocked": bool(dependency_payload),
    }
    execution_state = {
        key: value for key, value in execution_state.items()
        if value not in (None, "", [], {})
    }
    memory_event = {
        "schema_version": MEMORY_EVENT_SCHEMA_VERSION,
        "work_item": {
            "box_type": box_type,
            "box_id": box_id,
            "organization_id": organization_id,
        },
        "event_type": normalized_event_type,
        "summary": memory_summary,
        "state": {
            "before": previous_state,
            "after": resulting_state,
        },
        "execution_state": execution_state,
        "decision": decision_payload,
        "rationale": _text(rationale) or decision_payload.get("rationale"),
        "evidence": evidence if evidence not in (None, "", [], {}) else None,
        "source": {
            "surface": source,
            "refs": refs,
            "occurred_at": occurred_at,
            "captured_at": captured_at,
        },
        "confidence": confidence,
        "human_confirmation_status": _text(human_confirmation_status) or None,
    }
    memory_event = {
        key: value for key, value in memory_event.items()
        if value not in (None, "", [], {})
    }
    decision_context = {
        "ui_surface": source,
        "intent": decision_payload.get("type") or normalized_event_type,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "actor_label": actor_label,
        "actor_role": actor_role,
        "actor_team": actor_team,
        "department": department,
        "decision_reason": _text(rationale) or memory_summary,
        "confidence_at_decision": confidence,
        "human_confirmation_status": _text(human_confirmation_status) or None,
        "memory_line": memory_summary,
        "memory_event_schema_version": MEMORY_EVENT_SCHEMA_VERSION,
        "work_item": {
            "box_type": box_type,
            "box_id": box_id,
        },
    }
    decision_context = {
        key: value for key, value in decision_context.items()
        if value not in (None, "", [], {})
    }
    return {
        "memory_event": memory_event,
        "decision_context": decision_context,
        "summary": memory_summary,
        "reason": _text(rationale) or memory_summary,
    }


def commit_memory_event(
    db: Any,
    *,
    box_type: str,
    box_id: str,
    organization_id: Optional[str],
    event_type: str,
    source: str,
    actor_type: str = "system",
    actor_id: Optional[str] = None,
    actor_label: Optional[str] = None,
    actor_role: Optional[str] = None,
    actor_team: Optional[str] = None,
    department: Optional[str] = None,
    previous_state: Optional[str] = None,
    resulting_state: Optional[str] = None,
    owner: Any = None,
    dependency: Any = None,
    decision: Any = None,
    rationale: Optional[str] = None,
    evidence: Any = None,
    confidence: Optional[float] = None,
    human_confirmation_status: Optional[str] = None,
    next_action: Optional[str] = None,
    summary: Optional[str] = None,
    source_refs: Optional[Dict[str, Any]] = None,
    external_refs: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
    correlation_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    run_id: Optional[str] = None,
    occurred_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Commit one structured operational-memory event.

    Callers provide the facts observed or confirmed on a surface; this
    function turns them into a canonical audit row. The row remains the source
    of truth so it can be replayed into the MemoryRecord projection.
    """
    if db is None or not hasattr(db, "append_audit_event"):
        raise AttributeError("commit_memory_event requires db.append_audit_event")
    resolved_box_type = _text(box_type)
    resolved_box_id = _text(box_id)
    resolved_source = _text(source)
    if not resolved_box_type or not resolved_box_id:
        raise ValueError("commit_memory_event requires box_type and box_id")
    if not resolved_source:
        raise ValueError("commit_memory_event requires source")
    normalized_event_type = _normalize_event_type(event_type)
    refs = _normalize_source_refs(
        source_refs=source_refs,
        external_refs=external_refs,
        evidence=evidence,
    )
    payload_json = build_memory_event_payload(
        box_type=resolved_box_type,
        box_id=resolved_box_id,
        organization_id=organization_id,
        event_type=normalized_event_type,
        source=resolved_source,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        actor_role=actor_role,
        actor_team=actor_team,
        department=department,
        previous_state=previous_state,
        resulting_state=resulting_state,
        owner=owner,
        dependency=dependency,
        decision=decision,
        rationale=rationale,
        evidence=evidence,
        confidence=confidence,
        human_confirmation_status=human_confirmation_status,
        next_action=next_action,
        summary=summary,
        source_refs=source_refs,
        external_refs=external_refs,
        occurred_at=occurred_at,
    )
    decision_reason = payload_json.get("reason")
    audit_payload = {
        "box_type": resolved_box_type,
        "box_id": resolved_box_id,
        "organization_id": organization_id,
        "event_type": f"{MEMORY_EVENT_PREFIX}{normalized_event_type}",
        "from_state": previous_state,
        "to_state": resulting_state,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "payload_json": payload_json,
        "external_refs": refs,
        "idempotency_key": _idempotency_key(
            explicit=idempotency_key,
            box_type=resolved_box_type,
            box_id=resolved_box_id,
            event_type=normalized_event_type,
            source=resolved_source,
            refs=refs,
        ),
        "source": resolved_source,
        "correlation_id": correlation_id,
        "workflow_id": workflow_id,
        "run_id": run_id,
        "decision_reason": decision_reason,
        "agent_confidence": confidence,
        "ts": occurred_at or _utc_now(),
    }
    audit_payload = {
        key: value for key, value in audit_payload.items()
        if value not in (None, "", [], {})
    }
    appended = db.append_audit_event(audit_payload)
    if isinstance(appended, dict):
        return appended
    return audit_payload


def _runtime_status(response: Dict[str, Any]) -> str:
    for value in (
        response.get("status"),
        _clean_dict(response.get("result")).get("status"),
    ):
        text = _text(value).lower()
        if text:
            return text
    return "recorded"


def _runtime_reason(
    *,
    payload: Dict[str, Any],
    response: Dict[str, Any],
    status: str,
) -> str:
    result = _clean_dict(response.get("result"))
    for value in (
        payload.get("reason"),
        response.get("reason"),
        result.get("reason"),
        response.get("next_step"),
        status,
    ):
        text = _text(value)
        if text:
            return text
    return status or "recorded"


def _runtime_source(payload: Dict[str, Any]) -> str:
    return (
        _text(payload.get("source_channel"))
        or _text(payload.get("source"))
        or "finance_agent_runtime"
    )


def _runtime_actor_label(payload: Dict[str, Any], actor_id: Optional[str]) -> str:
    for value in (
        payload.get("actor_display"),
        payload.get("actor_email"),
        payload.get("actor_id"),
        actor_id,
    ):
        text = _text(value)
        if text:
            return text
    return "Finance agent"


def _runtime_owner_from_item(item: Dict[str, Any]) -> Dict[str, Any]:
    metadata = _clean_dict(item.get("metadata"))
    owner_email = _text(item.get("owner_email") or metadata.get("owner_email"))
    owner_label = _text(
        item.get("owner_label")
        or metadata.get("owner_label")
        or metadata.get("owner_name")
        or metadata.get("owner_title")
        or owner_email
    )
    return {
        key: value
        for key, value in {
            "id": item.get("owner_id") or metadata.get("owner_id"),
            "email": owner_email or None,
            "label": owner_label or None,
        }.items()
        if value not in (None, "", [], {})
    }


def _runtime_dependency(
    *,
    status: str,
    reason: str,
    owner: Dict[str, Any],
    response: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    normalized = _text(status).lower()
    if normalized not in {
        "blocked",
        "needs_info",
        "needs_field_review",
        "failed",
        "failed_post",
        "payment_failed",
        "error",
    }:
        return None
    owner_label = (
        _text(owner.get("label"))
        or _text(owner.get("email"))
        or ("Vendor / requester" if normalized == "needs_info" else "Finance team")
    )
    return {
        "type": "blocker" if normalized != "needs_info" else "information_request",
        "owner": owner_label,
        "reason": reason or normalized,
        "blockers": response.get("blockers") if isinstance(response.get("blockers"), list) else None,
    }


def _runtime_next_action(
    *,
    intent: str,
    status: str,
    response: Dict[str, Any],
) -> str:
    explicit = _text(response.get("next_step") or response.get("recommended_next_action"))
    if explicit and explicit != "none":
        return explicit.replace("_", " ")
    normalized = _text(status).lower()
    if normalized in {"approved", "posted", "posted_to_erp", "rejected", "closed"}:
        return "No next step."
    if normalized == "needs_info":
        return "Wait for the requested information and resume review."
    if normalized in {"blocked", "needs_field_review"}:
        return "Review blockers and decide the next action."
    if intent == "retry_post":
        return "Review the ERP retry result."
    return "Review the result and decide the next action."


def _runtime_summary(
    *,
    intent: str,
    status: str,
    reason: str,
    source: str,
) -> str:
    action_label = {
        "approve_invoice": "approval",
        "reject_invoice": "rejection",
        "request_info": "information request",
        "post_to_erp": "ERP post",
        "retry_post": "ERP retry",
        "update_invoice_fields": "field update",
        "resolve_field_review": "field review",
        "resolve_entity_route": "entity route",
        "resolve_non_invoice_review": "non-invoice review",
        "snooze_invoice": "snooze",
        "unsnooze_invoice": "unsnooze",
        "classify_document": "classification",
        "reverse_erp_post": "ERP reversal",
        "resubmit_invoice": "resubmission",
        "merge_ap_items": "merge",
        "split_ap_item": "split",
    }.get(intent, intent.replace("_", " "))
    status_label = status.replace("_", " ") if status else "recorded"
    sentence = f"{action_label.capitalize()} {status_label} from {source.replace('_', ' ')}"
    if reason and reason != status:
        sentence = f"{sentence}: {reason}"
    return sentence


def _runtime_source_refs(
    *,
    payload: Dict[str, Any],
    response: Dict[str, Any],
) -> Dict[str, Any]:
    result = _clean_dict(response.get("result"))
    refs = {
        "audit_event_id": response.get("audit_event_id"),
        "email_id": response.get("email_id") or payload.get("email_id"),
        "source_channel_id": payload.get("source_channel_id"),
        "source_message_ref": payload.get("source_message_ref"),
        "action_run_id": payload.get("action_run_id"),
        "correlation_id": payload.get("correlation_id"),
        "erp_reference": response.get("erp_reference") or result.get("erp_reference"),
    }
    return {
        key: value
        for key, value in refs.items()
        if value not in (None, "", [], {})
    }


def _runtime_evidence(
    *,
    intent: str,
    status: str,
    reason: str,
    payload: Dict[str, Any],
    response: Dict[str, Any],
    source_refs: Dict[str, Any],
) -> Dict[str, Any]:
    result = _clean_dict(response.get("result"))
    evidence = {
        "intent": intent,
        "status": status,
        "reason": reason,
        "audit_event_id": response.get("audit_event_id"),
        "policy_precheck": response.get("policy_precheck"),
        "result_status": result.get("status"),
        "result_reason": result.get("reason"),
        "source_refs": source_refs,
    }
    return {
        key: value
        for key, value in evidence.items()
        if value not in (None, "", [], {})
    }


def commit_runtime_memory_event(
    db: Any,
    *,
    organization_id: str,
    intent: str,
    input_payload: Optional[Dict[str, Any]],
    response: Optional[Dict[str, Any]],
    actor_type: str = "user",
    actor_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Capture operational memory for a completed runtime intent.

    Runtime intents are the common path for workspace, Slack, Teams,
    NetSuite, SAP, Gmail bulk, and most AP actions. This helper records the
    operational memory beside the existing runtime audit row without changing
    the state-machine behavior.
    """
    if not isinstance(response, dict) or response.get("idempotency_replayed"):
        return None
    payload = input_payload if isinstance(input_payload, dict) else {}
    ap_item_id = _text(response.get("ap_item_id") or payload.get("ap_item_id"))
    if not ap_item_id:
        return None
    status = _runtime_status(response)
    source = _runtime_source(payload)
    reason = _runtime_reason(payload=payload, response=response, status=status)
    source_refs = _runtime_source_refs(payload=payload, response=response)
    item: Dict[str, Any] = {}
    if hasattr(db, "get_ap_item"):
        try:
            item = db.get_ap_item(ap_item_id) or {}
        except Exception:
            item = {}
    owner = _runtime_owner_from_item(item) if isinstance(item, dict) else {}
    resulting_state = _text((item or {}).get("state")) or status
    runtime_actor_id = (
        _text(payload.get("actor_email"))
        or _text(payload.get("actor_id"))
        or _text(actor_id)
        or "finance_agent_runtime"
    )
    audit_event_id = _text(response.get("audit_event_id"))
    event_type = f"runtime_{intent}_{status}"
    return commit_memory_event(
        db,
        box_type="ap_item",
        box_id=ap_item_id,
        organization_id=organization_id,
        event_type=event_type,
        source=source,
        actor_type=actor_type,
        actor_id=runtime_actor_id,
        actor_label=_runtime_actor_label(payload, actor_id),
        resulting_state=resulting_state,
        owner=owner,
        dependency=_runtime_dependency(
            status=status,
            reason=reason,
            owner=owner,
            response=response,
        ),
        decision={
            "type": intent,
            "status": status,
            "runtime_audit_event_id": audit_event_id or None,
        },
        rationale=reason,
        evidence=_runtime_evidence(
            intent=intent,
            status=status,
            reason=reason,
            payload=payload,
            response=response,
            source_refs=source_refs,
        ),
        confidence=response.get("confidence"),
        human_confirmation_status="confirmed" if runtime_actor_id else None,
        next_action=_runtime_next_action(intent=intent, status=status, response=response),
        summary=_runtime_summary(intent=intent, status=status, reason=reason, source=source),
        source_refs=source_refs,
        idempotency_key=(
            f"memory-event:runtime:{audit_event_id}"
            if audit_event_id
            else None
        ),
        correlation_id=_text(payload.get("correlation_id")) or None,
        run_id=_text(payload.get("action_run_id")) or None,
    )
