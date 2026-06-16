from __future__ import annotations

from solden.core.database import SoldenDB
from solden.services.agent_improvement_register import (
    IMPROVEMENT_REGISTER_CONTRACT,
    IMPROVEMENT_REGISTER_PATTERN_TYPE,
    IMPROVEMENT_REGISTER_SNAPSHOT_TYPE,
    build_agent_improvement_register,
)
from solden.services.agent_memory import AgentMemoryService


ORG_ID = "org-improvement-register"


def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLDEN_SECRET_KEY", "test-secret-key")
    db = SoldenDB(str(tmp_path / "agent-improvement-register.db"))
    db.initialize()
    db.ensure_organization(ORG_ID, organization_name="Improvement Register Ltd")
    return db


def _snapshot():
    return {
        "snapshot_type": "ap_private_outcome_eval",
        "created_at": "2026-06-16T12:00:00+00:00",
        "company_learning": {
            "agent_improvement_candidates": [
                {
                    "key": "route_agent_decisions_through_memory",
                    "title": "Route AP agent decisions through agent memory",
                    "priority": "high",
                    "target_runtime_path": "AgentMemoryService.record_outcome",
                    "action_type": "instrument_agent_trace",
                    "metric": {
                        "name": "agent_trace_rate",
                        "value": 0.5,
                        "target": 0.8,
                    },
                    "evidence": {
                        "failed_case_count": 3,
                        "sample_size": 8,
                        "example_item_ids": ["AP-1", "AP-2"],
                    },
                    "confidence": 0.82,
                },
                {
                    "key": "reduce_recurring_blocker_po_missing",
                    "title": "Tune AP intake around PO missing",
                    "priority": "medium",
                    "target_runtime_path": "finance_runtime_invoice_processing",
                    "action_type": "tune_intake_policy",
                    "metric": {
                        "name": "recurring_blocker_share",
                        "value": 0.04,
                        "target": 0.05,
                    },
                    "evidence": {
                        "failed_case_count": 1,
                        "sample_size": 8,
                    },
                    "confidence": 0.71,
                },
            ]
        },
    }


def test_improvement_register_classifies_open_and_resolved_items(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)

    register = build_agent_improvement_register(
        ORG_ID,
        db=db,
        snapshot=_snapshot(),
        persist=False,
    )

    assert register["contract"] == IMPROVEMENT_REGISTER_CONTRACT
    assert register["summary"] == {
        "total": 2,
        "open": 1,
        "resolved": 1,
        "high_priority_open": 1,
        "next_item_key": "route_agent_decisions_through_memory",
        "next_item_title": "Route AP agent decisions through agent memory",
    }
    open_item = register["items"][0]
    assert open_item["status"] == "open"
    assert open_item["metric"]["direction"] == "higher_is_better"
    assert open_item["metric"]["target_met"] is False
    resolved_item = register["items"][1]
    assert resolved_item["status"] == "resolved"
    assert resolved_item["metric"]["direction"] == "lower_is_better"
    assert resolved_item["metric"]["target_met"] is True


def test_improvement_register_persists_snapshot_and_register_patterns(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    memory = AgentMemoryService(ORG_ID, db=db)

    register = build_agent_improvement_register(
        ORG_ID,
        db=db,
        agent_memory=memory,
        snapshot=_snapshot(),
        persist=True,
    )

    persisted = memory.latest_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=IMPROVEMENT_REGISTER_SNAPSHOT_TYPE,
    )
    assert persisted["payload"]["summary"] == register["summary"]
    patterns = memory.list_patterns(
        skill_id="ap_v1",
        pattern_type=IMPROVEMENT_REGISTER_PATTERN_TYPE,
        limit=5,
    )
    assert {row["pattern_key"] for row in patterns} == {
        "route_agent_decisions_through_memory",
        "reduce_recurring_blocker_po_missing",
    }
