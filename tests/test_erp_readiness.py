from __future__ import annotations

from solden.core import database as db_module
from solden.core.launch_controls import set_ga_readiness, set_rollback_controls
from solden.services.erp_readiness import evaluate_erp_connector_readiness


def _db(tmp_path, monkeypatch):
    db = db_module.get_db()
    db.initialize()
    return db

def test_connector_readiness_passes_for_enabled_connector_with_completed_checklist(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    db.save_erp_connection(
        organization_id="org-test",
        erp_type="quickbooks",
        access_token="token",
        refresh_token="refresh",
        realm_id="realm-1",
    )
    set_ga_readiness(
        "org-test",
        {
            "connector_checklists": {
                "quickbooks": {"completed": True, "signed_off": True},
            }
        },
        updated_by="owner-1",
        db=db,
    )

    readiness = evaluate_erp_connector_readiness("org-test", db=db)
    summary = readiness["summary"]
    quickbooks = next(row for row in readiness["connectors"] if row["erp_type"] == "quickbooks")

    assert summary["status"] == "pass"
    assert summary["configured_connectors_total"] == 1
    assert summary["enabled_connectors_total"] == 1
    assert summary["enabled_connectors_ready"] == 1
    assert summary["enabled_readiness_rate"] == 1.0
    assert quickbooks["ready"] is True
    assert quickbooks["readiness_status"] == "ready"
    assert quickbooks["evidence_contract"]["customer_evidence_status"] == "missing"


def test_connector_readiness_blocks_when_configured_connector_is_rollback_disabled(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    db.save_erp_connection(
        organization_id="org-test",
        erp_type="quickbooks",
        access_token="token",
        refresh_token="refresh",
        realm_id="realm-1",
    )
    set_ga_readiness(
        "org-test",
        {
            "connector_checklists": {
                "quickbooks": {"completed": True, "signed_off": True},
            }
        },
        updated_by="owner-1",
        db=db,
    )
    set_rollback_controls(
        "org-test",
        {"erp_connectors_disabled": ["quickbooks"], "reason": "incident"},
        updated_by="owner-1",
        db=db,
    )

    readiness = evaluate_erp_connector_readiness("org-test", db=db)
    summary = readiness["summary"]
    quickbooks = next(row for row in readiness["connectors"] if row["erp_type"] == "quickbooks")

    assert summary["status"] == "blocked"
    assert summary["enabled_connectors_total"] == 0
    assert "quickbooks:disabled_by_rollback" in summary["blocked_reasons"]
    assert quickbooks["rollback_blocked"] is True
    assert quickbooks["readiness_status"] == "disabled_by_rollback"


def test_connector_readiness_requires_evidence_in_strict_ga_scope(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    db.save_erp_connection(
        organization_id="org-test",
        erp_type="quickbooks",
        access_token="token",
        refresh_token="refresh",
        realm_id="realm-1",
    )
    set_ga_readiness(
        "org-test",
        {
            "connector_checklists": {
                "quickbooks": {"completed": True, "signed_off": True},
            },
            "parity_evidence": [
                {
                    "erp_type": "quickbooks",
                    "proof_type": "sandbox_validation",
                    "artifact": "qbo-sandbox.md",
                }
            ],
        },
        updated_by="owner-1",
        db=db,
    )

    readiness = evaluate_erp_connector_readiness(
        "org-test",
        db=db,
        connector_scope=["quickbooks"],
        require_full_ga_scope=True,
    )
    summary = readiness["summary"]
    quickbooks = next(row for row in readiness["connectors"] if row["erp_type"] == "quickbooks")

    assert summary["status"] == "blocked"
    assert summary["sandbox_evidence_observed"] == 1
    assert summary["customer_evidence_observed"] == 0
    assert "quickbooks:evidence_incomplete" in summary["blocked_reasons"]
    assert quickbooks["ready"] is False
    assert quickbooks["readiness_status"] == "pending_evidence"


def test_connector_readiness_passes_strict_ga_scope_when_evidence_is_complete(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    db.save_erp_connection(
        organization_id="org-test",
        erp_type="quickbooks",
        access_token="token",
        refresh_token="refresh",
        realm_id="realm-1",
    )
    set_ga_readiness(
        "org-test",
        {
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
        },
        updated_by="owner-1",
        db=db,
    )

    readiness = evaluate_erp_connector_readiness(
        "org-test",
        db=db,
        connector_scope=["quickbooks"],
        require_full_ga_scope=True,
    )
    summary = readiness["summary"]
    quickbooks = next(row for row in readiness["connectors"] if row["erp_type"] == "quickbooks")

    assert summary["status"] == "pass"
    assert summary["evidence_backed_connectors"] == 1
    assert summary["evidence_ready_for_ga_claims"] is True
    assert quickbooks["ready"] is True
    assert quickbooks["evidence_contract"]["evidence_status"] == "evidence_backed"
