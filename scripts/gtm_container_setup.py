#!/usr/bin/env python3
"""Provision Duct's GTM container from code, idempotently.

The container was clicked together by hand and it showed: a GA4 event tag was
waiting on a `form_submit` nothing pushed, six events the app *did* push had no
tag at all, and none of that was visible from the repository. A container you
cannot diff is a container nobody can audit.

So this is the source of truth. It creates the data-layer variables, one
catch-all trigger, and one GA4 event tag that forwards every event in
`EVENTS` with every parameter in `PARAMS`. Adding an event later means adding a
line here and re-running -- never clicking.

**Idempotent by name.** Anything already present is skipped, so re-running after
adding one event creates only the missing pieces. It writes to a workspace and
publishes nothing: review the diff in the GTM UI and submit it yourself.

Two gotchas worth knowing before editing:

* **GTM's regex is RE2, which has no lookahead.** "Every event except `gtm.*`"
  cannot be expressed, so the trigger matches an explicit union of `EVENTS`.
  An event missing from that list reaches the dataLayer and stops there.
* **Event parameters cannot be wildcarded.** Each is mapped by name on the tag,
  which is why `PARAMS` is a closed vocabulary rather than whatever a call site
  felt like sending.

Prerequisites:
    gcloud auth application-default login     # or GOOGLE_APPLICATION_CREDENTIALS
    # the account needs edit rights on the container

Run:
    cd backend && poetry run python ../scripts/gtm_container_setup.py
"""

from __future__ import annotations

import sys

import google.auth
from googleapiclient.discovery import build

CONTAINER_PUBLIC_ID = "GTM-PKL589SW"
GA4_MEASUREMENT_ID = "G-SXH5LYVTJ8"

SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers"]

# Every event Duct sends. The app half is `app/src/lib/analytics/index.js`
# (AnalyticsEvent); `download_started` comes from the marketing site, which
# shares no code with the app -- see `site/assets/duct-download.js`.
EVENTS = [
    "download_started",
    "sign_up",
    "connector_connected",
    "artifact_generated",
    "app_opened",
    "execution_approved",
    "team_member_invited",
    "execution_interest_submitted",
    # Attribution, pushed by site/assets/duct.js on every page.
    "utm_data",
]

# The closed parameter vocabulary (AnalyticsParam in the same module), plus the
# UTM fields. A parameter absent here is dropped on arrival at GA4.
PARAMS = [
    "method",
    "provider",
    "agent",
    "kind",
    "shell",
    "services",
    "os",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
]

TRIGGER_NAME = "Custom Event - Duct events"
TAG_NAME = "GA4 Event - Duct events"
CONFIG_TAG_NAME = "Google tag - Duct"


def log(message: str) -> None:
    sys.stdout.write(message + "\n")


def _param(key: str, value: str) -> dict:
    return {"type": "template", "key": key, "value": value}


def _dlv_ref(name: str) -> str:
    return f"{{{{DLV - {name}}}}}"


