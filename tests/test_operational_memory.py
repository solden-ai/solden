from __future__ import annotations

from datetime import datetime, timedelta, timezone

from solden.services.operational_memory import (
    build_decision_ledger,
    build_box_operational_memory_record,
    build_operational_memory_record,
)
from solden.services.memory_events import commit_memory_event
from solden.services.memory_events import commit_runtime_memory_event
from solden.services.operational_memory_capture import (
    capture_operational_memory_event,
    link_observed_event_to_work_item,
)


class _MemoryDB:
    def __init__(self, events, boxes=None, exceptions=None, outcome=None):
        self.events = list(events)
        self.boxes = dict(boxes or {})
        self.exceptions = list(exceptions or [])
        self.outcome = outcome

    def list_box_audit_events(self, box_type, box_id, limit=None, order="asc"):
        rows = [
            event for event in self.events
            if event.get("box_type") == box_type and event.get("box_id") == box_id
        ]
        rows.sort(key=lambda event: event.get("ts") or "", reverse=(order == "desc"))
        return rows if limit is None else rows[:limit]

    def get_generic_box(self, box_type, box_id):
        box = self.boxes.get((box_type, box_id))
        return dict(box) if box else None

    def get_ap_item(self, ap_item_id):
        box = self.boxes.get(("ap_item", ap_item_id))
        return dict(box) if box else None

    def get_ap_item_by_thread(self, organization_id, thread_id):
        for (box_type, _box_id), box in self.boxes.items():
            if (
                box_type == "ap_item"
                and box.get("organization_id") == organization_id
                and box.get("thread_id") == thread_id
            ):
                return dict(box)
        return None

    def get_ap_item_by_message_id(self, organization_id, message_id):
        for (box_type, _box_id), box in self.boxes.items():
            if (
                box_type == "ap_item"
                and box.get("organization_id") == organization_id
                and box.get("message_id") == message_id
            ):
                return dict(box)
        return None

    def list_ap_items(self, organization_id, limit=1000):
        rows = [
            dict(box)
            for (box_type, _box_id), box in self.boxes.items()
            if box_type == "ap_item" and box.get("organization_id") == organization_id
        ]
        return rows[:limit]

    def list_box_exceptions(self, box_type, box_id):
        return [
            exc for exc in self.exceptions
            if exc.get("box_type") == box_type and exc.get("box_id") == box_id
        ]

    def get_box_outcome(self, box_type, box_id):
        if not self.outcome:
            return None
        if self.outcome.get("box_type") == box_type and self.outcome.get("box_id") == box_id:
            return dict(self.outcome)
        return None

    def append_audit_event(self, payload):
        event = {
            "id": payload.get("id") or f"evt-{len(self.events) + 1}",
            "box_type": payload.get("box_type"),
            "box_id": payload.get("box_id") or payload.get("ap_item_id"),
            "event_type": payload.get("event_type"),
            "prev_state": payload.get("from_state"),
            "new_state": payload.get("to_state"),
            "actor_type": payload.get("actor_type"),
            "actor_id": payload.get("actor_id"),
            "payload_json": payload.get("payload_json") or {},
            "external_refs": payload.get("external_refs") or {},
            "idempotency_key": payload.get("idempotency_key"),
            "source": payload.get("source"),
            "correlation_id": payload.get("correlation_id"),
            "workflow_id": payload.get("workflow_id"),
            "run_id": payload.get("run_id"),
            "decision_reason": payload.get("decision_reason"),
            "agent_confidence": payload.get("agent_confidence"),
            "organization_id": payload.get("organization_id"),
            "ts": payload.get("ts") or "2026-06-05T17:00:00Z",
        }
        self.events.append(event)
        return event


