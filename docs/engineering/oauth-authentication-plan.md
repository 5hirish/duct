# OAuth Authentication for Google Ads — Implementation Plan

## Context

The current `/run` page requires users to manually enter 5+ credentials (developer token, OAuth client ID, OAuth client secret, refresh token, customer ID). This is a high-friction experience that will block client onboarding. The goal is to replace this with a standard "Sign in with Google Ads" OAuth 2.0 flow, so users authorize once and the app handles the rest.

---

## Key Decisions

### PyAirbyte — DEFER

PyAirbyte is **not** the right tool for this change. It would replace `google_ads_api_fetch.py`, but:

- The current fetch script already returns exactly the schema `build_brief()` expects (`source_metadata` + `rows[]` with `previous` comparison data)
- PyAirbyte's `source-google-ads` returns flat records per stream — you'd need to re-implement the two-window aggregation and merge logic that already exists
- That is more code, not less
- Add PyAirbyte when expanding to a second connector (GA4, HubSpot) — not before

**The OAuth work here changes how credentials are supplied to `google_ads_api_fetch.py`, not the fetch logic itself.**

### Supabase — DEFER

Not needed for this MVP. `sessionStorage` satisfies the requirement: tokens survive page navigation but are cleared when the tab closes — the right UX boundary for a sign-in flow. Add Supabase in Phase 3 when you need cross-session persistence, multi-user workspaces, or per-user token storage.

### Token Storage — sessionStorage

| Option | Decision |
|---|---|
| `localStorage` | No — overly persistent for credentials |
| `sessionStorage` | **Yes** — cleared on tab close, acceptable XSS risk for internal MVP |
| httpOnly cookie | No — adds CORS+cookie config complexity not worth it now |

### developer_token

The Google Ads `developer_token` is NOT part of the OAuth flow — it is tied to your Ads Developer account. **Store it as `GOOGLE_ADS_DEVELOPER_TOKEN` in the backend `.env` and never send it to the frontend.** The user form goes from 5 fields to zero input fields (aside from date range and account selector).

---

## Architecture: OAuth Flow

```
User clicks "Connect Google Ads"
  → Full-page nav: GET /auth/google/authorize
    → Backend: generate state token, redirect to Google consent URL
      (scope: https://www.googleapis.com/auth/adwords, access_type=offline, prompt=consent)
  → Google: user grants access
  → Google: redirects to /auth/google/callback?code=...&state=...
    → Backend: validate state (CSRF check), exchange code for tokens via google-auth-oauthlib
    → Backend: redirect to http://localhost:3000/run#refresh_token=<token>
  → Frontend /run page: useEffect reads window.location.hash on mount
    → Store refresh_token in sessionStorage
    → Clear hash from URL bar (window.history.replaceState)
    → Fetch /api/google-ads/accounts?refresh_token=...
    → Render account selector dropdown
  → User selects account, picks dates, clicks "Run report"
    → POST /api/report/google-ads with { customer_id, refresh_token, date_from, date_to }
    → Backend: fetch_campaigns() — unchanged
    → Report renders as before
```

