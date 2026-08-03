"""GA4 executors — key-event repair (create / delete).

The highest-value, lowest-blast-radius executions surfaced by the Gads
engagement: registering the *right* key events (e.g. the ``signup`` vs
``sign_up`` rename that silently dropped conversions) and removing polluting
ones. Requires the ``analytics.edit`` scope — the read-only audit token is not
enough, and the error message says exactly that.
"""

from __future__ import annotations

from typing import Any

from service.execution.registry import ExecutorSpec, register_executor

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
        label="Remove GA4 key event",
        preview=_delete_preview,
        apply=_delete_apply,
        rollback=_delete_rollback,
        destructive=True,
    )
)
