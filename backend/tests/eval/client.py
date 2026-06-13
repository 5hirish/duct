"""Judge client construction + credential resolution.

The judge is the harness's only network dependency. It runs a single
vision-capable Claude call, so we use the Anthropic Messages API directly (not
the Agent SDK) — structured output and image input are first-class there.

Credential order (per the project's CI decision): an explicit ``ANTHROPIC_API_KEY``
wins; otherwise fall back to the ``CLAUDE_CODE_OAUTH_TOKEN`` already present in
CI (Bearer auth + the oauth beta header). When neither is available — or the
``anthropic`` SDK isn't installed — ``judge_available()`` is False and callers
skip rather than fail. If a provided OAuth token turns out not to authenticate
the Messages API, the call surfaces an auth error the caller treats as a skip.
"""

from __future__ import annotations

import os

# Default judge model: the most capable grader, so the bar that guards against
# the (cheaper) content model's degradation is itself trustworthy.
DEFAULT_JUDGE_MODEL = "claude-opus-4-8"

# Claude Code OAuth tokens authenticate the Messages API via Bearer + this beta.
_OAUTH_BETA = "oauth-2025-04-20"


class JudgeUnavailable(RuntimeError):
    """No usable Claude credential / SDK is available for the judge."""


def _config_cred(name: str) -> str:
    """Best-effort read of a credential from Duct's settings (covers backend/.env
    for local runs). Never raises if config can't be imported."""
    try:
        from config import get_configs

        return str(getattr(get_configs(), name, "") or "")
    except Exception:
        return ""


def resolve_credentials() -> tuple[str, str]:
    """Return ``(api_key, oauth_token)`` — env first, then Duct config. Either
    or both may be empty."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "") or _config_cred("anthropic_api_key")
    oauth = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "") or _config_cred("claude_code_oauth_token")
    return api_key.strip(), oauth.strip()


def judge_available() -> bool:
    """True when the anthropic SDK is importable and a credential is present."""
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False
    api_key, oauth = resolve_credentials()
    return bool(api_key or oauth)


def build_judge_client():
    """Construct an ``anthropic.Anthropic`` client using the best available
    credential. Raises ``JudgeUnavailable`` when the SDK is missing or no
    credential is set."""
    try:
        import anthropic
    except Exception as exc:  # pragma: no cover - import guard
        raise JudgeUnavailable("the anthropic SDK is not installed") from exc

    api_key, oauth = resolve_credentials()
    if api_key:
        return anthropic.Anthropic(api_key=api_key)
    if oauth:
        # Bearer + oauth beta header, set as defaults so they ride every request
        # (including messages.parse()). x-api-key is intentionally NOT set.
        return anthropic.Anthropic(
            auth_token=oauth,
            default_headers={"anthropic-beta": _OAUTH_BETA},
        )
    raise JudgeUnavailable(
        "no Claude credential found (set ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN)"
    )