def test_decision_ledger_projects_contextual_state_transition():
    events = [
        {
            "id": "evt-1",
            "box_type": "ap_item",
            "box_id": "AP-memory-1",
            "event_type": "state_transition",
            "prev_state": "validated",
            "new_state": "needs_approval",
            "actor_type": "user",
            "actor_id": "controller-1",
            "decision_reason": "Controller granted policy exception",
            "agent_confidence": 0.91,
            "policy_version": "ap-v1",
            "source": "teams",
            "ts": "2026-06-05T10:00:00Z",
            "payload_json": {
                "decision_context": {
                    "ui_surface": "teams",
                    "intent": "grant_exception",
                    "risk_flags_shown": ["po_mismatch"],
                    "confidence_at_decision": 0.88,
                }
            },
            "external_refs": {"teams_message_id": "msg-1"},
        }
    ]

    ledger = build_decision_ledger(events)

    assert len(ledger) == 1
    entry = ledger[0]
    assert entry["event_id"] == "evt-1"
    assert entry["decision_type"] == "grant_exception"
    assert entry["rationale"] == "Controller granted policy exception"
    assert entry["source_surface"] == "teams"
    assert entry["previous_state"] == "validated"
    assert entry["resulting_state"] == "needs_approval"
    assert entry["context_snapshot"]["risk_flags_shown"] == ["po_mismatch"]
    assert entry["evidence_refs"]["teams_message_id"] == "msg-1"


def test_operational_memory_record_keeps_execution_state_and_decision_ledger():
    events = [
        {
            "id": "evt-2",
            "box_type": "ap_item",
            "box_id": "AP-memory-2",
            "event_type": "state_transition",
            "prev_state": "validated",
            "new_state": "needs_approval",
            "actor_type": "agent",
            "actor_id": "ap-agent",
            "decision_reason": "PO mismatch requires controller review",
            "source": "agent_background",
            "ts": "2026-06-05T11:00:00Z",
            "payload_json": {
                "decision_context": {
                    "ui_surface": "agent_background",
                    "intent": "route_for_approval",
                    "validation_gate_at_decision": {"passed": False},
                }
            },
        }
    ]
    item = {
        "id": "AP-memory-2",
        "organization_id": "org-memory",
        "state": "needs_approval",
        "vendor_name": "Memory Vendor",
        "invoice_number": "INV-222",
        "owner_email": "controller@example.com",
        "owner_source": "auto",
        "confidence": 0.82,
        "exception_code": "po_match_required",
        "waiting_condition": {"kind": "approval", "owner": "controller@example.com"},
        "erp_reference": "NS-222",
        "field_confidences": {"amount": 0.94},
    }

    record = build_operational_memory_record(
        item=item,
        timeline=[{"summary": "Routed for approval", "ts": "2026-06-05T11:00:00Z"}],
        exceptions=[
            {
                "id": "exc-1",
                "exception_type": "po_match_required",
                "severity": "high",
                "reason": "PO mismatch requires controller review",
            }
        ],
        outcome=None,
        db=_MemoryDB(events),
        box_type="ap_item",
        box_id="AP-memory-2",
    )

    assert record["record_id"] == "ap_item:AP-memory-2"
    assert record["work_item_ref"]["label"] == "INV-222"
    assert record["execution_state"]["owner"]["email"] == "controller@example.com"
    assert record["execution_state"]["waiting_on"] == "controller@example.com"
    assert record["execution_state"]["waiting_reason"] == "PO mismatch requires controller review"
    assert record["execution_state"]["latest_system_state"]["erp_reference"] == "NS-222"
    assert record["execution_state"]["dependencies"][0]["type"] == "waiting_condition"
    assert record["decision_ledger"][0]["decision_type"] == "route_for_approval"
    assert record["decision_ledger"][0]["summary"] == (
        "Ap-agent routed the work item for approval because PO mismatch requires controller review."
    )
    assert record["context_summary"]["who_owns_it"] == "controller@example.com"
    assert record["memory_narrative"][-1] == "Awaiting approval from controller@example.com."
    assert record["proof"]["field_confidences"]["amount"] == 0.94
    assert record["owner"]["email"] == "controller@example.com"


