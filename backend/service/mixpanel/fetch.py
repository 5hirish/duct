"""Mixpanel read pull + connector registration — the cross-platform event truth.

Every ad platform and GA4 sees a slice of the funnel under its own event
names; Mixpanel receives the raw name from web AND app SDKs. The engagement's
sharpest catch (GA4 dropping 174 web signups/month to a rename) only surfaced
because Mixpanel's count disagreed. That makes this pull the reconciliation
anchor for signup / login / upgrade counts.

Counting rules encoded:
- **Internal traffic is not filtered by Mixpanel.** ``internal_patterns`` on
  the credential (comma-separated distinct_id substrings) is applied as a
  ``where`` clause to every count and funnel; the patterns used are echoed in
  the summary so a number can never be quoted without its exclusion.
- Funnel results arrive per day. They are summed across the window and the
  conversion ratios recomputed — Mixpanel's per-day ratios do not average.
- Key events default to a name-pattern match (signup, sign_up, login, signin,
  purchase, upgrade, trial, checkout) over the project's top events; pass
  ``key_events`` on the credential to pin them.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any

from service.connectors import (
    CAP_ACCOUNTS,
    ConnectorAuthContext,
    ConnectorMeta,
    register_connector,
)
from service.mixpanel import client as mp

logger = logging.getLogger(__name__)

_KEY_EVENT_PATTERN = re.compile(
    r"sign.?up|sign.?in|log.?in|purchase|upgrade|trial|checkout|subscri|convert", re.I
)
MAX_FUNNELS = 5


def window(days: int) -> tuple[str, str]:
    """(from, to) ISO dates for the last N whole days, ending yesterday."""
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=max(days, 1) - 1)
    return start.isoformat(), end.isoformat()


def pick_key_events(creds: dict[str, str], names: list[str]) -> list[str]:
    pinned = [e.strip() for e in (creds.get("key_events") or "").split(",") if e.strip()]
    if pinned:
        return pinned
    matched = [n for n in names if _KEY_EVENT_PATTERN.search(n)]
    return matched[:10] or names[:10]


def summarise_counts(counts: dict) -> dict[str, int]:
    """{event: total over the window} from the ``events`` payload."""
    totals: dict[str, int] = {}
    for event, by_date in (counts.get("values") or {}).items():
        totals[str(event)] = int(sum(int(v or 0) for v in (by_date or {}).values()))
    return totals


def summarise_funnel(raw: dict) -> dict[str, Any]:
    """Sum a per-day funnel response into one set of steps with recomputed ratios."""
    step_counts: list[int] = []
    step_events: list[str] = []
    for _day, entry in (raw.get("data") or {}).items():
        for idx, step in enumerate(entry.get("steps") or []):
            if idx >= len(step_counts):
                step_counts.append(0)
                step_events.append(str(step.get("event") or step.get("goal") or f"step {idx + 1}"))
            step_counts[idx] += int(step.get("count") or 0)
    steps = []
    first = step_counts[0] if step_counts else 0
    for idx, count in enumerate(step_counts):
        prev = step_counts[idx - 1] if idx else count
        steps.append(
            {
                "event": step_events[idx],
                "count": count,
                "step_conversion": round(count / prev, 4) if prev else None,
                "overall_conversion": round(count / first, 4) if first else None,
            }
        )
    return {
        "steps": steps,
        "entered": first,
        "completed": step_counts[-1] if step_counts else 0,
        "completion_rate": (round(step_counts[-1] / first, 4) if first and step_counts else None),
    }


def fetch_mixpanel(creds: dict[str, str], days: int = 30) -> dict[str, Any]:
    mp.require_credentials(creds)
    project_id = mp.require_project_id(creds)
    from_date, to_date = window(days)
    patterns = mp.internal_patterns(creds)
    where = mp.internal_traffic_where(patterns)

    out: dict[str, Any] = {}
    errors: dict[str, str] = {}
    names: list[str] = []
    totals: dict[str, int] = {}

    try:
        names = mp.event_names(creds)
        out["top_events"] = names
    except mp.ApiError as exc:
        errors["event_names"] = str(exc)[:500]
        logger.warning("mixpanel event names failed: %s", exc)

    key_events = pick_key_events(creds, names)
    if key_events:
        try:
            counts = mp.event_counts(creds, key_events, from_date, to_date, where=where)
            totals = summarise_counts(counts)
            out["event_counts"] = {
                "events": key_events,
                "series": counts.get("series") or [],
                "values": counts.get("values") or {},
            }
        except mp.ApiError as exc:
            errors["event_counts"] = str(exc)[:500]
            logger.warning("mixpanel event counts failed: %s", exc)

    funnels: list[dict[str, Any]] = []
    try:
        for row in mp.funnels_list(creds)[:MAX_FUNNELS]:
            funnel_id = row.get("funnel_id") or row.get("id")
            if funnel_id is None:
                continue
            try:
                raw = mp.funnel(creds, funnel_id, from_date, to_date, where=where)
                funnels.append(
                    {
                        "funnel_id": funnel_id,
                        "name": row.get("name") or f"Funnel {funnel_id}",
                        **summarise_funnel(raw),
                    }
                )
            except mp.ApiError as exc:
                errors[f"funnel_{funnel_id}"] = str(exc)[:300]
        out["funnels"] = funnels
    except mp.ApiError as exc:
        errors["funnels"] = str(exc)[:500]
        logger.warning("mixpanel funnels failed: %s", exc)

    return {
        "api": f"mixpanel-{mp.QUERY_API_VERSION}",
        "project_id": project_id,
        "region": mp.region(creds),
        "window": {"from": from_date, "to": to_date, "days": days},
        "summary": {
            "key_events": key_events,
            "event_totals": totals,
            "funnels": [
                {"name": f["name"], "entered": f["entered"], "completed": f["completed"],
                 "completion_rate": f["completion_rate"]}
                for f in funnels
            ],
            "internal_traffic_excluded": patterns,
        },
        "data": out,
        "errors": errors,
    }


class MixpanelConnector:
    """Manual service-account connector (username + secret, project-scoped)."""

    def list_accounts(self, auth: ConnectorAuthContext) -> list[dict[str, Any]]:
        creds = dict(auth.extras)
        mp.require_credentials(creds)  # ValueError → 422 upstream
        try:
            profile = mp.me(creds)
        except mp.ApiError as exc:
            if exc.status in (401, 403):
                raise ValueError(exc.hint() or str(exc)) from exc
            raise RuntimeError(str(exc)) from exc
        results = profile.get("results") if isinstance(profile, dict) else None
        projects = (results or {}).get("projects") or {}
        rows: list[dict[str, Any]] = []
        for pid, meta in projects.items():
            meta = meta or {}
            rows.append(
                {
                    "account_id": str(meta.get("id") or pid),
                    "account_name": str(meta.get("name") or f"Project {pid}"),
                    "region": mp.region(creds),
                }
            )
        if not rows:
            raise ValueError(
                "This service account has no projects. Grant it the project under "
                "Organization settings → Service Accounts, then retry."
            )
        wanted = str(creds.get("project_id") or "").strip()
        if wanted and not any(r["account_id"] == wanted for r in rows):
            raise ValueError(
                f"Service account cannot access project {wanted}. It can read: "
                + ", ".join(f"{r['account_name']} ({r['account_id']})" for r in rows)
            )
        rows.sort(key=lambda r: r["account_name"].lower())
        return rows


MIXPANEL_META = ConnectorMeta(
    id="mixpanel",
    label="Mixpanel",
    oauth_scope=None,  # service account pair — Mixpanel has no third-party OAuth
    capabilities=frozenset({CAP_ACCOUNTS}),
    # The one manual connector that writes: the annotation and hide-event
    # executors act on the project. No scope to derive that from — a service
    # account pair carries its permissions out of band — so it is declared.
    access=frozenset({"read", "write"}),
)

register_connector(MIXPANEL_META, MixpanelConnector())
