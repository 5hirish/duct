"""Google Ads service constants (connector id matches ``data/<id>/`` demo layout)."""

from __future__ import annotations

from pathlib import Path

GOOGLE_ADS_CONNECTOR_ID = "google_ads"
GA4_CONNECTOR_ID = "ga4"
GSC_CONNECTOR_ID = "gsc"
GTM_CONNECTOR_ID = "gtm"

# The read-only scopes, named here because two flows ask for them: each
# connector's own OAuth (`routes/auth.py`) and the onboarding sign-in bundle
# (`service/signin_sources.py`), which must request exactly the read half and
# never a connector's write scopes.
GSC_READ_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GA4_READ_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
GOOGLE_ADS_DATA_DIR = _BACKEND_ROOT / "data" / GOOGLE_ADS_CONNECTOR_ID
# Raw fetch-shaped demo input (not a brief; kept out of the app report list).
GOOGLE_ADS_RAW_PAYLOAD_PATH = GOOGLE_ADS_DATA_DIR / "raw" / "demo_raw_payload.json"
