from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from solden.core import database as db_module
from solden.core.auth import TokenData, get_current_user


REPORTED_HOME_ENDPOINTS = (
    "/api/workspace/api-keys",
    "/erp/gl-map?organization_id=org_legacy_default",
    "/api/workspace/team/invites?organization_id=org_legacy_default",
    "/api/ap/items/metrics/aggregation?organization_id=org_legacy_default&vendor_limit=5",
    "/api/workspace/exceptions?limit=10",
    "/api/workspace/exceptions/stats",
    "/api/workspace/dashboard/recent-activity?limit=20",
)


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization(
        "org_legacy_default",
        organization_name="Legacy Default Org",
    )
    inst.create_user(
        email="owner@example.com",
        name="Owner",
        organization_id="org_legacy_default",
        role="owner",
        workspace_role="owner",
        ap_role="controller",
    )
    return inst


@pytest.fixture()
def client(db):
    user = TokenData(
        user_id="owner@example.com",
        email="owner@example.com",
        organization_id="org_legacy_default",
        role="owner",
        workspace_role="owner",
        exp=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize("path", REPORTED_HOME_ENDPOINTS)
def test_reported_workspace_home_endpoints_do_not_500(client, path):
    response = client.get(path)
    assert response.status_code < 500, response.text
