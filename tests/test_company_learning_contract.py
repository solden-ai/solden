from __future__ import annotations

from solden.core.database import SoldenDB
from solden.services.agent_memory import AgentMemoryService
from solden.services.company_learning_contract import (
    COMPANY_LEARNING_CONTRACT,
    COMPANY_LEARNING_CONTRACT_SNAPSHOT_TYPE,
    COMPANY_LEARNING_OBJECTIVE_PATTERN_TYPE,
    COMPANY_LEARNING_SCOPE_PATTERN_TYPE,
    build_company_learning_contract,
)


ORG_ID = "org-company-learning"


def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLDEN_SECRET_KEY", "test-secret-key")
    db = SoldenDB(str(tmp_path / "company-learning.db"))
    db.initialize()
    db.ensure_organization(ORG_ID, organization_name="Company Learning Ltd")
    return db


def _snapshot():
    return {
        "contract": "solden_ap_learning_loop.v1",
        "snapshot_type": "ap_private_outcome_eval",
        "organization_id": ORG_ID,
        "generated_at": "2026-06-16T12:00:00+00:00",
        "scope": "ap_source_to_pay",
        "summary": {
            "total_items": 4,
            "terminal_items": 2,
            "memory_event_coverage_rate": 1.0,
            "agent_trace_rate": 0.75,
            "evidence_link_rate": 1.0,
            "outcome_traceability_rate": 0.5,
            "average_memory_completeness_score": 0.9,
        },
        "company_learning": {
            "company_memory_profile": {
                "contract": "solden_ap_learning_loop.v1",
                "snapshot_type": "company_learning_snapshot",
                "scope": "ap_source_to_pay",
                "headline": "AP company learning is forming from real traces",
                "maturity": {
                    "level": "forming",
                    "score": 0.83,
                    "signals": [
                        {
                            "key": "memory_event_coverage_rate",
                            "label": "Memory event coverage",
                            "value": 1.0,
                            "target": 0.95,
                        },
                        {
                            "key": "agent_trace_rate",
                            "label": "Agent trace coverage",
                            "value": 0.75,
                            "target": 0.8,
                        },
                    ],
                },
                "sample": {
                    "total_items": 4,
                    "terminal_items": 2,
                },
                "learning_gaps": [
                    {
                        "key": "route_agent_decisions_through_memory",
                        "title": "Route AP agent decisions through agent memory",
                        "priority": "high",
                    }
                ],
                "operating_patterns": {
                    "top_recurring_blocker": {
                        "key": "critical_field_low_confidence",
                        "count": 2,
                    }
                },
                "next_learning_objective": {
                    "key": "route_agent_decisions_through_memory",
                    "title": "Route AP agent decisions through agent memory",
                    "priority": "high",
                    "target_runtime_path": "AgentMemoryService.record_outcome",
                    "action_type": "instrument_agent_trace",
                    "target_metric": {
                        "name": "agent_trace_rate",
                        "value": 0.75,
                        "target": 0.8,
                    },
                },
                "evidence": {
                    "source_snapshot_type": "ap_private_outcome_eval",
                    "sample_size": 4,
                    "example_item_ids": ["AP-1", "AP-2"],
                },
                "confidence": 0.77,
            },
            "agent_improvement_candidates": [
                {
                    "key": "route_agent_decisions_through_memory",
                    "title": "Route AP agent decisions through agent memory",
                    "priority": "high",
                    "metric": {
                        "name": "agent_trace_rate",
                        "value": 0.75,
                        "target": 0.8,
                    },
                    "evidence": {
                        "failed_case_count": 1,
                        "sample_size": 4,
                    },
                }
            ],
        },
    }


def _improvement_register():
    return {
        "contract": "solden_agent_improvement_register.v1",
        "summary": {
            "total": 1,
            "open": 1,
            "resolved": 0,
            "high_priority_open": 1,
            "next_item_key": "route_agent_decisions_through_memory",
            "next_item_title": "Route AP agent decisions through agent memory",
        },
        "items": [],
    }


def test_company_learning_contract_normalizes_org_level_learning_signal(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)

    contract = build_company_learning_contract(
        ORG_ID,
        db=db,
        snapshot=_snapshot(),
        improvement_register=_improvement_register(),
        persist=False,
    )

    assert contract["contract"] == COMPANY_LEARNING_CONTRACT
    assert contract["summary"]["organization_learning_status"] == "forming"
    assert contract["summary"]["workflow_coverage_status"] == "ap_wedge_only"
    assert contract["summary"]["open_learning_objectives"] == 1
    assert contract["summary"]["high_priority_open_objectives"] == 1
    assert contract["summary"]["ready_for_company_learning_claim"] is True

    scope = contract["scopes"][0]
    assert scope["scope"] == "ap_source_to_pay"
    assert scope["status"] == "forming"
    assert scope["ready_for_scope_claim"] is True
    assert scope["maturity"]["signals"][0]["target_met"] is True
    assert scope["maturity"]["signals"][1]["target_met"] is False
    assert {row["key"] for row in scope["signal_chain"]} == {
        "record_level_memory",
        "private_outcome_eval",
        "company_profile",
        "improvement_register",
        "runtime_learning_objective",
    }
    assert scope["next_learning_objective"]["target_runtime_path"] == (
        "AgentMemoryService.record_outcome"
    )


def test_company_learning_contract_persists_snapshot_scope_and_objective_patterns(
    tmp_path,
    monkeypatch,
):
    db = _db(tmp_path, monkeypatch)
    memory = AgentMemoryService(ORG_ID, db=db)

    contract = build_company_learning_contract(
        ORG_ID,
        db=db,
        agent_memory=memory,
        snapshot=_snapshot(),
        improvement_register=_improvement_register(),
        persist=True,
    )

    persisted = memory.latest_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=COMPANY_LEARNING_CONTRACT_SNAPSHOT_TYPE,
    )
    assert persisted["payload"]["summary"] == contract["summary"]

    scope_patterns = memory.list_patterns(
        skill_id="ap_v1",
        pattern_type=COMPANY_LEARNING_SCOPE_PATTERN_TYPE,
        limit=5,
    )
    assert scope_patterns[0]["pattern_key"] == "ap_source_to_pay"
    objective_patterns = memory.list_patterns(
        skill_id="ap_v1",
        pattern_type=COMPANY_LEARNING_OBJECTIVE_PATTERN_TYPE,
        limit=5,
    )
    assert objective_patterns[0]["pattern_key"] == (
        "route_agent_decisions_through_memory"
    )


def test_company_learning_contract_reports_no_signal_without_snapshot(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)

    contract = build_company_learning_contract(ORG_ID, db=db, persist=False)

    assert contract["summary"]["organization_learning_status"] == "no_signal"
    assert contract["summary"]["ready_for_company_learning_claim"] is False
    assert contract["scopes"][0]["status"] == "no_signal"
