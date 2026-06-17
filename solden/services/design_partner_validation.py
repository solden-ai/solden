"""Design-partner validation gate for the AP wedge.

The launch tracker proves the product can run. This module answers a
different question: is live customer usage proving the wedge claim?
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional


CONTRACT_VERSION = "solden_design_partner_validation.v1"
WEDGE_CLAIM = (
    "A finance manager can run AP from inbox and decision surfaces with less "
    "context switching, less approval chasing, and less ERP re-entry."
)


DEFAULT_THRESHOLDS: Dict[str, float] = {
    "ap_triage_correctness_rate": 0.95,
    "critical_field_match_rate": 0.95,
    "entity_routing_clear_rate": 0.90,
    "approval_without_followup_rate": 0.80,
    "erp_writeback_success_rate": 0.85,
    "touchless_completion_rate": 0.70,
}

DEFAULT_MINIMUMS: Dict[str, int] = {
    "completed_items": 25,
    "truth_sample": 25,
    "critical_field_population": 50,
    "entity_invoice_population": 10,
    "approval_population": 10,
    "post_attempts": 10,
}


def build_design_partner_validation_report(
    kpis: Mapping[str, Any],
    *,
    minimums: Optional[Mapping[str, int]] = None,
    thresholds: Optional[Mapping[str, float]] = None,
) -> Dict[str, Any]:
    """Build the live-usage claim gate for a design-partner pilot.

    The report is intentionally conservative: missing live evidence returns
    ``insufficient_evidence`` instead of pretending implementation coverage is
    customer proof.
    """
    payload = _dict(kpis)
    resolved_minimums = {**DEFAULT_MINIMUMS, **{k: int(v) for k, v in _dict(minimums).items()}}
    resolved_thresholds = {**DEFAULT_THRESHOLDS, **{k: float(v) for k, v in _dict(thresholds).items()}}

    gates = [
        _completed_sample_gate(payload, resolved_minimums),
        _triage_truth_gate(payload, resolved_minimums, resolved_thresholds),
        _critical_field_gate(payload, resolved_minimums, resolved_thresholds),
        _entity_routing_gate(payload, resolved_minimums, resolved_thresholds),
        _approval_followup_gate(payload, resolved_minimums, resolved_thresholds),
        _erp_writeback_gate(payload, resolved_minimums, resolved_thresholds),
        _silent_failure_gate(payload, resolved_minimums),
        _duplicate_side_effect_gate(payload),
        _touchless_completion_gate(payload, resolved_minimums, resolved_thresholds),
    ]

    counts = {
        "pass": sum(1 for gate in gates if gate["status"] == "pass"),
        "fail": sum(1 for gate in gates if gate["status"] == "fail"),
        "insufficient_evidence": sum(1 for gate in gates if gate["status"] == "insufficient_evidence"),
    }
    measurable = counts["pass"] + counts["fail"]
    completed_items = _int(_path(payload, "totals", "completed_items"))
    post_attempts = _int(_path(payload, "proof_scorecard", "posting_reliability", "attempted_count"))

    if completed_items <= 0 and post_attempts <= 0:
        status = "no_live_signal"
    elif counts["fail"]:
        status = "needs_work"
    elif counts["insufficient_evidence"]:
        status = "collecting_evidence"
    else:
        status = "validated"

    next_actions = _build_next_actions(gates)
    return {
        "contract": CONTRACT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wedge": "ap_v1",
        "claim": WEDGE_CLAIM,
        "status": status,
        "summary": {
            "gate_count": len(gates),
            **counts,
            "measurable_gate_count": measurable,
            "measurable_pass_rate": round((counts["pass"] / measurable) if measurable else 0.0, 4),
            "completed_items": completed_items,
            "post_attempts": post_attempts,
        },
        "thresholds": resolved_thresholds,
        "minimums": resolved_minimums,
        "gates": gates,
        "next_actions": next_actions,
        "source_metrics": {
            "pilot_scorecard": _dict(payload.get("pilot_scorecard")),
            "proof_scorecard": _dict(payload.get("proof_scorecard")),
            "operator_metrics": _dict(payload.get("operator_metrics")),
        },
    }


def _completed_sample_gate(kpis: Mapping[str, Any], minimums: Mapping[str, int]) -> Dict[str, Any]:
    completed = _int(_path(kpis, "totals", "completed_items"))
    minimum = _int(minimums.get("completed_items"))
    return _count_gate(
        gate_id="live_completed_sample",
        label="Live completed invoice sample",
        observed_count=completed,
        threshold_count=minimum,
        evidence="kpis.totals.completed_items",
        insufficient_reason="Design-partner proof needs enough completed AP items to avoid anecdotal conclusions.",
        next_action="Run the in-scope AP workflow until the completed-item floor is met.",
    )


def _triage_truth_gate(
    kpis: Mapping[str, Any],
    minimums: Mapping[str, int],
    thresholds: Mapping[str, float],
) -> Dict[str, Any]:
    sample = _truth_sample(kpis, "ap_triage_correctness")
    rate = _rate_from_sample(sample)
    population = _sample_population(sample)
    return _rate_gate(
        gate_id="ap_triage_correctness",
        label="AP triage correctness",
        observed_rate=rate,
        threshold_rate=float(thresholds["ap_triage_correctness_rate"]),
        population=population,
        minimum_population=int(minimums["truth_sample"]),
        evidence="truth_samples.ap_triage_correctness",
        insufficient_reason="Requires a real pilot replay/traffic sample comparing Solden classification against operator truth.",
        fail_reason="AP triage accuracy is below the wedge threshold.",
        next_action="Review misclassified AP emails, update classification rules/prompts, and rerun the truth sample.",
    )


def _critical_field_gate(
    kpis: Mapping[str, Any],
    minimums: Mapping[str, int],
    thresholds: Mapping[str, float],
) -> Dict[str, Any]:
    summary = _dict(_path(kpis, "agentic_telemetry", "shadow_decision_scoring", "summary"))
    return _rate_gate(
        gate_id="critical_field_accuracy",
        label="Critical field accuracy",
        observed_rate=_float(summary.get("critical_field_match_rate")),
        threshold_rate=float(thresholds["critical_field_match_rate"]),
        population=_int(summary.get("critical_field_population")),
        minimum_population=int(minimums["critical_field_population"]),
        evidence="agentic_telemetry.shadow_decision_scoring.summary",
        insufficient_reason="Needs enough shadow-scored fields from live AP traffic.",
        fail_reason="Critical field match rate is below the quality bar.",
        next_action="Inspect sampled disagreements by vendor/field and tighten extraction or field-review gates.",
    )


def _entity_routing_gate(
    kpis: Mapping[str, Any],
    minimums: Mapping[str, int],
    thresholds: Mapping[str, float],
) -> Dict[str, Any]:
    routing = _dict(_path(kpis, "pilot_scorecard", "entity_routing"))
    population = _int(routing.get("invoice_population"))
    needs_review = _int(routing.get("needs_review_open_count"))
    clear_rate = 1.0 - ((needs_review / population) if population else 0.0)
    return _rate_gate(
        gate_id="entity_routing_clear_rate",
        label="Entity routing clear rate",
        observed_rate=clear_rate,
        threshold_rate=float(thresholds["entity_routing_clear_rate"]),
        population=population,
        minimum_population=int(minimums["entity_invoice_population"]),
        evidence="pilot_scorecard.entity_routing",
        insufficient_reason="Needs enough invoice traffic with entity-routing context.",
        fail_reason="Too many invoices are still blocked on entity routing review.",
        next_action="Add or correct entity/vendor mapping rules for the repeated routing blockers.",
    )


def _approval_followup_gate(
    kpis: Mapping[str, Any],
    minimums: Mapping[str, int],
    thresholds: Mapping[str, float],
) -> Dict[str, Any]:
    followup = _dict(_path(kpis, "proof_scorecard", "approval_followup"))
    population = _int(followup.get("population_count"))
    escalation_rate = _float(followup.get("escalation_rate"))
    observed = None if escalation_rate is None else 1.0 - escalation_rate
    return _rate_gate(
        gate_id="approval_without_followup_pressure",
        label="Approvals without follow-up pressure",
        observed_rate=observed,
        threshold_rate=float(thresholds["approval_without_followup_rate"]),
        population=population,
        minimum_population=int(minimums["approval_population"]),
        evidence="proof_scorecard.approval_followup",
        insufficient_reason="Needs enough approval cases to judge whether Solden reduces chasing.",
        fail_reason="Too many approval cases still require escalation/follow-up pressure.",
        next_action="Review approver mapping, reminders, and escalation rules for delayed approval paths.",
    )


def _erp_writeback_gate(
    kpis: Mapping[str, Any],
    minimums: Mapping[str, int],
    thresholds: Mapping[str, float],
) -> Dict[str, Any]:
    posting = _dict(_path(kpis, "proof_scorecard", "posting_reliability"))
    return _rate_gate(
        gate_id="erp_writeback_success",
        label="ERP writeback success",
        observed_rate=_float(posting.get("success_rate")),
        threshold_rate=float(thresholds["erp_writeback_success_rate"]),
        population=_int(posting.get("attempted_count")),
        minimum_population=int(minimums["post_attempts"]),
        evidence="proof_scorecard.posting_reliability",
        insufficient_reason="Needs enough ERP posting attempts from the pilot workflow.",
        fail_reason="Approved invoices are not posting to ERP at the required rate.",
        next_action="Separate product/runtime failures from ERP configuration failures and fix the top blocker first.",
    )


def _silent_failure_gate(kpis: Mapping[str, Any], minimums: Mapping[str, int]) -> Dict[str, Any]:
    posting = _dict(_path(kpis, "proof_scorecard", "posting_reliability"))
    attempted = _int(posting.get("attempted_count"))
    mismatches = _int(posting.get("mismatch_count"))
    if attempted < int(minimums["post_attempts"]):
        return _gate(
            "silent_failure_count",
            "Silent failure count",
            "insufficient_evidence",
            observed_count=mismatches,
            threshold_count=0,
            population=attempted,
            evidence="proof_scorecard.posting_reliability.mismatch_count",
            reason="Needs enough post-action verification attempts to prove silent failures are absent.",
            next_action="Keep post-action verification enabled and review every mismatch before expanding scope.",
        )
    return _gate(
        "silent_failure_count",
        "Silent failure count",
        "pass" if mismatches == 0 else "fail",
        observed_count=mismatches,
        threshold_count=0,
        population=attempted,
        evidence="proof_scorecard.posting_reliability.mismatch_count",
        reason="No silent post-action mismatches observed." if mismatches == 0 else "Post-action verification found mismatches.",
        next_action="Investigate mismatches by AP item and connector before calling the wedge validated.",
    )


def _duplicate_side_effect_gate(kpis: Mapping[str, Any]) -> Dict[str, Any]:
    duplicate_metrics = (
        _path(kpis, "agentic_telemetry", "duplicate_side_effects")
        or _path(kpis, "duplicate_side_effects")
    )
    duplicate_metrics = _dict(duplicate_metrics)
    if not duplicate_metrics:
        return _gate(
            "duplicate_side_effect_count",
            "Duplicate side-effect count",
            "insufficient_evidence",
            observed_count=None,
            threshold_count=0,
            population=None,
            evidence="agentic_telemetry.duplicate_side_effects",
            reason="Live duplicate-side-effect monitoring is not present in the KPI payload yet.",
            next_action="Add live duplicate side-effect counters or attach audit-review evidence to the weekly pilot report.",
        )
    count = _int(duplicate_metrics.get("count"))
    return _gate(
        "duplicate_side_effect_count",
        "Duplicate side-effect count",
        "pass" if count == 0 else "fail",
        observed_count=count,
        threshold_count=0,
        population=_int(duplicate_metrics.get("population")),
        evidence="agentic_telemetry.duplicate_side_effects",
        reason="No duplicate side effects observed." if count == 0 else "Duplicate side effects were observed.",
        next_action="Stop expansion until duplicate approval/posting side effects are root-caused and fixed.",
    )


def _touchless_completion_gate(
    kpis: Mapping[str, Any],
    minimums: Mapping[str, int],
    thresholds: Mapping[str, float],
) -> Dict[str, Any]:
    automation = _dict(_path(kpis, "pilot_scorecard", "automation"))
    return _rate_gate(
        gate_id="touchless_completion_rate",
        label="Touchless completed invoices",
        observed_rate=_float(automation.get("touchless_rate")),
        threshold_rate=float(thresholds["touchless_completion_rate"]),
        population=_int(automation.get("completed_item_count")),
        minimum_population=int(minimums["completed_items"]),
        evidence="pilot_scorecard.automation",
        insufficient_reason="Needs enough completed invoices to judge context-switch reduction.",
        fail_reason="Too many completed invoices still need manual handling.",
        next_action="Review the repeated manual-intervention reasons and automate or simplify the highest-volume path.",
    )


def _rate_gate(
    *,
    gate_id: str,
    label: str,
    observed_rate: Optional[float],
    threshold_rate: float,
    population: int,
    minimum_population: int,
    evidence: str,
    insufficient_reason: str,
    fail_reason: str,
    next_action: str,
) -> Dict[str, Any]:
    if observed_rate is None or population < minimum_population:
        return _gate(
            gate_id,
            label,
            "insufficient_evidence",
            observed_rate=observed_rate,
            threshold_rate=threshold_rate,
            population=population,
            evidence=evidence,
            reason=insufficient_reason,
            next_action=next_action,
        )
    passed = observed_rate >= threshold_rate
    return _gate(
        gate_id,
        label,
        "pass" if passed else "fail",
        observed_rate=observed_rate,
        threshold_rate=threshold_rate,
        population=population,
        evidence=evidence,
        reason="Observed rate meets the wedge threshold." if passed else fail_reason,
        next_action=next_action,
    )


def _count_gate(
    *,
    gate_id: str,
    label: str,
    observed_count: int,
    threshold_count: int,
    evidence: str,
    insufficient_reason: str,
    next_action: str,
) -> Dict[str, Any]:
    status = "pass" if observed_count >= threshold_count else "insufficient_evidence"
    return _gate(
        gate_id,
        label,
        status,
        observed_count=observed_count,
        threshold_count=threshold_count,
        population=observed_count,
        evidence=evidence,
        reason="Live sample floor is met." if status == "pass" else insufficient_reason,
        next_action=next_action,
    )


def _gate(
    gate_id: str,
    label: str,
    status: str,
    *,
    observed_rate: Optional[float] = None,
    threshold_rate: Optional[float] = None,
    observed_count: Optional[int] = None,
    threshold_count: Optional[int] = None,
    population: Optional[int] = None,
    evidence: str,
    reason: str,
    next_action: str,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": gate_id,
        "label": label,
        "status": status,
        "population": population,
        "evidence": evidence,
        "reason": reason,
        "next_action": next_action,
    }
    if observed_rate is not None:
        payload["observed_rate"] = round(max(0.0, min(1.0, observed_rate)), 4)
        payload["observed_pct"] = round(payload["observed_rate"] * 100.0, 2)
    if threshold_rate is not None:
        payload["threshold_rate"] = round(threshold_rate, 4)
        payload["threshold_pct"] = round(threshold_rate * 100.0, 2)
    if observed_count is not None:
        payload["observed_count"] = int(observed_count)
    if threshold_count is not None:
        payload["threshold_count"] = int(threshold_count)
    return payload


def _build_next_actions(gates: List[Dict[str, Any]]) -> List[str]:
    actions: List[str] = []
    for gate in gates:
        if gate.get("status") == "pass":
            continue
        action = str(gate.get("next_action") or "").strip()
        if action and action not in actions:
            actions.append(action)
    return actions[:6]


def _truth_sample(kpis: Mapping[str, Any], sample_key: str) -> Mapping[str, Any]:
    candidates = (
        _path(kpis, "truth_samples", sample_key),
        _path(kpis, "pilot_truth_samples", sample_key),
        _path(kpis, "design_partner_truth_samples", sample_key),
        _path(kpis, "agentic_telemetry", "truth_samples", sample_key),
    )
    for candidate in candidates:
        if isinstance(candidate, Mapping) and candidate:
            return candidate
    return {}


def _rate_from_sample(sample: Mapping[str, Any]) -> Optional[float]:
    if not sample:
        return None
    for key in ("rate", "accuracy_rate", "correct_rate"):
        value = sample.get(key)
        if value is not None:
            return _float(value)
    correct = sample.get("correct_count")
    total = sample.get("sample_count") or sample.get("population") or sample.get("total_count")
    if correct is not None and total:
        denominator = _int(total)
        if denominator > 0:
            return _int(correct) / denominator
    return None


def _sample_population(sample: Mapping[str, Any]) -> int:
    return _int(sample.get("sample_count") or sample.get("population") or sample.get("total_count"))


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _path(value: Mapping[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1.0:
        number = number / 100.0
    return max(0.0, min(1.0, number))
