"""Google Search Console connector + supplementary fetch functions."""

from __future__ import annotations

from typing import Any

from google.oauth2.credentials import Credentials

from config import get_configs
from service.connectors import (
    CAP_ACCOUNTS,
    ConnectorAuthContext,
    ConnectorMeta,
    entity_facts,
    register_connector,
)
from service.google.constants import GSC_CONNECTOR_ID, GSC_READ_SCOPE

_GSC_SCOPE = GSC_READ_SCOPE
_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _build_credentials(*, refresh_token: str, client_id: str, client_secret: str) -> Credentials:
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=_TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=[_GSC_SCOPE],
    )


def _build_service(*, refresh_token: str, client_id: str, client_secret: str):
    from googleapiclient.discovery import build

    credentials = _build_credentials(
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
    )
    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)


class GSCConnector:
    """Interactive GSC operations (site listing for account picker)."""

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
            raise ValueError("Missing GSC credentials: " + "; ".join(gaps))

        service = _build_service(
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
        resp = service.sites().list().execute()
        rows: list[dict[str, Any]] = []
        for entry in resp.get("siteEntry", []):
            site_url = entry.get("siteUrl") or ""
            if not site_url:
                continue
            permission = entry.get("permissionLevel", "")
            rows.append(
                {
                    # Canonical pair every adapter returns, so one picker can
                    # render every connector without a per-connector shim.
                    # Native keys stay alongside for connector-specific UI.
                    "account_id": site_url,
                    "account_name": _display_site(site_url),
                    # The entity here genuinely is a website, which is the case
                    # the favicon exists for.
                    "entity_url": _site_href(site_url),
                    # Not decoration: a user can hold both property kinds for
                    # one domain, and they display identically without this.
                    "entity_detail": (
                        "Domain property" if site_url.startswith("sc-domain:") else "URL prefix"
                    ),
                    "entity_meta": entity_facts(("Access", _PERMISSION_LABELS.get(permission, ""))),
                    "site_url": site_url,
                    "permission_level": permission,
                }
            )
        rows.sort(key=lambda row: row["site_url"].lower())
        return rows


def _display_site(site_url: str) -> str:
    """`sc-domain:example.com` reads as noise; `example.com` is the thing itself.

    Domain properties and URL-prefix properties are different objects in Search
    Console and a user may hold both, so the prefix is dropped for display only
    — `account_id` keeps the exact string the API needs.
    """
    if site_url.startswith("sc-domain:"):
        return site_url[len("sc-domain:"):]
    return site_url.rstrip("/")


def _site_href(site_url: str) -> str:
    """A URL a browser can actually fetch, for the row's favicon.

    ``sc-domain:example.com`` is a Search Console identifier, not a location;
    handing it to an ``<img src>`` as-is loads nothing.
    """
    if site_url.startswith("sc-domain:"):
        return "https://" + site_url[len("sc-domain:"):]
    return site_url if site_url.startswith(("http://", "https://")) else ""


#: Search Console's permission strings, in words. Which of these you hold
#: decides whether a property is worth mapping at all — a restricted user sees
#: a subset of the data, so the answer belongs in the picker rather than one
#: level down in a support article.
_PERMISSION_LABELS = {
    "siteOwner": "Owner",
    "siteFullUser": "Full access",
    "siteRestrictedUser": "Restricted",
    "siteUnverifiedUser": "Unverified",
}


#: Search Analytics' own ceiling per request. Pages beyond it come via
#: ``startRow``; a site big enough to need a third page is big enough that the
#: rows past 50,000 are noise next to the ones returned.
_API_PAGE_ROWS = 25_000
_MAX_PAGES = 2
#: What the agent actually receives. Everything fetched still counts toward
#: ``totals``, so a cut changes which rows are listed, never the totals.
RETURN_ROWS = 300
#: API dimension → row key. Written out rather than reusing the dimension
#: name, so the fields the catalog declares are literally visible here
#: (tests/test_insights_catalog_contract.py reads this file for them).
_ROW_KEYS = {"query": "query", "page": "page"}


def _search_analytics(
    site_url: str,
    date_from: str,
    date_to: str,
    dimensions: list[str],
    report_type: str,
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """One Search Analytics report, paginated, cut to the rows worth reading.

    This was two calls at ``rowLimit: 100``. The API sorts by clicks, so the
    cut kept the queries already earning clicks and dropped the zero-click
    impression tail — the list an SEO actually works from (``knowledge/gsc.md``
    measured 71% of impressions missing at 250 rows). Now every row is
    fetched, the ones returned are the highest-impression rows, and the
    envelope says how much of the whole they cover so the agent can say
    "partial" instead of reading a missing row as zero.

    ``dataState: all`` because ``final`` zeroes the last two or three days,
    which reads as a traffic cliff at the end of every window.
    """
    service = _build_service(
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
    )
    fetched: list[dict[str, Any]] = []
    for page in range(_MAX_PAGES):
        body = {
            "startDate": date_from,
            "endDate": date_to,
            "dimensions": dimensions,
            "dataState": "all",
            "rowLimit": _API_PAGE_ROWS,
            "startRow": page * _API_PAGE_ROWS,
        }
        resp = service.searchanalytics().query(siteUrl=site_url.strip(), body=body).execute()
        batch = resp.get("rows", [])
        fetched.extend(batch)
        if len(batch) < _API_PAGE_ROWS:
            break

    rows: list[dict[str, Any]] = []
    for row in fetched:
        keys = row.get("keys", [])
        entry: dict[str, Any] = {
            _ROW_KEYS[dim]: (keys[i] if i < len(keys) else "") for i, dim in enumerate(dimensions)
        }
        entry |= {
            "clicks": float(row.get("clicks", 0.0)),
            "impressions": float(row.get("impressions", 0.0)),
            "ctr": float(row.get("ctr", 0.0)),
            "avg_position": float(row.get("position", 0.0)),
        }
        rows.append(entry)
    rows.sort(key=lambda item: item["impressions"], reverse=True)

    total_impressions = sum(r["impressions"] for r in rows)
    returned = rows[:RETURN_ROWS]
    returned_impressions = sum(r["impressions"] for r in returned)
    return {
        "report_type": report_type,
        "date_range": f"{date_from} to {date_to}",
        "row_count": len(returned),
        "totals": {
            "rows_available": len(rows),
            "clicks": sum(r["clicks"] for r in rows),
            "impressions": total_impressions,
        },
        "truncated": len(rows) > len(returned),
        # Share of the window's impressions the listed rows account for. Read
        # it before concluding anything about a row that is not listed.
        "impressions_coverage": round(returned_impressions / total_impressions, 3) if total_impressions else 1.0,
        "data_state": "all (the last 2-3 days are not yet final)",
        "rows": returned,
    }


def fetch_gsc_query_performance(
    site_url: str,
    date_from: str,
    date_to: str,
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Organic queries from Search Console, highest impressions first."""
    return _search_analytics(
        site_url, date_from, date_to, ["query"], "gsc_query_performance",
        refresh_token=refresh_token, client_id=client_id, client_secret=client_secret,
    )


def fetch_gsc_page_performance(
    site_url: str,
    date_from: str,
    date_to: str,
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Organic pages from Search Console, highest impressions first."""
    return _search_analytics(
        site_url, date_from, date_to, ["page"], "gsc_page_performance",
        refresh_token=refresh_token, client_id=client_id, client_secret=client_secret,
    )


def fetch_gsc_query_page(
    site_url: str,
    date_from: str,
    date_to: str,
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Which page ranks for which query.

    The only view that shows cannibalisation (one query splitting impressions
    across several pages) or a query landing on the wrong page; flat query and
    page tables cannot answer either.
    """
    return _search_analytics(
        site_url, date_from, date_to, ["query", "page"], "gsc_query_page",
        refresh_token=refresh_token, client_id=client_id, client_secret=client_secret,
    )


GSC_META = ConnectorMeta(
    id=GSC_CONNECTOR_ID,
    label="Google Search Console",
    oauth_scope=_GSC_SCOPE,
    capabilities=frozenset({CAP_ACCOUNTS}),
    entity_noun="property",
    entity_noun_plural="properties",
)

register_connector(GSC_META, GSCConnector())
