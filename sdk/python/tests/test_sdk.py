"""SDK coverage. Uses httpx's MockTransport so tests run without
network and without spinning up the Solden backend."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import httpx
import pytest

# Make the SDK importable when running pytest from the repo root.
_SDK_ROOT = Path(__file__).resolve().parents[1]
if str(_SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(_SDK_ROOT))

from solden import (  # noqa: E402  (sys.path insert above)
    APIKeyExpired,
    IdempotencyConflict,
    InvalidScope,
    NotFound,
    RateLimitExceeded,
    Solden,
    StateConflict,
    verify_signature,
)


# ─── Helpers ───────────────────────────────────────────────────


def _client(handler):
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return Solden(
        api_key="sk_test",
        base_url="https://api.example.com",
        max_retries=0,
        http_client=http_client,
    )


def _resp(status: int, body: Dict[str, Any]):
    return httpx.Response(status, json=body)


# ─── Happy paths ───────────────────────────────────────────────


def test_me_get_returns_identity() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        return _resp(200, {"key_id": "k1", "organization_id": "org_x"})

    client = _client(handler)
    assert client.me.get() == {"key_id": "k1", "organization_id": "org_x"}
    assert captured["url"].endswith("/v1/me")
    assert captured["auth"] == "Bearer sk_test"


def test_records_list_passes_query_params() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = dict(request.url.params)
        return _resp(200, {"records": [], "next_cursor": None})

    client = _client(handler)
    client.records.list(
        box_type="ap_item", state="needs_approval", limit=25,
    )
    assert captured["query"]["box_type"] == "ap_item"
    assert captured["query"]["state"] == "needs_approval"
    assert captured["query"]["limit"] == "25"


def test_intents_execute_auto_generates_idempotency_key() -> None:
    """When the caller doesn't supply a key, the SDK generates a
    fresh UUID4 so a network-blip retry doesn't double-execute."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["idem"] = request.headers.get("Idempotency-Key")
        captured["body"] = json.loads(request.content)
        return _resp(200, {"ok": True, "result": {}})

    client = _client(handler)
    client.intents.execute("approve_invoice", {"ap_item_id": "ap1"})
    assert captured["idem"], "SDK must auto-generate an idempotency key"
    assert captured["body"] == {
        "intent": "approve_invoice", "input": {"ap_item_id": "ap1"},
    }


def test_intents_execute_respects_explicit_idempotency_key() -> None:
    """An explicit key lets the call site own the retry boundary."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["idem"] = request.headers.get("Idempotency-Key")
        return _resp(200, {"ok": True})

    client = _client(handler)
    client.intents.execute(
        "approve_invoice", {"ap_item_id": "ap1"},
        idempotency_key="my-stable-key",
    )
    assert captured["idem"] == "my-stable-key"


def test_iter_records_walks_cursor_pages() -> None:
    pages = [
        {"records": [{"id": "a"}, {"id": "b"}], "next_cursor": "c1"},
        {"records": [{"id": "c"}], "next_cursor": None},
    ]
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        page = pages[call_count["n"]]
        call_count["n"] += 1
        return _resp(200, page)

    client = _client(handler)
    ids = [r["id"] for r in client.iter_records(box_type="ap_item")]
    assert ids == ["a", "b", "c"]
    assert call_count["n"] == 2


# ─── Error translation ────────────────────────────────────────


def test_404_raises_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(
            404,
            {"error_code": "not_found", "message": "ap_item:x not found",
             "request_id": "req_1"},
        )

    client = _client(handler)
    with pytest.raises(NotFound) as info:
        client.records.get("x", box_type="ap_item")
    assert info.value.status_code == 404
    assert info.value.request_id == "req_1"


def test_403_invalid_scope_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(403, {"error_code": "invalid_scope",
                           "message": "missing_scope:intents:execute"})

    client = _client(handler)
    with pytest.raises(InvalidScope):
        client.intents.execute("approve_invoice", {})


def test_403_api_key_expired_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(403, {"error_code": "api_key_expired",
                           "message": "key past expires_at"})

    client = _client(handler)
    with pytest.raises(APIKeyExpired):
        client.me.get()


def test_409_state_conflict_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(409, {"error_code": "state_conflict",
                           "message": "ap_item:x is closed"})

    client = _client(handler)
    with pytest.raises(StateConflict):
        client.intents.execute("approve_invoice", {"ap_item_id": "x"})


def test_409_idempotency_conflict_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(409, {"error_code": "idempotency_conflict",
                           "message": "key reused with different payload"})

    client = _client(handler)
    with pytest.raises(IdempotencyConflict):
        client.intents.execute("approve_invoice", {})


def test_429_carries_scope_limit_window_retry_after() -> None:
    """RateLimitExceeded must surface every field of the typed
    envelope so callers can write smart backoff."""
    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(
            429,
            {
                "error_code": "rate_limit_exceeded",
                "message": "per_key trip",
                "scope": "per_key",
                "limit": 100,
                "window_seconds": 60,
                "retry_after_seconds": 17,
            },
        )

    client = _client(handler)
    with pytest.raises(RateLimitExceeded) as info:
        client.me.get()
    assert info.value.scope == "per_key"
    assert info.value.limit == 100
    assert info.value.window_seconds == 60
    assert info.value.retry_after_seconds == 17


def test_429_retried_when_max_retries_allow() -> None:
    """Default retry: 429 once, then 200. The second call should
    return cleanly without raising."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "1"},
                json={"error_code": "rate_limit_exceeded",
                      "message": "trip", "retry_after_seconds": 1},
            )
        return _resp(200, {"ok": True})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = Solden(
        api_key="sk", base_url="https://api.example.com",
        max_retries=2, http_client=http_client,
    )
    # The internal retry sleeps for Retry-After; patch time.sleep
    # to keep the test fast.
    import solden.client as client_mod

    original_sleep = client_mod.time.sleep
    client_mod.time.sleep = lambda _s: None
    try:
        assert client.me.get() == {"ok": True}
    finally:
        client_mod.time.sleep = original_sleep
    assert attempts["n"] == 2


