"""Presentation helpers for rendering operational memory on product surfaces.

The durable object is still the MemoryRecord assembled by
``operational_memory``. This module only projects that record into the compact
field set each surface needs: status, owner, why, decision, evidence, next,
where, and changed.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple


DEFAULT_FIELD_ORDER = (
    "Status",
    "Owner",
    "Waiting on",
    "Why",
    "Decision",
    "Evidence",
    "Next",
    "Where",
    "Changed",
)


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("summary", "label", "name", "email", "id", "type"):
            text = _text(value.get(key))
            if text:
                return text
        parts = []
        for key, item in value.items():
            text = _text(item)
            if text:
                parts.append(f"{str(key).replace('_', ' ')}: {text}")
            if len(parts) >= 2:
                break
        return " | ".join(parts)
    if isinstance(value, list):
        return ", ".join(_text(item) for item in value if _text(item))
    return str(value or "").strip()


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _sentenceish(*values: Any) -> str:
    text = _first_text(*values)
    if not text:
        return ""
    return text.replace("_", " ")


def _latest_decision(memory: Dict[str, Any]) -> Dict[str, Any]:
    context = _dict(memory.get("context_summary"))
    latest = _dict(context.get("latest_decision"))
    if latest:
        return latest
    ledger = _list(memory.get("decision_ledger"))
    for entry in reversed(ledger):
        if isinstance(entry, dict):
            return entry
    return {}


def _evidence_label(memory: Dict[str, Any]) -> str:
    context = _dict(memory.get("context_summary"))
    context_evidence = _dict(context.get("evidence"))
    proof = _dict(memory.get("proof"))
    quality = _dict(
        context_evidence.get("memory_quality")
        or proof.get("memory_quality")
        or memory.get("memory_quality")
    )

    decision_refs = _list(context_evidence.get("decision_refs"))
    if decision_refs:
        surfaces = []
        for ref in decision_refs:
            surface = _first_text(_dict(ref).get("source_surface"), _dict(ref).get("surface"))
            if surface:
                surfaces.append(surface)
        if surfaces:
            return "Decision evidence from " + ", ".join(dict.fromkeys(surfaces))
        rendered_refs = _text(decision_refs)
        if rendered_refs:
            return rendered_refs
        return f"{len(decision_refs)} decision evidence ref{'s' if len(decision_refs) != 1 else ''}"

    attachment_url = _first_text(context_evidence.get("attachment_url"), proof.get("attachment_url"))
    if attachment_url:
        return "Attachment linked"
    attachment_hash = _first_text(
        context_evidence.get("attachment_content_hash"),
        proof.get("attachment_content_hash"),
    )
    if attachment_hash:
        return "Attachment hash verified"
    if _dict(context_evidence.get("field_confidences")) or _dict(proof.get("field_confidences")):
        return "Field evidence linked"
    if _list(context_evidence.get("source_conflicts")) or _list(proof.get("source_conflicts")):
        return "Source conflict evidence linked"
    evidence_status = _first_text(quality.get("evidence_status"))
    verification_status = _first_text(quality.get("verification_status"))
    if evidence_status == "linked":
        if verification_status in {"confirmed", "human_confirmed"}:
            return "Evidence linked and confirmed"
        return "Evidence linked"
    if evidence_status == "provenance_only":
        return "Provenance captured"
    direct = _first_text(
        context_evidence.get("memory_evidence"),
        proof.get("memory_evidence"),
        memory.get("evidence"),
    )
    if direct:
        return direct
    return ""


def _memory_url(memory: Dict[str, Any], item: Optional[Dict[str, Any]], explicit: Optional[str]) -> str:
    if explicit:
        return str(explicit).strip()
    links = _dict(memory.get("links"))
    direct = _first_text(
        memory.get("full_memory_url"),
        memory.get("memory_url"),
        memory.get("workspace_url"),
        memory.get("record_url"),
        links.get("memory"),
        links.get("record"),
    )
    if direct:
        return direct

    work_item_ref = _dict(memory.get("work_item_ref"))
    record_id = _first_text(
        memory.get("box_id"),
        work_item_ref.get("id"),
        _dict(item or {}).get("id"),
    )
    if not record_id:
        raw_record = _first_text(memory.get("record_id"))
        if ":" in raw_record:
            record_id = raw_record.split(":", 1)[1]
    if not record_id:
        return ""
    base = os.getenv("APP_BASE_URL", "https://workspace.soldenai.com").rstrip("/")
    return f"{base}/records/{record_id}"


def build_surface_memory_snapshot(
    memory: Any,
    *,
    item: Optional[Dict[str, Any]] = None,
    surface: str = "generic",
    full_memory_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the canonical field set a surface can render directly."""
    if not isinstance(memory, dict) or not memory:
        return {}

    item = item if isinstance(item, dict) else {}
    execution = _dict(memory.get("execution_state"))
    context = _dict(memory.get("context_summary"))
    owner = _dict(memory.get("owner"))
    execution_owner = _dict(execution.get("owner"))
    latest = _latest_decision(memory)
    blocked_on = _list(context.get("blocked_on"))
    work_item_ref = _dict(memory.get("work_item_ref"))
    surfaces = _list(context.get("where_it_happened"))

    status = _sentenceish(
        context.get("what_is_happening")
        or memory.get("what_is_happening")
        or memory.get("current_state")
        or item.get("state")
        or item.get("status")
    )
    owner_label = _first_text(
        context.get("who_owns_it"),
        memory.get("owner_label"),
        execution.get("owner_label"),
        owner.get("label"),
        owner.get("name"),
        owner.get("email"),
        execution_owner.get("label"),
        execution_owner.get("email"),
        memory.get("waiting_on"),
        execution.get("waiting_on"),
    )
    waiting_on = _first_text(
        memory.get("waiting_on"),
        execution.get("waiting_on"),
        context.get("who_owns_it"),
    )
    why = _sentenceish(
        blocked_on[0] if blocked_on else "",
        context.get("why_it_is_happening"),
        memory.get("waiting_reason"),
        execution.get("waiting_reason"),
        latest.get("rationale"),
    )
    decision = _sentenceish(
        latest.get("summary"),
        latest.get("decision_type"),
        latest.get("type"),
    )
    evidence = _evidence_label(memory)
    next_action = _sentenceish(
        context.get("next_action"),
        memory.get("next_step"),
        execution.get("next_action"),
    )
    where = _sentenceish(surfaces)
    changed = _sentenceish(
        context.get("what_changed_since_last_step"),
        latest.get("resulting_state"),
    )

    fields: List[Dict[str, str]] = []
    for label, value in (
        ("Status", status),
        ("Owner", owner_label),
        ("Waiting on", waiting_on),
        ("Why", why),
        ("Decision", decision),
        ("Evidence", evidence),
        ("Next", next_action),
        ("Where", where),
        ("Changed", changed),
    ):
        if value:
            fields.append({"label": label, "value": value})

    return {
        "surface": surface,
        "contract": "solden_memory_surface.v1",
        "work_item": _first_text(
            work_item_ref.get("label"),
            item.get("invoice_number"),
            item.get("po_number"),
            item.get("id"),
        ),
        "status": status,
        "owner": owner_label,
        "waiting_on": waiting_on,
        "why": why,
        "decision": decision,
        "evidence": evidence,
        "next": next_action,
        "where": where,
        "changed": changed,
        "full_memory_url": _memory_url(memory, item, full_memory_url),
        "fields": fields,
    }