def test_operational_memory_renders_work_in_progress_story():
    events = [
        {
            "id": "evt-procurement",
            "box_type": "ap_item",
            "box_id": "AP-memory-3",
            "event_type": "state_transition",
            "prev_state": "reviewing",
            "new_state": "review_paused",
            "actor_type": "user",
            "actor_id": "buyer@example.com",
            "decision_reason": "sourcing_exception_raised",
            "source": "email",
            "ts": "2026-06-05T12:00:00Z",
            "payload_json": {
                "decision_context": {
                    "actor_role": "Procurement",
                    "intent": "pause_review",
                    "ui_surface": "email",
                }
            },
        },
        {
            "id": "evt-legal",
            "box_type": "ap_item",
            "box_id": "AP-memory-3",
            "event_type": "state_transition",
            "prev_state": "review_paused",
            "new_state": "exception_approved",
            "actor_type": "user",
            "actor_id": "legal@example.com",
            "source": "teams",
            "ts": "2026-06-05T13:00:00Z",
            "payload_json": {
                "decision_context": {
                    "actor_role": "Legal",
                    "intent": "approve_exception",
                    "ui_surface": "teams",
                }
            },
        },
        {
            "id": "evt-finance",
            "box_type": "ap_item",
            "box_id": "AP-memory-3",
            "event_type": "state_transition",
            "prev_state": "exception_approved",
            "new_state": "budget_reallocation_requested",
            "actor_type": "user",
            "actor_id": "finance@example.com",
            "source": "web",
            "ts": "2026-06-05T14:00:00Z",
            "payload_json": {
                "decision_context": {
                    "actor_role": "Finance",
                    "intent": "request_budget_reallocation",
                    "ui_surface": "web",
                }
            },
        },
    ]
    item = {
        "id": "AP-memory-3",
        "organization_id": "org-memory",
        "state": "needs_approval",
        "subject": "Supplier onboarding exception",
        "metadata": {
            "owner_label": "Operations Director",
            "waiting_action": "sign-off",
        },
    }

    record = build_operational_memory_record(
        item=item,
        timeline=[],
        exceptions=[],
        outcome=None,
        db=_MemoryDB(events),
        box_type="ap_item",
        box_id="AP-memory-3",
    )

    assert record["memory_narrative"] == [
        "Procurement paused review after a sourcing exception was raised.",
        "Legal approved the exception.",
        "Finance requested a budget reallocation.",
        "Awaiting sign-off from Operations Director.",
    ]
    assert record["context_summary"]["what_is_happening"] == (
        "Finance requested a budget reallocation."
    )
    assert record["context_summary"]["who_owns_it"] == "Operations Director"
    assert record["context_summary"]["where_it_happened"] == ["email", "teams", "web"]
    assert record["context_summary"]["what_changed_since_last_step"] == (
        "exception_approved -> budget_reallocation_requested"
    )


def test_box_operational_memory_loads_generic_workflow_box():
    events = [
        {
            "id": "evt-pr-submit",
            "box_type": "purchase_request",
            "box_id": "PR-memory-1",
            "event_type": "purchase_request_submitted",
            "prev_state": "draft",
            "new_state": "submitted",
            "actor_type": "user",
            "actor_id": "requester@example.com",
            "decision_reason": "budget_reallocation_required",
            "source": "slack",
            "ts": "2026-06-05T15:00:00Z",
            "payload_json": {
                "decision_context": {
                    "actor_role": "Finance",
                    "intent": "request_budget_reallocation",
                    "ui_surface": "slack",
                }
            },
        }
    ]
    db = _MemoryDB(
        events,
        boxes={
            ("purchase_request", "PR-memory-1"): {
                "id": "PR-memory-1",
                "box_type": "purchase_request",
                "organization_id": "org-memory",
                "status": "submitted",
                "title": "Office buildout request",
                "owner_label": "Operations Director",
                "waiting_action": "sign-off",
            }
        },
        exceptions=[
            {
                "id": "exc-pr-1",
                "box_type": "purchase_request",
                "box_id": "PR-memory-1",
                "exception_type": "budget_exception",
                "reason": "Budget reallocation is required before approval",
                "severity": "high",
            }
        ],
    )

    record = build_box_operational_memory_record(
        db=db,
        box_type="purchase_request",
        box_id="PR-memory-1",
    )

    assert record["record_id"] == "purchase_request:PR-memory-1"
    assert record["current_state"] == "submitted"
    assert record["work_item_ref"]["label"] == "Office buildout request"
    assert record["context_summary"]["who_owns_it"] == "Operations Director"
    assert record["memory_narrative"] == [
        "Finance requested a budget reallocation because a budget reallocation was required.",
        "Awaiting sign-off from Operations Director.",
    ]
    assert record["open_exceptions"][0]["exception_type"] == "budget_exception"


