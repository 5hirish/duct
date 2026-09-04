# Duct App — agent instructions

Next.js App Router report viewer and agent interface.

## Stack

- **Framework:** Next.js 16 App Router, React 19, TypeScript 6, Node 22 (pinned in `app/.nvmrc` — the OpenNext/wrangler toolchain requires ≥22; dev runs on port 3003)
- **UI:** shadcn/ui + Radix UI primitives, Tailwind CSS 4, lucide-react, next-themes (light/dark)
- **Charts:** Nivo (heatmaps, complex) + Recharts (general) — both intentionally present
- **State:** React Context (`InsightContext.js`) + component-level state only. No Redux/Zustand.
- **HTTP:** Native `fetch` wrapped in `lib/api.js`. No type-safe client or OpenAPI generation.
- **Auth:** Custom API key (`NEXT_PUBLIC_DUCT_API_KEY`) sent to backend + Google Sign-In (`GoogleSignInButton.jsx`). No next-auth/Clerk/Supabase.
- **Observability:** Sentry (`@sentry/nextjs` — server, edge, client), Google Tag Manager (`NEXT_PUBLIC_GTM_ID`), Cloudflare Turnstile bot protection.

## Deployment

- **Host:** Cloudflare Workers via `@opennextjs/cloudflare` adapter + wrangler CLI.
- `npm run deploy:cf` → OpenNext build + `wrangler deploy` (do not run directly — all deploys go through CI/CD on merge to main).
- **CI/CD:** GitHub Actions (`app.yml`) — lint, typecheck, `next build` on every PR; on push to `main` the `deploy` job runs `opennextjs-cloudflare build` + `wrangler deploy`. (Replaced the Cloudflare "Workers Builds" git integration, which failed on its Node 20 builder — wrangler@4.99 needs ≥22.)

## Route structure

Two route groups under `app/`:

- `(auth)/` — login page
- `(app)/` — authenticated app shell:
  - `audit/` + `audit/[sessionId]/` — general audit reports
  - `audit/seo/` + `audit/seo/[sessionId]/` — SEO audit variant
  - `connections/` — connector/integration management
  - `generate/` — report generation workflow
  - `insights/` + `insights/[slug]/` + `insights/generate/` — insights hub
  - `insights/organic-growth/` + `[slug]/` + `generate/` — organic growth insights
  - `onboarding/` — new user setup
  - `projects/` + `project/[projectId]/` — project management
  - `project/[projectId]/members/` — project members + invitations (owner/collaborator)

Plus `invite/[token]/` at the top level (outside every route group): the invitation landing page, which must render for signed-out recipients.

## Key utilities

- `lib/api.js` — fetch wrapper for backend calls
- `lib/membersApi.js` — project members + invitations (server-only; no localStorage mirror, unlike `lib/projects.js`)
- `lib/engines.js` — LLM engine/model selection
- `lib/insightData.js` — insight fetching and management
- `lib/localInsights.js` — client-side insight storage
- `lib/reports.js` — report generation helpers
- `lib/userPreferences.js` — preference persistence
- `lib/analytics-client.js` — analytics event wrapper
- `lib/format.js` — dates, numbers and labels: `relativeTime`, `relativeDays`,
  `formatDate`, `formatTime`, `toDate`, `dayKey`, `compactNumber`,
  `formatNumber`, `titleCase`, `formatTitle`, `capitalize`, `initials`.
  Use these instead of a component-local `fmtDate`/`fmtNum`/`prettify` — the
  per-component copies had drifted apart before they were consolidated.
- `lib/sse.js` — `consumeSseStream` / `parseSseDataFrame`, shared by every
  streaming endpoint (audit, content, insights)
- `lib/authFetch.js` — the one home for the auth token: `AUTH_TOKEN_KEY`,
  `authToken`, `hasAuthToken`, `authedHeaders`, `authedRequest`, plus
  `decodeJwtPayload` / `isTokenValid`. Never hardcode `"duct_auth_token"`.

## UI conventions

Full reasoning in `docs/engineering/desktop-adaptive-ui-review.html` (in `duct`).

**[`DESIGN.md`](DESIGN.md) is the design & UX companion to this section** —
the look/feel/voice layer: design tokens as built, the canonical pattern per
job (cards, spinners, badges, empty/loading/error states, confirmations),
layout & density principles, microcopy voice, the anti-generated-UI
checklist, and a close-on-touch gap list. Read it before building or
restyling any screen. This section stays the home of the mechanical rules
below (sizing, units, CSS layout, accessibility).

Its **"Go and look"** section lists the reference builds to open in a browser
when a screen is off and the reason will not come — shadcn's components,
blocks, charts and typeset pages, which are the reference implementation of
the primitives we vendor. Compare a screenshot of the real thing against your
`/preview` frame; that is usually faster than reasoning from a stylesheet.

