"""Step 0 verification spike for the Higgsfield video integration.

Goal: prove the ONE risky assumption before any feature code is built —
that Higgsfield's hosted MCP (`https://mcp.higgsfield.ai/mcp`, OAuth-protected)
accepts a STORED / REPLAYED bearer token from a HEADLESS backend, via the same
Claude Agent SDK the content runner uses in production. While we're connected,
it also harvests the facts the rest of the plan depends on:

  - the exact Higgsfield tool names (namespaced `mcp__higgsfield__*`),
  - each tool's input parameters (revealed by the model's tool_use blocks),
  - the image-to-video + poll/status tool pair,
  - the response field that holds the final video URL.

Auth:
  - Higgsfield: pass the token via --token or the HIGGSFIELD_TOKEN env var. Use
    either an OAuth access token (from your frontend's Higgsfield OAuth flow) or
    a long-lived Higgsfield CLI/API token. The whole point of the spike is to
    learn which one survives headless replay.
  - Anthropic (for the SDK itself): resolved from backend config exactly like the
    content runner (ANTHROPIC_API_KEY / CLAUDE_CODE_OAUTH_TOKEN), via build_sdk_env.

Run from the backend dir:

    # List tools only (no credits spent):
    HIGGSFIELD_TOKEN=... ./.venv/bin/python scripts/higgsfield_spike.py

    # Actually generate one clip (spends Higgsfield credits):
    HIGGSFIELD_TOKEN=... ./.venv/bin/python scripts/higgsfield_spike.py \
        --generate --image-url https://example.com/keyframe.jpg \
        --prompt "slow push-in, hair moves gently in the wind"

If the MCP server shows status "failed" / "needs auth" in the init dump below,
a replayed bearer does NOT work headlessly → fall back to the cloud REST API
(Option B in the plan).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
from uuid import uuid4

HIGGSFIELD_MCP_URL = "https://mcp.higgsfield.ai/mcp"


def _resolve_anthropic_key() -> str:
    """Resolve the Anthropic API key for the SDK, same path as the content runner."""
    from agents.engines import PROVIDER_CONFIG_ATTR, Engine, resolve_engine_provider
    from config import get_configs

    cfg = get_configs()
    provider = resolve_engine_provider(Engine.V3, cfg.generate_provider or None)
    return getattr(cfg, PROVIDER_CONFIG_ATTR[provider], "") or ""


def _dump_message(msg: object) -> None:
    """Print a single SDK message in a flat, schema-revealing form.

    We inspect by attribute / type-name rather than isinstance so the script is
    robust to which symbols a given claude_agent_sdk version exports.
    """
    kind = type(msg).__name__

    # The init SystemMessage carries MCP connection status + (with tool-search
    # disabled) the loaded tool definitions. This is the bearer-replay verdict.
    if kind == "SystemMessage":
        data = getattr(msg, "data", None)
        subtype = getattr(msg, "subtype", "")
        if subtype == "init" or data is not None:
            print(f"\n[init/system subtype={subtype!r}]")
            if isinstance(data, dict):
                if "mcp_servers" in data:
                    print("  mcp_servers:", data.get("mcp_servers"))
                tools = data.get("tools")
                if tools:
                    hf = [t for t in tools if isinstance(t, str) and "higgsfield" in t]
                    print("  higgsfield tools:", hf or "(none surfaced)")
            else:
                print("  data:", data)
        return

    # Assistant turns: text + tool_use blocks (tool_use.input reveals param shapes).
    content = getattr(msg, "content", None)
    if kind == "AssistantMessage" and isinstance(content, list):
        for block in content:
            btype = type(block).__name__
            if getattr(block, "text", None):
                print(f"\n[assistant.text] {block.text}")
            elif btype == "ToolUseBlock" or getattr(block, "name", None):
                print(f"\n[tool_use] {getattr(block, 'name', '?')}")
                print("  input:", getattr(block, "input", None))
        return

    # Tool results: the completion payload — find which field holds the video URL.
    if kind in ("UserMessage", "ToolResultMessage") and isinstance(content, list):
        for block in content:
            if type(block).__name__ == "ToolResultBlock" or getattr(block, "tool_use_id", None):
                print(f"\n[tool_result tool_use_id={getattr(block, 'tool_use_id', '?')}]")
                print("  content:", getattr(block, "content", None))
        return

    if kind == "ResultMessage":
        print(f"\n[result] is_error={getattr(msg, 'is_error', '?')} "
              f"turns={getattr(msg, 'num_turns', '?')} "
              f"cost_usd={getattr(msg, 'total_cost_usd', '?')}")
        return


def _build_prompt(args: argparse.Namespace) -> str:
    enumerate_step = (
        "1. List EVERY Higgsfield tool you can see (tools whose name starts with "
        "`mcp__higgsfield__`). For each, state its exact name and its input "
        "parameters (name, type, required/optional). Identify which tool does "
        "image-to-video and which one polls/checks generation status."
    )
    if not args.generate:
        return (
            "You are connected to the Higgsfield MCP server. Do ONLY this, then stop:\n"
            + enumerate_step
            + "\nDo NOT generate anything — this is a read-only inventory. Be concise."
        )
    return (
        "You are connected to the Higgsfield MCP server.\n"
        + enumerate_step
        + f"\n2. Then create ONE image-to-video clip: animate the image at "
        f"{args.image_url!r} with this motion prompt: {args.prompt!r}. "
        "Use a 9:16 aspect ratio and the shortest / cheapest duration available. "
        "Submit the job, then poll the status tool until it completes.\n"
        "3. When it finishes, report the FINAL video URL and paste the raw fields "
        "of the completion response so I can see exactly which field holds the URL.\n"
        "Show the exact tool inputs you used at each step. Be concise."
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Higgsfield MCP bearer-replay + tool-discovery spike.")
    parser.add_argument("--token", default=os.environ.get("HIGGSFIELD_TOKEN", ""),
                        help="Higgsfield OAuth access token or long-lived CLI/API token "
                             "(or set HIGGSFIELD_TOKEN).")
    parser.add_argument("--generate", action="store_true",
                        help="Actually run one image-to-video generation (SPENDS CREDITS). "
                             "Default is list-only.")
    parser.add_argument("--image-url", default="",
                        help="Keyframe image URL to animate (required with --generate).")
    parser.add_argument("--prompt", default="subtle, natural motion; slow cinematic push-in",
                        help="Motion prompt for the clip.")
    parser.add_argument("--max-turns", type=int, default=16,
                        help="Agent turn budget (needs headroom to poll).")
    args = parser.parse_args()

    if not args.token:
        raise SystemExit("No Higgsfield token. Pass --token or set HIGGSFIELD_TOKEN.")
    if args.generate and not args.image_url:
        raise SystemExit("--generate requires --image-url (the keyframe to animate).")

    from agents.core import claude_sdk as _sdk
    from agents.content.v3.runner import _resolve_anthropic_model
    from agents.models import AgentPermissionMode, ModelName
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    from config import get_configs

    cfg = get_configs()
    key = _resolve_anthropic_key()

    # Same subprocess env hygiene + auth routing the content runner uses, so the
    # spike reproduces the production SDK path (and survives being launched from
    # an IDE / Claude Code parent).
    env, config_dir = _sdk.build_sdk_env(
        service_name="duct-higgsfield-spike",
        api_key=key,
        oauth_token=cfg.claude_code_oauth_token,
        config_env_var="DUCT_HIGGSFIELD_SPIKE_CONFIG_DIR",
        config_suffix="duct-higgsfield-spike",
        log_prefix="hf-spike",
        session_id=str(uuid4()),
        enable_tool_search=False,  # eager-load schemas so the model sees every tool
    )

    stderr_lines: list[str] = []
    options = ClaudeAgentOptions(
        model=_resolve_anthropic_model(ModelName.CLAUDE_SONNET_4_6),
        permission_mode=AgentPermissionMode.DONT_ASK,
        system_prompt=(
            "You are a terse diagnostic harness. Use the Higgsfield MCP tools as "
            "instructed and report exactly what you observe — tool names, parameters, "
            "and raw responses. Do not editorialize."
        ),
        allowed_tools=["mcp__higgsfield__*"],
        max_turns=args.max_turns,
        env=env,
        setting_sources=[],
        cli_path=shutil.which("claude") or None,
        mcp_servers={
            "higgsfield": {
                "type": "http",
                "url": HIGGSFIELD_MCP_URL,
                "headers": {"Authorization": f"Bearer {args.token}"},
            }
        },
        stderr=lambda ln: stderr_lines.append(ln),
    )

    print(f"Connecting to {HIGGSFIELD_MCP_URL} with a {'GENERATE' if args.generate else 'LIST-ONLY'} run…")
    print("Watch the [init/system] line for the higgsfield server status — that's the bearer-replay verdict.\n")

    try:
        async with ClaudeSDKClient(options) as client:
            await client.query(_build_prompt(args))
            async for msg in client.receive_response():
                _dump_message(msg)
    except Exception:  # noqa: BLE001
        import traceback
        print("\n✗ SPIKE FAILED — exception while connecting/streaming:")
        traceback.print_exc()
        print("\n--- subprocess stderr ---")
        for ln in stderr_lines:
            print("   ", ln.rstrip())
        if not stderr_lines:
            print("    (none captured)")
        raise
    finally:
        if config_dir:
            from contextlib import suppress
            with suppress(Exception):
                _sdk.cleanup_session_config_dir(config_dir)

    print("\n✓ Stream completed. Record from the output above:")
    print("  - higgsfield server status in [init/system] (connected ⇒ bearer replay works headless)")
    print("  - the image-to-video tool name + its image/prompt/duration/aspect params (from [tool_use])")
    print("  - the status/poll tool name")
    print("  - the final video URL field name (from [tool_result] / [assistant.text])")


if __name__ == "__main__":
    asyncio.run(main())
