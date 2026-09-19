#!/usr/bin/env python3
"""Pull one agent session out of the database into a folder you can review.

An agent's answer is a function of six things the transcript UI shows one of:
the sentence typed, the composed opening turn (business context, profile,
memory digest, connector list), the system prompt in force, every tool call
with its full input and output, the artifact versions it wrote, and what it
cost. The `session-audit` skill (`.agents/skills/session-audit/`) reviews a
session against all six and then attempts the same task independently, on
the same data, to compare. This script is the pull. It reads, never writes.

    poetry run python scripts/session_bundle.py list [--agent insights] [--limit 20]
    poetry run python scripts/session_bundle.py <conversation-id> --out <dir>
    poetry run python scripts/session_bundle.py <conversation-id> --out <dir> --prompt-check

Reads DATABASE_URL the way the server does (``backend/.env`` then
``backend/.env.local``; ``DUCT_ENV_FILE`` overrides), so run it from
``backend/``. Nothing from the environment is ever printed. Every string
that lands in the bundle goes through ``redact_secrets`` first, because a
tool output can quote a provider's error page and a memory can quote a
person, and the bundle is going to be read by an agent that was not the one
trusted with the session.

The bundle is customer data. It belongs in the private audit home the skill
names, never in this repository — ``.audits/`` here is gitignored for the
case where the private checkout is not beside this one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from agents.content.persistence import load_events  # noqa: E402
from agents.core.events import EventKind  # noqa: E402
from db.session import get_engine  # noqa: E402
from models.artifact import Artifact  # noqa: E402
from models.content.conversation import AgentConversation  # noqa: E402
from models.execution import ExecutionChangeSet  # noqa: E402
from models.memory import ProjectMemory  # noqa: E402
from models.project import Project  # noqa: E402
from models.settings import UserProfile  # noqa: E402
from models.usage import ModelUsage  # noqa: E402
from service.artifact_store import artifact_text_content, extension_for  # noqa: E402
from service.memory import redact_secrets  # noqa: E402

# Where the desktop app's sidecar keeps local uploads. A session run on the
# desktop wrote its artifact there, not under this checkout's uploads_dir,
# so the store's read comes back empty on the machine that ran it. Probed
# by relative key when the store has nothing; --uploads-dir names another.
DESKTOP_UPLOAD_DIRS = tuple(
    Path.home() / "Library" / "Application Support" / app / "uploads"
    for app in ("ai.getduct.desktop", "ai.getduct.desktop.dev")
)

# Project columns that are context, not bookkeeping: what the agent could
# have been told about the business. Listed rather than dumped so a new
# operational column never rides into a bundle by accident.
PROJECT_CONTEXT_FIELDS = (
    "name", "url", "company_name", "industry", "business_model", "tagline",
    "pitch", "description", "targets", "audience", "competition",
    "brand_channels", "autonomy_level", "memory_paused",
)
PROFILE_FIELDS = ("display_name", "role", "writing_preset", "communication_language", "timezone", "notes")
MEMORY_FIELDS = (
    "id", "scope", "kind", "title", "body", "entity_key", "attribute", "period",
    "value", "observed_at", "valid_from", "valid_to", "source_type", "source_refs",
    "agent_type", "conversation_id", "confidence", "importance", "status",
    "pinned", "recall_count", "last_recalled_at",
)
ARTIFACT_FIELDS = (
    "id", "group_id", "version", "slug", "agent_type", "kind", "content_type",
    "title", "filename", "size_bytes", "summary", "created_at",
)
CHANGE_SET_FIELDS = ("id", "title", "status", "connector_type", "account_id", "created_at")
USAGE_FIELDS = (
    "provider", "model", "tier", "scope", "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_creation_tokens", "cost_micros", "created_at",
)
# How much of a tool payload the transcript shows inline; the whole thing
# is in tools/. The transcript is for reading the run, not the data.
TRANSCRIPT_PAYLOAD_CHARS = 400
ACTIVE_MEMORY_LIMIT = 200


def _plain(value: Any) -> Any:
    """JSON-safe, with dates and UUIDs as strings."""
    return json.loads(json.dumps(value, default=str))


def _row(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: _plain(getattr(obj, f, None)) for f in fields}


def _short(value: Any) -> str:
    return str(value).replace("-", "")[:8]


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 - not in a checkout, or no git
        return ""


def _tool_output_text(output: Any) -> str:
    return output if isinstance(output, str) else json.dumps(output, indent=2, default=str)


def artifact_content(row: Any, extra_dirs: tuple[Path, ...] = ()) -> tuple[str, str]:
    """The artifact's text and where it came from: the store, a desktop
    uploads directory, or nowhere ('' with 'missing')."""
    text = artifact_text_content(row)
    if text:
        return text, "store"
    key = (row.storage_key or "").lstrip("/")
    if key:
        for base in (*extra_dirs, *DESKTOP_UPLOAD_DIRS):
            path = base / key
            if path.is_file():
                return path.read_text(encoding="utf-8", errors="replace"), str(base)
    return "", "missing"


# ---------------------------------------------------------------------------
# Pull
# ---------------------------------------------------------------------------

def list_conversations(db: Session, *, agent_type: str, limit: int) -> list[dict[str, Any]]:
    stmt = select(AgentConversation).order_by(AgentConversation.last_active_at.desc()).limit(limit)
    if agent_type:
        stmt = stmt.where(AgentConversation.agent_type == agent_type)
    rows = []
    for conv in db.exec(stmt).all():
        project = db.get(Project, conv.project_id)
        versions = db.exec(
            select(Artifact).where(Artifact.conversation_id == conv.id)
        ).all()
        rows.append({
            "id": str(conv.id),
            "agent_type": conv.agent_type,
            "project": project.name if project else "",
            "title": conv.title or "",
            "run_status": conv.run_status,
            "events": conv.last_seq,
            "artifact_versions": len(versions),
            "last_active_at": _plain(conv.last_active_at),
        })
    return rows


def pull(db: Session, conversation_id: UUID, *, uploads_dirs: tuple[Path, ...] = ()) -> dict[str, Any]:
    conv = db.get(AgentConversation, conversation_id)
    if conv is None:
        raise SystemExit(f"no conversation {conversation_id}")
    project = db.get(Project, conv.project_id)
    profile = db.get(UserProfile, project.user_id) if project else None
    events = load_events(db, conv.id)
    artifacts = sorted(
        db.exec(select(Artifact).where(Artifact.conversation_id == conv.id)).all(),
        key=lambda a: (str(a.group_id), a.version),
    )
    written = db.exec(
        select(ProjectMemory).where(ProjectMemory.conversation_id == conv.id).order_by(ProjectMemory.recorded_at)
    ).all()
    active = db.exec(
        select(ProjectMemory)
        .where(ProjectMemory.project_id == conv.project_id)
        .where(ProjectMemory.status == "active")
        .order_by(ProjectMemory.importance.desc(), ProjectMemory.recorded_at.desc())
        .limit(ACTIVE_MEMORY_LIMIT)
    ).all()
    change_sets = db.exec(
        select(ExecutionChangeSet).where(ExecutionChangeSet.conversation_id == conv.id)
    ).all()
    usage = db.exec(
        select(ModelUsage).where(ModelUsage.conversation_id == conv.id).order_by(ModelUsage.created_at)
    ).all()

    return {
        "bundled_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "repo_sha": _git_sha(),
        "conversation": {
            "id": str(conv.id),
            "agent_type": conv.agent_type,
            "mode": conv.mode,
            "title": conv.title,
            "status": conv.status,
            "run_status": conv.run_status,
            "run_error": _plain(conv.run_error),
            "summary": conv.summary,
            "input_tokens": conv.input_tokens,
            "output_tokens": conv.output_tokens,
            "meta": _plain(conv.meta),
            "created_at": _plain(conv.created_at),
            "last_active_at": _plain(conv.last_active_at),
        },
        "project": ({"id": str(project.id), **_row(project, PROJECT_CONTEXT_FIELDS)} if project else None),
        "profile": (_row(profile, PROFILE_FIELDS) if profile else None),
        "events": [
            {"seq": e.seq, "kind": e.kind, "created_at": _plain(e.created_at), "data": _plain(e.data)}
            for e in events
        ],
        "artifacts": [
            {**_row(a, ARTIFACT_FIELDS), "storage_key": a.storage_key, "content": text, "content_from": source}
            for a in artifacts
            for text, source in [artifact_content(a, uploads_dirs)]
        ],
        "memories_written": [_row(m, MEMORY_FIELDS) for m in written],
        "memories_active": [_row(m, MEMORY_FIELDS) for m in active],
        "change_sets": [_row(c, CHANGE_SET_FIELDS) for c in change_sets],
        "usage": [_row(u, USAGE_FIELDS) for u in usage],
    }


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def pair_tools(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """tool_use and tool_result rows, joined on tool_use_id, in call order."""
    calls: dict[str, dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    for ev in events:
        data = ev.get("data") or {}
        if ev.get("kind") == EventKind.TOOL_USE:
            entry = {
                "seq": ev["seq"], "name": data.get("name", ""), "tool_use_id": data.get("tool_use_id", ""),
                "input": data.get("input"), "result": None, "is_error": False, "result_seq": None,
            }
            calls[entry["tool_use_id"]] = entry
            ordered.append(entry)
        elif ev.get("kind") == EventKind.TOOL_RESULT:
            entry = calls.get(data.get("tool_use_id", ""))
            if entry is None:
                entry = {
                    "seq": ev["seq"], "name": data.get("name", ""), "tool_use_id": data.get("tool_use_id", ""),
                    "input": None, "result": None, "is_error": False, "result_seq": None,
                }
                ordered.append(entry)
            # The recorder's field is `result`; the paired entry keeps that name
            # so a tools/ file reads like the row it came from.
            entry["result"] = data.get("result")
            entry["is_error"] = bool(data.get("is_error"))
            entry["result_seq"] = ev["seq"]
    return ordered


def usage_totals(usage: list[dict[str, Any]]) -> dict[str, Any]:
    keys = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")
    totals: dict[str, Any] = {k: sum(int(u.get(k) or 0) for u in usage) for k in keys}
    totals["cost_usd"] = round(sum(int(u.get("cost_micros") or 0) for u in usage) / 1_000_000, 4)
    totals["calls"] = len(usage)
    totals["models"] = sorted({f"{u.get('provider', '')}/{u.get('model', '')}" for u in usage})
    return totals


def render_transcript(bundle: dict[str, Any]) -> str:
    """The run as a document: context first, then turns, tool calls collapsed
    to a line each, artifacts named where their version landed."""
    conv = bundle["conversation"]
    out: list[str] = []
    out.append(f"# Session {conv['id']}")
    out.append("")
    out.append(
        f"**Agent:** {conv['agent_type']} · **Project:** {(bundle.get('project') or {}).get('name', '')} · "
        f"**Run status:** {conv['run_status']} · **Bundled:** {bundle['bundled_at']} · "
        f"**Repo at bundle time:** {bundle.get('repo_sha', '')[:12] or 'unknown'}"
    )
    totals = usage_totals(bundle.get("usage", []))
    out.append(
        f"**Usage:** {totals['calls']} model calls · {totals['input_tokens']:,} in / "
        f"{totals['output_tokens']:,} out · cache read {totals['cache_read_tokens']:,} · "
        f"${totals['cost_usd']} · {', '.join(totals['models']) or 'no usage rows'}"
    )
    out.append("")

    tools = pair_tools(bundle["events"])
    by_seq = {t["seq"]: t for t in tools}
    artifacts_by_created = list(bundle.get("artifacts", []))

    for ev in bundle["events"]:
        kind, data, seq = ev["kind"], ev.get("data") or {}, ev["seq"]
        if kind == EventKind.CONTEXT:
            out.append(f"## [{seq}] Context the model read")
            out.append("")
            out.append(
                f"provider `{data.get('provider', '')}` · model `{data.get('model', '')}` · "
                f"thinking `{data.get('thinking', '') or 'off'}` · resume `{data.get('resume')}` · "
                f"system prompt sha256 `{data.get('system_prompt_sha256', '')[:16]}…` "
                f"({data.get('system_prompt_chars', 0):,} chars)"
            )
            out.append("")
            blocks = data.get("blocks") or {}
            for name in ("business_context", "user_context", "memory", "data_sources"):
                text = str(blocks.get(name) or "")
                out.append(f"<details><summary>{name} ({len(text):,} chars)</summary>\n")
                out.append("```")
                out.append(text or "(empty)")
                out.append("```\n</details>")
                out.append("")
            out.append(
                f"artifact_format `{blocks.get('artifact_format', '')}` · autonomy `{blocks.get('autonomy', '')}` · "
                f"compress `{blocks.get('compress')}`"
            )
            out.append("")
        elif kind == EventKind.USER:
            content = data.get("content")
            text = content if isinstance(content, str) else json.dumps(content, default=str)
            out.append(f"## [{seq}] User\n\n{text}\n")
        elif kind == EventKind.THINKING:
            out.append(f"<details><summary>[{seq}] Thinking</summary>\n\n{data.get('text', '')}\n\n</details>\n")
        elif kind == EventKind.ASSISTANT:
            out.append(f"## [{seq}] Assistant\n\n{data.get('text', '')}\n")
        elif kind == EventKind.QUESTION:
            out.append(f"## [{seq}] Agent asked\n\n```json\n{json.dumps(data.get('questions'), indent=2)}\n```\n")
        elif kind == EventKind.ANSWER:
            out.append(f"## [{seq}] User answered\n\n```json\n{json.dumps(data.get('answers'), indent=2)}\n```\n")
        elif kind == EventKind.TOOL_USE:
            t = by_seq.get(seq) or {}
            arg = json.dumps(t.get("input"), default=str)
            outp = _tool_output_text(t.get("result"))
            verdict = "error" if t.get("is_error") else "ok"
            out.append(
                f"- [{seq}] **{t.get('name', '')}** {arg[:TRANSCRIPT_PAYLOAD_CHARS]} → {verdict}, "
                f"{len(outp):,} chars (tools/{seq:04d}-{t.get('name', '')}.json)"
            )
        elif kind == EventKind.TOOL_RESULT:
            continue
        elif kind == EventKind.FAILURE:
            out.append(f"## [{seq}] Failure\n\n```json\n{json.dumps(data, indent=2, default=str)}\n```\n")
        else:
            out.append(f"- [{seq}] {kind}: {json.dumps(data, default=str)[:TRANSCRIPT_PAYLOAD_CHARS]}")

    if artifacts_by_created:
        out.append("")
        out.append("## Artifacts")
        out.append("")
        for a in artifacts_by_created:
            out.append(
                f"- v{a['version']} **{a['title'] or a['slug']}** ({a['content_type']}, {a['size_bytes']:,} bytes, "
                f"{a['created_at']}) → artifacts/{a['slug'] or 'artifact'}-v{a['version']}.{extension_for(a['content_type'])}"
                + (" · **bytes missing**" if a.get("content_from") == "missing" else "")
            )
    written = bundle.get("memories_written", [])
    if written:
        out.append("")
        out.append("## Memories this session wrote")
        out.append("")
        for m in written:
            out.append(f"- [{m['kind']}] **{m['title']}** — {str(m['body'])[:TRANSCRIPT_PAYLOAD_CHARS]}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def write_bundle(bundle: dict[str, Any], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def put(rel: str, text: str) -> None:
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(redact_secrets(text), encoding="utf-8")
        written.append(path)

    put("bundle.json", json.dumps(bundle, indent=2, default=str))
    put("transcript.md", render_transcript(bundle))
    for t in pair_tools(bundle["events"]):
        put(
            f"tools/{t['seq']:04d}-{t['name'] or 'tool'}.json",
            json.dumps(
                {"name": t["name"], "input": t["input"], "is_error": t["is_error"], "result": t["result"]},
                indent=2,
                default=str,
            ),
        )
    for a in bundle.get("artifacts", []):
        put(f"artifacts/{a['slug'] or 'artifact'}-v{a['version']}.{extension_for(a['content_type'])}", a["content"] or "")
    return written


def prompt_check(bundle: dict[str, Any]) -> str:
    """Does the system prompt in force at the session match the code here now?

    A finding against a prompt that has since changed is a finding against
    history. The fingerprint in the CONTEXT row is compared with every shape
    this checkout can build for the agent, so the reviewer knows whether a
    proposal targets the prompt that produced the run."""
    ctx = next((e for e in bundle["events"] if e["kind"] == EventKind.CONTEXT), None)
    if ctx is None:
        return "prompt check: this session predates CONTEXT rows; the prompt in force is unknown."
    stored = (ctx.get("data") or {}).get("system_prompt_sha256", "")
    agent_type = bundle["conversation"]["agent_type"]
    if agent_type != "insights":
        return f"prompt check: no fingerprint builder for '{agent_type}' yet; stored sha {stored[:16]}…"
    from agents.insights.prompts.autonomous import (
        CAPABILITIES_PHASE_3,
        CAPABILITIES_UNATTENDED,
        build_insights_system_prompt,
    )

    shapes = {
        f"interactive, execute={ex}": hashlib.sha256(
            build_insights_system_prompt(capabilities=CAPABILITIES_PHASE_3, can_execute=ex).encode()
        ).hexdigest()
        for ex in (True, False)
    }
    shapes.update({
        f"unattended, execute={ex}": hashlib.sha256(
            build_insights_system_prompt(capabilities=CAPABILITIES_UNATTENDED, can_execute=ex).encode()
        ).hexdigest()
        for ex in (True, False)
    })
    match = [name for name, sha in shapes.items() if sha == stored]
    if match:
        return f"prompt check: the session ran on this checkout's prompt ({match[0]})."
    return (
        "prompt check: the system prompt has CHANGED since this session "
        f"(stored {stored[:16]}…, none of {len(shapes)} current shapes match). "
        "Read docs/engineering/agent-prompts.md at the session's commit before proposing prompt edits."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", help="a conversation id, or 'list'")
    parser.add_argument("--agent", default="", help="with list: only this agent type")
    parser.add_argument("--limit", type=int, default=20, help="with list: how many")
    parser.add_argument("--out", default="", help="bundle directory (default .audits/bundles/<short id>)")
    parser.add_argument("--prompt-check", action="store_true", help="compare the session's system prompt with this checkout")
    parser.add_argument("--uploads-dir", action="append", default=[], help="another local uploads directory to probe for artifact bytes")
    args = parser.parse_args(argv)

    engine = get_engine()
    if engine is None:
        print("DATABASE_URL is not configured; nothing to read.", file=sys.stderr)
        return 2

    with Session(engine) as db:
        if args.target == "list":
            rows = list_conversations(db, agent_type=args.agent, limit=args.limit)
            for r in rows:
                print(
                    f"{r['id']}  {r['agent_type']:<9} {r['run_status']:<9} v×{r['artifact_versions']:<2} "
                    f"ev {r['events']:<4} {r['last_active_at'][:16]}  {r['project'][:24]:<24} {r['title'][:60]}"
                )
            return 0
        bundle = pull(db, UUID(args.target), uploads_dirs=tuple(Path(d) for d in args.uploads_dir))

    out_dir = Path(args.out) if args.out else Path(".audits") / "bundles" / _short(bundle["conversation"]["id"])
    files = write_bundle(bundle, out_dir)
    print(f"bundled {bundle['conversation']['id']} → {out_dir}  ({len(files)} files)")
    print(f"  events {len(bundle['events'])} · tools {len(pair_tools(bundle['events']))} · "
          f"artifacts {len(bundle['artifacts'])} · memories written {len(bundle['memories_written'])}")
    for a in bundle["artifacts"]:
        if a["content_from"] == "missing":
            print(f"  artifact v{a['version']} '{a['title']}': bytes not found (store, desktop uploads); pass --uploads-dir")
    if args.prompt_check:
        print("  " + prompt_check(bundle))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
