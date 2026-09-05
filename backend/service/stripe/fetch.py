"""Stripe read pull + connector registration — the "money truth" source.

Ported from Gads ``fetch_stripe.py``. Every ad platform reports *its own*
attributed conversions; Stripe reports money that actually settled. When they
disagree, Stripe wins.

Counting rules encoded — get these wrong and acquisition looks 2-3x better:
- A subscription in ``incomplete`` / ``incomplete_expired`` NEVER CHARGED:
  abandoned or failed checkout, not a sale. Excluded from every "new" count.
- ``metadata.change_type == "upgrade"`` is revenue expansion, not acquisition.
- Most successful charges are RENEWALS of the existing base — never read
  charge volume as acquisition.
- Refunds are netted out.
- Prices come off subscription ITEMS, not the legacy top-level ``plan``
  (null for multi-item subscriptions → silent $0).
- ``charge.invoice`` was REMOVED in the dahlia train — subscription payments
  link via payment_intent now; never infer "no invoice ⇒ not a renewal".
"""

from __future__ import annotations

import collections
import logging
from typing import Any

from service.connectors import (
    CAP_ACCOUNTS,
    ConnectorAuthContext,
    ConnectorMeta,
    entity_facts,
    register_connector,
)
from service.stripe import client as st

logger = logging.getLogger(__name__)


def slim_subscription(s: dict) -> dict:
    items = ((s.get("items") or {}).get("data")) or []
    prices = [i.get("price") or {} for i in items]
    legacy = s.get("plan") or {}
    currency = (prices[0].get("currency") if prices else None) or legacy.get("currency")
    nickname = (prices[0].get("nickname") if prices else None) or legacy.get("nickname")
    interval = ((prices[0].get("recurring") or {}).get("interval")
                if prices else None) or legacy.get("interval")
    if prices:
        minor = sum((p.get("unit_amount") or 0) * (i.get("quantity") or 1)
                    for p, i in zip(prices, items))
    else:
        minor = legacy.get("amount")
    md = s.get("metadata") or {}
    return {
        "id": s["id"],
        "created": s["created"],
        "day": st.day(s["created"]),
        "status": s["status"],
        "paid": s["status"] not in st.NEVER_PAID,
        "plan": nickname,
        "items": len(items) or 1,
        "amount": st.money(minor, currency),
        "currency": currency,
        "interval": interval,
        "change_type": md.get("change_type"),
        "canceled_at": s.get("canceled_at"),
    }


def slim_charge(c: dict) -> dict:
    return {
        "id": c["id"],
        "created": c["created"],
        "day": st.day(c["created"]),
        "status": c["status"],
        "amount": st.money(c.get("amount"), c.get("currency")),
        "refunded_amount": st.money(c.get("amount_refunded"), c.get("currency")),
        "currency": c.get("currency"),
        "paid": bool(c.get("paid")),
        "refunded": bool(c.get("refunded")),
        "payment_intent": c.get("payment_intent"),
        "customer": c.get("customer"),
        "failure_code": c.get("failure_code"),
    }


