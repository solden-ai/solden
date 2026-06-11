"""Ask Solden API — auth, contract shape, quota, validation, suggestions."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from solden.core import database as db_module
from solden.core.auth import get_current_user
from solden.api import ask_solden as ask_routes


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization("orgApiA", organization_name="orgApiA")
    return inst


def _user(org="orgApiA", workspace_role="member"):
    return SimpleNamespace(
        user_id="op-9", email="op9@example.com", organization_id=org,
        role="user", workspace_role=workspace_role,
    )


def _client(org="orgApiA", workspace_role="member"):
    app = FastAPI()
    app.include_router(ask_routes.router)
    app.dependency_overrides[get_current_user] = lambda: _user(org, workspace_role)
    return TestClient(app)


def _unauth_client():
    app = FastAPI()
    app.include_router(ask_routes.router)
    return TestClient(app)


def test_ask_requires_auth():
    assert _unauth_client().post(
        "/api/workspace/ask", json={"question": "what's open?"}
    ).status_code in (401, 403)


def test_ask_contract_shape(db):
    db.create_ap_item({
        "id": "AP-api-1", "organization_id": "orgApiA", "vendor_name": "Acme",
        "amount": 10.0, "currency": "EUR", "invoice_number": "INV-api-1",
        "state": "approved",
    })
    with patch("solden.services.ask_solden.get_llm_gateway", side_effect=RuntimeError("x")):
        resp = _client().post(
            "/api/workspace/ask",
            json={"question": "Why did we approve INV-api-1?",
                  "history": [{"q": "hi", "a": "hello"}]},
        )
    assert resp.status_code == 200
    body = resp.json()
    for key in ("answer", "sources", "retrieval", "model", "latency_ms", "fallback"):
        assert key in body, key
    assert body["organization_id"] == "orgApiA"
    assert all({"id", "type", "summary", "link"} <= set(s) for s in body["sources"])


def test_ask_validation():
    client = _client()
    assert client.post("/api/workspace/ask", json={"question": ""}).status_code == 422
    assert client.post(
        "/api/workspace/ask", json={"question": "x" * 1001}
    ).status_code == 422
    # Oversized history ITEM is rejected at the model layer (2k cap).
    assert client.post(
        "/api/workspace/ask",
        json={"question": "ok then", "history": [{"q": "a", "a": "x" * 2001}]},
    ).status_code == 422


def test_ask_quota_429(db, monkeypatch):
    from solden.services import rate_limit as rl
    monkeypatch.setattr(rl, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(ask_routes, "_ASK_SOLDEN_DAILY_LIMIT", 1)
    # Fresh in-memory window for this identity regardless of prior tests.
    rl._quota_memory_store.pop("quota:ask_solden:op-9:orgApiA", None)
    client = _client()
    with patch("solden.services.ask_solden.get_llm_gateway", side_effect=RuntimeError("x")):
        first = client.post("/api/workspace/ask", json={"question": "what's blocked?"})
        second = client.post("/api/workspace/ask", json={"question": "what's blocked?"})
    assert first.status_code == 200
    assert second.status_code == 429
    assert "Retry-After" in second.headers
    detail = second.json()["detail"]
    assert detail["scope"] == "ask_solden"
    assert detail["reset_after_seconds"] > 0


def test_suggestions_not_quota_gated(db, monkeypatch):
    """Suggestions are deterministic reads — they must never burn or hit
    the Q&A quota."""
    monkeypatch.setattr(ask_routes, "_ASK_SOLDEN_DAILY_LIMIT", 0)
    client = _client()
    for _ in range(3):
        resp = client.get("/api/workspace/ask/suggestions")
        assert resp.status_code == 200
    body = resp.json()
    assert body["suggestions"]
    assert len(body["suggestions"]) <= 4
    assert "What's our policy on first-time vendors?" in body["suggestions"]
