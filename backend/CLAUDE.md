# Duct Backend — Claude Code instructions

Python reporting and synthesis backend for Duct.

## Product role

Per `docs/mvp-plan.md`, this backend is the actual product engine:

- read from client-owned destinations with read-only access
- normalize data into typed internal models
- compute signals and comparisons
- synthesize findings into structured output
- render customer-facing delivery artifacts
- deliver via email and alerts

The web app is not the primary product surface. The backend is.

## MVP architecture

The current and planned backend stack is:

- **Ingestion:** PyAirbyte for early pilots, client-managed Airbyte later
- **Query layer:** DuckDB + Ibis
- **Transforms:** dbt
- **Orchestration:** Dagster
- **Synthesis:** Claude API + Instructor with typed models
- **Delivery:** Resend and Slack webhooks
- **Workspace/auth metadata:** Supabase

## Product-shape constraints

- Do not build a dashboard-first product here.
- The primary value is the brief and alert output.
- The backend should support a thin onboarding app, not depend on a rich frontend.
- Design all outputs for operator clarity: what changed, why it matters, what to do next.

## Current directory structure

- `scripts/` — MVP entry points
- `briefs/schemas/` — typed internal and output schemas
- `briefs/templates/` — prompt contracts and brief templates
- `reports/` — generated artifacts and debug outputs

## Code design rules

- Normalize first, synthesize second.
- Keep typed schemas central and explicit.
- Keep renderers downstream of normalized payloads, not raw source data.
- Separate ingestion, normalization, synthesis, rendering, and delivery concerns.
- Prefer extensible evidence models so future tools can enrich the same findings.

## Sequencing rules from the plans

- Validate the brief/report shape before building heavy automation.
- Start with one customer, one tool, one brief/report end-to-end.
- Add connectors and orchestration only after the output format is useful.
- Add real-time anomaly detection after the scheduled brief flow works.

## What not to build yet

- no custom auth in backend
- no full Airbyte platform management
- no heavyweight job system beyond the planned orchestration layer
- no broad dashboard experience
- no complex cross-tool logic before the single-source MVP is producing useful output
