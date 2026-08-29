"""Phase 3 retrieval: time-aware expansion, reinforcement ranking, the eval set.

Covers only what Phase 3 added. The table, supersession, digest, routes,
consolidation and controls are exercised in tests/test_memory.py and
tests/test_memory_phase2.py and are not repeated here.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.project import Project  # noqa: E402
from service.memory import (  # noqa: E402
    build_memory_context,
    default_importance,
    expand_time_range,
    opening_alerts,
    rank_memories,
    remember,
    search,
    touch_recall,
)
from tests.eval.memory_recall import (  # noqa: E402
    ABSTENTION,
    KNOWLEDGE_UPDATE,
    format_report,
    run_eval,
    seed_corpus,
)
from utils.dates import utcnow  # noqa: E402


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def project(db):
    row = Project(id=uuid4(), user_id=uuid4(), name="Acme")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _write(db, project, **kw):
    kw.setdefault("kind", "conclusion")
    kw.setdefault("title", "Something")
    return remember(db, project_id=project.id, source_refs=[{"source": "t"}], **kw)


# ---------------------------------------------------------------------------
# Time-aware query expansion
# ---------------------------------------------------------------------------

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "question, first_day, last_day",
    [
        ("what changed in the last 7 days", "2026-08-22", None),
        ("how did CPA move in August", "2026-08-01", "2026-08-31"),
        ("clicks in July 2025", "2025-07-01", "2025-07-31"),
        ("anything since 2026-06-01", "2026-06-01", None),
        ("between 2026-05-01 and 2026-05-31 what broke", "2026-05-01", "2026-05-31"),
        ("what happened in Q2 2026", "2026-04-01", "2026-06-30"),
        ("organic traffic in 2025", "2025-01-01", "2025-12-31"),
        ("what did we do yesterday", "2026-08-28", "2026-08-28"),
    ],
)
def test_a_date_range_is_read_out_of_the_question(question, first_day, last_day):
    window = expand_time_range(question, now=NOW)
    assert window, f"no range read from {question!r}"
    assert window.since.date().isoformat() == first_day
    assert (window.until.date().isoformat() if window.until else None) == last_day


def test_a_question_with_no_date_filters_nothing():
    """A miss must degrade to "no filter", never to an empty result."""
    assert not expand_time_range("how is the site doing", now=NOW)
    assert not expand_time_range("", now=NOW)


def test_a_bare_month_means_the_most_recent_one():
    """"in October" in August 2026 is last October, not one that has not happened."""
    assert expand_time_range("traffic in October", now=NOW).since.year == 2025
    assert expand_time_range("traffic in March", now=NOW).since.year == 2026


def test_search_applies_the_range_it_read_but_never_overrides_the_caller(db, project):
    old = _write(db, project, title="Redirect shipped", observed_at=utcnow() - timedelta(days=90))
    recent = _write(db, project, title="Redirect verified", observed_at=utcnow() - timedelta(days=2))

    found = search(db, project_id=project.id, query="redirect in the last 7 days", time_aware=True)
    assert [r.id for r in found] == [recent.id]

    # An explicit range is the caller's instruction; the question does not win.
    both = search(
        db, project_id=project.id, query="redirect in the last 7 days",
        since=utcnow() - timedelta(days=365), time_aware=True,
    )
    assert {r.id for r in both} == {old.id, recent.id}


# ---------------------------------------------------------------------------
# Reinforcement ranking
# ---------------------------------------------------------------------------

def test_recall_lifts_a_memory_above_an_equally_relevant_neighbour(db, project):
    """MemoryBank's reinforcement: what gets recalled gets easier to recall."""
    ignored = _write(db, project, title="Canonical tags on blog", importance=5,
                     observed_at=utcnow() - timedelta(days=20))
    used = _write(db, project, title="Canonical tags on plans", importance=5,
                  observed_at=utcnow() - timedelta(days=20))
    for _ in range(6):
        touch_recall(db, [used.id])
    db.refresh(used)

    ranked = rank_memories([ignored, used])
    assert ranked[0].id == used.id


def test_ranking_prefers_the_important_over_the_merely_recent(db, project):
    goal = _write(db, project, kind="goal", title="Target CPA $45",
                  observed_at=utcnow() - timedelta(days=25))
    noise = _write(db, project, kind="event", title="Sitemap ping",
                   observed_at=utcnow() - timedelta(days=20))
    db.refresh(goal)
    db.refresh(noise)
    # Recency alone would put the event first; importance is what separates them.
    assert rank_memories([noise, goal])[0].id == goal.id


def test_a_pinned_entry_outranks_everything(db, project):
    pinned = _write(db, project, kind="event", title="Old but pinned",
                    observed_at=utcnow() - timedelta(days=300))
    pinned.pinned = True
    db.add(pinned)
    db.commit()
    fresh = _write(db, project, kind="goal", title="Fresh and important")
    assert rank_memories([fresh, pinned])[0].id == pinned.id


