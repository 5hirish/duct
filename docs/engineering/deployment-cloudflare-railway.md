# Deployment: Cloudflare Workers (app) + Railway (backend)

Production shape for this monorepo:

- **[`app/`](../../app/)** — Next.js report viewer on **Cloudflare Workers** via [OpenNext for Cloudflare](https://opennext.js.org/cloudflare) (`@opennextjs/cloudflare`).
- **[`backend/`](../../backend/)** — FastAPI API on **Railway** using **Railpack + Poetry** (no Docker in `backend/` so Railway does not auto-pick a Dockerfile).

Official references:

- Cloudflare Workers + GitHub Actions: [External CI/CD](https://developers.cloudflare.com/workers/wrangler/ci-cd/) → [GitHub Actions](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/)
- Railway Git deploys: [GitHub autodeploys](https://docs.railway.com/guides/github-autodeploys)
- Railway config as code: [railway.toml / railway.json](https://docs.railway.com/reference/config-as-code)

---

## Architecture

```mermaid
flowchart LR
  subgraph cf [Cloudflare]
    Worker[duct-app_Worker_OpenNext]
    R2[(R2_duct-next-cache)]
    Worker --> R2
  end
  subgraph railway [Railway]
    API[FastAPI_uvicorn]
  end
  Browser --> Worker
  Worker -->|"NEXT_PUBLIC_API_BASE"| API
```

The browser loads the Worker. Client-side API calls use [`app/src/lib/api.js`](../../app/src/lib/api.js): `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000` in dev) must be the **public HTTPS URL** of the Railway service in production.

---

## Repo files (Cloudflare / OpenNext)

Already in the tree:

| File | Role |
|------|------|
| [`app/wrangler.jsonc`](../../app/wrangler.jsonc) | Worker name `duct-app`, `nodejs_compat`, assets binding, self-reference, R2 `NEXT_INC_CACHE_R2_BUCKET` → bucket name `duct-next-cache` |
| [`app/open-next.config.ts`](../../app/open-next.config.ts) | R2 incremental cache for OpenNext |
| [`app/package.json`](../../app/package.json) | `preview:cf`, `deploy:cf` scripts; devDependencies `@opennextjs/cloudflare`, `wrangler` |
| [`app/public/_headers`](../../app/public/_headers) | Long cache for `/_next/static/*` |

**R2:** Create bucket `duct-next-cache` in Cloudflare (or change `bucket_name` in `wrangler.jsonc` to match).

---

## Part 1 — Cloudflare Worker (manual or CI)

### One-off / local

From `app/`:

- `npm run preview:cf` — build + `wrangler dev`
- `npm run deploy:cf` — build + deploy

`wrangler login` for local auth.

### Worker environment

Configure in the Cloudflare dashboard (or Wrangler) for the Worker:

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_BASE` | Railway API URL (`https://…`) |
| `NEXT_PUBLIC_APP_URL` | Canonical app URL (`metadataBase` in [`app/src/app/layout.js`](../../app/src/app/layout.js)) |

Avoid `NEXT_PUBLIC_DUCT_API_KEY` in production if possible (key is exposed to every browser); prefer a server-side API proxy later ([`app/README.md`](../../app/README.md)).

**Build-time note:** `NEXT_PUBLIC_*` is inlined at **Next/OpenNext build time**. In **GitHub Actions**, pass these as `env` on the build step (or non-secret `vars` in `wrangler.jsonc` for safe values only).

### CORS

[`backend/config.py`](../../backend/config.py) — set `FRONTEND_ORIGIN` (env) to the deployed **Cloudflare app origin** (custom domain or `*.workers.dev`).

---

## Part 2 — Railway (API)

1. New Railway project → deploy from GitHub; **root directory** `backend`.
2. **No `Dockerfile`** under `backend/` — Railway [uses a Dockerfile if present](https://docs.railway.com/reference/config-as-code); without it, **Railpack** + Poetry applies to `pyproject.toml` / `poetry.lock`.
3. **Start command:** `poetry run uvicorn server:app --host 0.0.0.0 --port $PORT` (Railway sets `PORT`).
4. **Python:** match `>=3.11,<3.13` from [`backend/pyproject.toml`](../../backend/pyproject.toml) (e.g. 3.12 in Railway UI / docs).

### Railway environment

Mirror [`backend/config.py`](../../backend/config.py): `FRONTEND_ORIGIN`, `DUCT_API_KEY`, Google OAuth and Ads, LLM keys, etc. **`GOOGLE_OAUTH_REDIRECT_URI`** must use the **Railway public host** for the OAuth callback path you expose.

Ephemeral disk: `backend/data/` is not durable for multi-instance production; plan object storage or a DB if you scale beyond one instance.

### Optional: `railway.toml`

See [Config as code](https://docs.railway.com/reference/config-as-code). Example shape:

- `build.builder` = `RAILPACK` (explicit)
- `deploy.startCommand` = uvicorn command above
- `build.watchPatterns` relative to service root — e.g. `**/*.py`, `pyproject.toml`, `poetry.lock` so `app/` changes do not redeploy the API

---

## Part 3 — CI/CD (GitHub)

### Cloudflare: chosen approach — GitHub Actions

Use [`cloudflare/wrangler-action@v3`](https://github.com/cloudflare/wrangler-action) (not Cloudflare dashboard Git Builds for the same Worker, to avoid double deploys).

GitHub **repository secrets:**

- `CLOUDFLARE_API_TOKEN` — Workers + **R2** for the cache bucket
- `CLOUDFLARE_ACCOUNT_ID`

Workflow sketch:

1. `on.push` to default branch with `paths:` under `app/**` (and lockfile / `wrangler.jsonc` / `open-next.config.ts` as needed).
2. `actions/checkout@v4`, setup Node (match `app/package.json` `engines`).
3. In `app/`: `npm ci`, `npx opennextjs-cloudflare build`.
4. `wrangler-action` with `workingDirectory: app`, `apiToken`, `accountId` (default command deploys).

Docs: [GitHub Actions for Workers](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/).

### Railway: Git autodeploy

Connect the repo in Railway; pick the production branch. Optional **Wait for CI** ([doc](https://docs.railway.com/guides/github-autodeploys)) if a workflow runs on `push` to that branch — Railway waits for green GitHub checks.

**Deploy order:** Stand up Railway and a stable URL first, then set Worker `NEXT_PUBLIC_API_BASE` (and rebuild/redeploy the Worker if that URL changes).

### OAuth (Google Cloud Console)

When URLs are final, update authorized **redirect URIs** and **JavaScript origins** to match Railway + Cloudflare hosts.

---

## Out of scope for this stack

**Cloudflare Python Workers** for this FastAPI app: not a fit for `google-ads`, LangChain, and filesystem-backed `data/` without major rework. Keep the API on Railway.

---

## Checklist

- [ ] R2 bucket exists and matches `wrangler.jsonc`
- [ ] Railway service: root `backend`, Railpack, start command, env vars
- [ ] `FRONTEND_ORIGIN` = Cloudflare app URL; `NEXT_PUBLIC_API_BASE` = Railway URL
- [ ] Google OAuth redirect URI matches Railway
- [ ] GitHub secrets + workflow for Cloudflare (when you add `.github/workflows/…`)
- [ ] End-to-end: `/`, `/reports`, API calls from deployed app
