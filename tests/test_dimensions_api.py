"""Dimension rollup read API (H5) — list dimensions + "everything on CC 402".

Covers the list endpoint (+ type filter), the per-dimension records rollup, and
tenant isolation (a dimension in another org returns 404, no existence leak).
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from solden.core import database as db_module
from solden.core.auth import get_current_user
from solden.api import dimensions as dim_routes


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization("orgA", organization_name="orgA")
    inst.ensure_organization("orgB", organization_name="orgB")
    return inst


def _user(org: str = "orgA") -> SimpleNamespace:
    return SimpleNamespace(user_id="u-1", email="u@example.com", organization_id=org, role="user")


def _client(org: str) -> TestClient:
    app = FastAPI()
    app.include_router(dim_routes.router)
    app.dependency_overrides[get_current_user] = lambda: _user(org)
    return TestClient(app)


@pytest.fixture()
def client_orgA(db):
    return _client("orgA")


@pytest.fixture()
def client_orgB(db):
    return _client("orgB")


def test_list_dimensions_and_type_filter(db, client_orgA):
    db.upsert_dimension(organization_id="orgA", dimension_type="gl_account", code="5210", label="SaaS", source="erp_coa")
    db.upsert_dimension(organization_id="orgA", dimension_type="cost_center", code="402", source="payment_request")
    alld = client_orgA.get("/api/workspace/dimensions").json()
    assert alld["count"] == 2
    gl = client_orgA.get("/api/workspace/dimensions?type=gl_account").json()
    assert gl["count"] == 1
    assert gl["dimensions"][0]["code"] == "5210"


def test_rollup_records_for_dimension(db, client_orgA):
    d = db.upsert_dimension(organization_id="orgA", dimension_type="cost_center", code="402", source="payment_request")
    db.link_dimension(organization_id="orgA", box_type="ap_item", box_id="AP-1", dimension_id=d["id"], status="confirmed")
    db.link_dimension(organization_id="orgA", box_type="ap_item", box_id="AP-2", dimension_id=d["id"], status="confirmed")
    resp = client_orgA.get(f"/api/workspace/dimensions/{d['id']}/records")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dimension"]["code"] == "402"
    assert body["count"] == 2
    assert {r["box_id"] for r in body["records"]} == {"AP-1", "AP-2"}


def test_rollup_cross_tenant_returns_404(db, client_orgA, client_orgB):
    d = db.upsert_dimension(organization_id="orgA", dimension_type="gl_account", code="7000", source="erp_coa")
    # orgB cannot read orgA's dimension records — 404, never a leak.
    assert client_orgB.get(f"/api/workspace/dimensions/{d['id']}/records").status_code == 404
    # orgB's dimension list is its own (empty), not orgA's.
    assert client_orgB.get("/api/workspace/dimensions").json()["count"] == 0


def test_rollup_missing_dimension_returns_404(client_orgA):
    assert client_orgA.get("/api/workspace/dimensions/DIM-nope/records").status_code == 404
