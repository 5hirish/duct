"""Mixpanel executors — timeline annotations + Lexicon event hiding.

Two reversible metadata writes, both App API, both service-account authed:

- ``mixpanel.create_annotation`` — a dated note on every chart in the project.
  The execution framework's natural companion: when Duct applies a change to
  an ad account or a tag container, the analytics timeline should say so, or
  next month's "why did signups jump on the 14th" is a mystery again.
  Rollback deletes the annotation. Allowlisted for auto-apply: no data moves.
- ``mixpanel.hide_event`` — hide (or unhide) an event in Lexicon. The
  engagement carried a legacy typo event (``plan_upgrade_initated``) that kept
  landing in reports; hiding it is the fix. Rollback restores the previous
  schema. Always waits for a human — it changes what analysts see.

Credentials arrive per-request in the manual-connector shape
(``service_account_username``, ``service_account_secret``, ``project_id``,
``region``); nothing here reads env.
"""

from __future__ import annotations

import re
from typing import Any

from service.execution.registry import ExecutorSpec, register_executor
from service.mixpanel import client as mp

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$")


def _creds(change: dict, creds: dict[str, Any]) -> dict[str, str]:
    """Executor creds + the target's project id (target wins over the blob)."""
    merged = {k: str(v) for k, v in creds.items() if v}
    project_id = str((change.get("target") or {}).get("project_id") or "").strip()
    if project_id:
        merged["project_id"] = project_id
    mp.require_credentials(merged)
    mp.require_project_id(merged)
    return merged


def _require(change: dict, section: str, key: str) -> Any:
    value = (change.get(section) or {}).get(key)
    if value in (None, ""):
        raise ValueError(f"change.{section}.{key} is required for {change.get('op_type')}")
    return value


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, mp.ApiError):
        if exc.status in (401, 403):
            return ValueError(exc.hint() or f"Mixpanel rejected the request: {exc}")
        return RuntimeError(f"Mixpanel App API error: {exc}")
    return RuntimeError(f"Mixpanel App API error: {exc}")


# ---------------------------------------------------------------------------
# mixpanel.create_annotation
# ---------------------------------------------------------------------------

def _annotation_inputs(change: dict) -> tuple[str, str]:
    when = str(_require(change, "payload", "date")).strip()
    if not _DATE_RE.match(when):
        raise ValueError("payload.date must be 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'")
    if len(when) == 10:
        when += " 00:00:00"
    description = str(_require(change, "payload", "description")).strip()
    if len(description) > 500:
        raise ValueError("payload.description must be 500 characters or fewer")
    return when, description


def _annotation_preview(change: dict, creds: dict) -> dict:
    creds = _creds(change, creds)
    when, description = _annotation_inputs(change)
    day = when[:10]
    warnings: list[str] = []
    try:
        existing = mp.list_annotations(creds, day, day)
    except mp.ApiError as exc:
        raise _translate(exc) from exc
    same = [a for a in existing if str(a.get("description", "")).strip() == description]
    if same:
        warnings.append(f"An identical annotation already exists on {day}.")
    return {
        "current": {"annotations_that_day": [
            {"id": a.get("id"), "description": a.get("description"), "date": a.get("date")}
            for a in existing
        ]},
        "diff": f"Annotate {when} on project {creds['project_id']}: “{description}”",
        "warnings": warnings,
        "mutate_payload": {"date": when, "description": description},
    }


def _annotation_apply(change: dict, creds: dict) -> dict:
    creds = _creds(change, creds)
    when, description = _annotation_inputs(change)
    try:
        created = mp.create_annotation(creds, when, description)
    except mp.ApiError as exc:
        raise _translate(exc) from exc
    annotation_id = created.get("id") if isinstance(created, dict) else None
    if annotation_id is None:
        raise RuntimeError(f"Mixpanel did not return an annotation id: {created!r}")
    return {"annotation": created, "rollback": {"annotation_id": annotation_id}}


def _annotation_rollback(change: dict, creds: dict) -> dict:
    creds = _creds(change, creds)
    annotation_id = ((change.get("result") or {}).get("rollback") or {}).get("annotation_id")
    if annotation_id is None:
        raise ValueError("No rollback handle recorded for this change")
    try:
        mp.delete_annotation(creds, annotation_id)
    except mp.ApiError as exc:
        raise _translate(exc) from exc
    return {"deleted_annotation_id": annotation_id}


# ---------------------------------------------------------------------------
# mixpanel.hide_event
# ---------------------------------------------------------------------------

def _hide_inputs(change: dict) -> tuple[str, bool]:
    name = str(_require(change, "target", "event_name")).strip()
    hidden = (change.get("payload") or {}).get("hidden", True)
    if not isinstance(hidden, bool):
        raise ValueError("payload.hidden must be true or false")
    return name, hidden


def _hide_preview(change: dict, creds: dict) -> dict:
    creds = _creds(change, creds)
    name, hidden = _hide_inputs(change)
    try:
        schema = mp.get_schema(creds, "event", name)
    except mp.ApiError as exc:
        raise _translate(exc) from exc
    schema_json = dict((schema or {}).get("schemaJson") or {})
    currently_hidden = bool(schema_json.get("hidden", False))
    warnings: list[str] = []
    if currently_hidden == hidden:
        warnings.append(
            f"'{name}' is already {'hidden' if hidden else 'visible'} in Lexicon — applying is a no-op."
        )
    verb = "Hide" if hidden else "Unhide"
    return {
        "current": {"schema_json": schema_json, "has_schema": schema is not None},
        "diff": f"{verb} event '{name}' in Lexicon (project {creds['project_id']})",
        "warnings": warnings,
        "mutate_payload": {"entityType": "event", "name": name, "schemaJson": {**schema_json, "hidden": hidden}},
    }


def _hide_apply(change: dict, creds: dict) -> dict:
    creds = _creds(change, creds)
    name, hidden = _hide_inputs(change)
    previous = dict(((change.get("current") or {}).get("schema_json")) or {})
    if not previous and "has_schema" not in (change.get("current") or {}):
        try:
            schema = mp.get_schema(creds, "event", name)
        except mp.ApiError as exc:
            raise _translate(exc) from exc
        previous = dict((schema or {}).get("schemaJson") or {})
    try:
        mp.upsert_schema(creds, "event", name, {**previous, "hidden": hidden})
    except mp.ApiError as exc:
        raise _translate(exc) from exc
    return {
        "event_name": name,
        "hidden": hidden,
        "rollback": {"event_name": name, "schema_json": previous},
    }


def _hide_rollback(change: dict, creds: dict) -> dict:
    creds = _creds(change, creds)
    handle = (change.get("result") or {}).get("rollback") or {}
    name = handle.get("event_name")
    if not name:
        raise ValueError("No rollback handle recorded for this change")
    previous = dict(handle.get("schema_json") or {})
    previous.setdefault("hidden", False)
    try:
        mp.upsert_schema(creds, "event", name, previous)
    except mp.ApiError as exc:
        raise _translate(exc) from exc
    return {"event_name": name, "restored_schema_json": previous}


register_executor(
    ExecutorSpec(
        op_type="mixpanel.create_annotation",
        connector_type="mixpanel",
        label="Add Mixpanel timeline annotation",
        preview=_annotation_preview,
        apply=_annotation_apply,
        rollback=_annotation_rollback,
    )
)

register_executor(
    ExecutorSpec(
        op_type="mixpanel.hide_event",
        connector_type="mixpanel",
        label="Hide/unhide event in Mixpanel Lexicon",
        preview=_hide_preview,
        apply=_hide_apply,
        rollback=_hide_rollback,
    )
)
