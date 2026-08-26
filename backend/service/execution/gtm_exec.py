"""GTM executors — workspace edits and container publishing as a deploy.

GTM is deploy-shaped (Gads corpus): workspace edits are invisible to
production until a container version is created and published, and a publish
changes the live site for every visitor. That split is encoded in the op
registry:

- ``gtm.upsert_tag`` / ``gtm.upsert_variable`` — workspace-scoped, reversible
  (created entities are deleted, updated ones restored from the snapshot).
  These may auto-apply under assisted autonomy because production never sees
  them until a publish.
- ``gtm.publish_version`` — **destructive**. Apply re-captures the outgoing
  live version id immediately before creating+publishing the new version (the
  record-rollback-target-first rule), so rollback can republish it.
- ``gtm.rollback_to_version`` — **destructive**: republishes an older version.

GTM API quotas are tight (per-account rate limits measured in requests per
*minute*), so every executor holds a module lock — one GTM mutation in flight
per process, never a concurrent burst.
"""

from __future__ import annotations

import threading
from typing import Any

from service.execution.registry import ExecutorSpec, register_executor
from service.google.gtm import build_gtm_service

# Serialize all GTM API work — quota protection (see module docstring).
_GTM_LOCK = threading.Lock()

_ENTITY_KINDS = {
    "tag": {"list_key": "tag", "label": "Tag"},
    "variable": {"list_key": "variable", "label": "Variable"},
}


def _require(change: dict, section: str, key: str) -> Any:
    value = (change.get(section) or {}).get(key)
    if value in (None, ""):
        raise ValueError(f"change.{section}.{key} is required for {change.get('op_type')}")
    return value


def _translate(exc: Exception) -> Exception:
    from googleapiclient.errors import HttpError

    if isinstance(exc, HttpError):
        if exc.resp.status in (401, 403):
            return ValueError(
                "GTM access denied — reconnect Google Tag Manager from the Connections "
                "page (the edit/publish scopes are requested there)."
            )
        if exc.resp.status == 429:
            return RuntimeError(
                "GTM API quota exhausted — Tag Manager rate limits are per-minute; "
                "retry this change set in a minute or two."
            )
    return RuntimeError(f"GTM API error: {exc}")


def _entities(service, kind: str, workspace_path: str):
    """The tags()/variables() collection resource for a workspace."""
    workspaces = service.accounts().containers().workspaces()
    return workspaces.tags() if kind == "tag" else workspaces.variables()


def _container_path_of(workspace_path: str) -> str:
    # "accounts/A/containers/C/workspaces/W" → "accounts/A/containers/C"
    parts = workspace_path.split("/")
    if len(parts) < 4 or parts[0] != "accounts" or parts[2] != "containers":
        raise ValueError(f"Not a GTM workspace path: {workspace_path!r}")
    return "/".join(parts[:4])


def _resolve_workspace(service, change: dict) -> str:
    """Workspace path from target.workspace_path, or the container's default
    workspace when only target.container_path is given. The resolved path is
    stashed in ``current`` at preview time so apply reuses it."""
    target = change.get("target") or {}
    workspace_path = str(target.get("workspace_path") or "").strip()
    if workspace_path:
        return workspace_path
    stashed = str((change.get("current") or {}).get("workspace_path") or "").strip()
    if stashed:
        return stashed
    container_path = str(target.get("container_path") or "").strip()
    if not container_path:
        raise ValueError("target.workspace_path or target.container_path is required")
    try:
        response = (
            service.accounts().containers().workspaces().list(parent=container_path).execute()
        )
    except Exception as exc:
        raise _translate(exc) from exc
    workspaces = response.get("workspace", [])
    if not workspaces:
        raise ValueError(f"No workspaces on container {container_path}")
    default = next(
        (w for w in workspaces if w.get("name", "").lower() == "default workspace"),
        workspaces[0],
    )
    return default["path"]


def _container_path(change: dict) -> str:
    target = change.get("target") or {}
    container_path = str(target.get("container_path") or "").strip()
    if container_path:
        return container_path
    workspace_path = str(target.get("workspace_path") or "").strip()
    if workspace_path:
        return _container_path_of(workspace_path)
    raise ValueError("target.container_path or target.workspace_path is required")


def _live_version_id(service, container_path: str) -> str:
    """The currently-published version id, "" when nothing was ever published."""
    try:
        live = service.accounts().containers().versions().live(parent=container_path).execute()
    except Exception as exc:
        from googleapiclient.errors import HttpError

        if isinstance(exc, HttpError) and exc.resp.status == 404:
            return ""
        raise _translate(exc) from exc
    return str(live.get("containerVersionId") or "")


# ---------------------------------------------------------------------------
# gtm.upsert_tag / gtm.upsert_variable — workspace-scoped, reversible
# ---------------------------------------------------------------------------

