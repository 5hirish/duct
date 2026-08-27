"""RevenueCat read pull + connector registration.

Ported from Gads ``fetch_revenuecat.py``. RevenueCat is the mobile
subscription truth: installs and in-app events are fire-and-forget signals
that cannot see refunds, billing retries, grace periods, or cancellations —
this source can.

PII rule from Gads: ``app_user_id`` values are SHA-256 hashed by default —
stable enough to join across pulls, useless for identifying a person.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from service.connectors import (
    CAP_ACCOUNTS,
    ConnectorAuthContext,
    ConnectorMeta,
    register_connector,
)
from service.revenuecat import client as rc

logger = logging.getLogger(__name__)


def _pull(out: dict, errors: dict, key: str, fn) -> list:
    try:
        rows = fn()
        out[key] = rows
        return rows
    except rc.ApiError as exc:
        errors[key] = exc.summary
        hint = exc.hint()
        if hint:
            errors[key] += f" → {hint}"
        logger.warning("revenuecat pull section %s failed: %s", key, exc.summary)
        if exc.code == 401:  # key itself rejected — everything else fails identically
            raise ValueError(f"RevenueCat rejected the key: {exc.summary}. {hint}") from exc
        return []
    except Exception as exc:  # noqa: BLE001 — never abort a long pull on one section
        errors[key] = str(exc)[:500]
        logger.warning("revenuecat pull section %s failed", key, exc_info=True)
        return []


def _hash_user_id(value: str) -> str:
    return hashlib.sha256((value or "").encode()).hexdigest()[:16]


def redact_customers(rows: list[dict]) -> list[dict]:
    """SHA-256 the app_user_id (PII rule) and keep only analytical fields."""
    out = []
    for row in rows:
        out.append({
            "id_hash": _hash_user_id(str(row.get("id") or "")),
            "first_seen_at": row.get("first_seen_at"),
            "last_seen_at": row.get("last_seen_at"),
            "last_seen_country": row.get("last_seen_country"),
            "last_seen_platform": row.get("last_seen_platform"),
            "active_entitlements": row.get("active_entitlements"),
        })
    return out


def fetch_revenuecat(creds: dict[str, str], days: int = 30) -> dict[str, Any]:
    """Project structure + overview metrics + redacted customer sample.

    ``days`` is accepted for interface parity; the overview metrics endpoint
    is snapshot-shaped (RevenueCat computes its own windows).
    """
    rc.require_credentials(creds)
    project_id = (creds.get("project_id") or "").strip()
    out: dict[str, Any] = {}
    errors: dict[str, str] = {}

    if not project_id:
        found = rc.projects(creds)
        if not found:
            raise ValueError("This RevenueCat key can reach no projects.")
        project_id = found[0].get("id", "")
        out["projects_visible"] = [{"id": p.get("id"), "name": p.get("name")} for p in found]
    base = f"projects/{project_id}"
    out["project_id"] = project_id

    _pull(out, errors, "apps", lambda: rc.get_all(f"{base}/apps", creds))
    _pull(out, errors, "products", lambda: rc.get_all(f"{base}/products", creds))
    _pull(out, errors, "entitlements", lambda: rc.get_all(f"{base}/entitlements", creds))
    _pull(out, errors, "offerings", lambda: rc.get_all(f"{base}/offerings", creds))

    # Overview metrics — the tight 25/min budget domain; throttled.
    _pull(out, errors, "metrics_overview",
          lambda: [rc.api(f"{base}/metrics/overview", creds, throttle=True)])

    customers = _pull(out, errors, "customers",
                      lambda: rc.get_all(f"{base}/customers", creds, cap=500))
    out["customers"] = redact_customers(customers)
    out["customers_redacted"] = True

    metrics = ((out.get("metrics_overview") or [{}])[0] or {}).get("metrics") or []
    summary = {m.get("id"): m.get("value") for m in metrics if isinstance(m, dict)}
    if summary:
        summary["note"] = (
            "RevenueCat reports settled subscription state (incl. refunds, "
            "grace periods, billing retries) — reconcile ad-platform "
            "conversions against this, never the reverse."
        )

    return {
        "api": "revenuecat-v2",
        "project_id": project_id,
        "days": days,
        "summary": summary,
        "data": out,
        "errors": errors,
    }


class RevenueCatConnector:
    """Manual v2 secret-key connector (OAuth exists but registration is a
    support-email process — deferred)."""

    def list_accounts(self, auth: ConnectorAuthContext) -> list[dict[str, Any]]:
        creds = dict(auth.extras)
        rc.require_credentials(creds)  # ValueError → 422 upstream
        try:
            rows = rc.projects(creds)
        except rc.ApiError as exc:
            if exc.code in (401, 403):
                raise ValueError(f"RevenueCat rejected the key: {exc.summary}. {exc.hint()}") from exc
            raise RuntimeError(f"RevenueCat project listing failed: {exc}") from exc
        return [
            {"account_id": p.get("id", ""), "account_name": p.get("name", "") or p.get("id", "")}
            for p in rows
        ]


REVENUECAT_META = ConnectorMeta(
    id="revenuecat",
    label="RevenueCat",
    oauth_scope=None,  # manual secret key; OAuth registration is support-gated
    capabilities=frozenset({CAP_ACCOUNTS}),
)

register_connector(REVENUECAT_META, RevenueCatConnector())
