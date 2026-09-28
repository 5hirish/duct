"""Eval cases for the agent gate (``tests/eval/gate.py``), by agent.

A case is synthetic by rule: this repository is public and CI runs on it, so
a customer's session never becomes a case here. A bug found in a real session
becomes one when it reproduces on a synthetic account; otherwise it stays a
private replay (``scripts/session_replay.py``).
"""

from __future__ import annotations

from tests.eval.cases.insights import INSIGHTS_CASES

CASES = {case.id: case for case in INSIGHTS_CASES}

#: Which cases a change under each path runs. Anything shared runs them all.
AGENT_PATHS = {
    "insights": ("backend/agents/insights/",),
}


def cases_for(agent: str = "all") -> list:
    return [c for c in CASES.values() if agent in ("all", c.agent)]
