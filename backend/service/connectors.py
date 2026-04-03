"""Connector registry, auth context, and adapter protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

# Capability tokens for optional connector features
CAP_ACCOUNTS = "accounts"
CAP_CAMPAIGN_REPORT = "campaign_report"


@dataclass(frozen=True)
class ConnectorMeta:
    """Product-facing connector catalog entry."""

    id: str
    label: str
    oauth_scope: str | None
    capabilities: frozenset[str]


@dataclass(frozen=True)
class ConnectorAuthContext:
    """User/session credentials and hints (not server env secrets)."""

    connector_id: str
    refresh_token: str | None = None
    extras: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class ConnectorAdapter(Protocol):
    """Strategy for connector-specific interactive operations."""

    def list_accounts(self, auth: ConnectorAuthContext) -> list[dict[str, Any]]:
        """Return account rows for UIs; raises ValueError for bad auth, RuntimeError for upstream."""
        ...


CONNECTOR_REGISTRY: dict[str, tuple[ConnectorMeta, ConnectorAdapter]] = {}


def register_connector(meta: ConnectorMeta, adapter: ConnectorAdapter) -> None:
    CONNECTOR_REGISTRY[meta.id] = (meta, adapter)


def get_connector(connector_id: str) -> tuple[ConnectorMeta, ConnectorAdapter]:
    """Return metadata and adapter, or raise KeyError if unknown."""
    return CONNECTOR_REGISTRY[connector_id]


def normalize_connector_id(connector_id: str) -> str:
    """Normalize path or form values: ``google-ads`` → ``google_ads``."""
    return connector_id.strip().lower().replace("-", "_")
