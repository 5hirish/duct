"""GA4 executors — key events, audiences, and Google Ads links.

Key-event repair is the highest-value, lowest-blast-radius execution surfaced
by the Gads engagement: registering the *right* key events (e.g. the
``signup`` vs ``sign_up`` rename that silently dropped conversions) and
removing polluting ones. Audience create/archive and Ads-link management round
out the admin surface. All ops require the ``analytics.edit`` scope — the
read-only audit token is not enough, and the error message says exactly that.

API split: key events + googleAdsLinks live in Admin API **v1beta**; audiences
are **v1alpha-only** (``_admin_service_alpha``). Archiving an audience is
permanent — recreation from the snapshot re-accumulates members from zero.
"""

from __future__ import annotations

from typing import Any

from service.execution.registry import ExecutorSpec, register_executor

# Every GA4 executor writes through the Admin API. Reading needs only
# analytics.readonly, which is why someone can connect GA4 successfully and
# still be unable to run any of these.
_GA4_WRITE = frozenset({"https://www.googleapis.com/auth/analytics.edit"})

_GA4_EDIT_SCOPE = "https://www.googleapis.com/auth/analytics.edit"
_VALID_COUNTING = {"ONCE_PER_EVENT", "ONCE_PER_SESSION"}
_EDIT_HINT = (
    "GA4 edit access denied — the Google Analytics connection is read-only. "
    "Reconnect Google Analytics with manage (analytics.edit) access to execute changes."
)


