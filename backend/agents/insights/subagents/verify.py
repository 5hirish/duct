"""The verification subagent — prove the number before the analyst uses it.

A separate context, not a step in the main loop, for two reasons:

* **Context hygiene.** Running twelve checks means fetching several entities and
  reasoning about each; doing that inline would fill the analyst's window with
  check plumbing before it wrote a word of the actual answer.
* **A different job.** The analyst is trying to find what matters. The verifier
  is trying to find what is wrong with the data — an adversarial posture that
  reads badly when mixed into the same turn.

Its system prompt is static (see ``agents/insights/checks.py::all_checks_block``),
so it stays in the cached prefix. It discovers coverage by fetching: a
``not_connected`` result turns a check into its declared gap line rather than
into a failure.
"""

from __future__ import annotations

from typing import Any

from agents.insights.checks import all_checks_block

VERIFY_SUBAGENT_NAME = "verify"

DESCRIPTION = (
    "Check whether this project's marketing data can be trusted before you draw "
    "conclusions from it. Delegate to this before any analysis that will carry a "
    "recommendation, and pass the specific question you are trying to answer. Returns "
    "what it verified, what it found wrong, and — importantly — what it could not check "
    "at all."
)

SYSTEM_PROMPT = f"""\
You are Duct's data integrity checker. You are not writing the analysis; you are \
deciding whether the analysis can be trusted, and the main agent is waiting on \
your answer.

Marketing data does not error. It returns a plausible wrong value, and every \
number downstream repeats it. Everything below is a check that exists because \
the naive reading produced a believable wrong number in a real account.

## How to work

1. Read the connector notes (**ReadConnectorNotes**) for each source you touch \
BEFORE judging its numbers. The notes are the specific ways that platform lies.
2. Fetch what the checks need (**FetchData**). Fetch once per entity; do not \
re-fetch the same entity with the same window.
3. Run every check you have the data for.
4. When a check's data is unreachable — `not_connected`, `needs_account`, or a \
failed fetch — do NOT treat it as a finding and do NOT ask for a connection. \
Report it verbatim as the gap line given with that check.

## What to report

Be specific and be brief. For each check: what you looked at, over what window, \
and what you concluded. State confidence honestly — "consistent with X, but this \
data cannot distinguish X from Y" is a better answer than a verdict you cannot \
support.

Finish with two lists, both of which the main agent will use:

- **Trust these numbers**: what you verified, and over what window.
- **Could not verify**: every gap line, verbatim. This list is not a failure \
report — it is half the value. A number nobody checked should never be presented \
with the same confidence as one that was.

Never invent a figure. Never soften a finding to be agreeable. If everything \
checks out, say so plainly and briefly.

## The checks
{all_checks_block()}
"""


def build_verify_subagent(tools: list[Any], model: Any = None) -> dict:
    """The verifier as a ``deepagents`` SubAgent.

    ``tools`` is the data-tool list the parent already built, passed through so
    the subagent shares the parent's project scoping and credential closure —
    it never resolves its own. ``model`` allows a cheaper model for the checking
    pass than for the analysis.
    """
    subagent: dict[str, Any] = {
        "name": VERIFY_SUBAGENT_NAME,
        "description": DESCRIPTION,
        "system_prompt": SYSTEM_PROMPT,
        "tools": tools,
    }
    if model is not None:
        subagent["model"] = model
    return subagent
