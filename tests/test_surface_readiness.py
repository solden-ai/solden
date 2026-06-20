from __future__ import annotations

from solden.services.surface_readiness import build_surface_readiness


class _FakeDB:
    def get_erp_connections(self, organization_id: str):
        assert organization_id == "org-1"
        return [
            {
                "erp_type": "netsuite",
                "is_active": True,
                "deep_link_id": "ns-panel",
                "last_sync_at": "2026-06-12T10:00:00Z",
            },
            {
                "erp_type": "sage_accounting",
                "is_active": False,
                "last_sync_at": "2026-06-11T10:00:00Z",
            },
        ]


class _FakeEvidenceDB(_FakeDB):
    def ensure_organization(self, organization_id: str, organization_name: str | None = None):
        assert organization_id == "org-1"
        return {
            "settings_json": {
                "ga_readiness": {
                    "connector_checklists": {
                        "quickbooks": {"completed": True, "signed_off": True},
                    },
                    "parity_evidence": [
                        {"erp_type": "quickbooks", "proof_type": "sandbox_validation"},
                        {"erp_type": "quickbooks", "proof_type": "customer_pilot"},
                        {"erp_type": "quickbooks", "proof_type": "failure_mode_matrix"},
                    ],
                    "signoffs": [
                        {"erp_type": "quickbooks", "signed_by": "eng-lead"},
                    ],
                }
            }
        }


def _surface(payload, key: str):
    return next(row for row in payload["surfaces"] if row["key"] == key)


def _constraint_keys(row):
    return {item["key"] for item in row.get("capability_constraints", [])}


def test_surface_readiness_catalog_covers_current_product_surfaces():
    payload = build_surface_readiness("")

    assert payload["contract"] == "surface_readiness.v1"
    assert payload["summary"]["total"] == 11
    assert payload["summary"]["erp_total"] == 6
    assert payload["summary"]["erp_solden_standard_status"] == "ap_operational_memory_standard"
    assert payload["summary"]["erp_solden_standard_surfaces"] == 6
    assert payload["summary"]["embedded_erp_surfaces"] == 3
    assert payload["summary"]["provider_neutral_erp_surfaces"] == 3
    assert payload["summary"]["erp_validation_pending"] == 6
    assert payload["summary"]["erp_lifecycle_gap"] == 0
    assert payload["summary"]["erp_lifecycle_constrained"] == 2

    supported_erps = [
        _surface(payload, key)
        for key in ("netsuite", "sap", "sage_intacct", "quickbooks", "xero", "sage_accounting")
    ]
    assert {row["solden_standard_status"] for row in supported_erps} == {"ap_operational_memory_standard"}
    assert {row["lifecycle_parity"]["status"] for row in supported_erps} == {"covered_with_declared_constraints"}
    assert all(row["lifecycle_parity"]["summary"]["gap_actions"] == [] for row in supported_erps)
    assert {row["maturity"] for row in supported_erps} == {"ap_operational_memory_standard"}
    assert _surface(payload, "outlook")["surface_model"] == "outlook_mail_add_in"
    assert _surface(payload, "teams")["surface_model"] == "teams_adaptive_cards"
    assert _surface(payload, "netsuite")["surface_model"] == "native_panel"
    assert _surface(payload, "sap")["memory_surface"] == "Fiori extension"
    assert _surface(payload, "sap")["surface_model"] == "fiori_extension"
    assert _surface(payload, "sage_intacct")["surface_model"] == "platform_services_panel"
    assert _surface(payload, "quickbooks")["memory_surface"] == "Provider-neutral ERP memory API"
    assert _surface(payload, "quickbooks")["surface_model"] == "provider_neutral_memory_api"
    assert _surface(payload, "xero")["surface_model"] == "provider_neutral_memory_api"
    assert _surface(payload, "sage_accounting")["connection_method"] == "OAuth 2.0"
    assert _surface(payload, "sage_accounting")["surface_model"] == "provider_neutral_memory_api"

    assert _constraint_keys(_surface(payload, "quickbooks")) == {"no_native_panel"}
    assert _constraint_keys(_surface(payload, "xero")) == {"no_native_panel"}
    assert _constraint_keys(_surface(payload, "sage_intacct")) == {
        "manual_credits",
        "manual_settlement",
        "sandbox_validation_pending",
    }
    assert _constraint_keys(_surface(payload, "sage_accounting")) == {
        "no_native_panel",
        "manual_credits",
        "manual_settlement",
        "sandbox_validation_pending",
    }
    assert _surface(payload, "sage_intacct")["validation_status"]["status"] == "sandbox_validation_pending"


def test_surface_readiness_overlays_erp_connection_state():
    payload = build_surface_readiness("org-1", db=_FakeDB())

    assert payload["summary"]["erp_connected"] == 1

    netsuite = _surface(payload, "netsuite")
    assert netsuite["connected"] is True
    assert netsuite["connection_status"] == "connected"
    assert netsuite["deep_link_id"] == "ns-panel"

    sage_accounting = _surface(payload, "sage_accounting")
    assert sage_accounting["connected"] is False
    assert sage_accounting["connection_status"] == "not_connected"


def test_surface_readiness_includes_erp_evidence_contract():
    payload = build_surface_readiness("org-1", db=_FakeEvidenceDB())

    assert payload["erp_evidence_contract"]["contract"] == "erp_evidence_contract.v1"
    assert payload["summary"]["erp_evidence_backed"] == 1
    assert payload["summary"]["erp_customer_observed"] == 1
    assert payload["summary"]["erp_missing_customer_evidence"] == 5

    quickbooks = _surface(payload, "quickbooks")
    assert quickbooks["evidence_contract"]["evidence_status"] == "evidence_backed"
    assert quickbooks["evidence_contract"]["ready_for_claim"] is True
    assert quickbooks["validation_status"]["status"] == "evidence_backed"
    assert quickbooks["validation_status"]["ready_for_claim"] is True
    assert quickbooks["solden_standard_status"] == "ap_operational_memory_standard"
    assert quickbooks["lifecycle_parity"]["status"] == "covered_with_declared_constraints"


def test_surface_readiness_overlays_non_erp_statuses():
    payload = build_surface_readiness(
        "org-1",
        integration_statuses=[
            {"name": "gmail", "connected": True, "last_sync_at": "2026-06-12T09:00:00Z"},
            {"name": "teams", "status": "disconnected"},
            {"integration_type": "slack", "connected": True, "requires_reconnect": True},
        ],
    )

    gmail = _surface(payload, "gmail")
    assert gmail["connected"] is True
    assert gmail["connection_status"] == "connected"
    assert gmail["last_sync_at"] == "2026-06-12T09:00:00Z"

    teams = _surface(payload, "teams")
    assert teams["connected"] is False
    assert teams["connection_status"] == "disconnected"

    slack = _surface(payload, "slack")
    assert slack["connected"] is True
    assert slack["requires_reauthorization"] is True
