"""Shared streaming helpers.

Two pieces that sit on opposite sides of the harness boundary (see
``agents/core/ports``):

  * ``pump_stream_event`` — **harness adapter, Claude Agent SDK.** Decodes one
    SDK message (thinking/text deltas, token usage, ``message_stop``,
    ``ResultMessage``, ``TodoWrite``) and dispatches to callbacks. The audit v3
    runner drives discrete turns around it and keeps its own loop and state;
    this owns only the per-message decode. The LangChain equivalent is
    ``stream_agent`` in ``agents/core/lc.py``.

  * ``DuctArtifactStreamParser`` — **harness-neutral.** The ``<duct_artifact>``
    tag state machine, driven by plain text deltas from any harness. The pump's
    ``on_text`` feeds it on v3; ``stream_agent`` feeds it from LangChain chunks.
    It forwards prose vs in-tag payload to agent-specific callbacks (audit
    builds HTML, content parses JSON).

The tag is ``<duct_artifact>``. It used to be ``<duct_report>``, which was
wrong the moment content started emitting plans and post drafts through it —
the parser still *accepts* the legacy tag so recorded conversations replay,
but nothing emits it.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from agents.core.prompts import (
    DUCT_ARTIFACT_CLOSE,
    DUCT_ARTIFACT_OPEN,
    LEGACY_ARTIFACT_CLOSE,
    LEGACY_ARTIFACT_OPEN,
)
from agents.models import AgentTool

logger = logging.getLogger(__name__)

# The TodoWrite tool's canonical name, sourced from the single AgentTool enum
# (StrEnum → plain str for the by-name comparisons below). agents.models is a
# pure-enum leaf module, so importing it keeps core import-light.
_TODO_WRITE = AgentTool.TODO_WRITE.value


def is_todo_write(block: Any) -> bool:
    """True if an assistant content block is a ``TodoWrite`` tool call."""
    return (
        getattr(block, "type", None) == "tool_use"
        and getattr(block, "name", None) == _TODO_WRITE
        and isinstance(getattr(block, "input", None), dict)
    )


async def pump_stream_event(
    msg: Any,
    *,
    on_text: Callable[[str], Awaitable[None]],
    on_thinking: Callable[[str], Awaitable[None]] | None = None,
    on_message_stop: Callable[[], Awaitable[None]] | None = None,
    on_usage: Callable[[dict, str], None] | None = None,
    on_result: Callable[[Any], Awaitable[None]] | None = None,
    on_todo: Callable[[list], Awaitable[None]] | None = None,
    on_tool_use: Callable[[str], None] | None = None,
) -> None:
    """Decode one SDK message and dispatch to the provided callbacks.

    The caller owns the parser: ``on_text`` receives each raw text delta (do
    first-token timing there, then ``await parser.feed(text)``); ``on_message_stop``
    fires at a turn boundary (flush the parser + any agent-specific work there).
    ``on_usage(usage, phase)`` is called with ``phase`` in ``{"start", "delta"}``.
    Unhandled message types are ignored. Only ``on_text`` is required.
    """
    from claude_agent_sdk.types import ResultMessage, StreamEvent

    if isinstance(msg, StreamEvent):
        ev = msg.event
        ev_type = ev.get("type")

        if ev_type == "content_block_delta":
            delta = ev.get("delta", {})
            delta_type = delta.get("type")
            if delta_type == "thinking_delta":
                text = delta.get("thinking", "")
                if text and on_thinking:
                    await on_thinking(text)
            elif delta_type == "text_delta":
                text = delta.get("text", "")
                if text:
                    await on_text(text)
        elif ev_type == "content_block_start":
            if on_tool_use:
                block = ev.get("content_block", {})
                if block.get("type") == "tool_use":
                    on_tool_use(block.get("name", "?"))
        elif ev_type == "message_start":
            if on_usage:
                usage = ev.get("message", {}).get("usage", {})
                if usage:
                    on_usage(usage, "start")
        elif ev_type == "message_delta":
            if on_usage:
                usage = ev.get("usage", {})
                if usage:
                    on_usage(usage, "delta")
        elif ev_type == "message_stop":
            if on_message_stop:
                await on_message_stop()
        return

    if isinstance(msg, ResultMessage):
        if on_result:
            await on_result(msg)
        return

    if on_todo and hasattr(msg, "content") and msg.content:
        for block in msg.content:
            if is_todo_write(block):
                await on_todo(block.input.get("todos", []))


# ---------------------------------------------------------------------------
# <duct_artifact> tag parser (harness-neutral)
# ---------------------------------------------------------------------------

TextCallback = Callable[[str], Awaitable[None]]
CloseCallback = Callable[[str, str], Awaitable[None]]  # (raw_payload, turn_text)
OpenCallback = Callable[[], Awaitable[None]]

# (open, close) pairs the parser recognises, canonical first. Legacy is accepted
# on the way in so a conversation recorded before the rename — or a turn already
# in flight against a cached system prompt — still yields its payload.
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