**Why redirect with URL fragment (#) instead of storing server-side:** Simpler MVP, no session storage on backend. Tokens are briefly in the URL bar but this is acceptable for an internal/operator tool. For production: swap to server-side session pattern (backend stores token keyed by random session ID, frontend fetches it and backend deletes it).

### SDK roles

- `google-auth-oauthlib` → handles OAuth consent flow → produces `refresh_token` (already a transitive dep of `google-ads`, **zero new packages**)
- `google-ads` SDK → already handles all GAQL querying and fetching in `google_ads_api_fetch.py` — **unchanged**
- For future multi-provider OAuth (HubSpot, Meta, GA4): use **Nango** (already in roadmap, deferred). Do not add `authlib` now — wait until provider #2.

---

## One-Time Google Cloud Console Setup (manual, before coding)

1. Google Cloud Console → APIs & Services → Credentials → Create OAuth 2.0 Client ID → type **Web application**
2. Add authorized redirect URIs:
   - `http://localhost:8000/auth/google/callback`
   - Production backend URL (when deployed)
3. Enable **Google Ads API** in the project
4. Note `client_id` and `client_secret` — these go in backend `.env` as `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`
5. Ensure `GOOGLE_ADS_DEVELOPER_TOKEN` is in `.env`

---

## Files to Modify

### `backend/server.py`

1. **Add env vars** at top of file:
   ```python
   GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
   GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
   GOOGLE_OAUTH_REDIRECT_URI = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
   FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
   _oauth_states: dict[str, float] = {}  # state_token → timestamp, for CSRF
   ```

2. **Update CORS** to use `FRONTEND_ORIGIN`.

3. **Update `ReportRequest`** — make `client_id`, `client_secret`, `login_customer_id` optional (they will no longer come from the frontend in normal use).

4. **Update `_resolve_ads_credentials()`** — `client_id` and `client_secret` always come from env vars, never from request body. Only `refresh_token` comes from the request.

5. **Add `GET /auth/google/authorize`** using `google-auth-oauthlib`:
   ```python
   from google_auth_oauthlib.flow import Flow
   import secrets, time

   @app.get("/auth/google/authorize")
   def google_authorize():
       state = secrets.token_urlsafe(32)
       _oauth_states[state] = time.time()
       flow = Flow.from_client_config(
           {"web": {
               "client_id": GOOGLE_OAUTH_CLIENT_ID,
               "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
               "auth_uri": "https://accounts.google.com/o/oauth2/auth",
               "token_uri": "https://oauth2.googleapis.com/token",
           }},
           scopes=["https://www.googleapis.com/auth/adwords"],
           redirect_uri=GOOGLE_OAUTH_REDIRECT_URI,
       )
       auth_url, _ = flow.authorization_url(
           access_type="offline", prompt="consent", state=state
       )
       return RedirectResponse(auth_url)
   ```
   Note: `google-auth-oauthlib` is already a transitive dependency of `google-ads` — no new packages needed.

6. **Add `GET /auth/google/callback`** (receives `code` and `state` query params):
   - Validate `state` in `_oauth_states` and not older than 5 minutes (reject CSRF)
   - Reconstruct `Flow` with same config, call `flow.fetch_token(code=code)`
   - Extract `flow.credentials.refresh_token`
   - Return `RedirectResponse` to `{FRONTEND_ORIGIN}/run#refresh_token={refresh_token}`

7. **Add `GET /api/google-ads/accounts`** (accepts `refresh_token` as query param):
   - Call `list_accessible_accounts()` from new script
   - Return list of `{ customer_id, descriptive_name, currency_code, time_zone }`

### `backend/scripts/google_ads_accounts.py` (NEW FILE)

Create `list_accessible_accounts(developer_token, client_id, client_secret, refresh_token) -> list[dict]`:
- Build `GoogleAdsClient` from those creds
- Call `CustomerService.list_accessible_customers()` → returns resource names like `"customers/1234567890"`
- For each, run a GAQL query: `SELECT customer.id, customer.descriptive_name, customer.currency_code, customer.time_zone, customer.manager FROM customer LIMIT 1`
- Label MCC accounts (`customer.manager == True`) in the returned dict
- Catch per-account exceptions silently (some accounts may be inaccessible)
- Return list of account dicts

### `backend/pyproject.toml`

**No changes needed.** `google-auth-oauthlib` is already a transitive dependency of `google-ads ^24.0`.

### `app/src/app/run/page.jsx`

Replace the 5-field credential form with a 3-state UI:

**State machine:** `"checking" | "unauthenticated" | "selecting_account" | "ready"`

**State variables:**
```javascript
const [authState, setAuthState] = useState("checking");
const [refreshToken, setRefreshToken] = useState(null);
const [accounts, setAccounts] = useState([]);
const [selectedAccount, setSelectedAccount] = useState(null);
```

**`useEffect` on mount:**
1. Check `window.location.hash` for `#refresh_token=...` (returning from OAuth)
   - If found: store in `sessionStorage.setItem("gads_refresh_token", token)`, clear hash with `window.history.replaceState(null, "", window.location.pathname)`
2. Check `sessionStorage.getItem("gads_refresh_token")`
3. If token found: set `refreshToken`, call `fetchGoogleAdsAccounts(token)`, set `authState = "selecting_account"`
4. If no token: set `authState = "unauthenticated"`

**Render by state:**
- `unauthenticated`: Show `<a href="{BACKEND}/auth/google/authorize">Connect Google Ads</a>` (full page nav, not fetch)
- `selecting_account`: Show `<select>` populated from `accounts`, plus date pickers, plus "Run report" button (disabled until account selected)
- `ready`: Same as above but account pre-selected; show "Sign out" link

**Sign out:**
```javascript
function signOut() {
  sessionStorage.removeItem("gads_refresh_token");
  sessionStorage.removeItem("gads_customer_id");
  setRefreshToken(null); setSelectedAccount(null); setAuthState("unauthenticated");
}
```

**Modified POST payload** — remove `developer_token`, `client_id`, `client_secret`, `login_customer_id`; add `refresh_token` from sessionStorage, `account_name` and `currency_code` from selected account object.

### `app/src/lib/api.js`

Add:
```javascript
export async function fetchGoogleAdsAccounts(refreshToken) {
  const res = await fetch(`${BASE}/api/google-ads/accounts?refresh_token=${encodeURIComponent(refreshToken)}`);
  if (!res.ok) throw new Error(`Failed to fetch accounts: ${res.status}`);
  return res.json();
}
```

---

## New Environment Variables (`backend/.env`)

```
GOOGLE_OAUTH_CLIENT_ID=<your-web-app-oauth-client-id>
GOOGLE_OAUTH_CLIENT_SECRET=<your-web-app-oauth-client-secret>
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/auth/google/callback
FRONTEND_ORIGIN=http://localhost:3000
GOOGLE_ADS_DEVELOPER_TOKEN=<your-developer-token>
```

The existing `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN` env vars can remain for CLI/local script use — they are separate from the OAuth app credentials.

---

## Files NOT Changed

- `backend/scripts/google_ads_api_fetch.py` — fetch logic unchanged
- `backend/scripts/google_ads_brief.py` — brief logic unchanged
- `backend/briefs/schemas/google_ads_brief.py` — schema unchanged
- `app/src/components/GoogleAdsReport.js` — rendering unchanged

---

## Risks & Gotchas

| Risk | Mitigation |
|---|---|
| Google only returns `refresh_token` on first consent | Use `prompt=consent` in authorize URL to always force a new one |
| `list_accessible_customers()` may include MCC manager accounts (can't query directly for campaigns) | Include `customer.manager` in GAQL, label MCCs in the dropdown |
| `sessionStorage` is tab-scoped — second tab requires re-auth | Acceptable for MVP single-operator use; fix with Supabase in Phase 3 |
| Token briefly visible in URL bar via `#fragment` | Acceptable for internal tool; swap to server-side session pattern for production |
| Python 3.11/3.12 constraint from `google-ads` | Already handled in `pyproject.toml` — `google-ads ^24.0` includes `list_accessible_customers()` |
| Future multi-provider OAuth (HubSpot, Meta) | Use Nango (already in roadmap, deferred). Do not add `authlib` now — wait until provider #2. |

---

## Verification

1. Start backend: `cd backend && uvicorn server:main --reload --port 8000`
2. Start frontend: `cd app && npm run dev`
3. Navigate to `http://localhost:3000/run`
4. Confirm "Connect Google Ads" button appears (not the old credential form)
5. Click it — confirm redirect to Google consent screen
6. Complete consent — confirm redirect back to `/run` with account dropdown populated
7. Select an account, pick a date range, click "Run report"
8. Confirm report generates and renders (same output as before)
9. Refresh the page — confirm sessionStorage restores the connection without re-auth
10. Close tab, reopen — confirm re-auth is required (sessionStorage cleared)
11. Click "Sign out" — confirm returns to unauthenticated state
