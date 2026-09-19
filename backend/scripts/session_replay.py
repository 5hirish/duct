#!/usr/bin/env python3
"""Re-run a stored session on its own data, with the code and model of today.

The question an audit ends on is "would this prompt change have helped?",
and the only honest answer is to run the same question, over the same
pulls, and read the brief that comes out. This does that. The bundle's
FetchData bodies seed the session cache and the connectors are closed
(``replay`` in ``agents/insights/data_tools.py``): a pull the original run
never made returns ``not_in_replay``, so nothing reaches a provider and the
two runs differ only in the prompt, the model, and the dice.

    poetry run python scripts/session_replay.py <bundle dir> [--model ...] [--provider ...] [--tier heavy]
    poetry run python scripts/session_replay.py <bundle dir> --prompt "a different question"

Writes ``<bundle dir>/replays/<timestamp>-<model>/`` with the brief, the
reply, every event that reached the stream, the tool traffic, and a
``replay.json`` naming the prompt fingerprint and the seed coverage, so the
record can cite it. Nothing is written to the database: no recorder, no
artifact persister, no memory tools (``remember=False``), no pausing tools
(``interactive=False``), no execution tools. It does spend the model
credential the user's settings resolve to — this is a real run.

A session with a CONTEXT row replays the turn the model actually read. One
without (before 2026-09-19) gets its blocks rebuilt from the database now —
project fields, profile, memory digest, connector list — and the output
says ``reconstructed: true`` so a reviewer knows the priming may differ.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session  # noqa: E402

from agents.core.context import format_business_context  # noqa: E402
from agents.core.events import AgentEvent, EventKind  # noqa: E402
from agents.core.voice import user_context_block  # noqa: E402
from agents.insights.brief import DEFAULT_FORMAT  # noqa: E402
from agents.insights.data_tools import REPLAY_CONNECTOR  # noqa: E402
from agents.insights.setup import data_sources_block, resolve_run  # noqa: E402
from agents.insights.v1.runner import AutonomousInsightsRunner  # noqa: E402
from agents.models import Provider  # noqa: E402
from agents.registry import AgentType  # noqa: E402
from db.session import get_engine  # noqa: E402
from models.execution import AUTONOMY_ASK  # noqa: E402
from models.project import Project  # noqa: E402
from service.memory import build_memory_context, redact_secrets  # noqa: E402
from service.profile import resolve as resolve_profile  # noqa: E402

FETCH_TOOL = "FetchData"
# The replayed turn ends when the model stops; the chat loop that would wait
# for a follow-up has nobody to wait for.
IDLE_TIMEOUT = 1.0


def load_bundle(bundle_dir: Path) -> dict[str, Any]:
    return json.loads((bundle_dir / "bundle.json").read_text(encoding="utf-8"))


def replay_seed(events: list[dict[str, Any]]) -> dict[tuple[str, str, str], str]:
    """FetchData bodies keyed as the model asked for them.

    The key is the call's arguments, not the envelope's resolved window: the
    replayed model will ask with the same arguments if it reasons the same
    way, and the cache is keyed on arguments. For a repeated key a body whose
    envelope says ``ok`` wins over one that does not, whatever the order: the
    first audit's session had pulled the same report three times, failing
    twice, and "first wins" replayed the failure."""
    inputs: dict[str, dict[str, Any]] = {}
    seed: dict[tuple[str, str, str], str] = {}
    for ev in events:
        data = ev.get("data") or {}
        if ev.get("kind") == EventKind.TOOL_USE and data.get("name") == FETCH_TOOL:
            inputs[data.get("tool_use_id", "")] = data.get("input") or {}
        elif ev.get("kind") == EventKind.TOOL_RESULT and data.get("name") == FETCH_TOOL:
            args = inputs.get(data.get("tool_use_id", ""), {})
            key = (
                str(args.get("entity_id", "")).strip(),
                str(args.get("date_from", "")).strip(),
                str(args.get("date_to", "")).strip(),
            )
            result = data.get("result")
            # A row with no stored body (older recorder versions, a truncated
            # preview) must not seed `null`: the model would read that as a
            # failed pull and write a brief about the outage.
            if result is None or result == "":
                continue
            body = result if isinstance(result, str) else json.dumps(result, default=str)
            if not key[0]:
                continue
            if key not in seed or (_is_ok(body) and not _is_ok(seed[key])):
                seed[key] = body
    return seed


def _is_ok(body: str) -> bool:
    try:
        parsed = json.loads(body)
    except ValueError:
        return False
    return isinstance(parsed, dict) and parsed.get("status") == "ok"


def context_row(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((e.get("data") for e in events if e.get("kind") == EventKind.CONTEXT), None)


def first_prompt(events: list[dict[str, Any]]) -> str:
    for ev in events:
        if ev.get("kind") == EventKind.USER:
            content = (ev.get("data") or {}).get("content")
            return content if isinstance(content, str) else json.dumps(content, default=str)
    return ""


def strip_session_memories(digest: str, written_ids: list[str]) -> tuple[str, int]:
    """Drop digest lines that cite a memory this very session wrote.

    A rebuilt digest is the project as the database knows it today, which
    includes the conclusions the run under replay reached. Priming the
    replay with its own answer is not a replay. Lines are matched on the
    short id the digest cites (m_ + first eight hex), and the count of
    dropped lines goes in replay.json so the reader knows it happened."""
    shorts = {f"m_{str(i).replace('-', '')[:8]}" for i in written_ids}
    kept, dropped = [], 0
    for line in digest.splitlines():
        if any(s in line for s in shorts):
            dropped += 1
            continue
        kept.append(line)
    return "\n".join(kept), dropped


def reconstruct_blocks(db: Session, bundle: dict[str, Any], *, owner_id: UUID | None, run: Any) -> dict[str, str]:
    """Blocks for a session that never recorded them: the best the database
    can say today, which is not what the model read then."""
    project = db.get(Project, UUID(bundle["project"]["id"])) if (bundle.get("project") or {}).get("id") else None
    business = format_business_context(
        {k: getattr(project, k, None) for k in (
            "name", "url", "industry", "business_model", "pitch", "targets", "audience", "competition"
        )} if project else None
    )
    memory, dropped = "", 0
    if project is not None:
        try:
            memory = build_memory_context(
                db, project_id=project.id, user_id=owner_id,
                agent_type=str(AgentType.INSIGHTS), query=first_prompt(bundle["events"]),
                subject=first_prompt(bundle["events"]),
            ).text
        except Exception:  # noqa: BLE001 - a digest is optional priming
            memory = ""
        memory, dropped = strip_session_memories(
            memory, [m["id"] for m in bundle.get("memories_written", [])]
        )
    return {
        "business_context": business,
        "user_context": user_context_block(resolve_profile(owner_id, None)),
        "memory": memory,
        "memory_lines_dropped": dropped,
        "data_sources": data_sources_block(run, user_id=owner_id),
        "artifact_format": DEFAULT_FORMAT,
        "autonomy": run.autonomy,
    }


async def run_replay(
    bundle: dict[str, Any],
    *,
    prompt: str,
    blocks: dict[str, Any],
    run: Any,
    provider: Provider,
    model: Any,
    seed: dict[tuple[str, str, str], str],
    project_id: UUID | None,
    owner_id: UUID | None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    async def emit(body: dict) -> None:
        events.append(body)

    runner = AutonomousInsightsRunner(
        api_key=run.api_key,
        provider=provider,
        model=model,
        thinking="",
        verify_provider=run.verify_provider,
        verify_model=run.verify_model,
        verify_api_key=run.verify_api_key,
    )
    await runner.run_session(
        f"replay-{uuid4()}",
        emit,
        prompt=prompt,
        business_context=str(blocks.get("business_context") or ""),
        user_context=str(blocks.get("user_context") or ""),
        memory=str(blocks.get("memory") or ""),
        data_sources=str(blocks.get("data_sources") or ""),
        project_id=project_id,
        user_id=owner_id,
        conversation_id=None,
        remember=False,
        artifact_format=str(blocks.get("artifact_format") or DEFAULT_FORMAT),
        autonomy=str(blocks.get("autonomy") or AUTONOMY_ASK),
        chat_idle_timeout=IDLE_TIMEOUT,
        compress=bool(blocks.get("compress", True)),
        replay=seed,
        interactive=False,
        execute=False,
    )
    return events


def write_replay(out_dir: Path, *, events: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    def put(name: str, text: str) -> None:
        (out_dir / name).write_text(redact_secrets(text), encoding="utf-8")

    reply = "".join(e.get("text", "") for e in events if e.get("event") == AgentEvent.AGENT_MESSAGE_CHUNK)
    versions = [e for e in events if e.get("event") == AgentEvent.ARTIFACT_VERSION]
    for v in versions:
        payload = v.get("payload") or {}
        ext = "html" if payload.get("format") == "html" else "md"
        put(f"brief-v{v.get('version_id', 1)}.{ext}", str(payload.get("content") or ""))
    put("reply.md", reply)
    put("events.json", json.dumps(events, indent=2, default=str))
    steps = [
        {"label": e.get("label"), "status": e.get("status")}
        for e in events if e.get("event") == AgentEvent.STEP_FINISHED
    ]
    put("replay.json", json.dumps({**meta, "artifact_versions": len(versions), "steps": steps}, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bundle", help="a bundle directory written by session_bundle.py")
    parser.add_argument("--prompt", default="", help="replace the opening question (same data, different ask)")
    parser.add_argument("--provider", default="", help="override the provider the user's settings resolve to")
    parser.add_argument("--model", default="", help="override the model")
    parser.add_argument("--tier", default="", help="lift the analysis tier (heavy | standard | light)")
    args = parser.parse_args(argv)

    bundle_dir = Path(args.bundle)
    bundle = load_bundle(bundle_dir)
    events = bundle["events"]
    ctx = context_row(events)
    project = bundle.get("project") or {}
    project_id = UUID(project["id"]) if project.get("id") else None

    engine = get_engine()
    if engine is None:
        print("DATABASE_URL is not configured; the replay needs the project's model settings.", file=sys.stderr)
        return 2
    with Session(engine) as db:
        owner_id = db.get(Project, project_id).user_id if project_id else None
        run = resolve_run(user_id=owner_id, project_id=project_id, tier_override=args.tier)
        if ctx is not None:
            blocks, reconstructed = dict(ctx.get("blocks") or {}), False
        else:
            blocks, reconstructed = reconstruct_blocks(db, bundle, owner_id=owner_id, run=run), True

    provider = Provider(args.provider) if args.provider else run.provider
    model = args.model or run.model
    prompt = args.prompt or str(blocks.get("prompt") or first_prompt(events))
    seed = replay_seed(events)

    started = datetime.now().astimezone()
    replay_events = asyncio.run(run_replay(
        bundle, prompt=prompt, blocks=blocks, run=run, provider=provider, model=model,
        seed=seed, project_id=project_id, owner_id=owner_id,
    ))
    misses = sum(
        1 for e in replay_events
        if e.get("event") == AgentEvent.STEP_FINISHED and e.get("connector_id") == REPLAY_CONNECTOR
    )
    model_name = str(getattr(model, "value", model))
    out_dir = bundle_dir / "replays" / f"{started.strftime('%Y%m%d-%H%M%S')}-{model_name.replace('/', '_')}"
    write_replay(out_dir, events=replay_events, meta={
        "session": bundle["conversation"]["id"],
        "started_at": started.isoformat(timespec="seconds"),
        "duration_s": round((datetime.now().astimezone() - started).total_seconds(), 1),
        "provider": str(getattr(provider, "value", provider)),
        "model": model_name,
        "tier": args.tier or run.tier,
        "prompt": prompt,
        "reconstructed": reconstructed,
        "memory_lines_dropped": blocks.get("memory_lines_dropped", 0),
        "original_system_prompt_sha256": (ctx or {}).get("system_prompt_sha256", ""),
        "seed_keys": [list(k) for k in seed],
        "seed_misses": misses,
        "blocks_sha256": hashlib.sha256(json.dumps(blocks, sort_keys=True, default=str).encode()).hexdigest(),
    })
    print(f"replayed {bundle['conversation']['id']} → {out_dir}")
    print(f"  {model_name} · seed {len(seed)} pulls · misses {misses} · reconstructed {reconstructed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
