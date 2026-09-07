"""The ``<duct_artifact>`` stream parser.

Harness-neutral by construction: a tag state machine driven by plain text
deltas, which is why it outlived the Claude Agent SDK pump it used to sit
beside (``pump_stream_event``, removed with V3). ``stream_agent`` in
``agents/core/lc.py`` feeds it from LangChain chunks; it forwards prose versus
in-tag payload to agent-specific callbacks, and what those do with the payload
differs — audit builds HTML, content parses JSON.

The tag is ``<duct_artifact>``. It used to be ``<duct_report>``, which was
wrong the moment content started emitting plans and post drafts through it —
the parser still *accepts* the legacy tag so recorded conversations replay,
but nothing emits it.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from agents.core.prompts import (
    DUCT_ARTIFACT_CLOSE,
    DUCT_ARTIFACT_OPEN,
    LEGACY_ARTIFACT_CLOSE,
    LEGACY_ARTIFACT_OPEN,
)

logger = logging.getLogger(__name__)

TextCallback = Callable[[str], Awaitable[None]]
CloseCallback = Callable[[str, str], Awaitable[None]]  # (raw_payload, turn_text)
OpenCallback = Callable[[], Awaitable[None]]

_TAG_PAIRS: tuple[tuple[str, str], ...] = (
    (DUCT_ARTIFACT_OPEN, DUCT_ARTIFACT_CLOSE),
    (LEGACY_ARTIFACT_OPEN, LEGACY_ARTIFACT_CLOSE),
)

class DuctArtifactStreamParser:
    """Feed streamed text deltas in; callbacks fire as tags open, stream, close.

    Callbacks (all async):
      on_text(text)            — prose outside the tag (emit AGENT_MESSAGE_CHUNK).
      on_artifact_chunk(text)  — a token inside the tag (emit ARTIFACT_CHUNK).
      on_artifact_close(raw, turn_text) — the tag closed; ``raw`` is the payload
                                 between the tags, ``turn_text`` the accumulated
                                 prose before it (audit uses it as exec summary).
      on_open()                — optional; the tag just opened (for logging).

    Recognises ``<duct_artifact>`` and the legacy ``<duct_report>``. Whichever
    opens first decides which close tag ends the payload, so a stream can never
    be terminated by the other convention's closing tag.
    """

    def __init__(
        self,
        *,
        on_text: TextCallback,
        on_artifact_chunk: TextCallback,
        on_artifact_close: CloseCallback,
        on_open: OpenCallback | None = None,
        log_prefix: str = "agent",
        open_tag: str | None = None,
        close_tag: str | None = None,
    ) -> None:
        self._on_text = on_text
        self._on_artifact_chunk = on_artifact_chunk
        self._on_artifact_close = on_artifact_close
        self._on_open = on_open
        self._log_prefix = log_prefix

        # An explicit pair (used by tests and by any agent with its own tag)
        # replaces the defaults entirely; otherwise both conventions are live.
        if open_tag is not None and close_tag is not None:
            self._pairs = ((open_tag, close_tag),)
        else:
            self._pairs = _TAG_PAIRS
        # Hold back enough trailing characters that the longest open tag can
        # never be missed when split across chunk boundaries.
        self._holdback_len = max(len(o) for o, _ in self._pairs) - 1

        self.in_tag = False
        self._close = ""        # close tag matching the open tag that fired
        self._buf = ""          # accumulated payload bytes inside the tag
        self._holdback = ""     # tail held back in case it's a split open tag
        self.turn_text: list[str] = []
        self.artifact_chunk_count = 0

    @property
    def report_chunk_count(self) -> int:
        """Deprecated alias for ``artifact_chunk_count``."""
        return self.artifact_chunk_count

    def _find_open(self, working: str) -> tuple[int, str, str]:
        """Earliest open tag in ``working`` → (index, open_tag, close_tag).

        Returns ``(-1, "", "")`` when no convention has opened yet. Earliest
        wins so that prose mentioning one tag cannot mask a real one later.
        """
        best = (-1, "", "")
        for open_tag, close_tag in self._pairs:
            idx = working.find(open_tag)
            if idx != -1 and (best[0] == -1 or idx < best[0]):
                best = (idx, open_tag, close_tag)
        return best

    async def feed(self, chunk: str) -> None:
        """Process one streamed text delta."""
        if self.in_tag:
            if self._close in chunk:
                # Close tag fully contained in this chunk.
                safe, _, remainder = chunk.partition(self._close)
                if safe:
                    self.artifact_chunk_count += 1
                    self._buf += safe
                    await self._on_artifact_chunk(safe)
                await self._finish()
                if remainder:
                    await self.feed(remainder)
            else:
                # Accumulate; the close tag may be split across chunks.
                self._buf += chunk
                if self._close in self._buf:
                    raw, _, remainder = self._buf.partition(self._close)
                    self._buf = raw
                    await self._finish()
                    if remainder:
                        await self.feed(remainder)
                elif chunk:
                    self.artifact_chunk_count += 1
                    if self.artifact_chunk_count % 50 == 0:
                        logger.info(
                            "%s: %s streaming — %d chunks, ~%d chars buffered",
                            self._log_prefix, self._close, self.artifact_chunk_count, len(self._buf),
                        )
                    await self._on_artifact_chunk(chunk)
            return

        working = self._holdback + chunk
        self._holdback = ""

        idx, open_tag, close_tag = self._find_open(working)
        if idx != -1:
            before = working[:idx]
            after = working[idx + len(open_tag):]
            if before:
                await self._on_text(before)
                self.turn_text.append(before)
            self.in_tag = True
            self._close = close_tag
            self._buf = ""
            if self._on_open is not None:
                await self._on_open()
            if after:
                await self.feed(after)
        else:
            # Hold back enough trailing chars that a split open tag isn't missed.
            if len(working) > self._holdback_len:
                safe = working[:-self._holdback_len]
                self._holdback = working[-self._holdback_len:]
                await self._on_text(safe)
                self.turn_text.append(safe)
            else:
                self._holdback = working

    async def flush(self) -> None:
        """Flush any held-back trailing prose (call at end of a turn)."""
        if self._holdback:
            await self._on_text(self._holdback)
            self.turn_text.append(self._holdback)
            self._holdback = ""

    async def _finish(self) -> None:
        self.in_tag = False
        raw = self._buf
        self._buf = ""
        await self._on_artifact_close(raw, "".join(self.turn_text).strip())


# Deprecated alias — import DuctArtifactStreamParser instead.
DuctReportStreamParser = DuctArtifactStreamParser