**Sizing: ask the container, not the window.** The viewport is the wrong ruler
here — the sidebar takes 16rem out of it, and the agent panes are user-resizable,
so `lg:` can be true while the box you are in is 300px. Each layout REGION
declares a container (`.app-main`, `.app-main-wide`, the full-bleed wrapper, both
`SplitWorkspace` panes), so components use `@`-variants and are correct wherever
they are placed.

- Content: `@container` variants on Tailwind's `@`-scale — `@md` 28rem, `@lg` 32rem,
  `@xl` 36rem, `@2xl` 42rem, `@4xl` 56rem. Roughly 224px per grid column.
- Viewport (`sm:`/`md:`/…) only for genuine device concerns: the sign-in page,
  the sidebar's mobile sheet, the pane toggle, and `md:text-sm` on chat inputs
  (which exists to stop iOS zooming a sub-16px field).
- No hand-picked pixel breakpoints. There are currently zero; keep it that way.
- Before adding `container-type` anywhere new: it implies `contain: layout`, which
  makes that element the containing block for `position: fixed` descendants.
  Overlays must be portalled (they are — see below) or they will shrink to it.

**Units.** Type, spacing and sticky offsets in `rem` so they follow the reader's
text size. Device units stay `px`: borders, outlines, shadows, radii, 1px optical
nudges. Prose gets `max-width: var(--measure)` (68ch) or the `.measure` utility —
never tables, code, or column layouts.

**CSS lives in `src/app/styles/`.** `globals.css` is a manifest of imports and
nothing else; order is load-bearing (see its header). Add a partial for a new
concern rather than growing an existing one, and put page-specific styling with
the page.

**Shared UI primitives — use them, don't re-fork.**

- Overlays: `ui/dialog` (Radix — portal, focus trap, Escape, scroll lock) and
  `ui/lightbox`. Never hand-roll a `fixed inset-0` backdrop.
- Busy state: `ui/spinner`. Colour comes from `currentColor`.
- Agent shells: `hooks/useAgentSession` (the session lifecycle),
  `workspace/AgentChat` (the transcript pane), `workspace/SplitWorkspace`
  (split + responsive), `PipelineProgress` (the working ladder),
  `workspace/CodeBlock`. See "Agent workspaces" below before touching any of
  them.
- Shortcuts: `lib/shortcuts`' `useShortcut("mod+k", fn)` — platform-neutral, owned
  by the surface that needs it.
- Commands: `useRegisterCommands` from `components/commands/CommandRegistry`. A
  route contributes its own commands and they withdraw on unmount.
- Navigation: `lib/navigation`'s `NAV_SECTIONS` is the single source of truth for
  the sidebar and the palette.

**Agent workspaces — one lifecycle, one chat pane, agent-specific slots.**

Three agents (content, audit, insights) share a session protocol: create,
stream, park on a pause, chat, reconnect, resume. That protocol lives in two
places and nowhere else:

- `lib/agentSession.js` — the pure reducer over the shared `AgentEvent`
  vocabulary (`lib/agentEvents.js`) and the `Phase` enum (`lib/agentPhase.js`).
  No React, no network. Tested by replaying recorded streams from
  `lib/__fixtures__/*.json` (`npm test`).
- `hooks/useAgentSession.js` — the effects: session creation with orphan
  cleanup, transcript hydration before the live stream, the reconnect loop
  (reattach to the live session, then resume the conversation), pause answers
  by `interrupt_id`, and the per-tab reload handle (`lib/agentSessionHandle.js`)
  that lets a reloaded tab reattach instead of re-running the prompt.

A workspace composes `useAgentSession` + `workspace/AgentChat` +
`workspace/SplitWorkspace` and keeps only what its agent owns: the right pane,
the events the reducer returns unchanged (a plan payload, an artifact version,
a slide render request) handled in `onEvent`, and the copy. Read
`components/content/ContentWorkspace.jsx` as the reference — it is the
shortest of the three.

To see it run without a backend: `npm run mock:agents` replays the fixtures
over SSE on :8012 (pausing where the real backend would), and
`scripts/smoke-agent-workspaces.mjs` drives all three workspaces through a
headless browser against it — pause, reload-and-reattach, answer, follow-up,
turn failure — and screenshots each state. Run it after touching the shell.

The shell borrows deliberately from harnesses built in the open.
[`docs/engineering/agent-harness-references.md`](../docs/engineering/agent-harness-references.md)
records which ones, at which revision, and the gaps they expose in ours (a
status row with elapsed time, typed error codes, queued follow-ups, context
left). Check it before adding a lifecycle feature — the answer is often
already pinned to a `file:line` there.