def test_generic_workflow_read_route_attaches_memory(monkeypatch):
    from solden.api import workflow_routes

    db = _MemoryDB(
        [
            {
                "id": "evt-coi-submit",
                "box_type": "vendor_coi",
                "box_id": "COI-memory-1",
                "event_type": "vendor_coi_submitted",
                "prev_state": "draft",
                "new_state": "submitted",
                "actor_type": "user",
                "actor_id": "admin@example.com",
                "source": "web",
                "ts": "2026-06-05T16:00:00Z",
                "payload_json": {
                    "decision_context": {
                        "actor_role": "Risk",
                        "intent": "submit",
                        "ui_surface": "web",
                    }
                },
            }
        ],
        boxes={
            ("vendor_coi", "COI-memory-1"): {
                "id": "COI-memory-1",
                "box_type": "vendor_coi",
                "organization_id": "org-memory",
                "state": "submitted",
                "vendor": "Globex",
            }
        },
    )
    user = type("User", (), {"organization_id": "org-memory"})()

    monkeypatch.setenv("FEATURE_WORKFLOW_BUILDER", "true")
    monkeypatch.setattr(workflow_routes, "get_db", lambda: db)

    response = workflow_routes.get_box("vendor_coi", "COI-memory-1", user)

    assert response["state"] == "submitted"
    assert response["memory"]["record_id"] == "vendor_coi:COI-memory-1"
    assert response["memory"]["work_item_ref"]["label"] == "Globex"
    assert response["surface_memory"]["contract"] == "solden_memory_surface.v1"
    assert response["surface_memory"]["work_item"] == "Globex"
    assert response["decision_ledger"][0]["source_surface"] == "web"


def test_memory_event_commit_captures_and_projects_ap_exception_memory():
    db = _MemoryDB([])

    row = commit_memory_event(
        db,
        box_type="ap_item",
        box_id="AP-memory-capture-1",
        organization_id="org-memory",
        event_type="blocker_confirmed",
        source="slack",
        actor_type="user",
        actor_id="finance@example.com",
        actor_role="Finance",
        previous_state="needs_approval",
        resulting_state="blocked",
        owner={"label": "CFO delegate", "email": "delegate@example.com"},
        dependency={
            "type": "approval",
            "owner": "CFO delegate",
            "reason": "Sarah is unavailable and the amount exceeds the approval threshold",
        },
        decision={
            "type": "escalate_to_delegate",
            "outcome": "delegate_approval_requested",
        },
        rationale="Approval threshold exceeded and Sarah is unavailable",
        evidence=[
            {"source": "slack", "ref": "thread-123", "description": "Finance escalation thread"},
            {"source": "gmail", "ref": "msg-456", "description": "Vendor follow-up"},
        ],
        confidence=0.93,
        human_confirmation_status="confirmed",
        next_action="Escalate to the CFO delegate and notify the vendor",
        summary="Finance escalated invoice approval to the CFO delegate.",
        source_refs={"slack_thread_ts": "thread-123"},
        idempotency_key="memory-event:AP-memory-capture-1:blocker",
        occurred_at="2026-06-05T17:15:00Z",
    )

    assert row["event_type"] == "memory_event:blocker_confirmed"
    assert row["idempotency_key"] == "memory-event:AP-memory-capture-1:blocker"
    assert row["payload_json"]["memory_event"]["event_type"] == "blocker_confirmed"
    assert row["payload_json"]["memory_event"]["human_confirmation_status"] == "confirmed"
    assert row["payload_json"]["decision_context"]["ui_surface"] == "slack"
    assert row["payload_json"]["decision_context"]["intent"] == "escalate_to_delegate"
    assert row["external_refs"]["slack_thread_ts"] == "thread-123"

    item = {
        "id": "AP-memory-capture-1",
        "organization_id": "org-memory",
        "state": "blocked",
        "invoice_number": "INV-CAP-1",
    }
    record = build_operational_memory_record(
        item=item,
        timeline=[],
        exceptions=[],
        outcome=None,
        db=db,
        box_type="ap_item",
        box_id="AP-memory-capture-1",
    )

    assert record["context_summary"]["what_is_happening"] == (
        "Finance escalated invoice approval to the CFO delegate."
    )
    assert record["context_summary"]["who_owns_it"] == "CFO delegate"
    assert record["context_summary"]["why_it_is_happening"] == (
        "Sarah is unavailable and the amount exceeds the approval threshold"
    )
    assert record["context_summary"]["next_action"] == (
        "Escalate to the CFO delegate and notify the vendor"
    )
    assert record["context_summary"]["where_it_happened"] == ["slack"]
    assert record["execution_state"]["owner_label"] == "CFO delegate"
    assert record["execution_state"]["owner"]["email"] == "delegate@example.com"
    assert record["execution_state"]["dependencies"][0]["type"] == "memory_dependency"
    assert record["decision_ledger"][0]["decision_type"] == "escalate_to_delegate"
    assert record["decision_ledger"][0]["human_confirmation_status"] == "confirmed"
    assert record["proof"]["memory_evidence"][0]["ref"] == "thread-123"


