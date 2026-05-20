"""Tiered approval thresholds for the procurement (purchase_order) workflow.

Distinct from ``fraud_controls`` (which is an AP payment *ceiling*): this
is amount-tiered *approval routing* for POs —

  * amount <= ``auto_approve_ceiling``   → agent may auto-approve
  * amount  > ``dual_approval_above``     → two approvers required
  * otherwise                             → single human approver

Stored under ``settings_json["procurement_thresholds"]``. Every change is
audited, mirroring fraud_controls. FX is intentionally out of scope for
now — the comparison is in the PO's own currency (multi-currency tiering
lands with the Phase 5 hardening pass).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_AUTO_APPROVE_CEILING = 1_000.0
DEFAULT_DUAL_APPROVAL_ABOVE = 25_000.0


@dataclass(frozen=True)
class ProcurementThresholds:
    auto_approve_ceiling: float = DEFAULT_AUTO_APPROVE_CEILING
    dual_approval_above: float = DEFAULT_DUAL_APPROVAL_ABOVE
    base_currency: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls, data: Optional[Dict[str, Any]], *, base_currency: str = ""
    ) -> "ProcurementThresholds":
        data = data or {}

        def _float(key: str, default: float) -> float:
            try:
                value = float(data.get(key, default))
                return value if value >= 0 else default
            except (TypeError, ValueError):
                logger.warning(
                    "[ProcurementThresholds] %s not numeric (%r); using %s",
                    key, data.get(key), default,
                )
                return default

        return cls(
            auto_approve_ceiling=_float("auto_approve_ceiling", DEFAULT_AUTO_APPROVE_CEILING),
            dual_approval_above=_float("dual_approval_above", DEFAULT_DUAL_APPROVAL_ABOVE),
            base_currency=(str(data.get("base_currency") or base_currency or "")).upper(),
        )


@dataclass(frozen=True)
class POApprovalRouting:
    """How a PO of a given amount should be routed for approval."""

    auto_approvable: bool
    requires_dual_approval: bool
    amount: float
    tier: str  # "auto" | "single" | "dual"


def evaluate_po_approval(
    amount: float, config: ProcurementThresholds
) -> POApprovalRouting:
    """Classify a PO amount into an approval tier (PO-currency comparison)."""
    amt = float(amount or 0.0)
    if amt > config.dual_approval_above:
        return POApprovalRouting(False, True, amt, "dual")
    if amt <= config.auto_approve_ceiling:
        return POApprovalRouting(True, False, amt, "auto")
    return POApprovalRouting(False, False, amt, "single")


def _load_org_settings(org_id: str, db: Any) -> Dict[str, Any]:
    try:
        org = db.get_organization(org_id)
    except Exception as exc:
        logger.warning("[ProcurementThresholds] Could not load org %s: %s", org_id, exc)
        return {}
    if not org:
        return {}
    settings = org.get("settings") or org.get("settings_json") or {}
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except json.JSONDecodeError:
            settings = {}
    return settings if isinstance(settings, dict) else {}


def load_procurement_thresholds(org_id: str, db: Any) -> ProcurementThresholds:
    settings = _load_org_settings(org_id, db)
    return ProcurementThresholds.from_dict(settings.get("procurement_thresholds"))


def save_procurement_thresholds(
    org_id: str,
    config: ProcurementThresholds,
    *,
    modified_by: str,
    db: Any,
) -> ProcurementThresholds:
    """Persist thresholds + emit an audit event (no silent modifications)."""
    previous = load_procurement_thresholds(org_id, db)
    settings = _load_org_settings(org_id, db)
    settings["procurement_thresholds"] = config.to_dict()
    db.update_organization(org_id, settings=settings)
    try:
        db.append_audit_event({
            "ap_item_id": "",
            "event_type": "procurement_thresholds_modified",
            "actor_type": "user",
            "actor_id": modified_by,
            "reason": "Procurement approval thresholds updated",
            "metadata": {
                "entity_type": "procurement_thresholds",
                "entity_id": org_id,
                "previous": previous.to_dict(),
                "current": config.to_dict(),
                "modified_at": datetime.now(timezone.utc).isoformat(),
            },
            "organization_id": org_id,
            "source": "procurement_thresholds_api",
        })
    except Exception as audit_exc:
        logger.error(
            "[ProcurementThresholds] Audit write failed for org %s: %s",
            org_id, audit_exc,
        )
        raise
    return config
