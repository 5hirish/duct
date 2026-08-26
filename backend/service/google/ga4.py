"""Google Analytics 4 connector + supplementary fetch functions."""

from __future__ import annotations

from typing import Any

from google.oauth2.credentials import Credentials

from config import get_configs
from service.connectors import (
    CAP_ACCOUNTS,
    ConnectorAuthContext,
    ConnectorMeta,
    register_connector,
)
from service.google.constants import GA4_CONNECTOR_ID

_GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
# Requested on top of readonly at consent time so stored GA4 tokens can also
# drive the staged-execution GA4 admin executors (key events, audiences —
# service/execution/ga4_exec.py). Tokens minted before this change stay
# read-only until the user reconnects.
_GA4_EDIT_SCOPE = "https://www.googleapis.com/auth/analytics.edit"
_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _build_credentials(*, refresh_token: str, client_id: str, client_secret: str) -> Credentials:
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=_TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=[_GA4_SCOPE],
    )


class GA4Connector:
    """Interactive GA4 operations (property listing for account picker)."""

    def list_accounts(self, auth: ConnectorAuthContext) -> list[dict[str, Any]]:
        cfg = get_configs()
        refresh_token = (auth.refresh_token or "").strip()
        client_id = cfg.google_oauth_client_id or cfg.google_ads_client_id
        client_secret = cfg.google_oauth_client_secret or cfg.google_ads_client_secret

        gaps: list[str] = []
        if not refresh_token:
            gaps.append("refresh_token")
        if not client_id:
            gaps.append("GOOGLE_OAUTH_CLIENT_ID or GOOGLE_ADS_CLIENT_ID")
        if not client_secret:
            gaps.append("GOOGLE_OAUTH_CLIENT_SECRET or GOOGLE_ADS_CLIENT_SECRET")
        if gaps:
            raise ValueError("Missing GA4 credentials: " + "; ".join(gaps))

        credentials = _build_credentials(
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
        from googleapiclient.discovery import build

        admin_service = build("analyticsadmin", "v1beta", credentials=credentials, cache_discovery=False)
        resp = admin_service.accountSummaries().list(pageSize=200).execute()

        rows: list[dict[str, Any]] = []
        for account in resp.get("accountSummaries", []):
            account_name = account.get("displayName") or account.get("name", "")
            for prop in account.get("propertySummaries", []):
                prop_name = prop.get("displayName") or prop.get("property", "")
                property_resource = prop.get("property", "")
                property_id = property_resource.split("/")[-1] if property_resource else ""
                if not property_id:
                    continue
                rows.append(
                    {
                        "property_id": property_id,
                        "property_name": prop_name,
                        "account_name": account_name,
                    }
                )
        rows.sort(key=lambda row: (row["account_name"].lower(), row["property_name"].lower()))
        return rows


def fetch_ga4_landing_pages(
    property_id: str,
    date_from: str,
    date_to: str,
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Fetch paid landing page performance from GA4."""
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        DateRange,
        Dimension,
        Filter,
        FilterExpression,
        Metric,
        OrderBy,
        RunReportRequest,
        StringFilter,
    )

    credentials = _build_credentials(
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
    )
    client = BetaAnalyticsDataClient(credentials=credentials)
    req = RunReportRequest(
        property=f"properties/{property_id.strip()}",
        date_ranges=[DateRange(start_date=date_from, end_date=date_to)],
        dimensions=[
            Dimension(name="pagePath"),
            Dimension(name="sessionSourceMedium"),
        ],
        metrics=[
            Metric(name="sessions"),
            Metric(name="bounceRate"),
            Metric(name="engagementRate"),
            Metric(name="averageSessionDuration"),
            Metric(name="conversions"),
            Metric(name="totalRevenue"),
        ],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="sessionSourceMedium",
                string_filter=StringFilter(
                    match_type=StringFilter.MatchType.CONTAINS,
                    value="google / cpc",
                ),
            )
        ),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=100,
    )
    resp = client.run_report(req)

    rows: list[dict[str, Any]] = []
    for row in resp.rows:
        dims = row.dimension_values
        metrics = row.metric_values
        sessions = int(float(metrics[0].value or 0))
        bounce_rate = float(metrics[1].value or 0)
        engagement_rate = float(metrics[2].value or 0)
        avg_session_duration = float(metrics[3].value or 0)
        conversions = float(metrics[4].value or 0)
        total_revenue = float(metrics[5].value or 0)
        rows.append(
            {
                "page_path": dims[0].value,
                "session_source_medium": dims[1].value,
                "sessions": sessions,
                "bounce_rate": bounce_rate,
                "engagement_rate": engagement_rate,
                "average_session_duration": avg_session_duration,
                "conversions": conversions,
                "total_revenue": total_revenue,
            }
        )

    return {
        "report_type": "ga4_landing_pages",
        "date_range": f"{date_from} to {date_to}",
        "row_count": len(rows),
        "rows": rows,
    }


def fetch_ga4_conversion_paths(
    property_id: str,
    date_from: str,
    date_to: str,
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Fetch channel-level conversion context from GA4."""
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, OrderBy, RunReportRequest

    credentials = _build_credentials(
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
    )
    client = BetaAnalyticsDataClient(credentials=credentials)
    req = RunReportRequest(
        property=f"properties/{property_id.strip()}",
        date_ranges=[DateRange(start_date=date_from, end_date=date_to)],
        dimensions=[
            Dimension(name="sessionSourceMedium"),
            Dimension(name="sessionDefaultChannelGroup"),
        ],
        metrics=[
            Metric(name="conversions"),
            Metric(name="totalRevenue"),
            Metric(name="sessions"),
            Metric(name="engagedSessions"),
        ],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="conversions"), desc=True)],
        limit=100,
    )
    resp = client.run_report(req)

    rows: list[dict[str, Any]] = []
    for row in resp.rows:
        dims = row.dimension_values
        metrics = row.metric_values
        conversions = float(metrics[0].value or 0)
        total_revenue = float(metrics[1].value or 0)
        sessions = int(float(metrics[2].value or 0))
        engaged_sessions = int(float(metrics[3].value or 0))
        rows.append(
            {
                "session_source_medium": dims[0].value,
                "session_default_channel_group": dims[1].value,
                "conversions": conversions,
                "total_revenue": total_revenue,
                "sessions": sessions,
                "engaged_sessions": engaged_sessions,
            }
        )

    return {
        "report_type": "ga4_conversion_paths",
        "date_range": f"{date_from} to {date_to}",
        "row_count": len(rows),
        "rows": rows,
    }


GA4_META = ConnectorMeta(
    id=GA4_CONNECTOR_ID,
    label="Google Analytics 4",
    oauth_scope=f"{_GA4_SCOPE} {_GA4_EDIT_SCOPE}",
    capabilities=frozenset({CAP_ACCOUNTS}),
)

register_connector(GA4_META, GA4Connector())
