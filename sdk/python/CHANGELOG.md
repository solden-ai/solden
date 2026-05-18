# Changelog

## [0.1.0] — 2026-05-18

Initial public release.

* Sync (`Solden`) and async (`AsyncSolden`) clients sharing the same
  resource surface: `me`, `records`, `intents`, `webhooks`, `audit`.
* Auto-generated `Idempotency-Key` on every `intents.execute` call.
* Built-in 429 retry honouring `Retry-After` (header beats body).
* Typed exceptions per `error_code` — every non-2xx response routes
  to a specific class inheriting from `SoldenError`.
* `verify_signature()` helper for inbound webhook verification.
* Pagination iterator `Solden.iter_records()`.
* Env-var auth via `SOLDEN_API_KEY`.
