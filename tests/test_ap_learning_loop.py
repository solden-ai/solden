from __future__ import annotations

from solden.core.database import SoldenDB
from solden.services.agent_memory import AgentMemoryService
from solden.services.ap_learning_loop import (
    PRIVATE_OUTCOME_EVAL_TYPE,
    APLearningLoopService,
    run_scheduled_ap_learning_loop_evals,
)
from solden.services.memory_events import commit_memory_event


ORG_ID = "org-learning-loop"
EMPTY_ORG_ID = "org-learning-empty"


def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLDEN_SECRET_KEY", "test-secret-key")
    db = SoldenDB(str(tmp_path / "ap-learning-loop.db"))
    db.initialize()
    db.ensure_organization(ORG_ID, organization_name="Learning Loop Ltd")
    return db


def _seed_item(
    db,
    *,
    item_id: str,
    vendor: str,
    state: str,
    amount: float = 1200.0,
    exception_code: str = "critical_field_low_confidence",
):
    return db.create_ap_item(
        {
            "id": item_id,
            "organization_id": ORG_ID,
            "thread_id": f"thread-{item_id}",
            "message_id": f"msg-{item_id}",
            "state": state,
            "vendor_name": vendor,
            "invoice_number": f"INV-{item_id}",
            "amount": amount,
            "currency": "USD",
            "exception_code": exception_code,
            "metadata": {
                "document_type": "invoice",
                "processing_status": state,
            },
        }
    )


def _capture_field_review_memory(db, *, item_id: str, vendor: str, actor_type: str = "agent"):
    commit_memory_event(
        db,
        box_type="ap_item",
        box_id=item_id,
        organization_id=ORG_ID,
        event_type="field_review_required",
        source="gmail",
        actor_type=actor_type,
        actor_id="ap-agent@solden.local" if actor_type == "agent" else "operator@example.com",
        resulting_state="needs_info",
        owner={"label": "AP operator", "email": "ap@example.com"},
        dependency={
            "type": "field_review",
            "owner": "AP operator",
            "reason": "Vendor and amount confidence need confirmation",
        },
        decision={"type": "hold_for_field_review"},
        rationale="Vendor and amount confidence need confirmation",
        evidence={
            "gmail_message_id": f"msg-{item_id}",
            "attachment_content_hash": f"sha256:{item_id}",
            "vendor_name": vendor,
        },
        next_action="Confirm the vendor and amount",
        summary="Review vendor and amount before this invoice moves forward.",
        source_refs={"gmail_message_id": f"msg-{item_id}"},
    )


