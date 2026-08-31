"""The insights brief becomes a versioned artifact.

Phase 4 of `docs/engineering/autonomous-insights-agent-plan.md`. Three things
have to hold, and they are what this file pins:

  * **A brief the model wrote is never lost.** The payload has no schema — it
    is streamed prose — so every parse path degrades to "store it anyway"
    rather than raising. A malformed fence costs a good title, not the brief.
  * **The content decides the format.** A markdown document stored as
    `text/html` renders as garbage in an iframe, so the declared format is
    recorded and the bytes are believed.
  * **Generalising the persister did not move audit.** The store learned an
    adapter seam; audit's rows — slug, filename, content type — must come out
    byte-identical, or this refactor silently renamed everyone's reports.

Fake chat model throughout — no API key, no network.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from sqlmodel import select

from agents.core.events import AgentEvent
from agents.insights.brief import (
    ARTIFACT_KIND,
    DEFAULT_TITLE,
    brief_artifact_version,
    parse_brief,
    sniff_format,
)
from agents.insights.prompts.autonomous import (
    build_insights_system_prompt,
    build_insights_user_prompt,
)
from agents.insights.schema import create_insights_session
from agents.insights.v1.runner import AutonomousInsightsRunner
from agents.preferences import UserPreferences
from agents.registry import AgentCapability, AgentType, get_spec
from models.artifact import Artifact
import service.artifact_store as store

# Fixtures (engine/db/local_storage/store_db/owner/project) come from the
# artifact-store suite — the same DB shape, so they are imported rather than
# re-declared.
from tests.test_artifact_store import (  # noqa: F401
    db,
    engine,
    local_storage,
    owner,
    project,
    store_db,
)


class ToolCallingFake(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self


def _fake(*responses: str):
    return ToolCallingFake(responses=[AIMessage(content=r) for r in responses])


@pytest.fixture
def session():
    return create_insights_session(str(uuid.uuid4()))


@pytest.fixture
def emitted():
    events: list[dict] = []

    async def emit(event: dict) -> None:
        events.append(event)

    emit.events = events  # type: ignore[attr-defined]
    return emit


RUNNER = AutonomousInsightsRunner(api_key="unused-no-network")

MARKDOWN_BRIEF = """<duct_artifact>
---
title: Why CPA rose through August
format: markdown
---
# Why CPA rose through August

Spend held; conversions fell.

