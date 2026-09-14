"""One way to build an agent's user turn, for every agent there will ever be.

Every agent had its own answer to "what does the model need to know about this
person, this project and this moment". Insights assembled four blocks in one
order, audit hand-rolled a ``<business_context>`` with its own labels and called
the operator ``<user_preferences>``, content prepended a voice block and
appended memory. The cost was not the duplication, it was that nothing declared
the intent: ``display_name`` reached insights and content and silently missed
audit for a release, because no single place said what an agent gets.

So an agent declares a :class:`ContextSpec` in ``agents/registry.py``, a run
resolves a :class:`TurnContext` once, and :func:`build_turn` renders them. A new
agent that declares nothing gets everything, which is the right default: the
failure mode of an extra block is a few hundred tokens, and the failure mode of
a missing one is a report that does not know who asked for it.

Two invariants this file exists to hold:

**Per-user and per-project text lives in the user turn, never the system
prompt.** A system prompt is the cached prefix; one customer's name in it gives
every account a prefix of its own and loses the hit on every call of every run.
That rule used to live in comments in three modules. It is now structural —
there is no argument to :func:`build_turn` that can reach a system prompt — and
``tests/test_turn.py`` fails if a builder starts interpolating per-user
data into one anyway.

**Blocks render most-stable first, most-volatile last.** Within a session this
is free: turn one becomes the prefix for turn two whatever the order. It pays
across runs. Two insights runs on the same project a week apart share a system
prompt, and if their turns open with the same byte-identical
``<business_context>`` and ``<user_context>``, the cached prefix extends past
the system prompt into the turn. Put the memory digest first instead and the
match ends at the first block, because memory moved in between. Hence
:data:`BLOCK_ORDER`, which is the whole point of the module and the one thing
not to "tidy" into declaration order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.core.prompts import xml_block

#: Canonical block order: stable at the top, volatile at the bottom, request
#: last. Changing this order is a cache decision, not a formatting one — read
#: the module docstring before you do. Names match the rendered XML tag.
BLOCK_ORDER: tuple[str, ...] = (
    "business_context",   # project settings — changes when someone edits them
    "user_context",       # the operator's profile — changes ~never
    "report_guidance",    # how to shape the deliverable for them — derived from the profile
    "agent_context",      # stored per-(project, agent) working notes
    "prior_reports",      # artifact summaries — appended to, rarely rewritten
    "project_memory",     # memory digest — moves whenever the agent learns
    "data_sources",       # connection + account state — per run
    "deliverable_format", # per-run posture
    "autonomy",           # per-run posture
    "request",            # the ask itself — different every turn
)


@dataclass(frozen=True)
class ContextSpec:
    """What one agent wants in its turn. Declared once, in the registry.

    Everything defaults to on. An agent opts out of what genuinely does not
    apply to it — a paid-ads budget in an SEO crawl is noise the model has to
    read past — and opting out is one named field, not a new code path.

    ``paid_section`` and ``organic_section`` are sub-toggles of
    ``business_context``: the business context model is a superset covering
    every agent, and a run should see the part that bears on it.
    """

    business_context: bool = True
    paid_section: bool = True
    organic_section: bool = True
    user_context: bool = True
    agent_context: bool = True
    prior_reports: bool = True
    project_memory: bool = True
    data_sources: bool = True

    def wants(self, block: str) -> bool:
        """Whether ``block`` is enabled. Unknown blocks are always allowed.

        Posture blocks (``deliverable_format``, ``autonomy``) and ``request``
        have no toggle: they are properties of the run, not of the agent, and
        an agent that passes one means it.
        """
        return bool(getattr(self, block, True))


#: What an agent that declares nothing gets.
DEFAULT_SPEC = ContextSpec()


@dataclass
class TurnContext:
    """The rendered blocks for one turn, keyed by tag.

    Deliberately holds rendered strings rather than models. Resolution is
    per-agent and touches the database, the profile row and the memory service;
    rendering is pure. Keeping them apart is what lets ``tests/test_turn.py``
    assert the ordering without a database.
    """

    blocks: dict[str, str] = field(default_factory=dict)

    def set(self, tag: str, text: str) -> "TurnContext":
        """Record a rendered block. Empty text is dropped, not stored as ''."""
        if text and text.strip():
            self.blocks[tag] = text.strip()
        return self

    def get(self, tag: str) -> str:
        return self.blocks.get(tag, "")


def build_turn(
    *,
    spec: ContextSpec = DEFAULT_SPEC,
    context: TurnContext,
    request: str = "",
    request_fallback: str = "",
    wrap_request: bool = True,
) -> str:
    """Assemble the user turn: context blocks in canonical order, then the ask.

    Blocks the spec has switched off are dropped even when the caller rendered
    them, so a toggle is honoured at one point rather than at every call site.
    Blocks absent from :data:`BLOCK_ORDER` are appended after the ordered ones
    and before the request, so an agent with a block of its own is not blocked
    on editing this file — but anything reused by a second agent belongs in the
    order, where its cache position is a decision someone made on purpose.
    """
    parts: list[str] = []
    for tag in BLOCK_ORDER:
        if tag == "request":
            continue
        if not spec.wants(tag):
            continue
        rendered = context.get(tag)
        if rendered:
            parts.append(rendered)

    for tag, rendered in context.blocks.items():
        if tag not in BLOCK_ORDER and rendered:
            parts.append(rendered)

    body = (request or "").strip() or (request_fallback or "").strip()
    if body:
        # ``wrap_request=False`` is for an agent whose opening turn is already a
        # composed instruction rather than a user's words. Tagging one would
        # change prompt bytes for no gain — the ask is last either way, which is
        # the only thing the cache cares about.
        parts.append(xml_block("request", body) if wrap_request else body)
    return "\n\n".join(parts)


def spec_for(agent_type: str) -> ContextSpec:
    """The declared spec for an agent type, or the all-on default.

    Unknown types get the default rather than raising: a run is not worth
    failing over a registry entry someone has not written yet, and the default
    is the safe direction to be wrong in.
    """
    try:
        from agents.registry import AGENT_REGISTRY

        entry = AGENT_REGISTRY.get(agent_type)
        return getattr(entry, "context", None) or DEFAULT_SPEC
    except Exception:  # noqa: BLE001 — a prompt detail, never a blocker
        return DEFAULT_SPEC


__all__ = [
    "BLOCK_ORDER",
    "ContextSpec",
    "DEFAULT_SPEC",
    "TurnContext",
    "build_turn",
    "spec_for",
]
