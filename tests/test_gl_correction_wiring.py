"""GL correction wiring — DB-backed persistence, history suggestion, stats.

GLCorrectionService used to be unwired and in-memory only (history/stats
were per-process and almost always empty). These tests pin the wired
behaviour:

  - corrections persist to the gl_corrections table and read back from a
    *fresh* service instance (no in-process cache);
  - the corrections-history source + conflict flag surface through the live
    gl-code suggestion payload;
  - the workspace analytics endpoint is org-scoped.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from solden.api import workspace_shell  # noqa: E402
from solden.core import database as db_module  # noqa: E402
from solden.core.auth import get_current_user  # noqa: E402
from solden.services.gl_correction import GLCorrectionService, get_gl_correction  # noqa: E402
from solden.services.gmail_extension_support import build_gl_suggestion_payload  # noqa: E402


# ─── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization("orgA", organization_name="Acme UK Ltd")
    inst.ensure_organization("orgB", organization_name="Beta Co")
    return inst


def _user(org: str = "orgA") -> SimpleNamespace:
    return SimpleNamespace(
        user_id=f"leader@{org}.com",
        email=f"leader@{org}.com",
        organization_id=org,
        role="user",
    )


def _persist(org: str, vendor: str, original_gl: str, corrected_gl: str, n: int = 1):
    svc = get_gl_correction(org)
    for i in range(n):
        svc.persist_correction(
            invoice_id=f"inv-{vendor}-{original_gl}-{corrected_gl}-{i}",
            vendor=vendor,
            original_gl=original_gl,
            corrected_gl=corrected_gl,
            corrected_by="operator",
            reason="test",
        )


# ─── Service: DB-backed, no in-process cache ────────────────────────


def test_persist_correction_is_db_backed_across_instances(db):
    _persist("orgA", "Acme", "5000", "5200", n=2)

    # A brand-new service instance (no shared in-memory state) sees the rows.
    fresh = GLCorrectionService("orgA")
    recent = fresh.get_recent_corrections(limit=10)
    assert len(recent) == 2
    assert {r["corrected_gl"] for r in recent} == {"5200"}
    assert {r["original_gl"] for r in recent} == {"5000"}


def test_get_correction_stats_db_backed(db):
    _persist("orgA", "Acme", "5000", "5200", n=3)
    _persist("orgA", "Globex", "5000", "5300", n=1)

    stats = GLCorrectionService("orgA").get_correction_stats()
    assert stats["total_corrections"] == 4
    assert stats["unique_vendors"] == 2
    vendors = {row["vendor"] for row in stats["by_vendor"]}
    assert vendors == {"Acme", "Globex"}


def test_recent_corrections_filtered_by_vendor(db):
    _persist("orgA", "Acme", "5000", "5200", n=2)
    _persist("orgA", "Globex", "5000", "5300", n=1)

    acme = GLCorrectionService("orgA").get_recent_corrections(vendor="acme", limit=10)
    assert len(acme) == 2
    assert all(r["vendor"] == "Acme" for r in acme)


# ─── History suggestion ─────────────────────────────────────────────


def test_history_suggestion_from_corrections(db):
    _persist("orgA", "Acme", "5000", "5200", n=3)

    hint = GLCorrectionService("orgA").get_history_suggestion("Acme")
    assert hint is not None
    assert hint["gl_code"] == "5200"
    assert hint["source"] == "corrections_history"
    assert hint["confidence"] > 0.5


def test_history_suggestion_none_without_signal(db):
    assert GLCorrectionService("orgA").get_history_suggestion("NoSuchVendor") is None


# ─── Suggestion payload: history source + conflict flag ─────────────


def test_suggestion_payload_includes_history(db):
    _persist("orgA", "Acme", "5000", "5200", n=3)

    class _Learning:
        def suggest_gl_code(self, *a, **k):
            return None

    class _VendorIntel:
        def get_suggestion(self, *a, **k):
            return None

    with patch(
        "solden.services.finance_learning.get_finance_learning_service",
        return_value=_Learning(),
    ), patch(
        "solden.services.vendor_intelligence.get_vendor_intelligence",
        return_value=_VendorIntel(),
    ):
        payload = build_gl_suggestion_payload(organization_id="orgA", vendor_name="Acme")

    assert payload["has_suggestion"] is True
    assert payload["primary"]["gl_code"] == "5200"
    assert payload["primary"]["source"] == "corrections_history"
    # Single source agreeing with itself => no conflict.
    assert payload["gl_conflict"] is False


def test_suggestion_payload_flags_conflict(db):
    _persist("orgA", "Globex", "5000", "5200", n=3)

    class _Learning:
        def suggest_gl_code(self, *a, **k):
            return None

    class _VendorIntel:
        def get_suggestion(self, *a, **k):
            return {"suggested_gl": "9999", "gl_description": "Other", "known_vendor": True}

    with patch(
        "solden.services.finance_learning.get_finance_learning_service",
        return_value=_Learning(),
    ), patch(
        "solden.services.vendor_intelligence.get_vendor_intelligence",
        return_value=_VendorIntel(),
    ):
        payload = build_gl_suggestion_payload(organization_id="orgA", vendor_name="Globex")

    codes = {payload["primary"]["gl_code"], *(a["gl_code"] for a in payload["alternatives"])}
    assert {"5200", "9999"} <= codes
    assert payload["gl_conflict"] is True


# ─── Workspace analytics endpoint (org-scoped) ──────────────────────


def _client(org: str) -> TestClient:
    app = FastAPI()
    app.include_router(workspace_shell.router)
    app.dependency_overrides[get_current_user] = lambda: _user(org)
    return TestClient(app)


def test_stats_endpoint_org_scoped(db):
    _persist("orgA", "Acme", "5000", "5200", n=2)

    resp_a = _client("orgA").get("/api/workspace/gl-corrections/stats")
    assert resp_a.status_code == 200
    assert resp_a.json()["total_corrections"] == 2

    # orgB has no corrections — must not see orgA's history.
    resp_b = _client("orgB").get("/api/workspace/gl-corrections/stats")
    assert resp_b.status_code == 200
    assert resp_b.json()["total_corrections"] == 0
