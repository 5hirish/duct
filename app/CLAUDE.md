# Duct App — Claude Code instructions

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

## What's not here

- No dedicated auth library (next-auth, Clerk, Supabase)
- No form library (React Hook Form, Formik)
- No global state library (Redux, Zustand, Jotai)
- No test suite (Jest, Vitest, Playwright) — E2E tests live in `site/`, not `app/`
- No Supabase anywhere in this project

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
