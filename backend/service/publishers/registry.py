"""Social schedulers as connectors: which ones exist, which a person connected.

Nothing publishes by default. A project publishes through a scheduler its
owner connected (their own key, ``service/vendor_keys.py``), and each linked
account remembers which scheduler holds it, so a project can post to LinkedIn
through one and TikTok through another. A post that went out records its
scheduler too (``ContentPost.publisher``), because the one that holds a
queued post is the only one that can change or cancel it.

Adding a scheduler is an adapter beside its client that satisfies
``Publisher`` (``base.py``), its ``PublisherSpec`` in ``_SPECS`` below, and
nothing else: the routes, the agent's tools and the app's Accounts tab read
this list.
"""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session

from service.post_bridge.publisher import POSTBRIDGE, PostBridgePublisher
from service.publishers.base import Publisher, PublisherSpec
from service.vendor_keys import VendorNotConnected
from service.zernio.publisher import ZERNIO, ZernioPublisher

# Display order on the Accounts tab; no scheduler outranks another.
_SPECS: dict[str, tuple[PublisherSpec, type]] = {
    POSTBRIDGE.id: (POSTBRIDGE, PostBridgePublisher),
    ZERNIO.id: (ZERNIO, ZernioPublisher),
}

NO_SCHEDULER = (
    "No scheduler is connected yet. Connect "
    + " or ".join(spec.label for spec, _ in _SPECS.values())
    + " in Content → Accounts and link the account to post from."
)


def all_specs() -> tuple[PublisherSpec, ...]:
    return tuple(spec for spec, _ in _SPECS.values())


def spec_for(publisher_id: str | None) -> PublisherSpec | None:
    entry = _SPECS.get(publisher_id or "")
    return entry[0] if entry else None


def connected_specs(owner_id: UUID, db: Session) -> list[PublisherSpec]:
    """The schedulers ``owner_id`` can publish through: a key they saved, or
    the instance's own where it may be spent (local and desktop)."""
    return [spec for spec, _ in _SPECS.values() if spec.key.source(owner_id, db) is not None]


def open_publisher(publisher_id: str, api_key: str) -> Publisher:
    _, cls = _SPECS[publisher_id]
    return cls(api_key)


def publisher_for(owner_id: UUID, publisher_id: str, db: Session) -> Publisher:
    """The scheduler ``publisher_id`` on the key ``owner_id`` may spend, or
    ``VendorNotConnected`` saying where to connect it."""
    spec = spec_for(publisher_id)
    if spec is None:
        raise VendorNotConnected(NO_SCHEDULER)
    return open_publisher(spec.id, spec.key.resolve(owner_id, db))


__all__ = [
    "NO_SCHEDULER",
    "all_specs",
    "connected_specs",
    "open_publisher",
    "publisher_for",
    "spec_for",
]
