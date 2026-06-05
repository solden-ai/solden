"""Operational-memory read projection.

Solden's durable object is the work item in flight. The database already
stores the pieces across ``ap_items`` / ``boxes``, ``audit_events``,
``box_exceptions``, and ``box_outcomes``. This module assembles those pieces
into a single MemoryRecord-shaped payload for embedded surfaces and workspace
reads without introducing a new table.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


_TERMINAL_STATES = {"closed", "rejected", "reversed"}
_HUMAN_WAIT_STATES = {
    "needs_approval",
    "needs_second_approval",
    "needs_info",
    "failed_post",
    "payment_failed",
}


def _safe_json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _safe_json_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _humanize_token(value: Any, fallback: str = "") -> str:
    token = str(value or "").strip()
    if not token:
        return fallback
    return token.replace("_", " ").replace("-", " ").strip().capitalize()


def _plain_token(value: Any) -> str:
    return str(value or "").strip().replace("_", " ").replace("-", " ")


def _sentence(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:] if text else text
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _first_exception_reason(item: Dict[str, Any], exceptions: list, metadata: Dict[str, Any]) -> str:
    for value in (
        item.get("exception_reason"),
        metadata.get("exception_reason"),
        metadata.get("needs_info_question"),
        metadata.get("agent_recovery_reason"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    for exc in exceptions or []:
        if not isinstance(exc, dict):
            continue
        for key in ("detail", "message", "description", "reason", "title"):
            text = str(exc.get(key) or "").strip()
            if text:
                return text
        for key in ("code", "exception_code"):
            text = str(exc.get(key) or "").strip()
            if text:
                return _humanize_token(text)
    code = item.get("exception_code") or metadata.get("exception_code")
    return _humanize_token(code)


def _last_timeline_event(timeline: list) -> Optional[Dict[str, Any]]:
    for event in reversed(timeline or []):
        if isinstance(event, dict):
            return {
                "type": event.get("event_type") or event.get("type") or event.get("action"),
                "summary": event.get("summary") or event.get("message") or event.get("title"),
                "created_at": event.get("created_at") or event.get("ts") or event.get("timestamp"),
            }
    return None


def _waiting_on(state: str, owner_email: str) -> str:
    if owner_email:
        return owner_email
    if state in {"awaiting_payment", "payment_in_flight"}:
        return "ERP / payment rail"
    if state in _HUMAN_WAIT_STATES:
        return "Finance team"
    if state in {"received", "validated", "approved", "ready_to_post"}:
        return "Solden"
    if state == "posted_to_erp":
        return "ERP"
    if state in _TERMINAL_STATES:
        return "No one"
    return "Finance team"


def _waiting_reason(
    *,
    state: str,
    item: Dict[str, Any],
    exceptions: list,
    metadata: Dict[str, Any],
    outcome: Optional[Dict[str, Any]],
) -> str:
    exception_reason = _first_exception_reason(item, exceptions, metadata)
    if exception_reason:
        return exception_reason
    if outcome and isinstance(outcome, dict):
        text = str(outcome.get("summary") or outcome.get("reason") or "").strip()
        if text:
            return text
    state_reasons = {
        "received": "The work item has been received and is waiting for validation.",
        "validated": "The work item passed validation and is waiting for routing.",
        "needs_approval": "Approval is required before this work item can move forward.",
        "needs_second_approval": "A second approval is required by policy.",
        "needs_info": "More information is required before this work item can move forward.",
        "approved": "The work item is approved and waiting for ERP posting.",
        "ready_to_post": "The work item is ready to post to the ERP.",
        "posted_to_erp": "The work item is posted in ERP and waiting for payment tracking.",
        "awaiting_payment": "The work item is waiting for the ERP or payment rail to confirm payment.",
        "payment_in_flight": "Payment is in flight and waiting for settlement confirmation.",
        "payment_executed": "Payment has been confirmed and the record is waiting to close.",
        "payment_failed": "Payment failed and needs review.",
        "failed_post": "ERP posting failed and needs review.",
        "closed": "The record is complete.",
        "rejected": "The record was rejected.",
        "reversed": "The ERP post was reversed.",
    }
    return state_reasons.get(state, _humanize_token(state, "The record is waiting for the next step."))


def _next_step(state: str, owner_email: str) -> str:
    owner = owner_email or "the assigned owner"
    next_steps = {
        "received": "Validate extracted fields.",
        "validated": "Route the work item for approval or request missing context.",
        "needs_approval": f"{owner} should approve, reject, or request info.",
        "needs_second_approval": f"{owner} should provide the second approval or reject.",
        "needs_info": f"{owner} should add the missing information.",
        "approved": "Post the approved work item to the ERP.",
        "ready_to_post": "Post the approved work item to the ERP.",
        "posted_to_erp": "Wait for payment confirmation or close when paid.",
        "awaiting_payment": "Wait for payment confirmation.",
        "payment_in_flight": "Wait for settlement confirmation.",
        "payment_executed": "Close the record after final audit checks.",
        "payment_failed": "Review the failed payment and retry, reverse, or close.",
        "failed_post": f"{owner} should fix the ERP posting issue and retry.",
        "closed": "No next step.",
        "rejected": "No next step.",
        "reversed": "No next step.",
    }
    return next_steps.get(state, "Review the timeline and decide the next action.")


def _event_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    payload = event.get("payload_json")
    if isinstance(payload, dict):
        return dict(payload)
    return _safe_json_dict(payload)


def _event_external_refs(event: Dict[str, Any]) -> Dict[str, Any]:
    refs = event.get("external_refs")
    if isinstance(refs, dict):
        return dict(refs)
    return _safe_json_dict(refs)


def _payload_memory_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    memory_event = payload.get("memory_event") if isinstance(payload, dict) else None
    return memory_event if isinstance(memory_event, dict) else {}


def _memory_event_decision(memory_event: Dict[str, Any]) -> Dict[str, Any]:
    decision = memory_event.get("decision") if isinstance(memory_event, dict) else None
    return decision if isinstance(decision, dict) else {}


def _memory_event_execution_state(memory_event: Dict[str, Any]) -> Dict[str, Any]:
    execution_state = memory_event.get("execution_state") if isinstance(memory_event, dict) else None
    return execution_state if isinstance(execution_state, dict) else {}


def _coerce_confidence(*values: Any) -> Optional[float]:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _decision_type(event: Dict[str, Any], context: Dict[str, Any], payload: Dict[str, Any]) -> str:
    memory_event = _payload_memory_event(payload)
    memory_decision = _memory_event_decision(memory_event)
    for value in (
        context.get("intent"),
        memory_decision.get("type"),
        memory_event.get("decision_type"),
        memory_event.get("event_type"),
        payload.get("decision_type"),
        payload.get("decision"),
        payload.get("action"),
        event.get("event_type"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return "event"


def _decision_actor_label(event: Dict[str, Any], context: Dict[str, Any]) -> str:
    for key in ("actor_label", "actor_role", "actor_team", "department", "team"):
        text = str(context.get(key) or "").strip()
        if text:
            return text
    actor_id = str(event.get("actor_id") or context.get("actor_id") or "").strip()
    if actor_id:
        return actor_id
    actor_type = str(event.get("actor_type") or context.get("actor_type") or "").strip()
    return _humanize_token(actor_type, "System")


def _decision_action_phrase(decision_type: str, resulting_state: Any = None) -> str:
    token = str(decision_type or "").strip().lower()
    if token.startswith("memory_event:"):
        token = token.split(":", 1)[1]
    state = str(resulting_state or "").strip().lower()
    mapping = {
        "approve": "approved the work item",
        "approve_invoice": "approved the invoice",
        "approve_exception": "approved the exception",
        "grant_exception": "approved the exception",
        "legal_approved_exception": "approved the exception",
        "pause_review": "paused review",
        "procurement_pause_review": "paused review",
        "request_budget_reallocation": "requested a budget reallocation",
        "finance_request_budget_reallocation": "requested a budget reallocation",
        "request_info": "requested more information",
        "request_invoice_info": "requested more information",
        "reject": "rejected the work item",
        "reject_invoice": "rejected the invoice",
        "route_for_approval": "routed the work item for approval",
        "route_to_approver": "routed the work item for approval",
        "post_to_erp": "posted the work item to the ERP",
        "retry_erp_post": "retried ERP posting",
        "owner_changed": "changed the owner",
        "blocker_confirmed": "confirmed a blocker",
        "context_recorded": "recorded operational context",
        "decision_confirmed": "confirmed a decision",
        "dependency_identified": "identified a dependency",
        "evidence_attached": "attached evidence",
        "escalate_to_delegate": "escalated the work item to a delegate",
        "next_action_set": "set the next action",
    }
    if token in mapping:
        return mapping[token]
    state_mapping = {
        "needs_approval": "routed the work item for approval",
        "needs_second_approval": "routed the work item for second approval",
        "needs_info": "requested more information",
        "approved": "approved the work item",
        "rejected": "rejected the work item",
        "failed_post": "flagged an ERP posting issue",
        "payment_failed": "flagged a payment issue",
        "closed": "closed the work item",
    }
    if state in state_mapping:
        return state_mapping[state]
    fallback = _plain_token(token or state or "recorded a decision").lower()
    return fallback if " " in fallback else f"recorded {fallback}"


def _decision_reason_clause(rationale: Any) -> str:
    text = str(rationale or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith(("because ", "after ", "while ", "when ", "until ")):
        return text
    token = text.strip().lower()
    mapping = {
        "sourcing_exception_raised": "after a sourcing exception was raised",
        "sourcing exception raised": "after a sourcing exception was raised",
        "budget_reallocation_required": "because a budget reallocation was required",
        "po_mismatch": "because the PO did not match",
        "po_match_required": "because PO matching is required",
        "critical_field_low_confidence": "because a critical field had low confidence",
    }
    if token in mapping:
        return mapping[token]
    if not text:
        return ""
    reason = text if text[:2].isupper() else f"{text[0].lower()}{text[1:]}"
    return f"because {reason}"


def _decision_summary_line(
    *,
    event: Dict[str, Any],
    context: Dict[str, Any],
    payload: Dict[str, Any],
    decision_type: str,
    rationale: Any,
) -> str:
    memory_event = _payload_memory_event(payload)
    for key in ("memory_line", "operational_memory_line", "summary_line", "action_summary"):
        text = str(context.get(key) or payload.get(key) or "").strip()
        if text:
            return _sentence(text)
    text = str(memory_event.get("summary") or "").strip()
    if text:
        return _sentence(text)
    actor = _decision_actor_label(event, context)
    action = _decision_action_phrase(decision_type, event.get("new_state"))
    reason = _decision_reason_clause(rationale)
    line = f"{actor} {action}"
    if reason:
        line = f"{line} {reason}"
    return _sentence(line)


def build_decision_ledger(
    audit_events: List[Dict[str, Any]],
    *,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Project audit events into contextual decision-ledger entries.

    The ledger is intentionally event-backed. A future table can materialize
    this, but the canonical source remains ``audit_events``.
    """
    ledger: List[Dict[str, Any]] = []
    for event in audit_events or []:
        if not isinstance(event, dict):
            continue
        payload = _event_payload(event)
        context = payload.get("decision_context")
        context = context if isinstance(context, dict) else {}
        memory_event = _payload_memory_event(payload)
        memory_decision = _memory_event_decision(memory_event)
        rationale = (
            event.get("decision_reason")
            or context.get("decision_reason")
            or memory_decision.get("rationale")
            or memory_event.get("rationale")
            or payload.get("reason")
            or payload.get("summary")
            or memory_event.get("summary")
            or payload.get("message")
        )
        has_state_change = event.get("prev_state") is not None or event.get("new_state") is not None
        if not (context or rationale or has_state_change or memory_event):
            continue
        decision_type = _decision_type(event, context, payload)
        ledger.append({
            "event_id": event.get("id"),
            "decision_type": decision_type,
            "decided_by": {
                "type": event.get("actor_type") or context.get("actor_type"),
                "id": event.get("actor_id") or context.get("actor_id"),
            },
            "actor_label": _decision_actor_label(event, context),
            "decided_at": event.get("ts"),
            "source_surface": (
                context.get("ui_surface")
                or _safe_json_dict(memory_event.get("source")).get("surface")
                or event.get("source")
            ),
            "previous_state": event.get("prev_state"),
            "resulting_state": event.get("new_state"),
            "rationale": rationale,
            "summary": _decision_summary_line(
                event=event,
                context=context,
                payload=payload,
                decision_type=decision_type,
                rationale=rationale,
            ),
            "context_snapshot": context,
            "evidence_refs": _event_external_refs(event),
            "memory_event": memory_event,
            "policy_version": event.get("policy_version") or context.get("policy_version"),
            "confidence": _coerce_confidence(
                event.get("agent_confidence"),
                context.get("confidence_at_decision"),
                memory_event.get("confidence"),
            ),
            "human_confirmation_status": (
                context.get("human_confirmation_status")
                or memory_event.get("human_confirmation_status")
            ),
            "governance_verdict": event.get("governance_verdict"),
            "correlation_id": event.get("correlation_id"),
        })
    return ledger[-limit:] if limit > 0 else ledger


