"""Behavior → standing-policy proposals (tribal-knowledge Build 3).

Detects stable enacted behavior — a human repeatedly approving what the agent
escalated for one vendor — and proposes it back as an explicit, BOUNDED
standing rule. Proposals are advisory rows: creating one changes nothing;
accepting lands a rules-table row (the cascade's existing Step-1 mechanism,
versioned via rule_versions); declining records a deliberate non-rule with its
reason and is never re-proposed.

Deterministic throughout: thresholds + observed amounts, no LLM.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from solden.core.feature_flags import is_policy_proposals_enabled
from solden.services.agent_memory import AgentMemoryService
from solden.services.ap_learning_loop import PRIVATE_OUTCOME_EVAL_TYPE

logger = logging.getLogger(__name__)

PROPOSAL_KIND_VENDOR_STANDING_APPROVAL = "vendor_standing_approval"

# Higher than the soft-dampen threshold (3): a proposal asks the human to make
# the pattern POLICY, so the evidence bar is higher than quietly de-escalating.
MIN_APPROVE_AFTER_ESCALATE = 5
# The proposed rule is bounded by observed history — never unbounded.
AMOUNT_CAP_MULTIPLIER = 1.2
_HISTORY_LIMIT = 20
_VENDOR_SCAN_LIMIT = 25


_APPROVED_FINAL_STATES = {"approved", "posted_to_erp", "paid", "closed"}


def _observed_amount_cap(
    db: Any, organization_id: str, vendor_name: str
) -> Optional[Dict[str, Any]]:
    """The amount bound for the proposed rule, from APPROVED history only and
    within ONE currency.

    Rejected/exception invoices must not inflate the cap, and amounts in mixed
    currencies must not be compared — the cap comes from the vendor's dominant
    currency and the rule carries a matching currency clause. Returns
    ``{"cap": float, "currency": str}`` or None (no bound -> no proposal).
    """
    try:
        history = db.get_vendor_invoice_history(
            organization_id, vendor_name, limit=_HISTORY_LIMIT
        ) or []
    except Exception:
        return None
    by_currency: Dict[str, List[float]] = {}
    for row in history:
        row = row or {}
        approved = bool(row.get("was_approved")) or (
            str(row.get("final_state") or "").strip().lower() in _APPROVED_FINAL_STATES
        )
        if not approved:
            continue
        try:
            value = float(row.get("amount"))
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        currency = str(row.get("currency") or "").strip().upper()
        by_currency.setdefault(currency, []).append(value)
    if not by_currency:
        return None
    # Dominant currency = the one with the most approved rows.
    currency = max(by_currency, key=lambda c: len(by_currency[c]))
    amounts = by_currency[currency]
    if not currency:
        # History rows without a currency can't safely bound a money rule.
        return None
    return {
        "cap": round(max(amounts) * AMOUNT_CAP_MULTIPLIER, 2),
        "currency": currency,
    }


def _proposed_rule(vendor_name: str, amount_cap: float, currency: str) -> Dict[str, Any]:
    """A rules-table payload (the cascade's existing Step-1 shape) — identical
    semantics to a manually created rule. Bounded by amount AND currency."""
    return {
        "name": f"Standing approval: {vendor_name} under {amount_cap:,.2f} {currency}",
        "priority": 100,
        "workflow": "ap",
        "conditions": {
            "all_of": [
                {"field": "vendor_name", "op": "eq", "value": vendor_name},
                {"field": "amount", "op": "lt", "value": amount_cap},
                {"field": "currency", "op": "eq", "value": currency},
            ],
        },
        "actions": [{"type": "auto_approve"}],
    }


def _compact(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in payload.items() if v is not None and v != [] and v != {}}


def _vendor_count_from_pattern(pattern: Dict[str, Any], vendor_name: str) -> Optional[int]:
    target = str(vendor_name or "").strip().lower()
    if not target:
        return None
    for row in pattern.get("affected_vendors") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("vendor_name") or "").strip().lower() != target:
            continue
        try:
            return int(row.get("count") or 0)
        except (TypeError, ValueError):
            return None
    return None


def _recurring_pattern_citation(
    patterns: List[Dict[str, Any]], vendor_name: str
) -> Dict[str, Any]:
    for row in patterns:
        pattern = row.get("pattern") if isinstance(row, dict) else {}
        if not isinstance(pattern, dict):
            continue
        vendor_count = _vendor_count_from_pattern(pattern, vendor_name)
        if not vendor_count:
            continue
        examples = [
            str(item_id)
            for item_id in (pattern.get("example_item_ids") or [])
            if item_id
        ][:3]
        return _compact({
            "pattern_type": row.get("pattern_type"),
            "pattern_key": row.get("pattern_key"),
            "label": pattern.get("label"),
            "count": pattern.get("count"),
            "vendor_count": vendor_count,
            "share": pattern.get("share"),
            "confidence": row.get("confidence"),
            "updated_at": row.get("updated_at"),
            "example_item_ids": examples,
        })
    return {}


def _private_eval_citation(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    payload = snapshot.get("payload") if isinstance(snapshot, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    release_gate = (
        payload.get("release_gate") if isinstance(payload.get("release_gate"), dict) else {}
    )
    return _compact({
        "snapshot_type": snapshot.get("snapshot_type"),
        "created_at": snapshot.get("created_at"),
        "contract": payload.get("contract"),
        "scope": payload.get("scope"),
        "total_items": summary.get("total_items"),
        "memory_event_coverage_rate": summary.get("memory_event_coverage_rate"),
        "agent_trace_rate": summary.get("agent_trace_rate"),
        "evidence_link_rate": summary.get("evidence_link_rate"),
        "outcome_traceability_rate": summary.get("outcome_traceability_rate"),
        "release_gate_status": release_gate.get("status"),
    })


def _learning_citation(db: Any, organization_id: str, vendor_name: str) -> Dict[str, Any]:
    """Attach the learning-loop evidence that made this proposal defensible.

    This must remain best-effort: a missing eval snapshot should never block
    proposal detection, but when a snapshot or recurring pattern exists the
    proposed policy should cite it explicitly.
    """
    try:
        memory = AgentMemoryService(organization_id, db=db)
        snapshot = memory.latest_eval_snapshot(
            skill_id="ap_v1",
            scope="organization",
            snapshot_type=PRIVATE_OUTCOME_EVAL_TYPE,
        )
        patterns = memory.list_patterns(
            skill_id="ap_v1",
            pattern_type="company_ap_blocker",
            limit=20,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[policy_proposals] learning citation lookup failed for %s/%s: %s",
            organization_id, vendor_name, exc,
        )
        return {}

    citation = _compact({
        "source": "ap_learning_loop",
        "source_label": "AP learning loop",
        "private_eval_snapshot": _private_eval_citation(snapshot) if snapshot else {},
        "recurring_pattern": _recurring_pattern_citation(patterns, vendor_name),
    })
    return citation


def detect_policy_proposals(db: Any, organization_id: str) -> List[Dict[str, Any]]:
    """Scan recent decision feedback for proposal-worthy patterns. Returns the
    proposals created this pass (suppression handled by the store: one open
    proposal per vendor+kind; declined = never re-nag)."""
    if not is_policy_proposals_enabled():
        return []
    org_id = str(organization_id or "").strip()
    if not org_id:
        return []

    created: List[Dict[str, Any]] = []
    try:
        vendors = db.list_recent_feedback_vendors(
            organization_id=org_id, limit=_VENDOR_SCAN_LIMIT
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[policy_proposals] vendor scan failed for %s: %s", org_id, exc)
        return []

    for vendor in vendors:
        try:
            summary = db.get_vendor_decision_feedback_summary(org_id, vendor) or {}
            approves = int(summary.get("approve_after_escalate_count") or 0)
            rejects = int(summary.get("reject_count") or 0)
            if approves < MIN_APPROVE_AFTER_ESCALATE or rejects > 0:
                continue
            bound = _observed_amount_cap(db, org_id, vendor)
            if not bound:
                # Can't bound the rule by approved, single-currency amounts ->
                # don't propose.
                continue
            amount_cap = bound["cap"]
            currency = bound["currency"]
            window_days = int(summary.get("window_days") or 180)
            behavior_summary = (
                f"You've approved {vendor}'s invoices {approves} times after the "
                f"agent escalated them (last {window_days} days, no rejections). "
                f"Make it a standing rule? Auto-approve {vendor} invoices under "
                f"{amount_cap:,.2f} {currency}."
            )
            evidence = {
                "approve_after_escalate_count": approves,
                "window_days": window_days,
                "amount_cap": amount_cap,
                "currency": currency,
                "feedback_summary": {
                    k: summary.get(k)
                    for k in (
                        "total_feedback", "approve_count", "reject_count",
                        "override_rate", "strictness_bias",
                    )
                },
            }
            learning_citation = _learning_citation(db, org_id, vendor)
            if learning_citation:
                evidence["learning_citation"] = learning_citation
            proposal = db.create_policy_proposal(
                organization_id=org_id,
                proposal_kind=PROPOSAL_KIND_VENDOR_STANDING_APPROVAL,
                vendor_name=vendor,
                behavior_summary=behavior_summary,
                evidence=evidence,
                proposed_rule=_proposed_rule(vendor, amount_cap, currency),
            )
            if not proposal:
                continue  # suppressed (pending, accepted, or declined exists)
            created.append(proposal)
            # Advisory governance audit — org-keyed (no work item).
            try:
                db.append_audit_event({
                    "ap_item_id": "",
                    "event_type": "policy_proposal_created",
                    "actor_type": "agent",
                    "actor_id": "policy_proposal_detector",
                    "organization_id": org_id,
                    "reason": behavior_summary,
                    "payload_json": {
                        "proposal_id": proposal.get("id"),
                        "proposal_kind": PROPOSAL_KIND_VENDOR_STANDING_APPROVAL,
                        "vendor_name": vendor,
                        "amount_cap": amount_cap,
                        **(
                            {"learning_citation": learning_citation}
                            if learning_citation else {}
                        ),
                    },
                })
            except Exception as audit_exc:  # noqa: BLE001
                logger.warning(
                    "[policy_proposals] proposal audit failed for %s: %s",
                    vendor, audit_exc,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[policy_proposals] detection failed for %s/%s: %s",
                org_id, vendor, exc,
            )
    return created
