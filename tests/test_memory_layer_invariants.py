from __future__ import annotations

from pathlib import Path

import pytest

from solden.services.audit_memory import ensure_memory_payload_for_audit_event
from solden.services.memory_events import commit_memory_event
from solden.services.memory_invariants import (
    PRIMARY_MEMORY_COVERAGE_SURFACES,
    MemoryInvariantError,
    assert_memory_event_payload,
    assert_work_item_audit_event_memory_payload,
    audit_event_requires_operational_memory,
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
    memory_event = row["payload_json"]["memory_event"]
    assert memory_event["evidence"]["captured_from"] == "slack"
    assert memory_event["evidence"]["source_refs"]["slack_thread_ts"] == "171000.1"
    assert memory_event["quality"]["evidence_status"] == "linked"
    assert memory_event["quality"]["verification_status"] == "confirmed"


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
    assert "memory_event.evidence" in violations
    assert "memory_event.quality" in violations


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
                    "evidence": {
                        "captured_from": "workspace",
                        "event_type": "decision_recorded",
                    },
                    "quality": {
                        "evidence_status": "provenance_only",
                        "verification_status": "system_observed",
                    },
                    "confidence": confidence,
                },
                "decision_context": {"intent": "approve_exception"},
                "summary": "Finance approved the exception.",
                "reason": "Exception was approved by policy owner.",
            }
        )

        assert "memory_event.confidence must be between 0 and 1" in violations


def test_work_item_audit_events_require_canonical_operational_memory():
    assert audit_event_requires_operational_memory(
        box_type="payment_request",
        box_id="PAYREQ-1",
    )

    with pytest.raises(MemoryInvariantError):
        assert_work_item_audit_event_memory_payload(
            box_type="payment_request",
            box_id="PAYREQ-1",
            payload_json={"summary": "Payment request changed state."},
        )


def test_reference_audit_events_do_not_require_operational_memory():
    for box_type in ("organization", "vendor", "user", "workspace_audit", "audit_export"):
        assert not audit_event_requires_operational_memory(
            box_type=box_type,
            box_id="ref-1",
        )
        assert_work_item_audit_event_memory_payload(
            box_type=box_type,
            box_id="ref-1",
            payload_json={"summary": "Reference audit row."},
        )


def test_memory_event_builder_records_provenance_when_evidence_is_not_explicit():
    db = _MemoryDB()

    row = commit_memory_event(
        db,
        box_type="close_task",
        box_id="CLOSE-1",
        organization_id="org-memory",
        event_type="owner_changed",
        source="workspace",
        actor_type="user",
        actor_id="controller@example.com",
        decision={"type": "assign_owner"},
        rationale="Controller assigned the accrual review to finance ops.",
        summary="Controller assigned the accrual review.",
    )

    assert memory_event_invariant_violations(row["payload_json"]) == []
    memory_event = row["payload_json"]["memory_event"]
    assert memory_event["evidence"]["captured_from"] == "workspace"
    assert memory_event["evidence"]["event_type"] == "owner_changed"
    assert memory_event["quality"]["evidence_status"] == "provenance_only"
    assert memory_event["quality"]["verification_status"] == "system_observed"


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
    assert memory_event["evidence"]["captured_from"] == "workspace_spa"
    assert memory_event["quality"]["evidence_status"] == "linked"
    assert payload_json["decision_context"]["ui_surface"] == "workspace_spa"


def test_existing_memory_event_payloads_are_upgraded_before_validation():
    payload_json = ensure_memory_payload_for_audit_event(
        {
            "event_type": "decision_recorded",
            "actor_type": "user",
            "actor_id": "finance@example.com",
            "source": "workspace",
            "organization_id": "org-memory",
            "ts": "2026-06-06T12:00:00+00:00",
        },
        box_type="procurement_request",
        box_id="REQ-memory-3",
        payload_json={
            "memory_event": {
                "schema_version": "1.0",
                "work_item": {
                    "box_type": "procurement_request",
                    "box_id": "REQ-memory-3",
                    "organization_id": "org-memory",
                },
                "event_type": "decision_recorded",
                "summary": "Legal approved the sourcing exception.",
                "source": {
                    "surface": "workspace",
                    "captured_at": "2026-06-06T12:00:00+00:00",
                },
                "decision": {"type": "legal_approved_exception"},
            },
            "decision_context": {"intent": "legal_approved_exception"},
            "summary": "Legal approved the sourcing exception.",
            "reason": "Exception was approved by legal.",
        },
        external_refs={"audit_event_id": "evt-legacy-1"},
        now="2026-06-06T12:00:00+00:00",
    )

    assert_memory_event_payload(payload_json)
    memory_event = payload_json["memory_event"]
    assert memory_event["evidence"]["source_refs"]["audit_event_id"] == "evt-legacy-1"
    assert memory_event["quality"]["evidence_status"] == "linked"


def test_primary_memory_sources_remain_wired():
    repo_root = Path(__file__).resolve().parents[1]

    for surface in PRIMARY_MEMORY_COVERAGE_SURFACES:
        source_path = repo_root / surface.path
        assert source_path.exists(), f"{surface.name} missing file: {surface.path}"
        source_text = source_path.read_text(encoding="utf-8")

        missing = missing_coverage_tokens(surface=surface, source_text=source_text)
        assert missing == [], f"{surface.name} is missing memory wiring tokens: {missing}"
