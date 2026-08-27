# RevenueCat

- **RevenueCat is the mobile subscription truth.** Installs and in-app events
  are fire-and-forget signals; RevenueCat sees refunds, billing retries,
  grace periods, and cancellations. Reconcile ad-platform conversions against
  it, never the reverse.
- **Public SDK keys can never read the REST API.** Keys starting
  `appl_`/`goog_`/`amzn_`/`rcb_` are mobile SDK keys; the REST API needs a
  **Secret API key (V2)** (Project settings → API keys).
- **v2 keys are granular and default to NOTHING.** A key with no scopes 401s
  everywhere; a key missing only `charts_metrics:overview:read` 403s on
  metrics and looks healthy on structure — both read as "the key is wrong"
  if you aren't expecting it.
- **Two rate-limit domains:** charts/metrics is 25 req/min (the one a
  reporting pull hammers); customer info is 480 req/min. Self-pace chart
  calls (~2.4s apart) instead of discovering the budget via 429s.
- **`next_page` is a RELATIVE path** (`/v2/...`), not a full URL — naive
  joining onto the API base double-prefixes `/v2`.
- v2 requires `Authorization: Bearer <key>` (v1 accepted the bare key) — a
  missing Bearer prefix is an instant 401 with a working key.
- **Hash `app_user_id` before storing or quoting it** (SHA-256) — stable
  enough to join across pulls, useless for identifying a person.
- Error envelopes carry `retryable` and `backoff_ms` — honour the server's
  own backoff hint when present.
