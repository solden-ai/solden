# solden — Python SDK for the Solden /v1 API

Official Python client. Sync + async. Thin wrapper over the public
REST API documented at
[docs/v1/](https://github.com/solden-ai/solden/tree/main/docs/v1).

## Install

```bash
pip install solden
```

## Quickstart

```python
from solden import Solden

client = Solden(api_key="sk_live_...")

# Confirm the key
print(client.me.get())

# List records the agent can read
page = client.records.list(box_type="ap_item", state="needs_approval")
for record in page["records"]:
    if record["data"]["amount"] < 1000:
        client.intents.execute(
            "approve_invoice",
            {"ap_item_id": record["id"]},
        )
```

Set `SOLDEN_API_KEY` in your environment and omit `api_key=...` to
pick it up implicitly.

## Async

```python
from solden import AsyncSolden

async with AsyncSolden() as client:
    identity = await client.me.get()
    page = await client.records.list(box_type="ap_item")
```

## Idempotency

Every `intents.execute` call generates a UUID4 `Idempotency-Key`
automatically. To make a retried operation reuse the same key,
pass one explicitly:

```python
client.intents.execute(
    "approve_invoice",
    {"ap_item_id": "ap_abc"},
    idempotency_key="approve-ap_abc-2026-05-18T10:14Z",
)
```

## Rate limits

The client retries 429 responses up to `max_retries` times (default
3), sleeping for `Retry-After` between attempts. To handle limits
explicitly instead, catch `RateLimitExceeded`:

```python
from solden import Solden, RateLimitExceeded

client = Solden(max_retries=0)

try:
    client.intents.execute(...)
except RateLimitExceeded as e:
    print(f"backing off {e.retry_after_seconds}s on {e.scope}")
```

## Webhook signature verification

```python
from solden import verify_signature

@app.post("/solden-webhooks")
async def receive(request):
    body = await request.body()
    if not verify_signature(
        body,
        request.headers.get("X-Solden-Signature", ""),
        secret=os.environ["SOLDEN_WEBHOOK_SECRET"],
    ):
        return Response(status_code=401)
    payload = await request.json()
    ...
```

Always verify against the **raw** request body. Re-serialising the
parsed JSON will reorder keys and break verification.

## Pagination helper

```python
for record in client.iter_records(box_type="ap_item"):
    process(record)
```

Walks every page until `next_cursor` is null. No async equivalent yet
— call `await client.records.list(cursor=...)` in a loop.

## Errors

Every non-2xx response raises a typed exception:

| Exception              | error_code                        |
|------------------------|-----------------------------------|
| `MissingAPIKey`        | `missing_api_key`                 |
| `InvalidAPIKey`        | `invalid_api_key`                 |
| `APIKeyRevoked`        | `api_key_revoked`                 |
| `APIKeyExpired`        | `api_key_expired`                 |
| `InvalidScope`         | `invalid_scope`                   |
| `InvalidRequest`       | `invalid_request`, `invalid_url`, `invalid_event_type`, `unsupported_box_type`, `empty_update` |
| `NotFound`             | `not_found`                       |
| `StateConflict`        | `state_conflict`                  |
| `IdempotencyConflict`  | `idempotency_conflict`            |
| `RateLimitExceeded`    | `rate_limit_exceeded`             |
| `InternalError`        | `internal_error`                  |

All inherit from `SoldenError`. Catch that for a fallback handler.

## License

Apache-2.0. See `LICENSE` at the repository root.