def memory_fact_pairs(
    memory: Any,
    *,
    item: Optional[Dict[str, Any]] = None,
    labels: Sequence[str] = DEFAULT_FIELD_ORDER,
    max_facts: int = 8,
) -> List[Tuple[str, str]]:
    snapshot = build_surface_memory_snapshot(memory, item=item)
    allowed = set(labels)
    pairs = [
        (field["label"], field["value"])
        for field in snapshot.get("fields", [])
        if field.get("label") in allowed and field.get("value")
    ]
    return pairs[: max(1, int(max_facts))]


def adaptive_card_memory_facts(
    memory: Any,
    *,
    item: Optional[Dict[str, Any]] = None,
    labels: Sequence[str] = DEFAULT_FIELD_ORDER,
    max_facts: int = 8,
) -> List[Dict[str, str]]:
    return [
        {"title": label, "value": value[:220]}
        for label, value in memory_fact_pairs(memory, item=item, labels=labels, max_facts=max_facts)
    ]


def render_slack_memory_summary(
    memory: Any,
    *,
    item: Optional[Dict[str, Any]] = None,
    heading: str = "Solden memory",
    labels: Sequence[str] = DEFAULT_FIELD_ORDER,
    max_facts: int = 6,
) -> str:
    snapshot = build_surface_memory_snapshot(memory, item=item)
    pairs = memory_fact_pairs(memory, item=item, labels=labels, max_facts=max_facts)
    if not pairs and not snapshot.get("full_memory_url"):
        return ""
    lines = [f"*{label}:* {value}" for label, value in pairs]
    full_memory_url = str(snapshot.get("full_memory_url") or "").strip()
    if full_memory_url:
        lines.append(f"*Full memory:* <{full_memory_url}|Open in Solden>")
    return f"*{heading}:*\n" + "\n".join(lines)