Rules that follow:

- **Do not fork the chat pane or the lifecycle.** A new agent gets a new
  workspace file of ~150 lines, not a new `*Chat.jsx`. Two forks of the chat
  had drifted 600 lines apart while rendering the same thing; a third had
  none of the fixes. That is the failure this structure exists to prevent.
- **A new pause is one entry in `workspace/PauseCard.jsx`.** The reducer, the
  hook and the backend route already carry any pause event that arrives with
  an `interrupt_id`; the card is the only agent-visible part.
- **A new protocol event goes in the reducer, with a fixture.** Agent-specific
  payloads stay in the workspace's `onEvent`.
- **Phases are the protocol, not a UI mood.** Only the reducer moves `phase`;
  a workspace that needs a different input policy passes `inputDisabled`
  rather than inventing a state. The default policy keeps the box open while
  the agent works or a card waits: a message then is *queued* (the row carries
  a mark until `user_input_consumed` releases it), not refused and not a new
  turn.
- **Failures are typed; copy comes from the code.** `friendlyErrorMessage(raw,
  code)` and `errorAction(code)` in `lib/agentSession.js` are the only places
  a failure becomes words or a button. A new failure kind is a new `ErrorCode`
  (mirrored from the backend) with a row in `ERROR_COPY`, never a regex on the
  message.
- **The status row says what is happening, with a clock.** While the agent
  works the header reads `Working · 1m 12s · Collecting source data` — phase,
  elapsed, and the step in progress (or "Reconnecting to the model (2/4)",
  "Compacting context"). The context ring beside it is `workspace/ContextRing`
  over the reducer's `usage`; it is the same ring the insights desk shows for
  a new thread.

**Accessibility.** Desktop keyboard and screen-reader basics, not a full audit.

- Every form control needs an accessible name. A `placeholder` is not one — it
  disappears on focus and is skipped by some readers. Use a visible `<label>`,
  or `aria-label` where the design has no room for one.
- Anything clickable is a `<button>`. A `<div onClick>` cannot be tabbed to or
  triggered with Enter/Space, and the focus ring comes free with the element.
  For a whole card, put the button on the title and stretch it with an
  `after:absolute after:inset-0` pseudo-element — one tab stop, one readable
  name, and the card stays a container.
- Live regions are rationed. The agent's phase label (`role="status"`) is the
  one in each chat shell; streaming tokens and the rotating `PipelineProgress`
  subtitle are deliberately silent, because announcing them talks over the user.
- `html { scroll-padding-top: 4rem }` in `styles/base.css` keeps a focused
  element out from under the sticky header (WCAG 2.2 AA 2.4.11).
- Decorative icons take `aria-hidden`; an icon-only button takes an `aria-label`.

**Look at it before you call it done.** CSS written and never rendered is a
guess, and guesses compound: three plausible-sounding rules in a row produce a
layout nobody would have drawn on purpose. If a change touches layout, spacing,
alignment or colour, render it and check — do not use the person reviewing the
PR as your renderer.

**Use `/preview`.** `src/app/preview/` is a dev-only route (404s in production,
no auth, no backend) that mounts one component at a time in the real app's CSS.
Add scenes to `preview/scenes.jsx`; pick a **surface** (in place, dialog, sheet,
drawer, alert, notification, page, toolbar) and a **device** (phone, iPad either
way up, desktop-min, desktop, wide), in light, dark, or both at once.

Two modes, because there are two jobs:

- **Working** — the workbench. Seed a component by adding a scene to
  `preview/scenes.jsx`: `{ id, group, title, state, note, render }`, importing
  the real component and passing real props. That is the whole API. Ad hoc and
  skewed to the last thing touched, which is correct for what it is for.
