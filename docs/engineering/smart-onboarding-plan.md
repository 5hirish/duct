# Smart onboarding — the audit is the onboarding

**Status:** Accepted 2026-09-08; Phases 1–3 built the same day, then Phase 2b
(ChatGPT sign-in in the shell), Phase 5 (the wizard is gone; Project context
lives at `/project/[id]`), and from Phase 4 the contextual Search Console
prompt, the share link and the guest sign-in gate on it. Rendered end to end
against a live crawl of getduct.ai and a live OpenAI 401 (see §10 for what is
built and what is not).

Companion reading:
[`autonomous-insights-agent-plan.md`](autonomous-insights-agent-plan.md) (the same
"wire what exists, delete the wizard" shape, one agent over),
[`model-routing-ux-design.html`](model-routing-ux-design.html) §10 (the tier map no
run reads yet — §4 here is where an agent run starts reading it),
[`project-collaboration-plan.md`](project-collaboration-plan.md) (members + invites,
reused as-is),
[`agent-memory-research.html`](agent-memory-research.html) §07 (provenance chips —
every field this plan infers gets one),
[`../archive/2026-Q2/business-profile-context-enrichment-plan.md`](../archive/2026-Q2/business-profile-context-enrichment-plan.md)
(the enrichment idea, archived unbuilt; this is where it ships).

---

## 1. The problem, stated precisely

Activation for Duct is **the first verified finding delivered** — a number Duct
checked and disagreed with. Nothing before that moment is value; it is cost the
user pays on trust.

Today the cost is front-loaded and the value never arrives:

```
sign in → /insights/organic-growth → DeskDayOne checklist
       → /onboarding?new=1 → 5 screens, ~17 fields about yourself
       → "Save Project" → nothing happens
```

