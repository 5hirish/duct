"""The documents onboarding reads beside the website.

Same shape as ``prefetch.py`` and for the same reason: the user adds a file on
the "Found it" card, then spends 30–90 seconds connecting a provider, and the
reading should be finished by the time the audit asks for it. ``add_documents``
extracts the text at upload; the session names the ids it was given and
``take_documents`` hands the text over.

In-process, with the prefetch's TTL. A miss on another replica means the run
drafts from the site alone: thinner, never wrong. Only the text is kept, never
the file, and only until the entry expires.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from agents.audit.prefetch import TTL_SECONDS
from service.documents import MAX_DOCUMENTS, DocumentError, Extracted, extract_document

#: Text is at most ``service.documents.MAX_CHARS`` per entry, so this bounds the
#: store near 8 MB however many guests are minted. The route's limiter comes first.
MAX_ENTRIES = 200


@dataclass
class StoredDocument:
    doc_id: str
    owner_id: str
    document: Extracted
    created_at: float = field(default_factory=time.monotonic)

    @property
    def expired(self) -> bool:
        return time.monotonic() - self.created_at > TTL_SECONDS

    def summary(self) -> dict[str, Any]:
        """What the file's tile shows: never the text itself."""
        doc = self.document
        return {
            "id": self.doc_id,
            "name": doc.name,
            "kind": doc.kind.value,
            "pages": doc.pages,
            "chars": len(doc.text),
            "truncated": doc.truncated,
        }


_entries: dict[str, StoredDocument] = {}


def _prune() -> None:
    for key in [k for k, v in _entries.items() if v.expired]:
        _entries.pop(key, None)
    if len(_entries) > MAX_ENTRIES:
        oldest = sorted(_entries.values(), key=lambda e: e.created_at)[: len(_entries) - MAX_ENTRIES]
        for entry in oldest:
            _entries.pop(entry.doc_id, None)


async def add_documents(files: list[tuple[str, bytes]], *, owner_id: str) -> list[dict[str, Any]]:
    """Read each ``(name, bytes)`` and keep its text. One result per file, in
    order: a summary with an ``id``, or ``{"name", "error"}`` with the reason.
    A file that cannot be read never fails the others."""
    _prune()
    results: list[dict[str, Any]] = []
    for name, data in files:
        try:
            # pypdf is pure Python and a 50-page deck is real CPU; off the loop.
            document = await asyncio.to_thread(extract_document, name, data)
        except DocumentError as exc:
            results.append({"name": name, "error": exc.reason.value})
            continue
        entry = StoredDocument(doc_id=secrets.token_urlsafe(16), owner_id=owner_id, document=document)
        _entries[entry.doc_id] = entry
        results.append(entry.summary())
    return results


def take_documents(doc_ids: list[str] | None, *, owner_id: str | None) -> list[Extracted]:
    """The live documents among ``doc_ids`` that belong to ``owner_id``, in the
    order given. Unknown, expired and someone else's ids are dropped alike."""
    found: list[Extracted] = []
    for doc_id in (doc_ids or [])[:MAX_DOCUMENTS]:
        entry = _entries.get(doc_id or "")
        if entry is None or entry.expired or owner_id is None or entry.owner_id != owner_id:
            continue
        found.append(entry.document)
    return found
