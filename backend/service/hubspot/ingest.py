"""HubSpot ingestion scaffold using dlt.

This file is intentionally lightweight and not wired into production flow yet.
It serves as the first implementation anchor for connector ingestion + DuckDB.
"""

from __future__ import annotations

from typing import Any

import dlt


@dlt.source(name="hubspot_source")
def hubspot_source(config: dict[str, Any]):
    """Minimal resource scaffold for future HubSpot ingestion."""

    @dlt.resource(name="contacts", write_disposition="replace")
    def contacts():
        for row in config.get("seed_contacts", []):
            yield row

    return contacts


def run_hubspot_ingest(config: dict[str, Any]) -> Any:
    """Run a local DuckDB pipeline for initial connector experiments."""
    pipeline = dlt.pipeline(
        pipeline_name="hubspot_ingest",
        destination="duckdb",
        dataset_name="hubspot_raw",
    )
    return pipeline.run(hubspot_source(config))
