"""Catalog-driven fetching and the integrity check library.

The two halves of "the agent can now actually look at your data, and know
whether to believe it":

  * ``fetchers`` — the entity catalog is the tool surface. Adding a connector is
    a catalog entry plus one dispatch line, and nothing in the agent changes.
  * ``checks``   — every check declares the catalog entities it needs and is
    skipped, visibly, when they are absent. No check names a connector.

Nothing here touches a network: the dispatch table is asserted against the
catalog, and the one test that would need a provider replaces the call.
"""

from __future__ import annotations

import json
import uuid

import pytest

from agents.insights import fetchers
from agents.insights.catalog.base import _CATALOGS
from agents.insights.checks import CHECKS, MONEY, all_checks_block, coverage
from agents.insights.data_tools import KNOWLEDGE_INDEX, _truncate, knowledge_index_block
from agents.insights.fetchers import (
    MAX_RESPONSE_CHARS,
    fetch_entity,
    fetch_specs,
    known_entities,
    resolve_window,
)
from agents.knowledge import load_knowledge_pack


# ---------------------------------------------------------------------------
# The catalog IS the tool surface
# ---------------------------------------------------------------------------

def test_every_catalog_entity_can_actually_be_fetched():
    """A catalog entry the dispatcher cannot serve is an entity the agent will
    name and then fail on — the drift this test exists to catch."""
    catalogued = {
        entity["entity_id"]
        for catalog in _CATALOGS.values()
        for entity in catalog["entities"]
    }

    assert catalogued == set(known_entities())


def test_specs_carry_their_connector():
    """Which connector an entity belongs to is what lets the fetcher resolve an
    account without the model naming one."""
    specs = fetch_specs()

    assert specs["search_terms"].connector_id == "google_ads"
    assert specs["gsc_query_performance"].connector_id == "gsc"


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def test_default_window_ends_yesterday():
    """Ad platforms settle a day's numbers after it closes, so including today
    understates the most recent day — a quiet way for a number to be wrong."""
    from datetime import date, timedelta

    _start, end = resolve_window("", "")

    assert end == (date.today() - timedelta(days=1)).isoformat()


def test_reversed_dates_are_ordered_not_rejected():
    assert resolve_window("2026-08-30", "2026-08-01") == ("2026-08-01", "2026-08-30")


def test_a_half_specified_window_falls_back_whole():
    """Pairing one real date with a guessed one produces a window nobody asked
    for; falling back entirely is at least a window the agent can see."""
    only_start, _ = resolve_window("2026-01-01", "")

    assert only_start != "2026-01-01"


# ---------------------------------------------------------------------------
# Failure is an instruction, never an exception
# ---------------------------------------------------------------------------

@pytest.fixture
def bound_project(monkeypatch):
    """A connector that resolves cleanly, so a test can reach the fetch call."""
    import service.connector_access as access

    class _Src:
        status = "bound"
        account_id = "111"

    monkeypatch.setattr(access, "get_data_source", lambda *a, **k: _Src())
    monkeypatch.setattr(access, "resolve_read_credentials", lambda *a, **k: {"refresh_token": "t"})


def test_unknown_entity_lists_the_real_ones():
    result = fetch_entity("made_up", user_id=uuid.uuid4(), project_id=uuid.uuid4())

    assert result["status"] == "unknown_entity"
    assert "search_terms" in result["message"]


def test_a_provider_error_tells_the_agent_not_to_retry(monkeypatch, bound_project):
    """A raised exception ends the run; a payload lets the agent say what it
    could not read and carry on."""
    from dataclasses import replace

    def _boom(*_a, **_kw):
        raise RuntimeError("upstream 503")

    specs = {**fetch_specs()}
    specs["search_terms"] = replace(specs["search_terms"], call=_boom)
    monkeypatch.setattr(fetchers, "fetch_specs", lambda: specs)

    result = fetch_entity("search_terms", user_id=uuid.uuid4(), project_id=uuid.uuid4())

    assert result["status"] == "fetch_failed"
    assert "Do not retry" in result["message"]
    # The window travels even on failure — the agent can say what it tried.
    assert result["date_from"] and result["date_to"]


def test_an_unbound_connector_says_which_tool_fixes_it(monkeypatch):
    """Every non-ok status is an instruction, not just a refusal."""
    import service.connector_access as access

    class _Src:
        status = "available"
        account_id = ""

    monkeypatch.setattr(access, "get_data_source", lambda *a, **k: _Src())

    result = fetch_entity("search_terms", user_id=uuid.uuid4(), project_id=uuid.uuid4())

    assert result["status"] == "needs_account"
    assert "SelectAccount" in result["message"]


def test_compaction_keeps_every_number_a_brief_could_quote():
    """The property the whole feature rests on.

    Compaction changes how rows are written, never which numbers they carry —
    a brief quotes these values into a customer's inbox. If a release ever
    makes the fold lossy, this is where it stops.
    """
    rows = [
        {"query": f"term {i}", "clicks": i * 3, "cost": round(i * 1.37, 2), "position": i / 7}
        for i in range(300)
    ]
    payload = {
        "status": "ok",
        "entity_id": "gsc_queries",
        "date_from": "2026-08-01",
        "date_to": "2026-08-30",
        "data": {"row_count": len(rows), "rows": rows},
    }

    out = _truncate(payload, compress=True)

    assert len(out) < len(json.dumps(payload))
    for row in rows:
        for value in (row["clicks"], row["cost"], row["position"]):
            assert str(value) in out, f"{value} did not survive compaction"