def _admin_service(creds: dict[str, Any]):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    for key in ("client_id", "client_secret", "refresh_token"):
        if not (creds.get(key) or "").strip():
            raise ValueError(f"Missing GA4 credential: {key}")
    credentials = Credentials(
        None,
        refresh_token=creds["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        scopes=[_GA4_EDIT_SCOPE],
    )
    return build("analyticsadmin", "v1beta", credentials=credentials, cache_discovery=False)


def _require(change: dict, section: str, key: str) -> Any:
    value = (change.get(section) or {}).get(key)
    if value in (None, ""):
        raise ValueError(f"change.{section}.{key} is required for {change.get('op_type')}")
    return value


def _translate(exc: Exception) -> Exception:
    from googleapiclient.errors import HttpError

    if isinstance(exc, HttpError) and exc.resp.status in (401, 403):
        return ValueError(_EDIT_HINT)
    return RuntimeError(f"GA4 Admin API error: {exc}")


def _list_key_events(service, property_id: str) -> list[dict[str, Any]]:
    try:
        response = service.properties().keyEvents().list(parent=f"properties/{property_id}").execute()
    except Exception as exc:
        raise _translate(exc) from exc
    return response.get("keyEvents", [])


# ---------------------------------------------------------------------------
# ga4.create_key_event
# ---------------------------------------------------------------------------

def _create_preview(change: dict, creds: dict) -> dict:
    property_id = str(_require(change, "target", "property_id"))
    event_name = str(_require(change, "payload", "event_name")).strip()
    counting = (change.get("payload", {}).get("counting_method") or "ONCE_PER_EVENT").upper()
    if counting not in _VALID_COUNTING:
        raise ValueError(f"counting_method must be one of {sorted(_VALID_COUNTING)}")

    existing = _list_key_events(_admin_service(creds), property_id)
    names = {e.get("eventName") for e in existing}
    warnings = []
    if event_name in names:
        warnings.append(f"'{event_name}' is already a key event on property {property_id}.")
    return {
        "current": {"key_events": sorted(n for n in names if n)},
        "diff": f"Register '{event_name}' as a key event (counting: {counting}) on property {property_id}",
        "warnings": warnings,
        "mutate_payload": {"eventName": event_name, "countingMethod": counting},
    }


def _create_apply(change: dict, creds: dict) -> dict:
    property_id = str(_require(change, "target", "property_id"))
    event_name = str(_require(change, "payload", "event_name")).strip()
    counting = (change.get("payload", {}).get("counting_method") or "ONCE_PER_EVENT").upper()

    service = _admin_service(creds)
    try:
        created = (
            service.properties()
            .keyEvents()
            .create(
                parent=f"properties/{property_id}",
                body={"eventName": event_name, "countingMethod": counting},
            )
            .execute()
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {
        "key_event": created,
        "rollback": {"delete_resource": created.get("name", "")},
    }


def _create_rollback(change: dict, creds: dict) -> dict:
    resource = ((change.get("result") or {}).get("rollback") or {}).get("delete_resource")
    if not resource:
        raise ValueError("No rollback handle recorded for this change")
    service = _admin_service(creds)
    try:
        service.properties().keyEvents().delete(name=resource).execute()
    except Exception as exc:
        raise _translate(exc) from exc
    return {"deleted": resource}


# ---------------------------------------------------------------------------
# ga4.delete_key_event
# ---------------------------------------------------------------------------

def _delete_preview(change: dict, creds: dict) -> dict:
    property_id = str(_require(change, "target", "property_id"))
    event_name = str(_require(change, "target", "event_name")).strip()

    existing = _list_key_events(_admin_service(creds), property_id)
    match = next((e for e in existing if e.get("eventName") == event_name), None)
    if match is None:
        return {
            "current": {"key_events": sorted(e.get("eventName", "") for e in existing)},
            "diff": f"Remove key event '{event_name}' from property {property_id}",
            "warnings": [f"'{event_name}' is not currently a key event — applying would fail."],
            "mutate_payload": {},
        }
    return {
        "current": {"key_event": match},
        "diff": f"Remove key event '{event_name}' ({match.get('name')}) from property {property_id}",
        "warnings": [],
        "mutate_payload": {"delete": match.get("name")},
    }


def _delete_apply(change: dict, creds: dict) -> dict:
    property_id = str(_require(change, "target", "property_id"))
    event_name = str(_require(change, "target", "event_name")).strip()

    service = _admin_service(creds)
    existing = _list_key_events(service, property_id)
    match = next((e for e in existing if e.get("eventName") == event_name), None)
    if match is None:
        raise ValueError(f"'{event_name}' is not a key event on property {property_id}")
    try:
        service.properties().keyEvents().delete(name=match["name"]).execute()
    except Exception as exc:
        raise _translate(exc) from exc
    return {
        "deleted": match["name"],
        # Recreate from the snapshot to undo.
        "rollback": {
            "recreate": {
                "parent": f"properties/{property_id}",
                "eventName": match.get("eventName"),
                "countingMethod": match.get("countingMethod", "ONCE_PER_EVENT"),
            }
        },
    }


def _delete_rollback(change: dict, creds: dict) -> dict:
    recreate = ((change.get("result") or {}).get("rollback") or {}).get("recreate")
    if not recreate:
        raise ValueError("No rollback handle recorded for this change")
    service = _admin_service(creds)
    try:
        created = (
            service.properties()
            .keyEvents()
            .create(
                parent=recreate["parent"],
                body={
                    "eventName": recreate["eventName"],
                    "countingMethod": recreate["countingMethod"],
                },
            )
            .execute()
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {"recreated": created.get("name", "")}


register_executor(
    ExecutorSpec(
        op_type="ga4.create_key_event",
        connector_type="ga4",
        required_scopes=_GA4_WRITE,
        label="Register GA4 key event",
        preview=_create_preview,
        apply=_create_apply,
        rollback=_create_rollback,
    )
)

register_executor(
    ExecutorSpec(
        op_type="ga4.delete_key_event",
        connector_type="ga4",
        required_scopes=_GA4_WRITE,
        label="Remove GA4 key event",
        preview=_delete_preview,
        apply=_delete_apply,
        rollback=_delete_rollback,
        destructive=True,
    )
)


# ---------------------------------------------------------------------------
# Audiences — GA4 Admin API v1alpha (audiences are not in v1beta)
# ---------------------------------------------------------------------------

def _admin_service_alpha(creds: dict[str, Any]):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    for key in ("client_id", "client_secret", "refresh_token"):
        if not (creds.get(key) or "").strip():
            raise ValueError(f"Missing GA4 credential: {key}")
    credentials = Credentials(
        None,
        refresh_token=creds["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        scopes=[_GA4_EDIT_SCOPE],
    )
    return build("analyticsadmin", "v1alpha", credentials=credentials, cache_discovery=False)


def _list_audiences(service, property_id: str) -> list[dict[str, Any]]:
    try:
        response = service.properties().audiences().list(parent=f"properties/{property_id}").execute()
    except Exception as exc:
        raise _translate(exc) from exc
    return response.get("audiences", [])


def _audience_body(change: dict) -> dict[str, Any]:
    """Audience resource body from payload: either a full ``audience`` dict or
    the convenience fields (display_name/description/membership_duration_days/
    filter_clauses)."""
    payload = change.get("payload") or {}
    body = dict(payload.get("audience") or {})
    if payload.get("display_name"):
        body["displayName"] = payload["display_name"]
    if payload.get("description"):
        body["description"] = payload["description"]
    if payload.get("membership_duration_days"):
        body["membershipDurationDays"] = int(payload["membership_duration_days"])
    if payload.get("filter_clauses"):
        body["filterClauses"] = payload["filter_clauses"]
    if not body.get("displayName"):
        raise ValueError("payload.display_name (or audience.displayName) is required")
    if not body.get("filterClauses"):
        raise ValueError(
            "payload.filter_clauses (GA4 AudienceFilterClause list) is required — "
            "an audience needs at least one inclusion clause"
        )
    body.setdefault("membershipDurationDays", 30)
    body.setdefault("description", "")
    return body


# ---------------------------------------------------------------------------
# ga4.create_audience
# ---------------------------------------------------------------------------

def _audience_create_preview(change: dict, creds: dict) -> dict:
    property_id = str(_require(change, "target", "property_id"))
    body = _audience_body(change)

    existing = _list_audiences(_admin_service_alpha(creds), property_id)
    names = {a.get("displayName") for a in existing}
    warnings = []
    if body["displayName"] in names:
        warnings.append(
            f"An audience named '{body['displayName']}' already exists on property {property_id}."
        )
    return {
        "current": {"audience_count": len(existing), "audience_names": sorted(n for n in names if n)},
        "diff": (
            f"Create audience '{body['displayName']}' on property {property_id} "
            f"(membership {body['membershipDurationDays']}d, "
            f"{len(body['filterClauses'])} filter clause(s))"
        ),
        "warnings": warnings,
        "mutate_payload": body,
    }


def _audience_create_apply(change: dict, creds: dict) -> dict:
    property_id = str(_require(change, "target", "property_id"))
    body = _audience_body(change)

    service = _admin_service_alpha(creds)
    try:
        created = (
            service.properties()
            .audiences()
            .create(parent=f"properties/{property_id}", body=body)
            .execute()
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {
        "audience": created,
        # GA4 audiences cannot be deleted — archive is the undo.
        "rollback": {"archive_resource": created.get("name", "")},
    }


def _audience_create_rollback(change: dict, creds: dict) -> dict:
    resource = ((change.get("result") or {}).get("rollback") or {}).get("archive_resource")
    if not resource:
        raise ValueError("No rollback handle recorded for this change")
    service = _admin_service_alpha(creds)
    try:
        service.properties().audiences().archive(name=resource, body={}).execute()
    except Exception as exc:
        raise _translate(exc) from exc
    return {"archived": resource}


# ---------------------------------------------------------------------------
# ga4.archive_audience — destructive: archiving is permanent in GA4
# ---------------------------------------------------------------------------

def _find_audience(service, property_id: str, change: dict) -> dict[str, Any] | None:
    """Locate by resource name (payload/target audience_resource) or displayName."""
    wanted_resource = str(
        (change.get("target") or {}).get("audience_resource")
        or (change.get("payload") or {}).get("audience_resource")
        or ""
    ).strip()
    wanted_name = str(
        (change.get("target") or {}).get("display_name")
        or (change.get("payload") or {}).get("display_name")
        or ""
    ).strip()
    if not wanted_resource and not wanted_name:
        raise ValueError("target.audience_resource or target.display_name is required")
    for audience in _list_audiences(service, property_id):
        if wanted_resource and audience.get("name") == wanted_resource:
            return audience
        if wanted_name and audience.get("displayName") == wanted_name:
            return audience
    return None


def _audience_archive_preview(change: dict, creds: dict) -> dict:
    property_id = str(_require(change, "target", "property_id"))
    service = _admin_service_alpha(creds)
    match = _find_audience(service, property_id, change)
    if match is None:
        return {
            "current": {},
            "diff": f"Archive an audience on property {property_id}",
            "warnings": ["Audience not found on this property — applying would fail."],
            "mutate_payload": {},
        }
    return {
        "current": {"audience": match},
        "diff": (
            f"Archive audience '{match.get('displayName')}' ({match.get('name')}) "
            f"on property {property_id} — archiving is PERMANENT; a recreated "
            "audience re-accumulates members from zero"
        ),
        "warnings": ["GA4 audiences cannot be unarchived."],
        "mutate_payload": {"archive": match.get("name")},
    }


def _audience_archive_apply(change: dict, creds: dict) -> dict:
    property_id = str(_require(change, "target", "property_id"))
    service = _admin_service_alpha(creds)
    match = _find_audience(service, property_id, change)
    if match is None:
        raise ValueError(f"Audience not found on property {property_id}")
    try:
        service.properties().audiences().archive(name=match["name"], body={}).execute()
    except Exception as exc:
        raise _translate(exc) from exc
    # Snapshot the definition: rollback recreates it, but membership history
    # is NOT restored — members re-accumulate from zero.
    recreate = {
        key: match[key]
        for key in ("displayName", "description", "membershipDurationDays", "filterClauses")
        if key in match
    }
    return {
        "archived": match["name"],
        "rollback": {"recreate_parent": f"properties/{property_id}", "recreate": recreate},
    }


def _audience_archive_rollback(change: dict, creds: dict) -> dict:
    handle = ((change.get("result") or {}).get("rollback")) or {}
    recreate = handle.get("recreate")
    parent = handle.get("recreate_parent")
    if not recreate or not parent:
        raise ValueError("No rollback handle recorded for this change")
    service = _admin_service_alpha(creds)
    try:
        created = service.properties().audiences().create(parent=parent, body=recreate).execute()
    except Exception as exc:
        raise _translate(exc) from exc
    return {
        "recreated": created.get("name", ""),
        "note": "Recreated from snapshot — audience membership re-accumulates from zero.",
    }


# ---------------------------------------------------------------------------
# ga4.create_google_ads_link / ga4.delete_google_ads_link — v1beta
# ---------------------------------------------------------------------------

def _list_ads_links(service, property_id: str) -> list[dict[str, Any]]:
    try:
        response = (
            service.properties().googleAdsLinks().list(parent=f"properties/{property_id}").execute()
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return response.get("googleAdsLinks", [])


def _norm_ads_customer_id(value: str) -> str:
    digits = str(value).replace("-", "").strip()
    if not digits.isdigit() or len(digits) != 10:
        raise ValueError(f"customer_id must be a 10-digit Google Ads customer id, got {value!r}")
    return digits


def _ads_link_create_preview(change: dict, creds: dict) -> dict:
    property_id = str(_require(change, "target", "property_id"))
    customer_id = _norm_ads_customer_id(str(_require(change, "payload", "customer_id")))

    existing = _list_ads_links(_admin_service(creds), property_id)
    linked = {link.get("customerId") for link in existing}
    warnings = []
    if customer_id in linked:
        warnings.append(f"Property {property_id} is already linked to Ads customer {customer_id}.")
    return {
        "current": {"linked_customer_ids": sorted(c for c in linked if c)},
        "diff": f"Link Google Ads customer {customer_id} to GA4 property {property_id}",
        "warnings": warnings,
        "mutate_payload": {"customerId": customer_id},
    }


def _ads_link_create_apply(change: dict, creds: dict) -> dict:
    property_id = str(_require(change, "target", "property_id"))
    customer_id = _norm_ads_customer_id(str(_require(change, "payload", "customer_id")))

    service = _admin_service(creds)
    try:
        created = (
            service.properties()
            .googleAdsLinks()
            .create(parent=f"properties/{property_id}", body={"customerId": customer_id})
            .execute()
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {
        "google_ads_link": created,
        "rollback": {"delete_resource": created.get("name", "")},
    }


def _ads_link_create_rollback(change: dict, creds: dict) -> dict:
    resource = ((change.get("result") or {}).get("rollback") or {}).get("delete_resource")
    if not resource:
        raise ValueError("No rollback handle recorded for this change")
    service = _admin_service(creds)
    try:
        service.properties().googleAdsLinks().delete(name=resource).execute()
    except Exception as exc:
        raise _translate(exc) from exc
    return {"deleted": resource}


def _ads_link_delete_preview(change: dict, creds: dict) -> dict:
    property_id = str(_require(change, "target", "property_id"))
    customer_id = _norm_ads_customer_id(str(_require(change, "target", "customer_id")))

    existing = _list_ads_links(_admin_service(creds), property_id)
    match = next((link for link in existing if link.get("customerId") == customer_id), None)
    if match is None:
        return {
            "current": {"linked_customer_ids": sorted(link.get("customerId", "") for link in existing)},
            "diff": f"Unlink Google Ads customer {customer_id} from GA4 property {property_id}",
            "warnings": [f"Customer {customer_id} is not linked to this property — applying would fail."],
            "mutate_payload": {},
        }
    return {
        "current": {"google_ads_link": match},
        "diff": (
            f"Unlink Google Ads customer {customer_id} ({match.get('name')}) from "
            f"GA4 property {property_id} — conversion import and audience sharing stop"
        ),
        "warnings": ["Relinking later restarts data sharing but does not backfill the gap."],
        "mutate_payload": {"delete": match.get("name")},
    }


def _ads_link_delete_apply(change: dict, creds: dict) -> dict:
    property_id = str(_require(change, "target", "property_id"))
    customer_id = _norm_ads_customer_id(str(_require(change, "target", "customer_id")))

    service = _admin_service(creds)
    existing = _list_ads_links(service, property_id)
    match = next((link for link in existing if link.get("customerId") == customer_id), None)
    if match is None:
        raise ValueError(f"Customer {customer_id} is not linked to property {property_id}")
    try:
        service.properties().googleAdsLinks().delete(name=match["name"]).execute()
    except Exception as exc:
        raise _translate(exc) from exc
    return {
        "deleted": match["name"],
        "rollback": {
            "recreate_parent": f"properties/{property_id}",
            "recreate": {"customerId": customer_id},
        },
    }


def _ads_link_delete_rollback(change: dict, creds: dict) -> dict:
    handle = ((change.get("result") or {}).get("rollback")) or {}
    recreate = handle.get("recreate")
    parent = handle.get("recreate_parent")
    if not recreate or not parent:
        raise ValueError("No rollback handle recorded for this change")
    service = _admin_service(creds)
    try:
        created = service.properties().googleAdsLinks().create(parent=parent, body=recreate).execute()
    except Exception as exc:
        raise _translate(exc) from exc
    return {"recreated": created.get("name", "")}


register_executor(
    ExecutorSpec(
        op_type="ga4.create_audience",
        connector_type="ga4",
        required_scopes=_GA4_WRITE,
        label="Create GA4 audience",
        preview=_audience_create_preview,
        apply=_audience_create_apply,
        rollback=_audience_create_rollback,
    )
)

register_executor(
    ExecutorSpec(
        op_type="ga4.archive_audience",
        connector_type="ga4",
        required_scopes=_GA4_WRITE,
        label="Archive GA4 audience",
        preview=_audience_archive_preview,
        apply=_audience_archive_apply,
        rollback=_audience_archive_rollback,
        destructive=True,
    )
)

register_executor(
    ExecutorSpec(
        op_type="ga4.create_google_ads_link",
        connector_type="ga4",
        required_scopes=_GA4_WRITE,
        label="Link Google Ads account to GA4",
        preview=_ads_link_create_preview,
        apply=_ads_link_create_apply,
        rollback=_ads_link_create_rollback,
    )
)

register_executor(
    ExecutorSpec(
        op_type="ga4.delete_google_ads_link",
        connector_type="ga4",
        required_scopes=_GA4_WRITE,
        label="Unlink Google Ads account from GA4",
        preview=_ads_link_delete_preview,
        apply=_ads_link_delete_apply,
        rollback=_ads_link_delete_rollback,
        destructive=True,
    )
)
