# Duct Backend

This directory contains the Python reporting and synthesis side of Duct.

## What lives here now

- `scripts/` — report-generation entry points
- `briefs/` — typed schemas and prompt templates
- `reports/` — generated report artifacts

## Intended scope

- data ingestion helpers
- normalization
- signal generation
- synthesis
- report rendering
- delivery
- future orchestration

## Boundary

- Do not put static marketing site files here.
- Do not put future authenticated web app code here.
- Marketing lives in `site/`.
- Future product UI lives in `app/`.
