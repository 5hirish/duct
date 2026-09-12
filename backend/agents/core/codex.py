"""Subscription-backed GPT (Codex) for the v1 (LangChain) engine.

The OpenAI counterpart of what ``agents/core/claude_cli.py`` was, and a
materially better shape than it. Where a Claude subscription could only be
reached by spawning the `claude` CLI (measured: ~125s/call, a ~150k-token
prefix, no streaming), ``_ChatOpenAICodex`` is a plain ``ChatOpenAI`` subclass
pointed at ``https://chatgpt.com/backend-api/codex`` with OAuth headers. It
ships inside ``langchain-openai``, which this project already depends on.

Two credential shapes reach this module, and the second is the one that
matters for the product:

* **A file store** (``~/.langchain/chatgpt-auth.json``) written by
  ``login_chatgpt()`` — an operator-level login on the machine running the
  backend. Kept for a self-hosted backend whose operator logged in by hand.
* **A per-request credential** — the ChatGPT *access token* the desktop shell
  obtained through its own OAuth (``desktop/src-tauri/src/chatgpt.rs``) and
  sent in the ordinary ``X-Provider-OpenAI`` header, with the account id
  beside it in ``X-OpenAI-Account-Id``. The refresh token never leaves the
  user's keychain: the backend holds a token good for about an hour and
  nothing that could mint another. ``service/auth.py`` packs the two headers
  into one string so the credential rides through ``resolve_job_run``,
  ``ProviderKey`` and ``resolve_chat_model`` exactly as an API key does — the
  whole point is that nothing between the request and the client has to know.

The credential's own shape decides the route, never a UI selection: an API key
starts with ``sk-``, an OAuth access token is a JWT. Same principle the
Anthropic header used to tell a key from an OAuth token.

``_ChatOpenAICodex`` is private and its own docstring calls it "experimental
and unofficial"; OpenAI's docs steer automation toward API keys, and consumer
plans are individual-use. That is why the credential is per user and per
request, and why ``PUT /providers/openai/key`` refuses to store one.

**Which models this route may ask for.** The Codex backend serves a ChatGPT
account a narrower set than an API key: every ``*-pro`` variant is refused
outright with "The '<model>' model is not supported when using Codex with a
ChatGPT account". Duct's catalogue (``agents/models.py``) lists no OpenAI
``-pro`` id at all, so the tier map's three rungs — sol, terra, luna — and the
``GPT_5_MINI`` fallback beneath them are all reachable on a plan. Adding a
``-pro`` id to that catalogue would make the Heavy tier fail for every
subscription user and nobody else, which is exactly the kind of break a
verify step reports as ``model_access`` long after the change.

Three request fields are forced by the backend and set for us:
``use_responses_api``, ``store=False`` and ``streaming=True``. It also rejects
a request with no top-level ``instructions`` and any ``SystemMessage`` in the
input list — ``_ChatOpenAICodex`` lifts one into the other, so a runner's
system prompt arrives intact with nothing here to do.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agents.models import Provider

logger = logging.getLogger(__name__)

# OpenAI API keys start with this; a ChatGPT OAuth access token does not.
API_KEY_PREFIX = "sk-"

# Every JWT's header is base64url of ``{"alg": …`` and so begins like this.
_JWT_PREFIX = "eyJ"

# Separates access token from account id inside the packed credential. Neither
# half can contain it: a JWT is base64url and dots, an account id is a UUID.
_PACK_SEPARATOR = "|"

# The claim namespace OpenAI puts the ChatGPT account under, in both the
# id_token and (as observed by the Codex CLI) the access token.
_AUTH_CLAIMS = "https://api.openai.com/auth"

# What the ``originator`` header says. Honest about who is calling; if OpenAI
# ever gates by it, the verify step's ``subscription_blocked`` row is the
# fallback, not a spoofed value. ``LANGCHAIN_CODEX_ORIGINATOR`` is the env
# override langchain-openai already documents, so it is honoured here too.
ORIGINATOR = "duct"

# The token provider protocol demands a non-empty refresh token; the shell
# holds the real one and the backend must never see it. This sentinel is the
# documented promise that it never will.
_REFRESH_HELD_BY_SHELL = "held-by-desktop-shell"

# When a JWT carries no ``exp`` claim, assume OpenAI's usual lifetime.
_DEFAULT_ACCESS_LIFETIME = timedelta(hours=1)


# ---------------------------------------------------------------------------
# Credential shapes
# ---------------------------------------------------------------------------


def is_openai_api_key(api_key: str) -> bool:
    """True for a Console API key, as opposed to a ChatGPT OAuth credential."""
    return bool(api_key) and api_key.strip().startswith(API_KEY_PREFIX)


def is_subscription_credential(value: str) -> bool:
    """True when ``value`` is a ChatGPT access token (packed or bare).

    A JWT, by shape: three dot-separated base64url segments whose header
    decodes to a JSON object. Nothing an API key or a blank could satisfy.
    """
    if not value:
        return False
    token = value.strip().split(_PACK_SEPARATOR, 1)[0]
    if not token.startswith(_JWT_PREFIX) or token.count(".") != 2:
        return False
    return bool(decode_jwt_claims(token, segment=0))


# The only provider Duct can reach through a consumer plan.
#
# Anthropic disabled third-party OAuth on the Messages API in Feb 2026 and its
# terms forbid routing a Claude plan through another application at all, so
# there is no second entry to add here later. That matters because the shape
# test above answers only "is this a JWT" — it cannot tell a ChatGPT token from
# any other JWT a user might paste into the wrong box, and every caller that
# *renders* or *bills* a source has to ask both questions. Asking only the
# first is how the settings page came to promise an Anthropic subscription
# that cannot exist.
SUBSCRIPTION_PROVIDERS = frozenset({Provider.OPENAI})


def is_plan_credential(provider: Provider, value: str) -> bool:
    """True when ``value`` is a plan token *and* ``provider`` has a plan path."""
    return provider in SUBSCRIPTION_PROVIDERS and is_subscription_credential(value)


def is_usable_credential(provider: Provider, value: str) -> bool:
    """False for a credential this provider could never accept.

    Deliberately narrow: the only shape certain enough to reject on is that a
    JWT is not an API key. Every vendor Duct talks to issues a prefixed opaque
    string (``sk-ant-``, ``sk-``, ``AIza``, ``xai-``); the single reason a JWT
    appears in a provider slot at all is that a ChatGPT plan travels as one,
    and that is OpenAI's slot. Anywhere else it is stale or mis-pasted.

    Why this exists rather than the caller just checking presence: ``bool(key)``
    was being reported as ``reachable`` and ``runnable``, so a leftover JWT in
    the Anthropic slot lit the tile green *and* made ``/models/preview`` promise
    "Heavy jobs run on claude-opus-5" — a run that 401s. Presence is not
    reachability, and the difference has to be decided once, here, or each
    endpoint invents its own answer.

    Do not widen this to per-provider prefixes without moving the prefix table
    here first: OpenRouter's key may front any OpenAI-compatible gateway, so
    its shape is genuinely not ours to assert.
    """
    value = (value or "").strip()
    if not value:
        return False
    if is_subscription_credential(value):
        return provider in SUBSCRIPTION_PROVIDERS
    return True


def pack_subscription_credential(access_token: str, account_id: str = "") -> str:
    """One string carrying both halves, for the credential plumbing."""
    token = (access_token or "").strip()
    account = (account_id or "").strip()
    return f"{token}{_PACK_SEPARATOR}{account}" if account else token


@dataclass(frozen=True)
class SubscriptionCredential:
    """The two values the Codex backend needs on every request."""

    access_token: str
    account_id: str
    expires_at: datetime
    plan_type: str = ""


def unpack_subscription_credential(value: str) -> SubscriptionCredential:
    """The packed form back into its parts, filling the account id from the
    token's own claims when the header did not carry one."""
    token, _, account = (value or "").strip().partition(_PACK_SEPARATOR)
    claims = decode_jwt_claims(token)
    auth = claims.get(_AUTH_CLAIMS) if isinstance(claims.get(_AUTH_CLAIMS), dict) else {}
    account_id = account.strip() or str(auth.get("chatgpt_account_id") or "")
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and exp > 0:
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    else:
        expires_at = datetime.now(timezone.utc) + _DEFAULT_ACCESS_LIFETIME
    return SubscriptionCredential(
        access_token=token,
        account_id=account_id,
        expires_at=expires_at,
        plan_type=str(auth.get("chatgpt_plan_type") or ""),
    )