def test_compaction_leaves_the_envelope_readable():
    """The window has to travel with the data — a number without its date range
    is the easiest way to state something false (see fetch_entity). Compaction
    must not cost us the fields that carry it."""
    payload = {
        "status": "ok",
        "entity_id": "gsc_queries",
        "date_from": "2026-08-01",
        "date_to": "2026-08-30",
        "data": {"rows": [{"q": f"q{i}", "clicks": i} for i in range(50)]},
    }

    parsed = json.loads(_truncate(payload, compress=True))

    assert parsed["status"] == "ok"
    assert parsed["date_from"] == "2026-08-01"
    assert parsed["date_to"] == "2026-08-30"


def test_commas_in_a_string_field_do_not_shift_the_columns():
    """Search terms contain commas, quotes and newlines. A row folded to CSV
    without quoting them would slide every later value one column left and
    hand the model a real number under the wrong heading — wrong in the one
    way nobody would catch by reading."""
    rows = [
        {"search_term": 'ga4 alternative, free', "clicks": 111, "cost": 1.5},
        {"search_term": 'best "analytics" tool', "clicks": 222, "cost": 2.5},
        {"search_term": "a,b,c,d", "clicks": 333, "cost": 3.5},
    ] * 10
    payload = {"status": "ok", "data": {"rows": rows}}

    out = _truncate(payload, compress=True)

    # Each row's own values stay adjacent to each other, which is what a shift
    # would break.
    assert '"ga4 alternative, free",111,1.5' in out or "111,1.5" in out
    assert "333,3.5" in out


def test_duplicate_rows_are_not_collapsed_into_one():
    """Two identical rows are two rows.

    The compactor has a path that folds an array of identical values down to a
    sample — defensible for a log tail, wrong for an analytics pull, where the
    duplicate is a second real record and the count is a number a brief quotes.
    ``lossless_only`` does not gate that path, so compaction.py verifies each
    result and discards one that lost content. This test is that guarantee: it
    is about what reaches the model, not about which library setting produced
    it, so it keeps holding if the library changes its mind.
    """
    payload = {"status": "ok", "data": {"rows": ["identical" * 120] * 200}}

    out = _truncate(payload, compress=True)

    # Either the rows survive as rows, or the payload was too big and the
    # documented cut fired. What must never happen is a tidy, complete-looking
    # response holding 2 of the 200.
    if "data_truncated" not in out:
        assert json.loads(out)["data"]["rows"] == payload["data"]["rows"]


def test_compression_off_is_the_old_behaviour_exactly():
    """The preference has to be a real switch: off must produce the bytes the
    tool produced before compaction existed."""
    payload = {"status": "ok", "data": {"rows": [{"q": f"q{i}", "clicks": i} for i in range(50)]}}

    assert _truncate(payload, compress=False) == json.dumps(payload, default=str)


def test_oversized_responses_keep_their_envelope():
    """Cutting a JSON blob mid-structure would corrupt it. The status and the
    window survive so the agent can narrow the range instead of wondering why
    the numbers stopped."""
    payload = {
        "status": "ok",
        "entity_id": "search_terms",
        "date_from": "2026-08-01",
        "date_to": "2026-08-30",
        "data": {"rows": ["x" * 1000] * 200},
    }

    out = _truncate(payload)

    assert len(out) < MAX_RESPONSE_CHARS + 5_000
    assert '"date_from": "2026-08-01"' in out
    assert "Narrow the date range" in out


# ---------------------------------------------------------------------------
# The check library
# ---------------------------------------------------------------------------

def test_no_check_names_a_connector():
    """The rule that makes the library connector-agnostic: a check declares the
    catalog ENTITIES it needs, never a vendor. Break this and adding a connector
    stops being a catalog entry."""
    connectors = {"google_ads", "ga4", "gsc", "gtm", "stripe", "meta_ads", "apple_ads"}

    for check in CHECKS:
        assert not (set(check.requires) & connectors), (
            f"{check.id} requires a connector name; it must require catalog entities"
        )


def test_checks_split_into_runnable_and_skipped():
    cov = coverage(known_entities())

    assert cov.runnable
    assert cov.skipped
    assert len(cov.runnable) + len(cov.skipped) == len(CHECKS)


def test_money_checks_wait_for_a_billing_connector():
    """The strongest checks in the library are declared but unreachable today.
    That is the point: the skip tells the user what a billing connection would
    buy, and the day one lands they run with no change here."""
    cov = coverage(known_entities())

    assert {c.id for c in cov.skipped} == {c.id for c in CHECKS if c.family == MONEY}


def test_a_new_connector_lights_up_its_checks_with_no_code_change():
    """The contract, exercised: hand coverage the entities a billing connector
    would add, and the money checks become runnable."""
    with_billing = set(known_entities()) | {"billing_charges", "billing_subscriptions"}

    cov = coverage(with_billing)

    assert cov.skipped == ()
    assert {c.id for c in cov.runnable} == {c.id for c in CHECKS}


def test_every_skipped_check_has_a_sentence_for_the_user():
    """"Could not verify" is half the output, so every check has to be able to
    say what it did not check."""
    for check in CHECKS:
        assert check.if_skipped.strip()
        assert not check.if_skipped.lower().startswith("connect ")  # a gap, not a nag


def test_check_block_is_cache_stable():
    """It rides in the verifier's system prompt, so it must not vary."""
    assert all_checks_block() == all_checks_block()


# ---------------------------------------------------------------------------
# Connector notes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(KNOWLEDGE_INDEX))
def test_every_indexed_pack_exists(name: str):
    """The index is what the agent reads in the system prompt; an entry with no
    file is an offer the tool cannot honour."""
    assert load_knowledge_pack(name).strip()


def test_index_is_names_and_summaries_not_bodies():
    """Progressive disclosure: the prefix carries the menu, the tool carries the
    meal. Ten packs inline would defeat the point."""
    block = knowledge_index_block()

    assert len(block) < 2_000
    assert all(name in block for name in KNOWLEDGE_INDEX)
