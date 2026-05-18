"""Solden sync + async client.

Both clients share the same resource namespaces (``records``, ``intents``,
``webhooks``, ``audit``, ``me``) so swapping sync↔async is a one-line
change. The async client uses :class:`httpx.AsyncClient` underneath; the
sync client uses :class:`httpx.Client`. All retry / idempotency /
rate-limit handling is in :class:`_Transport` so both inherit it.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict, Iterable, Iterator, List, Optional, Union

import httpx

from solden._version import __version__
from solden.exceptions import RateLimitExceeded, raise_for_error

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.soldenai.com"
DEFAULT_TIMEOUT = 30.0


# ─── Sync transport ──────────────────────────────────────────────


class _SyncTransport:
    """Thin wrapper around ``httpx.Client`` with retry + auth.

    Splits out from the public client so :class:`Solden` and
    :class:`AsyncSolden` can share resource classes that don't care
    whether the call is sync or async at construction time.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float,
        max_retries: int,
        http_client: Optional[httpx.Client],
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._owned_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    def __enter__(self) -> "_SyncTransport":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        headers = _default_headers(self._api_key)
        if extra_headers:
            headers.update(extra_headers)

        for attempt in range(self._max_retries + 1):
            response = self._client.request(
                method, url, params=params, json=json,
                headers=headers, timeout=self._timeout,
            )
            if response.status_code == 204:
                return None
            try:
                body = response.json() if response.content else None
            except ValueError:
                body = None
            if response.is_success:
                return body

            if (
                response.status_code == 429
                and attempt < self._max_retries
            ):
                wait = _retry_after(response, body)
                logger.info(
                    "solden-sdk: 429 rate_limit_exceeded, retrying in %ss",
                    wait,
                )
                time.sleep(wait)
                continue

            raise_for_error(response.status_code, body)
            # raise_for_error always raises; this is unreachable.
            return None

        # All retries exhausted on 429 → final raise.
        raise RateLimitExceeded(
            "rate limit retries exhausted",
            status_code=429,
            error_code="rate_limit_exceeded",
        )


# ─── Async transport ─────────────────────────────────────────────