def decode_jwt_claims(token: str, *, segment: int = 1) -> dict[str, Any]:
    """A JWT segment as a dict, **without** signature verification.

    Local claim extraction only — the account id for a header, an expiry for a
    log line. Never an authorisation decision: the Codex backend verifies the
    signature, and it is the only party that can.
    """
    parts = (token or "").split(".")
    if len(parts) != 3:
        return {}
    raw = parts[segment]
    try:
        padded = raw + "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


# ---------------------------------------------------------------------------
# The operator file store (self-hosted backend, logged in by hand)
# ---------------------------------------------------------------------------


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


def should_use_codex(api_key: str = "") -> bool:
    """True when v1's OpenAI slot should run on a ChatGPT subscription.

    An explicit API key always wins: it is the supported path, the only one that
    may serve end users, and the one with predictable latency. A per-request
    access token is the next answer; the operator's file store is the last.
    """
    if is_openai_api_key(api_key):
        return False
    if is_subscription_credential(api_key):
        return True
    return codex_available()


# ---------------------------------------------------------------------------
# Building the client
# ---------------------------------------------------------------------------


class _HeaderTokenProvider:
    """A ``_ChatGPTOAuthTokenProvider`` over the credential one request carried.

    Returns the same token every time and never refreshes: there is no refresh
    token here to refresh with, by design. When the token expires, the run
    fails with a 401 that the verify step names ``subscription_revoked`` and
    the shell answers by minting a fresh one on the next request.
    """

    def __init__(self, credential: SubscriptionCredential) -> None:
        from langchain_openai.chatgpt_oauth import _ChatGPTToken

        self._token = _ChatGPTToken(
            access_token=credential.access_token,
            refresh_token=_REFRESH_HELD_BY_SHELL,
            expires_at=credential.expires_at,
            account_id=credential.account_id or None,
            plan_type=credential.plan_type or None,
        )

    def get_token(self):
        return self._token

    async def aget_token(self):
        return self._token

    def get_access_token(self) -> str:
        return self._token.access_token

    async def aget_access_token(self) -> str:
        return self._token.access_token


