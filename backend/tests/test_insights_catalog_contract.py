"""The entity catalogs must describe what the fetchers actually return.

The catalog is the insights agent's map of the data: it names every field the
agent may reference and sort by. Nothing enforced that the names were real, so
they drifted — `service/google/gsc.py` renamed `position` to `avg_position`,
GA4's fetcher emits `page_path` and `total_revenue`, and the catalogs kept
advertising the old names. The agent was being told about fields that do not
exist in the rows it receives.

The 90-day staleness warning in `service/pipeline.py` was the only signal, and a
warning is advisory — it says "someone should look", not "this is wrong". These
tests make the drift fail instead.

Fields are matched against the string keys of dict literals in each connector's
fetcher module. That is deliberately loose: it cannot catch a field emitted
under a computed key, but it does catch the rename-one-side mistake that
actually happened, and it needs no credentials or network.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from agents.insights.catalog import get_catalog_for_connector, is_catalog_stale
from agents.insights.catalog.base import validate_catalog

BACKEND = Path(__file__).resolve().parent.parent

# Catalog -> the module whose returned dicts define that connector's row shape.
FETCHER_SOURCES = {
    "google_ads": ["service/google/fetch.py"],
    "ga4": ["service/google/ga4.py"],
    "gsc": ["service/google/gsc.py"],
}

CONNECTORS = sorted(FETCHER_SOURCES)


def _dict_literal_keys(*relative_paths: str) -> set[str]:
    keys: set[str] = set()
    for relative in relative_paths:
        tree = ast.parse((BACKEND / relative).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.add(key.value)
    return keys


@pytest.mark.parametrize("connector", CONNECTORS)
def test_catalog_is_structurally_valid(connector):
    validate_catalog(get_catalog_for_connector(connector))


@pytest.mark.parametrize("connector", CONNECTORS)
def test_declared_fields_are_actually_emitted(connector):
    """Every field the agent is told about must exist in the fetcher's rows."""
    catalog = get_catalog_for_connector(connector)
    emitted = _dict_literal_keys(*FETCHER_SOURCES[connector])

    for entity in catalog["entities"]:
        declared = {
            name
            for name, meta in entity["fields"].items()
            # `classification` fields are assigned by the agent, not fetched.
            if meta.get("type") != "classification"
        }
        missing = sorted(declared - emitted)
        assert not missing, (
            f"{connector}/{entity['entity_id']} declares {missing}, which "
            f"{', '.join(FETCHER_SOURCES[connector])} never emits. Either the "
            f"fetcher renamed a key or the catalog invented one."
        )


@pytest.mark.parametrize("connector", CONNECTORS)
def test_sortable_fields_are_declared(connector):
    """`sortable_by` is part of the same contract and drifted with the renames."""
    catalog = get_catalog_for_connector(connector)
    for entity in catalog["entities"]:
        undeclared = sorted(set(entity.get("sortable_by", [])) - set(entity["fields"]))
        assert not undeclared, f"{connector}/{entity['entity_id']} sorts by undeclared {undeclared}"


@pytest.mark.parametrize("connector", CONNECTORS)
def test_catalog_is_not_stale(connector):
    """Fails once a catalog passes the 90-day re-audit window.

    Deliberately a test and not just the startup warning: bumping `last_audited`
    should be a decision someone makes after re-checking the fields, not a line
    that scrolls past in a log every morning.
    """
    catalog = get_catalog_for_connector(connector)
    assert not is_catalog_stale(catalog), (
        f"{connector} catalog was last audited {catalog['last_audited']} "
        f"(today {date.today()}). Re-verify its fields and api_version against "
        f"{', '.join(FETCHER_SOURCES[connector])}, then bump last_audited."
    )
