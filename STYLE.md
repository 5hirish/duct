# Duct style guide

The `AGENTS.md` files say what must not break. This file says what good code
looks like once it works.

**Why it is worth writing down now.** The old argument for careful code was
that a human would have to modify it later. That argument is weaker than it
was. The one that replaced it is cheaper to verify: an agent reads this
codebase on every task, and a codebase it can follow costs fewer tokens to
change correctly. Code whose shape is predictable makes the *next* change cost
what the last one cost. Code that drifts makes every future change more
expensive than the one before it — that is the whole bill, and it compounds
quietly.

So the bar is not beauty for its own sake. It is: **a reader who has never seen
this file should be able to tell what it guarantees, and why, without opening
another one.**

Rules here are defaults with reasons, not law. When the code in front of you
disagrees with this file, take the better path and say so in the PR — a
convention that no longer matches the code should be fixed here, not worked
around silently. The [non-negotiables in `AGENTS.md`](AGENTS.md#non-negotiables)
are the exception: those are enforced by tests, and a red test is not an
invitation to negotiate.

---

## Everywhere

**Comments carry reasoning, not description.** A comment restating the line
below it is noise. A comment naming the failure that motivated the line is why
the code survives the next refactor. If nothing went wrong to motivate a line,
it usually needs no comment.

```python
# Length of the raw invitation token before URL-safe encoding. 32 bytes gives a
# 43-character token — far past guessing range for a link that also expires.
_TOKEN_BYTES = 32
```

**Name the constraint, not the mechanism.** `get_project_row_for_user` reads
the project off the row; `check_access` would not have told you that. Where a
name can mislead, the docstring corrects it in one line.

**Reach for the shared helper before writing a local one.** Every helper module
in this repo exists because divergent local copies had already drifted:
`backend/utils/dates.py`, `backend/utils/strings.py`,
`backend/utils/formatting.py`, `backend/service/rest.py`,
`app/src/lib/format.js`, `app/src/lib/sse.js`, `app/src/lib/authFetch.js`. A
second copy of `fmtDate` is not a small duplication; it is the first half of a
bug that shows up months later in one of the two copies.

**Delete rather than deprecate.** Agent-accelerated work makes bloat the
default, so removal has to be a normal move rather than a special occasion.
Dead code that no route dispatches is not free — it is read, indexed and
reasoned about on every task. When you remove something, record the consequence
that is no longer obvious (see the engine removals in `backend/AGENTS.md`), not
the fact of removal, which git already has.

---

## Python (`backend/`)

Verified conventions, not aspirations — these hold across the tree today.

**Every module opens with a docstring** (98/98 in `routes/` and `service/`).
First line says what the module is for; the body states the invariant it holds
and links the plan or test that proves it.

```python
"""Artifact library endpoints — /api/user/artifacts (Bearer JWT).

Read/serve/delete for the versioned artifact store (models/artifact.py).
Every route is membership-checked through service.membership — content bytes
are served only here, never from a public URL.
"""
```

**`from __future__ import annotations` is the first import in every module.**
No exceptions in the tree; do not start one.

**Imports are grouped stdlib → third-party → local**, blank line between
groups; inside a group, plain `import x` before `from x import y`, each half
alphabetised. Ruff runs on its default rule set here and does not sort imports,
so nothing will correct you.

**Module-private names take a leading underscore** — `_serialize`,
`_get_readable`, `_TOKEN_BYTES`. If a helper is used by another module, it
loses the underscore and gains a docstring; that promotion should be a
deliberate edit, not a side effect.

**Public functions carry return types** (97% of them do). `-> str | None` is
the contract; the name is only a hint.

**Make optional and boolean parameters keyword-only** — `def _serialize(row, *,
version_count=None)`. This one is a judgment call rather than a house rule: only
about one function in eight uses it today. Reach for it when a call site would
otherwise read `f(row, 3, True)`, which tells the reader nothing.

**Docstrings state the contract and its edges**, not the mechanics:

```python
def generate_invitation_token() -> tuple[str, str]:
    """Return ``(plaintext, sha256_hash)``. Only the hash is ever persisted."""
```

**Timestamps come from `utils/dates.utcnow()`.** Never `datetime.now()` or
`datetime.utcnow()`. Naive datetimes compare and serialise differently on
SQLite (desktop sidecar) and Postgres (Railway), so this is a correctness rule
wearing a style rule's clothes.

**JSON columns use `models/columns.py::json_column()`.** Raw `postgresql.JSONB`
does not compile on SQLite, and the desktop build finds out at runtime.

**`HTTPException` is raised where the decision is made, not where the response
is written.** Mostly that is a route, but five service modules raise it too —
`service/auth.py`, `service/membership.py`, `service/credentials.py` and the two
credential resolvers. That is deliberate for access checks: the rule that a
non-member gets **404, not 403** (a 403 confirms the row exists) has to be
impossible to get wrong at a call site, so the helper raises rather than
returning a value each caller must remember to interpret. Elsewhere, prefer
returning a value and letting the route decide.

**Section banners (`# --- Name ---`) are used in two files and are not a
convention.** Do not add them to reach a house style that is not there; if a
module needs headings to be navigable, it probably needs splitting.

---

## JavaScript in the app (`app/`)

Everything in this section is about `app/` — React 19 on Next 16, ES modules,
JSX. **None of it applies to `site/`**, which is a different language with the
opposite constraints; that section is below.

**`lib/` exports are named. `components/` export default.** Zero default
exports across 59 files in `lib/`; components use a default export plus named
sub-exports where useful. Follow whichever side of that line you are on.

**A file-top comment names the trap, not the contents.** The valuable comment
is the one that stops the next edit from being wrong:

```js
// Shared fetch helper for user-scoped backend APIs (Bearer JWT + X-API-Key).
// Reads BASE and the API key at call time — the desktop shell repoints both at
// boot (lib/localBackend.js), so callers must never copy them into constants.
```

**Exported functions get a one-line JSDoc where the name can mislead.** Used
heavily in `lib/` (200+ occurrences) and worth the line every time it says
something the signature does not:

```js
/** Claims from a JWT without verifying it — display only, never a trust decision. */
```

**Never read configuration into a module-level constant.** The desktop shell
repoints the backend base URL and API key at boot. Read at call time.

**Browser storage access is wrapped in `try`/`catch` and degrades to a falsy
default** — 9 of the 10 `lib/` modules that touch `localStorage` do this.
Private windows and blocked site data throw on access, so an unguarded read
takes the page down rather than losing a preference.

**`"use client"` is the first line of the file when the component needs it** —
before the file comment, since it must be the first statement.

**No new state library.** React Context plus component state, as
`app/AGENTS.md` says. The absence of Redux/Zustand is a decision, not a gap.

---

## The static site (`site/`)

`site/` is hand-written HTML with two shared stylesheets and a handful of
vanilla scripts. There is no build step, no package manager and no framework,
and that is the product decision, not a stage it has not reached yet — so the
`app/` section above is not a lighter version of these rules, it is a different
set. Do not bring modules, JSX, or a dependency into `site/`.

Most of what governs a page here is not style at all: the `<head>` checklist,
canonical form, asset order and GTM placement are **invariants enforced by
`.github/scripts/check-pages.py` in CI**, and they live in
[`site/AGENTS.md`](site/AGENTS.md). Read that first. What follows is only the
part CI cannot check.

**`<meta name="description">` is 140–160 characters**; `og:description` and
`twitter:description` 120–140. CI checks only that a description exists, so the
length is on you.

**Every page carries JSON-LD** — `WebPage` for a landing page, `CollectionPage`
for the blog index, `Article` for a post (set dynamically by `blog/post.html`).

**Page-specific CSS goes in an inline `<style>` at the end of `<head>`**, never
into `assets/duct.css`. That file is shared by every page, so a one-page
override added to it is a change to all of them.

**JavaScript stays vanilla and conservative.** No frameworks, no bundler, no
`import`. `config.js` loads before `duct.js` because it defines the
`DUCT_CONFIG` that `duct.js` reads; `duct.js` is deferred and last.

**Never hardcode the GTM ID in JavaScript** — read `DUCT_CONFIG.gtm`. The
`<noscript>` iframe is the one exception, since it cannot run JS to look one up.
Leave the existing hardcoded IDs there alone.

---

## Before you call it done

**Attack your own diff.** Read it as though someone else wrote it and you are
looking for the reason to reject it. Most of what a reviewer would catch, the
author can catch first, and an agent asked to review its own diff catches more
than one asked to write carefully in the first place.

**Then check the diff against its neighbours.** Individually defensible changes
that together dissolve an architecture is the specific way agent-accelerated
codebases fail — each PR argues for itself and nothing argues for the whole.
Before merging, ask what the third change of this shape would do to the module.
If the answer is "we would need to reorganise", do that now, while it is one
file.

The checks in `make check` are the floor, not the bar. They prove the change
did not break a rule someone already wrote down. They cannot tell you the
change was worth making.
