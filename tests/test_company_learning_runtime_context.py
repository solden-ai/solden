from __future__ import annotations

from solden.core.database import SoldenDB
from solden.services.agent_improvement_register import IMPROVEMENT_REGISTER_SNAPSHOT_TYPE
from solden.services.agent_memory import AgentMemoryService
from solden.services.ap_learning_loop import PRIVATE_OUTCOME_EVAL_TYPE
from solden.services.company_learning_contract import (
    COMPANY_LEARNING_CONTRACT_SNAPSHOT_TYPE,
)
from solden.services.company_learning_runtime_context import (
    COMPANY_LEARNING_RUNTIME_CONTEXT,
    build_company_learning_runtime_context,
)


ORG_ID = "org-runtime-learning"


def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLDEN_SECRET_KEY", "test-secret-key")
    db = SoldenDB(str(tmp_path / "company-learning-runtime.db"))
    db.initialize()
    db.ensure_organization(ORG_ID, organization_name="Runtime Learning Ltd")
    return db


def _record_snapshots(memory: AgentMemoryService) -> None:
    memory.record_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=PRIVATE_OUTCOME_EVAL_TYPE,
        payload={
            "release_gate": {"status": "needs_work"},
            "summary": {"total_items": 4, "memory_event_coverage_rate": 1.0},
        },
    )
    memory.record_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=IMPROVEMENT_REGISTER_SNAPSHOT_TYPE,
        payload={
            "summary": {
                "open": 1,
                "high_priority_open": 1,
                "next_item_title": "Route AP agent decisions through memory",
            },
            "items": [
                {
                    "key": "route_agent_decisions_through_memory",
                    "title": "Route AP agent decisions through memory",
                    "status": "open",
                    "priority": "high",
                    "action_type": "instrument_agent_trace",
                    "target_runtime_path": "APDecisionService.decide",
                    "metric": {
                        "name": "agent_trace_rate",
                        "value": 0.72,
                        "target": 0.9,
                        "target_met": False,
                    },
                    "evidence": {"sample_size": 4, "failed_case_count": 1},
                }
            ],
        },
    )
    memory.record_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=COMPANY_LEARNING_CONTRACT_SNAPSHOT_TYPE,
        payload={
            "summary": {
                "organization_learning_status": "forming",
                "ready_for_company_learning_claim": True,
                "workflow_coverage_status": "ap_wedge_only",
                "next_learning_objective_title": (
                    "Route AP agent decisions through memory"
                ),
            }
        },
    )


def test_runtime_context_reports_no_signal_without_learning_snapshots(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)

    context = build_company_learning_runtime_context(ORG_ID, db=db)

    assert context["contract"] == COMPANY_LEARNING_RUNTIME_CONTEXT
    assert context["usable"] is False
    assert context["status"] == "no_signal"
    assert context["improvement_objectives"] == []


def test_runtime_context_compacts_fresh_learning_and_vendor_policy_proposals(
    tmp_path,
    monkeypatch,
):
    db = _db(tmp_path, monkeypatch)
    memory = AgentMemoryService(ORG_ID, db=db)
    _record_snapshots(memory)
    db.create_policy_proposal(
        organization_id=ORG_ID,
        proposal_kind="vendor_standing_approval",
        vendor_name="Google Cloud EMEA Limited",
        behavior_summary="Google Cloud has a repeat approval pattern.",
        evidence={"learning_citation": {"source": "ap_learning_loop"}},
        proposed_rule={
            "rule_type": "vendor_amount",
            "vendor_name": "Google Cloud EMEA Limited",
            "amount_cap": 5000,
            "currency": "USD",
        },
    )
    db.create_policy_proposal(
        organization_id=ORG_ID,
        proposal_kind="vendor_standing_approval",
        vendor_name="Other Vendor",
        behavior_summary="Other vendor proposal.",
        evidence={"learning_citation": {"source": "ap_learning_loop"}},
        proposed_rule={"rule_type": "vendor_amount"},
    )

    context = build_company_learning_runtime_context(
        ORG_ID,
        db=db,
        agent_memory=memory,
        vendor_name="Google Cloud EMEA Limited",
    )

    assert context["usable"] is True
    assert context["status"] == "available"
    assert context["summary"]["company_learning_status"] == "forming"
    assert context["summary"]["pending_policy_proposals"] == 1
    assert context["improvement_objectives"][0]["target_runtime_path"] == (
        "APDecisionService.decide"
    )
    assert "Current learning objective" in context["runtime_guidance"][0]
    assert context["pending_policy_proposals"]["proposals"][0]["vendor_name"] == (
        "Google Cloud EMEA Limited"
    )
