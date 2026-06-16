from __future__ import annotations

from solden.core.database import SoldenDB
from solden.services.finance_learning import FinanceLearningService


def test_finance_learning_records_outcome_calibration_from_runtime_outcome(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLDEN_SECRET_KEY", "test-secret-key")
    db = SoldenDB(str(tmp_path / "finance-learning.db"))
    db.initialize()

    service = FinanceLearningService("test-org", db=db)
    result = service.record_runtime_outcome(
        ap_item={
            "id": "ap-1",
            "vendor_name": "Calibrated Vendor",
            "amount": 100.0,
            "currency": "USD",
        },
        response={
            "status": "posted_to_erp",
            "gl_code": "5200",
            "post_verified": True,
        },
        shadow_decision={"proposed_action": "auto_approve_post"},
        actor_id="tester",
    )
    calibration = service.get_outcome_calibration(
        vendor_name="Calibrated Vendor",
        action_key="auto_approve_post",
    )

    assert result["recorded"]
    assert calibration["sample_count"] == 1
    assert calibration["success_rate"] == 1.0
    assert calibration["shadow_match_rate"] == 1.0
    assert calibration["verification_rate"] == 1.0


def test_finance_learning_lists_compact_runtime_outcome_traces(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLDEN_SECRET_KEY", "test-secret-key")
    db = SoldenDB(str(tmp_path / "finance-learning-traces.db"))
    db.initialize()

    service = FinanceLearningService("test-org", db=db)
    service.record_runtime_outcome(
        ap_item={
            "id": "ap-trace-1",
            "vendor_name": "Trace Vendor",
            "amount": 200.0,
            "currency": "USD",
        },
        response={
            "status": "posted_to_erp",
            "ap_item_id": "ap-trace-1",
            "post_verified": True,
        },
        shadow_decision={"proposed_action": "auto_approve_post"},
        actor_id="agent@solden.local",
    )

    traces = service.list_runtime_outcome_traces(ap_item_id="ap-trace-1")

    assert len(traces) == 1
    assert traces[0]["ap_item_id"] == "ap-trace-1"
    assert traces[0]["actual_action"] == "auto_approve_post"
    assert traces[0]["proposed_action"] == "auto_approve_post"
    assert traces[0]["matched_shadow"] is True
    assert traces[0]["verification_succeeded"] is True
