"""Gmail extension operational-memory capture contract tests."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from solden.api import gmail_extension as gmail_extension_module
from solden.core import database as db_module
from solden.core.auth import TokenData
from solden.services.memory_invariants import memory_event_invariant_violations


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    return inst


@pytest.fixture()
def org_id() -> str:
    return f"org-gmail-memory-{uuid.uuid4().hex[:10]}"


def _as_gmail_operator(org_id: str) -> TokenData:
    return TokenData(
        user_id="u-gmail-memory",
        email="gmail-operator@acme.com",
        organization_id=org_id,
        role="operator",
        workspace_role="member",
        exp=datetime.now(timezone.utc) + timedelta(hours=1),
    )


@pytest.fixture()
def client(db, org_id):
    app.dependency_overrides[gmail_extension_module.get_current_user] = (
        lambda: _as_gmail_operator(org_id)
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(gmail_extension_module.get_current_user, None)


def _seed_item(db, *, organization_id: str) -> dict:
    suffix = uuid.uuid4().hex[:10]
    return db.create_ap_item({
        "id": f"AP-GMAIL-MEM-{suffix}",
        "invoice_key": f"inv-gmail-memory-{suffix}",
        "thread_id": f"thr-gmail-memory-{suffix}",
        "message_id": f"msg-gmail-memory-{suffix}",
        "subject": "Invoice waiting on PO evidence",
        "sender": "billing@example-vendor.test",
        "vendor_name": "Example Vendor",
        "amount": 12400.0,
        "currency": "USD",
        "invoice_number": f"INV-GMAIL-MEM-{suffix}",
        "state": "needs_info",
        "confidence": 0.96,
        "organization_id": organization_id,
        "metadata": {},
    })


def test_gmail_extension_memory_capture_endpoint_commits_confirmed_context(
    client,
    db,
    org_id,
):
    item = _seed_item(db, organization_id=org_id)

    resp = client.post(
        "/extension/memory-events/capture",
        json={
            "organization_id": org_id,
            "box_type": "ap_item",
            "box_id": item["id"],
            "source": "gmail_extension",
            "event_type": "thread_context_recorded",
            "summary": "Gmail thread confirms the invoice is waiting on PO evidence.",
            "decision": {"type": "hold_for_missing_po"},
            "rationale": "The thread says the purchase order was not attached.",
            "evidence": {
                "gmail_message_id": item["message_id"],
                "gmail_thread_id": item["thread_id"],
            },
            "confidence": 0.97,
            "human_confirmation_status": "confirmed",
            "next_action": "Attach the PO evidence before ERP follow-up.",
            "source_refs": {
                "gmail_message_id": item["message_id"],
                "gmail_thread_id": item["thread_id"],
            },
            "auto_commit": True,
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "committed"
    assert body["event"]["event_type"] == "memory_event:thread_context_recorded"
    assert body["link"]["work_item"]["box_id"] == item["id"]

    events = db.list_box_audit_events("ap_item", item["id"])
    captured = next(
        event for event in events
        if event.get("event_type") == "memory_event:thread_context_recorded"
    )
    payload = captured["payload_json"]
    assert memory_event_invariant_violations(payload) == []
    assert payload["memory_event"]["source"]["surface"] == "gmail_extension"
    assert payload["memory_event"]["evidence"]["gmail_message_id"] == item["message_id"]
    assert payload["decision_context"]["actor_id"] == "gmail-operator@acme.com"
