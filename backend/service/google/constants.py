"""Google Ads service constants (connector id matches ``data/<id>/`` demo layout)."""

from __future__ import annotations

from pathlib import Path

GOOGLE_ADS_CONNECTOR_ID = "google_ads"

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
GOOGLE_ADS_DATA_DIR = _BACKEND_ROOT / "data" / GOOGLE_ADS_CONNECTOR_ID
