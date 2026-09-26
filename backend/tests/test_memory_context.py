"""What memory puts in a turn: order, toggles, budget, recall and alerts.

Each test here pins a way the memory context used to go wrong while every
block in it was individually correct: blocks landing after the volatile digest
and costing the cached prefix, an agent's "no prior reports" toggle ignored,
the digest cut mid-line with the cut entries still reported as recalled, every
shown entry counted as used, and a pricing-page incident opening an ads
question.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from agents.core.turn import BLOCK_ORDER, MEMORY_BLOCKS
from agents.registry import AgentType
from models.agent_context import AgentContext
from models.artifact import Artifact
from models.auth import User
from models.memory import SCOPE_USER, SOURCE_USER
from models.project import Project
from service.memory import (
    _digest_query,
    _touches,
    build_memory_context,
    record_artifact_memory,
    remember,
    render_digest,
    touch_cited,
    short_id,
)
from tests.conftest import make_sqlite_engine


@pytest.fixture
def db():
    with Session(make_sqlite_engine()) as session:
        yield session


@pytest.fixture
def owner(db):
    user = User(email="memory-context@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def project(db, owner):
    row = Project(user_id=owner.id, name="Acme", slug="acme")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _write(db, project, **kw):
    return remember(db, **{
        "kind": "conclusion", "title": "Something true", "project_id": project.id,
        "source_refs": [{"conversation_id": "c1"}], **kw,
    })


def _report(db, project, owner, *, title="SEO audit"):
    artifact = Artifact(
        group_id=uuid4(), version=1, project_id=project.id, user_id=owner.id,
        kind="report", title=title, slug=title.lower().replace(" ", "-"), summary="Score 71.",
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    record_artifact_memory(db, artifact)
    return artifact


# ---------------------------------------------------------------------------
# Order and toggles
# ---------------------------------------------------------------------------

def test_memory_owns_one_contiguous_run_of_the_block_order():
    """Memory reaches a turn as one string in the project_memory slot, so the
    tags it holds must be adjacent in BLOCK_ORDER or that string lands out of
    order. A tag slipped in between would be swallowed into MEMORY_BLOCKS."""
    assert set(MEMORY_BLOCKS) == {
        "user_memory", "agent_context", "prior_reports", "project_memory", "memory_opening",
    }
    assert "project_memory" in BLOCK_ORDER


def test_stable_blocks_come_before_the_digest(db, project, owner):
    """The digest changes with every question and every day; everything that
    does not must come first, or the cached prefix ends at the digest."""
    _write(db, project, kind="goal", title="Target CPA $45", entity_key="kpi:cpa", attribute="target")
    _write(db, project, kind="watch", title="Watch /plans", entity_key="page:/plans")
    remember(db, scope=SCOPE_USER, kind="method", title="Compare to last year",
             user_id=owner.id, source_type=SOURCE_USER)
    _report(db, project, owner)
    db.add(AgentContext(project_id=project.id, agent_id=str(AgentType.SEO_AUDIT), data={"k": "v"}))
    db.commit()

    text = build_memory_context(
        db, project_id=project.id, user_id=owner.id, agent_type=str(AgentType.SEO_AUDIT),
        query="https://acme.com", subject="https://acme.com",
    ).text
    positions = [text.index(f"<{tag}") for tag in MEMORY_BLOCKS]
    assert positions == sorted(positions)


def test_an_agent_that_declines_prior_reports_does_not_get_them(db, project, owner):
    """Content declares prior_reports=False in the registry. The toggle used to
    be applied only by the turn builder, which never saw this block on its own."""
    _report(db, project, owner)
    content = build_memory_context(
        db, project_id=project.id, user_id=owner.id,
        agent_type=str(AgentType.TIKTOK_STUDIO), artifact_kind=None,
    )
    assert "<prior_reports>" not in content.text
    insights = build_memory_context(
        db, project_id=project.id, user_id=owner.id, agent_type=str(AgentType.INSIGHTS),
    )
    assert "<prior_reports>" in insights.text


def test_a_report_is_listed_once_not_in_both_blocks(db, project, owner):
    _report(db, project, owner, title="SEO audit")
    context = build_memory_context(
        db, project_id=project.id, user_id=owner.id, agent_type=str(AgentType.INSIGHTS),
    )
    assert context.text.count("SEO audit") == 1
    # Without the prior-reports block the digest still names it.
    assert "SEO audit" in render_digest(db, project_id=project.id).text


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

def test_the_budget_drops_whole_entries_and_only_reports_what_was_shown(db, project):
    rows = [_write(db, project, kind="event", title=f"Entry {i:02d} " + "x" * 150) for i in range(20)]
    digest = render_digest(db, project_id=project.id, max_chars=1_000)
    shown = [r for r in rows if short_id(r.id) in digest.text]
    assert 0 < len(shown) < len(rows)
    assert {e["id"] for e in digest.recalled} == {short_id(r.id) for r in shown}
    # No entry is cut in half.
    for line in digest.text.splitlines():
        if line.startswith("[m_"):
            assert line.endswith("x")


def test_a_full_digest_keeps_the_entries_about_this_question(db, project):
    """The old cut fell at the end, which was the question's own section."""
    for i in range(20):
        _write(db, project, kind="event", title=f"Routine note {i:02d} " + "x" * 150)
    wanted = _write(db, project, kind="event", title="Pricing page conversion fell 30%")
    digest = render_digest(db, project_id=project.id, query="pricing conversion", max_chars=800)
    assert short_id(wanted.id) in digest.text


