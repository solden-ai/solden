"""Human API routes for the purchase_order workflow (create + full lifecycle)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from main import app  # noqa: E402
from solden.core import database as db_module  # noqa: E402
from solden.core.auth import TokenData, get_current_user  # noqa: E402

ORG = "orgPORoutes"


@pytest.fixture(autouse=True)
def _enable_procurement_surface(monkeypatch):
    monkeypatch.setenv("FEATURE_PROCUREMENT_SURFACE", "true")


def _user():
    return TokenData(
        user_id="buyer_1", email="buyer@acme.test", organization_id=ORG,
        role="member", exp=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture()
def client():
    db = db_module.get_db()
    db.initialize()
    db.ensure_organization(ORG, organization_name=ORG)
    app.dependency_overrides[get_current_user] = _user
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


def _create(client, **kw):
    body = {"vendor_name": "Acme", "total_amount": 200.0}
    body.update(kw)
    r = client.post("/api/workspace/purchase-orders", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_procurement_surface_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FEATURE_PROCUREMENT_SURFACE", raising=False)
    from solden.api import purchase_order_routes
    app_local = FastAPI()
    app_local.include_router(purchase_order_routes.router)
    app_local.dependency_overrides[get_current_user] = _user
    client = TestClient(app_local)
    r = client.get("/api/workspace/purchase-orders")
    assert r.status_code == 404
    assert r.json()["detail"]["detail"] == "procurement_surface_disabled"


def test_create_list_get(client):
    po = _create(client)
    assert po["state"] == "draft"
    po_id = po["po_id"]
    lst = client.get("/api/workspace/purchase-orders").json()
    assert any(p["po_id"] == po_id for p in lst["purchase_orders"])
    got = client.get(f"/api/workspace/purchase-orders/{po_id}").json()
    assert got["po_id"] == po_id


def test_full_lifecycle_via_routes(client):
    po_id = _create(client)["po_id"]
    assert client.post(f"/api/workspace/purchase-orders/{po_id}/submit", json={}).json()["status"] == "pending_approval"
    assert client.post(f"/api/workspace/purchase-orders/{po_id}/approve", json={}).json()["status"] == "approved"
    # receive (no line items -> fully_received)
    rcv = client.post(f"/api/workspace/purchase-orders/{po_id}/receive", json={})
    assert rcv.status_code == 200 and rcv.json()["state"] == "fully_received"
    assert client.post(f"/api/workspace/purchase-orders/{po_id}/close", json={}).json()["status"] == "closed"


def test_illegal_transition_returns_409(client):
    po_id = _create(client)["po_id"]
    # approve a draft (must submit first) -> illegal
    r = client.post(f"/api/workspace/purchase-orders/{po_id}/approve", json={})
    assert r.status_code == 409


def test_amend_draft_via_route(client):
    po_id = _create(client)["po_id"]
    r = client.post(
        f"/api/workspace/purchase-orders/{po_id}/amend",
        json={"fields": {"vendor_name": "Acme Corp", "total_amount": 999.0}},
    )
    assert r.status_code == 200 and r.json()["status"] == "amended"
    got = client.get(f"/api/workspace/purchase-orders/{po_id}").json()
    assert got["vendor_name"] == "Acme Corp" and got["total_amount"] == 999.0


def test_amend_after_submit_409(client):
    po_id = _create(client)["po_id"]
    client.post(f"/api/workspace/purchase-orders/{po_id}/submit", json={})
    r = client.post(
        f"/api/workspace/purchase-orders/{po_id}/amend",
        json={"fields": {"total_amount": 1.0}},
    )
    assert r.status_code == 409


def test_issue_disabled_without_flag(client):
    po_id = _create(client)["po_id"]
    client.post(f"/api/workspace/purchase-orders/{po_id}/submit", json={})
    client.post(f"/api/workspace/purchase-orders/{po_id}/approve", json={})
    # FEATURE_PROCUREMENT_ERP_WRITE off -> ERP write returns disabled (not issued)
    r = client.post(f"/api/workspace/purchase-orders/{po_id}/issue", json={})
    assert r.status_code == 200
    assert r.json()["status"] != "issued"


def test_cross_tenant_get_404(client):
    # a PO in another org is not visible to this session's org
    db = db_module.get_db()
    db.ensure_organization("other-org-routes", organization_name="other")
    db.create_purchase_order_box({
        "po_id": "PO-other-routes", "organization_id": "other-org-routes",
        "vendor_name": "X", "total_amount": 1.0, "requested_by": "u",
    })
    r = client.get("/api/workspace/purchase-orders/PO-other-routes")
    assert r.status_code == 404


def test_cancel_records_terminal_box_outcome(client):
    """M3: reaching a terminal PO state records exactly one box_outcome row,
    so the Outcome primitive is populated for purchase_order like ap_item."""
    po_id = _create(client)["po_id"]
    r = client.post(f"/api/workspace/purchase-orders/{po_id}/cancel", json={})
    assert r.status_code == 200, r.text
    db = db_module.get_db()
    outcome = db.get_box_outcome(box_type="purchase_order", box_id=po_id)
    assert outcome is not None, "no terminal box_outcome recorded for the cancelled PO"
    assert outcome.get("outcome_type") == "cancelled"