def test_runtime_intent_memory_event_captures_surface_action_context():
    db = _MemoryDB(
        [],
        boxes={
            ("ap_item", "AP-runtime-memory-1"): {
                "id": "AP-runtime-memory-1",
                "organization_id": "org-memory",
                "state": "needs_info",
                "invoice_number": "INV-RUNTIME-1",
                "owner_email": "controller@example.com",
            }
        },
    )

    row = commit_runtime_memory_event(
        db,
        organization_id="org-memory",
        intent="request_info",
        input_payload={
            "ap_item_id": "AP-runtime-memory-1",
            "email_id": "gmail-thread-1",
            "reason": "Vendor needs to send the missing PO",
            "source_channel": "teams",
            "source_channel_id": "conversation-1",
            "source_message_ref": "activity-1",
            "actor_id": "teams-user-1",
            "actor_display": "Mo Finance",
            "correlation_id": "corr-runtime-1",
            "action_run_id": "run-runtime-1",
        },
        response={
            "status": "needs_info",
            "ap_item_id": "AP-runtime-memory-1",
            "email_id": "gmail-thread-1",
            "next_step": "wait_for_vendor_response",
            "audit_event_id": "audit-runtime-1",
            "result": {"status": "needs_info"},
        },
        actor_type="user",
        actor_id="controller@example.com",
    )

    assert row is not None
    assert row["event_type"] == "memory_event:runtime_request_info_needs_info"
    assert row["source"] == "teams"
    assert row["payload_json"]["memory_event"]["source"]["surface"] == "teams"
    assert row["payload_json"]["memory_event"]["decision"]["type"] == "request_info"
    assert row["payload_json"]["memory_event"]["execution_state"]["dependency"]["type"] == "information_request"
    assert row["external_refs"]["source_message_ref"] == "activity-1"
    assert row["idempotency_key"] == "memory-event:runtime:audit-runtime-1"

    record = build_box_operational_memory_record(
        db=db,
        box_type="ap_item",
        box_id="AP-runtime-memory-1",
    )

    assert record["context_summary"]["who_owns_it"] == "controller@example.com"
    assert record["context_summary"]["why_it_is_happening"] == "Vendor needs to send the missing PO"
    assert record["context_summary"]["next_action"] == "wait for vendor response"
    assert record["context_summary"]["where_it_happened"] == ["teams"]
    assert record["decision_ledger"][0]["decision_type"] == "request_info"


