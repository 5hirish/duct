"""Mixpanel Query + App API — the one tool that sees every platform under one name.

Ported from the Gads engagement, where Mixpanel was read through the claude.ai
MCP connector and turned out to be the cross-check that caught GA4 silently
dropping web signups (event-edit rules renamed ``signup`` → ``sign_up`` while
the key event stayed ``signup``). Mixpanel receives the raw event name from
every platform, so its counts are the reference the others get reconciled to.

Auth: a **Service Account** (username + secret) pasted by the user, sent as
HTTP Basic. Service accounts are project-scoped by the org admin, so
``/api/app/me`` tells us exactly which projects this pair may read — that is
what ``list_accounts`` surfaces. Project tokens / API secrets are rejected:
a project token cannot read the Query API at all.

Regions matter: EU- and India-resident projects live on their own hosts, and
a US call against an EU project 401s with a message that looks like a bad
secret. The ``region`` field on the credential picks the host.

Sharp edges carried over from the engagement:
- **No internal-traffic filter exists.** QA accounts sit inside every funnel
  until you exclude them yourself — ``internal_patterns`` on the credential
  becomes a ``where`` clause on every query.
- Query API quota is 60 queries/hour and 5 concurrent; ``Pacer`` keeps a
  process from tripping the concurrency ceiling.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from service.rest import Endpoint, Pacer, RetryPolicy
from service.rest import ApiError as BaseApiError

API_HOSTS = {
    "us": "https://mixpanel.com",
    "eu": "https://eu.mixpanel.com",
    "in": "https://in.mixpanel.com",
}
QUERY_API_VERSION = "query-2.0"

# 60 queries/hour → one every second is comfortably inside it and never
# trips the 5-concurrent ceiling from a single process.
_PACER = Pacer(1.0)


class ApiError(BaseApiError):
    """Mixpanel error envelopes: ``{"error": "..."}`` (Query) or
    ``{"status": "error", "error": "..."}`` (App)."""

    def parse(self, body: str) -> str:
        try:
            data = json.loads(body)
        except Exception:  # noqa: BLE001
            return ""
        if isinstance(data, dict):
            return str(data.get("error") or data.get("message") or "")
        return ""

    def hint(self) -> str:
        if self.status in (401, 403):
            return (
                "Mixpanel rejected the service account. Check the username/secret pair, "
                "that the account has been granted this project, and that `region` "
                "matches where the project is hosted (EU projects 401 on the US host)."
            )
        if self.status == 429:
            return "Mixpanel Query API quota is 60 queries/hour — wait and retry."
        return ""


def require_credentials(creds: dict[str, str]) -> tuple[str, str]:
    username = (creds.get("service_account_username") or "").strip()
    secret = (creds.get("service_account_secret") or "").strip()
    if not username or not secret:
        raise ValueError(
            "Mixpanel credentials incomplete — service_account_username and "
            "service_account_secret are both required. Create a Service Account at "
            "Organization settings → Service Accounts and grant it the project. "
            "Project tokens and API secrets cannot read the Query API."
        )
    return username, secret


def require_project_id(creds: dict[str, str]) -> str:
    project_id = str(creds.get("project_id") or "").strip()
    if not project_id.isdigit():
        raise ValueError(
            "Mixpanel project_id missing or not numeric. It is the number in the "
            "project URL (mixpanel.com/project/<id>/...)."
        )
    return project_id


def region(creds: dict[str, str]) -> str:
    value = (creds.get("region") or "us").strip().lower()
    return value if value in API_HOSTS else "us"


def internal_patterns(creds: dict[str, str]) -> list[str]:
    """Comma-separated distinct_id substrings that mark internal/QA accounts."""
    raw = creds.get("internal_patterns") or ""
    return [p.strip() for p in raw.split(",") if p.strip()]


def internal_traffic_where(patterns: list[str]) -> str:
    """A Query API ``where`` expression excluding distinct_ids that contain any
    of the patterns. Empty when there is nothing to exclude."""
    if not patterns:
        return ""
    clauses = [
        f'not ("{p.replace(chr(34), "")}" in string(properties["distinct_id"]))'
        for p in patterns
    ]
    return " and ".join(clauses)


_ENDPOINTS: dict[str, Endpoint] = {}


def _endpoint(creds: dict[str, str]) -> Endpoint:
    key = region(creds)
    endpoint = _ENDPOINTS.get(key)
    if endpoint is None:
        endpoint = Endpoint(
            base_url=API_HOSTS[key],
            error_cls=ApiError,
            retry=RetryPolicy(attempts=4, first=2.0, cap=30.0),
            timeout=90,
        )
        _ENDPOINTS[key] = endpoint
    return endpoint


def _headers(creds: dict[str, str]) -> dict[str, str]:
    username, secret = require_credentials(creds)
    token = base64.b64encode(f"{username}:{secret}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def api(
    path: str,
    creds: dict[str, str],
    params: dict | None = None,
    *,
    method: str = "GET",
    json_body: Any = None,
) -> dict:
    """One Mixpanel call (Query or App API). Raises ApiError on failure."""
    return _endpoint(creds).request(
        path,
        headers=_headers(creds),
        method=method,
        params=params,
        json=json_body,
        pacer=_PACER,
    )


# ------------------------------------------------------------------ reads

def me(creds: dict[str, str]) -> dict:
    """The service account's own profile: which projects/orgs it may access."""
    return api("api/app/me", creds)


