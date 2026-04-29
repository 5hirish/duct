"""HubSpot query scaffold for future Ibis/DuckDB-backed tools."""

from __future__ import annotations

from typing import Any


def fetch_hubspot_contacts_summary(*, limit: int = 50) -> dict[str, Any]:
    """Placeholder query contract for agent tool integration.

    A future implementation should query the dlt-managed DuckDB dataset with Ibis,
    apply goal-specific filters, and return deterministic rows for synthesis.
    """
    return {
        "report_type": "hubspot_contacts_summary",
        "row_count": 0,
        "rows": [],
        "note": f"HubSpot scaffold only. Query pipeline not wired yet (requested limit={limit}).",
    }
