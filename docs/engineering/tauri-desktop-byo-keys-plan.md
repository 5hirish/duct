# Tauri Desktop App + Bring‑Your‑Own Provider Keys — Implementation Plan

> **Status:** Draft for review
> **Date:** 2026‑06‑18
> **Branch:** `claude/stoic-volta-2alwt0`
> **Owner:** @5hirish

## 1. Goal

Ship an **alpha/beta desktop app** (macOS / Windows / Linux) to early adopters and
friends, with a new **Providers** surface that lets each user supply their **own
provider API keys** (Anthropic / OpenAI / Gemini, plus OpenRouter later). During
the beta this shifts inference cost to the tester and keeps our spend at zero.

Two hard constraints shape the whole design:

1. **Protect our IP.** Agent prompts and orchestration code must never ship to the
   user's machine. They stay server‑side on Railway.
2. **Handle user keys carefully.** Encrypted at rest (OS keychain), encrypted in
   transit (TLS), never logged, never durably persisted server‑side.

## 2. Decision & guiding principle

- **Shell: Tauri (v2).** The desktop app is a *thin client* — it renders our
  existing Next frontend and calls the existing Railway API. That is Tauri's
  sweet spot (system webview + a little native capability), and it gives a
  ~5–10 MB artifact instead of Electron's ~150 MB. Electron's only edge (bundled
  Node to run agents locally) is irrelevant because **we are not running agents
  locally** (see §4).
- **Principle: the desktop app changes nothing about where the agent runs.** The
  browser is already a thin client of Railway today; the desktop app is a second
  thin client. Our prompts already never leave the backend — the desktop bundle
  ships only the already‑public frontend JS.

## 3. Architecture

```
┌─────────────────────────────┐         HTTPS (TLS)        ┌──────────────────────┐        ┌────────────┐
│  Tauri desktop shell        │  ── POST /api/insights ──▶ │  Railway (FastAPI)   │ ─────▶ │  Provider   │
│  ┌───────────────────────┐  │     + X-API-Key            │                      │  uses  │  (Anthropic │
│  │ existing Next frontend │  │     + X-Provider-Key(s)    │  reads prompts/*.py  │  user  │   /OpenAI/  │
│  │ (loaded from hosted    │  │                            │  builds system+tools │  key   │   Gemini)   │
│  │  URL — already public) │  │  ◀── SSE tokens / JSON ──  │  runs v1/v2/v3       │ ◀───── │            │
│  └───────────────────────┘  │                            │  agent (our IP)      │        └────────────┘
│  Rust core: OS keychain     │                            └──────────────────────┘
│  (keyring crate) + updater  │   The prompt only ever exists between Railway and the provider.
└─────────────────────────────┘   The user's key is used in Railway memory per‑request, never stored.
```

**What ships in the desktop bundle:** the compiled Next frontend (identical to
what `app.getduct.ai` already serves to every browser) + a thin Rust shell. No
prompts, no agent code, no secrets.

## 4. Non‑goals / explicit guardrails

- ❌ **No on‑device agent execution.** That would force bundling prompts/runners
  into the binary, where `strings binary | grep` recovers them. Agents stay on
  Railway.
