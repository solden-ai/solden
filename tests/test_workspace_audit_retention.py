"""Tests for workspace audit-retention administration evidence."""
from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from solden.api import workspace_shell as ws  # noqa: E402
from solden.core import database as db_module  # noqa: E402
from solden.core.auth import get_current_user  # noqa: E402
from solden.services.subscription import PlanFeatures, PlanLimits, PlanTier  # noqa: E402


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization("org-test", organization_name="org-test")
    inst.update_organization("org-test", settings_json={})
    inst.upsert_subscription_record(
        "org-test",
        {
            "plan": PlanTier.PROFESSIONAL.value,
            "status": "active",
            "limits": asdict(PlanLimits.for_tier(PlanTier.PROFESSIONAL)),
            "features": asdict(PlanFeatures.for_tier(PlanTier.PROFESSIONAL)),
        },
    )
    return inst


def _admin_user():
    return SimpleNamespace(
        email="admin@example.com",
        user_id="admin-user",
        organization_id="org-test",
        role="owner",
    )


@pytest.fixture()
def client_factory(db):
    def _build(user_factory):
        app = FastAPI()
        app.include_router(ws.router)
        app.dependency_overrides[get_current_user] = user_factory
        return TestClient(app)
    return _build


def _latest_event(db, *, event_type: str):
    result = db.search_audit_events(
        organization_id="org-test",
        event_types=[event_type],
        box_type="workspace_audit",
        box_id="audit-log",
        limit=5,
    )
    events = result.get("events") or []
    return events[0] if events else None


def test_retention_patch_records_audit_event(db, client_factory):
    client = client_factory(_admin_user)

    resp = client.patch(
        "/api/workspace/audit/retention",
        json={"organization_id": "org-test", "days": 90},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["configured_days"] == 90
    assert body["effective_days"] == 90

    event = _latest_event(db, event_type="audit_retention_updated")
    assert event is not None
    assert event["actor_id"] == "admin@example.com"
    assert event["source"] == "workspace_audit"
    payload = event["payload_json"]
    assert payload["previous_configured_days"] is None
    assert payload["previous_effective_days"] == PlanLimits.for_tier(PlanTier.PROFESSIONAL).agent_activity_retention_days
    assert payload["configured_days"] == 90
    assert payload["effective_days"] == 90
    assert payload["tier_ceiling_days"] == PlanLimits.for_tier(PlanTier.PROFESSIONAL).agent_activity_retention_days
