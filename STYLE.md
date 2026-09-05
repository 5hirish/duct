# Duct style guide

The `AGENTS.md` files say what must not break. This file says what good code
looks like once it works.

It is organised around the principles this codebase is built on: **modularity,
reusability, readability, commenting, deliberate error handling, named
constants over magic strings, and recognisable design patterns.** None of
these are aspirations — each section cites the code that already embodies the
principle, with measured adoption where it could be measured. Where the tree
falls short, the gap is named in [Known gaps](#known-gaps--close-on-touch) so
it gets closed on touch instead of rediscovered.

The bar is: **a reader who has never seen this file should be able to tell
what it guarantees, and why, without opening another one.** Code whose shape
is predictable makes the next change cost what the last one cost; code that
drifts makes every future change more expensive than the one before it.

Rules here are defaults with reasons, not law. When the code in front of you
disagrees with this file, take the better path and say so in the PR — a
convention that no longer matches the code should be fixed here, not worked
around silently. The [non-negotiables in `AGENTS.md`](AGENTS.md#non-negotiables)
are the exception: those are enforced by tests, and a red test is not an
invitation to negotiate.

---

## Modularity — layers with one-way dependencies

The repo is organised into structured modules with a strict downward
dependency direction, and the important boundaries are enforced by tests, not
by this document.

**Backend** (`backend/`) is a four-layer stack:

```
routes/   → HTTP shape, dependency injection, HTTPException
service/  → domain logic, vendor adapters, access checks
agents/   → prompts/tools/schemas (plain Python) + versioned runners (adapters)
models/   → SQLModel tables + portable column types
utils/    → stdlib-only leaf modules
```

Routes import `service`/`models`/`agents`; `service` imports `models`/`utils`;
`utils` imports nothing but stdlib. `routes/activity.py` is the smallest
complete example of the shape; `routes/artifacts.py` is the reference route
module. Two boundaries are machine-checked: framework imports outside the
adapter allowlist (`tests/test_harness_boundaries.py`) and auth dependencies
on every mounted route (`tests/test_route_auth_boundaries.py`).

**App** (`app/src/`) is three layers: `app/` (pages) → `components/` (feature
folders + `ui/` primitives) → `lib/` (pure logic and fetch wrappers). `lib/`
never imports `components/`; `components/` never imports `app/`. Keep it that
way — a `lib/` module that needs a component is a component in the wrong
folder.

**One concern per module.** A module that needs section banners to stay
navigable is usually asking to be split. Banners (`# --- Name ---`) are used
sparingly in a handful of long modules (`service/membership.py`,
`agents/registry.py`, `lib/format.js`); treat them as a smell worth noticing,
not a house style to imitate.

**Domain code stays framework-free.** The full declaration lives in
`agents/core/ports/__init__.py`. Tool bodies, prompts, schemas and scoring are
plain Python; framework imports live only in runners and binders.
`agents/core/memory_tools.py` is the reference shape — `_remember_sync` /
`_search_sync` hold the logic, `build_memory_tools_lc` /
`build_memory_tools_sdk` are thin binders over it.

---

## Reusability — the shared helper comes first

Every shared module in this repo exists because divergent local copies had
already drifted, and each one says so in its docstring:

- `backend/utils/dates.py` — replaced 23 private `_utcnow()` definitions.
- `backend/service/rest.py` — replaced five hand-rolled retry loops that
  disagreed on whether a 204 is a success.
- `backend/models/columns.py` — `json_column()` / `utc_datetime()`; the
  `_UTCDateTime` docstring names the desktop sign-in bug that motivated it.
- `backend/agents/core/lc.py` — the LangChain adapter every V1 runner shares.
- `backend/service/artifact_store.py` — one persistence path, per-agent
  adapters.
- `app/src/lib/format.js` — every card was growing its own `fmtDate`, and the
  copies disagreed on what "just now" meant.
- `app/src/lib/sse.js`, `lib/authFetch.js`,
  `components/workspace/agentPhase.js` — same story, each documented in place.

So the discipline is:

1. **Check the shared helper before writing a local one.** The area
   `AGENTS.md` lists them; so does the module docstring of anything in
   `utils/` or `lib/`.
2. **Extract on the second copy, not the first.** One implementation is a
   guess; `agents/core/lc.py` was extracted when insights became the second V1
   runner, and that is the model. The same rule governs adapters — do not
   abstract until the second concrete implementation exists.
3. **Extend the helper when it almost fits**, rather than forking it. A
   per-vendor deviation in `service/rest.py` is a one-line override
   (`service/stripe/client.py` starts backoff at 1s), not a copied loop.

**Not everything with the same name is a duplicate.** The four module-private
`_serialize` functions in `routes/` and the eight per-vendor
`require_credentials` functions are a *convention* — same name, same role,
different row or vendor. Do not consolidate them into a generic helper; the
genericity would cost more than the repetition.

---

## Named constants — a string used twice gets a name

Raw string literals are fine as human-facing text. They are not fine as
**config values, status vocabularies, storage keys, dispatch keys, or
anything compared with `==`** — a typo'd literal fails silently, and a
vocabulary spelled inline in five files cannot be renamed safely.

Where a value should live:

- **Settings** — a field on `Configs` in `backend/config.py`, never a bare
  `os.environ` read (and a new field means updating `.env.example`;
  `tests/test_env_example.py` will remind you). Every field carries a comment
  saying why it exists.
- **Status/kind vocabularies** — a `StrEnum` next to the model or schema that
  owns it. The tree has 56 of them; `agents/models.py` (providers/models) and
  `agents/core/events.py` (stream events) are the hubs. When the strings cross
  the wire, say so where the enum is defined — `events.py` opens with *"the
  string values are a contract with the frontend… never change an existing
  value; only add new members."*
- **Frontend mirrors** — a constants module in `lib/` (`contentEnums.js`,
  `auditEvents.js`, `agentSteps.js`) mirroring the backend enum, with a
  pointer back to it.
- **Storage keys** — a named export beside the accessor. This rule is fully
  honoured today: 26 of 26 `localStorage` call sites go through a constant.
  Never hardcode `"duct_auth_token"`; `lib/authFetch.js` owns it.
- **HTTP statuses** — the named `HTTP_404_NOT_FOUND`-style constants from
  `fastapi.status`, not bare integers. (Today 404 is almost always named and
  422 never is; prefer named for new code.)
- **Tunables** — a module-level constant with a comment carrying the reason,
  like `_TOKEN_BYTES = 32` in `service/membership.py`, whose comment explains
  the threat model rather than restating the number.

When you touch a line that spells out a literal which already has a named home
— a connector id, a post status, an execution state — switch it to the
constant as part of the change. The specific offenders are listed in
[Known gaps](#known-gaps--close-on-touch).

---

## Error handling — typed at the boundary, explained when broad

**Backend.**

- **`HTTPException` is raised where the decision is made.** Mostly a route;
  deliberately also five service modules (`service/auth.py`,
  `service/membership.py`, `service/credentials.py` and the credential
  resolvers), because the 404-not-403 rule for non-members has to be
  impossible to get wrong at a call site. `get_project_for_user`'s docstring
  is the canonical statement of why. Elsewhere, return a value and let the
  route decide.
- **External APIs get a typed error hierarchy.** `service/rest.py::ApiError`
  is the base — it carries `status`, `body`, `url`, and two overridable hooks:
  `parse()` (vendor envelope → one line) and `hint()` (what the operator
  should do). A new connector subclasses it in ~6 lines
  (`service/stripe/client.py` is the model) and writes **no transport code** —
  retry, backoff and rate-limit pacing live in `rest.py` alone.
- **Vendor SDKs are translated at the boundary.** The Google clients catch
  `GoogleAdsException` and re-raise stdlib types
  (`raise RuntimeError(...) from exc` — `service/google/fetch.py`).
  `service/execution/registry.py` states the executor contract: `ValueError`
  for bad input (→ 422), `RuntimeError` for upstream failure.
- **One global handler, for the one error that isn't a bug:**
  `ProviderKeyRequired` → 402 with a structured body so the browser can open
  the right provider tile (`server.py`).
- **Broad `except Exception` needs its reason on the same line.** The good
  instances say why the failure is survivable —
  `# noqa: BLE001 — summary is best-effort sugar` (`routes/artifacts.py`). A
  bare `except Exception: pass` with no comment is the anti-pattern; the tree
  still has a handful (see Known gaps) and should not grow more.

**App.**

- **Requests that must succeed** throw with the server's `detail` and attach
  `.status` to the error — `lib/authFetch.js::authedRequest` is the one
  implementation, and its comment explains why callers need the status (a 401
  is a different problem from a 400, with a different fix). New `lib/*Api.js`
  modules call `authedRequest`; they do not re-implement it.
- **Requests that are optional degrade to a falsy default** so the UI never
  becomes unusable over sugar — `fetchEngineStatus` returns `{}` on failure
  and says why in a comment (`lib/api.js`).
- **Browser storage access is always wrapped in `try`/`catch`** and degrades
  to a default, with the cause named in a comment ("private mode / storage
  disabled — the session lasts this page load"). Private windows throw on
  access; an unguarded read takes the page down rather than losing a
  preference.

---

## Comments and docstrings — write down the why

Comment generously, but make every comment carry information the code cannot:
the constraint, the contract, the failure that motivated the line, the
counterfactual that was rejected. A comment restating the line below it is
the one kind that is worse than nothing, because it trains readers to skip
comments.

The shapes that work here, each with a live example:

- **A constant explained by its threat model** (`service/membership.py`):

  ```python
  # Length of the raw invitation token before URL-safe encoding. 32 bytes gives a
  # 43-character token — far past guessing range for a link that also expires.
  _TOKEN_BYTES = 32
  ```

- **A config field explaining a platform constraint you cannot see from the
  code** (`config.py` — why two Google OAuth clients exist and are not
  interchangeable).
- **A file-top comment naming the trap, not the contents**
  (`lib/authFetch.js`):

  ```js
  // Reads BASE and the API key at call time — the desktop shell repoints both at
  // boot (lib/localBackend.js), so callers must never copy them into constants.
  ```

- **A design decision defended with its counterfactual** (`lib/desk.js` — why
  buckets are keyed by "who is holding it" and what topic-based cards broke).

**Docstrings are prose contracts, not section templates.** 94% of backend
modules open with a docstring (first line: what the module is for; body: the
invariant it holds). Public functions get one when the name under-specifies —
a one-liner for the contract's edge, a paragraph when the reader needs the
reason:

```python
def generate_invitation_token() -> tuple[str, str]:
    """Return ``(plaintext, sha256_hash)``. Only the hash is ever persisted."""
```

`Args:`/`Returns:` sections are an anti-convention — there are two in the
entire backend, and they should not multiply. The type annotations already
carry the mechanics; the docstring's job is what the types cannot say.

In the app, exported `lib/` functions get a one-line JSDoc wherever the
signature under-specifies: `/** Claims from a JWT without verifying it —
display only, never a trust decision. */`

**When you delete code, record the consequence that is no longer obvious**,
not the fact of removal — git already has that. The engine removals in
`backend/AGENTS.md` are the model.

---

## Readability — naming and shape

**Name the constraint, not the mechanism.** `get_project_row_for_user` reads
the project off the row; `check_access` would not have told you that. Where a
name can mislead, the docstring corrects it in one line.

**Backend naming:** `snake_case`, verb-first, with consistent prefixes —
`resolve_*` for choosing among sources, `build_*` for constructing,
`fetch_*`/`list_*` for reads, `_serialize` for the route-local row shaper.
Module-private names take a leading underscore; promotion to public is a
deliberate edit that also adds a docstring.

**App naming:** `lib/` files are `camelCase.js` with meaningful suffixes —
`*Api.js` (backend fetch wrapper), `*Events.js` (SSE vocabulary mirror),
`*Enums.js` (backend enum mirror). Components are `PascalCase.jsx`, one per
file, in feature folders. `components/ui/` is vendored shadcn in
kebab-case `.tsx`; the two hand-written primitives (`lightbox.jsx`,
`spinner.jsx`) follow the app's own style — that split is intentional.

**Exports:** `lib/` exports are named (0 default exports across 59 files);
components export default plus named sub-exports. Follow whichever side of
the line you are on.

**Mechanical conventions, near-universally held:**

- `from __future__ import annotations` is the first import in every backend
  module (99%).
- Imports group stdlib → third-party → local, blank line between groups,
  alphabetised within. Ruff will not correct you; nothing else will either.
- Public functions carry return types (97%). `-> str | None` is the contract;
  the name is only a hint.
- Optional and boolean parameters go keyword-only when a call site would
  otherwise read `f(row, 3, True)`.
- `"use client"` is line 1 of the file, before the file comment — it must be
  the first statement.

---

## Design patterns — extend the shape that exists

The codebase already uses a small set of named patterns. Before inventing a
new shape, check whether the change is another instance of one of these — the
third instance of an existing pattern is cheap, the first instance of a new
one is not:

- **Registry** — a dict from key to spec, with a loader that guarantees
  completeness: `service/connectors.py::CONNECTOR_REGISTRY` (+
  `load_connectors()`, which exists because import side effects left the
  registry incomplete), `agents/registry.py::AGENT_REGISTRY`,
  `service/execution/registry.py::EXECUTOR_REGISTRY`.
- **Protocol (structural typing)** at boundaries —
  `service/connectors.py::ConnectorAdapter`, and the `Emitter` / `ToolBinder`
  / `AskUser` ports in `agents/core/ports/__init__.py`, all
  `@runtime_checkable`.
- **Strategy** — `ExecutorSpec(preview, apply, rollback)`: one op type, three
  callables of identical signature.
- **Adapter + template method** around vendor APIs — `Endpoint` plus an
  `ApiError` subclass overriding `parse()`/`hint()`.
- **Ports & adapters (binder/runner split)** for agent harnesses — logic in
  plain functions, one thin binder per framework. Written on the second
  implementation, never the first.
- **Dependency injection** via FastAPI `Depends`, composed at the router
  level: `routes/namespace.py` bundles `APP_AND_USER`; `routes/content.py`
  declares `get_current_user` on the router so an endpoint cannot be written
  without it.
- **Factory functions** where each use needs its own instance —
  `json_column()`, `utc_datetime()`, the lazy `_*_spec()` builders in
  `agents/registry.py`, `@lru_cache get_configs()`.
- **React composition** — `SplitWorkspace` takes `left`/`right` as plain
  nodes (no render props, no triggers to wire); `AgentChat` takes the
  agent-specific parts as slots (`renderSteps`, `headerExtra`, copy) over one
  shared transcript; the `(app)/layout.js` provider stack; `CommandRegistry`'s
  mount/unmount contribution model so no central file has to import half the
  app.
- **Reducer + hook** — `lib/agentSession.js` is the agent session as a pure
  reducer (no React, replayable against recorded streams in tests);
  `hooks/useAgentSession.js` owns only the effects. State transitions that
  can be tested without a browser should be written so they can be.

When you add an instance, name the pattern in the module docstring — the word
"registry" or "adapter" in the first line tells the next reader which contract
they can assume.

---

## The static site (`site/`)

`site/` is hand-written HTML with two shared stylesheets and a handful of
vanilla scripts. No build step, no package manager, no framework — that is
the product decision, not a stage it has not reached. Do not bring modules,
JSX, or a dependency into `site/`.

Most of what governs a page here is invariants enforced by
`.github/scripts/check-pages.py` in CI — the `<head>` checklist, canonical
form, asset order, GTM placement — and they live in
[`site/AGENTS.md`](site/AGENTS.md). Read that first. What CI cannot check:

- `<meta name="description">` is 140–160 characters; `og:description` and
  `twitter:description` 120–140.
- Every page carries JSON-LD — `WebPage` for a landing page, `CollectionPage`
  for the blog index, `Article` for a post.
- Page-specific CSS goes in an inline `<style>` at the end of `<head>`, never
  into `assets/duct.css` — that file is shared by every page.
- JavaScript stays vanilla and conservative. `config.js` loads before
  `duct.js` because it defines the `DUCT_CONFIG` that `duct.js` reads.
- Never hardcode the GTM ID in JavaScript — read `DUCT_CONFIG.gtm`. The
  `<noscript>` iframe is the one exception, since it cannot run JS.

---

## Known gaps — close on touch

Measured against the principles above, these are the places the tree
currently falls short. Do not fix them in a sweep; fix each one when a change
already touches the line, and shrink this list in the same PR.

- **The connector id vocabulary is spelled as literals in five parallel
  places** — `service/pipeline.py` (three literal sets),
  `agents/insights/catalog/base.py`, `service/connectors.py`,
  `app/src/lib/api.js`, `app/src/lib/executionApi.js` — while
  `service/google/constants.py::GOOGLE_ADS_CONNECTOR_ID` sits unused beside
  them. New connector ids get a constant; touched literals switch to it.
- **`ContentStatus` (`agents/content/schema.py`) documents itself as
  mandatory and is barely used** — `routes/content.py` and
  `agents/content/tools.py` still assign `"posted"` / `"scheduled"` inline.
- **The execution state machine compares inline tuples**
  (`routes/execution.py`, `service/execution/service.py`) although
  `models/execution.py` defines the status sets; the frontend mirror in
  `lib/desk.js` compares bare strings too.
- **`block_type` is a `Literal[...]` on the backend and a bare `switch` in
  `InsightBlock.jsx`** — neither side has a named constant, so the ten-way
  contract exists only as spelling.
- **`"audit_seo"` appears as a bare literal in five frontend files** while
  its siblings have constants (`AGENT_TYPE`, `INSIGHTS_AGENT`) and the
  backend has `AgentType.SEO_AUDIT`.
- **Three `lib/*Api.js` modules re-implement `authedRequest`** —
  `executionApi.js`, `memoryApi.js`, `membersApi.js` are near-byte-identical
  copies of the helper that `deskApi.js` / `connectorsApi.js` /
  `artifactsApi.js` correctly import.
- **`utils/dates.utcnow()` is only ~54% adopted** — `routes/content.py` alone
  has 12 direct `datetime.now(timezone.utc)` calls. The substance holds
  (there is not one naive datetime in the tree — keep it that way), but the
  helper is the named home; use it in new code and switch touched lines.
- **A handful of bare `except Exception: pass` with no reason** —
  `service/crawl/extractor.py`, `agents/core/session.py`,
  `utils/helpers.py`. Broad catches are fine; unexplained ones are not.
- **`utils/helpers.py` misses three conventions at once** (no module
  docstring, no `from __future__`, an unexplained bare except). Do not copy
  it; fix it when touched.
- **`lib/api.js` predates the error convention** — it throws from raw
  response text and never attaches `.status`. New code follows the
  `authFetch.js` shape; migrate `api.js` call paths as they are touched.

---

## Before you call it done

**Attack your own diff.** Read it as though someone else wrote it and you are
looking for the reason to reject it. Most of what a reviewer would catch, the
author can catch first, and for free.

**Then check the diff against its neighbours.** Individually defensible
changes that together dissolve an architecture is the specific way
agent-accelerated codebases fail — each PR argues for itself and nothing
argues for the whole. Ask what the third change of this shape would do to the
module; if the answer is "we would need to reorganise", do it now, while it
is one file.

**Run the principles as a checklist over the diff:** does anything spell a
literal that has a named home? Does a local helper duplicate a shared one?
Does a broad catch explain itself? Did a touched line leave the Known-gaps
list one entry shorter?

The checks in `make check` are the floor, not the bar. They prove the change
did not break a rule someone already wrote down. They cannot tell you the
change was worth making.
