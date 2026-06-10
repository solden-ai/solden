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
            proposal = db.create_policy_proposal(
                organization_id=org_id,
                proposal_kind=PROPOSAL_KIND_VENDOR_STANDING_APPROVAL,
                vendor_name=vendor,
                behavior_summary=behavior_summary,
                evidence={
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
                },
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
