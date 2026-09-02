"""Clarity read pull + connector registration — what paid clicks do after landing.

Normalises the Data Export API's metric list into four blocks the agent can
reason about without knowing Clarity's casing quirks:

- ``traffic``      — sessions, bot sessions, distinct users, pages/session
- ``engagement``   — average scroll depth, total/active engagement time
- ``friction``     — dead clicks, rage clicks, quick-backs, excessive scroll,
                     script errors, error clicks: sessions affected + share
- ``pages``        — popular pages, plus the friction breakdown per URL

Budget rule: one pull = two API calls (overall + URL dimension) out of the
ten the project gets per day. The window is whatever Clarity allows (≤3
days) — the ``days`` argument is clamped, never trusted.
"""

from __future__ import annotations

import logging
from typing import Any

from service.clarity import client as cl
from service.connectors import (
    CAP_ACCOUNTS,
    ConnectorAuthContext,
    ConnectorMeta,
    register_connector,
)

logger = logging.getLogger(__name__)

_FRICTION = {
    "DeadClickCount": "dead_clicks",
    "RageClickCount": "rage_clicks",
    "QuickbackClick": "quick_backs",
    "ExcessiveScroll": "excessive_scroll",
    "ScriptErrorCount": "script_errors",
    "ErrorClickCount": "error_clicks",
}


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _lower(row: dict) -> dict[str, Any]:
    return {str(k).lower(): v for k, v in (row or {}).items()}


def _first(rows: list[dict]) -> dict[str, Any]:
    return _lower(rows[0]) if rows else {}


def normalise(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """The metric list → {traffic, engagement, friction, pages}."""
    by_name = {str(m.get("metricName") or ""): list(m.get("information") or []) for m in metrics}

    traffic = _first(by_name.get("Traffic", []))
    scroll = _first(by_name.get("ScrollDepth", []))
    engaged = _first(by_name.get("EngagementTime", []))

    friction: dict[str, dict[str, Any]] = {}
    for metric, key in _FRICTION.items():
        row = _first(by_name.get(metric, []))
        friction[key] = {
            "sessions": int(_num(row.get("sessionscount"))),
            "sessions_pct": round(_num(row.get("sessionswithmetricpercentage")), 2),
            "page_views": int(_num(row.get("pagesviews"))),
            "total": int(_num(row.get("subtotal"))),
        }

    pages = [
        {"url": str(_lower(r).get("url") or ""), "visits": int(_num(_lower(r).get("visitscount")))}
        for r in by_name.get("PopularPages", [])
    ]

    return {
        "traffic": {
            "sessions": int(_num(traffic.get("totalsessioncount"))),
            "bot_sessions": int(_num(traffic.get("totalbotsessioncount"))),
            "distinct_users": int(_num(traffic.get("distinctusercount"))),
            "pages_per_session": round(_num(traffic.get("pagespersessionpercentage")), 2),
        },
        "engagement": {
            "avg_scroll_depth_pct": round(_num(scroll.get("averagescrolldepth")), 2),
            "total_time_seconds": int(_num(engaged.get("totaltime"))),
            "active_time_seconds": int(_num(engaged.get("activetime"))),
        },
        "friction": friction,
        "pages": pages,
    }


def friction_by_url(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-URL friction rows from a ``dimension1=URL`` call."""
    rows: dict[str, dict[str, Any]] = {}
    for metric in metrics:
        key = _FRICTION.get(str(metric.get("metricName") or ""))
        if not key:
            continue
        for raw in metric.get("information") or []:
            row = _lower(raw)
            url = str(row.get("url") or "")
            if not url:
                continue
            entry = rows.setdefault(url, {"url": url})
            entry[key] = int(_num(row.get("sessionscount")))
            entry[f"{key}_pct"] = round(_num(row.get("sessionswithmetricpercentage")), 2)
    return sorted(rows.values(), key=lambda r: -(r.get("rage_clicks", 0) + r.get("dead_clicks", 0)))


def fetch_clarity(creds: dict[str, str], days: int = 3) -> dict[str, Any]:
    cl.require_credentials(creds)
    num_days = max(1, min(int(days or 1), cl.MAX_DAYS))
    out: dict[str, Any] = {}
    errors: dict[str, str] = {}
    calls = 0

    overall: dict[str, Any] = {}
    try:
        metrics = cl.live_insights(creds, num_days)
        calls += 1
        overall = normalise(metrics)
        out.update(overall)
    except cl.ApiError as exc:
        errors["live_insights"] = str(exc)[:500]
        logger.warning("clarity live insights failed: %s", exc)

    if "live_insights" not in errors:
        try:
            by_url = cl.live_insights(creds, num_days, ["URL"])
            calls += 1
            out = {**out, "friction_by_url": friction_by_url(by_url)}
        except cl.ApiError as exc:
            errors["friction_by_url"] = str(exc)[:500]
            logger.warning("clarity per-URL insights failed: %s", exc)

    friction = overall.get("friction") or {}
    return {
        "api": f"clarity-{cl.API_VERSION}",
        "project_id": str(creds.get("project_id") or ""),
        "window": {"days": num_days, "note": "Clarity exports only the last 1–3 days."},
        "summary": {
            "sessions": (overall.get("traffic") or {}).get("sessions", 0),
            "rage_click_sessions_pct": (friction.get("rage_clicks") or {}).get("sessions_pct", 0),
            "dead_click_sessions_pct": (friction.get("dead_clicks") or {}).get("sessions_pct", 0),
            "quick_back_sessions_pct": (friction.get("quick_backs") or {}).get("sessions_pct", 0),
            "script_error_sessions_pct": (friction.get("script_errors") or {}).get("sessions_pct", 0),
            "api_calls_spent": calls,
            "daily_budget": cl.DAILY_REQUEST_BUDGET,
        },
        "data": out,
        "errors": errors,
    }


class ClarityConnector:
    """Manual API-token connector. Verification spends 1 of the 10 daily calls."""

    def list_accounts(self, auth: ConnectorAuthContext) -> list[dict[str, Any]]:
        creds = dict(auth.extras)
        cl.require_credentials(creds)  # ValueError → 422 upstream
        try:
            cl.live_insights(creds, 1)
        except cl.ApiError as exc:
            if exc.status in (401, 403):
                raise ValueError(exc.hint() or str(exc)) from exc
            if exc.status == 429:
                raise RuntimeError(exc.hint()) from exc
            raise RuntimeError(str(exc)) from exc
        project_id = str(creds.get("project_id") or "").strip()
        return [
            {
                "account_id": project_id,
                "account_name": f"Clarity project {project_id}" if project_id else "Clarity project",
                "warning": (
                    f"Data Export allows {cl.DAILY_REQUEST_BUDGET} requests/day and covers only "
                    "the last 3 days — each Duct pull spends 2."
                ),
            }
        ]


CLARITY_META = ConnectorMeta(
    id="clarity",
    label="Microsoft Clarity",
    oauth_scope=None,  # project-scoped export token; Clarity has no OAuth
    capabilities=frozenset({CAP_ACCOUNTS}),
)

register_connector(CLARITY_META, ClarityConnector())
