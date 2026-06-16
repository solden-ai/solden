from __future__ import annotations

from datetime import timedelta

from solden.core.database import SoldenDB
from solden.services.agent_improvement_register import IMPROVEMENT_REGISTER_SNAPSHOT_TYPE
from solden.services.agent_memory import AgentMemoryService
from solden.services.ap_learning_loop import PRIVATE_OUTCOME_EVAL_TYPE
from solden.services.company_learning_contract import (
    COMPANY_LEARNING_CONTRACT_SNAPSHOT_TYPE,
)
from solden.services.learning_loop_health import (
    LEARNING_LOOP_HEALTH_CONTRACT,
    build_learning_loop_health,
)


ORG_ID = "org-learning-loop-health"


def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLDEN_SECRET_KEY", "test-secret-key")
    db = SoldenDB(str(tmp_path / "learning-loop-health.db"))
    db.initialize()
    db.ensure_organization(ORG_ID, organization_name="Learning Loop Health Ltd")
    return db


def _record_required_snapshots(
    memory: AgentMemoryService,
    *,
    release_gate_status: str = "pass",
    ready_for_company_learning_claim: bool = True,
) -> None:
    memory.record_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=PRIVATE_OUTCOME_EVAL_TYPE,
        payload={
            "summary": {
                "total_items": 5,
                "terminal_items": 4,
                "memory_event_coverage_rate": 1.0,
            },
            "release_gate": {"status": release_gate_status},
        },
    )
    memory.record_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=IMPROVEMENT_REGISTER_SNAPSHOT_TYPE,
        payload={
            "summary": {
                "open": 1,
                "high_priority_open": 0,
                "next_item_title": "Keep learning loop fresh",
            }
        },
    )
    memory.record_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=COMPANY_LEARNING_CONTRACT_SNAPSHOT_TYPE,
        payload={
            "summary": {
                "organization_learning_status": "forming",
                "ready_for_company_learning_claim": ready_for_company_learning_claim,
                "next_learning_objective_title": "Keep learning loop fresh",
                "workflow_coverage_status": "ap_wedge_only",
            }
        },
    )


def test_learning_loop_health_reports_no_signal_without_snapshots(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)

    health = build_learning_loop_health(ORG_ID, db=db)

    assert health["contract"] == LEARNING_LOOP_HEALTH_CONTRACT
    assert health["status"] == "no_signal"
    assert health["summary"]["observed_components"] == 0
    assert health["summary"]["fresh_components"] == 0
    assert health["components"]["private_eval"]["observed"] is False


def test_learning_loop_health_reports_healthy_when_required_snapshots_are_fresh(
    tmp_path,
    monkeypatch,
):
    db = _db(tmp_path, monkeypatch)
    memory = AgentMemoryService(ORG_ID, db=db)
    _record_required_snapshots(memory)

    health = build_learning_loop_health(ORG_ID, db=db, agent_memory=memory)

    assert health["status"] == "healthy"
    assert health["summary"]["observed_components"] == 3
    assert health["summary"]["fresh_components"] == 3
    assert health["summary"]["release_gate"] == "pass"
    assert health["summary"]["company_learning_status"] == "forming"
    assert health["summary"]["ready_for_company_learning_claim"] is True
    assert health["summary"]["blocking_reasons"] == []


def test_learning_loop_health_needs_work_when_company_learning_claim_is_not_ready(
    tmp_path,
    monkeypatch,
):
    db = _db(tmp_path, monkeypatch)
    memory = AgentMemoryService(ORG_ID, db=db)
    _record_required_snapshots(memory, ready_for_company_learning_claim=False)

    health = build_learning_loop_health(ORG_ID, db=db, agent_memory=memory)

    assert health["status"] == "needs_work"
    assert health["summary"]["release_gate"] == "pass"
    assert health["summary"]["ready_for_company_learning_claim"] is False
    assert "company_learning_claim_not_ready" in health["summary"]["blocking_reasons"]


def test_learning_loop_health_reports_stale_when_scheduler_has_not_refreshed_snapshots(
    tmp_path,
    monkeypatch,
):
    from solden.services import learning_loop_health as module

    db = _db(tmp_path, monkeypatch)
    memory = AgentMemoryService(ORG_ID, db=db)
    _record_required_snapshots(memory)
    generated_at = module._now()
    monkeypatch.setattr(module, "_now", lambda: generated_at + timedelta(hours=48))

    health = build_learning_loop_health(ORG_ID, db=db, agent_memory=memory)

    assert health["status"] == "stale"
    assert health["summary"]["observed_components"] == 3
    assert health["summary"]["fresh_components"] == 0
    assert health["components"]["company_learning_contract"]["fresh"] is False


def test_learning_loop_health_surfaces_pending_policy_proposals(
    tmp_path,
    monkeypatch,
):
    db = _db(tmp_path, monkeypatch)
    db.create_policy_proposal(
        organization_id=ORG_ID,
        proposal_kind="vendor_standing_approval",
        vendor_name="Google Cloud EMEA Limited",
        behavior_summary="Learning loop found a repeatable approval pattern.",
        evidence={
            "learning_citation": {
                "source": "ap_learning_loop",
                "private_eval_snapshot": {"release_gate_status": "needs_work"},
            }
        },
        proposed_rule={
            "rule_type": "vendor_amount",
            "vendor_name": "Google Cloud EMEA Limited",
            "amount_cap": 1200,
            "currency": "USD",
        },
    )

    health = build_learning_loop_health(ORG_ID, db=db)

    assert health["summary"]["pending_policy_proposals"] == 1
    assert health["summary"]["pending_policy_proposals_available"] is True
    proposal = health["pending_policy_proposals"]["proposals"][0]
    assert proposal["proposal_kind"] == "vendor_standing_approval"
    assert proposal["has_learning_citation"] is True


def test_learning_loop_health_needs_work_when_policy_proposals_lack_learning_citations(
    tmp_path,
    monkeypatch,
):
    db = _db(tmp_path, monkeypatch)
    memory = AgentMemoryService(ORG_ID, db=db)
    _record_required_snapshots(memory)
    db.create_policy_proposal(
        organization_id=ORG_ID,
        proposal_kind="vendor_standing_approval",
        vendor_name="Google Cloud EMEA Limited",
        behavior_summary="Proposal has no learning citation and should block health.",
        evidence={},
        proposed_rule={
            "rule_type": "vendor_amount",
            "vendor_name": "Google Cloud EMEA Limited",
            "amount_cap": 1200,
            "currency": "USD",
        },
    )

    health = build_learning_loop_health(ORG_ID, db=db, agent_memory=memory)

    assert health["status"] == "needs_work"
    assert health["summary"]["policy_proposal_learning_citation_rate"] == 0.0
    assert health["summary"]["policy_proposals_missing_learning_citations"] == 1
    assert (
        "policy_proposals_missing_learning_citations"
        in health["summary"]["blocking_reasons"]
    )