def test_capture_loop_commits_confirmed_context_to_memory_event():
    db = _MemoryDB(
        [],
        boxes={
            ("ap_item", "AP-capture-1"): {
                "id": "AP-capture-1",
                "organization_id": "org-test",
                "thread_id": "thread-capture-1",
                "vendor_name": "AWS",
                "invoice_number": "44128",
                "amount": 48210,
                "currency": "USD",
                "state": "needs_approval",
            }
        },
    )

    result = capture_operational_memory_event(
        db,
        organization_id="org-test",
        actor_id="mo@example.com",
        actor_label="Mo",
        observed={
            "source": "slack",
            "source_refs": {"gmail_thread_id": "thread-capture-1", "slack_thread_ts": "171000.1"},
            "event_type": "dependency_identified",
            "summary": "CFO delegate approval is required because Sarah is unavailable.",
            "dependency": {
                "type": "approval_delegate",
                "owner": "CFO delegate",
                "reason": "Sarah is unavailable until Monday.",
            },
            "decision": {
                "type": "escalate_to_delegate",
                "rationale": "Invoice exceeds the approval threshold.",
            },
            "rationale": "Invoice exceeds the approval threshold and Sarah is unavailable.",
            "next_action": "Escalate to CFO delegate and notify vendor.",
            "confidence": 0.84,
            "human_confirmation_status": "confirmed",
        },
    )

    assert result["status"] == "committed"
    assert result["link"]["work_item"]["box_id"] == "AP-capture-1"
    assert result["event"]["event_type"] == "memory_event:dependency_identified"

    record = build_box_operational_memory_record(
        db=db,
        box_type="ap_item",
        box_id="AP-capture-1",
        item=db.get_ap_item("AP-capture-1"),
    )
    assert record["waiting_on"] == "CFO delegate"
    assert record["waiting_reason"] == "Sarah is unavailable until Monday."
    assert record["next_step"] == "Escalate to CFO delegate and notify vendor."
    assert record["decision_ledger"][-1]["human_confirmation_status"] == "confirmed"
    assert any(
        "CFO delegate approval is required" in line
        for line in record["memory_narrative"]
    )


def test_capture_loop_asks_before_committing_unconfirmed_context():
    db = _MemoryDB(
        [],
        boxes={
            ("ap_item", "AP-capture-2"): {
                "id": "AP-capture-2",
                "organization_id": "org-test",
                "invoice_number": "INV-LOW",
                "vendor_name": "AWS",
                "amount": 48210,
                "state": "validated",
            }
        },
    )

    result = capture_operational_memory_event(
        db,
        organization_id="org-test",
        actor_id="agent",
        observed={
            "source": "slack",
            "invoice_number": "INV-LOW",
            "vendor_name": "AWS",
            "amount": 48210,
            "summary": "This may be waiting on Legal confirmation.",
            "dependency": {"owner": "Legal", "reason": "Possible revised vendor terms."},
            "confidence": 0.61,
        },
    )

    assert result["status"] == "needs_confirmation"
    assert result["confirmation_request"]["kind"] == "confirm_memory_event"
    assert "Should Solden record this" in result["confirmation_request"]["question"]
    assert db.events == []


def test_capture_recency_breaks_ties_toward_recent_work_item():
    now = datetime.now(timezone.utc)
    db = _MemoryDB(
        [],
        boxes={
            ("ap_item", "AP-recent"): {
                "id": "AP-recent",
                "organization_id": "org-test",
                "vendor_name": "Globex Software",
                "amount": 1000,
                "state": "needs_approval",
                "created_at": (now - timedelta(days=2)).isoformat(),
            },
            ("ap_item", "AP-stale"): {
                "id": "AP-stale",
                "organization_id": "org-test",
                "vendor_name": "Globex Software",
                "amount": 1000,
                "state": "needs_approval",
                "created_at": (now - timedelta(days=90)).isoformat(),
            },
        },
    )

    result = capture_operational_memory_event(
        db,
        organization_id="org-test",
        actor_id="agent",
        observed={
            "source": "gmail",
            "vendor_name": "Globex Software",
            "amount": 1000,
            "summary": "The $1,000 Globex bill needs a look.",
        },
    )

    # vendor + amount only (0.40) sits below the link bar, so Solden asks rather
    # than silently links, and it suggests the most RECENT matching item.
    assert result["status"] == "needs_link"
    assert result["link"]["status"] == "needs_confirmation"
    assert result["link"]["work_item"]["box_id"] == "AP-recent"
    assert db.events == []