class _AsyncTransport:
    """Async mirror of :class:`_SyncTransport`."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float,
        max_retries: int,
        http_client: Optional[httpx.AsyncClient],
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._owned_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        if self._owned_client:
            await self._client.aclose()

    async def __aenter__(self) -> "_AsyncTransport":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        import asyncio

        url = f"{self._base_url}{path}"
        headers = _default_headers(self._api_key)
        if extra_headers:
            headers.update(extra_headers)

        for attempt in range(self._max_retries + 1):
            response = await self._client.request(
                method, url, params=params, json=json,
                headers=headers, timeout=self._timeout,
            )
            if response.status_code == 204:
                return None
            try:
                body = response.json() if response.content else None
            except ValueError:
                body = None
            if response.is_success:
                return body

            if (
                response.status_code == 429
                and attempt < self._max_retries
            ):
                wait = _retry_after(response, body)
                logger.info(
                    "solden-sdk: 429 rate_limit_exceeded, retrying in %ss",
                    wait,
                )
                await asyncio.sleep(wait)
                continue

            raise_for_error(response.status_code, body)
            return None

        raise RateLimitExceeded(
            "rate limit retries exhausted",
            status_code=429,
            error_code="rate_limit_exceeded",
        )


# ─── Helpers ──────────────────────────────────────────────────


def _default_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": f"solden-python/{__version__}",
        "Accept": "application/json",
    }


def _retry_after(response: httpx.Response, body: Optional[Dict[str, Any]]) -> int:
    """Pick the wait time from the most-specific signal available.

    Header beats body — header is what the spec promises; the body
    field is for clients that drop headers (rare).
    """
    header = response.headers.get("Retry-After")
    if header:
        try:
            return max(int(header), 1)
        except ValueError:
            pass
    if body and isinstance(body, dict):
        body_value = body.get("retry_after_seconds")
        if isinstance(body_value, int) and body_value > 0:
            return body_value
    return 5


# ─── Resource namespaces (transport-agnostic) ───────────────────


class _MeResource:
    def __init__(self, transport: Union[_SyncTransport, _AsyncTransport]) -> None:
        self._t = transport

    def get(self) -> Dict[str, Any]:
        """Echo back the resolved key identity."""
        return self._t.request("GET", "/v1/me")


class _RecordsResource:
    def __init__(self, transport: Union[_SyncTransport, _AsyncTransport]) -> None:
        self._t = transport

    def list(
        self,
        *,
        box_type: str,
        state: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> Any:
        """List a page of records. Returns the raw response — call
        :meth:`iter` for automatic pagination across pages."""
        params: Dict[str, Any] = {"box_type": box_type, "limit": limit}
        if state:
            params["state"] = state
        if cursor:
            params["cursor"] = cursor
        return self._t.request("GET", "/v1/records", params=params)

    def get(self, box_id: str, *, box_type: str) -> Any:
        return self._t.request(
            "GET", f"/v1/records/{box_id}",
            params={"box_type": box_type},
        )


class _IntentsResource:
    def __init__(self, transport: Union[_SyncTransport, _AsyncTransport]) -> None:
        self._t = transport

    def list(self) -> Any:
        return self._t.request("GET", "/v1/intents")

    def preview(self, intent: str, input: Dict[str, Any]) -> Any:
        return self._t.request(
            "POST", "/v1/intents/preview",
            json={"intent": intent, "input": input},
        )

    def execute(
        self,
        intent: str,
        input: Dict[str, Any],
        *,
        idempotency_key: Optional[str] = None,
    ) -> Any:
        """Commit an intent.

        If ``idempotency_key`` is None, the SDK generates a fresh UUID4
        so retries-due-to-network-blips don't double-execute. Pass an
        explicit key when your call site owns the retry boundary
        (e.g. a job runner that may re-invoke this code path) so the
        same logical operation reuses the same key across attempts.
        """
        key = idempotency_key or str(uuid.uuid4())
        return self._t.request(
            "POST", "/v1/intents/execute",
            json={"intent": intent, "input": input},
            extra_headers={"Idempotency-Key": key},
        )


class _WebhooksResource:
    def __init__(self, transport: Union[_SyncTransport, _AsyncTransport]) -> None:
        self._t = transport

    def list(self, *, active_only: bool = False) -> Any:
        params = {"active_only": "true"} if active_only else None
        return self._t.request("GET", "/v1/webhooks", params=params)

    def create(
        self,
        *,
        url: str,
        event_types: List[str],
        description: str = "",
    ) -> Any:
        return self._t.request(
            "POST", "/v1/webhooks",
            json={
                "url": url,
                "event_types": event_types,
                "description": description,
            },
        )

    def get(self, webhook_id: str) -> Any:
        return self._t.request("GET", f"/v1/webhooks/{webhook_id}")

    def update(
        self,
        webhook_id: str,
        *,
        url: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Any:
        body: Dict[str, Any] = {}
        if url is not None:
            body["url"] = url
        if event_types is not None:
            body["event_types"] = event_types
        if description is not None:
            body["description"] = description
        if is_active is not None:
            body["is_active"] = is_active
        return self._t.request(
            "PATCH", f"/v1/webhooks/{webhook_id}", json=body,
        )

    def delete(self, webhook_id: str) -> None:
        self._t.request("DELETE", f"/v1/webhooks/{webhook_id}")

    def rotate_secret(self, webhook_id: str) -> Any:
        return self._t.request(
            "POST", f"/v1/webhooks/{webhook_id}/rotate-secret",
        )

    def test(self, webhook_id: str) -> Any:
        return self._t.request("POST", f"/v1/webhooks/{webhook_id}/test")

    def deliveries(self, webhook_id: str, *, limit: int = 50) -> Any:
        return self._t.request(
            "GET", f"/v1/webhooks/{webhook_id}/deliveries",
            params={"limit": limit},
        )


class _AuditResource:
    def __init__(self, transport: Union[_SyncTransport, _AsyncTransport]) -> None:
        self._t = transport

    def list(
        self,
        *,
        box_id: Optional[str] = None,
        box_type: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> Any:
        params: Dict[str, Any] = {"limit": limit}
        if box_id:
            params["box_id"] = box_id
        if box_type:
            params["box_type"] = box_type
        if event_type:
            params["event_type"] = event_type
        return self._t.request("GET", "/v1/audit", params=params)


# ─── Public sync client ──────────────────────────────────────────


class Solden:
    """Sync Solden client.

    Usage::

        client = Solden(api_key="sk_live_...")
        identity = client.me.get()
        page = client.records.list(box_type="ap_item", state="needs_approval")

    Resources: :attr:`me`, :attr:`records`, :attr:`intents`,
    :attr:`webhooks`, :attr:`audit`.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        resolved_key = api_key or os.environ.get("SOLDEN_API_KEY")
        if not resolved_key:
            raise ValueError(
                "api_key is required (pass it directly, or set "
                "SOLDEN_API_KEY in the environment)"
            )
        resolved_base = (
            base_url
            or os.environ.get("SOLDEN_BASE_URL")
            or DEFAULT_BASE_URL
        )
        self._transport = _SyncTransport(
            api_key=resolved_key,
            base_url=resolved_base,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )
        self.me = _MeResource(self._transport)
        self.records = _RecordsResource(self._transport)
        self.intents = _IntentsResource(self._transport)
        self.webhooks = _WebhooksResource(self._transport)
        self.audit = _AuditResource(self._transport)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> "Solden":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ─── Convenience iterators ──────────────────────────────────

    def iter_records(
        self,
        *,
        box_type: str,
        state: Optional[str] = None,
        page_size: int = 200,
    ) -> Iterator[Dict[str, Any]]:
        """Yield every record across pages. Stops when ``next_cursor``
        comes back null."""
        cursor: Optional[str] = None
        while True:
            page = self.records.list(
                box_type=box_type, state=state,
                cursor=cursor, limit=page_size,
            )
            for record in page.get("records", []):
                yield record
            cursor = page.get("next_cursor")
            if not cursor:
                return


# ─── Public async client ────────────────────────────────────────


class AsyncSolden:
    """Async Solden client.

    Same resource surface as :class:`Solden`; every method is a
    coroutine.

    Usage::

        async with AsyncSolden() as client:
            page = await client.records.list(box_type="ap_item")
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        resolved_key = api_key or os.environ.get("SOLDEN_API_KEY")
        if not resolved_key:
            raise ValueError(
                "api_key is required (pass it directly, or set "
                "SOLDEN_API_KEY in the environment)"
            )
        resolved_base = (
            base_url
            or os.environ.get("SOLDEN_BASE_URL")
            or DEFAULT_BASE_URL
        )
        self._transport = _AsyncTransport(
            api_key=resolved_key,
            base_url=resolved_base,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )
        self.me = _MeResource(self._transport)
        self.records = _RecordsResource(self._transport)
        self.intents = _IntentsResource(self._transport)
        self.webhooks = _WebhooksResource(self._transport)
        self.audit = _AuditResource(self._transport)

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> "AsyncSolden":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
