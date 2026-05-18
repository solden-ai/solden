"""Solden — official Python SDK for the /v1 API.

Quickstart:

    from solden import Solden

    client = Solden(api_key="sk_live_...")
    for record in client.records.list(box_type="ap_item", state="needs_approval"):
        client.intents.execute("approve_invoice", {"ap_item_id": record["id"]})

The SDK is a thin wrapper around the public REST API. Every method
maps 1:1 to an endpoint documented at
https://github.com/soldenai/Clearledgr-AP/tree/main/docs/v1 .
"""

from solden._version import __version__
from solden.client import AsyncSolden, Solden
from solden.exceptions import (
    APIKeyExpired,
    APIKeyRevoked,
    IdempotencyConflict,
    InternalError,
    InvalidAPIKey,
    InvalidRequest,
    InvalidScope,
    MissingAPIKey,
    NotFound,
    RateLimitExceeded,
    SoldenError,
    StateConflict,
)
from solden.webhooks import verify_signature

__all__ = [
    "__version__",
    "AsyncSolden",
    "Solden",
    # Exceptions
    "APIKeyExpired",
    "APIKeyRevoked",
    "IdempotencyConflict",
    "InternalError",
    "InvalidAPIKey",
    "InvalidRequest",
    "InvalidScope",
    "MissingAPIKey",
    "NotFound",
    "RateLimitExceeded",
    "SoldenError",
    "StateConflict",
    # Webhook verification
    "verify_signature",
]