def summarise(subs: list[dict], charges: list[dict]) -> dict[str, Any]:
    """Everything downstream should read THIS, not the raw rows."""
    paid_new = [s for s in subs if s["paid"] and s["change_type"] != "upgrade"]
    upgrades = [s for s in subs if s["paid"] and s["change_type"] == "upgrade"]
    never = [s for s in subs if not s["paid"]]

    ok = [c for c in charges if c["status"] == "succeeded" and c["paid"]]
    gross = sum(c["amount"] for c in ok)
    refunded = sum(c["refunded_amount"] for c in ok)

    by_month: dict[str, dict] = collections.defaultdict(
        lambda: {"paid_new_subs": 0, "upgrades": 0, "never_paid": 0,
                 "gross": 0.0, "refunded": 0.0})
    for s in paid_new:
        by_month[st.month(s["created"])]["paid_new_subs"] += 1
    for s in upgrades:
        by_month[st.month(s["created"])]["upgrades"] += 1
    for s in never:
        by_month[st.month(s["created"])]["never_paid"] += 1
    for c in ok:
        m = by_month[st.month(c["created"])]
        m["gross"] += c["amount"]
        m["refunded"] += c["refunded_amount"]
    for m in by_month.values():
        m["gross"] = round(m["gross"], 2)
        m["refunded"] = round(m["refunded"], 2)

    return {
        "paid_new_subs": len(paid_new),
        "upgrades": len(upgrades),
        "never_paid_subs": len(never),
        "charges_succeeded": len(ok),
        "charges_failed": sum(1 for c in charges if c["status"] == "failed"),
        "gross_revenue": round(gross, 2),
        "refunded": round(refunded, 2),
        "net_revenue": round(gross - refunded, 2),
        "new_mrr_equivalent": round(
            sum(s["amount"] / (12 if s["interval"] == "year" else 1) for s in paid_new), 2),
        "by_month": dict(sorted(by_month.items())),
    }


def fetch_stripe(creds: dict[str, str], days: int = 30) -> dict[str, Any]:
    st.require_credentials(creds)
    gte, lte = st.window(days)

    out: dict[str, Any] = {}
    errors: dict[str, str] = {}
    subs: list[dict] = []
    charges: list[dict] = []
    try:
        subs = [slim_subscription(s) for s in st.get_all(
            "subscriptions", creds, {"created": {"gte": gte}, "status": "all"})]
        out["subscriptions"] = subs
    except st.ApiError as exc:
        errors["subscriptions"] = str(exc)[:500]
        logger.warning("stripe subscriptions pull failed: %s", exc)
    try:
        charges = [slim_charge(c) for c in st.get_all("charges", creds, {"created": {"gte": gte}})]
        out["charges"] = charges
    except st.ApiError as exc:
        errors["charges"] = str(exc)[:500]
        logger.warning("stripe charges pull failed: %s", exc)

    return {
        "api": f"stripe-{st.STRIPE_VERSION}",
        "window": {"gte": gte, "lte": lte, "days": days, "from": st.day(gte), "to": st.day(lte)},
        "summary": summarise(subs, charges),
        "data": out,
        "errors": errors,
    }


class StripeConnector:
    """Manual restricted-key connector (rk_live_… read key)."""

    def list_accounts(self, auth: ConnectorAuthContext) -> list[dict[str, Any]]:
        creds = dict(auth.extras)
        key = st.require_credentials(creds)  # ValueError → 422 upstream
        permissions = st.probe_permissions(creds)
        if all(v != "ok" for v in permissions.values()):
            raise ValueError(
                "Stripe rejected the key on every resource — check it was copied "
                "whole and grants read on Subscriptions, Charges, Invoices, "
                "Customers, Products, Prices."
            )
        name = "Stripe account"
        account_id = ""
        try:
            acct = st.api("account", creds)
            account_id = acct.get("id", "")
            name = (
                (acct.get("settings") or {}).get("dashboard", {}).get("display_name")
                or (acct.get("business_profile") or {}).get("name")
                or account_id or name
            )
        except st.ApiError:
            pass  # account read not granted — the probe already proved the key works
        readable = sorted(k for k, v in permissions.items() if v == "ok")
        row: dict[str, Any] = {
            "account_id": account_id,
            "account_name": name,
            # A restricted key is the norm here, so what it can actually read
            # is the useful fact about it — not that a key exists.
            "entity_meta": entity_facts(
                ("Readable", f"{len(readable)} of {len(permissions)} resources"),
            ),
            "permissions": permissions,
        }
        warning = st.key_warning(key)
        if warning:
            row["warning"] = warning
        return [row]


STRIPE_META = ConnectorMeta(
    id="stripe",
    label="Stripe",
    oauth_scope=None,  # restricted read key — Stripe Apps OAuth needs a published app
    capabilities=frozenset({CAP_ACCOUNTS}),
)

register_connector(STRIPE_META, StripeConnector())
