"""Connector knowledge packs — the encoded gotcha corpus.

Each ``<name>.md`` distills hard-won, platform-specific traps ("this API lies
to you like *this*") from real engagements into rules an agent reads every
session. Packs are static per agent configuration and injected into the
SYSTEM prompt (never per-request data), so the cached prompt prefix stays
byte-identical across sessions of the same mode.

Add a pack: drop ``<name>.md`` here and list it in the agent's pack tuple.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PACK_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=32)
def load_knowledge_pack(name: str) -> str:
    """Contents of ``<name>.md``, or "" when absent (never raises)."""
    path = _PACK_DIR / f"{name}.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def knowledge_block(names: tuple[str, ...] | list[str]) -> str:
    """Concatenate packs into one <connector_knowledge> XML block ("" if none)."""
    packs = [p for p in (load_knowledge_pack(n) for n in names) if p]
    if not packs:
        return ""
    body = "\n\n".join(packs)
    return (
        "<connector_knowledge>\n"
        "Hard-won platform facts. Trust these over intuition — each one was "
        "verified against live accounts and exists because the naive reading "
        "produced a plausible wrong number.\n\n"
        f"{body}\n"
        "</connector_knowledge>"
    )