def event_names(creds: dict[str, str], limit: int = 25) -> list[str]:
    """Most common event names in the project (Query API ``events/names``)."""
    data = api(
        "api/query/events/names",
        creds,
        {"project_id": require_project_id(creds), "type": "general", "limit": limit},
    )
    if isinstance(data, list):
        return [str(n) for n in data]
    return [str(n) for n in (data.get("results") or data.get("names") or [])]


def event_counts(
    creds: dict[str, str],
    events: list[str],
    from_date: str,
    to_date: str,
    *,
    unit: str = "day",
    where: str = "",
) -> dict:
    """Daily counts for named events (Query API ``events``).

    Returns ``{"series": [dates], "values": {event: {date: count}}}``."""
    params: dict[str, Any] = {
        "project_id": require_project_id(creds),
        "event": json.dumps(events),
        "type": "general",
        "unit": unit,
        "from_date": from_date,
        "to_date": to_date,
    }
    if where:
        params["where"] = where
    data = api("api/query/events", creds, params)
    return data.get("data") or {"series": [], "values": {}}


def funnels_list(creds: dict[str, str]) -> list[dict]:
    data = api("api/query/funnels/list", creds, {"project_id": require_project_id(creds)})
    return list(data) if isinstance(data, list) else list(data.get("results") or [])


def funnel(
    creds: dict[str, str],
    funnel_id: int | str,
    from_date: str,
    to_date: str,
    *,
    where: str = "",
) -> dict:
    """One saved funnel's per-day step counts (Query API ``funnels``)."""
    params: dict[str, Any] = {
        "project_id": require_project_id(creds),
        "funnel_id": funnel_id,
        "from_date": from_date,
        "to_date": to_date,
        "unit": "day",
    }
    if where:
        params["where"] = where
    return api("api/query/funnels", creds, params)


# ----------------------------------------------------------------- writes

def list_annotations(creds: dict[str, str], from_date: str = "", to_date: str = "") -> list[dict]:
    project_id = require_project_id(creds)
    params: dict[str, Any] = {}
    if from_date:
        params["fromDate"] = from_date
    if to_date:
        params["toDate"] = to_date
    data = api(f"api/app/projects/{project_id}/annotations", creds, params or None)
    return list(data.get("results") or [])


def create_annotation(creds: dict[str, str], date: str, description: str) -> dict:
    project_id = require_project_id(creds)
    data = api(
        f"api/app/projects/{project_id}/annotations",
        creds,
        method="POST",
        json_body={"date": date, "description": description},
    )
    return data.get("results") or data


def delete_annotation(creds: dict[str, str], annotation_id: int | str) -> dict:
    project_id = require_project_id(creds)
    return api(
        f"api/app/projects/{project_id}/annotations/{annotation_id}", creds, method="DELETE"
    )


def get_schema(creds: dict[str, str], entity_type: str, name: str) -> dict | None:
    """One Lexicon schema entry, or None when the entity has no schema yet."""
    project_id = require_project_id(creds)
    try:
        data = api(f"api/app/projects/{project_id}/schemas/{entity_type}/{name}", creds)
    except ApiError as exc:
        if exc.status == 404:
            return None
        raise
    return data.get("results") or data


def upsert_schema(creds: dict[str, str], entity_type: str, name: str, schema_json: dict) -> dict:
    """Create/replace one Lexicon schema entry (``hidden``, ``dropped``,
    ``description`` …). Non-truncating: other entries are untouched."""
    project_id = require_project_id(creds)
    return api(
        f"api/app/projects/{project_id}/schemas",
        creds,
        method="POST",
        json_body={
            "entries": [{"entityType": entity_type, "name": name, "schemaJson": schema_json}],
            "truncate": False,
        },
    )
