"""Tribal-knowledge Build 2 — high-signal rationale elicitation.

The evaluator is deterministic: it reads only persisted signals (decision risk
flags, the vendor-context snapshot, the validation gate) and returns ONE
templated contextual question. Clean approvals never prompt.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from solden.services.elicitation_signals import evaluate_elicitation


def _item(metadata=None, **over):
    base = {
        "id": "AP-el-1",
        "vendor_name": "Acme",
        "amount": 100.0,
        "currency": "EUR",
        "state": "needs_approval",
        "metadata": metadata or {},
    }
    base.update(over)
    return base


def test_clean_item_never_prompts():
    out = evaluate_elicitation(_item(), {})
    assert out == {"required": False, "signals": [], "question": ""}


def test_bank_change_is_highest_priority():
    out = evaluate_elicitation(_item(metadata={
        "ap_decision_risk_flags": ["bank_details_recently_changed", "amount_anomaly_2sigma"],
    }), {})
    assert out["required"]
    assert out["signals"][0] == "bank_details_recently_changed"
    assert "bank details changed" in out["question"]


def test_amount_deviation_question_includes_ratio():
    out = evaluate_elicitation(_item(
        amount=3200.0,
        metadata={
            "vendor_intelligence": {"vendor_context": {"avg_invoice_amount": 1000.0, "invoice_count": 12}},
            "ap_decision_risk_flags": ["amount_anomaly_2sigma"],
        },
    ), {})
    assert out["required"]
    assert "amount_deviation" in out["signals"]
    assert "3.2x" in out["question"]
    assert "Acme" in out["question"]


def test_amount_deviation_derived_without_flag():
    # No persisted flag, but amount > 3x the vendor's typical.
    out = evaluate_elicitation(_item(
        amount=5000.0,
        metadata={"vendor_intelligence": {"vendor_context": {"avg_invoice_amount": 1000.0, "invoice_count": 9}}},
    ), {})
    assert out["required"]
    assert "amount_deviation" in out["signals"]


def test_first_time_vendor():
    out = evaluate_elicitation(_item(metadata={
        "vendor_intelligence": {"vendor_context": {"invoice_count": 0}},
    }), {})
    assert out["required"]
    assert "first_time_vendor" in out["signals"]
    assert "first invoice from Acme" in out["question"]


def test_missing_po_from_validation_gate():
    out = evaluate_elicitation(_item(metadata={
        "validation_gate": {"reason_codes": ["po_required_missing"]},
    }), {})
    assert out["required"]
    assert "po_required_missing" in out["signals"]
    assert "no PO" in out["question"]


def test_override_payload_trigger():
    out = evaluate_elicitation(_item(), {"action_variant": "budget_override"})
    assert out["required"]
    assert "budget_override" in out["signals"]


def test_flag_off_disables(monkeypatch):
    monkeypatch.setenv("FEATURE_HIGH_SIGNAL_ELICITATION", "false")
    out = evaluate_elicitation(_item(metadata={
        "ap_decision_risk_flags": ["bank_details_recently_changed"],
    }), {})
    assert out == {"required": False, "signals": [], "question": ""}


# ─── Handler backstop gate ──────────────────────────────────────────


def _handler_scaffold(item_metadata, payload, actor_type="user"):
    """Minimal scaffolding to drive ApproveInvoiceHandler.execute directly."""
    import asyncio

    from solden.services.finance_skills.ap_intent_handlers import ApproveInvoiceHandler

    skill = MagicMock()
    skill.skill_id = "ap"
    skill.audit_contract.return_value = {}
    workflow = MagicMock()
    workflow.approve_invoice = AsyncMock(return_value={"status": "approved"})
    runtime = MagicMock()
    runtime.actor_type = actor_type
    runtime.actor_id = "op@example.com"
    runtime.correlation_id_for_item.return_value = "corr-1"
    runtime.coerce_bool.return_value = False
    runtime.append_runtime_audit.return_value = {"id": "evt-audit-1"}
    context = {
        "payload": payload,
        "ap_item": _item(metadata=item_metadata),
        "ap_item_id": "AP-el-1",
        "email_id": "thread-1",
        "policy_precheck": {"eligible": True, "reason_codes": []},
        "workflow": workflow,
    }
    handler = ApproveInvoiceHandler()
    result = asyncio.run(handler.execute(skill, runtime, context, idempotency_key="idem-el"))
    return result, workflow, runtime


def test_handler_blocks_high_signal_thin_reason_with_question():
    result, workflow, runtime = _handler_scaffold(
        {"ap_decision_risk_flags": ["bank_details_recently_changed"]},
        {"reason": ""},
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "high_signal_rationale_required"
    assert "bank details changed" in result["question"]
    workflow.approve_invoice.assert_not_called()
    # The block itself is audited.
    audit_kwargs = runtime.append_runtime_audit.call_args.kwargs
    assert audit_kwargs["reason"] == "high_signal_rationale_required"


def test_handler_proceeds_with_real_reason():
    result, workflow, _ = _handler_scaffold(
        {"ap_decision_risk_flags": ["bank_details_recently_changed"]},
        {"reason": "Called the vendor; they confirmed the new IBAN on a verified line."},
    )
    assert result.get("reason") != "high_signal_rationale_required"
    workflow.approve_invoice.assert_called_once()


def test_handler_never_blocks_agent_actor():
    result, workflow, _ = _handler_scaffold(
        {"ap_decision_risk_flags": ["bank_details_recently_changed"]},
        {"reason": ""},
        actor_type="agent",
    )
    assert result.get("reason") != "high_signal_rationale_required"
    workflow.approve_invoice.assert_called_once()


def test_handler_never_blocks_clean_item():
    result, workflow, _ = _handler_scaffold({}, {"reason": ""})
    assert result.get("reason") != "high_signal_rationale_required"
    workflow.approve_invoice.assert_called_once()