# ─── Misc ─────────────────────────────────────────────────────


def test_close_idempotent() -> None:
    client = _client(lambda r: _resp(200, {}))
    client.close()
    # Calling again must not raise (idempotency on close is a
    # mainstream Python convention).
    client.close()


def test_env_var_picks_up_key(monkeypatch) -> None:
    monkeypatch.setenv("SOLDEN_API_KEY", "sk_from_env")
    transport = httpx.MockTransport(
        lambda r: _resp(
            200, {"got": r.headers.get("Authorization")},
        )
    )
    http_client = httpx.Client(transport=transport)
    client = Solden(http_client=http_client)
    assert client.me.get() == {"got": "Bearer sk_from_env"}


def test_missing_key_raises_at_construction() -> None:
    with pytest.raises(ValueError) as info:
        Solden()
    assert "api_key" in str(info.value).lower()


# ─── Webhook signature verification ───────────────────────────


def test_verify_signature_accepts_valid_signature() -> None:
    import hashlib
    import hmac

    body = b'{"event":"invoice.approved"}'
    secret = "whsec_test"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(body, f"sha256={sig}", secret=secret)


def test_verify_signature_rejects_wrong_signature() -> None:
    assert not verify_signature(
        b'{"a":1}', "sha256=" + ("0" * 64), secret="whsec_test",
    )


def test_verify_signature_rejects_missing_prefix() -> None:
    assert not verify_signature(b"{}", "abcd1234", secret="whsec_test")


def test_verify_signature_rejects_empty_header() -> None:
    assert not verify_signature(b"{}", "", secret="whsec_test")


def test_verify_signature_rejects_empty_secret() -> None:
    assert not verify_signature(b"{}", "sha256=abc", secret="")


def test_verify_signature_accepts_string_body() -> None:
    """Callers often pass already-decoded text; accept it and
    encode UTF-8 internally."""
    import hashlib
    import hmac

    body = '{"a":1}'
    secret = "whsec_test"
    sig = hmac.new(
        secret.encode(), body.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert verify_signature(body, f"sha256={sig}", secret=secret)


# ─── Webhooks resource ────────────────────────────────────────


def test_webhooks_create_passes_body() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _resp(
            201,
            {"id": "wh_1", "url": "https://example.com",
             "secret": "whsec_xyz", "is_active": True},
        )

    client = _client(handler)
    out = client.webhooks.create(
        url="https://example.com",
        event_types=["invoice.approved"],
        description="Approval relay",
    )
    assert captured["body"] == {
        "url": "https://example.com",
        "event_types": ["invoice.approved"],
        "description": "Approval relay",
    }
    assert out["secret"] == "whsec_xyz"


def test_webhooks_delete_handles_204() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = _client(handler)
    # Must not raise on 204 (no JSON body).
    assert client.webhooks.delete("wh_1") is None
