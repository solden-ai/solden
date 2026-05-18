"""HMAC-SHA256 signature verification for inbound webhooks.

Use this on your webhook receiver before trusting any payload:

    from solden import verify_signature

    @app.post("/solden-webhooks")
    async def receive(request):
        body = await request.body()
        sig = request.headers.get("X-Solden-Signature", "")
        if not verify_signature(body, sig, secret=os.environ["SOLDEN_WEBHOOK_SECRET"]):
            return 401
        ...

Always verify against the **raw** body bytes. Re-serialising the
parsed JSON will reorder keys and break verification.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Union


def verify_signature(
    body: Union[bytes, str],
    header_value: str,
    *,
    secret: str,
) -> bool:
    """Returns True iff ``header_value`` is a valid signature for
    ``body`` computed with ``secret``.

    ``header_value`` should be the literal value of the
    ``X-Solden-Signature`` (or legacy ``X-Clearledgr-Signature``)
    header — formatted as ``sha256=<hex>``. Any other shape returns
    False.

    Uses :func:`hmac.compare_digest` so the comparison is
    constant-time and immune to timing side-channels.
    """
    if not header_value or not header_value.startswith("sha256="):
        return False
    if not secret:
        return False

    expected = header_value[len("sha256="):]
    body_bytes = body.encode("utf-8") if isinstance(body, str) else body

    computed = hmac.new(
        secret.encode("utf-8"), body_bytes, hashlib.sha256
    ).hexdigest()
    try:
        return hmac.compare_digest(computed, expected)
    except (TypeError, ValueError):
        return False
