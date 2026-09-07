"""Duct's agent ports — the boundaries an agent SDK is allowed to touch.

Duct rents an agent harness; it does not marry one. Harnesses are the
fastest-churning, least-differentiated layer in this stack — ``deepagents`` is
0.x on a weekly cadence, and ADK and the Claude Agent SDK have each already
been rented and returned. The durable assets are the domain layer
(prompts, tools, schemas, goals, scoring, the artifact contract) and the
boundaries around the harness. Those boundaries are the ports declared here.

What this module is NOT
-----------------------
There is deliberately **no** ``AgentHarness`` interface, and there should never
be one. Harnesses differ in *capability*, not just API shape:

  * Take the intersection and you lose subagents, filesystem, skills, HITL
    granularity and compaction — the entire reason to rent a harness.
  * Take the union and you are writing a framework, plus adapters for it, which
    is strictly worse than the three-engine problem this replaced.

So the harness is allowed to be harness-shaped *inside a runner*. What crosses
its boundary is standardized. That is what made removing an engine a normal
week rather than a rewrite: when the Claude Agent SDK went, the domain layer
did not move, and the audit runner it had served kept its prompts, tools,
schemas and event vocabulary unchanged.

The rule for adding a port
--------------------------
**Write the adapter on the second implementation, not the first.** A port with
one implementation is a guess; a port with two is a fact.

Every port below now has exactly one adapter, because there is one engine. That
is not a reason to collapse them into their callers. They were each *earned*
against a second implementation that has since been retired, and the shape they
were pulled into is what a third harness would arrive through — the ADK
migration and the SDK removal both went through these seams. Deleting a proven
boundary because its second implementation is gone is how the next migration
becomes a rewrite. What the rule forbids is inventing a *new* port on a single
implementation.

The ports
---------

=========================  ==========================================  =================================
Port                       Contract                                    Adapters
=========================  ==========================================  =================================
Tools                      plain domain callable + a description        ``build_memory_tools_lc``,
                           single-sourced next to it                    ``build_artifact_tools_lc``,
                                                                        ``build_execution_tools_lc``
                                                                        (each had an SDK twin)
Events out                 ``AgentEvent`` / ``EventKind`` vocabulary    ``stream_agent`` (agents/core/lc.py);
                           + an ``Emitter``                             the SDK's ``pump_stream_event`` was
                                                                        the second, until V3 went
                                                                        (agents/core/events.py)
Human-in-the-loop          ``bridge_ask_user_question`` — emit          tool-shaped on V1; was SDK-shaped
                           QUESTIONS_REQUIRED, await a Future           on V3 (agents/core/session.py)
Artifacts                  ``<duct_artifact>`` tag +                    harness-neutral by construction
                           ``DuctArtifactStreamParser`` +               (agents/core/stream.py,
                           ``ArtifactPersister``                        service/artifact_store.py)
Session / state            ``BaseAgentSession`` registry                *one impl* — in-process. The
                                                                        LangGraph checkpointer is the
                                                                        natural second; do not abstract
                                                                        before it exists.
Model transport            ``Provider`` / ``ModelName`` / ``Engine``    native Anthropic, native Gemini,
                           registries + ``get_api_key_kwargs``          native OpenAI, native OpenRouter;
                                                                        OpenAI-compatible for any gateway
                                                                        without a package of its own
                                                                        (agents/models.py, engines.py)
=========================  ==========================================  =================================

The external standard behind each port
--------------------------------------
Ports point at contracts with multi-vendor backing, not at Duct inventions:

  * **Tools → MCP.** Under the Linux Foundation's Agentic AI Foundation since
    Dec 2025 (OpenAI, Anthropic, Google, Microsoft, AWS, Block). We bind tools
    as plain callables for cost, but keep them MCP-*expressible*: the source of
    truth is a plain function plus a description, never a framework object.
  * **Model transport → OpenAI-compatible chat completions.** The one interface
    every provider implements, and therefore the floor this port guarantees:
    any gateway can be reached by making its endpoint a config value, no new
    dependency required. A first-party package is taken *over* that floor where
    one exists — OpenRouter's ``ChatOpenRouter`` carries routing preferences and
    a reasoning object the bare shape has nowhere to put — but the floor is what
    makes Ollama, vLLM or llama.cpp a config entry rather than a project.
  * **Events out → AG-UI.** See ``AG_UI_EVENT`` in agents/core/events.py for the
    mapping and for why we map rather than rename.
  * **Observability → OpenTelemetry GenAI semantic conventions.** See
    agents/core/telemetry.py. Pinned, because ``gen_ai.agent`` is still
    experimental.

Enforcement
-----------
``tests/test_harness_boundaries.py`` fails if an agent-framework import appears
outside the adapter allowlist. That is what makes "modular" a property of the
codebase rather than an intention in a document.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Emitter", "ToolBinder", "AskUser"]


@runtime_checkable
class Emitter(Protocol):
    """Push one event onto an agent's outbound stream.

    ``body`` always carries an ``event`` key holding an ``AgentEvent`` value;
    the rest of the keys are per-event payload. Implementations must never
    raise into the agent loop — delivery is best-effort by contract, which is
    what lets ``ArtifactPersister``/``ConversationRecorder`` wrap this safely
    (SSE first, persistence after).
    """

    async def __call__(self, body: dict) -> None: ...


@runtime_checkable
class ToolBinder(Protocol):
    """Bind Duct domain functions into one harness's native tool objects.

    The domain logic lives in plain sync/async functions with zero framework
    imports; a binder is the thin shim that wraps them. Returns whatever the
    target harness accepts — ``StructuredTool`` today, MCP tool dicts when the
    Claude Agent SDK was also a target — hence ``list[Any]``: the point of the
    port is that callers never inspect the elements.

    Reference: ``build_memory_tools_lc``, whose bodies were shared with an SDK
    twin for a year and did not change when that twin went.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> list[Any]: ...


@runtime_checkable
class AskUser(Protocol):
    """Suspend a run until a human answers, then resume it.

    The harness-neutral half is ``bridge_ask_user_question``: emit
    QUESTIONS_REQUIRED, await an ``asyncio.Future`` the messages route
    resolves, return the completed tool input. Each harness only supplies the
    shape that suspends it — a LangChain tool today, an SDK tool callback when
    V3 was also a target. LangGraph's ``interrupt()`` is the upgrade path, and
    it plugs in here without the route or the frontend noticing.
    """

    async def __call__(self, session: Any, session_id: str, input_data: dict, emit: Emitter) -> dict: ...
