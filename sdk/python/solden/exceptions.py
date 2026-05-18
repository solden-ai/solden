"""Typed exceptions for every error_code the /v1 API returns.

Catch the most-specific one you can; ``SoldenError`` is the base for
'I don't care which one' fallback handlers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class SoldenError(Exception):
    """Base class. Every SDK error inherits from this."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        request_id: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.request_id = request_id
        self.raw = raw or {}


# ─── Auth (401 / 403) ──────────────────────────────────────────


class MissingAPIKey(SoldenError):
    """No ``Authorization`` or ``X-API-Key`` header was sent."""


class InvalidAPIKey(SoldenError):
    """The key didn't match any active row."""


class APIKeyRevoked(SoldenError):
    """The key was revoked."""


class APIKeyExpired(SoldenError):
    """The key is past its ``expires_at``."""


class InvalidScope(SoldenError):
    """The key authenticated but lacks the scope for this endpoint."""


# ─── Client (400 / 404 / 409) ──────────────────────────────────


class InvalidRequest(SoldenError):
    """Input validation failed (missing field, wrong type, bad URL)."""


class NotFound(SoldenError):
    """Resource missing — or wrong tenant (indistinguishable by design)."""


class StateConflict(SoldenError):
    """The Box state machine rejected this transition."""


class IdempotencyConflict(SoldenError):
    """Same ``Idempotency-Key`` used with a different payload. Use a
    fresh key."""


# ─── Throttling (429) ─────────────────────────────────────────


class RateLimitExceeded(SoldenError):
    """The per-key or per-org window tripped.

    Inspect ``retry_after_seconds`` and ``scope`` (``per_key`` or
    ``per_org``) on the exception to decide how long to wait.
    """

    def __init__(
        self,
        message: str,
        *,
        scope: Optional[str] = None,
        limit: Optional[int] = None,
        window_seconds: Optional[int] = None,
        retry_after_seconds: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.scope = scope
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after_seconds = retry_after_seconds


# ─── Server (500) ─────────────────────────────────────────────


class InternalError(SoldenError):
    """Server-side. ``request_id`` is your handle for support."""


# ─── Code → exception mapping ─────────────────────────────────


_ERROR_CODE_MAP: Dict[str, type] = {
    "missing_api_key": MissingAPIKey,
    "invalid_api_key": InvalidAPIKey,
    "api_key_revoked": APIKeyRevoked,
    "api_key_expired": APIKeyExpired,
    "invalid_scope": InvalidScope,
    "invalid_request": InvalidRequest,
    "invalid_url": InvalidRequest,
    "invalid_event_type": InvalidRequest,
    "unsupported_box_type": InvalidRequest,
    "empty_update": InvalidRequest,
    "not_found": NotFound,
    "state_conflict": StateConflict,
    "idempotency_conflict": IdempotencyConflict,
    "rate_limit_exceeded": RateLimitExceeded,
    "internal_error": InternalError,
}


def raise_for_error(
    status_code: int,
    body: Optional[Dict[str, Any]],
) -> None:
    """Translate a non-2xx response into the right SDK exception.

    ``body`` is the parsed JSON from the response (or ``None`` if the
    server returned a non-JSON error — rare, but the catch-all
    ``SoldenError`` covers it).
    """
    body = body or {}
    error_code = body.get("error_code") or "internal_error"
    message = body.get("message") or f"HTTP {status_code}"
    request_id = body.get("request_id")
    exc_cls = _ERROR_CODE_MAP.get(error_code, SoldenError)

    if exc_cls is RateLimitExceeded:
        raise RateLimitExceeded(
            message,
            scope=body.get("scope"),
            limit=body.get("limit"),
            window_seconds=body.get("window_seconds"),
            retry_after_seconds=body.get("retry_after_seconds"),
            status_code=status_code,
            error_code=error_code,
            request_id=request_id,
            raw=body,
        )

    raise exc_cls(
        message,
        status_code=status_code,
        error_code=error_code,
        request_id=request_id,
        raw=body,
    )
