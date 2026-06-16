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


def test_surface_readiness_catalog_covers_current_product_surfaces():
    payload = build_surface_readiness("")

    assert payload["contract"] == "surface_readiness.v1"
    assert payload["summary"]["total"] == 11
    assert payload["summary"]["erp_total"] == 6

    assert _surface(payload, "outlook")["maturity"] == "production_ready"
    assert _surface(payload, "teams")["maturity"] == "production_ready"
    assert _surface(payload, "netsuite")["maturity"] == "native_panel_ready"
    assert _surface(payload, "sap")["memory_surface"] == "Fiori extension"
    assert _surface(payload, "sage_intacct")["maturity"] == "sandbox_pending"
    assert _surface(payload, "quickbooks")["memory_surface"] == "Provider-neutral ERP memory API"
    assert _surface(payload, "xero")["maturity"] == "api_memory_ready"
    assert _surface(payload, "sage_accounting")["connection_method"] == "OAuth 2.0"


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
