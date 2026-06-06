from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.testclient import TestClient

from solden.api import erp_memory_surface
from solden.core.auth import get_current_user
from solden.core import database as db_module


def _user(org_id: str = "org-erp-memory"):
    return SimpleNamespace(
        user_id="user-erp-memory",
        email="ops@example.com",
        organization_id=org_id,
        role="owner",
    )


def _client(db, user=None):
    app = FastAPI()
    app.include_router(erp_memory_surface.router)
    resolved_user = user or _user()
    app.dependency_overrides[get_current_user] = lambda: resolved_user
    app.dependency_overrides[erp_memory_surface.get_current_user] = lambda: resolved_user
    erp_memory_surface._get_db = lambda: db
    return TestClient(app)


def _db():
    db = db_module.get_db()
    db.initialize()
    db.ensure_organization("org-erp-memory", organization_name="ERP Memory")
    return db


def _create_item(db, *, item_id: str, erp_reference: str, erp_type: str = "quickbooks") -> Dict[str, Any]:
    return db.create_ap_item({
        "id": item_id,
        "organization_id": "org-erp-memory",
        "invoice_key": f"key-{item_id}",
        "thread_id": f"thread-{item_id}",
        "message_id": f"msg-{item_id}",
        "vendor_name": "Acme Cloud",
        "amount": 1200.0,
        "currency": "USD",
        "invoice_number": f"INV-{item_id}",
        "state": "needs_approval",
        "erp_reference": erp_reference,
        "metadata": {"erp_type": erp_type},
    })


def test_quickbooks_erp_reference_returns_live_operational_memory():
    db = _db()
    _create_item(db, item_id="AP-QB-MEMORY", erp_reference="QB-BILL-100", erp_type="quickbooks")
    db.append_audit_event({
        "ap_item_id": "AP-QB-MEMORY",
        "event_type": "approval_requested",
        "actor_type": "agent",
        "actor_id": "ap-agent",
        "organization_id": "org-erp-memory",
        "source": "quickbooks",
        "decision_reason": "Amount exceeds the auto-posting threshold.",
        "payload_json": {
            "dependency": {
                "type": "approval",
                "owner": "Controller",
                "reason": "Amount exceeds the auto-posting threshold.",
            },
            "next_action": "Controller approval",
        },
        "external_refs": {"erp_record_id": "QB-BILL-100"},
    })

    client = _client(db)
    response = client.get("/extension/ap-items/by-erp-reference/quickbooks/QB-BILL-100")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["erp_type"] == "quickbooks"
    assert body["erp_reference"] == "QB-BILL-100"
    assert body["surface"]["source_channel"] == "erp_native_quickbooks"
    assert body["surface"]["memory_contract"] == "solden_memory_surface.v1"
    assert body["memory"]["record_id"] == "ap_item:AP-QB-MEMORY"
    assert body["memory"]["context_summary"]["who_owns_it"] == "Controller"
    assert body["memory"]["context_summary"]["next_action"] == "Controller approval"
    assert body["surface_memory"]["owner"] == "Controller"
    assert body["surface_memory"]["why"] == "Amount exceeds the auto-posting threshold."
    assert body["surface_memory"]["next"] == "Controller approval"
    assert body["surface_memory"]["full_memory_url"].endswith("/records/AP-QB-MEMORY")
    assert body["operational_memory"] == body["memory"]
    assert body["decision_ledger"]


def test_xero_erp_reference_action_uses_xero_memory_surface(monkeypatch):
    db = _db()
    _create_item(db, item_id="AP-XERO-MEMORY", erp_reference="XERO-BILL-200", erp_type="xero")
    captured: Dict[str, Any] = {}

    def fake_runtime(**kwargs):
        captured["runtime_kwargs"] = kwargs
        return object()

    async def fake_dispatch(runtime, intent, payload, *, idempotency_key=None):
        captured["intent"] = intent
        captured["payload"] = payload
        captured["idempotency_key"] = idempotency_key
        return {"status": "approved", "ap_item_id": payload["ap_item_id"]}

    monkeypatch.setattr("solden.services.agent_command_dispatch.build_channel_runtime", fake_runtime)
    monkeypatch.setattr("solden.services.agent_command_dispatch.dispatch_runtime_intent", fake_dispatch)

    client = _client(db)
    response = client.post(
        "/extension/ap-items/by-erp-reference/xero/XERO-BILL-200/approve",
        json={"reason": "approved from Xero bill view", "idempotency_key": "xero-approve-1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_channel"] == "erp_native_xero"
    assert body["intent"] == "approve_invoice"
    assert captured["intent"] == "approve_invoice"
    assert captured["payload"]["ap_item_id"] == "AP-XERO-MEMORY"
    assert captured["payload"]["source_channel"] == "erp_native_xero"
    assert captured["payload"]["source_message_ref"] == "XERO-BILL-200"
    assert captured["idempotency_key"] == "xero-approve-1"
