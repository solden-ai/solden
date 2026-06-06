"""Operational-memory invariants.

This module is intentionally small and boring: memory is a product primitive,
so committed memory payloads must have a minimum canonical shape and primary
source surfaces must stay wired to the memory write path.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple


class MemoryInvariantError(ValueError):
    """Raised when a memory payload is not a canonical memory event."""


@dataclass(frozen=True)
class MemoryCoverageSurface:
    name: str
    path: str
    required_tokens: Tuple[str, ...]


PRIMARY_MEMORY_COVERAGE_SURFACES: Tuple[MemoryCoverageSurface, ...] = (
    MemoryCoverageSurface(
        name="runtime_intents",
        path="solden/services/finance_agent_runtime.py",
        required_tokens=("_commit_intent_memory_event", "commit_runtime_memory_event"),
    ),
    MemoryCoverageSurface(
        name="erp_intake",
        path="solden/services/intake_adapter.py",
        required_tokens=("_capture_intake_memory_event", "capture_operational_memory_event"),
    ),
    MemoryCoverageSurface(
        name="outlook_processor",
        path="solden/services/outlook_email_processor.py",
        required_tokens=("_capture_outlook_memory_event", "capture_operational_memory_event"),
    ),
    MemoryCoverageSurface(
        name="slack_reply_sync",
        path="solden/api/slack_invoices.py",
        required_tokens=("slack_reply_synced", "capture_operational_memory_event"),
    ),
    MemoryCoverageSurface(
        name="workspace_capture_api",
        path="solden/api/workspace_records.py",
        required_tokens=("/memory-events/capture", "capture_operational_memory_event"),
    ),
    MemoryCoverageSurface(
        name="gmail_extension_capture_api",
        path="solden/api/gmail_extension.py",
        required_tokens=("/memory-events/capture", "capture_operational_memory_event"),
    ),
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def memory_event_missing_fields(payload_json: Dict[str, Any]) -> list[str]:
    payload = _dict(payload_json)
    memory_event = _dict(payload.get("memory_event"))
    work_item = _dict(memory_event.get("work_item"))
    source = _dict(memory_event.get("source"))
    decision = _dict(memory_event.get("decision"))
    missing: list[str] = []

    required_values = {
        "memory_event": memory_event,
        "memory_event.schema_version": memory_event.get("schema_version"),
        "memory_event.work_item.box_type": work_item.get("box_type"),
        "memory_event.work_item.box_id": work_item.get("box_id"),
        "memory_event.event_type": memory_event.get("event_type"),
        "memory_event.summary": memory_event.get("summary"),
        "memory_event.source.surface": source.get("surface"),
        "memory_event.source.captured_at": source.get("captured_at"),
        "memory_event.decision.type": decision.get("type"),
        "decision_context": payload.get("decision_context"),
        "summary": payload.get("summary"),
        "reason": payload.get("reason"),
    }
    for key, value in required_values.items():
        if isinstance(value, dict):
            if not value:
                missing.append(key)
        elif not _text(value):
            missing.append(key)
    return missing


def memory_event_invariant_violations(payload_json: Dict[str, Any]) -> list[str]:
    violations = memory_event_missing_fields(payload_json)
    payload = _dict(payload_json)
    memory_event = _dict(payload.get("memory_event"))

    confidence = memory_event.get("confidence")
    if confidence not in (None, ""):
        try:
            numeric = float(confidence)
        except (TypeError, ValueError):
            violations.append("memory_event.confidence must be numeric")
        else:
            if not math.isfinite(numeric) or numeric < 0 or numeric > 1:
                violations.append("memory_event.confidence must be between 0 and 1")

    return violations


def assert_memory_event_payload(payload_json: Dict[str, Any]) -> None:
    violations = memory_event_invariant_violations(payload_json)
    if violations:
        raise MemoryInvariantError(
            "memory_event_invariant_violation: " + ", ".join(violations)
        )


def missing_coverage_tokens(
    *,
    surface: MemoryCoverageSurface,
    source_text: str,
) -> list[str]:
    return [
        token
        for token in surface.required_tokens
        if token not in source_text
    ]


def all_coverage_paths(
    surfaces: Iterable[MemoryCoverageSurface] = PRIMARY_MEMORY_COVERAGE_SURFACES,
) -> list[str]:
    return [surface.path for surface in surfaces]