def test_capture_auto_commit_uses_verified_link_score_not_payload_confidence():
    db = _MemoryDB(
        [],
        boxes={
            ("ap_item", "AP-gate"): {
                "id": "AP-gate",
                "organization_id": "org-test",
                "invoice_number": "INV-GATE",
                "vendor_name": "Globex Software",
                "amount": 500,
                "state": "validated",
            }
        },
    )

    # Inferred match invoice(0.45)+vendor(0.20)+amount(0.20)=0.85 -> linked, but
    # below the 0.90 auto-commit bar. A caller-supplied confidence must not
    # override the verified link score and bypass the human.
    result = capture_operational_memory_event(
        db,
        organization_id="org-test",
        actor_id="agent",
        observed={
            "source": "gmail",
            "invoice_number": "INV-GATE",
            "vendor_name": "Globex Software",
            "amount": 500,
            "summary": "Auto-log please.",
            "confidence": 0.99,
            "auto_commit": True,
        },
    )

    assert result["status"] == "needs_confirmation"
    assert db.events == []


def test_capture_auto_commit_commits_on_verified_direct_ref():
    db = _MemoryDB(
        [],
        boxes={
            ("ap_item", "AP-direct"): {
                "id": "AP-direct",
                "organization_id": "org-test",
                "thread_id": "thread-direct",
                "vendor_name": "Globex Software",
                "state": "validated",
            }
        },
    )

    # A verified 1.0 link (direct ref) with auto_commit still commits, so the
    # gate fix does not regress the real auto-commit callers (slack/outlook/erp).
    result = capture_operational_memory_event(
        db,
        organization_id="org-test",
        actor_id="agent",
        observed={
            "source": "outlook",
            "source_refs": {"gmail_thread_id": "thread-direct"},
            "event_type": "outlook_triaged",
            "summary": "Autopilot attached the message to the linked item.",
            "confidence": 1.0,
            "auto_commit": True,
        },
    )

    assert result["status"] == "committed"
    assert result["link"]["confidence"] == 1.0
    assert db.events


def test_link_fuzzy_vendor_matches_reordered_tokens():
    db = _MemoryDB(
        [],
        boxes={
            ("ap_item", "AP-fuzzy"): {
                "id": "AP-fuzzy",
                "organization_id": "org-test",
                "invoice_number": "INV-FZ",
                "vendor_name": "Globex Software",
                "amount": 1000,
                "state": "validated",
            }
        },
    )

    # Reordered tokens: strict equality would miss "software globex" and leave
    # this below the link bar (invoice+amount = 0.65). Fuzzy lifts it to linked.
    link = link_observed_event_to_work_item(
        db,
        organization_id="org-test",
        observed={
            "invoice_number": "INV-FZ",
            "vendor_name": "software globex",
            "amount": 1000,
        },
    )

    assert link["status"] == "linked"
    assert link["work_item"]["box_id"] == "AP-fuzzy"
    assert "vendor" in link["match_evidence"]
    assert link["confidence"] >= 0.72


def test_narrative_vocab_is_box_type_scoped():
    """L4: AP-state narratives apply only to ap_item; other box types get
    box-type-neutral prose, not mis-applied AP semantics."""
    from solden.services.operational_memory import _next_step, _waiting_on, _waiting_reason
    # ap_item "approved" keeps its AP-specific narrative.
    assert "ERP" in _next_step("approved", "", "ap_item")
    assert _waiting_on("approved", "", "ap_item") == "Solden"
    assert "ERP posting" in _waiting_reason(
        state="approved", item={}, exceptions=[], metadata={}, outcome=None, box_type="ap_item",
    )
    # purchase_order "approved" must NOT inherit the AP "post to ERP" prescription.
    po_next = _next_step("approved", "", "purchase_order")
    assert "ERP" not in po_next
    assert po_next == "Review the timeline and decide the next action."
    assert _waiting_on("approved", "", "purchase_order") == "the assigned owner"
    assert "ERP posting" not in _waiting_reason(
        state="approved", item={}, exceptions=[], metadata={}, outcome=None, box_type="purchase_order",
    )
