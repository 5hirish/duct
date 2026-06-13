"""Conversation persistence for streaming agents — chat history + resume.

The runner already calls ``emit()`` for every SSE event, so we persist by
*wrapping* the emit callback (`ConversationRecorder.wrap_emit`) rather than
scattering DB writes through the runner. One assistant + one thinking event is
written per turn (flushed on MESSAGE_STOP), never per streamed chunk.

On resume we don't replay the SDK transcript (it's deleted on cleanup); instead
we rebuild a fresh SDK session re-primed from the DB — `build_reprime_block`
produces the `<conversation_summary>` + `<recent_turns>` block, and
`summarize_conversation` folds the tail into a running summary so reopened
chats start lean (the compaction step).

Design: see models/content/conversation.py. The artifact link is polymorphic
(`ARTIFACT_REGISTRY` maps (agent_type, artifact_type) → table).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlmodel import Session, select

from agents.core.events import AgentEvent
from db.session import get_session as db_session
from models.content import AgentConversation, AgentEvent as AgentEventRow, ContentPlan, ContentPost

logger = logging.getLogger(__name__)

# (agent_type, artifact_type) → the SQLModel table the polymorphic artifact_id
# points at. Lets a future agent produce multiple artifact types without a
# schema change — add a row here, no migration.
ARTIFACT_REGISTRY: dict[tuple[str, str], type] = {
    ("tiktok_studio", "post"): ContentPost,
    ("tiktok_studio", "plan"): ContentPlan,
}

# How many new events since the last summary before we (re)summarize on resume.
_SUMMARY_THRESHOLD = 8
# How many raw recent turns to inline verbatim in the re-prime block.
_RECENT_TURNS = 6
_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_SUMMARY_TIMEOUT = 45.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Low-level DB helpers (sync — callers pass a Session)
# ---------------------------------------------------------------------------

def _next_seq(db: Session, conversation_id: UUID) -> int:
    """Atomically allocate the next per-conversation seq (no MAX+1 race) and
    bump last_active_at. Returns the new seq."""
    row = db.execute(
        update(AgentConversation)
        .where(AgentConversation.id == conversation_id)
        .values(last_seq=AgentConversation.last_seq + 1, last_active_at=_utcnow())
        .returning(AgentConversation.last_seq)
    ).first()
    db.commit()
    return int(row[0]) if row else 0


def append_event(db: Session, conversation_id: UUID, kind: str, data: dict) -> None:
    """Append one event to the conversation log."""
    seq = _next_seq(db, conversation_id)
    db.add(AgentEventRow(conversation_id=conversation_id, seq=seq, kind=kind, data=data))
    db.commit()


def load_events(db: Session, conversation_id: UUID, *, after_seq: int = 0) -> list[AgentEventRow]:
    return list(
        db.exec(
            select(AgentEventRow)
            .where(AgentEventRow.conversation_id == conversation_id)
            .where(AgentEventRow.seq > after_seq)
            .order_by(AgentEventRow.seq)
        )
    )


def get_conversation(db: Session, conversation_id: UUID) -> AgentConversation | None:
    return db.get(AgentConversation, conversation_id)


def list_conversations(
    db: Session,
    *,
    agent_type: str,
    project_id: UUID | None = None,
    artifact_type: str | None = None,
    artifact_id: UUID | None = None,
    include_archived: bool = False,
) -> list[AgentConversation]:
    stmt = select(AgentConversation).where(AgentConversation.agent_type == agent_type)
    if project_id is not None:
        stmt = stmt.where(AgentConversation.project_id == project_id)
    if artifact_type is not None:
        stmt = stmt.where(AgentConversation.artifact_type == artifact_type)
    if artifact_id is not None:
        stmt = stmt.where(AgentConversation.artifact_id == artifact_id)
    if not include_archived:
        stmt = stmt.where(AgentConversation.status == "active")
    stmt = stmt.order_by(AgentConversation.last_active_at.desc())
    return list(db.exec(stmt))


def find_active_conversation(
    db: Session, *, artifact_type: str, artifact_id: UUID
) -> AgentConversation | None:
    return db.exec(
        select(AgentConversation)
        .where(AgentConversation.artifact_type == artifact_type)
        .where(AgentConversation.artifact_id == artifact_id)
        .where(AgentConversation.status == "active")
    ).first()


def archive_conversation(db: Session, conversation_id: UUID) -> None:
    db.execute(
        update(AgentConversation)
        .where(AgentConversation.id == conversation_id)
        .values(status="archived", last_active_at=_utcnow())
    )
    db.commit()


def link_artifact(
    db: Session, conversation_id: UUID, artifact_type: str, artifact_id: UUID
) -> None:
    """Bind a conversation to the artifact it produced (e.g. once a draft post
    gets a post_id) so 'click post → resume' can find it. Idempotent."""
    db.execute(
        update(AgentConversation)
        .where(AgentConversation.id == conversation_id)
        .values(artifact_type=artifact_type, artifact_id=artifact_id, last_active_at=_utcnow())
    )
    db.commit()


def resolve_or_create_conversation(
    db: Session,
    *,
    agent_type: str,
    project_id: UUID,
    mode: str,
    artifact_type: str | None = None,
    artifact_id: UUID | None = None,
    conversation_id: UUID | None = None,
    resume: bool = False,
    start_fresh: bool = False,
) -> tuple[AgentConversation, bool]:
    """Resolve the conversation for a session create. Returns (conversation,
    is_resume). is_resume=True means there is prior history to re-prime from.

    - explicit conversation_id → load it (resume if it has events)
    - resume + artifact → find the active conversation for that artifact
    - start_fresh → archive any active conversation for the artifact, create new
    - otherwise → create a fresh active conversation
    """
    if start_fresh and artifact_type and artifact_id:
        existing = find_active_conversation(db, artifact_type=artifact_type, artifact_id=artifact_id)
        if existing:
            archive_conversation(db, existing.id)

    if not start_fresh:
        conv: AgentConversation | None = None
        if conversation_id is not None:
            conv = get_conversation(db, conversation_id)
        elif resume and artifact_type and artifact_id:
            conv = find_active_conversation(db, artifact_type=artifact_type, artifact_id=artifact_id)
        if conv is not None:
            return conv, conv.last_seq > 0

    conv = AgentConversation(
        agent_type=agent_type,
        project_id=project_id,
        mode=mode,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv, False


# ---------------------------------------------------------------------------
# Recorder — wraps emit to persist the conversation
# ---------------------------------------------------------------------------

class ConversationRecorder:
    """Persists a conversation by wrapping the runner's emit callback.

    Buffers streamed assistant/thinking text and flushes one event of each per
    turn on MESSAGE_STOP. DB writes run in a thread so they never block the
    streaming event loop, and a failed write never breaks the SSE stream.
    """

    def __init__(self, conversation_id: UUID) -> None:
        self.conversation_id = conversation_id
        self._assistant_buf: list[str] = []
        self._thinking_buf: list[str] = []

    def wrap_emit(self, emit_fn):
        async def _emit(body: dict) -> None:
            await emit_fn(body)  # SSE first — streaming must never wait on a DB write
            try:
                await self._persist(body)
            except Exception:
                logger.warning(
                    "persistence: failed to record event for conversation %s",
                    self.conversation_id, exc_info=True,
                )
        return _emit

    async def _persist(self, body: dict) -> None:
        event = body.get("event")
        if event == AgentEvent.AGENT_MESSAGE_CHUNK:
            self._assistant_buf.append(body.get("text", ""))
        elif event == AgentEvent.THINKING_CHUNK:
            self._thinking_buf.append(body.get("text", ""))
        elif event == AgentEvent.MESSAGE_STOP:
            await self._flush_turn()
        elif event == AgentEvent.QUESTIONS_REQUIRED:
            await self._append("question", {"questions": body.get("questions", [])})

    async def _flush_turn(self) -> None:
        thinking = "".join(self._thinking_buf).strip()
        assistant = "".join(self._assistant_buf).strip()
        self._thinking_buf.clear()
        self._assistant_buf.clear()
        if thinking:
            await self._append("thinking", {"text": thinking})
        if assistant:
            await self._append("assistant", {"text": assistant})

    async def record_user(self, content: Any) -> None:
        await self._append("user", {"content": content})

    async def record_answer(self, answers: dict) -> None:
        await self._append("answer", {"answers": answers})

    async def _append(self, kind: str, data: dict) -> None:
        await asyncio.to_thread(self._append_sync, kind, data)

    def _append_sync(self, kind: str, data: dict) -> None:
        with next(db_session()) as db:
            append_event(db, self.conversation_id, kind, data)


# ---------------------------------------------------------------------------
# Re-prime + compaction
# ---------------------------------------------------------------------------

def _event_text(ev: AgentEventRow) -> str:
    """Human-readable one-liner for a stored event, used in <recent_turns>."""
    if ev.kind == "user":
        c = ev.data.get("content", "")
        return c if isinstance(c, str) else " ".join(
            b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"
        )
    if ev.kind in ("assistant", "thinking"):
        return ev.data.get("text", "")
    if ev.kind == "question":
        qs = ev.data.get("questions", [])
        return "asked: " + "; ".join(q.get("question", "") for q in qs if isinstance(q, dict))
    if ev.kind == "answer":
        return "answered: " + "; ".join(f"{k}={v}" for k, v in ev.data.get("answers", {}).items())
    return ev.data.get("text", "")


def build_reprime_block(conversation: AgentConversation, recent_events: list[AgentEventRow]) -> str:
    """Build the resume context block prepended to the initial prompt on resume.

    summary covers events up to summary_through_seq; recent_events are the raw
    turns after it. thinking is dropped from recent turns (noisy, not needed for
    continuity)."""
    parts: list[str] = []
    if conversation.summary:
        parts.append(f"<conversation_summary>\n{conversation.summary}\n</conversation_summary>")
    turns = [e for e in recent_events if e.kind in ("user", "assistant", "question", "answer")]
    turns = turns[-(_RECENT_TURNS * 2):]
    if turns:
        lines = [f"{e.kind}: {_event_text(e)}".strip() for e in turns]
        parts.append("<recent_turns>\n" + "\n".join(lines) + "\n</recent_turns>")
    return ("\n".join(parts) + "\n\n") if parts else ""


async def summarize_conversation(
    conversation: AgentConversation, new_events: list[AgentEventRow], api_key: str
) -> str:
    """Fold the prior summary + new turns into a fresh running summary (Haiku).

    Returns the new summary text, or the prior summary on any failure — never
    raises. Reuses the lightweight query() pattern from enrichment.py.
    """
    if not api_key:
        return conversation.summary
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    except ImportError:
        return conversation.summary

    transcript = "\n".join(f"{e.kind}: {_event_text(e)}" for e in new_events if _event_text(e))
    if not transcript.strip():
        return conversation.summary

    prompt = (
        "You maintain a running summary of an ongoing chat between a user and a "
        "content-creation agent working on a social post/plan. Update the summary "
        "so a fresh agent could resume seamlessly: keep decisions, the user's "
        "preferences/constraints, and open threads; drop pleasantries.\n\n"
        f"PRIOR SUMMARY:\n{conversation.summary or '(none)'}\n\n"
        f"NEW TURNS:\n{transcript}\n\n"
        "Return ONLY the updated summary (a few tight paragraphs, no preamble)."
    )
    options = ClaudeAgentOptions(
        model=_HAIKU_MODEL,
        permission_mode="bypassPermissions",
        max_turns=1,
        env={"ANTHROPIC_API_KEY": api_key},
        setting_sources=[],
    )

    async def _run() -> str | None:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                return (getattr(message, "result", "") or "").strip() or None
        return None

    try:
        result = await asyncio.wait_for(_run(), timeout=_SUMMARY_TIMEOUT)
        return result or conversation.summary
    except Exception as exc:
        logger.warning("persistence: summarize failed (%s); keeping prior summary", exc)
        return conversation.summary


def should_summarize(conversation: AgentConversation) -> bool:
    return (conversation.last_seq - conversation.summary_through_seq) > _SUMMARY_THRESHOLD


def save_summary(db: Session, conversation_id: UUID, summary: str, through_seq: int) -> None:
    db.execute(
        update(AgentConversation)
        .where(AgentConversation.id == conversation_id)
        .values(summary=summary, summary_through_seq=through_seq)
    )
    db.commit()


def build_working_artifact_xml(mode: str, plan_id: UUID | None, post_id: UUID | None) -> str:
    """Serialize the session's current persisted plan/post as an XML context
    block — the same shape routes.agents._content_context_xml injects on chat
    turns, reused here so the resumed agent sees the live artifact on turn 1.

    slides_html is excluded from posts (large + derived from `slides`)."""
    try:
        with next(db_session()) as db:
            if mode == "plan_month" and plan_id is not None:
                plan = db.get(ContentPlan, plan_id)
                if plan is None:
                    return ""
                payload = {
                    "id": str(plan.id),
                    "name": plan.name,
                    "start_date": plan.start_date,
                    "character": plan.character,
                    "days": plan.days,
                }
                return f"<working_plan id='{plan.id}'>\n{json.dumps(payload, default=str)}\n</working_plan>\n\n"
            if mode == "draft_post" and post_id is not None:
                post = db.get(ContentPost, post_id)
                if post is None:
                    return ""
                payload = post.model_dump(exclude={"slides_html"})
                return f"<working_post id='{post.id}'>\n{json.dumps(payload, default=str)}\n</working_post>\n\n"
    except Exception:
        logger.warning("persistence: working-artifact serialization failed", exc_info=True)
    return ""


_RESUME_INSTRUCTION = (
    "You are RESUMING an existing conversation. Above is a summary and/or the "
    "recent turns of the prior discussion, and the current {artifact} in "
    "<working_{artifact}>. Pick up where you left off: greet the user in one short "
    "line that shows you remember the context, then wait for their next "
    "instruction. Do NOT re-run research or regenerate the {artifact} unless the "
    "user explicitly asks."
)


async def build_resume_initial_prompt(session: Any, api_key: str) -> str:
    """Build the turn-1 prompt for a resumed session: working artifact +
    re-prime block (summary + recent turns) + a resume instruction. Compacts
    (Haiku-summarizes) the tail first when the conversation has grown past the
    threshold, so reopened chats start lean. Never raises — returns whatever
    context it can assemble."""
    conversation_id = getattr(session, "conversation_id", None)
    mode = getattr(session, "mode", "draft_post")
    if conversation_id is None:
        return ""

    # Compaction: fold the tail into the running summary if it's grown enough.
    try:
        with next(db_session()) as db:
            conv = get_conversation(db, conversation_id)
            if conv is None:
                return ""
            if should_summarize(conv):
                new_events = load_events(db, conversation_id, after_seq=conv.summary_through_seq)
                new_summary = await summarize_conversation(conv, new_events, api_key)
                if new_summary and new_summary != conv.summary:
                    save_summary(db, conversation_id, new_summary, conv.last_seq)
                    conv = get_conversation(db, conversation_id)
            recent = load_events(db, conversation_id, after_seq=conv.summary_through_seq)
            reprime = build_reprime_block(conv, recent)
    except Exception:
        logger.warning("persistence: resume re-prime failed for %s", conversation_id, exc_info=True)
        return ""

    artifact_kind = "plan" if mode == "plan_month" else "post"
    artifact_xml = build_working_artifact_xml(
        mode, getattr(session, "plan_id", None), getattr(session, "post_id", None)
    )
    instruction = _RESUME_INSTRUCTION.format(artifact=artifact_kind)
    return f"{artifact_xml}{reprime}{instruction}"
