from __future__ import annotations

from pathlib import Path

import pytest

from solden.services.audit_memory import ensure_memory_payload_for_audit_event
from solden.services.memory_events import commit_memory_event
from solden.services.memory_invariants import (
    PRIMARY_MEMORY_COVERAGE_SURFACES,
    MemoryInvariantError,
    assert_memory_event_payload,
    memory_event_invariant_violations,
    missing_coverage_tokens,
)


class _MemoryDB:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def append_audit_event(self, payload: dict) -> dict:
        row = {
            "id": f"evt-{len(self.events) + 1}",
            "box_type": payload.get("box_type"),
            "box_id": payload.get("box_id"),
            "event_type": payload.get("event_type"),
            "payload_json": payload.get("payload_json") or {},
            "external_refs": payload.get("external_refs") or {},
            "source": payload.get("source"),
            "organization_id": payload.get("organization_id"),
            "ts": payload.get("ts"),
        }
        self.events.append(row)
        return row


def test_committed_memory_event_satisfies_required_payload_invariants():
    db = _MemoryDB()

    row = commit_memory_event(
        db,
        box_type="procurement_request",
        box_id="REQ-memory-1",
        organization_id="org-memory",
        event_type="review_paused",
        source="slack",
        actor_type="user",
        actor_id="procurement@example.com",
        resulting_state="blocked",
        owner={"email": "ops@example.com", "label": "Operations Director"},
        dependency={
            "type": "sign_off",
            "owner": "Operations Director",
            "reason": "Budget reallocation needs approval",
        },
        decision={
            "type": "pause_review",
            "outcome": "awaiting_operations_sign_off",
        },
        rationale="Finance requested a budget reallocation before approval can continue.",
        evidence={"slack_thread_ts": "171000.1", "source": "slack"},
        confidence=0.92,
        human_confirmation_status="confirmed",
        next_action="Wait for Operations Director sign-off",
        summary="Procurement paused review after finance requested a budget reallocation.",
    )

    assert row["event_type"] == "memory_event:review_paused"
    assert memory_event_invariant_violations(row["payload_json"]) == []


def test_memory_payload_invariants_reject_plain_audit_payloads():
    with pytest.raises(MemoryInvariantError) as exc:
        assert_memory_event_payload({"summary": "state changed"})

    message = str(exc.value)
    assert "memory_event" in message
    assert "decision_context" in message


def test_memory_payload_invariants_reject_missing_core_fields():
    violations = memory_event_invariant_violations(
        {
            "memory_event": {
                "schema_version": "1.0",
                "work_item": {"box_type": "ap_item"},
                "event_type": "decision_recorded",
                "summary": "Finance approved the exception.",
                "source": {"captured_at": "2026-06-06T12:00:00+00:00"},
                "decision": {},
            },
            "decision_context": {"intent": "approve_exception"},
            "summary": "Finance approved the exception.",
            "reason": "Exception was approved by policy owner.",
        }
    )

    assert "memory_event.work_item.box_id" in violations
    assert "memory_event.source.surface" in violations
    assert "memory_event.decision.type" in violations


def test_memory_payload_invariants_reject_invalid_confidence():
    for confidence in (1.4, float("nan")):
        violations = memory_event_invariant_violations(
            {
                "memory_event": {
                    "schema_version": "1.0",
                    "work_item": {"box_type": "ap_item", "box_id": "AP-1"},
                    "event_type": "decision_recorded",
                    "summary": "Finance approved the exception.",
                    "source": {
                        "surface": "workspace",
                        "captured_at": "2026-06-06T12:00:00+00:00",
                    },
                    "decision": {"type": "approve_exception"},
                    "confidence": confidence,
                },
                "decision_context": {"intent": "approve_exception"},
                "summary": "Finance approved the exception.",
                "reason": "Exception was approved by policy owner.",
            }
        )

        assert "memory_event.confidence must be between 0 and 1" in violations


def test_thin_audit_rows_are_promoted_to_operational_memory():
    payload_json = ensure_memory_payload_for_audit_event(
        {
            "event_type": "state_transition",
            "from_state": "draft",
            "to_state": "blocked",
            "actor_type": "user",
            "actor_id": "finance@example.com",
            "source": "workspace_spa",
            "decision_reason": "Procurement paused review after budget changed.",
            "organization_id": "org-memory",
            "ts": "2026-06-06T12:00:00+00:00",
        },
        box_type="procurement_request",
        box_id="REQ-memory-2",
        payload_json={"waiting_condition": {"owner": "Operations Director"}},
        external_refs={"slack_thread_ts": "171000.2"},
        now="2026-06-06T12:00:00+00:00",
    )

    assert_memory_event_payload(payload_json)
    memory_event = payload_json["memory_event"]
    assert memory_event["work_item"]["box_type"] == "procurement_request"
    assert memory_event["work_item"]["box_id"] == "REQ-memory-2"
    assert memory_event["state"]["before"] == "draft"
    assert memory_event["state"]["after"] == "blocked"
    assert memory_event["execution_state"]["dependency"]["owner"] == "Operations Director"
    assert memory_event["changes"]["event_type"] == "state_transition"
    assert payload_json["decision_context"]["ui_surface"] == "workspace_spa"


def test_primary_memory_sources_remain_wired():
    repo_root = Path(__file__).resolve().parents[1]

    for surface in PRIMARY_MEMORY_COVERAGE_SURFACES:
        source_path = repo_root / surface.path
        assert source_path.exists(), f"{surface.name} missing file: {surface.path}"
        source_text = source_path.read_text(encoding="utf-8")

        missing = missing_coverage_tokens(surface=surface, source_text=source_text)
        assert missing == [], f"{surface.name} is missing memory wiring tokens: {missing}"
