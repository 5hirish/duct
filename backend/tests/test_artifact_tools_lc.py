"""The project artifact library, as tools a LangChain agent can call.

These lived only as Claude-Agent-SDK MCP tools, which is one reason the
project-scoped audit could not move off that harness. The port keeps the names
and the write model; what changes is the transport (plain callables), the
argument style (typed Pydantic instead of ``args: dict``) and the result type
(a JSON string, which is what LangChain tools return).

The store is replaced at its seams — nothing here touches a database.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

from agents.core.artifact_tools import artifact_card, build_artifact_tools_lc

PROJECT = uuid4()


def _row(**over):
    fields = {
        "id": uuid4(), "group_id": uuid4(), "slug": "keyword-gap-plan", "kind": "memo",
        "content_type": "text/markdown", "title": "Keyword gap plan", "version": 2,
        "meta": {"label": "tightened intro"},
    }
    return SimpleNamespace(**{**fields, **over})


class _FakeDB:
    """`with next(get_session()) as db:` is the store's access pattern."""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _fake_db_session(monkeypatch) -> None:
    monkeypatch.setattr("db.session.get_session", lambda: iter([_FakeDB()]))


async def _call(tools, name: str, **kwargs):
    tool = next(t for t in tools if t.name == name)
    return await tool.ainvoke(kwargs)


def _tools(**over):
    return build_artifact_tools_lc(PROJECT, user_id=uuid4(), agent_type="audit_seo", **over)


# ---------------------------------------------------------------------------
# Surface
# ---------------------------------------------------------------------------

def test_the_five_tool_names_match_the_sdk_originals():
    assert [t.name for t in _tools()] == [
        "ListArtifacts", "GetArtifact", "CreateArtifact", "UpdateArtifact", "RewriteArtifact",
    ]


def test_no_project_means_no_tools():
    """An ephemeral or lead-magnet run has no library to reach into."""
    assert build_artifact_tools_lc(None) == []


def test_the_write_tools_carry_their_arguments_as_a_schema():
    tools = {t.name: t for t in _tools()}
    update = tools["UpdateArtifact"].args_schema.model_json_schema()
    assert "artifact" in update["properties"] and "edits" in update["properties"]
    # A nested edit is a real object, not a free-form dict.
    assert update["$defs"]["TextEdit"]["required"] == ["old_str", "new_str"]


# ---------------------------------------------------------------------------
# Reports stay out of the generic write path
# ---------------------------------------------------------------------------

async def test_creating_a_report_is_refused():
    result = await _call(
        _tools(), "CreateArtifact",
        slug="q3", title="Q3", kind="report", content_type="text/markdown", content="x",
    )
    assert "report flow" in result


async def test_editing_a_report_is_refused(monkeypatch):
    import service.artifact_store as store

    monkeypatch.setattr(store, "resolve_reference", lambda *_a, **_k: _row(kind="report"))
    _fake_db_session(monkeypatch)

    result = await _call(
        _tools(), "RewriteArtifact", artifact="q3", content="new", label="l",
    )
    assert "report flow" in result


async def test_an_unknown_content_type_is_refused_before_any_write():
    result = await _call(
        _tools(), "CreateArtifact",
        slug="s", title="T", kind="memo", content_type="application/x-invented", content="x",
    )
    assert "Unsupported content_type" in result
    assert "text/markdown" in result, "the refusal must say what is allowed"


# ---------------------------------------------------------------------------
# Failures come back as text the model can act on
# ---------------------------------------------------------------------------

async def test_a_failed_edit_match_names_the_fallback(monkeypatch):
    import service.artifact_store as store

    monkeypatch.setattr(store, "resolve_reference", lambda *_a, **_k: _row())
    monkeypatch.setattr(store, "artifact_text_content", lambda _row: "the body")
    monkeypatch.setattr(store, "apply_text_edits", lambda _src, _edits: ("", ["no match for 'nope'"]))
    _fake_db_session(monkeypatch)

    result = await _call(
        _tools(), "UpdateArtifact",
        artifact="keyword-gap-plan", edits=[{"old_str": "nope", "new_str": "x"}],
    )
    assert "no match for 'nope'" in result
    assert "RewriteArtifact" in result, "a failed match must point at the fallback"


async def test_a_version_conflict_is_returned_not_raised(monkeypatch):
    import service.artifact_store as store

    def _conflict(*_a, **_k):
        # The exception carries the newer head so a caller can merge onto it.
        raise store.ArtifactConflict(_row(version=3))

    monkeypatch.setattr(store, "resolve_reference", lambda *_a, **_k: _row())
    monkeypatch.setattr(store, "revise_artifact", _conflict)
    _fake_db_session(monkeypatch)

    result = await _call(
        _tools(), "RewriteArtifact", artifact="keyword-gap-plan", content="new", expected_version=2,
    )
    assert "latest is v3" in result
    assert "re-read and retry" in result, "a conflict must tell the model what to do next"


async def test_a_missing_artifact_says_so(monkeypatch):
    import service.artifact_store as store

    monkeypatch.setattr(store, "resolve_reference", lambda *_a, **_k: None)
    _fake_db_session(monkeypatch)

    result = await _call(_tools(), "RewriteArtifact", artifact="ghost", content="x")
    assert "No artifact matching 'ghost'" in result


# ---------------------------------------------------------------------------
# The card
# ---------------------------------------------------------------------------

async def test_a_successful_write_emits_the_card_and_returns_it(monkeypatch):
    import service.artifact_store as store

    row = _row(version=3)
    monkeypatch.setattr(store, "resolve_reference", lambda *_a, **_k: _row())
    monkeypatch.setattr(store, "revise_artifact", lambda *_a, **_k: row)
    _fake_db_session(monkeypatch)
    cards: list[dict] = []

    async def on_artifact(card: dict) -> None:
        cards.append(card)

    result = await _call(
        _tools(on_artifact=on_artifact), "RewriteArtifact",
        artifact="keyword-gap-plan", content="new", label="tightened intro",
    )

    assert cards == [artifact_card(row)]
    assert json.loads(result)["rewritten"]["version"] == 3


async def test_a_broken_card_consumer_does_not_fail_the_write(monkeypatch):
    """The card is UI sugar; a dead SSE consumer must not lose a saved version."""
    import service.artifact_store as store

    monkeypatch.setattr(store, "resolve_reference", lambda *_a, **_k: _row())
    monkeypatch.setattr(store, "revise_artifact", lambda *_a, **_k: _row(version=4))
    _fake_db_session(monkeypatch)

    async def on_artifact(_card: dict) -> None:
        raise RuntimeError("SSE consumer gone")

    result = await _call(
        _tools(on_artifact=on_artifact), "RewriteArtifact", artifact="k", content="new",
    )
    assert json.loads(result)["rewritten"]["version"] == 4