- `saveProjectFinal()` ([onboarding/page.jsx:331](../../app/src/app/%28app%29/onboarding/page.jsx#L331))
  saves and returns. No navigation, no next action.
- Every field is extraction (the user describing themselves to the model), not
  delivery. B2B evaluators tolerate that *after* proof, not before.
- The URL — the one input that could populate the other sixteen — is weight 1,
  optional, last on step 1.
- The connector, which DeskDayOne itself calls "the step that changes everything",
  is not in the wizard at all.
- Skip exists on steps 2–4 only (`step > 1 && step < TOTAL_STEPS`), so the
  highest-friction screen has no exit; skipping step 1 leaves step 2's selects
  `disabled` with an apology.
- "% complete" measures the user's remaining labour, not capability gained.

Meanwhile `/lead/seo-audit?url=…` runs a full audit for an anonymous stranger
from a URL alone. **The unauthenticated lead funnel has a better path to value
than the product.** This plan makes that path *the* product entry — on the
user's own model key, so the unit economics are the user's inference plus
Duct's crawl, and nothing else.

### What already exists (reuse, do not rebuild)

| Capability | Where | Used by onboarding today? |
|---|---|---|
| Unauthenticated audit session end-to-end | `app/src/app/(public)/lead/seo-audit/page.jsx`, `AuditWorkspace` | ❌ |
| Crawl with rich per-page signals (title, description, OG, schema, pillars…) | `agents/audit/crawl.py::run_crawl`, `PageSignals` — engine-neutral, no model needed | ❌ |
| Competitor research layered on the crawl | `agents/audit/enrichment.py::enrich_context` | ❌ |
| URL reachability pre-flight, SSRF-guarded, no auth | `routes/lead_magnet.py::check_url` | ❌ |
| Human-in-the-loop question in chat | `agents/core/session.py::bridge_ask_user_question` | ❌ |
| BYO provider keys: per-request headers, keychain on desktop, encrypted store server-side | `lib/providerKeys.js`, `set_provider_key` (Rust), `PUT /providers/{id}/key` | settings only |
| Key resolution with source attribution (`user` / `stored` / `env` / `cloud` / `subscription`) | `agents/engines.py::resolve_provider_key` — `subscription` is named in the docstring and never returned; §4 makes it real | ✅ (every run) |
| ChatGPT-subscription chat model + OAuth login, browser and device-code | `langchain_openai.chat_models.codex._ChatOpenAICodex`, `langchain_openai.chatgpt_oauth.login_chatgpt` / `login_chatgpt_device` — shipped in the pinned `langchain-openai` 1.6.0, experimental | ❌ |
| Tier resolver that already computes "which providers are reachable for this user" | `routes/providers.py::models_preview`, `agents/tiers.py` | **no run reads it** |
| Local project → backend push on sign-in | `lib/projects.js::hydrateProjectsFromBackend` | ✅ (the merge path) |
| Multi-provider identity per user | `models/auth.py::AuthIdentity` | Google only |
| System-browser OAuth for sign-in *and* connectors, via deep link | `desktop-auth`, `connectorAuth.js` | ✅ |
| Session resume after archive | `lib/auditResume.js` | ✅ |
| Execution upsell card | `components/audit/ExecutionOffer.jsx` | ✅ |
| Members + email invitations | `lib/membersApi.js`, `models/membership.py` | ✅ |
| Analytics + crash reporting behind a provider seam | `lib/analytics/`, `instrumentation-client.ts` | events only — **no identity call exists** |

The work is wiring and deletion. The genuinely new pieces: the guest user (§5),
a real key probe (§4), the crawl prefetch (§3), and the project-draft events from
the audit runner (§6).

---

## 2. Decisions taken

Step numbers throughout this document follow §3: **1** URL · **2** provider ·
**3** session · **4** report · **5** share · **6** intros. The launch screen is
step 0.

### The flow

| Decision | Choice | Why |
|---|---|---|
| Who pays for inference | **The user.** Step 2 connects a provider before anything runs on a model. Duct pays for the crawl only. | Unit economics from minute one. The lead magnet's `duct_pays` path is separate and unchanged. |
| Which provider to recommend | **ChatGPT sign-in on desktop** — the user's existing Plus/Pro plan, via the Codex OAuth that `langchain-openai` 1.6 ships. **API key** as the second option, and the only option on the web. | Most users already pay for ChatGPT. `_ChatOpenAICodex` + `login_chatgpt()` are in the pinned dependency today; OpenAI's stated position is "use Codex and your subscription wherever you like". Anthropic banned the equivalent on 2026-04-04, so this is OpenAI-only. §4 has the trust boundary. |
| When the key fails | **Diagnose, then allow skip.** Skip opens step 3 with the project already drafted from the crawl and a "connect a model to start" card in place of the first turn. | A failed key must not be a dead end; the crawl has already produced something worth landing on. §4 has the failure table. |
| When sign-in happens | **After the report** — at the connector (step 4) or the share (step 5), whichever comes first. Never before the URL. | Everything before the report is stateless; the account is a side-effect of getting value. |
| First connector | **Bundled with Google sign-in** — GSC + GA4 read scopes in the same consent. | One browser round-trip returns the user signed in *with* a data source. Declining the scopes still signs them in. |
| First share | **Read-only report link.** Invite offered after. | `inviteMember` grants the whole project — too much for a first B2B share. |

### Identity and storage

| Decision | Choice | Why |
|---|---|---|
| How a guest's work persists | **A real `users` row** with `AuthIdentity(provider="guest")`, linked or merged on sign-in (§5). | Every owning table is `NOT NULL` on its owner. A real user keeps every auth boundary intact and gives the provider key a place to live before sign-in. |
| "Sign up with ChatGPT" | **Identity hint now, login later.** The Codex OAuth id_token carries `chatgpt_account_id`, `chatgpt_user_id`, `plan_type` and (scope `email`) the address; step 2 writes them to `AuthIdentity(provider="openai")` on the guest and pre-fills the account. The provider is the issuer (`auth.openai.com`), not the product — the same row an official "Sign in with ChatGPT" would land on later. Real sign-in stays Google until OpenAI's partner programme opens. | That token's audience is the Codex client, not Duct — accepting it *as* authentication is audience confusion. As a link key it is safe: when a Google sign-in arrives with the same email, the merge is automatic. Official "Sign in with ChatGPT" is a six-partner beta (2026-08-02) with no open programme. |

### Scope

| Decision | Choice | Why |
|---|---|---|
| The audit run reads the tier map | **Yes** — the first agent run to do so (§4). | Today a run takes its provider from the instance default; a user holding only an OpenAI key gets a 402. Step 2 is meaningless until this is fixed. |
| Old wizard | **Deleted** (§9). Project context becomes a settings surface pre-filled with provenance. | It is the thing this plan replaces. |

---

## 3. The flow

```
 0  Launch        "Sign in"  |  "Audit my site"            (same screen on web (auth)/page.js)
                                   │  silently mints a guest (§5)
 1  URL           one field → check-url → favicon + title + description back in <1s
                  "Found it — Acme, 'meal planning for busy families.' Right?"      ← the draft project, and the first reward
                  ▶ crawl prefetch starts NOW, in the background (no model needed)   ← §3.1
 2  Provider      "Continue with ChatGPT" (desktop, your existing plan)  |  "Use an API key"   ← §4
                  verify (real call) → confetti  |  diagnose → fix steps  |  skip
 3  Session       AuditWorkspace opens with the crawl already done: "I've read 14 pages of acme.com."
                  enrich → synthesise on the user's key. Runner emits PROJECT_DRAFT (§6).
                  No key (skipped)? The session shows the "connect a model to start" card; the project is already drafted.
 4  Report lands  contextual (not timed) prompt: "Sign in with Google to pull Search Console into this."
                  → sign-in + GSC/GA4 scopes, one round-trip → property pick if needed → agent reassesses (resume, not new run)
 5  Share         "Send this to whoever owns the number" → read-only link (sign-in if still guest); invite offered after
 6  Intros        Execution ("Duct can fix these") on ExecutionOffer; nav intro. One at a time, on triggers, dismissal per user.
```

### 3.1 Crawl prefetch — the step-2 wait is the crawl's budget

Today the crawl runs inside `run_pipeline`, after the key is resolved. Step 2
takes the user 30–90 s; the crawl takes ~30 s; running them serially wastes the
one wait the user is willing to sit through. So the crawl detaches:

```
POST /api/audit/prefetch   { url }  →  { crawl_id, draft: {…} }      (guest token; no provider key needed)
```

- Runs `run_crawl` (already engine-neutral, plain HTTP), caches the `CrawlResult`
  in-process keyed by `crawl_id` with a 15-minute TTL — long enough for the
  provider step, short enough that nothing needs a table.
- Returns the deterministic project draft (§6, layer 1) in the response. No SSE
  needed for it; the URL screen renders the confirmation from this payload.
- `run_pipeline` gains `crawl_id: str | None`. Present and live → skip
  `run_crawl`; expired or missing → crawl as today. Nothing else in the runner
  changes; the key is still resolved at session start exactly as now.
- The background-tasks tray (§8) shows it: *"Reading acme.com… 9 of 14 pages."*

### Sign-in touchpoints, in order of preference

1. **Connector** (step 4) — the Google sign-in *is* the GSC/GA4 grant.
2. **Share / invite** (step 5) — "Sign in to send this."
3. **Account drawer** — a persistent, quiet *"Guest — save your work"* row. Not an
   overlay; nothing may fight the report for attention.
4. **Relaunch, day 2+** — "Your Acme audit is still here — sign in to keep it."
   Said once, kindly. The guest JWT lives in webview storage; a cleared cache loses it.

### Prompt discipline

Steps 4–6 stack four prompts in one session. Rules, enforced in one place
(`lib/onboardingPrompts.js`, a small state machine, not four components each
deciding for themselves):

- At most **one** prompt visible at a time.
- Each has a **trigger**, never a timer: connector on dwell-after-scroll-end *or*
  on the first question the agent cannot answer without data; share after the
  connector prompt resolves (accepted, declined, or dismissed); execution intro on
  the first `EXECUTION_PROPOSED` event; nav intro on first navigation away.
- Dismissal is **per user, server-side** (`user_preferences`), so a returning user
  never sees one twice on a second device.
- The prompt surface is the chat-input bottom sheet shape from `SplitWorkspace` —
  non-blocking, never covers the artifact.

---

## 4. The provider step

### The prerequisite nobody can skip

An audit run resolves its provider from the instance default —
`resolve_engine_provider(engine, cfg.generate_provider)` at
[agents.py:1182](../../backend/routes/agents.py#L1182) — and only then looks for a
key. A user who connects OpenAI on a Google-default instance is asked for a
Google key and gets a 402. The tier map from `/settings/models` was built to
answer "which provider can this user actually run on", and
[`model-routing-ux-design.html`](model-routing-ux-design.html) §10 records that no
agent run reads it yet.

**This plan makes the audit route the first reader.** Provider and model for the
run come from `resolve_tier_model(job=AUDIT, reachable=…)`, where *reachable* is
computed the way `models_preview` already computes it — request headers, stored
keys, and server env only where `allow_server_provider_keys()` says so. Connect
OpenAI, run on OpenAI. This is the smallest possible slice of the "agents read
the tier map" task, and onboarding is the reason to cut it now.

### The screen — two paths

**Path A — "Continue with ChatGPT" (desktop only, recommended).** Uses the
plan the user already pays for. Copy: *"Runs on your ChatGPT Plus or Pro plan —
no API key, no extra bill. Duct never sees your ChatGPT password or history."*
Offered only when `get_shell_info().capabilities.chatgptAuth` is true; the web
app shows path B alone.

**Path B — "Use an API key".** The `PROVIDERS` list from `lib/providerKeys.js`,
OpenAI first. Copy: *"Paste an OpenAI API key. Duct runs on your account, so an
audit costs you cents."* Console link inline.

### Path A's trust boundary — the refresh token never leaves the machine

The Codex OAuth token is not an API key. It is the user's ChatGPT account:
conversation history, workspace, everything. So the rule is the one API keys
already follow — per-request header, never stored on Duct's servers — applied
one level stricter:

| Build | Who runs the OAuth | Where the refresh token lives | What the backend receives |
|---|---|---|---|
| Downloaded desktop (thin shell → hosted API) | The **Rust shell**: `login_chatgpt`'s flow re-implemented in the shell (PKCE, loopback callback, same Codex client id), because the backend is on Railway and cannot bind the user's `localhost:1455`. | OS keychain, beside the provider keys (`KEYCHAIN_SERVICE`). The shell refreshes it. | The short-lived **access token** in the existing `X-Provider-OpenAI` header — a JWT (`eyJ…`) is told from an `sk-…` key by prefix, the way the Anthropic header already tells a key from an OAuth token — plus one new `X-OpenAI-Account-Id` header. The backend builds `_ChatOpenAICodex` with a token provider that returns exactly those two values and never refreshes. |
| Self-host / sidecar | The **sidecar** itself, `login_chatgpt()` with a keychain-backed `_ChatGPTOAuthTokenProvider` (the Protocol is public; the file store is only the default). | OS keychain. | Nothing — it is local. |

The subscription is not a new provider. It is a second credential kind for
`Provider.OPENAI`, and `ProviderKey.source` is the discriminator:
`resolve_provider_key` returns `ProviderKey(source="subscription")` when the
`X-Provider-OpenAI` value is a JWT, which the docstring already promises and no
code path delivers. `billed_to_duct` is already false for it. Because the
provider stays `openai`, the tier map, the reachable-set computation and
`resolve_tier_model` need no changes at all.

Consequences, stated so nobody rediscovers them:

- **No background jobs on the subscription in the thin shell.** Nightly checks
  and consolidation have no request to carry a header and no refresh token to
  mint one. They need a stored API key; the settings page says so where the
  schedule is enabled.
- **`PUT /providers/openai/key` refuses a JWT.** There is no key to remember,
  and storing the refresh token server-side would be exactly the credential
  pooling OpenAI calls a grey area.
- **The `originator` header is `duct`.** Set once in the backend, honest about
  who is calling. If OpenAI ever gates by originator, the verify step's
  `subscription_blocked` row (below) is the fallback, not a spoofed header.
- **Identity.** The id_token's `chatgpt_account_id` / `chatgpt_user_id` /
  `plan_type` / email go to `AuthIdentity(provider="openai")` on the guest —
  the link key from §2, never the login.

**Path B storage:** desktop → `set_provider_key` (keychain, works with no
account); web → `sessionStorage`; and, because a guest is a real user, **also**
`PUT /providers/{id}/key` so the key survives a refresh and a device switch.
`absorb_guest` (§5) carries `provider_keys` across a merge. The key is sent as
`X-Provider-*` on the verify call and on the session create, exactly as every
run does today.

### Verify — a real call, or it is not a verification

New endpoint, the one thing here that must not be faked:

```
POST /api/providers/{id}/verify     headers: X-Provider-*     →  { ok, model, latency_ms }  |  { ok: false, code, fix }
```

One minimal completion on the cheapest model the tier map names for that
provider. `models_preview` cannot do this — it resolves, it never calls. Cost is
a fraction of a cent, on the user's key.

The failure taxonomy is the whole value of the screen. Each `code` maps to a fix
the user can act on, with the vendor's page linked:

| `code` | What actually happened | Fix shown |
|---|---|---|
| `invalid_key` | 401 | "Keys start with `sk-`. Copy it again from the console — it's shown only once." |
| `no_billing` | OpenAI `insufficient_quota`, Anthropic `credit balance too low` — **the most common failure on a fresh account** | "This account has no credit. Add $5 at billing → try again." |
| `model_access` | 403 / 404 on the model — tier or org-verification gate | "Your account can't use `<model>` yet. Duct will use `<fallback>` instead." (auto-downgrade via `resolve_fallback_models`, then re-verify) |
| `rate_limited` | 429 | "Try again in a moment." (auto-retry once) |
| `unreachable` | network / proxy / DNS | "Can't reach `api.openai.com`. Corporate proxy? Duct respects `HTTPS_PROXY`." |
| `subscription_quota` | 429 from `chatgpt.com/backend-api/codex` — the five-hour window is spent (Plus: 15–80 GPT-5.5 messages), or the known third-party 429 (openai-python #2951) | "Your ChatGPT plan's window is used up — resets at `<time>`. Use an API key to keep going, or wait." |
| `subscription_revoked` | refresh fails; the user signed out of ChatGPT or revoked the app | "Sign in with ChatGPT again." (re-runs the shell flow) |
| `subscription_blocked` | the Codex backend rejects the `originator` or the account's plan — OpenAI changed the rules | "ChatGPT sign-in isn't available for this account right now. Use an API key." Duct-side kill switch: `CHATGPT_AUTH_ENABLED=false` hides path A. |
| `unknown` | anything else | the raw vendor message, verbatim, plus "Skip for now" |

Success → confetti, once, brief. Keep the report landing's celebration bigger —
peak-end rule; the key is a chore, the report is the peak.

### Skip — a state, not an error

"Skip for now" opens the session (step 3) with everything the crawl already
produced: the drafted project, the page list, the tray showing the crawl done.
The agent cannot run, so instead of a 402 the session renders a
`ProviderRequiredCard` where the first assistant turn would be: *"I've read 14
pages of acme.com and I'm ready. Connect a model and I'll start."* — with the
same provider control inline. `ProviderKeyRequired` already arrives as a 402
with the provider in it; no client handles it today, so this card is also the
generic handler every other agent surface gets for free.

---

## 5. The guest user

### Why not nullable owners

`Project.user_id`, `AgentConversation.project_id`, `Artifact.project_id`,
`ProjectMember.user_id` are all `NOT NULL`. That is *why* anonymous audits are
"fully ephemeral" ([agents.py:1007](../../backend/routes/agents.py#L1007)) — nothing
is written. Loosening any of them means every route in
`test_route_auth_boundaries.py` grows a "no owner" branch, and the membership
non-negotiable stops being one rule.

### What a guest is

A real `users` row and a real JWT. Nothing downstream can tell the difference,
which is the point — including the provider-key store, which is what lets step 2
remember a key for someone who has no account yet.

```
POST /api/auth/guest        body: { install_id }         (desktop: from get_shell_info; web: a generated, stored uuid)
  → users(email = f"guest+{install_id}@guest.getduct.ai")
  → auth_identities(provider="guest", provider_user_id=install_id)
  → normal access token
```

Idempotent on `install_id`: relaunching the app resumes the same guest.

### Linking on sign-in

The Google callback ([auth.py:385](../../backend/routes/auth.py#L385)) gains one
branch, keyed on the guest token the client presents alongside the OAuth state:

| Google email state | Action | User id afterwards |
|---|---|---|
| Unknown | **Link.** Add `AuthIdentity(google)` to the guest row, replace the email, drop the guest identity. | unchanged |
| Already a user | **Merge.** In one transaction: reassign the guest's `projects`, `project_members`, `artifacts.user_id`, `user_preferences`, `provider_keys` to the existing user; delete the guest (cascade removes nothing that was moved). Re-identify telemetry with the surviving id. | the existing user's |

Merge is the case that bites if it is not designed in. It is one service function,
`service/auth.py::absorb_guest(db, guest_id, into_user_id)`, with a test for
each table it touches, so a table added later fails the test instead of orphaning
rows.

### Hygiene

- **Sweep:** guests with no non-guest identity and `created_at < now − 30d` are
  deleted nightly; cascade removes their projects and their stored keys. A
  scheduled job, not a migration.
- **Cost exposure:** none for inference — every run spends the user's key. The
  crawl and the prefetch cache are Duct's; `check-url`'s rate limit extends to
  `/audit/prefetch`, per guest.
- **Route auth:** nothing changes. A guest *is* a member of their own project.

---

## 6. Project draft from the audit

### Two layers, two confidence levels

**Layer 1 — after the crawl. Deterministic, free, instant.** Returned by
`/audit/prefetch` (§3.1) and, when a session crawls for itself, emitted as
`PROJECT_DRAFT` by the runner. From `PageSignals` and the crawl plan, no model
call:

| Project field | Source | Provenance |
|---|---|---|
| `name`, `company_name` | `og:site_name` → root `<title>` (site-name segment) | `crawl` |
| `pitch` | root `meta_description` → `og_description` | `crawl` |
| `url` | `plan.root_url` (post-redirect) | `crawl` |
| favicon | `<link rel=icon>` (extend `extract_signals`, one field) | `crawl` |
| `content_pillars` | `_extract_brand_pillars` | `crawl` |
| `brand_channels.active_channels` | social profile links in `external_links` | `crawl` |

This is what the skip path (§4) has, and it is enough for a project to exist.

**Layer 2 — after enrichment. Inferred, on the user's key.** The runner gets one
flag, `draft_project: bool`; when set, the second `PROJECT_DRAFT` carries:

| Project field | Source | Provenance |
|---|---|---|
| `industry`, `business_model` | **classified** against `get_project_config` option lists — a Light-tier call with the allowed values in the prompt, output constrained to them | `inferred` |
| `competition.competitors[]`, `compare_against` | `research_context.competitors` | `inferred` |
| `audience.personas[]` | new `EnrichmentOutput.personas` (≤2) | `inferred` |
| `brand_channels.brand_voice` | new `EnrichmentOutput.brand_voice`, from the existing `BRAND_VOICES` list | `inferred` |

`enrich_context` already returns competitors, content gaps and notes; the
personas and voice ride the same research pass — no extra call. Today
`wants_research` is false for empty business context; a draft run has *only* the
URL, so the gate becomes `draft_project or (the existing condition)` and the
research prompt takes the crawl's own signals as its business context. Same
security posture as now: web tools only, no writers, the H2 text it interpolates
is already treated as attacker-authored.

**Never inferred:** `targets.north_star_metric`, goal window, growth stage. The
agent asks these in chat via `build_ask_user_tool` when a finding needs them
("Which of these matters more to you right now — signups or demo requests?"),
and writes the answer to project memory with provenance `user`.

### Client side

`lib/projectDraft.js` merges each layer into the active project (`saveProject`
+ `pushProjectToBackend`, which is now a real write because a guest is a real
user). Every inferred field carries `{ value, provenance }`; the project-context
surface (§9) renders provenance chips and a one-click *confirm*, the same chips
the memory timeline already draws.

---

## 7. Telemetry identity

Nothing sets identity today. Add to the seam, never to a page:

- `lib/analytics/index.js::identify(userId)` — GTM provider sets `user_id`;
  `none` provider no-ops. Called on guest creation, on link (same id, harmless),
  on merge (new id). Gated on consent exactly as `trackEvent` is.
- Crash reporter: `setUser({ id })` in `instrumentation-client.ts` behind the same
  provider seam — **id only, never email**.
- Desktop `telemetry/` mirrors both.

Funnel events, all `trackEvent`, with the missing GTM triggers added at the same
time or the funnel stays unmeasured: `onboarding_start`, `onboarding_url_ok`,
`onboarding_url_failed{reason}`, `provider_verify{provider, ok, code}`,
`provider_skipped`, `audit_report_ready{ms}`, `prompt_shown{kind}`,
`prompt_accepted{kind}`, `prompt_dismissed{kind}`, `guest_linked`, `guest_merged`.

`provider_verify{code}` is the one to watch first: if `no_billing` dominates, the
step-2 copy leads with "add credit before you start", not after.

---

## 8. Background tasks tray

The crawl prefetch is the first thing that runs while the user is somewhere
else. Next: project enrichment after they navigate away, then nightly checks and
execution runs. So this is not an onboarding component: it is a generic
`BackgroundTasks` tray in the shell footer, fed by a small store any agent can
post to (`{ id, label, progress?, state }`), rendered non-modally, with a
single-line delight budget (*"Read 14 pages of acme.com — found 3 competitors"*).
Onboarding is its first client, not its owner.

---

## 9. Removing the old wizard

Delete `app/src/app/(app)/onboarding/` and everything that only existed for it.
The wizard was also the project *editor*, so that role moves to a real surface:

**New:** `/project/[projectId]` becomes **Project context** — the same fields,
one scrollable page, pre-filled from the draft, provenance chip + *confirm* on
every inferred field, section anchors instead of steps. No progress bar; the
header says what Duct can now do (*"Can answer 6 of 9 question types"*).
`getProjectCompletion` in `lib/projects.js` stays as its data source.

**Rewire** (every current reference, so nothing 404s):

| File | Today | After |
|---|---|---|
| `(app)/project/[projectId]/page.jsx:5` | `redirect('/onboarding?project_id=')` | *is* the Project context page |
| `(app)/projects/page.jsx:102-105` | "Start by completing onboarding" → `/onboarding?new=1` | "Audit a site to start a project" → `/start` |
| `(app)/project/[projectId]/members/page.jsx:35` | link to `/onboarding?project_id=` | link to `/project/[id]` |
| `components/content/BrandContextForm.jsx:168` | link to `/onboarding?project_id=` | link to `/project/[id]#brand` |
| `components/insights/desk/DeskDayOne.jsx:121` | "Create a project" → `/onboarding?new=1` | "Audit a site" → `/start` |
| `components/commands/AppCommands.jsx:93-95` | command → `/onboarding?new=1` | command → `/start` |
| `components/AppNav.jsx:33` | `onboarding: "Onboarding"` label | `start: "Get started"`, `project: "Project context"` |
| `app/styles/generate.css:28-60` | `.onboarding-progress-shell`, `.onboarding-actions` | delete |
| `app/styles/connections.css:1` | comment mentions onboarding | fix comment |
| `(app)/audit/seo/page.jsx:94`, `(app)/content/page.jsx:109` | comments only | fix comments |
| `app/src/app/preview/catalogue.jsx` | wizard preview entry, if any | replace with `/start`, provider step and Project context previews |

`lib/projects.js:158` keeps its "deliberate save points" comment with the new
save point named.

---

## 10. Phases

Each phase ships on its own and leaves the app better than it found it.

**Built (2026-09-08):** Phase 1 in full (`POST /auth/guest`, link + merge in
the Google callback, `absorb_guest` walking the schema, the 30-day sweep
function — its nightly schedule is not wired). Phase 2 in full (the audit
route resolves through `resolve_job_run`; `POST /providers/{id}/verify`;
`ProviderRequiredCard` on the session route for the skip path — the generic
402 handler for other agents is not). Phase 3 in full (`/start`, prefetch with
the layer-1 draft and background crawl, `draft_project` with both layers,
`lib/projectDraft.js`, the aqueduct strip). From Phase 4: the guest row in the
sidebar and a sign-in that passes the guest's link code. Analytics events
exist; their GTM triggers do not. Phase 0 was skipped — the wizard is no
longer the entry, so its dead end is unreachable from onboarding.

**Built (2026-09-08, second pass):** Phase 2b — the shell runs the ChatGPT
OAuth (`desktop/src-tauri/src/chatgpt.rs`), the access token rides as the
OpenAI credential with the account id beside it, `resolve_chat_model` sends
it to `_ChatOpenAICodex`, the three `subscription_*` verify codes, the
`CHATGPT_AUTH_ENABLED` kill switch, a ChatGPT tile on the Models page. The
sidecar variant in the table above is **not** a separate path: the shell's
flow serves both builds, and the operator file store stays only for a
backend someone logged into by hand. The identity hint
(`AuthIdentity(provider="openai")`) is not written — "Sign up with ChatGPT"
was deferred, and the hint exists for nothing else. Phase 5 — Project context
at `/project/[id]` (the wizard's sections, provenance chips with one-click
confirm, section anchors), every §9 rewire, `/onboarding` deleted with its
CSS. From Phase 4 — the contextual connector prompt is the audit agent
mounting the insights agent's `RequestConnection`, asked for Search Console
once after the report on the onboarding audit; the share link is
`/open/audit/<conversation>?p=<project>` (membership-gated by the backend,
nothing public) with a Share dialog on the report that is the guest's
sign-in moment; `/start` redesigned as the threshold split. Analytics gained
`audit_shared`.

**Built (third pass):** the bundled GSC/GA4 scopes on sign-in, scoped to the
one stage they were designed for. The connector prompt on the onboarding
audit, when the user is a guest and the source is Search Console or
Analytics, becomes "Sign in with Google to connect": it parks the way back
(`/open/audit/<conversation>?kickoff=sources`), arms the bundle
(`lib/signInSources.js`, ten-minute expiry, consumed by the sign-in page at
the moment it builds the authorize URL) and sends the guest through the
ordinary sign-in page with `?sources=onboarding`. The backend asks for the
two *read* scopes with an offline grant and forced consent, and after the
account exists stores one `connector_credentials` row per scope Google
actually granted — declining both is a complete sign-in with nothing stored
(`service/signin_sources.py`; the upsert is shared with the Connections page
via `service/connector_store.py`). Back in the conversation the resume
opens by asking the agent to list the sources and bind the property, which
is the honest form of "reassess": the audit agent has no Search Console
reader, so the gain shows on the next insight run. Every other sign-in
(Share dialog, invitation, login page) and every connector flow on the
Connections page is untouched, and the bundle can never carry a write scope
(`tests/test_signin_sources.py` guards both).

**Fixed (fourth pass) — the returning user's project.** `/start` merged the
crawl's draft into `getActiveProject()`, so a signed-in user auditing any
site rewrote whichever project they had open: name, pitch, industry,
personas, competitors. The provenance guards did not stop it, because they
only protect a field whose provenance is recorded and every project made
before drafts existed has none. Three changes, and the first matters most
because it protects the *right* project too:

  1. `mergeDraft` treats a non-empty field with no recorded provenance as the
     user's. The placeholder name is excluded, or a new project would keep it
     forever.
  2. `projectsForSite()` resolves by website — lowercase host, `www.`
     stripped, subdomains kept apart — and `applyProjectDraft` uses it
     instead of the active project when no caller names one.
  3. `/start` writes nothing until the site card is confirmed. It hydrates
     first (a signed-in user on a new machine has an empty local store and
     would match nothing), then says which project this becomes, offers a
     separate one, and asks when two projects share the site. A guest sees
     none of it, having no projects.

The audit that follows says so again from the workspace, because that write
lands while the user is reading the report — `CornerNotice`, dismissible,
linking to the project.

**Not built:** the prompt state machine, Phase 6 (tray, intros, day-2
nudge), GTM triggers for every onboarding event. Provenance is kept
client-side only — `toApi` in `lib/projectsApi.js` does not send it — so a
second device sees the drafted values without their chips.

**Phase 0 — stop the bleeding (hours).** Route `saveProjectFinal` to the desk with
the first audit queued; skip on every step; "% complete" → capability copy; the
GTM triggers for the existing four `trackEvent` calls. This is the only phase
that touches the old wizard, and only so it stops losing users while the rest is
built.

**Phase 1 — guest user + identity.** `POST /auth/guest`, link + merge in the
Google callback, `absorb_guest` with per-table tests, the sweep job, `identify()`
on both telemetry seams. Nothing user-visible yet; everything after depends on it.

**Phase 2 — the run reads the tier map + verify.** The audit route resolves
provider and model through `resolve_tier_model` over reachable keys;
`POST /providers/{id}/verify` with the failure taxonomy; the `ProviderRequiredCard`
as the client's 402 handler. Independent of onboarding and valuable on its own —
today a user with only an OpenAI key on a Google-default instance cannot run
anything.

**Phase 2b — ChatGPT sign-in.** The shell-side OAuth (PKCE + loopback, Codex
client id) storing to the keychain; the JWT in `X-Provider-OpenAI` with prefix
detection, plus `X-OpenAI-Account-Id`; `_ChatOpenAICodex` behind a header-backed token provider in the
backend; `source="subscription"` in `resolve_provider_key`; the sidecar variant
on `login_chatgpt()`; the three `subscription_*` verify codes and the kill
switch. Gated behind `capabilities.chatgptAuth` so an older shell simply shows
path B.

**Phase 3 — `/start`.** The `(public)/start` route: URL screen → provider step →
`AuditWorkspace`. `check-url` returning title / description / favicon /
`is_spa_suspected` / bot-wall; `/audit/prefetch` with the cache and layer-1
draft; `draft_project=true` and the layer-2 emit; `lib/projectDraft.js`. Launch
screen on desktop *and* the web `(auth)/page.js`. **This is the phase that moves
activation.**

**Phase 4 — deferred sign-in.** Google sign-in with GSC/GA4 incremental scopes,
the contextual connector prompt, reassess-by-resume, read-only report link,
share prompt, the prompt state machine, the account-drawer guest row.

**Phase 5 — delete the wizard.** Project context page, the §9 rewires, delete the
route and its CSS.

**Phase 6 — polish.** Background tasks tray, execution and nav intros, the
day-2 relaunch nudge, the two celebrations.

---

## 11. Frictions this plan does not remove (known, accepted)

- **The Codex backend has no SLA.** `chatgpt.com/backend-api/codex` is
  undocumented, LangChain marks its client experimental, and OpenAI's blessing
  is a quote, not a contract. Path A can stop working on a Tuesday. The
  `subscription_blocked` row, the kill switch and path B are the whole
  mitigation; there is no cleverer one.
- **A fresh OpenAI account has no credit.** The verify step catches it and says
  what to do, but the user still leaves for a billing page and comes back. The
  `provider_verify{code}` event tells us how often; if it is most of them, the
  step-2 copy leads with it. Path A makes this the minority case on desktop.
- **Bot walls and CSR-only apps** crawl thin or not at all. `check-url` says so
  at step 1, before the wait — honest, not delightful.
- **Gatekeeper / SmartScreen** on first launch is outside the product; the site's
  download page pre-empts it.
- **The prefetch cache is in-process.** A multi-replica API loses it on an
  unlucky hop and the session simply crawls again — slower, never wrong. Move it
  to the database only if the miss rate says so.

---

## 12. Non-goals

- No Duct-funded runs anywhere in this flow. The lead magnet keeps its own.
- No official "Sign in with ChatGPT" as *login* until OpenAI opens the
  programme. No Claude-subscription route at all — Anthropic closed it on
  2026-04-04 and the Messages API rejects `sk-ant-oat`.
- No demo / seeded project. The user's own site is the demo.
- No changes to the audit's report content or template — this plan changes what
  happens *around* the audit, not the audit.
