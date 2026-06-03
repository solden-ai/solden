"""Workspace exception queue API pagination tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from solden.api import workspace_records as workspace_module
from solden.core import database as db_module
from solden.core.auth import TokenData


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    return inst


def _as_workspace_owner() -> TokenData:
    return TokenData(
        user_id="u-workspace-owner",
        email="owner@acme.com",
        organization_id="org-test",
        role="owner",
        workspace_role="owner",
        exp=datetime.now(timezone.utc) + timedelta(hours=1),
    )


@pytest.fixture()
def client(db):
    app.dependency_overrides[workspace_module.get_current_user] = _as_workspace_owner
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(workspace_module.get_current_user, None)


def _seed_ap_box(db, box_id: str, vendor_name: str = "Acme") -> None:
    db.create_ap_item({
        "id": box_id,
        "invoice_key": f"inv-{box_id}",
        "thread_id": f"thr-{box_id}",
        "message_id": f"msg-{box_id}",
        "subject": f"Invoice {box_id}",
        "sender": "billing@vendor.com",
        "vendor_name": vendor_name,
        "amount": 500.0,
        "currency": "USD",
        "invoice_number": f"INV-{box_id}",
        "state": "needs_approval",
        "organization_id": "org-test",
    })


def _seed_exception(
    db,
    box_id: str,
    *,
    exception_type: str = "approval_wait",
    severity: str = "medium",
    organization_id: str = "org-test",
) -> dict:
    return db.raise_box_exception(
        box_id=box_id,
        box_type="ap_item",
        organization_id=organization_id,
        exception_type=exception_type,
        severity=severity,
        reason=f"{exception_type} seeded for pagination",
        raised_by="test",
        raised_actor_type="system",
    )


def test_workspace_exceptions_paginates_after_filters(client, db):
    for index in range(5):
        box_id = f"AP-PAGE-{index}"
        _seed_ap_box(db, box_id, vendor_name=f"Vendor {index}")
        _seed_exception(db, box_id, exception_type="approval_wait")
    _seed_ap_box(db, "AP-OTHER-TYPE", vendor_name="Other Type")
    _seed_exception(db, "AP-OTHER-TYPE", exception_type="amount_anomaly")

    # Different tenant rows must not count toward this workspace page.
    db.raise_box_exception(
        box_id="AP-OTHER-TENANT",
        box_type="ap_item",
        organization_id="other-org",
        exception_type="approval_wait",
        severity="critical",
        reason="tenant isolation",
        raised_by="test",
        raised_actor_type="system",
    )

    first = client.get(
        "/api/workspace/exceptions?exception_type=approval_wait&limit=2&offset=0"
    )
    second = client.get(
        "/api/workspace/exceptions?exception_type=approval_wait&limit=2&offset=2"
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
    assert all(row["exception_type"] == "approval_wait" for row in second_body["items"])
    assert {
        row["id"] for row in first_body["items"]
    }.isdisjoint({row["id"] for row in second_body["items"]})


def test_workspace_exceptions_searches_box_summary_before_paging(client, db):
    _seed_ap_box(db, "AP-NEEDLE", vendor_name="Needle Systems")
    _seed_exception(db, "AP-NEEDLE", exception_type="amount_anomaly")
    _seed_ap_box(db, "AP-HAYSTACK", vendor_name="Haystack LLC")
    _seed_exception(db, "AP-HAYSTACK", exception_type="amount_anomaly")

    resp = client.get("/api/workspace/exceptions?q=Needle&limit=50&offset=0")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["count"] == 1
    assert body["items"][0]["box_id"] == "AP-NEEDLE"
    assert body["items"][0]["box_summary"]["vendor_name"] == "Needle Systems"
