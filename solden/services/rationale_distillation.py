"""Distill the why behind a decision from the conversation we already hold.

Tribal-knowledge Build 1. Operators often decide with a one-word rationale
while the real "why" sits in the email/Slack context already linked to the
work item. When a decision commits with a THIN ``human_rationale``, this
service reads the PERSISTED conversation context (the invoice email excerpt +
the timeline's captured crumbs — Slack replies, request-info questions, prior
rationales) and asks the LLM for a strictly extractive proposed rationale.

Hard rules:

* Strictly post-decision, fire-and-forget, best-effort — a distillation
  failure can never break or delay the decision itself.
* Strictly extractive — the prompt instructs the model to answer
  ``INSUFFICIENT`` when the excerpts don't show a reason, and we store
  nothing in that case. No plausible-but-invented whys.
* Never impersonates the human — the result is committed as its own
  follow-up memory event (``rationale_distilled``) with
  ``human_confirmation_status="machine_distilled"`` and provenance refs.
  The audit chain is append-only; the decision row is never mutated. A
  human confirm (``rationale_confirmed``) promotes it.
* Phase 1 reads persisted content only (no live Gmail/Slack/Teams fetch).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# A rationale is "thin" when it is empty, shorter than this, or a stock token.
THIN_RATIONALE_MIN_CHARS = 20
_STOCK_TOKENS = {
    "ok", "okay", "yes", "approve", "approved", "reject", "rejected", "done",
    "lgtm", "fine", "request_info", "needs_info", "approved_in_slack",
    "rejected_in_slack", "approved_in_teams", "rejected_in_teams",
    "approved_in_gmail", "rejected_in_gmail",
}

# Surface-injected default reasons are machine labels, never an operator's
# why — e.g. ``approved_in_netsuite_panel``, ``info_requested_from_sap_fiori_
# panel``. Matching the SHAPE (verb + in/from/via + surface, snake_case, no
# spaces) instead of enumerating surfaces: the enumeration above missed every
# ERP panel because it only listed the surfaces in mind on the day it was
# written.
_SURFACE_DEFAULT_RE = re.compile(
    r"^(approved|rejected|declined|info_requested|requested_info|escalated)"
    r"_(in|from|via)_[a-z0-9_]+$"
)

_INSUFFICIENT_TOKEN = "INSUFFICIENT"
_MAX_CONTEXT_CHARS = 12_000
_MAX_TIMELINE_EVENTS = 40


def is_thin_rationale(text: Any) -> bool:
    """True when the operator's rationale carries no real why."""
    s = " ".join(str(text or "").strip().split())
    if not s:
        return True
    token = s.lower().strip(".!")
    if token in _STOCK_TOKENS:
        return True
    if _SURFACE_DEFAULT_RE.match(token):
        return True
    return len(s) < THIN_RATIONALE_MIN_CHARS


def _safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value or "{}")
            return decoded if isinstance(decoded, dict) else {}
        except Exception:
            return {}
    return {}


def gather_decision_context(
    db: Any, *, ap_item_id: str, organization_id: str
) -> Tuple[str, Dict[str, Any]]:
    """Compose the persisted conversation context for one work item.

    Returns ``(context_text, source_refs)``. Persisted content only: item
    facts, the intake email's snippet/body excerpt (4000 chars at capture),
    and conversational crumbs from the timeline (Slack-reply summaries,
    request-info questions, prior rationales/summaries). The refs record
    exactly which sources fed the context, for provenance on the event.
    """
    item = db.get_ap_item(ap_item_id) or {}
    if str(item.get("organization_id") or "") != organization_id:
        return "", {}
    metadata = _safe_dict(item.get("metadata"))

    parts: List[str] = []
    refs: Dict[str, Any] = {}

    facts = (
        f"Work item: vendor={item.get('vendor_name') or 'unknown'}, "
        f"amount={item.get('amount')} {item.get('currency') or ''}, "
        f"invoice={item.get('invoice_number') or 'n/a'}, state={item.get('state')}"
    )
    parts.append(facts)

    snippet = str(metadata.get("source_snippet") or "").strip()
    body = str(metadata.get("source_body_excerpt") or "").strip()
    if snippet or body:
        parts.append("Intake email:\n" + "\n".join(p for p in (snippet, body) if p))
        if item.get("thread_id"):
            refs["gmail_thread_id"] = item.get("thread_id")

    try:
        events = db.list_ap_audit_events(ap_item_id, order="asc") or []
    except TypeError:
        events = db.list_ap_audit_events(ap_item_id) or []
    except Exception:
        events = []

    crumbs: List[str] = []
    contributing_event_ids: List[str] = []
    for event in events[-_MAX_TIMELINE_EVENTS:]:
        payload = _safe_dict(event.get("payload_json"))
        memory_event = _safe_dict(payload.get("memory_event"))
        texts: List[str] = []
        for candidate in (
            memory_event.get("summary"),
            _safe_dict(memory_event.get("evidence")).get("summary"),
            memory_event.get("rationale"),
            event.get("decision_reason"),
        ):
            s = str(candidate or "").strip()
            # Skip machine tokens and dupes; keep human-ish prose.
            if s and not is_thin_rationale(s) and s not in texts:
                texts.append(s)
        if not texts:
            continue
        actor = str(event.get("actor_id") or "").strip()
        ts = str(event.get("ts") or event.get("created_at") or "").strip()
        crumbs.append(f"[{ts}] {actor}: " + " | ".join(texts))
        if event.get("id"):
            contributing_event_ids.append(str(event["id"]))

    if crumbs:
        parts.append("Timeline notes and replies:\n" + "\n".join(crumbs))
        refs["audit_event_ids"] = contributing_event_ids[-20:]

    return "\n\n".join(parts)[:_MAX_CONTEXT_CHARS], refs


