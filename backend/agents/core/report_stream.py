"""Streaming parser for the ``<duct_report>`` convention, shared by Claude-SDK agents.

Both audit and content streamed model output token-by-token, forwarding prose as
AGENT_MESSAGE_CHUNK and the bytes inside ``<duct_report>…</duct_report>`` as
REPORT_CHUNK, then handing the closed payload to an agent-specific handler
(audit builds an HTML AuditReport; content parses JSON and branches on ``type``).
The tag state machine — holdback for open tags split across chunks, close tags
split across chunks, and recursion on the remainder — was duplicated verbatim.
It now lives here once; agents supply only the three callbacks.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from agents.core.prompts import DUCT_REPORT_CLOSE, DUCT_REPORT_OPEN

logger = logging.getLogger(__name__)

TextCallback = Callable[[str], Awaitable[None]]
CloseCallback = Callable[[str, str], Awaitable[None]]  # (raw_payload, turn_text)
OpenCallback = Callable[[], Awaitable[None]]


class DuctReportStreamParser:
    """Feed streamed text deltas in; callbacks fire as tags open, stream, close.

    Callbacks (all async):
      on_text(text)          — prose outside the tag (emit AGENT_MESSAGE_CHUNK).
      on_report_chunk(text)  — a token inside the tag (emit REPORT_CHUNK).
      on_report_close(raw, turn_text) — the tag closed; ``raw`` is the payload
                               between the tags, ``turn_text`` the accumulated
                               prose before it (audit uses it as exec summary).
      on_open()              — optional; the tag just opened (for logging).
    """

    def __init__(
        self,
        *,
        on_text: TextCallback,
        on_report_chunk: TextCallback,
        on_report_close: CloseCallback,
        on_open: OpenCallback | None = None,
        log_prefix: str = "agent",
        open_tag: str = DUCT_REPORT_OPEN,
        close_tag: str = DUCT_REPORT_CLOSE,
    ) -> None:
        self._on_text = on_text
        self._on_report_chunk = on_report_chunk
        self._on_report_close = on_report_close
        self._on_open = on_open
        self._log_prefix = log_prefix
        self._open = open_tag
        self._close = close_tag

        self.in_tag = False
        self._buf = ""          # accumulated payload bytes inside the tag
        self._holdback = ""     # tail held back in case it's a split open tag
        self.turn_text: list[str] = []
        self.report_chunk_count = 0

    async def feed(self, chunk: str) -> None:
        """Process one streamed text delta."""
        if self.in_tag:
            if self._close in chunk:
                # Close tag fully contained in this chunk.
                safe, _, remainder = chunk.partition(self._close)
                if safe:
                    self.report_chunk_count += 1
                    self._buf += safe
                    await self._on_report_chunk(safe)
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
                    self.report_chunk_count += 1
                    if self.report_chunk_count % 50 == 0:
                        logger.info(
                            "%s: <duct_report> streaming — %d chunks, ~%d chars buffered",
                            self._log_prefix, self.report_chunk_count, len(self._buf),
                        )
                    await self._on_report_chunk(chunk)
            return

        working = self._holdback + chunk
        self._holdback = ""

        if self._open in working:
            before, _, after = working.partition(self._open)
            if before:
                await self._on_text(before)
                self.turn_text.append(before)
            self.in_tag = True
            self._buf = ""
            if self._on_open is not None:
                await self._on_open()
            if after:
                await self.feed(after)
        else:
            # Hold back enough trailing chars that a split open tag isn't missed.
            holdback_len = len(self._open) - 1
            if len(working) > holdback_len:
                safe = working[:-holdback_len]
                self._holdback = working[-holdback_len:]
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
        await self._on_report_close(raw, "".join(self.turn_text).strip())