def test_unrated_entries_are_rated_by_kind(db, project):
    """A stated goal and a routine metric should not share one flat default."""
    goal = _write(db, project, kind="goal", title="Target CPA $45")
    metric = _write(db, project, kind="metric", title="CPA $71 in Q1", period="2026-Q1")
    assert goal.importance == default_importance("goal") > metric.importance
    # An explicit rating from the writer still wins.
    rated = _write(db, project, kind="metric", title="CPA $52 in Q2", period="2026-Q2",
                   importance=9)
    assert rated.importance == 9


# ---------------------------------------------------------------------------
# Proactive recall — speaking first, only when the run touches the memory
# ---------------------------------------------------------------------------

def test_an_open_watch_on_the_audited_site_is_raised(db, project):
    watch = _write(db, project, kind="watch", title="Watch /plans indexation",
                   entity_key="page:/plans", attribute="indexation")
    alerts = opening_alerts(db, project_id=project.id, subject="https://acme.com")
    assert [a.id for a in alerts] == [watch.id]

    context = build_memory_context(db, project_id=project.id, subject="https://acme.com")
    assert "<memory_opening>" in context.text
    # The chips list it once, even though the digest's Open section has it too.
    assert len(context.recalled) == len({e["memory_id"] for e in context.recalled})


def test_a_resolved_watch_and_a_vague_one_stay_quiet(db, project):
    _write(db, project, kind="watch", title="Watch /plans indexation",
           entity_key="page:/plans", attribute="indexation",
           valid_to=utcnow() - timedelta(days=1))
    _write(db, project, kind="watch", title="Keep an eye on things generally")
    assert opening_alerts(db, project_id=project.id, subject="https://acme.com") == []


def test_a_competitor_watch_is_raised_only_when_the_run_is_about_them(db, project):
    _write(db, project, kind="watch", title="Watch databox pricing",
           entity_key="competitor:databox", attribute="pricing")
    assert opening_alerts(db, project_id=project.id, subject="https://acme.com") == []
    assert opening_alerts(db, project_id=project.id, subject="https://databox.com") != []


def test_no_subject_means_no_interjection(db, project):
    _write(db, project, kind="watch", title="Watch /plans", entity_key="page:/plans")
    assert opening_alerts(db, project_id=project.id, subject="") == []
    assert "<memory_opening>" not in build_memory_context(db, project_id=project.id).text


# ---------------------------------------------------------------------------
# The evaluation set
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def graded():
    """Seed the corpus once and grade all 50 questions."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        project = Project(id=uuid4(), user_id=uuid4(), name="Acme")
        db.add(project)
        db.commit()
        index = seed_corpus(db, project.id)
        results = run_eval(db, project.id, index)
        print("\n" + format_report(results))
        yield results


# Thresholds are a ratchet, not a target: they sit just under what the
# implementation scores today, so a regression fails the build and an
# improvement invites raising them.
#
# knowledge-update stops at 0.9 for one question — "does /pricing still
# resolve", where the entry says "301s to /plans". Lexical search cannot bridge
# "resolve" to "301", and the question stays in the set on purpose: it is the
# concrete case for the pgvector sidecar the design leaves optional, and a
# floor of 1.0 would only be reachable by deleting the evidence for it.
@pytest.mark.parametrize(
    "axis, floor",
    [("extraction", 0.9), ("multi-session", 0.8), ("temporal", 0.9), ("knowledge-update", 0.9)],
)
def test_recall_holds_per_axis(graded, axis, floor):
    result = graded[axis]
    assert result.recall >= floor, f"{axis} recall {result.recall:.0%}\n" + "\n".join(result.misses)


def test_no_superseded_fact_is_served_as_current(graded):
    """The stale-fact rate — 15-40% for vanilla RAG, ~0% for a bi-temporal ledger."""
    result = graded[KNOWLEDGE_UPDATE]
    assert result.leak_rate == 0.0, "\n".join(result.misses)


def test_a_date_range_excludes_what_falls_outside_it(graded):
    result = graded["temporal"]
    assert result.leak_rate == 0.0, "\n".join(result.misses)


def test_unanswerable_questions_return_nothing(graded):
    result = graded[ABSTENTION]
    assert result.abstained == result.asked, "\n".join(result.misses)


def test_the_corpus_seeded_and_superseded_as_written(graded):
    """Guards the eval itself: a corpus that failed to load would score well."""
    assert sum(r.asked for r in graded.values()) == 50


def test_the_known_synonym_gap_is_the_only_knowledge_update_miss(graded):
    """Pin the one documented failure so a second one cannot hide behind it."""
    misses = [m for m in graded[KNOWLEDGE_UPDATE].misses if "missed" in m]
    assert len(misses) == 1 and "still resolve" in misses[0], misses
