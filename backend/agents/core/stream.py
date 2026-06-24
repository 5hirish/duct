"""Shared streaming helpers for Claude-SDK agents.

Two cohesive pieces both runners share:

  * ``pump_stream_event`` — decode one SDK message (thinking/text deltas, token
    usage, ``message_stop``, ``ResultMessage``, ``TodoWrite``) and dispatch to
    callbacks. The *outer* loop differs per agent (audit drives discrete turns;
    content runs one streaming-input session with a startup watchdog), so this
    owns only the per-message decode; the caller keeps its loop and state.

  * ``DuctArtifactStreamParser`` — the ``<duct_artifact>`` tag state machine. The
    pump's ``on_text`` feeds it; it forwards prose vs in-tag payload to
    agent-specific callbacks (audit builds HTML, content parses JSON). The
    ``<duct_artifact>`` convention is shared by every Duct agent — not audit-
    specific — so it belongs here in core.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from agents.core.prompts import DUCT_ARTIFACT_CLOSE, DUCT_ARTIFACT_OPEN
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
# <duct_artifact> tag parser (shared convention; not agent-specific)
# ---------------------------------------------------------------------------

TextCallback = Callable[[str], Awaitable[None]]
CloseCallback = Callable[[str, str], Awaitable[None]]  # (raw_payload, turn_text)
OpenCallback = Callable[[], Awaitable[None]]


class DuctArtifactStreamParser:
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
        open_tag: str = DUCT_ARTIFACT_OPEN,
        close_tag: str = DUCT_ARTIFACT_CLOSE,
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
                            "%s: <duct_artifact> streaming — %d chunks, ~%d chars buffered",
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
