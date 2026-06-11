"""Backwards-compatible aliases for the Content Studio agent's event vocabulary.

Event/step names are now defined once in agents/core/events.py and shared across
all agent types (content emits the subset it supports). These aliases keep
existing imports working; the frontend still mirrors the same string values in
app/src/lib/contentEvents.js.
"""

from __future__ import annotations

from agents.core.events import STEP_LABELS, AgentEvent, AgentStep, StepStatus

# Aliases — same class objects; existing `ContentEvent.X` / `ContentStep.X` access works.
ContentEvent = AgentEvent
ContentStep = AgentStep

__all__ = ["STEP_LABELS", "ContentEvent", "ContentStep", "StepStatus"]
