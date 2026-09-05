# Duct App

The Next.js App Router frontend — sign-in, connectors, projects, and the agent
workspaces. Deploys to Cloudflare Workers via OpenNext, and is also what the
Tauri desktop shell loads.

Application code is JavaScript (`.js` / `.jsx`), not TypeScript. The exception is
`src/components/ui/`, the vendored shadcn/ui primitives, which ship as `.tsx` —
follow the surrounding file's language rather than converting either way.

## Surfaces

| Route | What it is |
|---|---|
| `/insights` | Insight briefs — list, detail, and the interactive generate flow |
| `/audit` | SEO audit workspace |
| `/content` | Content planner and studio |
| `/connections` | OAuth connector linking and account selection |
| `/projects`, `/project/[id]` | Projects, members, and per-project memory |
| `/execute` | Staged change sets — preview, approve, apply, roll back |
| `/memory` | Agent memory timeline |
| `/settings/models` | Heavy / Standard / Light model tier assignment |
| `/onboarding` | Business-context capture |

Agent workspaces share one shell — [`src/components/workspace/SplitWorkspace.jsx`](src/components/workspace/SplitWorkspace.jsx) (chat left, viewport
right, a CSS pane toggle on mobile). Compose it rather than re-forking the
split and responsive logic.

## Local run

```bash
npm install
npm run dev          # http://localhost:3003
```

Or `make serve-app` from the repo root.

Dev ports are pinned deliberately, not framework defaults, so they stay clear of
other local stacks: **Next 3003**, **FastAPI 8002**, **static site 8090**.

Against a local backend, set `API_PUBLIC_URL=http://localhost:8002` and
`FRONTEND_ORIGIN=http://localhost:3003` in `backend/.env.local` so OAuth
redirects and CORS line up. `NEXT_PUBLIC_API_BASE` should match the API origin;
`src/lib/api.js` already defaults to `http://localhost:8002` in dev.

If you set `NEXT_PUBLIC_APP_URL` for a local build, use `http://localhost:3003`
so `metadataBase` matches the dev origin.

## Environment

`NEXT_PUBLIC_*` variables are inlined into the client bundle **at build time**,
so changing one in a dashboard does nothing until the next build.

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE` | API origin |
| `NEXT_PUBLIC_DUCT_API_KEY` | App identity header — **not** an authorization boundary; it ships to the browser |
| `NEXT_PUBLIC_APP_URL`, `NEXT_PUBLIC_SITE_URL` | Absolute URLs for `metadataBase` |
| `NEXT_PUBLIC_GTM_ID` | Google Tag Manager container (optional) |
| `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_APP_ENV` | Error reporting (optional) |
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | Cloudflare Turnstile on sign-in (optional) |
| `NEXT_PUBLIC_SHELL_SCHEME` | Deep-link scheme when running inside the desktop shell |
| `NEXT_PUBLIC_CDN_IMAGE_RESIZING` | Cloudflare image resizing toggle |

## Checks

```bash
make check-app       # lint, typecheck, slide parity, build
```

`check:parity` guards a real coupling: the slide renderer here and
`templates.py` in the backend must agree, or a generated post previews
differently from how it publishes. `check:connectors`, `check:desk` and
`check:sources` are the other sanity scripts.

## Production

OpenNext + Wrangler live here (`wrangler.jsonc`, `open-next.config.ts`).
Deployment runs from CI on merge to `main` — do not deploy from a CLI.

- Local prod-like build: `npm run preview:cf`
- `npm run build` is plain Next; the Worker build is `opennextjs-cloudflare build`

## Boundaries

- Rendering lives here; synthesis lives in `backend/`. Do not move Python
  pipeline logic into this app, and do not render HTML in the backend.
- Do not assume a repo-adjacent `backend/data` tree exists at runtime. It does
  not on Workers — guard filesystem access and fail open.

Conventions: [`AGENTS.md`](AGENTS.md) (`CLAUDE.md` symlinks to it).