## What could not be verified
Offline conversion imports — GSC was never connected.
</duct_artifact>"""


# ---------------------------------------------------------------------------
# Reading a payload — the part with no schema
# ---------------------------------------------------------------------------

def test_front_matter_carries_the_title():
    brief = parse_brief("---\ntitle: Q3 paid search\nformat: markdown\n---\n# Body\n")

    assert brief.title == "Q3 paid search"
    assert brief.format == "markdown"
    assert brief.body.startswith("# Body")


def test_a_brief_with_no_front_matter_still_gets_a_title():
    """The one outcome to avoid is losing a brief the model actually wrote."""
    brief = parse_brief("## August paid search\n\nSpend held.\n")

    assert brief.title == "August paid search"
    assert brief.body.startswith("## August")


def test_an_untitled_brief_falls_back_rather_than_failing():
    brief = parse_brief("Just some prose with no heading at all.")

    assert brief.title == DEFAULT_TITLE
    assert brief.body.startswith("Just some prose")


def test_a_horizontal_rule_is_not_front_matter():
    """`---` appears in ordinary markdown. Only a *leading* fence counts, or
    every brief with a section break loses its first paragraph."""
    brief = parse_brief("# Real title\n\nIntro.\n\n---\n\nMore body.\n")

    assert brief.title == "Real title"
    assert "More body." in brief.body


def test_html_is_detected_from_the_bytes_not_the_declaration():
    brief = parse_brief(
        "---\ntitle: Forwarded review\nformat: markdown\n---\n"
        "<!doctype html><html><head><title>x</title></head><body>hi</body></html>"
    )

    assert brief.format == "html"


def test_a_declaration_the_content_contradicts_is_recorded_not_obeyed():
    """A markdown document served as text/html renders as garbage in an iframe.
    The bytes are the only evidence that cannot be wrong."""
    brief = parse_brief("---\ntitle: t\nformat: html\n---\n# Actually markdown\n")

    assert brief.format == "markdown"
    assert brief.declared_format == "html"

    version = brief_artifact_version({
        "version_id": 1,
        "payload": {
            "title": brief.title,
            "format": brief.format,
            "content": brief.body,
            "declared_format": brief.declared_format,
        },
    })
    assert version.content_type == store.MARKDOWN
    assert version.meta["declared_format"] == "html"


def test_an_html_title_comes_from_the_document():
    brief = parse_brief("<!doctype html><html><head><title>Q3 review</title></head></html>")

    assert brief.title == "Q3 review"
    assert brief.format == "html"


def test_sniffing_never_returns_something_unrenderable():
    for source in ("", "   ", "# md", "<div>x</div>", "plain text", "---\n"):
        assert sniff_format(source) in ("markdown", "html")


# ---------------------------------------------------------------------------
# Emitting versions
# ---------------------------------------------------------------------------

async def test_a_closing_tag_publishes_a_brief_version(session, emitted):
    await RUNNER.run_session(
        session.session_id, emitted, llm=_fake(MARKDOWN_BRIEF),
        session=session, prompt="why did CPA jump?", chat_idle_timeout=0.01,
    )

    versions = [e for e in emitted.events if e["event"] == AgentEvent.ARTIFACT_VERSION]
    assert len(versions) == 1
    assert versions[0]["version_id"] == 1
    assert versions[0]["label"] == "Initial brief"
    assert versions[0]["payload"]["title"] == "Why CPA rose through August"
    assert versions[0]["payload"]["format"] == "markdown"
    assert "Spend held" in versions[0]["payload"]["content"]


async def test_the_brief_does_not_also_arrive_as_chat_prose(session, emitted):
    """The tag's payload streams as ARTIFACT_CHUNK, not AGENT_MESSAGE_CHUNK —
    otherwise the brief is pasted into the transcript as well as the pane."""
    await RUNNER.run_session(
        session.session_id, emitted, llm=_fake(f"Here is the read.\n{MARKDOWN_BRIEF}"),
        session=session, prompt="?", chat_idle_timeout=0.01,
    )

    prose = "".join(
        e["text"] for e in emitted.events if e["event"] == AgentEvent.AGENT_MESSAGE_CHUNK
    )
    assert "Here is the read." in prose
    assert "Spend held" not in prose
    assert any(e["event"] == AgentEvent.ARTIFACT_CHUNK for e in emitted.events)


async def test_a_second_brief_is_the_next_version(session, emitted):
    await session.chat_queue.put("redo it with mobile split out")
    await session.chat_queue.put(None)

    await RUNNER.run_session(
        session.session_id, emitted, llm=_fake(MARKDOWN_BRIEF, MARKDOWN_BRIEF),
        session=session, prompt="?", chat_idle_timeout=2.0,
    )

    versions = [e for e in emitted.events if e["event"] == AgentEvent.ARTIFACT_VERSION]
    assert [v["version_id"] for v in versions] == [1, 2]
    assert versions[1]["label"] == "Update 2"


async def test_a_resumed_session_continues_the_version_numbers(session, emitted):
    """(group_id, version) is unique. Restarting at v1 on resume would collide
    with the stored head and the brief would be dropped, not stored twice."""
    await RUNNER.run_session(
        session.session_id, emitted, llm=_fake(MARKDOWN_BRIEF),
        session=session, prompt="?", start_version=3, chat_idle_timeout=0.01,
    )

    versions = [e for e in emitted.events if e["event"] == AgentEvent.ARTIFACT_VERSION]
    assert versions[0]["version_id"] == 4
    assert versions[0]["label"] == "Update 4"


async def test_an_empty_artifact_publishes_nothing(session, emitted):
    """An empty version would be a blank brief in the artifacts list forever."""
    await RUNNER.run_session(
        session.session_id, emitted, llm=_fake("<duct_artifact>\n\n</duct_artifact>"),
        session=session, prompt="?", chat_idle_timeout=0.01,
    )

    assert not [e for e in emitted.events if e["event"] == AgentEvent.ARTIFACT_VERSION]


# ---------------------------------------------------------------------------
# Storing them
# ---------------------------------------------------------------------------

async def test_a_brief_persists_as_a_readable_markdown_artifact(
    local_storage, store_db, project, owner, db  # noqa: F811
):
    persister = store.ArtifactPersister(
        project_id=project.id,
        user_id=owner.id,
        agent_type=str(AgentType.INSIGHTS),
        kind=ARTIFACT_KIND,
        adapt=brief_artifact_version,
    )
    wrapped = persister.wrap_emit(lambda body: asyncio.sleep(0))
    await wrapped({
        "event": AgentEvent.ARTIFACT_VERSION,
        "version_id": 1,
        "label": "Initial brief",
        "payload": {
            "title": "Why CPA rose through August",
            "format": "markdown",
            "content": "# Why CPA rose\n\nSpend held; conversions fell.\n",
        },
    })
    await asyncio.sleep(0)

    row = db.exec(select(Artifact)).one()
    assert row.kind == ARTIFACT_KIND
    assert row.agent_type == str(AgentType.INSIGHTS)
    assert row.content_type == store.MARKDOWN
    assert row.title == "Why CPA rose through August"
    assert row.slug == "why-cpa-rose-through-august"
    assert row.filename.endswith("_why-cpa-rose-through-august_v1.md")
    # The body is retrievable, which is the whole point of persisting it.
    assert "conversions fell" in store.artifact_text_content(row)


async def test_brief_versions_extend_one_artifact(
    local_storage, store_db, project, owner, db  # noqa: F811
):
    persister = store.ArtifactPersister(
        project_id=project.id, user_id=owner.id, agent_type=str(AgentType.INSIGHTS),
        kind=ARTIFACT_KIND, adapt=brief_artifact_version,
    )
    wrapped = persister.wrap_emit(lambda body: asyncio.sleep(0))
    for n, body in ((1, "# v1"), (2, "# v2")):
        await wrapped({
            "event": AgentEvent.ARTIFACT_VERSION,
            "version_id": n,
            "label": f"Version {n}",
            "payload": {"title": "August brief", "format": "markdown", "content": body},
        })
    await asyncio.sleep(0)

    rows = list(db.exec(select(Artifact).order_by(Artifact.version)))
    assert [r.version for r in rows] == [1, 2]
    assert rows[0].group_id == rows[1].group_id
    assert store.artifact_text_content(rows[1]) == "# v2"


def test_generalising_the_persister_left_audit_where_it_was(
    local_storage, store_db, project  # noqa: F811
):
    """The adapter seam must not have renamed anyone's stored reports."""
    from tests.test_artifact_store import _freehand_report

    version = store.audit_report_version({
        "version_id": 2,
        "label": "Update 2",
        "payload": _freehand_report(url="https://www.example.com").model_dump(),
    })

    assert version.content_type == store.HTML
    assert version.title == "SEO audit — example.com"
    assert version.slug_stem == "seo-audit-example.com"
    assert version.file_stem == "seo-audit_example.com"
    assert version.meta["label"] == "Update 2"
    assert "html_report" not in version.structured_json


