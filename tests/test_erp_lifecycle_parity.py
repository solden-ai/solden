from __future__ import annotations

from solden.services.erp_lifecycle_parity import (
    SUPPORTED_AP_ERPS,
    build_erp_lifecycle_parity_catalog,
    build_lifecycle_parity_for_erp,
)
from solden.services.surface_readiness import build_surface_readiness


def _surface(payload, key: str):
    return next(row for row in payload["surfaces"] if row["key"] == key)


def _action(report, key: str):
    return next(row for row in report["actions"] if row["key"] == key)


def _declared_constraints(payload) -> dict[str, list[dict[str, str]]]:
    return {
        key: list((_surface(payload, key).get("capability_constraints") or []))
        for key in SUPPORTED_AP_ERPS
    }


def test_surface_readiness_embeds_lifecycle_parity_for_every_supported_erp():
    payload = build_surface_readiness("")

    assert payload["summary"]["erp_lifecycle_gap"] == 0
    assert payload["summary"]["erp_lifecycle_constrained"] == 2

    for erp_type in SUPPORTED_AP_ERPS:
        parity = _surface(payload, erp_type)["lifecycle_parity"]
        assert parity["contract"] == "erp_lifecycle_parity.v1"
        assert parity["erp_type"] == erp_type
        assert parity["solden_standard_status"] == "ap_operational_memory_standard"
        assert parity["status"] == "covered_with_declared_constraints"
        assert parity["summary"]["gap_actions"] == []
        assert _action(parity, "post_bill")["status"] == "covered"


def test_api_first_erps_cover_full_ap_lifecycle_without_weakening_the_standard():
    payload = build_surface_readiness("")

    for erp_type in ("netsuite", "sap", "quickbooks", "xero"):
        parity = _surface(payload, erp_type)["lifecycle_parity"]
        assert _action(parity, "apply_credit")["status"] == "covered"
        assert _action(parity, "apply_settlement")["status"] == "covered"
        assert parity["summary"]["declared_constraint_actions"] == 0
        for action in parity["actions"]:
            assert action["adapter_contract"]["validates"] is True
            assert action["api_supported"] is True


def test_sage_limitations_are_declared_constraints_not_maturity_tiers():
    payload = build_surface_readiness("")

    for erp_type in ("sage_intacct", "sage_accounting"):
        row = _surface(payload, erp_type)
        parity = row["lifecycle_parity"]
        constraint_keys = {item["key"] for item in row["capability_constraints"]}

        assert row["solden_standard_status"] == "ap_operational_memory_standard"
        assert parity["status"] == "covered_with_declared_constraints"
        assert constraint_keys >= {"manual_credits", "manual_settlement"}

        credit = _action(parity, "apply_credit")
        settlement = _action(parity, "apply_settlement")
        assert credit["status"] == "declared_constraint"
        assert credit["required_constraint_key"] == "manual_credits"
        assert credit["constraint_declared"] is True
        assert settlement["status"] == "declared_constraint"
        assert settlement["required_constraint_key"] == "manual_settlement"
        assert settlement["constraint_declared"] is True


def test_missing_constraint_declaration_turns_unsupported_lifecycle_action_into_gap():
    report = build_lifecycle_parity_for_erp("sage_intacct", capability_constraints=[])

    assert report["status"] == "gap"
    assert set(report["summary"]["gap_actions"]) == {"apply_credit", "apply_settlement"}
    assert _action(report, "apply_credit")["gap_reasons"] == ["unsupported_without_declared_constraint"]
    assert _action(report, "apply_settlement")["gap_reasons"] == ["unsupported_without_declared_constraint"]


def test_lifecycle_parity_catalog_uses_declared_constraints_when_supplied():
    payload = build_surface_readiness("")
    catalog = build_erp_lifecycle_parity_catalog(
        constraints_by_erp=_declared_constraints(payload),
    )

    assert catalog["contract"] == "erp_lifecycle_parity.v1"
    assert catalog["summary"]["total_erps"] == 6
    assert catalog["summary"]["gap_erps"] == []