- ❌ **No subscription‑OAuth proxying.** `CLAUDE_CODE_OAUTH_TOKEN` /
  `claude setup-token` is for a single operator's own use only. The codebase
  already documents this (`config.py:135‑145`, `claude_oauth_available()` and the
  link to Anthropic's compliance docs). Multi‑user BYO = **Console API keys** only.
- ❌ **No durable server‑side storage of user keys** for the alpha. Keys live in
  the user's keychain and travel per‑request; the server holds them only in
  memory for the duration of the call.
- ❌ **No computer‑use / local automation** in this scope (see §13 for how Tauri
  keeps that door open later).

## 5. Current‑state findings (reviewed code)

### Backend (FastAPI on Railway)
- **Engine/key registry:** `agents/engines.py` — `PROVIDER_CONFIG_ATTR` (`:96`)
  maps `Provider → {openai,gemini,anthropic}_api_key`; `ENGINE_SUPPORTED_PROVIDERS`
  (`:53`), `ENGINE_SUPPORTS_OAUTH` (`:63`), `ENGINE_PROVIDER_ENV_VAR` (`:71`).
- **Single key chokepoint:** `routes/generate.py:_resolve_agent_config` (`:71`)
  resolves `api_key = getattr(cfg, PROVIDER_CONFIG_ATTR[provider], "")` (`:81`);
  `_build_agent` (`:85`) constructs the runner with `api_key=` (`:90‑93`). All
  three engines already accept `api_key` in their constructor.
- **Endpoints:** `POST /api/insights/generate` (`:673`) and
  `/api/insights/generate/stream` (`:682`), both `req: GenerateRequest` +
  `Depends(get_current_user_optional)`. The unified agent API lives in
  `routes/agents.py` (sessions/stream/messages).
- **Route auth:** routers mount `Depends(validate_api_key)` (`routes/namespace.py`)
  — the `X-API-Key` / `duct_api_key` gate. Orthogonal to the new per‑user key.
- **Config:** `config.py` Pydantic `BaseSettings`, `@lru_cache get_configs()`.
  Provider keys at `:132‑134`; `duct_api_key` (`:74`); **`credentials_encryption_key`
  Fernet** already used to encrypt connector refresh tokens at rest (`:78`) — a
  reusable pattern if we ever persist keys; `frontend_origin` for CORS (`:31`).
- **⚠ Concurrency hazard (must fix):** `agents/insights/v3/runner.py:_run_synthesis`
  mutates **process‑global `os.environ[ANTHROPIC_API_KEY]`** (`:186‑189`) with
  save/restore in `finally` (`:258‑261`). Two problems for multi‑user BYO:
  (a) `if api_key and not os.environ.get(env_var)` means a **server key already in
  the env wins and the user's key is ignored**; (b) concurrent requests with
  different keys race on the same global var. The SDK already accepts a per‑call
  `ClaudeAgentOptions(env={…})` (`:199`) — inject the key there instead. The v2
  ADK runner (`agents/insights/v2/runner.py`) likely needs the same audit.

### Frontend (Next 16 on Cloudflare)
- **API layer:** `lib/api.js` — `BASE` (`:9`), `backendApiHeaders()` adds
  `X-API-Key` from `NEXT_PUBLIC_DUCT_API_KEY` (`:13`), `authToken()` reads a
  Bearer JWT from `localStorage` (`:25`). `generateReport`/`generateReportStream`
  (`:89`, `:218`) POST to the insights endpoints.
- **Connections UI:** `app/(app)/connections/page.jsx` — a `connection-grid` of
  `connection-card`s (Google Ads/GSC/GA4/…). Natural home for a Providers tab.
- **Engine metadata:** `lib/engines.js` — `ENGINES` registry with
  `supportsOAuth`; purely UI, no agent logic (confirms no IP in the frontend).
- **Existing secret transport precedent:** connector refresh tokens are kept in
  `sessionStorage` and sent in request bodies (`lib/api.js:103‑113`).

### Env vars in use
- **Frontend (`NEXT_PUBLIC_*`):** `API_BASE`, `APP_ENV`, `APP_URL`,
  `CDN_IMAGE_RESIZING`, `DUCT_API_KEY`, `GTM_ID`, `SENTRY_DSN`, `SITE_URL`,
  `TURNSTILE_SITE_KEY`.
- **Backend (relevant):** `anthropic_api_key`, `openai_api_key`, `gemini_api_key`,
  `duct_api_key`, `credentials_encryption_key`, `claude_code_oauth_token`,
  `generate_engine`, `frontend_origin`, `app_env`, `sentry_dsn`.

## 6. Workstream A — Backend: per‑request BYO key (shell‑agnostic)

> This is the foundational domino. It is pure backend, has **no dependency on the
> desktop app**, and also powers a web BYO beta. Build it first.

1. **Transport via headers, not the request body.** Add a FastAPI dependency
   `get_user_provider_keys()` that reads per‑provider headers
   (`X-Provider-Anthropic`, `X-Provider-OpenAI`, `X-Provider-Gemini`) and returns
   `dict[Provider, str]`. Rationale: keeps secrets out of `GenerateRequest`
   bodies (which may be logged/streamed), consistent with the existing `X-API-Key`
   convention, easy to scrub centrally.
2. **Thread into the chokepoint.** Change `_resolve_agent_config` to accept
   `user_keys: dict[Provider, str] | None` and resolve
   `api_key = user_keys.get(provider) or getattr(cfg, PROVIDER_CONFIG_ATTR[provider], "")`.
   `_build_agent` is unchanged. Add the dependency param to `generate_insight` /
   `generate_insight_stream` and pass through `_run_generate_pipeline`.
3. **Fix the v3 global‑env hazard.** In `runner.py:_run_synthesis`, stop writing
   `os.environ`; instead set the provider env var inside the per‑call
   `ClaudeAgentOptions(env={…})` dict so each request is isolated and the user key
   always takes precedence for that request. Audit v2 (ADK) for the same pattern.
4. **Validation & failure UX.** Validate key shape per provider (e.g. `sk-ant-…`,
   `sk-…`); on missing/invalid key for the selected engine, return a typed error
   the UI can show ("Add your Anthropic key in Providers"). Reuse the
   `/api/engines/status` shape (`auth_method`, `supports_oauth`).
5. **No‑leak hygiene.** Never log key values; add a Sentry `before_send` scrubber
   for the new headers; ensure keys aren't echoed in error messages or SSE frames.
6. **Scope.** Insights (`v1/v2/v3`) first. Note follow‑ups for `routes/agents.py`
   sessions and the audit/content v3 runners (same chokepoint pattern).

**Out of scope for A:** persistence. If we later want "remember my key", reuse the
existing **Fernet `credentials_encryption_key`** pattern + a per‑user row — not a
plaintext column.

## 7. Workstream B — Frontend: Providers tab (works in web *and* desktop)

1. **New Providers section** in `connections/page.jsx` (tab or card group):
   per‑provider entry (Anthropic / OpenAI / Gemini; OpenRouter later) with
   masked input, "Connected/Not connected" pill (mirrors existing cards),
   test‑key button (calls `/api/engines/status`), and remove.
2. **Shell‑aware key store** (`lib/providerKeys.js`): one interface, two backends —
   - **Web build:** `sessionStorage` (consistent with current connector tokens).
   - **Desktop build:** detect `window.__TAURI__` and read/write via a Tauri
     command (`invoke('get_provider_key' | 'set_provider_key')` → OS keychain).
3. **Attach keys to requests** in `lib/api.js`: extend `backendAuthedHeaders()` to
   add the `X-Provider-*` headers from the store when present.
4. **Guidance copy:** prompt testers to paste **budget‑capped / restricted** keys
   (OpenAI project key with a cap, Anthropic workspace key) to bound blast radius.

## 8. Workstream C — Tauri shell

1. **Scaffold** `desktop/` (Tauri v2, `create-tauri-app`). Keep it out of the
   Next build; its own CI lane.
2. **Load the hosted URL** (`https://app.getduct.ai`) in the webview for the alpha
   → zero frontend rebuild, nothing secret added to the bundle. (Bundling a static
   export is a later option; see §11 risks.)
3. **Keychain command (Rust):** ~30 lines using the `keyring` crate — wraps macOS
   Keychain / Windows Credential Manager / Linux Secret Service. Expose
   `get_provider_key` / `set_provider_key` / `delete_provider_key` to the frontend
   via `invoke`.
4. **API transport & CORS:** because the webview loads a hosted origin and calls
   the Railway origin, confirm CORS (`frontend_origin`) allows it (it already does
   for the web app). If we later bundle the frontend locally (origin
   `tauri://localhost`), either add that origin to backend CORS **or** route API
   calls through Tauri's Rust HTTP plugin (no CORS). Decision flagged in §12.
5. **Auto‑update:** `tauri-plugin-updater` against a static manifest (e.g. R2).
6. **Packaging/signing:** macOS notarization (Apple Developer ID, ~$99/yr),
   Windows code‑signing cert (or accept SmartScreen warnings for alpha), Linux
   AppImage/deb. Treat the bundle as fully public.

## 9. Env‑var & config changes

| Scope | Var | Change |
|---|---|---|
| Backend | `X-Provider-*` (headers, not env) | New per‑request transport; no new server env var required |
| Backend | `anthropic/openai/gemini_api_key` | Now a **fallback** when no user key is supplied (unchanged for server‑funded paths) |
| Backend | `frontend_origin` (CORS) | Verify/extend to cover desktop origin **iff** we bundle locally |
| Frontend | `NEXT_PUBLIC_*` | None for hosted‑URL mode; only needed if we produce a separate static desktop build |
| Desktop | Tauri updater endpoint / signing keys | New CI secrets (not app runtime env) |

## 10. Security model (summary)

- **At rest:** OS keychain on device (Keychain / Credential Manager / Secret
  Service). Linux Secret Service may be absent on minimal setups → document the
  fallback.
- **In transit:** TLS to Railway; keys in headers (never URLs/query strings).
- **Transient:** plaintext only in Railway memory during the call; never logged,
  never persisted (alpha).
- **Gate key caveat:** `NEXT_PUBLIC_DUCT_API_KEY` is a shared app‑gate value baked
  into the (already public) client, not a user secret. Acceptable for alpha; note
  the existing TODO about a Next server proxy (`lib/api.js:12`).
- **Blast‑radius control:** restricted/budget‑capped keys recommended in‑product.

## 11. Phasing

- **Phase 0 — Backend BYO key (Workstream A).** Ships independently; testable via
  the existing web app with a header. *Unblocks everything.*
- **Phase 1 — Providers tab (Workstream B), web mode.** Real cost‑shifting for a
  web beta, no desktop needed.
- **Phase 2 — Tauri shell (Workstream C)** loading the hosted URL + keychain.
- **Phase 3 — Packaging, signing, auto‑update, distribute to testers.**

Each phase is shippable and reversible.

## 12. Decisions needed from you

1. **Key transport:** per‑provider headers (recommended) vs a single JSON header
   vs request‑body fields?
2. **Desktop frontend delivery:** load hosted `app.getduct.ai` (fastest, recommended)
   vs bundle a static export (offline‑capable, more work + CORS/build changes)?
3. **Providers in scope for alpha:** Anthropic + OpenAI + Gemini only, or include
   OpenRouter from day one?
4. **Repo location for the Tauri app:** new top‑level `desktop/` in this monorepo
   vs a separate repo?
5. **Persistence later:** confirm "never persist server‑side" for alpha (reuse
   Fernet pattern only if/when we add "remember key").

## 13. Future (out of scope, kept open)

- **Computer use:** prefer a **sandboxed** VM/container (local or cloud) where the
  desktop app is just a viewer — shell choice stays irrelevant. If we ever want
  real on‑device automation, add a `nut.js` (Node) or `pyautogui` (Python)
  **Tauri sidecar**; choosing Tauri now does not foreclose it.
- **Subscription‑OAuth (power users):** only viable with on‑device execution and
  within Anthropic's terms — revisit separately, not for multi‑user serving.
- **Mobile:** Tauri v2 can target iOS/Android from the same shell if a mobile BYO
  app is ever wanted.

## 14. Concrete change list (for implementation)

| File | Change |
|---|---|
| `backend/routes/generate.py` | `_resolve_agent_config` accepts `user_keys`; prefer user key; add header dependency to the two endpoints |
| `backend/routes/deps.py` *(new or existing deps module)* | `get_user_provider_keys()` header dependency → `dict[Provider,str]` |
| `backend/agents/insights/v3/runner.py` | Inject key via per‑call `ClaudeAgentOptions(env=…)`; stop mutating `os.environ` (`:186‑189`, `:258‑261`) |
| `backend/agents/insights/v2/runner.py` | Audit/repair the same global‑env pattern |
| `backend/utils/` + Sentry init | Scrub `X-Provider-*` headers; never log key values |
| `app/src/lib/providerKeys.js` *(new)* | Shell‑aware key store (sessionStorage ↔ Tauri keychain) |
| `app/src/lib/api.js` | Add `X-Provider-*` headers in `backendAuthedHeaders()` |
| `app/src/app/(app)/connections/page.jsx` | Providers tab/section UI |
| `desktop/` *(new)* | Tauri v2 shell: webview→hosted URL, `keyring` commands, updater, packaging |
```
