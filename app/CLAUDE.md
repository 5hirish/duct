# Duct App — Claude Code instructions

Next.js App Router report viewer and agent interface.

## Stack

- **Framework:** Next.js 16 App Router, React 19, TypeScript 6, Node 20 (dev runs on port 3003)
- **UI:** shadcn/ui + Radix UI primitives, Tailwind CSS 4, lucide-react, next-themes (light/dark)
- **Charts:** Nivo (heatmaps, complex) + Recharts (general) — both intentionally present
- **State:** React Context (`InsightContext.js`) + component-level state only. No Redux/Zustand.
- **HTTP:** Native `fetch` wrapped in `lib/api.js`. No type-safe client or OpenAPI generation.
- **Auth:** Custom API key (`NEXT_PUBLIC_DUCT_API_KEY`) sent to backend + Google Sign-In (`GoogleSignInButton.jsx`). No next-auth/Clerk/Supabase.
- **Observability:** Sentry (`@sentry/nextjs` — server, edge, client), Google Tag Manager (`NEXT_PUBLIC_GTM_ID`), Cloudflare Turnstile bot protection.

## Deployment

- **Host:** Cloudflare Workers via `@opennextjs/cloudflare` adapter + wrangler CLI.
- `npm run deploy:cf` → OpenNext build + `wrangler deploy` (do not run directly — all deploys go through CI/CD on merge to main).
- **CI:** GitHub Actions (`app.yml`) — lint, typecheck, `next build` on every PR and push to `main`.

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

## Key utilities

- `lib/api.js` — fetch wrapper for backend calls
- `lib/engines.js` — LLM engine/model selection
- `lib/insightData.js` — insight fetching and management
- `lib/localInsights.js` — client-side insight storage
- `lib/reports.js` — report generation helpers
- `lib/userPreferences.js` — preference persistence
- `lib/analytics-client.js` — analytics event wrapper

## What's not here

- No dedicated auth library (next-auth, Clerk, Supabase)
- No form library (React Hook Form, Formik)
- No global state library (Redux, Zustand, Jotai)
- No test suite (Jest, Vitest, Playwright) — E2E tests live in `site/`, not `app/`
- No Supabase anywhere in this project
