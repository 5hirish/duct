"""Pytest gate for a Scorecard.

Keeps the assertion out of the framework core so the scoring logic stays a
pure, importable library; tests call ``assert_scorecard`` and get a readable
markdown breakdown on failure instead of an opaque ``assert False``.
"""

from __future__ import annotations

from tests.eval.verdict import Scorecard


class ScorecardError(AssertionError):
    """Raised when an artifact fails its rubric — carries the full scorecard."""


def assert_scorecard(scorecard: Scorecard) -> None:
    """Raise with the rendered scorecard when the artifact didn't meet the bar."""
    if not scorecard.passed:
        raise ScorecardError("Agent eval did NOT meet the bar:\n\n" + scorecard.as_markdown())
