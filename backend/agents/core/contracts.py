"""Cross-cutting request + runner contracts.

These standardize the *shape* of every agent regardless of engine version, so a
v1/v2/v3 runner is swappable and routes can dispatch by interface instead of
``isinstance`` chains.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from agents.core.artifacts import BaseArtifact
from agents.core.business_context import BusinessContext
from agents.models import AgentEffort

# An agent emits SSE event bodies through this callback (see agents/core/events.py).
EmitFn = Callable[[dict], Awaitable[None]]


class BaseAgentRequest(BaseModel):
    """Fields every agent request shares. Per-agent requests (GenerateRequest,
    AuditRequest, PlanRequest) inherit and add their own."""

    engine: str = ""                      # "" | "v1" | "v2" | "v3" (falls back to config)
    effort: AgentEffort | None = None
    adaptive_thinking: bool = False
    business_context: BusinessContext = Field(default_factory=BusinessContext)


@runtime_checkable
class StreamingAgentRunner(Protocol):
    """Canonical streaming-runner interface (the v3 shape).

    A runner streams progress/events via ``emit`` and returns its final artifact
    (or None on failure). Insights' two-phase runners additionally expose
    ``setup_tools_for_goal`` / ``run_pipeline``; that engine-agnostic interface
    is documented in agents/insights and is the insights-specific contract.
    """

    async def run(
        self,
        session_id: str,
        request: Any,
        emit: EmitFn,
    ) -> BaseArtifact | None: ...