def test_ap_learning_loop_creates_private_eval_and_company_patterns(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    item_a = _seed_item(
        db,
        item_id="AP-LEARN-1",
        vendor="Google Cloud EMEA Limited",
        state="needs_info",
    )
    item_b = _seed_item(
        db,
        item_id="AP-LEARN-2",
        vendor="Google Cloud EMEA Limited",
        state="posted_to_erp",
        amount=2400.0,
    )
    _capture_field_review_memory(
        db,
        item_id=item_a["id"],
        vendor=item_a["vendor_name"],
        actor_type="agent",
    )
    _capture_field_review_memory(
        db,
        item_id=item_b["id"],
        vendor=item_b["vendor_name"],
        actor_type="user",
    )
    db.record_box_outcome(
        box_id=item_b["id"],
        box_type="ap_item",
        organization_id=ORG_ID,
        outcome_type="posted_to_erp",
        recorded_by="ap-agent@solden.local",
        recorded_actor_type="user",
        data={"erp_reference": "NS-BILL-100"},
    )
    agent_memory = AgentMemoryService(ORG_ID, db=db)
    agent_memory.record_outcome(
        skill_id="ap_v1",
        ap_item=item_a,
        ap_item_id=item_a["id"],
        event_type="field_review_routed",
        reason="requires_operator_confirmation",
        response={"status": "needs_info", "next_step": "confirm_fields"},
        actor_id="ap-agent@solden.local",
        source="finance_agent_loop",
    )

    snapshot = APLearningLoopService(
        ORG_ID, db=db, agent_memory=agent_memory
    ).evaluate_private_outcomes(persist=True)

    assert snapshot["contract"] == "solden_ap_learning_loop.v1"
    assert snapshot["scope"] == "ap_source_to_pay"
    assert snapshot["summary"]["total_items"] == 2
    assert snapshot["summary"]["terminal_items"] == 1
    assert snapshot["summary"]["terminal_outcomes_recorded"] == 1
    assert snapshot["summary"]["outcome_traceability_rate"] == 1.0
    assert snapshot["summary"]["memory_event_coverage_rate"] == 1.0
    assert snapshot["summary"]["agent_trace_rate"] == 0.5
    assert snapshot["summary"]["evidence_link_rate"] == 1.0
    assert snapshot["summary"]["average_memory_completeness_score"] == 1.0
    assert snapshot["release_gate"]["status"] == "needs_work"

    blockers = snapshot["company_learning"]["recurring_blockers"]
    assert blockers[0]["key"] == "critical_field_low_confidence"
    assert blockers[0]["count"] == 2
    assert blockers[0]["affected_vendors"][0] == {
        "vendor_name": "Google Cloud EMEA Limited",
        "count": 2,
    }
    assert blockers[0]["common_next_actions"][0]["next_action"] == (
        "Confirm the vendor and amount"
    )
    assert snapshot["company_learning"]["vendor_patterns"][0]["vendor_name"] == (
        "Google Cloud EMEA Limited"
    )
    candidates = snapshot["company_learning"]["agent_improvement_candidates"]
    trace_candidate = next(
        candidate for candidate in candidates
        if candidate["key"] == "route_agent_decisions_through_memory"
    )
    assert trace_candidate["metric"] == {
        "name": "agent_trace_rate",
        "value": 0.5,
        "target": 0.8,
    }
    assert trace_candidate["evidence"]["example_item_ids"] == ["AP-LEARN-2"]
    blocker_candidate = next(
        candidate for candidate in candidates
        if candidate["key"] == "reduce_recurring_blocker_critical_field_low_confidence"
    )
    assert blocker_candidate["action_type"] == "tune_intake_policy"
    assert blocker_candidate["evidence"]["blocker_count"] == 2

    persisted = agent_memory.latest_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=PRIVATE_OUTCOME_EVAL_TYPE,
    )
    assert persisted["payload"]["summary"]["total_items"] == 2
    patterns = agent_memory.list_patterns(
        skill_id="ap_v1",
        pattern_type="company_ap_blocker",
        pattern_key_prefix="critical_field_low_confidence",
    )
    assert patterns
    assert patterns[0]["pattern"]["example_item_ids"] == ["AP-LEARN-2", "AP-LEARN-1"]
    improvements = agent_memory.list_patterns(
        skill_id="ap_v1",
        pattern_type="agent_improvement_candidate",
        pattern_key_prefix="route_agent_decisions_through_memory",
    )
    assert improvements
    assert improvements[0]["pattern"]["evidence"]["failed_case_count"] == 1