def _entity_body(change: dict, kind: str) -> dict[str, Any]:
    body = (change.get("payload") or {}).get(kind)
    if not isinstance(body, dict) or not body:
        raise ValueError(f"payload.{kind} (full GTM {kind} body) is required")
    if not str(body.get("name") or "").strip():
        raise ValueError(f"payload.{kind}.name is required — upsert matches by name")
    if not str(body.get("type") or "").strip():
        raise ValueError(f"payload.{kind}.type is required (e.g. 'html', 'gaawe', 'v')")
    return body


def _find_by_name(service, kind: str, workspace_path: str, name: str) -> dict[str, Any] | None:
    collection = _entities(service, kind, workspace_path)
    try:
        response = collection.list(parent=workspace_path).execute()
    except Exception as exc:
        raise _translate(exc) from exc
    for entity in response.get(_ENTITY_KINDS[kind]["list_key"], []):
        if entity.get("name") == name:
            return entity
    return None


def _upsert_preview(kind: str):
    def preview(change: dict, creds: dict) -> dict:
        with _GTM_LOCK:
            service = build_gtm_service(creds)
            workspace_path = _resolve_workspace(service, change)
            body = _entity_body(change, kind)
            existing = _find_by_name(service, kind, workspace_path, body["name"])
        label = _ENTITY_KINDS[kind]["label"]
        action = "Update" if existing else "Create"
        return {
            "current": {
                "workspace_path": workspace_path,
                "existing": existing or {},
                "exists": existing is not None,
            },
            "diff": (
                f"{action} {label.lower()} '{body['name']}' (type {body['type']}) in "
                f"workspace {workspace_path} — workspace only, production unchanged "
                "until a publish"
            ),
            "warnings": [],
            "mutate_payload": body,
        }

    return preview


def _upsert_apply(kind: str):
    def apply(change: dict, creds: dict) -> dict:
        with _GTM_LOCK:
            service = build_gtm_service(creds)
            workspace_path = _resolve_workspace(service, change)
            body = _entity_body(change, kind)
            # Re-find at apply time — the preview snapshot may be stale.
            existing = _find_by_name(service, kind, workspace_path, body["name"])
            collection = _entities(service, kind, workspace_path)
            try:
                if existing is None:
                    created = collection.create(parent=workspace_path, body=body).execute()
                    return {
                        "created": created.get("path", ""),
                        "rollback": {"delete_path": created.get("path", "")},
                    }
                updated = collection.update(path=existing["path"], body=body).execute()
                return {
                    "updated": updated.get("path", ""),
                    "rollback": {"restore_path": existing["path"], "restore_body": existing},
                }
            except Exception as exc:
                raise _translate(exc) from exc

    return apply


def _upsert_rollback(kind: str):
    def rollback(change: dict, creds: dict) -> dict:
        handle = ((change.get("result") or {}).get("rollback")) or {}
        delete_path = str(handle.get("delete_path") or "")
        restore_path = str(handle.get("restore_path") or "")
        restore_body = handle.get("restore_body")
        with _GTM_LOCK:
            service = build_gtm_service(creds)
            # The collection resource only needs the entity path from here on.
            collection = _entities(service, kind, delete_path or restore_path)
            try:
                if delete_path:
                    collection.delete(path=delete_path).execute()
                    return {"deleted": delete_path}
                if restore_path and restore_body:
                    restored = collection.update(path=restore_path, body=restore_body).execute()
                    return {"restored": restored.get("path", "")}
            except Exception as exc:
                raise _translate(exc) from exc
        raise ValueError("No rollback handle recorded for this change")

    return rollback


# ---------------------------------------------------------------------------
# gtm.publish_version — DESTRUCTIVE: changes the live site for every visitor
# ---------------------------------------------------------------------------

def _publish_preview(change: dict, creds: dict) -> dict:
    with _GTM_LOCK:
        service = build_gtm_service(creds)
        workspace_path = _resolve_workspace(service, change)
        container_path = _container_path_of(workspace_path)
        live_id = _live_version_id(service, container_path)
    name = str((change.get("payload") or {}).get("name") or "").strip()
    warnings = []
    if not live_id:
        warnings.append(
            "This container has no live version yet — after publishing, rollback "
            "has nothing to republish."
        )
    return {
        "current": {"workspace_path": workspace_path, "live_version_id": live_id},
        "diff": (
            f"Create a container version from workspace {workspace_path} and PUBLISH it"
            + (f" as '{name}'" if name else "")
            + f" — replaces live version {live_id or '(none)'} for every visitor"
        ),
        "warnings": warnings,
        "mutate_payload": {
            "name": name,
            "notes": str((change.get("payload") or {}).get("notes") or ""),
        },
    }


