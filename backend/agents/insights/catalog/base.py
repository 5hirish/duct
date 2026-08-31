"""Catalog lookup and validation helpers."""

from __future__ import annotations

from datetime import date
from typing import Any

from agents.insights.catalog.ga4 import ENTITY_CATALOG as GA4_CATALOG
from agents.insights.catalog.google_ads import ENTITY_CATALOG as GOOGLE_ADS_CATALOG
from agents.insights.catalog.clarity import ENTITY_CATALOG as CLARITY_CATALOG
from agents.insights.catalog.growthbook import ENTITY_CATALOG as GROWTHBOOK_CATALOG
from agents.insights.catalog.gsc import ENTITY_CATALOG as GSC_CATALOG
from agents.insights.catalog.mixpanel import ENTITY_CATALOG as MIXPANEL_CATALOG

_CATALOGS: dict[str, dict[str, Any]] = {
    "google_ads": GOOGLE_ADS_CATALOG,
    "ga4": GA4_CATALOG,
    "gsc": GSC_CATALOG,
    "mixpanel": MIXPANEL_CATALOG,
    "clarity": CLARITY_CATALOG,
    "growthbook": GROWTHBOOK_CATALOG,
}


def validate_catalog(catalog: dict[str, Any]) -> None:
    required_top = {"connector_id", "schema_version", "last_audited", "api_version", "entities"}
    missing = sorted(required_top - set(catalog.keys()))
    if missing:
        raise ValueError(f"Catalog missing keys: {', '.join(missing)}")
    if not isinstance(catalog.get("entities"), list):
        raise ValueError("Catalog 'entities' must be a list")
    for entity in catalog["entities"]:
        for key in ("entity_id", "label", "tool", "description", "fields"):
            if key not in entity:
                raise ValueError(f"Entity missing '{key}' in {catalog.get('connector_id', 'unknown')}")


def get_catalog_for_connector(connector_id: str) -> dict[str, Any] | None:
    catalog = _CATALOGS.get((connector_id or "").strip().lower())
    if catalog:
        validate_catalog(catalog)
    return catalog


def get_catalogs_for_connectors(connector_ids: list[str]) -> list[dict[str, Any]]:
    catalogs: list[dict[str, Any]] = []
    for connector_id in connector_ids:
        catalog = get_catalog_for_connector(connector_id)
        if catalog:
            catalogs.append(catalog)
    return catalogs


def is_catalog_stale(catalog: dict[str, Any], max_days: int = 90) -> bool:
    last = date.fromisoformat(catalog.get("last_audited", "2000-01-01"))
    return (date.today() - last).days > max_days
