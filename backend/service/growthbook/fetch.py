"""GrowthBook read pull + connector registration — is the experiment alive?

Normalises experiments into what an operator needs to decide anything:
status, phases with dates, variations, and — for running experiments — the
results envelope reduced to per-metric per-variation users and conversion.

Encoded lesson (Gads F9): "running" is a setting. Two experiments ran 92
days, showed running throughout, and bucketed nobody after day 14 because a
datasource query edit broke the exposure predicate. So every running
experiment gets a ``stale_running`` flag when its current phase started more
than ``STALE_AFTER_DAYS`` ago and no result window reaches the last week —
the agent is told to verify exposures are still arriving before citing it.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from service.connectors import (
    CAP_ACCOUNTS,
    ConnectorAuthContext,
    ConnectorMeta,
    register_connector,
)
from service.growthbook import client as gb

logger = logging.getLogger(__name__)

STALE_AFTER_DAYS = 45
MAX_RESULTS = 10


def _iso_day(value: Any) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return str(value)[:10]


def slim_experiment(e: dict) -> dict[str, Any]:
    phases = [
        {
            "name": p.get("name") or "",
            "started": _iso_day(p.get("dateStarted")),
            "ended": _iso_day(p.get("dateEnded")),
            "coverage": p.get("coverage"),
        }
        for p in (e.get("phases") or [])
    ]
    return {
        "id": e.get("id") or "",
        "name": e.get("name") or "",
        "status": e.get("status") or "",
        "project": e.get("project") or "",
        "archived": bool(e.get("archived")),
        "hypothesis": (e.get("hypothesis") or "")[:300],
        "variations": [v.get("name") or v.get("key") or "" for v in (e.get("variations") or [])],
        "phases": phases,
        "updated": _iso_day(e.get("dateUpdated")),
    }


def summarise_results(raw: dict) -> dict[str, Any]:
    """The results envelope → per-metric rows of {variation, users, conversion}."""
    result = raw.get("result") or raw
    metrics_out = []
    for metric in result.get("metrics") or []:
        variations = []
        for v in metric.get("variations") or []:
            analyses = v.get("analyses") or []
            head = analyses[0] if analyses else {}
            users = int(v.get("users") or 0)
            numerator = head.get("numerator")
            denominator = head.get("denominator") or users
            rate = None
            if numerator is not None and denominator:
                rate = round(float(numerator) / float(denominator), 4)
            variations.append(
                {
                    "variation_id": v.get("variationId"),
                    "users": users,
                    "conversion_rate": rate,
                    "mean": head.get("mean"),
                    "chance_to_win": head.get("chanceToWin"),
                }
            )
        metrics_out.append({"metric_id": metric.get("metricId") or "", "variations": variations})
    return {
        "status": result.get("status") or "",
        "start": _iso_day(result.get("startDate")),
        "end": _iso_day(result.get("endDate")),
        "metrics": metrics_out,
    }


def stale_running(exp: dict[str, Any], results: dict[str, Any] | None, today: date | None = None) -> bool:
    """Running, started long ago, and no result window touching the last week."""
    if exp.get("status") != "running":
        return False
    today = today or datetime.now(timezone.utc).date()
    phases = exp.get("phases") or []
    started = phases[-1].get("started") if phases else ""
    if not started:
        return False
    try:
        age = (today - date.fromisoformat(started)).days
    except ValueError:
        return False
    if age < STALE_AFTER_DAYS:
        return False
    end = (results or {}).get("end") or ""
    try:
        recent = end and (today - date.fromisoformat(end)).days <= 7
    except ValueError:
        recent = False
    return not recent


def fetch_growthbook(creds: dict[str, str], days: int = 30) -> dict[str, Any]:
    gb.require_credentials(creds)
    project_id = str(creds.get("project_id") or "").strip()
    errors: dict[str, str] = {}
    experiments: list[dict[str, Any]] = []
    params = {"projectId": project_id} if project_id else None

    try:
        experiments = [slim_experiment(e) for e in gb.get_all("experiments", "experiments", creds, params)]
    except gb.ApiError as exc:
        errors["experiments"] = str(exc)[:500]
        logger.warning("growthbook experiments pull failed: %s", exc)

    running = [e for e in experiments if e["status"] == "running" and not e["archived"]]
    results: dict[str, Any] = {}
    for exp in running[:MAX_RESULTS]:
        try:
            results[exp["id"]] = summarise_results(gb.api(f"experiments/{exp['id']}/results", creds))
        except gb.ApiError as exc:
            errors[f"results_{exp['id']}"] = str(exc)[:300]

    experiments = [
        {**exp, "stale_running": stale_running(exp, results.get(exp["id"]))} for exp in experiments
    ]

    feature_count = 0
    try:
        feature_count = len(gb.get_all("features", "features", creds, params))
    except gb.ApiError as exc:
        errors["features"] = str(exc)[:300]

    out: dict[str, Any] = {
        "experiments": experiments,
        "results": results,
        "feature_count": feature_count,
    }

    return {
        "api": gb.API_VERSION,
        "project_id": project_id,
        "window": {"days": days, "note": "Experiment results cover each experiment's own analysis window."},
        "summary": {
            "experiments": len(experiments),
            "running": len(running),
            "stale_running": [e["name"] for e in experiments if e.get("stale_running")],
            "stopped": sum(1 for e in experiments if e["status"] == "stopped"),
            "feature_count": feature_count,
        },
        "data": out,
        "errors": errors,
    }


class GrowthBookConnector:
    """Manual API-key connector; accounts are GrowthBook projects."""

    def list_accounts(self, auth: ConnectorAuthContext) -> list[dict[str, Any]]:
        creds = dict(auth.extras)
        gb.require_credentials(creds)  # ValueError → 422 upstream
        try:
            projects = gb.get_all("projects", "projects", creds)
        except gb.ApiError as exc:
            if exc.status in (401, 403):
                raise ValueError(exc.hint() or str(exc)) from exc
            raise RuntimeError(str(exc)) from exc
        rows = [{"account_id": "", "account_name": "All projects"}]
        for p in projects:
            rows.append({"account_id": str(p.get("id") or ""), "account_name": str(p.get("name") or p.get("id") or "")})
        return rows


GROWTHBOOK_META = ConnectorMeta(
    id="growthbook",
    label="GrowthBook",
    oauth_scope=None,  # API key — GrowthBook has no third-party OAuth
    capabilities=frozenset({CAP_ACCOUNTS}),
)

register_connector(GROWTHBOOK_META, GrowthBookConnector())
