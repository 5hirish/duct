"""Wire shapes for the Content Planner agent (content_planner).

Domain shapes (PlanDraft, Day, PlanStrategy, ContentBrandContext) are reused
from agents.content.schema — the planner writes the same content_plans rows.
Only the request/session/config shapes are planner-specific.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agents.core.session import BaseAgentSession
from agents.models import Platform

# The planner has one mode (it manages/refreshes the canonical plan). Kept as a
# Literal for symmetry with content's RunMode and so the session shape is typed.
PlannerMode = Literal["update_plan"]


class PlannerTool(StrEnum):
    """Fully-namespaced names of the planner MCP tools (server ``duct_planner``).

    The @tool decorators register the short names; the SDK namespaces them as
    ``mcp__duct_planner__<short>``. This enum holds the namespaced form used in
    ClaudeAgentOptions.allowed_tools and the can_use_tool dispatch (mirrors
    ContentTool in agents/content/schema.py). Keep in sync with tools.py.
    """

    SUBMIT_PLAN          = "mcp__duct_planner__submit_plan"
    FETCH_BRAND_CONTEXT  = "mcp__duct_planner__fetch_brand_context"
    FETCH_PLANNER_CONFIG = "mcp__duct_planner__fetch_planner_config"
    SAVE_PLANNER_CONFIG  = "mcp__duct_planner__save_planner_config"
    FETCH_POST_METRICS   = "mcp__duct_planner__fetch_post_metrics"
    SYNC_ALL_POSTS       = "mcp__duct_planner__sync_all_posts"


class PlannerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    # First day of the rolling 7-day window. Defaults to today server-side.
    start_date: date | None = None


class PlannerConfig(BaseModel):
    """Per-project planner configuration.

    Persisted in agent_contexts (agent_id='content_planner', data=this dump).
    Gathered via AskUserQuestion on first run when incomplete.
    """

    model_config = ConfigDict(extra="ignore")

    # Which connected platforms to plan for (constrained to linked accounts).
    platforms: list[Platform] = Field(default_factory=list)
    # Posting cadence — posts per day (default 1). The plan spans the next 7 days,
    # so total posts ≈ posts_per_day × 7.
    posts_per_day: int = Field(default=1, ge=1, le=10)
    # Top geographies to optimise timing/relevance for — 1 to 3.
    geographies: list[str] = Field(default_factory=list)
    # The primary business objective this plan should drive — anchors the funnel
    # mix. e.g. awareness | followers | saves | website_traffic | trial_signups | sales
    primary_objective: str = ""
    # Where the CTA points (bio link / offer / landing page) — used for BOFU posts.
    cta_destination: str = ""
    # Anything coming up to plan around — launches, promos, events, seasonal moments.
    upcoming: str = ""
    # Audience deep-dive (optional refinements the strategist plans against).
    audience_pains: str = ""
    audience_desires: str = ""
    audience_objections: str = ""
    # Optional per-platform preferred local posting time notes (platform -> note).
    posting_times: dict[str, str] = Field(default_factory=dict)
    updated_at: datetime | None = None

    @field_validator("geographies")
    @classmethod
    def _cap_geographies(cls, v: list[str]) -> list[str]:
        cleaned = [g.strip() for g in v if isinstance(g, str) and g.strip()]
        return cleaned[:3]

    def is_complete(self) -> bool:
        """True once the agent has enough to plan without re-asking. Platforms,
        geographies, and the primary objective are the decision-critical inputs;
        the rest are optional refinements the agent infers when absent."""
        return bool(self.platforms) and bool(self.geographies) and bool(self.primary_objective)


@dataclass(kw_only=True)
class PlannerSession(BaseAgentSession):
    """Per-session state — BaseAgentSession plus planner-specific fields.

    Mirrors ContentSession's resume/recorder plumbing so the planner gets the
    same chat-history / resume behaviour through the shared routes layer.
    """

    project_id: UUID
    mode: PlannerMode = "update_plan"
    plan_id: UUID | None = None
    conversation_id: UUID | None = None
    recorder: Any = None
    resume: bool = False
    needs_reprime: bool = False
    resume_primer: str = ""
    todos: list[dict] = field(default_factory=list)


def make_planner_session(session_id: str, project_id: UUID) -> PlannerSession:
    """Build a PlannerSession with fresh asyncio queues."""
    return PlannerSession(
        session_id=session_id,
        agent_type="content_planner",
        project_id=project_id,
        mode="update_plan",
        event_queue=asyncio.Queue(),
        chat_queue=asyncio.Queue(),
        answer_future=None,
        created_at=time.monotonic(),
    )


__all__ = [
    "PlannerConfig",
    "PlannerMode",
    "PlannerRequest",
    "PlannerSession",
    "PlannerTool",
    "make_planner_session",
]
