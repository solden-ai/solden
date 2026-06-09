"""Resolve the real per-org AP policy version (M5).

Replaces the hardcoded ``CURRENT_AP_POLICY_VERSION = "v1"`` with a version that
reflects the org's ACTUAL decision config — routing thresholds, fraud controls,
match mode/tolerances, confidence gate. Built on the existing ``PolicyService``
registry: ``set_policy`` is idempotent on content_hash, so an unchanged config
returns the same version and a config change mints a new one. Resolvable: a
stamped ``v{N}`` maps to its snapshot in ``policy_versions`` (kind
``ap_decision_policy``), so an auditor can see exactly which thresholds/fraud/
match config governed a decision.

Best-effort throughout: any failure falls back to ``CURRENT_AP_POLICY_VERSION``
so a decision or transition NEVER breaks on policy resolution.
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Any, Dict

from solden.core.ap_states import CURRENT_AP_POLICY_VERSION

logger = logging.getLogger(__name__)

AP_DECISION_POLICY_KIND = "ap_decision_policy"


def _as_plain_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if dataclasses.is_dataclass(value):
        try:
            return dataclasses.asdict(value)
        except Exception:
            return dict(getattr(value, "__dict__", {}) or {})
    return dict(getattr(value, "__dict__", {}) or {})


def _ap_decision_policy_snapshot(db: Any, organization_id: str) -> Dict[str, Any]:
    """The effective config that governs an AP routing decision. Read in place;
    each piece is best-effort so a missing reader degrades, never raises."""
    snapshot: Dict[str, Any] = {}
    try:
        from solden.services.threshold_policy import get_org_thresholds
        snapshot["routing_thresholds"] = get_org_thresholds(db, organization_id) or {}
    except Exception:
        snapshot["routing_thresholds"] = {}
    try:
        from solden.core.fraud_controls import load_fraud_controls
        snapshot["fraud_controls"] = _as_plain_dict(load_fraud_controls(organization_id, db))
    except Exception:
        snapshot["fraud_controls"] = {}
    try:
        from solden.services.policy_service import PolicyService
        svc = PolicyService(organization_id)
        for kind in ("match_mode", "match_tolerances", "confidence_gate"):
            try:
                snapshot[kind] = svc.get_active(kind).content or {}
            except Exception:
                snapshot[kind] = {}
    except Exception:
        pass
    return snapshot


def resolve_ap_policy_version(db: Any, organization_id: str) -> str:
    """The org's current AP decision-policy version (e.g. ``"v3"``).

    Idempotent: unchanged config returns the same version (PolicyService dedups
    on content_hash); a config change mints the next version. Best-effort:
    falls back to ``CURRENT_AP_POLICY_VERSION`` on any error.
    """
    org_id = str(organization_id or "").strip()
    if not org_id:
        return CURRENT_AP_POLICY_VERSION
    try:
        from solden.services.policy_service import PolicyService
        snapshot = _ap_decision_policy_snapshot(db, org_id)
        pv = PolicyService(org_id).set_policy(
            AP_DECISION_POLICY_KIND,
            snapshot,
            actor="system",
            description="effective AP decision policy (auto-snapshot)",
        )
        return f"v{pv.version_number}"
    except Exception as exc:  # noqa: BLE001
        logger.debug("[ap_policy_version] resolve failed for %s: %s", org_id, exc)
        return CURRENT_AP_POLICY_VERSION
