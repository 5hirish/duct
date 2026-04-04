# Duct Backend

This directory contains the Python reporting and synthesis side of Duct.

## What lives here now

- `service/` — connectors, Google Ads fetch/brief pipeline
- `data/<connector_id>/raw/demo_raw_payload.json` — static raw demo input (Google Ads)
- `utils/` — shared formatting and metric helpers
- `service/google/schema.py` — Google Ads brief payload types
- `data/google_ads/google-ads-report.json` — checked-in demo brief; `raw/` + `generated/` for input / API output

## Product role

This is the product core described in `docs/mvp/mvp-plan.md`.

- read from client-owned data destinations
- normalize data into stable internal payloads
- generate typed findings and actions
- render reports and briefs
- later deliver email briefs and Slack alerts

## Intended scope

- data ingestion helpers
- normalization
- signal generation
- synthesis
- report rendering
- delivery
- future orchestration

## Planned stack

- PyAirbyte early, client-managed Airbyte later
- DuckDB + Ibis
- dbt
- Dagster
- Claude API + Instructor
- Resend
- Slack webhooks
- Supabase for workspace/auth metadata

## Boundary

- Do not put static marketing site files here.
- Do not put future authenticated web app code here.
- Marketing lives in `site/`.
- Future product UI lives in `app/`.

## Production deploy

Railway + Railpack (Poetry) is the intended API host; pairing with the Next app on Cloudflare Workers is documented in [`docs/engineering/deployment-cloudflare-railway.md`](../docs/engineering/deployment-cloudflare-railway.md).

## Local guidance

- Cursor instructions: `backend/AGENTS.md`
- Claude Code instructions: `backend/CLAUDE.md`