def main() -> int:
    credentials, _ = google.auth.default(scopes=SCOPES)
    gtm = build("tagmanager", "v2", credentials=credentials, cache_discovery=False)

    log("\n-- Finding container ------------------------------------------")
    container_path = None
    accounts = gtm.accounts().list().execute().get("account", [])
    for account in accounts:
        containers = (
            gtm.accounts().containers().list(parent=account["path"]).execute().get("container", [])
        )
        match = next((c for c in containers if c.get("publicId") == CONTAINER_PUBLIC_ID), None)
        if match:
            container_path = match["path"]
            log(f"  found {match.get('name')} ({container_path})")
            break

    if not container_path:
        log(
            f"\nContainer {CONTAINER_PUBLIC_ID} not found. The authenticated account "
            "needs edit access to it."
        )
        return 1

    workspaces = (
        gtm.accounts()
        .containers()
        .workspaces()
        .list(parent=container_path)
        .execute()
        .get("workspace", [])
    )
    workspace = next((w for w in workspaces if w.get("name") == "Default Workspace"), None)
    workspace = workspace or (workspaces[0] if workspaces else None)
    if not workspace:
        log("No workspace in the container.")
        return 1
    ws_path = workspace["path"]
    log(f"  workspace {workspace.get('name')}")

    variables_api = gtm.accounts().containers().workspaces().variables()
    triggers_api = gtm.accounts().containers().workspaces().triggers()
    tags_api = gtm.accounts().containers().workspaces().tags()

    existing_vars = {
        v["name"] for v in variables_api.list(parent=ws_path).execute().get("variable", [])
    }
    existing_triggers = {
        t["name"]: t["triggerId"]
        for t in triggers_api.list(parent=ws_path).execute().get("trigger", [])
    }
    existing_tags = {t["name"] for t in tags_api.list(parent=ws_path).execute().get("tag", [])}

    log("\n-- Data layer variables ---------------------------------------")
    for name in PARAMS:
        display = f"DLV - {name}"
        if display in existing_vars:
            log(f"  skip    {display}")
            continue
        variables_api.create(
            parent=ws_path,
            body={
                "name": display,
                "type": "v",
                "parameter": [
                    _param("name", name),
                    {"type": "integer", "key": "dataLayerVersion", "value": "2"},
                ],
            },
        ).execute()
        log(f"  created {display}")

    log("\n-- Trigger ----------------------------------------------------")
    if TRIGGER_NAME in existing_triggers:
        trigger_id = existing_triggers[TRIGGER_NAME]
        log(f"  skip    {TRIGGER_NAME}")
    else:
        created = triggers_api.create(
            parent=ws_path,
            body={
                "name": TRIGGER_NAME,
                "type": "CUSTOM_EVENT",
                "customEventFilter": [
                    {
                        "type": "matchRegex",
                        "parameter": [
                            _param("arg0", "{{_event}}"),
                            # A union, not `.*`: RE2 cannot express "not gtm.*",
                            # and a wildcard would forward GTM's own internals.
                            _param("arg1", "|".join(EVENTS)),
                        ],
                    }
                ],
            },
        ).execute()
        trigger_id = created["triggerId"]
        log(f"  created {TRIGGER_NAME}")

    log("\n-- Tags -------------------------------------------------------")
    if CONFIG_TAG_NAME in existing_tags:
        log(f"  skip    {CONFIG_TAG_NAME}")
    else:
        tags_api.create(
            parent=ws_path,
            body={
                "name": CONFIG_TAG_NAME,
                "type": "googtag",
                "parameter": [_param("tagId", GA4_MEASUREMENT_ID)],
                "firingTriggerId": ["2147479553"],  # built-in All Pages
            },
        ).execute()
        log(f"  created {CONFIG_TAG_NAME}")

    if TAG_NAME in existing_tags:
        log(f"  skip    {TAG_NAME}")
    else:
        tags_api.create(
            parent=ws_path,
            body={
                "name": TAG_NAME,
                "type": "gaawe",
                "parameter": [
                    # {{Event}} is GTM's built-in for the current dataLayer event
                    # name, so one tag serves every event in EVENTS.
                    _param("eventName", "{{Event}}"),
                    {
                        "type": "list",
                        "key": "eventParameters",
                        "list": [
                            {
                                "type": "map",
                                "map": [_param("name", p), _param("value", _dlv_ref(p))],
                            }
                            for p in PARAMS
                        ],
                    },
                ],
                "firingTriggerId": [trigger_id],
            },
        ).execute()
        log(f"  created {TAG_NAME}")

    log("\n-- Done -------------------------------------------------------")
    log("Nothing is published. Review the workspace and submit it yourself:")
    log(f"  https://tagmanager.google.com/#/container/{container_path}/workspaces/")
    log(
        "\nStill to remove by hand, because deleting is not this script's job:\n"
        "  - the Ahrefs Web Analytics custom HTML tag\n"
        "  - 'GA4 Event - form_submit', whose custom event nothing pushes\n"
        "  - the bespoke utm_data tag, now covered by the catch-all"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
