"""Governance endpoints reject non-admins.

The require_workspace_admin Depends gate is exercised by the dual_approval /
escalation / sample_data / workspace_rules member-403 tests. This covers the
one inline gate added in the same cluster: vendor_status verify-registration.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from solden.api import vendor_status  # noqa: E402
from solden.core.auth import get_current_user  # noqa: E402


def _member(org: str = "orgA") -> SimpleNamespace:
    return SimpleNamespace(
        user_id=f"member@{org}", email=f"member@{org}",
        organization_id=org, role="member", workspace_role="member",
    )


def test_verify_registration_requires_admin():
    # _require_admin fires before any DB/registry call, so no fixture needed.
    app = FastAPI()
    app.include_router(vendor_status.router)
    app.dependency_overrides[get_current_user] = lambda: _member()
    client = TestClient(app)
    resp = client.post("/api/vendors/Acme/verify-registration")
    assert resp.status_code == 403