- **Design system** — the durable catalogue, in three sections:
  **Foundations** (`preview/system.jsx` — colour/type/shape via `TokenSheet`,
  spacing, icons), **Primitives** (same file — every `ui/*` part with its
  variants), and **Patterns** (`preview/catalogue.jsx` — one entry per row of
  DESIGN.md's canon table). Pattern rules are **parsed from DESIGN.md**
  (`preview/canon.js`), never retyped, so the screen cannot disagree with the
  doc. A rule with no example is listed as a **gap** and counted in the header,
  so coverage is a number rather than an impression.

Adding a canon row to DESIGN.md therefore adds a gap. Close it with an example,
or leave it visible; do not delete the row to make the count look better.

Frames **mount only when scrolled near** and the catalogue crops them to their
specimen. Both are load-bearing, not polish: each frame is a whole Next document
(app bundle, Sentry, HMR client), and 27 entries × 2 devices eagerly mounted is
not slow, it is `ERR_INSUFFICIENT_RESOURCES` and a half-loaded page. Keep the
lazy mount if you touch `Frame`.

`/preview/frame?scene=…&surface=…&theme=…` renders one scene alone, so any state
is reachable by URL with nothing to click, and every frame exposes
`window.__preview` — `measure`, `contrast`, `aligned`, `smallTargets`,
`unnamed`, `overflowing`, `typeScale`, `tokens`, `overlay`. Prefer those over
retyping measurement code; they answer the same question the same way twice.
Full detail in the `component-preview` skill.

**Lenses** are the third axis, after surface and device: a device changes what
the component is, a lens changes who is looking at it. All are URL parameters.

- `vision=protanopia|deuteranopia|tritanopia|greyscale` — colour-vision
  simulation. WCAG 1.4.1 says colour is never the only channel, and this is what
  makes that checkable instead of assumed: under `deuteranopia` the connected
  green dot and the partial amber one converge, which is why the word stays
  beside the dot.
- `text=125|150|200` — the reader's text size, as a percentage. Type and spacing
  are in `rem` by house rule precisely so they follow it, which is only worth
  anything if someone moves it. A layout that holds at 100% and collapses at
  150% has a `px` in it.
- `inspect=outline|spacing|grid` — debug paint. `grid` is the spacing scale
  drawn, in `rem`, so it stays in phase with the layout under the text lens.

The **`tokens` scene** is the palette as the app actually resolves it — every
semantic pair with its live contrast ratio, the colours used as ink on the page,
the type ladder and the radii. It is read from computed style, so it cannot
drift from `tokens.css`, and the value shown is the one after the cascade: open
it in a dark frame to see the dark half. Check a new or changed token here
before shipping it. It earned that on its first render, catching
`--destructive-foreground` missing from the `.dark` block — white on the lifted
coral, 2.89:1, where its three neighbours sat at 7.8–9.9.

The preview chrome is built from `ui/*` like anything else. It shipped once with
native `<select>`s, and a native `<select>` draws its option list in the OS: it
ignored every class on the element and rendered a system-font, system-light menu
over a dark app. A harness for judging our components must not be the one screen
that does not use them.

Scenes render in **iframes, not resized divs**: media queries read the viewport,
so a `<div style="width:390px">` answers the container question and silently
gets `sm:`/`md:`/`dvh` wrong. Each frame also sets `container-type`, so both
rulers are right at once.

Do **not** rebuild a component's markup in a scratch HTML file next to a copy of
its stylesheet. That is a replica, and replicas drift: the first one written
that way was missing Tailwind's preflight, measured every box 34px too wide, and
sent a correct layout back for a fix it did not need.

- **Render every state, not just the happy one.** Partial, empty, loading,
  failed, disabled, and a name long enough to wrap are where layouts break, and
  they are the ones nobody opens by accident. A long account name is what
  revealed a status row wrapping onto three lines.
- **Widths are container widths, not devices.** The `@`-scale boundaries the
  code branches on, and each frame declares `container-type` so the variants
  respond to the frame rather than the window. Frames drag-resize; sweep the
  448–720 band rather than sampling it.
- **Measure, do not squint.** `getBoundingClientRect()` answers alignment
  exactly, and answers questions eyes are bad at: two glyphs can share a
  vertical centre and still look wrong because their boxes are 7px and 24px with
  padding on only one. Assert what the guides make checkable — shared rails,
  equal slots, the 24×24 target floor, rows that must stay on one line,
  `getComputedStyle` proving a destructive action is tinted, not filled.
- **A component that fetches gets an injectable loader** with a real default
  (`loadEntities` on `ProjectEntitySelect`), so a scene can stub it. One
  optional prop beats a hand-copied render of the same markup.

**Full-app visual review is a different, heavier job — do it only when asked**,
or when the change is to a whole screen's composition rather than to a
component. Opening real screens needs a signed-in session and a live backend,
and it answers a question isolation cannot: whether the piece fits its
surroundings. In-place work does not need that question answered, and paying
for it every time is why "look at it" gets skipped.

## What's not here

- No dedicated auth library (next-auth, Clerk, Supabase)
- No form library (React Hook Form, Formik)
- No global state library (Redux, Zustand, Jotai)
- No test suite (Jest, Vitest, Playwright) — E2E tests live in `site/`, not `app/`.
  This rules out *committed* browser tests; it does not rule out driving a
  browser to look at what you just built. See "Look at it before you call it
  done" above — read as a blanket ban, this line is why UI arrives unrendered.
  `src/app/preview/` is not a test suite either: it is a route that renders
  components, with no runner, no assertions and no dependency.
- No Supabase anywhere in this project

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
