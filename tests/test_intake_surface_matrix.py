from __future__ import annotations

from pathlib import Path

from solden.services.intake_surface_matrix import (
    RELEASE_INTAKE_SURFACE_MATRIX,
    build_intake_surface_matrix,
    ensure_release_intake_adapters_imported,
)
from solden.services.surface_memory_contract import SURFACE_MEMORY_CONTRACTS


ROOT = Path(__file__).resolve().parents[1]


def _intake(payload: dict, key: str) -> dict:
    return next(row for row in payload["intakes"] if row["key"] == key)


def test_intake_surface_matrix_is_release_complete():
    ensure_release_intake_adapters_imported()

    payload = build_intake_surface_matrix(repo_root=ROOT)

    assert payload["contract"] == "intake_surface_matrix.v1"
    assert payload["summary"]["total"] == 9
    assert payload["summary"]["ready"] == 9
    assert payload["summary"]["needs_work"] == 0
    assert {row["key"] for row in payload["intakes"]} == {
        "gmail",
        "outlook",
        "peppol_ubl",
        "netsuite",
        "sap",
        "quickbooks",
        "xero",
        "sage_intacct",
        "sage_accounting",
    }

    for row in payload["intakes"]:
        assert row["source_type_declared"], row
        assert row["identity_key_ok"], row
        assert row["missing_surface_contracts"] == [], row
        assert row["missing_source_files"] == [], row
        assert row["missing_source_tokens"] == {}, row


def test_erp_native_release_intakes_are_adapter_registered():
    ensure_release_intake_adapters_imported()

    payload = build_intake_surface_matrix(repo_root=ROOT)

    erp_rows = [row for row in payload["intakes"] if row["family"] == "erp_native"]
    assert {row["source_type"] for row in erp_rows} == {
        "netsuite",
        "sap_s4hana",
        "quickbooks",
        "xero",
        "sage_intacct",
        "sage_accounting",
    }
    for row in erp_rows:
        assert row["requires_adapter"] is True
        assert row["adapter_registered"] is True, row
        assert row["erp_native"] is True, row
        assert row["identity_key"].startswith(f"{row['source_type']}-bill:"), row


def test_non_erp_release_intakes_keep_non_erp_identity_keys():
    payload = build_intake_surface_matrix(repo_root=ROOT)

    assert _intake(payload, "gmail")["identity_key"] == "gmail-msg-1"
    assert _intake(payload, "outlook")["identity_key"] == "outlook:outlook-msg-1"
    assert _intake(payload, "peppol_ubl")["identity_key"] == "peppol_ubl:INV-PEPPOL-1"
    assert _intake(payload, "gmail")["erp_native"] is False
    assert _intake(payload, "outlook")["erp_native"] is False
    assert _intake(payload, "peppol_ubl")["erp_native"] is False


def test_intake_render_obligations_are_backed_by_surface_memory_contracts():
    payload = build_intake_surface_matrix(repo_root=ROOT)
    surface_keys = {contract.key for contract in SURFACE_MEMORY_CONTRACTS}
    ready_surface_keys = {
        contract.key
        for contract in SURFACE_MEMORY_CONTRACTS
        if contract.write_contracts
        and contract.read_contracts
        and contract.write_paths
        and contract.read_paths
    }

    for row in payload["intakes"]:
        required = set(row["required_surface_keys"])
        assert required <= surface_keys, row
        assert required <= ready_surface_keys, row

    for key in ("gmail", "outlook", "netsuite", "sap", "quickbooks", "xero", "sage_intacct", "sage_accounting"):
        row = _intake(payload, key)
        assert key in row["required_surface_keys"], row

    peppol = _intake(payload, "peppol_ubl")
    assert set(peppol["required_surface_keys"]) == {"workspace", "slack", "teams"}


def test_memory_source_surfaces_match_accepted_surface_contract_aliases():
    accepted_by_key = {
        contract.key: set(contract.accepted_event_surfaces)
        for contract in SURFACE_MEMORY_CONTRACTS
    }

    for case in RELEASE_INTAKE_SURFACE_MATRIX:
        source_surfaces = set(case.memory_source_surfaces)
        if case.key == "peppol_ubl":
            assert source_surfaces == {"peppol_ubl"}
            continue
        if case.key == "sap":
            accepted = accepted_by_key["sap"]
        else:
            accepted = accepted_by_key[case.key]
        assert source_surfaces & accepted, case
