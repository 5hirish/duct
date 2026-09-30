"""The eval gate's own plumbing, offline: the world, the checks, the verdicts.

A paid gate that is wrong about itself is worse than none: it teaches people
to re-run until green. So its arithmetic, its figure matching and its verdict
rules are pinned here for free, and one test drives a whole trial through the
real insights harness with a scripted model, the way the paid tier drives it
with a real one.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import threading
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
    CaseResult,
    Trial,
    decide,
    figures_in,
    quotes,
    report,
    run_trial,
    trial_record,
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


def test_a_baseline_from_another_model_judges_nothing():
    """Measured on V4 Pro, a V4 Flash run would read as a cost collapse; the
    verdict says which baseline is missing instead of passing or failing."""
    base = {"pass_rate": 0.667, "median_cost_usd": 0.0675, "median_model_calls": 4.5,
            "model": "deepseek/deepseek-v4-pro"}
    verdict, reason = decide("c", _trials(True, True, True, cost=0.007), base, model="deepseek/deepseek-v4-flash")

    assert verdict == INCONCLUSIVE
    assert "deepseek/deepseek-v4-pro" in reason and "--write-baseline" in reason
    assert decide("c", _trials(True, True, False, cost=0.0675, calls=4.5), base,
                  model="deepseek/deepseek-v4-pro")[0] == PASS


def test_every_case_is_synthetic_and_registered():
    assert cases_for("insights") and all(c.agent == "insights" for c in cases_for("insights"))
    assert set(CASES) == {c.id for c in cases_for()}


# ---------------------------------------------------------------------------
# A whole trial, offline
# ---------------------------------------------------------------------------

_PULL_BOTH = AIMessage(content="", tool_calls=[
    {"name": "FetchData", "args": {"entity_id": "ga4_landing_pages"}, "id": "f1"},
    {"name": "FetchData", "args": {"entity_id": "gsc_page_performance"}, "id": "f2"},
])


def _brief(organic_total: int) -> AIMessage:
    return AIMessage(content=(
        f"The tax guide lost its ranking.\n{DUCT_ARTIFACT_OPEN}\n---\ntitle: The tax guide slipped\n"
        f"format: markdown\n---\n# The tax guide slipped\n\n"
        f"Organic sessions were {organic_total:,} over the window.\n{DUCT_ARTIFACT_CLOSE}"
    ))


def _scripted(organic_total: int) -> ToolCallingFake:
    return ToolCallingFake(responses=[_PULL_BOTH, _brief(organic_total)])


class _Analyst(ToolCallingFake):
    """Pulls both sources, then writes the brief, deciding from the thread
    rather than a response index, so trials running at once can share it."""

    organic_total: int = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from langchain_core.outputs import ChatGeneration, ChatResult

        reply = _brief(self.organic_total) if messages[-1].type == "tool" else _PULL_BOTH
        return ChatResult(generations=[ChatGeneration(message=reply)])


def test_a_trial_runs_the_real_harness_on_the_world(monkeypatch):
    import db.session as session_module

    monkeypatch.setattr(session_module, "get_engine", lambda: make_sqlite_engine())
    world = SoloWorld()
    organic = _organic(world.ga4_landing_pages(*resolve_window("", "")))

    trial = run_trial(ORGANIC, 1, provider=Provider.OPENROUTER, model="x", api_key="unused",
                            llm=_scripted(organic), judge=False)

    assert trial.passed, trial.failures
    assert sorted(f[0] for f in trial.fetches) == ["ga4_landing_pages", "gsc_page_performance"]
    assert trial.figures_traced == trial.figures == 1


def test_a_brief_that_added_the_rows_itself_is_caught(monkeypatch):
    """The replay's error, reproduced: a total off by the model's own sum."""
    import db.session as session_module

    monkeypatch.setattr(session_module, "get_engine", lambda: make_sqlite_engine())
    world = SoloWorld()
    organic = _organic(world.ga4_landing_pages(*resolve_window("", "")))

    trial = run_trial(ORGANIC, 1, provider=Provider.OPENROUTER, model="x", api_key="unused",
                            llm=_scripted(organic - 177), judge=False)

    assert not trial.passed
    assert any("does not quote" in f for f in trial.failures)


@pytest.mark.parametrize("said, why", [
    ("Nothing moved enough to be worth a brief this week.", "ended without an artifact"),
    (f"Here is the brief.\n{DUCT_ARTIFACT_OPEN}\n# The tax guide slipped\n", "started and never published"),
])
def test_a_run_without_a_brief_keeps_what_the_agent_said(monkeypatch, said, why):
    """The first CI run lost two briefs in six and its record could not say how."""
    import db.session as session_module

    monkeypatch.setattr(session_module, "get_engine", lambda: make_sqlite_engine())
    trial = run_trial(ORGANIC, 1, provider=Provider.OPENROUTER, model="x", api_key="unused",
                            llm=ToolCallingFake(responses=[AIMessage(content=said)]), judge=False)
    result = CaseResult(ORGANIC.id, FAIL, "", [trial])

    assert any(why in f for f in trial.failures)
    assert trial.reply == said.split(DUCT_ARTIFACT_OPEN)[0].strip()
    assert json.loads(trial_record(result, trial, provider="p", model="m"))["reply"] == trial.reply
    assert f"> ended on: {trial.reply}" in report([result], provider="p", model="m", spent=0)


class _Stalled(ToolCallingFake):
    """A provider whose stream never finishes: OpenRouter's keep-alive bytes
    hold the connection open, so no read timeout ever fires."""

    async def _agenerate(self, *args, **kwargs):
        await asyncio.sleep(3600)


def test_a_trial_that_never_finishes_is_stopped_by_the_clock(monkeypatch):
    """One stalled call held a six-trial run for three hours on 2026-09-28."""
    import db.session as session_module

    monkeypatch.setattr(session_module, "get_engine", lambda: make_sqlite_engine())
    case = dataclasses.replace(ORGANIC, max_seconds=0.5)

    trial = run_trial(case, 1, provider=Provider.OPENROUTER, model="x", api_key="unused",
                            llm=_Stalled(responses=[]), judge=False)

    assert any("timed out after" in f for f in trial.failures)
    assert trial.seconds < 10


def test_a_stalled_judge_is_abandoned_not_waited_on(monkeypatch):
    """The judge is a blocking call, out of reach of the trial's clock."""
    import tests.eval.judge as judge_module
    from tests.eval import gate

    release = threading.Event()
    monkeypatch.setattr(gate, "JUDGE_SECONDS", 0.2)
    monkeypatch.setattr(judge_module, "evaluate", lambda *a, **k: release.wait(10))
    trial = Trial(case_id=ORGANIC.id, n=1, brief="# The tax guide slipped")

    gate._judge(ORGANIC, trial)
    release.set()

    assert trial.judge == {"skipped": "Timeout"}
    assert not trial.failures