def _publish_apply(change: dict, creds: dict) -> dict:
    payload = change.get("payload") or {}
    with _GTM_LOCK:
        service = build_gtm_service(creds)
        workspace_path = _resolve_workspace(service, change)
        container_path = _container_path_of(workspace_path)

        # Record the rollback target FIRST — the outgoing live version, captured
        # immediately before the publish, not from the (possibly stale) preview.
        prior_live_version_id = _live_version_id(service, container_path)

        try:
            created = (
                service.accounts()
                .containers()
                .workspaces()
                .create_version(
                    path=workspace_path,
                    body={
                        "name": str(payload.get("name") or ""),
                        "notes": str(payload.get("notes") or ""),
                    },
                )
                .execute()
            )
        except Exception as exc:
            raise _translate(exc) from exc
        if created.get("compilerError"):
            raise RuntimeError(
                "GTM refused to create the version: compiler error in the workspace. "
                "Nothing was published."
            )
        version = created.get("containerVersion") or {}
        version_path = version.get("path", "")
        if not version_path:
            raise RuntimeError(
                f"GTM version creation returned no version (syncStatus: {created.get('syncStatus')})"
            )

        try:
            published = (
                service.accounts().containers().versions().publish(path=version_path).execute()
            )
        except Exception as exc:
            raise _translate(exc) from exc

    published_version = published.get("containerVersion") or version
    return {
        "published_version_id": str(published_version.get("containerVersionId") or ""),
        "published_version_path": published_version.get("path", version_path),
        "rollback": {
            "container_path": container_path,
            "prior_live_version_id": prior_live_version_id,
        },
    }


def _publish_rollback(change: dict, creds: dict) -> dict:
    handle = ((change.get("result") or {}).get("rollback")) or {}
    container_path = str(handle.get("container_path") or "")
    prior_id = str(handle.get("prior_live_version_id") or "")
    if not container_path:
        raise ValueError("No rollback handle recorded for this change")
    if not prior_id:
        raise ValueError(
            "The container had no live version before this publish — there is "
            "nothing to republish. Fix forward in GTM instead."
        )
    with _GTM_LOCK:
        service = build_gtm_service(creds)
        try:
            republished = (
                service.accounts()
                .containers()
                .versions()
                .publish(path=f"{container_path}/versions/{prior_id}")
                .execute()
            )
        except Exception as exc:
            raise _translate(exc) from exc
    version = republished.get("containerVersion") or {}
    return {"republished_version_id": str(version.get("containerVersionId") or prior_id)}


# ---------------------------------------------------------------------------
# gtm.rollback_to_version — DESTRUCTIVE: republishes an older version
# ---------------------------------------------------------------------------

def _rollback_to_preview(change: dict, creds: dict) -> dict:
    version_id = str(_require(change, "payload", "version_id"))
    with _GTM_LOCK:
        service = build_gtm_service(creds)
        container_path = _container_path(change)
        live_id = _live_version_id(service, container_path)
    warnings = []
    if live_id == version_id:
        warnings.append(f"Version {version_id} is already live — applying is a no-op.")
    return {
        "current": {"live_version_id": live_id},
        "diff": (
            f"Republish container version {version_id} on {container_path} "
            f"(replacing live version {live_id or '(none)'}) for every visitor"
        ),
        "warnings": warnings,
        "mutate_payload": {"publish": f"{container_path}/versions/{version_id}"},
    }


def _rollback_to_apply(change: dict, creds: dict) -> dict:
    version_id = str(_require(change, "payload", "version_id"))
    with _GTM_LOCK:
        service = build_gtm_service(creds)
        container_path = _container_path(change)
        # Record-rollback-target-first: the outgoing live version.
        prior_live_version_id = _live_version_id(service, container_path)
        try:
            published = (
                service.accounts()
                .containers()
                .versions()
                .publish(path=f"{container_path}/versions/{version_id}")
                .execute()
            )
        except Exception as exc:
            raise _translate(exc) from exc
    version = published.get("containerVersion") or {}
    return {
        "published_version_id": str(version.get("containerVersionId") or version_id),
        "rollback": {
            "container_path": container_path,
            "prior_live_version_id": prior_live_version_id,
        },
    }


register_executor(
    ExecutorSpec(
        op_type="gtm.upsert_tag",
        connector_type="gtm",
        label="Create/update GTM tag (workspace)",
        preview=_upsert_preview("tag"),
        apply=_upsert_apply("tag"),
        rollback=_upsert_rollback("tag"),
    )
)

register_executor(
    ExecutorSpec(
        op_type="gtm.upsert_variable",
        connector_type="gtm",
        label="Create/update GTM variable (workspace)",
        preview=_upsert_preview("variable"),
        apply=_upsert_apply("variable"),
        rollback=_upsert_rollback("variable"),
    )
)

register_executor(
    ExecutorSpec(
        op_type="gtm.publish_version",
        connector_type="gtm",
        label="Publish GTM container version",
        preview=_publish_preview,
        apply=_publish_apply,
        rollback=_publish_rollback,
        destructive=True,
    )
)

register_executor(
    ExecutorSpec(
        op_type="gtm.rollback_to_version",
        connector_type="gtm",
        label="Republish an older GTM version",
        preview=_rollback_to_preview,
        apply=_rollback_to_apply,
        rollback=_publish_rollback,
        destructive=True,
    )
)
