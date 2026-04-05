"""Closed vocabularies for synthesis structured output (JSON schema / LLM).

Canonical enum definitions live in ``service.google.schema`` so the brief
payload, metrics builders, and Pydantic synthesis schema share the same
reporting vocabulary. This module keeps ``Syn*`` names for the agent layer.
"""

from __future__ import annotations

from service.google.schema import (
    ActionPriority as SynActionPriority,
    ActionType as SynActionType,
    ConfidenceLevel as SynConfidenceLevel,
    EvidenceDataSource as SynDataSource,
    EvidenceEntityType as SynEntityType,
    FindingType as SynFindingType,
)

__all__ = [
    "SynActionPriority",
    "SynActionType",
    "SynConfidenceLevel",
    "SynDataSource",
    "SynEntityType",
    "SynFindingType",
]
