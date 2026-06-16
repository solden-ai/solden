from __future__ import annotations

from solden.core import database as db_module
from solden.core.launch_controls import set_ga_readiness
from solden.services.erp_evidence_contract import build_erp_evidence_contract


def _db():
    db = db_module.get_db()
    db.initialize()
    return db


def _connector(payload, erp_type: str):
    return next(row for row in payload["connectors"] if row["erp_type"] == erp_type)


def test_erp_evidence_contract_separates_sandbox_customer_and_governance_proof():
    db = _db()
    set_ga_readiness(
        "org-erp-evidence",
        {
            "connector_checklists": {
                "quickbooks": {"completed": True, "signed_off": True},
                "xero": {"completed": True, "signed_off": True},
            },
            "parity_evidence": [
                {
                    "erp_type": "quickbooks",
                    "proof_type": "sandbox_validation",
                    "artifact": "qbo-sandbox-2026-06-16.md",
                },
                {
                    "connector": "qbo",
                    "stage": "customer pilot",
                    "artifact": "qbo-customer-pilot-2026-06-16.md",
                },
                {
                    "erp_type": "quickbooks",
                    "proof_type": "failure_mode_matrix",
                    "artifact": "qbo-failure-modes-2026-06-16.md",
                },
                {
                    "erp_type": "xero",
                    "proof_type": "sandbox_validation",
                    "artifact": "xero-sandbox-2026-06-16.md",
                },
            ],
            "runbooks": [
                {
                    "erp_type": "quickbooks",
                    "name": "QuickBooks rollback runbook",
                    "url": "https://runbooks.example.com/qbo",
                }
            ],
            "signoffs": [
                {
                    "erp_type": "quickbooks",
                    "signed_by": "eng-lead",
                    "signed_at": "2026-06-16T10:00:00Z",
                }
            ],
        },
        updated_by="owner-1",
        db=db,
    )

    payload = build_erp_evidence_contract(
        "org-erp-evidence",
        db=db,
        connector_scope=["quickbooks", "xero", "netsuite"],
    )

    quickbooks = _connector(payload, "quickbooks")
    assert quickbooks["evidence_status"] == "evidence_backed"
    assert quickbooks["ready_for_claim"] is True
    assert quickbooks["proof_types_observed"] == ["customer", "failure_mode", "sandbox"]
    assert quickbooks["known_gaps"] == []

    xero = _connector(payload, "xero")
    assert xero["evidence_status"] == "sandbox_only"
    assert xero["ready_for_claim"] is False
    assert "customer_evidence_missing" in xero["known_gaps"]
    assert "erp_signoff_missing" in xero["known_gaps"]

    netsuite = _connector(payload, "netsuite")
    assert netsuite["evidence_status"] == "missing_evidence"
    assert "sandbox_evidence_missing" in netsuite["known_gaps"]

    summary = payload["summary"]
    assert summary["total"] == 3
    assert summary["evidence_backed"] == 1
    assert summary["sandbox_observed"] == 2
    assert summary["customer_observed"] == 1
    assert summary["ready_for_ga_claims"] is False


def test_empty_erp_evidence_contract_is_safe_without_database_access():
    payload = build_erp_evidence_contract("", connector_scope=["quickbooks"])

    quickbooks = _connector(payload, "quickbooks")
    assert quickbooks["evidence_status"] == "missing_evidence"
    assert payload["summary"]["missing_customer_evidence"] == 1