class _Stubborn(ToolCallingFake):
    """A call that does not stop when cancelled, as the stalled stream did."""

    release: threading.Event

    async def _agenerate(self, *args, **kwargs):
        while not self.release.is_set():
            try:
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                continue


def test_a_trial_that_will_not_stop_is_abandoned(monkeypatch):
    """The gate returns on time even when a trial ignores its cancellation."""
    import db.session as session_module
    from tests.eval import gate

    monkeypatch.setattr(session_module, "get_engine", lambda: make_sqlite_engine())
    monkeypatch.setattr(gate, "STOP_GRACE_SECONDS", 0.5)
    case = dataclasses.replace(ORGANIC, max_seconds=0.5)
    stubborn = _Stubborn(responses=[], release=threading.Event())

    try:
        trial = run_trial(case, 1, provider=Provider.OPENROUTER, model="x", api_key="unused",
                          llm=stubborn, judge=False)
    finally:
        stubborn.release.set()

    assert trial.failures == ["timed out after 0s and did not stop; abandoned"]
    assert trial.seconds < 10


def test_a_case_runs_its_trials_at_once_and_each_keeps_its_own_pulls(monkeypatch):
    import db.session as session_module
    from tests.eval.gate import run_trials

    monkeypatch.setattr(session_module, "get_engine", lambda: make_sqlite_engine())
    organic = _organic(SoloWorld().ga4_landing_pages(*resolve_window("", "")))
    finished: list[int] = []

    trials = run_trials(ORGANIC, [1, 2, 3], provider=Provider.OPENROUTER, model="x", api_key="unused",
                        llm=_Analyst(responses=[], organic_total=organic), judge=False,
                        on_done=lambda t: finished.append(t.n))

    assert [t.n for t in trials] == [1, 2, 3] and sorted(finished) == [1, 2, 3]
    assert all(t.passed for t in trials), [t.failures for t in trials]
    assert all(len(t.fetches) == 2 for t in trials)


def test_a_brief_written_to_a_scratch_file_is_named_in_the_failure(monkeypatch):
    """What two of six DeepSeek trials did on 2026-09-28: the brief went to
    the virtual filesystem, the reply said it was written, and no artifact."""
    import db.session as session_module

    monkeypatch.setattr(session_module, "get_engine", lambda: make_sqlite_engine())
    llm = ToolCallingFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "write_file", "id": "w1",
                                           "args": {"file_path": "/brief.md", "content": "# Organic fell"}}]),
        AIMessage(content="The brief is written."),
    ])

    trial = run_trial(ORGANIC, 1, provider=Provider.OPENROUTER, model="x", api_key="unused",
                      llm=llm, judge=False)

    assert trial.tools == ["write_file"] and trial.files == ["/brief.md"]
    assert any("having written /brief.md to its scratch files" in f for f in trial.failures)


class _Card:
    def __init__(self, failures: list[str]):
        self.failures = failures

    def as_dict(self) -> dict:
        return {"failures": self.failures}


@pytest.mark.parametrize("cards, judged, failures", [
    ([["marker 'names_the_slip' missing from judge verdict"]] * 2, {"skipped": "IncompleteVerdict"}, []),
    ([["marker 'names_the_slip' missing from judge verdict"], ["marker 'names_the_slip': NOT HONORED"]],
     {"failures": ["marker 'names_the_slip': NOT HONORED"]}, ["judge: marker 'names_the_slip': NOT HONORED"]),
])
def test_a_verdict_that_leaves_markers_out_is_the_judges_failure(monkeypatch, cards, judged, failures):
    import tests.eval.judge as judge_module
    from tests.eval import gate

    answers = iter(cards)
    monkeypatch.setattr(judge_module, "evaluate", lambda *a, **k: _Card(next(answers)))
    trial = Trial(case_id=ORGANIC.id, n=1, brief="# The tax guide slipped")

    gate._judge(ORGANIC, trial)

    assert trial.judge == judged and trial.failures == failures
