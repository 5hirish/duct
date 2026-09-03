"""Connector registry, auth context, and adapter protocol."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from collections.abc import Mapping

logger = logging.getLogger(__name__)

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
    #: What this connector can do, for the connectors that cannot be asked.
    #: An OAuth connector's real answer is derived per credential from the
    #: scopes it was GRANTED (``service/connector_scopes.access_for``), because
    #: two users of the same connector can hold different permissions. Manual
    #: connectors have no scope to derive from — a Stripe restricted key or a
    #: Meta System User token carries its permissions out of band — so they
    #: declare it here. Read-only is the default because most of them are.
    access: frozenset[str] = frozenset({"read"})


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

# Modules whose import registers a connector. Registration is an import side
# effect, which used to mean the registry was only complete for a process that
# had imported the right routes — true for the running server, false for an
# agent tool, a test, or a script. load_connectors() makes it complete for
# everyone.
_ADAPTER_MODULES: tuple[str, ...] = (
    "service.google.ads",
    "service.google.ga4",
    "service.google.gsc",
    "service.google.gtm",
    "service.apple.ads.fetch",
    "service.meta.ads.fetch",
    "service.openai.ads.fetch",
    "service.revenuecat.fetch",
    "service.stripe.fetch",
    "service.mixpanel.fetch",
    "service.clarity.fetch",
    "service.growthbook.fetch",
)

_loaded = False


def load_connectors() -> None:
    """Import every adapter module once, so the registry is complete.

    Idempotent and best-effort per module: one connector whose optional
    dependency is missing must not hide the other eight.
    """
    global _loaded
    if _loaded:
        return
    _loaded = True
    import importlib

    for module in _ADAPTER_MODULES:
        try:
            importlib.import_module(module)
        except Exception:  # noqa: BLE001
            logger.warning("connectors: adapter %s failed to load", module, exc_info=True)


def register_connector(meta: ConnectorMeta, adapter: ConnectorAdapter) -> None:
    CONNECTOR_REGISTRY[meta.id] = (meta, adapter)


def registry() -> dict[str, tuple[ConnectorMeta, ConnectorAdapter]]:
    """The registry, guaranteed populated. Prefer this over reading
    CONNECTOR_REGISTRY directly outside a request that already booted."""
    load_connectors()
    return CONNECTOR_REGISTRY


def get_connector(connector_id: str) -> tuple[ConnectorMeta, ConnectorAdapter]:
    """Return metadata and adapter, or raise KeyError if unknown."""
    load_connectors()
    return CONNECTOR_REGISTRY[connector_id]


def normalize_connector_id(connector_id: str) -> str:
    """Normalize path or form values: ``google-ads`` → ``google_ads``."""
    return connector_id.strip().lower().replace("-", "_")
