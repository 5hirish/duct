"""Google Tag Manager connector: container listing and registry registration.

GTM is deploy-shaped: workspace edits are invisible to production until a
container version is created and published, and a publish changes the live
site for every visitor. The write scopes are requested up front (own consent,
own refresh token — separate from the other Google connectors) so the same
token later serves the staged-execution GTM executors.
"""

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
from service.google.constants import GTM_CONNECTOR_ID

_TOKEN_URI = "https://oauth2.googleapis.com/token"
GTM_SCOPES = (
    "https://www.googleapis.com/auth/tagmanager.readonly",
    "https://www.googleapis.com/auth/tagmanager.edit.containers",
    "https://www.googleapis.com/auth/tagmanager.publish",
)


def build_gtm_service(creds: dict[str, Any]):
    """Tag Manager v2 client from an execution-style creds dict."""
    from googleapiclient.discovery import build

    for key in ("client_id", "client_secret", "refresh_token"):
        if not (creds.get(key) or "").strip():
            raise ValueError(f"Missing GTM credential: {key}")
    credentials = Credentials(
        None,
        refresh_token=creds["refresh_token"],
        token_uri=_TOKEN_URI,
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        scopes=list(GTM_SCOPES),
    )
    return build("tagmanager", "v2", credentials=credentials, cache_discovery=False)


class GTMConnector:
    """Interactive GTM operations (container listing for the account picker)."""

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
            raise ValueError("Missing GTM credentials: " + "; ".join(gaps))

        service = build_gtm_service(
            {
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            }
        )
        try:
            accounts = service.accounts().list().execute().get("account", [])
        except Exception as exc:  # noqa: BLE001 — surface upstream failures as 502
            raise RuntimeError(f"GTM account listing failed: {exc}") from exc

        rows: list[dict[str, Any]] = []
        for account in accounts:
            account_id = account.get("accountId", "")
            account_name = account.get("name", "") or f"Account {account_id}"
            try:
                containers = (
                    service.accounts()
                    .containers()
                    .list(parent=f"accounts/{account_id}")
                    .execute()
                    .get("container", [])
                )
            except Exception as exc:  # noqa: BLE001 — skip unreadable accounts, keep the rest
                rows.append(
                    {
                        "account_id": account_id,
                        "account_name": account_name,
                        "entity_detail": f"Containers unavailable — {exc}",
                        "entity_meta": [],
                        "container_id": "",
                        "public_id": "",
                        "container_name": f"(containers unavailable: {exc})",
                        "path": "",
                    }
                )
                continue
            for container in containers:
                # e.g. "accounts/123/containers/456" — the executor target.
                path = container.get("path", "")
                container_id = container.get("containerId", "")
                public_id = container.get("publicId", "")
                rows.append(
                    {
                        # The canonical pair names the thing being *picked*,
                        # which for GTM is the container, not its parent
                        # account — same correction GA4 needed. Keyed on the
                        # account it produced one row per container all sharing
                        # one id, so the picker rendered N identical options
                        # and picking any of them stored the same value.
                        "account_id": path or container_id or public_id,
                        "account_name": container.get("name", "") or public_id,
                        "entity_detail": account_name,
                        "entity_meta": entity_facts(("Container", public_id)),
                        # The parent, under a name that says which it is.
                        "parent_account_id": account_id,
                        "parent_account_name": account_name,
                        "container_id": container_id,
                        "public_id": public_id,
                        "container_name": container.get("name", ""),
                        "path": path,
                    }
                )
        rows.sort(key=lambda r: (r.get("parent_account_name", "").lower(), r["account_name"].lower()))
        return rows


GTM_META = ConnectorMeta(
    id=GTM_CONNECTOR_ID,
    label="Google Tag Manager",
    oauth_scope=" ".join(GTM_SCOPES),
    capabilities=frozenset({CAP_ACCOUNTS}),
    entity_noun="container",
    entity_noun_plural="containers",
)

register_connector(GTM_META, GTMConnector())