# ---------------------------------------------------------------------------
# Recall means use
# ---------------------------------------------------------------------------

def test_showing_an_entry_is_not_recalling_it(db, project, owner):
    row = _write(db, project, kind="goal", title="Target CPA $45")
    build_memory_context(db, project_id=project.id, user_id=owner.id)
    db.refresh(row)
    assert row.recall_count == 0


def test_a_cited_entry_is_recalled_and_an_invented_one_matches_nothing(db, project, owner):
    cited = _write(db, project, title="Cited")
    ignored = _write(db, project, title="Ignored")
    count = touch_cited(
        db, project_id=project.id,
        text=f"CPA held at target ({short_id(cited.id)}), unlike m_00000000.",
    )
    assert count == 1
    db.refresh(cited)
    db.refresh(ignored)
    assert (cited.recall_count, ignored.recall_count) == (1, 0)


def test_a_citation_from_another_project_is_not_counted(db, project, owner):
    other = Project(user_id=owner.id, name="Other", slug="other")
    db.add(other)
    db.commit()
    foreign = _write(db, other, title="Theirs")
    assert touch_cited(db, project_id=project.id, text=short_id(foreign.id)) == 0


# ---------------------------------------------------------------------------
# Opening alerts and the relevant search
# ---------------------------------------------------------------------------

def test_a_page_is_touched_by_an_audit_of_the_site_or_by_naming_it():
    assert _touches("page:/pricing", subject="https://acme.com")
    assert _touches("page:/pricing", subject="why did the pricing page convert worse?")
    assert _touches("page:/pricing", subject="compare /pricing to last month")
    assert not _touches("page:/pricing", subject="why did CPA jump on the brand campaign?")
    assert not _touches("page:/blog/pricing-guide", subject="how is pricing doing?")
    # A path matches as a whole token, and the home page is named by no question.
    assert not _touches("page:/", subject="what is our CPA/ROAS split?")
    assert _touches("page:/", subject="https://acme.com")


def test_an_audited_url_searches_by_its_path():
    assert _digest_query("https://acme.com/blog/pricing-guide") == "blog pricing guide"
    assert _digest_query("https://acme.com") == ""
    assert _digest_query("why did CPA jump?") == "why did CPA jump?"


# ---------------------------------------------------------------------------
# Refreshing a long-lived thread
# ---------------------------------------------------------------------------

def _thread(db, project, *, primed_hours_ago: float):
    from datetime import timedelta

    from models.content.conversation import AgentConversation
    from service.memory import mark_memory_primed
    from utils.dates import utcnow

    conv = AgentConversation(agent_type=str(AgentType.INSIGHTS), project_id=project.id, mode="chat")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    mark_memory_primed(db, conv.id, when=utcnow() - timedelta(hours=primed_hours_ago))
    return conv


def _refresh(db, conv, project, owner):
    from service.memory import memory_refresh

    return memory_refresh(
        db, conversation_id=conv.id, project_id=project.id, user_id=owner.id,
        agent_type=str(AgentType.INSIGHTS), query="how are we doing?",
    )


def test_a_thread_resumed_within_the_hour_is_not_reloaded(db, project, owner):
    conv = _thread(db, project, primed_hours_ago=0.25)
    _write(db, project, title="Learned since")
    context, _ = _refresh(db, conv, project, owner)
    assert context is None


def test_an_old_thread_is_not_reloaded_when_nothing_changed(db, project, owner):
    from datetime import timedelta

    from utils.dates import utcnow

    known = _write(db, project, title="Known before the thread opened")
    known.recorded_at = utcnow() - timedelta(hours=4)
    db.add(known)
    db.commit()
    conv = _thread(db, project, primed_hours_ago=3)
    context, _ = _refresh(db, conv, project, owner)
    assert context is None


def test_an_old_thread_is_reloaded_once_something_changed(db, project, owner):
    conv = _thread(db, project, primed_hours_ago=3)
    fresh = _write(db, project, kind="decision", title="Paused the Brand campaign")
    context, check_again_at = _refresh(db, conv, project, owner)
    assert context is not None and short_id(fresh.id) in context.text
    # And it is now primed, so the next message does not reload it again.
    again, _ = _refresh(db, conv, project, owner)
    assert again is None
    assert check_again_at is not None


def test_what_the_thread_wrote_itself_does_not_make_it_stale(db, project, owner):
    conv = _thread(db, project, primed_hours_ago=3)
    _write(db, project, title="Noted in this very chat", conversation_id=conv.id)
    context, _ = _refresh(db, conv, project, owner)
    assert context is None


def test_the_recorder_credits_the_memories_a_finished_reply_cites(monkeypatch):
    """Every agent's reply passes the recorder, so that is where a citation is
    counted — and a reply that cites nothing costs no query."""
    import asyncio
    from contextlib import nullcontext

    import agents.content.persistence as persistence
    import service.memory as memory

    touched: list[dict] = []
    monkeypatch.setattr(memory, "touch_cited", lambda db, **kw: touched.append(kw) or 1)
    monkeypatch.setattr(persistence, "db_session", lambda: iter([nullcontext()]))

    recorder = persistence.ConversationRecorder(uuid4())
    project_id = uuid4()
    recorder.set_usage_context(user_id=uuid4(), project_id=project_id)
    asyncio.run(recorder._count_citations("Nothing to cite here."))
    assert touched == []
    asyncio.run(recorder._count_citations("CPA is on target (m_1a2b3c4d)."))
    assert touched and touched[0]["project_id"] == project_id
