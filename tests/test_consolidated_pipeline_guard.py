"""GET /consolidated (multi-entity) auth + tenant guard.

Two bugs shipped here together: (1) the financial-controller check passed the
user OBJECT to a role-string predicate, so it was always False (always-403,
endpoint unreachable); (2) behind it, an undefined verify_org_access would
NameError-500. No test ever reached past the FC gate, so neither surfaced.
These tests reach past it.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from solden.api import ap_items_read_routes  # noqa: E402
from solden.core import database as db_module  # noqa: E402
from solden.core.auth import get_current_user  # noqa: E402


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization("orgA", organization_name="Acme")
    inst.ensure_organization("orgB", organization_name="Beta")
    return inst


def _client(org: str, workspace_role: str = "admin") -> TestClient:
    user = SimpleNamespace(
        user_id=f"u@{org}", email=f"u@{org}",
        organization_id=org, role="admin", workspace_role=workspace_role,
    )
    app = FastAPI()
    app.include_router(ap_items_read_routes.router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_financial_controller_reaches_consolidated(db):
    # FC for orgA querying orgA: passes the (now-correct) FC gate AND
    # verify_org_access, runs the query — proves no always-403 and no NameError.
    resp = _client("orgA").get("/consolidated?parent_org_id=orgA")
    assert resp.status_code == 200


def test_consolidated_rejects_cross_org_parent(db):
    # FC for orgA asking for orgB's tree → tenant guard 403.
    resp = _client("orgA").get("/consolidated?parent_org_id=orgB")
    assert resp.status_code == 403


def test_consolidated_requires_financial_controller(db):
    # A plain member must not reach it.
    resp = _client("orgA", workspace_role="member").get("/consolidated?parent_org_id=orgA")
    assert resp.status_code == 403