def _build_prompt(context_text: str, decision_intent: str) -> str:
    return (
        "You are reading the persisted context around an accounts-payable work "
        f"item on which an operator just performed: {decision_intent}.\n\n"
        "From ONLY the excerpts below, state in 1-2 sentences WHY the operator "
        "made this decision. Rules:\n"
        "- Use only reasons explicitly present or directly evidenced in the "
        "excerpts. Do not infer, generalize, or invent.\n"
        f"- If the excerpts do not show a reason, reply exactly: {_INSUFFICIENT_TOKEN}\n"
        "- No preamble, no quotes around the answer, plain prose.\n\n"
        f"Excerpts:\n{context_text}"
    )


async def distill_rationale_for_decision(
    db: Any,
    *,
    organization_id: str,
    ap_item_id: str,
    decision_audit_event_id: Optional[str],
    decision_intent: str,
    actor_id: Optional[str] = None,
    existing_rationale: Any = None,
    correlation_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Distill + commit a proposed rationale. Returns the committed row or None.

    Callers must treat this as best-effort (it is spawned fire-and-forget after
    the decision commits); it also guards itself end to end.
    """
    from solden.core.feature_flags import is_rationale_distillation_enabled

    if not is_rationale_distillation_enabled():
        return None
    if not is_thin_rationale(existing_rationale):
        return None
    if not (organization_id and ap_item_id):
        return None

    try:
        context_text, source_refs = gather_decision_context(
            db, ap_item_id=ap_item_id, organization_id=organization_id
        )
        if not context_text:
            return None

        from solden.core.llm_gateway import LLMAction, get_llm_gateway

        gateway = get_llm_gateway()
        resp = await gateway.call(
            LLMAction.DISTILL_DECISION_RATIONALE,
            messages=[{"role": "user", "content": _build_prompt(context_text, decision_intent)}],
            organization_id=organization_id,
            ap_item_id=ap_item_id,
        )
        distilled = str(getattr(resp, "content", "") or "").strip()
        if not distilled or _INSUFFICIENT_TOKEN in distilled.upper()[:40]:
            logger.debug(
                "[rationale_distillation] insufficient evidence for %s", ap_item_id
            )
            return None
        distilled = distilled[:2000]

        from solden.services.memory_events import commit_memory_event

        # The decision event is the source this rationale attaches to, so its
        # id rides in source_refs (surfaces use it to pin the distilled why to
        # the decision's timeline entry).
        refs = dict(source_refs)
        if decision_audit_event_id:
            refs["decision_audit_event_id"] = str(decision_audit_event_id)
        row = commit_memory_event(
            db,
            box_type="ap_item",
            box_id=ap_item_id,
            organization_id=organization_id,
            event_type="rationale_distilled",
            source="rationale_distillation",
            actor_type="agent",
            actor_id="rationale_distiller",
            actor_label="Solden",
            decision={
                "type": decision_intent,
                "made_by": {"type": "user", "id": actor_id or ""},
            },
            rationale=distilled,
            summary=f"Solden's read of the thread: {distilled}"[:500],
            evidence={
                "items": [{"type": "persisted_context", "refs": source_refs}],
                "source_refs": refs,
            },
            human_confirmation_status="machine_distilled",
            source_refs=refs,
            correlation_id=correlation_id,
        )
        return row
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[rationale_distillation] failed for %s/%s: %s",
            organization_id, ap_item_id, exc,
        )
        return None
