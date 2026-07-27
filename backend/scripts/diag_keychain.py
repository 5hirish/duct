"""Probe whether the Claude Agent SDK can authenticate from the macOS Keychain
alone — no ANTHROPIC_API_KEY, no CLAUDE_CODE_OAUTH_TOKEN in the environment.

Run from the backend dir:
    ./.venv/bin/python scripts/diag_keychain.py
"""

from __future__ import annotations

import asyncio
import os

# Force Keychain-only auth: make sure no key/token reaches the subprocess.
for _v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
    os.environ.pop(_v, None)

from claude_agent_sdk import ClaudeAgentOptions, query  # noqa: E402


async def main() -> None:
    opts = ClaudeAgentOptions(max_turns=1, allowed_tools=[])
    saw_result = False
    async for m in query(prompt="Reply with exactly the token: KEYCHAIN_OK", options=opts):
        name = type(m).__name__
        result = getattr(m, "result", None)
        if result is not None:
            saw_result = True
            print(f"[{name}] result={result.strip()[:120]}")
        elif name == "SystemMessage":
            data = getattr(m, "data", {}) or {}
            print(
                f"[{name}] subtype={getattr(m, 'subtype', None)} "
                f"model={data.get('model')} apiKeySource={data.get('apiKeySource')}"
            )
    print("AUTH_OK (Keychain login works)" if saw_result else "NO_RESULT")


asyncio.run(main())