def _fetch_audit_events(db: Any, box_type: str, box_id: str) -> List[Dict[str, Any]]:
    if db is None:
        return []
    try:
        if hasattr(db, "list_box_audit_events"):
            return list(db.list_box_audit_events(box_type=box_type, box_id=box_id, limit=None, order="asc") or [])
        if box_type == "ap_item" and hasattr(db, "list_ap_audit_events"):
            return list(db.list_ap_audit_events(box_id, limit=None, order="asc") or [])
    except Exception:
        return []
    return []


def _fetch_box_exceptions(db: Any, box_type: str, box_id: str) -> List[Dict[str, Any]]:
    if db is None or not hasattr(db, "list_box_exceptions"):
        return []
    try:
        return list(db.list_box_exceptions(box_type=box_type, box_id=box_id) or [])
    except Exception:
        return []


def _fetch_box_outcome(db: Any, box_type: str, box_id: str) -> Optional[Dict[str, Any]]:
    if db is None or not hasattr(db, "get_box_outcome"):
        return None
    try:
        outcome = db.get_box_outcome(box_type=box_type, box_id=box_id)
    except Exception:
        return None
    return outcome if isinstance(outcome, dict) else None


def _dependencies(item: Dict[str, Any], metadata: Dict[str, Any], exceptions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deps: List[Dict[str, Any]] = []
    waiting_condition = item.get("waiting_condition") or metadata.get("waiting_condition")
    waiting_payload = _safe_json_dict(waiting_condition)
    if waiting_payload:
        deps.append({"type": "waiting_condition", "detail": waiting_payload})
    pending_plan = _safe_json_dict(item.get("pending_plan") or metadata.get("pending_plan"))
    if pending_plan:
        deps.append({"type": "pending_plan", "detail": pending_plan})
    for exc in exceptions or []:
        if not isinstance(exc, dict):
            continue
        if exc.get("resolved_at"):
            continue
        deps.append({
            "type": "open_exception",
            "id": exc.get("id"),
            "exception_type": exc.get("exception_type") or exc.get("type"),
            "severity": exc.get("severity"),
            "reason": exc.get("reason") or exc.get("message") or exc.get("title"),
        })
    return deps


def _latest_memory_event(audit_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    for event in reversed(audit_events or []):
        if not isinstance(event, dict):
            continue
        memory_event = _payload_memory_event(_event_payload(event))
        if memory_event:
            return memory_event
    return {}


def _memory_event_dependency(memory_event: Dict[str, Any]) -> Dict[str, Any]:
    execution_state = _memory_event_execution_state(memory_event)
    dependency = execution_state.get("dependency") or memory_event.get("dependency")
    return _safe_json_dict(dependency)


def _memory_event_owner(memory_event: Dict[str, Any]) -> Dict[str, Any]:
    execution_state = _memory_event_execution_state(memory_event)
    owner = execution_state.get("owner") or memory_event.get("owner")
    return _safe_json_dict(owner)


def _memory_event_next_action(memory_event: Dict[str, Any]) -> str:
    execution_state = _memory_event_execution_state(memory_event)
    for value in (
        execution_state.get("next_action"),
        memory_event.get("next_action"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _memory_event_waiting_on(memory_event: Dict[str, Any]) -> str:
    dependency = _memory_event_dependency(memory_event)
    owner = _memory_event_owner(memory_event)
    execution_state = _memory_event_execution_state(memory_event)
    for value in (
        dependency.get("owner"),
        dependency.get("waiting_on"),
        dependency.get("assigned_to"),
        execution_state.get("waiting_on"),
        owner,
    ):
        text = _first_display_value(value)
        if text:
            return text
    return ""


def _memory_event_waiting_reason(memory_event: Dict[str, Any]) -> str:
    dependency = _memory_event_dependency(memory_event)
    decision = _memory_event_decision(memory_event)
    for value in (
        dependency.get("reason"),
        dependency.get("description"),
        decision.get("rationale"),
        memory_event.get("rationale"),
        memory_event.get("summary"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _memory_event_evidence(memory_event: Dict[str, Any]) -> Any:
    evidence = memory_event.get("evidence") if isinstance(memory_event, dict) else None
    return evidence if evidence not in (None, "", [], {}) else None


def _latest_system_state(item: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "erp_reference": item.get("erp_reference"),
        "erp_posted_at": item.get("erp_posted_at"),
        "erp_journal_entry_id": item.get("erp_journal_entry_id"),
        "payment_reference": item.get("payment_reference"),
        "match_status": item.get("match_status") or metadata.get("match_status"),
        "approval_surface": item.get("approval_surface"),
        "approval_policy_version": item.get("approval_policy_version"),
    }


def _proof(item: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "attachment_url": item.get("attachment_url"),
        "attachment_content_hash": item.get("attachment_content_hash"),
        "field_confidences": (
            item.get("field_confidences")
            if isinstance(item.get("field_confidences"), dict)
            else _safe_json_dict(item.get("field_confidences"))
        ),
        "field_provenance": _safe_json_dict(metadata.get("field_provenance")),
        "field_evidence": _safe_json_dict(metadata.get("field_evidence")),
        "source_conflicts": _safe_json_list(metadata.get("source_conflicts")),
    }


def _open_exception_summaries(open_exceptions: List[Dict[str, Any]]) -> List[str]:
    summaries: List[str] = []
    for exc in open_exceptions or []:
        if not isinstance(exc, dict):
            continue
        reason = (
            exc.get("reason")
            or exc.get("message")
            or exc.get("title")
            or exc.get("exception_type")
            or exc.get("type")
        )
        text = str(reason or "").strip()
        if text:
            summaries.append(_sentence(text))
    return summaries


def _unique_nonempty(values: List[Any]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _first_display_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(
            _first_display_value(item)
            for item in value
            if _first_display_value(item)
        )
    if isinstance(value, dict):
        for key in ("label", "name", "email", "id"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return ""
    return str(value or "").strip()


def _change_summary(entry: Optional[Dict[str, Any]]) -> Optional[str]:
    if not entry:
        return None
    previous_state = entry.get("previous_state")
    resulting_state = entry.get("resulting_state")
    if previous_state and resulting_state:
        return f"{previous_state} -> {resulting_state}"
    return entry.get("summary")


def _awaiting_line(
    *,
    state: str,
    waiting_on: str,
    metadata: Dict[str, Any],
    item: Dict[str, Any],
) -> str:
    target = str(waiting_on or "").strip()
    if not target or target == "No one":
        return ""
    action = str(item.get("waiting_action") or metadata.get("waiting_action") or "").strip()
    if action:
        return _sentence(f"Awaiting {action} from {target}")
    if state in {"needs_approval", "needs_second_approval"}:
        return _sentence(f"Awaiting approval from {target}")
    if state == "needs_info":
        return _sentence(f"Awaiting missing information from {target}")
    if state in {"failed_post", "payment_failed"}:
        return _sentence(f"Awaiting review from {target}")
    return _sentence(f"Awaiting the next step from {target}")


def _build_memory_narrative(
    *,
    decision_ledger: List[Dict[str, Any]],
    open_exceptions: List[Dict[str, Any]],
    state: str,
    waiting_on: str,
    metadata: Dict[str, Any],
    item: Dict[str, Any],
) -> List[str]:
    lines = [
        str(entry.get("summary") or "").strip()
        for entry in (decision_ledger or [])[-5:]
        if str(entry.get("summary") or "").strip()
    ]
    if not lines:
        lines.extend(_open_exception_summaries(open_exceptions)[:2])
    awaiting = _awaiting_line(
        state=state,
        waiting_on=waiting_on,
        metadata=metadata,
        item=item,
    )
    if awaiting and awaiting not in lines:
        lines.append(awaiting)
    return lines


def _context_summary(
    *,
    work_item_ref: Dict[str, Any],
    state: str,
    waiting_on: str,
    waiting_reason: str,
    next_step: str,
    decision_ledger: List[Dict[str, Any]],
    open_exceptions: List[Dict[str, Any]],
    proof: Dict[str, Any],
) -> Dict[str, Any]:
    latest_decision = decision_ledger[-1] if decision_ledger else None
    surfaces = _unique_nonempty([
        entry.get("source_surface")
        for entry in decision_ledger or []
    ])
    evidence_refs: List[Dict[str, Any]] = []
    for entry in decision_ledger or []:
        refs = entry.get("evidence_refs")
        if isinstance(refs, dict) and refs:
            evidence_refs.append(refs)
    blocked_on = _open_exception_summaries(open_exceptions)
    return {
        "what_is_happening": (
            latest_decision.get("summary")
            if latest_decision
            else _sentence(f"{work_item_ref.get('label') or 'Work item'} is in {state or 'unknown'}")
        ),
        "why_it_is_happening": waiting_reason,
        "who_owns_it": waiting_on,
        "latest_decision": latest_decision,
        "blocked_on": blocked_on,
        "next_action": next_step,
        "where_it_happened": surfaces,
        "what_changed_since_last_step": _change_summary(latest_decision),
        "evidence": {
            "decision_refs": evidence_refs,
            "attachment_url": proof.get("attachment_url"),
            "attachment_content_hash": proof.get("attachment_content_hash"),
            "field_confidences": proof.get("field_confidences") or {},
            "source_conflicts": proof.get("source_conflicts") or [],
            "memory_evidence": proof.get("memory_evidence"),
        },
    }


def build_operational_memory_record(
    *,
    item: Dict[str, Any],
    timeline: Optional[List[Dict[str, Any]]] = None,
    exceptions: Optional[List[Dict[str, Any]]] = None,
    outcome: Optional[Dict[str, Any]] = None,
    db: Any = None,
    box_type: str = "ap_item",
    box_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the current MemoryRecord projection for one work item."""
    resolved_box_id = str(box_id or item.get("id") or "").strip()
    metadata = _safe_json_dict(item.get("metadata"))
    state = str(item.get("state") or item.get("status") or "").strip().lower()
    owner_email = str(item.get("owner_email") or metadata.get("owner_email") or "").strip()
    open_exceptions = [
        exc for exc in (exceptions or [])
        if isinstance(exc, dict) and not exc.get("resolved_at")
    ]
    audit_events = _fetch_audit_events(db, box_type, resolved_box_id)
    latest_memory_event = _latest_memory_event(audit_events)
    memory_owner = _memory_event_owner(latest_memory_event)
    memory_dependency = _memory_event_dependency(latest_memory_event)
    memory_waiting_on = _memory_event_waiting_on(latest_memory_event)
    memory_waiting_reason = _memory_event_waiting_reason(latest_memory_event)
    memory_next_action = _memory_event_next_action(latest_memory_event)
    memory_evidence = _memory_event_evidence(latest_memory_event)
    if not owner_email:
        owner_email = str(memory_owner.get("email") or "").strip()
    owner = {
        "id": item.get("owner_id") or metadata.get("owner_id") or memory_owner.get("id"),
        "email": owner_email or None,
        "assigned_at": item.get("owner_assigned_at") or metadata.get("owner_assigned_at"),
        "source": item.get("owner_source") or metadata.get("owner_source"),
    }
    decision_ledger = build_decision_ledger(audit_events)
    resolved_timeline = list(timeline or [])
    owner_label = str(
        _first_display_value(memory_owner)
        or item.get("owner_label")
        or metadata.get("owner_label")
        or metadata.get("owner_name")
        or metadata.get("owner_title")
        or owner_email
        or "Unassigned"
    ).strip()
    waiting_on = str(
        memory_waiting_on
        or item.get("waiting_on")
        or metadata.get("waiting_on")
        or metadata.get("waiting_on_label")
        or _first_display_value(metadata.get("approval_sent_to"))
        or _first_display_value(metadata.get("approval_delivery_targets"))
        or (owner_label if owner_label != "Unassigned" else "")
        or _waiting_on(state, owner_email)
    ).strip()
    waiting_reason = _waiting_reason(
        state=state,
        item=item,
        exceptions=list(exceptions or []),
        metadata=metadata,
        outcome=outcome,
    )
    if memory_waiting_reason:
        waiting_reason = memory_waiting_reason
    next_step = memory_next_action or _next_step(state, owner_email)
    last_event = _last_timeline_event(resolved_timeline)
    latest_system_state = _latest_system_state(item, metadata)
    dependencies = _dependencies(item, metadata, list(exceptions or []))
    if memory_dependency:
        dependencies.insert(0, {"type": "memory_dependency", "detail": memory_dependency})
    confidence = _coerce_confidence(item.get("confidence"), metadata.get("confidence"))
    proof = _proof(item, metadata)
    if memory_evidence is not None:
        proof["memory_evidence"] = memory_evidence
    work_item_ref = {
        "id": resolved_box_id,
        "type": item.get("document_type") or box_type,
        "label": (
            item.get("invoice_number")
            or item.get("po_number")
            or item.get("request_id")
            or item.get("reference")
            or item.get("title")
            or item.get("label")
            or item.get("name")
            or item.get("subject")
            or item.get("vendor_name")
            or item.get("vendor")
            or resolved_box_id
        ),
        "external_ref": item.get("erp_reference"),
    }
    memory_narrative = _build_memory_narrative(
        decision_ledger=decision_ledger,
        open_exceptions=open_exceptions,
        state=state,
        waiting_on=waiting_on,
        metadata=metadata,
        item=item,
    )
    context_summary = _context_summary(
        work_item_ref=work_item_ref,
        state=state,
        waiting_on=waiting_on,
        waiting_reason=waiting_reason,
        next_step=next_step,
        decision_ledger=decision_ledger,
        open_exceptions=open_exceptions,
        proof=proof,
    )

    return {
        "memory_record_version": "1.0",
        "record_id": f"{box_type}:{resolved_box_id}",
        "box_id": resolved_box_id,
        "box_type": box_type,
        "work_item_ref": work_item_ref,
        "current_state": item.get("state") or item.get("status"),
        "execution_state": {
            "owner": owner,
            "owner_label": owner_label,
            "waiting_on": waiting_on,
            "waiting_reason": waiting_reason,
            "next_action": next_step,
            "dependencies": dependencies,
            "open_exception_count": len(open_exceptions),
            "confidence": confidence,
            "latest_system_state": latest_system_state,
            "last_event": last_event,
        },
        "context_summary": context_summary,
        "memory_narrative": memory_narrative,
        "decision_ledger": decision_ledger,
        "timeline_event_count": len(audit_events) if audit_events else len(resolved_timeline),
        "open_exceptions": open_exceptions,
        "outcome": outcome,
        "proof": proof,
        "projected_at": datetime.now(timezone.utc).isoformat(),
        # Compatibility fields consumed by the current NetSuite panel.
        "owner": owner,
        "owner_label": owner_label,
        "waiting_on": waiting_on,
        "waiting_reason": waiting_reason,
        "next_step": next_step,
        "last_event": last_event,
    }


def build_box_operational_memory_record(
    *,
    db: Any,
    box_type: str,
    box_id: str,
    item: Optional[Dict[str, Any]] = None,
    timeline: Optional[List[Dict[str, Any]]] = None,
    exceptions: Optional[List[Dict[str, Any]]] = None,
    outcome: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build operational memory for any registered or declarative Box.

    AP is the first production wedge, but the memory substrate is the Box:
    ``(box_type, box_id)`` + audit events + exceptions + outcome. This helper
    keeps callers from reaching for AP-specific table readers when they only
    need the shared work-in-flight memory object.
    """
    resolved_item = item
    if resolved_item is None:
        try:
            from solden.core.box_registry import get_box
            resolved_item = get_box(box_type, box_id, db)
        except Exception:
            resolved_item = None
    if not isinstance(resolved_item, dict) or not resolved_item:
        raise ValueError(f"box_not_found:{box_type}:{box_id}")
    return build_operational_memory_record(
        item=resolved_item,
        timeline=timeline,
        exceptions=_fetch_box_exceptions(db, box_type, box_id) if exceptions is None else exceptions,
        outcome=_fetch_box_outcome(db, box_type, box_id) if outcome is None else outcome,
        db=db,
        box_type=box_type,
        box_id=box_id,
    )
