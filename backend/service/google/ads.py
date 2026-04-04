"""Google Ads connector: account listing and registry registration."""

from __future__ import annotations

import logging
from typing import Any

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

logger = logging.getLogger(__name__)

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
    login_customer_id: str = "",
) -> list[dict[str, Any]]:
    """List Google Ads customer accounts for OAuth credentials.

    ``login_customer_id`` (digits only, no dashes) should be your **manager (MCC)
    customer ID** when the signed-in user accesses child accounts through that
    MCC. Without it, ``search_stream`` often fails for sub-accounts and this
    function returns an empty list after silently skipping errors.
    """
    creds: dict[str, Any] = {
        "developer_token": developer_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "use_proto_plus": True,
    }
    login = _norm_customer_id(login_customer_id)
    if login:
        creds["login_customer_id"] = login
    client = GoogleAdsClient.load_from_dict(creds)
    customer_service = client.get_service("CustomerService")
    google_ads_service = client.get_service("GoogleAdsService")

    try:
        response = customer_service.list_accessible_customers()
    except GoogleAdsException as exc:
        message = exc.failure.errors[0].message if exc.failure.errors else str(exc)
        raise RuntimeError(message) from exc

    resource_names = list(response.resource_names)
    if not resource_names:
        logger.warning(
            "Google Ads list_accessible_customers returned no accounts. "
            "Common causes: developer token still in Test access (production accounts blocked), "
            "wrong Google user for OAuth, or Ads API not enabled for the Cloud project."
        )
        return []

    query = (
        "SELECT customer.id, customer.descriptive_name, customer.currency_code, "
        "customer.time_zone, customer.manager FROM customer LIMIT 1"
    )
    results: list[dict[str, Any]] = []
    for resource_name in resource_names:
        customer_id = _norm_customer_id(resource_name.split("/")[-1])
        try:
            stream = google_ads_service.search_stream(customer_id=customer_id, query=query)
            row = None
            for batch in stream:
                if batch.results:
                    row = batch.results[0]
                    break
            if row is None:
                logger.warning(
                    "Google Ads search_stream returned no rows for customer_id=%s "
                    "(check access and GOOGLE_ADS_LOGIN_CUSTOMER_ID if this is an MCC child).",
                    customer_id,
                )
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
        except Exception as exc:
            logger.warning(
                "Google Ads account list skipped customer_id=%s: %s. "
                "If this is a sub-account under an MCC, set GOOGLE_ADS_LOGIN_CUSTOMER_ID "
                "to the manager ID (digits only).",
                customer_id,
                exc,
            )
            continue

    if resource_names and not results:
        logger.warning(
            "list_accessible_customers returned %d resource(s) but none could be queried. "
            "Set GOOGLE_ADS_LOGIN_CUSTOMER_ID to your MCC (e.g. 9723262372) and retry.",
            len(resource_names),
        )

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
        gaps: list[str] = []
        if not rt:
            gaps.append("refresh_token (query param or GOOGLE_ADS_REFRESH_TOKEN env)")
        if not dt:
            gaps.append("GOOGLE_ADS_DEVELOPER_TOKEN")
        if not cid:
            gaps.append("GOOGLE_OAUTH_CLIENT_ID or GOOGLE_ADS_CLIENT_ID")
        if not secret:
            gaps.append("GOOGLE_OAUTH_CLIENT_SECRET or GOOGLE_ADS_CLIENT_SECRET")
        if gaps:
            raise ValueError(
                "Missing Google Ads API credentials: "
                + "; ".join(gaps)
                + ". OAuth alone is not enough — the Ads API requires a developer token."
            )
        login = cfg.google_ads_login_customer_id
        return list_accessible_accounts(dt, cid, secret, rt, login_customer_id=login)


GOOGLE_ADS_META = ConnectorMeta(
    id=GOOGLE_ADS_CONNECTOR_ID,
    label="Google Ads",
    oauth_scope="https://www.googleapis.com/auth/adwords",
    capabilities=frozenset({CAP_ACCOUNTS, CAP_CAMPAIGN_REPORT}),
)

register_connector(GOOGLE_ADS_META, GoogleAdsConnector())
