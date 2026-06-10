"""High-signal rationale elicitation (tribal-knowledge Build 2).

When an operator approves a HIGH-SIGNAL invoice without a reason, Solden asks
ONE contextual question and requires the answer. This module is the
DETERMINISTIC detector: it reads only data already persisted on the item at
approve time (the decision's risk flags, the vendor context snapshot, the
validation gate) and returns whether elicitation is required plus a
rule-templated question. No LLM anywhere in the gate — auditable, reproducible.

Friction invariant: a clean approval (no signals) NEVER prompts. The signals
are narrow and persisted, not fuzzily inferred at click time.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from solden.core.feature_flags import is_high_signal_elicitation_enabled


def _meta(item: Dict[str, Any]) -> Dict[str, Any]:
    m = item.get("metadata")
    if isinstance(m, str):
        try:
            m = json.loads(m or "{}")
        except Exception:
            m = {}
    return m if isinstance(m, dict) else {}


def _vendor_label(item: Dict[str, Any]) -> str:
    return str(item.get("vendor_name") or "this vendor").strip() or "this vendor"


def _fmt_amount(value: Any, currency: str = "") -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value or "")
    text = f"{amount:,.0f}" if amount == int(amount) else f"{amount:,.2f}"
    return f"{text} {currency}".strip()


def evaluate_elicitation(
    item: Dict[str, Any], payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Decide whether approving this item warrants a required why.

    Returns ``{"required": bool, "signals": [...], "question": str}``. Signals
    are priority-ordered; the question comes from the highest-severity one.
    """
    if not is_high_signal_elicitation_enabled():
        return {"required": False, "signals": [], "question": ""}

    item = item or {}
    payload = payload if isinstance(payload, dict) else {}
    metadata = _meta(item)
    vendor = _vendor_label(item)

    risk_flags = metadata.get("ap_decision_risk_flags")
    risk_flags = set(risk_flags) if isinstance(risk_flags, list) else set()
    vendor_intel = metadata.get("vendor_intelligence")
    vendor_context = (
        vendor_intel.get("vendor_context") if isinstance(vendor_intel, dict) else {}
    )
    vendor_context = vendor_context if isinstance(vendor_context, dict) else {}
    gate = metadata.get("validation_gate")
    gate_codes = set()
    if isinstance(gate, dict):
        codes = gate.get("reason_codes")
        if isinstance(codes, list):
            gate_codes = {str(c) for c in codes}

    signals: List[str] = []
    question = ""

    def _add(signal: str, q: str) -> None:
        nonlocal question
        signals.append(signal)
        if not question:
            question = q

    # 1) Bank-detail change — fraud-adjacent, highest severity.
    if "bank_details_recently_changed" in risk_flags:
        _add(
            "bank_details_recently_changed",
            f"{vendor}'s bank details changed recently — how was the change verified?",
        )

    # 2) Amount way off the vendor's typical.
    amount = None
    try:
        amount = float(item.get("amount"))
    except (TypeError, ValueError):
        amount = None
    avg = None
    try:
        avg = float(vendor_context.get("avg_invoice_amount"))
    except (TypeError, ValueError):
        avg = None
    if "amount_anomaly_2sigma" in risk_flags or (
        amount is not None and avg is not None and avg > 0 and amount > 3 * avg
    ):
        if amount is not None and avg is not None and avg > 0:
            ratio = round(amount / avg, 1)
            q = (
                f"This is {ratio}x {vendor}'s typical amount "
                f"(~{_fmt_amount(avg, str(item.get('currency') or ''))}) — what makes it OK?"
            )
        else:
            q = f"This amount is unusual for {vendor} — what makes it OK?"
        _add("amount_deviation", q)

    # 3) First invoice from this vendor.
    invoice_count = vendor_context.get("invoice_count")
    if "new_vendor" in risk_flags or invoice_count == 0:
        _add(
            "first_time_vendor",
            f"This is the first invoice from {vendor} — why is it OK to approve?",
        )

    # 4) PO required but missing.
    if "po_required_missing" in gate_codes:
        _add(
            "po_required_missing",
            "There's no PO behind this — why is it OK to approve without one?",
        )

    # 5) Budget override (the pre-existing required-rationale trigger).
    if (
        str(payload.get("action_variant") or "").strip().lower() == "budget_override"
        or str(payload.get("approve_override") or "").strip().lower() in {"true", "1", "yes"}
        or payload.get("approve_override") is True
    ):
        _add(
            "budget_override",
            "You're approving over the budget gate — what justifies the override?",
        )

    return {"required": bool(signals), "signals": signals, "question": question}
