"""Unit tests for knowledge packs, project-memory context blocks, and the
prior-artifact MCP tools (Phase 3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.conftest import make_sqlite_engine
from sqlmodel import Session

from agents.audit.prompts import build_audit_user_prompt, build_unified_system_prompt
from agents.audit.schema import AuditBusinessContext, CrawlPlan, CrawlResult
from agents.core.artifact_tools import build_artifact_tools_lc
from agents.core.context import format_agent_context, format_prior_artifacts
from agents.knowledge import knowledge_block, load_knowledge_pack
import db.session as db_session_module
from models.artifact import Artifact
from models.auth import User
from models.project import Project


# ---------------------------------------------------------------------------
# Knowledge packs
# ---------------------------------------------------------------------------

def test_missing_pack_returns_empty():
    assert load_knowledge_pack("nonexistent_connector") == ""
    assert knowledge_block(("nonexistent_connector",)) == ""


def test_seeded_packs_load():
    for name, marker in [
        ("gsc", "Paginate or lose the long tail"),
        ("ga4", "internal-traffic filtering"),
        ("google_ads", "micros"),
        ("gtm", "record the outgoing live version"),
    ]:
        pack = load_knowledge_pack(name)
        assert marker.lower() in pack.lower(), f"{name} pack missing marker"


def test_system_prompt_static_across_calls_and_includes_packs():
    p1 = build_unified_system_prompt("template", "seo_v1", knowledge_packs=("gsc",))
    p2 = build_unified_system_prompt("template", "seo_v1", knowledge_packs=("gsc",))
    assert p1 == p2  # cached-prefix invariant
    assert "<connector_knowledge>" in p1
    assert "<connector_knowledge>" not in build_unified_system_prompt("template", "seo_v1")


# ---------------------------------------------------------------------------
# Project-memory blocks in the user prompt
# ---------------------------------------------------------------------------

def _stub_crawl():
    return CrawlResult(plan=CrawlPlan(root_url="https://example.com"))


def test_user_prompt_extra_context_placement():
    block = format_prior_artifacts([
        SimpleNamespace(
            id=uuid4(), created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            title="SEO audit — example.com", kind="report", version=2,
            summary="Score 71. Top issue: missing meta descriptions.",
        )
    ])
    assert "<prior_reports>" in block and "Score 71" in block

    prompt = build_audit_user_prompt(_stub_crawl(), AuditBusinessContext(), extra_context=block)
    assert "<prior_reports>" in prompt
    assert "<prior_reports>" not in build_audit_user_prompt(_stub_crawl(), AuditBusinessContext())


def test_format_agent_context():
    assert format_agent_context(None) == ""
    assert format_agent_context({}) == ""
    block = format_agent_context({"preferred_tone": "direct", "focus": ["blog"]})
    assert "<agent_context>" in block and "preferred_tone" in block


# ---------------------------------------------------------------------------
# Prior-artifact MCP tools (project scoping)
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded(monkeypatch, tmp_path):
    engine = make_sqlite_engine()

    def _fake_db():
        yield Session(engine)

    monkeypatch.setattr(db_session_module, "get_session", _fake_db)
    # artifact_store binds db_session at import time — patch that name too so
    # persist_artifact_version writes into THIS engine, not the dev DB.
    import service.artifact_store as store_module

    monkeypatch.setattr(store_module, "db_session", _fake_db)
    import service.storage as storage_module
    from config import Configs

    cfg = Configs(storage_backend="local", uploads_dir=str(tmp_path))
    monkeypatch.setattr(storage_module, "get_configs", lambda: cfg)

    with Session(engine) as db:
        owner = User(email="tools@example.com")
        db.add(owner)
        db.commit()
        db.refresh(owner)
        mine = Project(user_id=owner.id, name="Mine")
        other = Project(user_id=owner.id, name="Other")
        db.add(mine)
        db.add(other)
        db.commit()
        db.refresh(mine)
        db.refresh(other)
        mine_id, other_id = mine.id, other.id
        rows = {}
        for proj_id, title in ((mine_id, "my report"), (other_id, "other report")):
            row = Artifact(
                group_id=uuid4(), version=1, project_id=proj_id, user_id=owner.id,
                agent_type="audit_seo", kind="report", content_type="application/json",
                title=title, structured_json={"t": title}, summary=f"summary of {title}",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            rows[title] = SimpleNamespace(id=row.id)
    return SimpleNamespace(mine=mine_id, other=other_id, rows=rows)


async def _call(tool_obj, **kwargs) -> str:
    """LangChain tools take keyword arguments and return a JSON string."""
    return await tool_obj.ainvoke(kwargs)


async def test_list_artifacts_scoped_to_project(seeded):
    list_tool = build_artifact_tools_lc(seeded.mine)[0]
    payload = json.loads(await _call(list_tool, kind="report"))
    titles = [a["title"] for a in payload["artifacts"]]
    assert titles == ["my report"]


async def test_get_artifact_denies_cross_project(seeded):
    get_tool = build_artifact_tools_lc(seeded.mine)[1]
    ok = await _call(get_tool, artifact_id=str(seeded.rows["my report"].id))
    assert "structured_json" in ok
    denied = await _call(get_tool, artifact_id=str(seeded.rows["other report"].id))
    assert "No artifact" in denied


# ---------------------------------------------------------------------------
# Write tools — create / patch-transport update / rewrite / conflicts
# ---------------------------------------------------------------------------

async def test_create_update_rewrite_flow(seeded):
    cards = []

    async def on_artifact(card):
        cards.append(card)

    _, _, create, update, rewrite = build_artifact_tools_lc(seeded.mine, on_artifact=on_artifact)

    created = await _call(
        create, slug="Keyword Gap Plan!", title="Keyword gap plan", kind="plan",
        content_type="text/markdown",
        content="# Plan\n\nTarget the zero-click long tail first.",
    )
    card = json.loads(created)["created"]
    assert card["slug"] == "keyword-gap-plan"  # slugified
    assert card["version"] == 1
    assert cards[-1]["slug"] == "keyword-gap-plan"  # in-chat card emitted

    # Targeted patch by slug — exact-string transport, new full version stored.
    updated = await _call(
        update, artifact="keyword-gap-plan",
        edits=[{"old_str": "zero-click long tail", "new_str": "high-intent long tail"}],
        label="sharpened targeting", expected_version=1,
    )
    card2 = json.loads(updated)["updated"]
    assert card2["version"] == 2 and card2["label"] == "sharpened targeting"

    # Failed match → clean retryable error steering to rewrite, no new version.
    failed = await _call(
        update, artifact="keyword-gap-plan",
        edits=[{"old_str": "does not exist", "new_str": "x"}], expected_version=2,
    )
    assert "RewriteArtifact" in failed

    # Optimistic concurrency: stale expected_version conflicts.
    stale = await _call(
        rewrite, artifact="keyword-gap-plan", content="# Plan v3", expected_version=1,
    )
    assert "conflict" in stale.lower()

    ok = await _call(
        rewrite, artifact="keyword-gap-plan", content="# Plan v3", expected_version=2,
    )
    assert json.loads(ok)["rewritten"]["version"] == 3


async def test_write_tools_reject_reports_and_bad_json(seeded):
    _, _, create, update, _ = build_artifact_tools_lc(seeded.mine)
    # Reports go through the report flow.
    denied = await _call(
        update, artifact=str(seeded.rows["my report"].id),
        edits=[{"old_str": "a", "new_str": "b"}],
    )
    assert "report flow" in denied
    # JSON vendor types must parse after any write.
    bad = await _call(
        create, slug="broken-table", title="Broken", kind="dataset",
        content_type="application/vnd.duct.table+json", content="not json at all",
    )
    assert "not valid JSON" in bad
