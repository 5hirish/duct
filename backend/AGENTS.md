# Duct Backend — Agent instructions

This directory contains the Python reporting and synthesis side of Duct.

## Role of the backend

- The backend is the product core.
- It reads data with read-only access.
- It normalizes source data into stable internal payloads.
- It generates typed findings and recommended actions.
- It renders deliverable outputs like reports, briefs, and alerts.

## Current scope

- `service/` — connectors and Google Ads fetch/brief
- `data/<connector_id>/` — static demo source payloads per connector
- `utils/` — formatting and metric helpers
- `service/google/schema.py` — Google Ads brief JSON contract (dataclasses)
- `data/google_ads/` — demo brief at root; `raw/` + `generated/` for fixtures / API output

## Architecture direction

- Keep the backend operator-first for MVP.
- Prefer deterministic normalization before LLM synthesis.
- Treat typed payloads and typed output schemas as core contracts.
- Design current work so more sources can enrich the same schema later.

## Constraints

- Do not mix static marketing site code into `backend/`.
- Do not assume a dashboard-first product shape.
- Keep the MVP lightweight and easy to iterate.
- Avoid adding infra-heavy systems before the brief format is validated.

## Near-term stack from the MVP plan

- ingestion: PyAirbyte early, client-managed Airbyte later
- query layer: DuckDB + Ibis
- transforms: dbt
- orchestration: Dagster
- synthesis: Claude API + Instructor / typed models
- delivery: Resend + Slack webhooks
- auth/workspace metadata: Supabase

## Working rules

- Preserve backward-compatible schema evolution where possible.
- Prefer small, inspectable JSON payloads over opaque pipeline steps.
- Keep rendering separate from ingestion and normalization.
- Optimize for one strong brief or report, not a broad dashboard.
