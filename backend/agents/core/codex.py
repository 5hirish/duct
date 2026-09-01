"""Subscription-backed GPT (Codex) for the v1 (LangChain) engine.

The OpenAI counterpart of ``agents/core/claude_cli.py``, and a materially better
shape than it. Where a Claude subscription can only be reached by spawning the
`claude` CLI (measured: ~125s/call, a ~150k-token Claude Code prefix, and no
token streaming), ``_ChatOpenAICodex`` is a plain ``ChatOpenAI`` subclass
pointed at ``https://chatgpt.com/backend-api/codex`` with refresh-aware OAuth
headers. No subprocess, so none of those three costs should apply — though that
is reasoned, not measured: see the UNVERIFIED note below.

It ships inside ``langchain-openai``, which this project already depends on, so
this module adds no dependency.

Auth is an operator-level credential on the machine, like v3's
``CLAUDE_CODE_OAUTH_TOKEN`` — not a per-request BYO header. That is deliberate:
a ChatGPT credential is an access+refresh pair that must be rotated and written
back, not the static string the ``X-Provider-*`` headers carry, and consumer
subscriptions are individual-use only, so there is no multi-user case to serve.
The operator logs in once with either helper from
``langchain_openai.chatgpt_oauth``::

    login_chatgpt()          # browser
    login_chatgpt_device()   # headless: prints a user code + verification URL

Both write ``~/.langchain/chatgpt-auth.json`` — deliberately *not*
``~/.codex/auth.json``, so refresh-token rotation here cannot invalidate a Codex
CLI or VS Code session.

UNVERIFIED — no ChatGPT login existed on this machine when this was written, so
nothing here has made a live call. Two things to confirm on first use:
  1. which model ids the Codex backend accepts (it may want codex-flavoured ids
     rather than Duct's ``gpt-5.6-*`` catalogue), and
  2. that streaming and ``with_structured_output`` behave, which is the exact
     pair that sank the Claude route.

``_ChatOpenAICodex`` is private and its own docstring calls it "experimental and
unofficial"; OpenAI's docs steer automation toward API keys. Individual use only.
See https://learn.chatgpt.com/docs/auth
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# OpenAI API keys start with this; a ChatGPT OAuth access token does not. Same
# routing principle the Anthropic path uses — the credential's own shape decides,
# never a UI selection — so a Codex token pasted into the existing OpenAI field
# is classified correctly without a new header.
API_KEY_PREFIX = "sk-"


def codex_store_path() -> Path:
    """Where ``langchain-openai`` keeps the ChatGPT OAuth token."""
    from langchain_openai.chatgpt_oauth import DEFAULT_STORE_PATH

    return DEFAULT_STORE_PATH


def codex_available() -> bool:
    """True when an operator has completed a ChatGPT login on this machine.

    A missing ``langchain_openai`` is treated as "unavailable" rather than an
    error: v1 on an API key must never need this path.
    """
    try:
        return codex_store_path().is_file()
    except Exception:  # pragma: no cover - defensive
        return False


def is_openai_api_key(api_key: str) -> bool:
    """True for a Console API key, as opposed to a ChatGPT OAuth credential."""
    return bool(api_key) and api_key.strip().startswith(API_KEY_PREFIX)


def should_use_codex(api_key: str = "") -> bool:
    """True when v1's OpenAI slot should run on the subscription.

    An explicit API key always wins: it is the supported path, the only one that
    may serve end users, and the one with predictable latency.
    """
    if is_openai_api_key(api_key):
        return False
    return codex_available()


def build_codex_chat(
    model: str,
    *,
    api_key: str = "",  # noqa: ARG001 — absent by construction; see should_use_codex
    temperature: float = 1.0,
    **kwargs: Any,
):
    """A LangChain chat model backed by a ChatGPT subscription.

    Imported lazily so v1 on Gemini/OpenRouter never pays for the import.
    """
    from langchain_openai.chat_models.codex import _ChatOpenAICodex
    from langchain_openai.chatgpt_oauth import _FileChatGPTOAuthTokenProvider

    if not codex_available():
        raise RuntimeError(
            "No ChatGPT login found at "
            f"{codex_store_path()}. Run `login_chatgpt()` (browser) or "
            "`login_chatgpt_device()` (headless) from "
            "langchain_openai.chatgpt_oauth, or set OPENAI_API_KEY to use the "
            "regular API instead."
        )

    logger.info("v1 OpenAI slot on ChatGPT subscription (Codex): model=%s", model)
    return _ChatOpenAICodex(
        model=model,
        temperature=temperature,
        token_provider=_FileChatGPTOAuthTokenProvider.from_default_store(),
        **kwargs,
    )