def test_the_default_adapter_is_the_audit_one():
    """Existing call sites pass no `adapt` — they must keep working unchanged."""
    persister = store.ArtifactPersister(project_id=uuid.uuid4())

    assert persister.adapt is store.audit_report_version


# ---------------------------------------------------------------------------
# The format preference
# ---------------------------------------------------------------------------

def test_markdown_is_the_default_deliverable():
    assert UserPreferences().preferred_artifact_format == "markdown"


def test_the_format_preference_never_reaches_the_system_prompt():
    """Per-user data in the cached prefix gives every customer their own cache.
    The contract for *how* to write an artifact is shared; *which format* is not.
    """
    prompt = build_insights_system_prompt()

    assert "duct_artifact" in prompt  # the mechanism is shared and cached
    assert "self-contained HTML document" not in prompt
    assert build_insights_system_prompt() == prompt


@pytest.mark.parametrize("fmt,marker", [
    ("markdown", "no HTML wrapper"),
    ("html", "self-contained HTML document"),
])
def test_the_preference_steers_the_user_turn(fmt, marker):
    turn = build_insights_user_prompt(prompt="why did CPA jump?", artifact_format=fmt)

    assert marker in turn
    assert "<deliverable_format>" in turn


def test_no_preference_asks_for_no_format():
    """A caller that has no preference must not silently invent one."""
    assert "<deliverable_format>" not in build_insights_user_prompt(prompt="x")


def test_insights_declares_versioned_output():
    spec = get_spec(AgentType.INSIGHTS)

    assert AgentCapability.VERSIONED_OUTPUT in spec.capabilities
