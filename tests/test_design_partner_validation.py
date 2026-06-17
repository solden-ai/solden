from __future__ import annotations

from solden.services.design_partner_validation import (
    CONTRACT_VERSION,
    build_design_partner_validation_report,
)


def _passing_kpis() -> dict:
    return {
        "totals": {"completed_items": 30},
        "truth_samples": {
            "ap_triage_correctness": {
                "sample_count": 30,
                "correct_count": 29,
            }
        },
        "agentic_telemetry": {
            "shadow_decision_scoring": {
                "summary": {
                    "critical_field_population": 80,
                    "critical_field_match_rate": 0.975,
                }
            },
            "duplicate_side_effects": {
                "population": 30,
                "count": 0,
            },
        },
        "pilot_scorecard": {
            "entity_routing": {
                "invoice_population": 30,
                "needs_review_open_count": 1,
            },
            "automation": {
                "completed_item_count": 30,
                "touchless_rate": 0.8,
            },
        },
        "proof_scorecard": {
            "approval_followup": {
                "population_count": 20,
                "escalation_rate": 0.1,
            },
            "posting_reliability": {
                "attempted_count": 12,
                "success_rate": 0.92,
                "mismatch_count": 0,
            },
        },
    }


def test_design_partner_validation_reports_no_live_signal_without_customer_data():
    report = build_design_partner_validation_report({})

    assert report["contract"] == CONTRACT_VERSION
    assert report["status"] == "no_live_signal"
    assert report["summary"]["insufficient_evidence"] > 0
    assert any(gate["id"] == "ap_triage_correctness" for gate in report["gates"])
    assert report["next_actions"]


def test_design_partner_validation_validates_when_live_wedge_thresholds_are_met():
    report = build_design_partner_validation_report(_passing_kpis())

    assert report["status"] == "validated"
    assert report["summary"]["pass"] == report["summary"]["gate_count"]
    assert report["summary"]["fail"] == 0
    assert report["summary"]["insufficient_evidence"] == 0
    assert report["next_actions"] == []


def test_design_partner_validation_fails_when_posting_or_duplicate_side_effects_regress():
    kpis = _passing_kpis()
    kpis["proof_scorecard"]["posting_reliability"]["success_rate"] = 0.5
    kpis["agentic_telemetry"]["duplicate_side_effects"]["count"] = 1

    report = build_design_partner_validation_report(kpis)
    failed = {gate["id"]: gate for gate in report["gates"] if gate["status"] == "fail"}

    assert report["status"] == "needs_work"
    assert "erp_writeback_success" in failed
    assert "duplicate_side_effect_count" in failed
