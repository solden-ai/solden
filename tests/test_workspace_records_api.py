"""Workspace AP record directory API pagination tests."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from solden.api import workspace_records as workspace_module
from solden.core import database as db_module
from solden.core.auth import TokenData
from solden.services.memory_events import commit_memory_event


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    return inst


@pytest.fixture()
def org_id() -> str:
    return f"org-workspace-records-{uuid.uuid4().hex[:10]}"


def _as_workspace_owner(org_id: str) -> TokenData:
    return TokenData(
        user_id="u-records-owner",
        email="records-owner@acme.com",
        organization_id=org_id,
        role="owner",
        workspace_role="owner",
        exp=datetime.now(timezone.utc) + timedelta(hours=1),
    )


@pytest.fixture()
def client(db, org_id):
    app.dependency_overrides[workspace_module.get_current_user] = lambda: _as_workspace_owner(org_id)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(workspace_module.get_current_user, None)


def _seed_item(
    db,
    *,
    organization_id: str,
    vendor_name: str,
    state: str = "needs_approval",
    amount: float = 500.0,
    confidence: float = 0.99,
    metadata: dict | None = None,
) -> dict:
    suffix = uuid.uuid4().hex[:10]
    return db.create_ap_item({
        "id": f"AP-REC-{suffix}",
        "invoice_key": f"inv-rec-{suffix}",
        "thread_id": f"thr-rec-{suffix}",
        "message_id": f"msg-rec-{suffix}",
        "subject": f"Invoice from {vendor_name}",
        "sender": "billing@vendor.example",
        "vendor_name": vendor_name,
        "amount": amount,
        "currency": "USD",
        "invoice_number": f"INV-{suffix}",
        "state": state,
        "confidence": confidence,
        "organization_id": organization_id,
        "metadata": metadata or {},
    })


def test_workspace_records_paginates_after_scope_filter(client, db, org_id):
    vendors = []
    for index in range(5):
        vendor = f"Records Vendor {index}"
        vendors.append(vendor)
        _seed_item(db, organization_id=org_id, vendor_name=vendor, amount=100 + index)
    _seed_item(db, organization_id=org_id, vendor_name="Closed Vendor", state="closed")
    _seed_item(db, vendor_name="Other Tenant Vendor", organization_id="other-records-org")

    first = client.get(
        "/api/workspace/records?active_slice_id=all_open&sort_col=vendor&sort_dir=asc&limit=2&offset=0"
    )
    second = client.get(
        "/api/workspace/records?active_slice_id=all_open&sort_col=vendor&sort_dir=asc&limit=2&offset=2"
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["total"] == 5
    assert first_body["count"] == 2
    assert first_body["limit"] == 2
    assert first_body["offset"] == 0
    assert first_body["has_more"] is True
    assert second_body["total"] == 5
    assert second_body["count"] == 2
    assert second_body["offset"] == 2
    assert second_body["items"][0]["vendor_name"] == vendors[2]
    assert "slice_counts" in first_body
    assert first_body["slice_counts"]["all_open"] == 5


def test_workspace_records_searches_before_paging(client, db, org_id):
    needle = _seed_item(db, organization_id=org_id, vendor_name="Needle Systems", amount=2200)
    _seed_item(db, organization_id=org_id, vendor_name="Haystack Logistics", amount=2200)

    resp = client.get("/api/workspace/records?q=Needle&limit=50&offset=0")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["count"] == 1
    assert body["items"][0]["id"] == needle["id"]


def test_workspace_records_blocker_filter_handles_metadata_json(client, db, org_id):
    _seed_item(
        db,
        organization_id=org_id,
        vendor_name="Manual Review Vendor",
        confidence=0.99,
        metadata={"requires_field_review": True, "source_conflicts": {"shape": "object"}},
    )
    _seed_item(
        db,
        organization_id=org_id,
        vendor_name="Clean Vendor",
        confidence=0.99,
        metadata={"source_conflicts": {"shape": "object"}},
    )

    resp = client.get("/api/workspace/records?blocker=confidence&limit=50&offset=0")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["vendor_name"] == "Manual Review Vendor"


def test_workspace_records_can_include_operational_memory(client, db, org_id):
    item = _seed_item(
        db,
        organization_id=org_id,
        vendor_name="Memory Systems",
        state="needs_info",
        amount=1200,
    )
    commit_memory_event(
        db,
        box_type="ap_item",
        box_id=item["id"],
        organization_id=org_id,
        event_type="request_info",
        source="gmail",
        actor_type="user",
        actor_id="controller@acme.com",
        owner={"label": "Controller", "email": "controller@acme.com"},
        dependency={
            "type": "information_request",
            "owner": "External source",
            "reason": "Missing PO is required before approval can continue",
        },
        decision={"type": "request_info"},
        rationale="Missing PO is required before approval can continue",
        evidence={"gmail_message_id": "msg-memory-1"},
        next_action="Wait for external response",
        summary="Controller requested missing PO context.",
        source_refs={"gmail_message_id": "msg-memory-1"},
        idempotency_key=f"memory-event:{item['id']}:request-info",
    )

    resp = client.get("/api/workspace/records?include_memory=true&limit=1&offset=0")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["id"] == item["id"]
    memory = body["items"][0]["memory"]
    assert memory["record_id"] == f"ap_item:{item['id']}"
    assert memory["context_summary"]["what_is_happening"] == (
        "Controller requested missing PO context."
    )
    assert memory["context_summary"]["why_it_is_happening"] == "Missing PO is required before approval can continue"
    assert memory["context_summary"]["next_action"] == "Wait for external response"
    assert body["items"][0]["surface_memory"]["contract"] == "solden_memory_surface.v1"
    assert body["items"][0]["surface_memory"]["owner"] == "External source"
    assert body["items"][0]["surface_memory"]["decision"] == (
        "Controller requested missing PO context."
    )
    assert "gmail message id: msg-memory-1" in body["items"][0]["surface_memory"]["evidence"]
    assert body["items"][0]["decision_ledger"][0]["source_surface"] == "gmail"
