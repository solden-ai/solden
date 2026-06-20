"""ERP AP lifecycle parity contract.

Every supported ERP targets the same Solden AP operational-memory standard.
Differences are acceptable only when the action is explicitly represented as a
capability constraint. This module ties the connector strategy to the adapter
contract so surface copy cannot hide an execution gap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set

from solden.services.erp_connector_strategy import (
    ConnectorCapability,
    get_erp_connector_strategy,
)


SOLDEN_AP_STANDARD_STATUS = "ap_operational_memory_standard"
ERP_LIFECYCLE_PARITY_CONTRACT = "erp_lifecycle_parity.v1"
SUPPORTED_AP_ERPS: tuple[str, ...] = (
    "netsuite",
    "sap",
    "sage_intacct",
    "quickbooks",
    "xero",
    "sage_accounting",
)


@dataclass(frozen=True)
class LifecycleAction:
    key: str
    label: str
    route_action: str
    adapter_validation: str
    required_constraint_key: Optional[str] = None
    governance_gate: Optional[str] = None


AP_LIFECYCLE_ACTIONS: tuple[LifecycleAction, ...] = (
    LifecycleAction(
        key="post_bill",
        label="Post AP bill",
        route_action="post_bill",
        adapter_validation="bill_post",
    ),
    LifecycleAction(
        key="apply_credit",
        label="Apply vendor credit",
        route_action="apply_credit",
        adapter_validation="credit_application",
        required_constraint_key="manual_credits",
    ),
    LifecycleAction(
        key="apply_settlement",
        label="Record settlement",
        route_action="apply_settlement",
        adapter_validation="settlement_application",
        required_constraint_key="manual_settlement",
        governance_gate="FEATURE_ERP_SETTLEMENT_WRITE",
    ),
)


async def _noop_post(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    return {"status": "success"}


async def _noop_credit(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    return {"status": "success"}


async def _noop_settlement(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    return {"status": "success"}


def _constraint_keys(capability_constraints: Iterable[Any]) -> Set[str]:
    keys: Set[str] = set()
    for item in capability_constraints or []:
        if isinstance(item, dict):
            key = str(item.get("key") or "").strip()
        else:
            key = str(item or "").strip()
        if key:
            keys.add(key)
    return keys


def _adapter_validation(erp_type: str, action: LifecycleAction) -> Dict[str, Any]:
    from solden.services.erp.contracts import (
        get_erp_bill_adapter,
        get_erp_finance_action_adapter,
    )

    token = str(erp_type or "").strip().lower()
    if action.adapter_validation == "bill_post":
        adapter = get_erp_bill_adapter(erp_type=token, post_handler=_noop_post)
        result = adapter.validate(
            {
                "invoice_number": "INV-PARITY-1",
                "vendor_name": "Parity Vendor",
                "amount": 100.0,
                "currency": "USD",
            }
        )
    else:
        adapter = get_erp_finance_action_adapter(
            erp_type=token,
            credit_handler=_noop_credit,
            settlement_handler=_noop_settlement,
        )
        payload = {
            "target_erp_reference": "ERP-BILL-PARITY-1",
            "amount": 25.0,
            "currency": "USD",
        }
        if action.adapter_validation == "credit_application":
            result = adapter.validate_credit(payload)
        else:
            result = adapter.validate_settlement(payload)

    return {
        "validates": bool(result.get("ok")),
        "reason": result.get("reason") or "unknown",
        "missing_fields": list(result.get("missing_fields") or []),
    }


def _action_support_field(action_key: str) -> str:
    if action_key == "post_bill":
        return "supports_api_post_bill"
    if action_key == "apply_credit":
        return "supports_api_apply_credit"
    if action_key == "apply_settlement":
        return "supports_api_apply_settlement"
    return ""


def build_lifecycle_parity_for_erp(
    erp_type: str,
    *,
    capability: Optional[ConnectorCapability] = None,
    capability_constraints: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Return per-action AP lifecycle parity for one ERP.

    Status semantics:
    - ``covered``: strategy routes to API and the adapter validates the action.
    - ``declared_constraint``: strategy does not route to API, but the matching
      capability constraint is declared.
    - ``gap``: the ERP lacks API support, adapter validation, or a required
      constraint declaration.
    """

    strategy = get_erp_connector_strategy()
    token = str(erp_type or "").strip().lower()
    resolved_capability = capability or strategy.resolve(token)
    constraints = _constraint_keys(capability_constraints or [])
    actions: List[Dict[str, Any]] = []

    for action in AP_LIFECYCLE_ACTIONS:
        route_plan = strategy.build_route_plan(
            erp_type=token,
            connection_present=True,
            action=action.route_action,
        )
        api_supported = bool(route_plan.get("api_supported"))
        support_field = _action_support_field(action.key)
        capability_support = (
            bool(getattr(resolved_capability, support_field, False))
            if support_field
            else False
        )
        validation = _adapter_validation(token, action)
        constraint_declared = bool(
            action.required_constraint_key and action.required_constraint_key in constraints
        )

        gap_reasons: List[str] = []
        if api_supported and not validation["validates"]:
            gap_reasons.append("adapter_validation_failed")
        if api_supported and not capability_support:
            gap_reasons.append("strategy_capability_mismatch")
        if not api_supported and not constraint_declared:
            gap_reasons.append("unsupported_without_declared_constraint")

        if api_supported and validation["validates"] and capability_support:
            status = "covered"
        elif not api_supported and constraint_declared:
            status = "declared_constraint"
        else:
            status = "gap"

        actions.append(
            {
                "key": action.key,
                "label": action.label,
                "status": status,
                "api_supported": api_supported,
                "primary_mode": route_plan.get("primary_mode"),
                "adapter_contract": validation,
                "required_constraint_key": action.required_constraint_key,
                "constraint_declared": constraint_declared,
                "governance_gate": action.governance_gate,
                "gap_reasons": gap_reasons,
            }
        )

    gap_actions = [row["key"] for row in actions if row["status"] == "gap"]
    constrained_actions = [row["key"] for row in actions if row["status"] == "declared_constraint"]
    return {
        "contract": ERP_LIFECYCLE_PARITY_CONTRACT,
        "erp_type": token,
        "solden_standard_status": SOLDEN_AP_STANDARD_STATUS,
        "status": "gap" if gap_actions else "covered_with_declared_constraints",
        "actions": actions,
        "summary": {
            "total_actions": len(actions),
            "covered_actions": sum(1 for row in actions if row["status"] == "covered"),
            "declared_constraint_actions": len(constrained_actions),
            "gap_actions": gap_actions,
            "constrained_actions": constrained_actions,
        },
    }


def build_erp_lifecycle_parity_catalog(
    *,
    constraints_by_erp: Optional[Dict[str, Iterable[Any]]] = None,
) -> Dict[str, Any]:
    strategy = get_erp_connector_strategy()
    declared_constraints = constraints_by_erp or {}
    rows = [
        build_lifecycle_parity_for_erp(
            erp_type,
            capability=strategy.resolve(erp_type),
            capability_constraints=declared_constraints.get(erp_type, []),
        )
        for erp_type in SUPPORTED_AP_ERPS
    ]
    return {
        "contract": ERP_LIFECYCLE_PARITY_CONTRACT,
        "solden_standard_status": SOLDEN_AP_STANDARD_STATUS,
        "erps": rows,
        "summary": {
            "total_erps": len(rows),
            "gap_erps": [row["erp_type"] for row in rows if row["status"] == "gap"],
        },
    }
