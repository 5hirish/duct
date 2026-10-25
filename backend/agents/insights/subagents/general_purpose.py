"""general-purpose sub-agent — the harness's default, made read-only.

``deepagents`` mounts a sub-agent named ``general-purpose`` on every deep agent
unless the caller supplies one by that name, and its default carries EVERY
tool of the parent. For the insights analyst that meant a helper holding
ProposeChanges, RollbackChangeSet, RememberFact, the artifact writers and the
pause tools, with none of the parent's limits or retry — rulebook gap 1.
Supplying this spec keeps the name (and the model's expectation that a general
helper exists) while choosing its tools: the readers and nothing that writes a
row, proposes a change, remembers, or parks the run on the user.
"""

from __future__ import annotations

from typing import Any

from agents.core.web_tools import WEB_FETCH_TOOL, WEB_SEARCH_TOOL

# deepagents' own name for its default sub-agent; supplying this name is what
# stops the harness from adding its every-tool default.
GENERAL_PURPOSE_SUBAGENT = "general-purpose"

# By tool name: the runner picks whichever of these it actually mounted, so a
# session shape without memory or artifacts simply hands the helper fewer.
GENERAL_PURPOSE_TOOLS: tuple[str, ...] = (
    "FetchData",
    "ListDataSources",
    "ReadConnectorNotes",
    "SearchMemory",
    "GetMemory",
    "ListArtifacts",
    "GetArtifact",
    "ListExecutableOps",
    "GetChangeSetStatus",
    WEB_SEARCH_TOOL,
    WEB_FETCH_TOOL,
)


def pick_read_tools(tools: list[Any]) -> list[Any]:
    """The parent's tool objects whose names are on the read-only list, so the
    helper shares the parent's project scoping and credential closure."""
    return [t for t in tools if getattr(t, "name", "") in GENERAL_PURPOSE_TOOLS]


def build_general_purpose_subagent(tools: list[Any], model: Any) -> dict[str, Any]:
    """The ``SubAgent`` spec, with the tool objects and model the runner chose."""
    return {
        "name": GENERAL_PURPOSE_SUBAGENT,
        "description": (
            "General-purpose research helper for a multi-step read-only task: "
            "pulling several entities, reading connector notes, memory and prior "
            "briefs, or the open web, then reporting back. It cannot propose "
            "changes, remember, write artifacts or ask the user — you do those."
        ),
        "system_prompt": (
            "You are a research helper for a marketing analyst. Do the task you "
            "were given using only the read tools you have, and return a concise, "
            "factual report with the numbers and their windows. Do not write the "
            "analysis, do not invent data you could not read, and do not address "
            "the user."
        ),
        "tools": list(tools),
        "model": model,
    }