def test_ap_learning_loop_flags_missing_learning_signal(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    item = _seed_item(
        db,
        item_id="AP-LEARN-GAP",
        vendor="Acme Supplies",
        state="closed",
        exception_code="",
    )

    snapshot = APLearningLoopService(ORG_ID, db=db).evaluate_private_outcomes(
        persist=False
    )
    case = snapshot["private_eval_cases"][0]

    assert snapshot["summary"]["memory_event_coverage_rate"] == 0.0
    assert snapshot["summary"]["agent_trace_rate"] == 0.0
    assert case["has_memory_events"] is False
    assert "why_it_is_happening" in case["missing_context"]
    assert "evidence" in case["missing_context"]
    assert snapshot["release_gate"]["checks"]["memory_event_coverage"] is False
    candidates = snapshot["company_learning"]["agent_improvement_candidates"]
    memory_candidate = next(
        candidate for candidate in candidates
        if candidate["key"] == "instrument_missing_memory_events"
    )
    assert memory_candidate["priority"] == "high"
    assert memory_candidate["evidence"]["example_item_ids"] == ["AP-LEARN-GAP"]
    assert (
        "Route every AP agent decision through AgentMemoryService"
        in snapshot["company_learning"]["recommended_actions"][0]
        or "Route every AP agent decision through AgentMemoryService"
        in snapshot["company_learning"]["recommended_actions"][1]
    )


def test_scheduled_ap_learning_loop_persists_non_empty_orgs_only(
    tmp_path, monkeypatch
):
    db = _db(tmp_path, monkeypatch)
    db.ensure_organization(EMPTY_ORG_ID, organization_name="Empty Pilot")
    item = _seed_item(
        db,
        item_id="AP-SCHEDULED-1",
        vendor="Google Cloud EMEA Limited",
        state="needs_info",
    )
    _capture_field_review_memory(
        db,
        item_id=item["id"],
        vendor=item["vendor_name"],
        actor_type="agent",
    )

    result = run_scheduled_ap_learning_loop_evals(
        organization_ids=[ORG_ID, EMPTY_ORG_ID],
        db=db,
        limit=100,
        window_days=30,
    )

    assert result["status"] == "ok"
    assert result["processed"] == 1
    assert result["skipped"] == 1
    assert result["errors"] == 0
    assert result["per_org"] == [
        {
            "organization_id": ORG_ID,
            "status": "persisted",
            "total_items": 1,
            "release_gate": "needs_work",
            "snapshot_type": PRIVATE_OUTCOME_EVAL_TYPE,
        },
        {
            "organization_id": EMPTY_ORG_ID,
            "status": "skipped_no_ap_items",
            "total_items": 0,
        },
    ]

    persisted = AgentMemoryService(ORG_ID, db=db).latest_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=PRIVATE_OUTCOME_EVAL_TYPE,
    )
    assert persisted["payload"]["summary"]["total_items"] == 1
    empty_snapshot = AgentMemoryService(EMPTY_ORG_ID, db=db).latest_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=PRIVATE_OUTCOME_EVAL_TYPE,
    )
    assert empty_snapshot == {}


def test_scheduled_ap_learning_loop_env_orgs_override_passed_orgs(
    tmp_path, monkeypatch
):
    db = _db(tmp_path, monkeypatch)
    db.ensure_organization(EMPTY_ORG_ID, organization_name="Empty Pilot")
    item = _seed_item(
        db,
        item_id="AP-SCHEDULED-ENV-1",
        vendor="Google Cloud EMEA Limited",
        state="needs_info",
    )
    _capture_field_review_memory(
        db,
        item_id=item["id"],
        vendor=item["vendor_name"],
        actor_type="agent",
    )
    monkeypatch.setenv("SOLDEN_AP_LEARNING_LOOP_ORG_IDS", EMPTY_ORG_ID)

    result = run_scheduled_ap_learning_loop_evals(
        organization_ids=[ORG_ID],
        db=db,
        limit=100,
        window_days=30,
    )

    assert result["processed"] == 0
    assert result["skipped"] == 1
    assert result["per_org"][0]["organization_id"] == EMPTY_ORG_ID
    assert AgentMemoryService(ORG_ID, db=db).latest_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=PRIVATE_OUTCOME_EVAL_TYPE,
    ) == {}


def test_celery_beat_schedules_ap_learning_loop_eval():
    from solden.services.celery_app import app

    schedule = app.conf.beat_schedule["run-ap-learning-loop-evals"]

    assert schedule["task"] == (
        "solden.services.celery_tasks.run_ap_learning_loop_evals_all_orgs"
    )