def _originator() -> str:
    return os.environ.get("LANGCHAIN_CODEX_ORIGINATOR") or ORIGINATOR


def build_codex_chat(
    model: str,
    *,
    api_key: str = "",
    temperature: float = 1.0,
    **kwargs: Any,
):
    """A LangChain chat model backed by a ChatGPT subscription.

    ``api_key`` is the packed per-request credential when the desktop shell
    signed the user in, or empty to use the operator's file store. Imported
    lazily so v1 on Gemini/OpenRouter never pays for the import.
    """
    from langchain_openai.chat_models.codex import _ChatOpenAICodex

    if is_subscription_credential(api_key):
        credential = unpack_subscription_credential(api_key)
        if not credential.account_id:
            # The Codex backend rejects a request with no account header as an
            # opaque error several screens later; say it here instead.
            logger.warning("codex: access token carried no chatgpt_account_id")
        token_provider: Any = _HeaderTokenProvider(credential)
        logger.info(
            "v1 OpenAI slot on the user's ChatGPT plan (%s): model=%s",
            credential.plan_type or "plan unknown",
            model,
        )
    else:
        from langchain_openai.chatgpt_oauth import _FileChatGPTOAuthTokenProvider

        if not codex_available():
            raise RuntimeError(
                "No ChatGPT login found at "
                f"{codex_store_path()}. Run `login_chatgpt()` (browser) or "
                "`login_chatgpt_device()` (headless) from "
                "langchain_openai.chatgpt_oauth, or set OPENAI_API_KEY to use the "
                "regular API instead."
            )
        token_provider = _FileChatGPTOAuthTokenProvider.from_default_store()
        logger.info("v1 OpenAI slot on the operator's ChatGPT login: model=%s", model)

    return _ChatOpenAICodex(
        model=getattr(model, "value", model),
        temperature=temperature,
        token_provider=token_provider,
        originator=_originator(),
        **kwargs,
    )
