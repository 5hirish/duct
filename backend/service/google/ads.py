"""Google Ads connector: account listing and registry registration."""

from __future__ import annotations

from typing import Any

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from config import get_configs
from service.google.constants import GOOGLE_ADS_CONNECTOR_ID
from service.connectors import (
    CAP_ACCOUNTS,
    CAP_CAMPAIGN_REPORT,
    ConnectorAuthContext,
    ConnectorMeta,
    register_connector,
)


def _norm_customer_id(customer_id: str) -> str:
    return customer_id.replace("-", "").strip()


def list_accessible_accounts(
    developer_token: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> list[dict[str, Any]]:
    """List Google Ads customer accounts for OAuth credentials."""
    creds: dict[str, Any] = {
        "developer_token": developer_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "use_proto_plus": True,
    }
    client = GoogleAdsClient.load_from_dict(creds)
    customer_service = client.get_service("CustomerService")
    google_ads_service = client.get_service("GoogleAdsService")

    try:
        response = customer_service.list_accessible_customers()
    except GoogleAdsException as exc:
        message = exc.failure.errors[0].message if exc.failure.errors else str(exc)
        raise RuntimeError(message) from exc

    query = (
        "SELECT customer.id, customer.descriptive_name, customer.currency_code, "
        "customer.time_zone, customer.manager FROM customer LIMIT 1"
    )
    results: list[dict[str, Any]] = []
    for resource_name in response.resource_names:
        customer_id = _norm_customer_id(resource_name.split("/")[-1])
        try:
            stream = google_ads_service.search_stream(customer_id=customer_id, query=query)
            row = None
            for batch in stream:
                if batch.results:
                    row = batch.results[0]
                    break
            if row is None:
                continue
            results.append(
                {
                    "customer_id": str(row.customer.id),
                    "descriptive_name": row.customer.descriptive_name or f"Customer {row.customer.id}",
                    "currency_code": row.customer.currency_code or "USD",
                    "time_zone": row.customer.time_zone or "",
                    "manager": bool(row.customer.manager),
                }
            )
        except Exception:
            continue

    results.sort(key=lambda item: item["descriptive_name"].lower())
    return results


class GoogleAdsConnector:
    """Interactive Google Ads operations (accounts, etc.)."""

    def list_accounts(self, auth: ConnectorAuthContext) -> list[dict[str, Any]]:
        cfg = get_configs()
        rt = (auth.refresh_token or "").strip() or cfg.google_ads_refresh_token
        dt = cfg.google_ads_developer_token
        cid = cfg.google_oauth_client_id or cfg.google_ads_client_id
        secret = cfg.google_oauth_client_secret or cfg.google_ads_client_secret
        if not all([dt, cid, secret, rt]):
            raise ValueError(
                "Missing Google Ads credentials. Set GOOGLE_ADS_DEVELOPER_TOKEN, "
                "GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET and provide refresh_token."
            )
        return list_accessible_accounts(dt, cid, secret, rt)


GOOGLE_ADS_META = ConnectorMeta(
    id=GOOGLE_ADS_CONNECTOR_ID,
    label="Google Ads",
    oauth_scope="https://www.googleapis.com/auth/adwords",
    capabilities=frozenset({CAP_ACCOUNTS, CAP_CAMPAIGN_REPORT}),
)

register_connector(GOOGLE_ADS_META, GoogleAdsConnector())
