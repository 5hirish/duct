"""Bisect the content agent's ClaudeSDKClient options to find what makes the
subprocess exit 1.

A minimal client works (proven), so this adds the content agent's option
groups one at a time (thinking → effort → partial msgs → agents → tools →
hooks → mcp server) and reports the FIRST stage that fails, with the
subprocess stderr.

Run from the backend dir:
    ./.venv/bin/python scripts/diag_agent.py
"""

from __future__ import annotations

import asyncio
import shutil
import traceback
from uuid import uuid4


def _resolve_api_key() -> str:
    from agents.engines import PROVIDER_CONFIG_ATTR, Engine, resolve_engine_provider
    from config import get_configs
    cfg = get_configs()
    provider = resolve_engine_provider(Engine.V3, cfg.generate_provider or None)
    return getattr(cfg, PROVIDER_CONFIG_ATTR[provider], "") or ""


async def main() -> None:
    from sqlalchemy import select

    from agents.content.schema import ContentTool, make_session
    from agents.content.subagents import (
        BUILD_SLIDES_AGENT,
        DRAFT_POST_AGENT,
        RESEARCH_PILLAR_AGENT,
    )
    from agents.content.tools import build_content_mcp_server
    from agents.content.v3.runner import _resolve_anthropic_model
    from agents.models import AgentEffort, AgentPermissionMode, AgentTool, ModelName, ThinkingMode
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    from claude_agent_sdk.types import HookMatcher, PermissionResultAllow, ThinkingConfigAdaptive
    from db.session import get_session
    from models.project import Project

    cli = shutil.which("claude")
    key = _resolve_api_key()
    env: dict[str, str] = {"OTEL_SERVICE_NAME": "duct-content-diag"}
    if key:
        env["ANTHROPIC_API_KEY"] = key

    # Real-ish dependencies for the heavier stages.
    with next(get_session()) as db:
        proj = db.execute(select(Project)).scalars().first()
    project_id = proj.id if proj else uuid4()

    async def emit(_body):  # noqa: ANN001
        return None

    session = make_session(str(uuid4()), project_id, "draft_post")

    async def can_use_tool(_name, _input, _ctx):  # noqa: ANN001
        return PermissionResultAllow()

    async def noop_hook(_input, _tool_use_id, _ctx):  # noqa: ANN001
        return {}

    base = dict(
        model=_resolve_anthropic_model(ModelName.CLAUDE_SONNET_4_6),
        permission_mode=AgentPermissionMode.DONT_ASK,
        system_prompt="Connectivity test. Reply with exactly: OK",
        max_turns=1,
        env=env,
        setting_sources=[],
        cli_path=cli,
    )

    # Cumulative option groups, in the order the runner layers them.
    stages: list[tuple[str, dict]] = [
        ("base", {}),
        ("+thinking", {"thinking": ThinkingConfigAdaptive(type=ThinkingMode.ADAPTIVE)}),
        ("+effort", {"effort": AgentEffort.MEDIUM}),
        ("+partial_msgs", {"include_partial_messages": True}),
        ("+agents", {"agents": {
            "research_pillar": RESEARCH_PILLAR_AGENT,
            "draft_post": DRAFT_POST_AGENT,
            "build_slides_html": BUILD_SLIDES_AGENT,
        }}),
        ("+allowed_tools", {"allowed_tools": [
            AgentTool.ASK_USER_QUESTION, AgentTool.TODO_WRITE, AgentTool.WEB_SEARCH,
            AgentTool.WEB_FETCH, AgentTool.AGENT,
            ContentTool.SUBMIT_PLAN, ContentTool.SUBMIT_POST_DRAFT,
        ]}),
        ("+hooks+can_use_tool", {
            "can_use_tool": can_use_tool,
            "hooks": {
                "PreToolUse": [HookMatcher(matcher=None, hooks=[noop_hook])],
                "PostToolUse": [HookMatcher(matcher="Agent", hooks=[noop_hook])],
            },
        }),
        ("+mcp_servers", {"mcp_servers": {"duct_content": build_content_mcp_server(project_id, emit, session)}}),
    ]

    acc: dict = {}
    for name, extra in stages:
        acc = {**acc, **extra}
        stderr_lines: list[str] = []
        opts = ClaudeAgentOptions(**base, **acc, stderr=lambda ln: stderr_lines.append(ln))
        print(f"\n--- stage: {name} ---")
        try:
            async with ClaudeSDKClient(opts) as client:
                await client.query("Say OK")
                async for _ in client.receive_response():
                    pass
            print(f"  ✓ {name} OK")
        except Exception:  # noqa: BLE001
            print(f"  ✗ {name} FAILED — this option group is the culprit.")
            traceback.print_exc()
            print("  --- subprocess stderr ---")
            for ln in stderr_lines:
                print("   ", ln.rstrip())
            if not stderr_lines:
                print("    (none captured)")
            return

    print("\nAll option stages passed. Now testing the REAL system prompt + full options…")

    from agents.content.channels import resolve as resolve_channel
    from agents.content.prompts import build_orchestrator_system_prompt
    from agents.content.v3.runner import _load_brand_context

    brand = _load_brand_context(project_id)
    real_system = build_orchestrator_system_prompt(brand, "draft_post", channel=resolve_channel("tiktok"))
    print(f"  real system prompt length: {len(real_system)} chars")
    real_base = {**base, "system_prompt": real_system}
    stderr_lines: list[str] = []
    opts = ClaudeAgentOptions(**real_base, **acc, stderr=lambda ln: stderr_lines.append(ln))
    try:
        async with ClaudeSDKClient(opts) as client:
            await client.query("Reply with exactly: OK")
            async for _ in client.receive_response():
                pass
        print("  ✓ real system prompt + full options OK — could NOT reproduce the failure.")
        print("    → the earlier exit-1 was most likely transient (e.g. a subscription "
              "rate/usage limit — note the RateLimitEvent above). The runner now retries "
              "the connect 3× with backoff, captures the real subprocess stderr, raises a "
              "classified RuntimeError (surfaced via PIPELINE_FAILED), and reports the "
              "exhausted failure to Sentry (tag content.failure=cli_startup).")
    except Exception:  # noqa: BLE001
        print("  ✗ real system prompt + full options FAILED — reproduced it!")
        traceback.print_exc()
        print("  --- subprocess stderr ---")
        for ln in stderr_lines:
            print("   ", ln.rstrip())
        if not stderr_lines:
            print("    (none captured)")


if __name__ == "__main__":
    asyncio.run(main())
