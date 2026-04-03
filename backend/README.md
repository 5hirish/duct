# Duct Backend

This directory contains the Python reporting and synthesis side of Duct.

## What lives here now

- `scripts/` — report-generation entry points
- `briefs/` — typed schemas and prompt templates
- `reports/` — generated report artifacts

## Product role

This is the product core described in `docs/mvp-plan.md`.

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

## Local guidance

- Cursor instructions: `backend/AGENTS.md`
- Claude Code instructions: `backend/CLAUDE.md`
