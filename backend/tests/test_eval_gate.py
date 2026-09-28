"""The eval gate's own plumbing, offline: the world, the checks, the verdicts.

A paid gate that is wrong about itself is worse than none: it teaches people
to re-run until green. So its arithmetic, its figure matching and its verdict
rules are pinned here for free, and one test drives a whole trial through the
real insights harness with a scripted model, the way the paid tier drives it
with a real one.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from langchain_core.messages import AIMessage

from agents.core.prompts import DUCT_ARTIFACT_CLOSE, DUCT_ARTIFACT_OPEN
from agents.insights import fetchers
from agents.insights.fetchers import resolve_window
from agents.models import Provider
from tests.conftest import make_sqlite_engine
from tests.eval.cases import CASES, cases_for
from tests.eval.cases.insights import ORGANIC
from tests.eval.cases.solo_world import SoloWorld
from tests.eval.gate import (
    FAIL,
    INCONCLUSIVE,
    PASS,
    Trial,
    decide,
    figures_in,
    quotes,
    run_trial,
)
from tests.fakes import ToolCallingFake

TODAY = date(2026, 9, 28)


def _window(days_ago_end: int, length: int) -> tuple[str, str]:
    end = TODAY - timedelta(days=days_ago_end)
    return (end - timedelta(days=length - 1)).isoformat(), end.isoformat()


def _organic(data: dict, page: str | None = None) -> int:
    return sum(r["sessions"] for r in data["rows"]
               if r["channel"] == "Organic Search" and (page is None or r["page_path"] == page))


# ---------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------

def test_two_halves_of_a_window_add_up_to_the_whole():
    """Any window is answered from the same daily series, so a model that asks
    for 28 days and one that asks for two 14s read the same account."""
    world = SoloWorld(today=TODAY)
    whole = _organic(world.ga4_landing_pages(*_window(1, 28)))
    halves = _organic(world.ga4_landing_pages(*_window(15, 14))) + _organic(
        world.ga4_landing_pages(*_window(1, 14)))
    assert abs(whole - halves) <= 40  # per-row rounding only


def test_the_planted_slip_is_there_to_find():
    world = SoloWorld(today=TODAY)
    guide = "/blog/freelance-tax-guide"
    before = _organic(world.ga4_landing_pages(*_window(15, 14)), guide)
    after = _organic(world.ga4_landing_pages(*_window(1, 14)), guide)
    assert after < 0.6 * before
    gsc = world.gsc("gsc_page_performance", "page")(*_window(1, 14))
    row = next(r for r in gsc["rows"] if r["page"].endswith(guide))
    assert row["avg_position"] > 6


def test_a_window_before_the_history_is_empty_not_invented():
    assert SoloWorld(today=TODAY).ga4_landing_pages("2020-01-01", "2020-01-31")["rows"] == []


def test_the_world_answers_under_the_real_fetch_path_and_leaves_no_trace(monkeypatch):
    import db.session as session_module

    monkeypatch.setattr(session_module, "get_engine", lambda: make_sqlite_engine())
    specs_before = fetchers.fetch_specs()
    with SoloWorld(today=TODAY).install():
        ok = fetchers.fetch_entity("ga4_landing_pages", user_id=uuid.uuid4(), project_id=None)
        missing = fetchers.fetch_entity("mixpanel_event_counts", user_id=uuid.uuid4(), project_id=None)
    assert ok["status"] == "ok" and ok["totals"]["sessions"] > 0
    assert "Organic Search" in ok["subtotals"]["channel"]
    assert missing["status"] == "not_connected"
    assert fetchers.fetch_specs() is specs_before


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Organic sessions: 10,662", "10662 organic sessions", "10 662 sessions", "about 10.7k sessions",
])
def test_an_exact_total_may_be_written_several_ways(text):
    assert quotes(text, 10662)


@pytest.mark.parametrize("text", ["10,663 sessions", "110,662", "10662.5", "1,066"])
def test_a_near_miss_is_not_a_quote(text):
    assert not quotes(text, 10662)


def test_figures_skip_percentages_years_and_small_numbers():
    text = "In 2026 sessions fell 23% to 10,662 (from 11,270); CPA €19.55 on 134 conversions."
    assert figures_in(text) == [10662.0, 11270.0, 19.55, 134.0]


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

def _trials(*passed: bool, cost: float = 0.1, calls: int = 10) -> list[Trial]:
    return [Trial("c", i, passed=p, cost_usd=cost, model_calls=calls) for i, p in enumerate(passed, 1)]


@pytest.mark.parametrize("passed, verdict", [
    ((True, True, True), PASS),
    ((True, True, False), INCONCLUSIVE),
    ((True, False, False), FAIL),
    ((False, False, False), FAIL),
])
def test_a_case_that_always_passed_is_judged_against_three_of_three(passed, verdict):
    assert decide("c", _trials(*passed), {"pass_rate": 1.0})[0] == verdict


def test_a_flaky_baseline_is_not_held_to_perfection():
    """A case that passes 2/3 on main is not failed for passing 2/3 here."""
    assert decide("c", _trials(True, True, False), {"pass_rate": 0.667})[0] == PASS


def test_a_big_move_in_cost_is_inconclusive_even_when_everything_passes():
    """An effort downgrade shows first as a cost drop with no visible change."""
    base = {"pass_rate": 1.0, "median_cost_usd": 0.20, "median_model_calls": 10}
    assert decide("c", _trials(True, True, True, cost=0.10), base)[0] == INCONCLUSIVE
    assert decide("c", _trials(True, True, True, cost=0.21), base)[0] == PASS


def test_no_trials_is_inconclusive_not_a_pass():
    assert decide("c", [], None)[0] == INCONCLUSIVE


def test_every_case_is_synthetic_and_registered():
    assert cases_for("insights") and all(c.agent == "insights" for c in cases_for("insights"))
    assert set(CASES) == {c.id for c in cases_for()}


# ---------------------------------------------------------------------------
# A whole trial, offline
# ---------------------------------------------------------------------------

def _scripted(organic_total: int) -> ToolCallingFake:
    brief = (
        f"{DUCT_ARTIFACT_OPEN}\n---\ntitle: The tax guide slipped\nformat: markdown\n---\n"
        f"# The tax guide slipped\n\nOrganic sessions were {organic_total:,} over the window.\n"
        f"{DUCT_ARTIFACT_CLOSE}"
    )
    return ToolCallingFake(responses=[
        AIMessage(content="", tool_calls=[
            {"name": "FetchData", "args": {"entity_id": "ga4_landing_pages"}, "id": "f1"},
            {"name": "FetchData", "args": {"entity_id": "gsc_page_performance"}, "id": "f2"},
        ]),
        AIMessage(content=f"The tax guide lost its ranking.\n{brief}"),
    ])


async def test_a_trial_runs_the_real_harness_on_the_world(monkeypatch):
    import db.session as session_module

    monkeypatch.setattr(session_module, "get_engine", lambda: make_sqlite_engine())
    world = SoloWorld()
    organic = _organic(world.ga4_landing_pages(*resolve_window("", "")))

    trial = await run_trial(ORGANIC, 1, provider=Provider.OPENROUTER, model="x", api_key="unused",
                            llm=_scripted(organic), judge=False)

    assert trial.passed, trial.failures
    assert sorted(f[0] for f in trial.fetches) == ["ga4_landing_pages", "gsc_page_performance"]
    assert trial.figures_traced == trial.figures == 1


async def test_a_brief_that_added_the_rows_itself_is_caught(monkeypatch):
    """The replay's error, reproduced: a total off by the model's own sum."""
    import db.session as session_module

    monkeypatch.setattr(session_module, "get_engine", lambda: make_sqlite_engine())
    world = SoloWorld()
    organic = _organic(world.ga4_landing_pages(*resolve_window("", "")))

    trial = await run_trial(ORGANIC, 1, provider=Provider.OPENROUTER, model="x", api_key="unused",
                            llm=_scripted(organic - 177), judge=False)

    assert not trial.passed
    assert any("does not quote" in f for f in trial.failures)
