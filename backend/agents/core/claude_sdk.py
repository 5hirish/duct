"""Shared Claude Agent SDK startup helpers for streaming agents.

The `claude` CLI subprocess can exit non-zero during initialize() before it
streams anything — usually a transient subscription/rate limit on the OAuth
path or a momentary spawn glitch. These helpers classify and phrase those
failures, isolate the worker's CLI config dir from an interactive ~/.claude,
and report exhausted failures to Sentry. They were written for the content
agent; they live here so audit and future Claude-SDK agents can reuse them.

Agent-specific text (the human label, the config-dir env var/suffix, the Sentry
tag namespace, log prefix) is passed in, so behavior is identical to the
original per-agent code when called with that agent's parameters.
"""

from __future__ import annotations

import logging
import os
import shutil
from collections import deque

logger = logging.getLogger(__name__)

# Per-session config dirs live under this subfolder of the agent's base dir, so
# cleanup can tell a throwaway session dir apart from the shared base.
_SESSION_DIR_SEGMENT = "sessions"

# Retry an initialize crash with backoff — nothing has streamed yet, so a fresh
# connect is side-effect-free.
MAX_CONNECT_ATTEMPTS = 3
CONNECT_BACKOFF_SECS = 1.5

# Substrings marking a startup stderr as a usage/rate limit (case-folded match).
RATE_LIMIT_HINTS = (
    "rate limit",
    "usage limit",
    "quota",
    "429",
    "limit reached",
    "overloaded",
)

# The SDK fills ProcessError.stderr with this literal when it couldn't drain the
# pipe — it carries no signal, so we treat it as "no stderr captured".
PLACEHOLDER_STDERR = "Check stderr output for details"


def captured_stderr(buf: deque[str], exc: Exception) -> str:
    """Best real subprocess stderr: our own ring buffer first, then the SDK's
    ProcessError.stderr — but never the meaningless placeholder."""
    text = "\n".join(buf).strip()
    if text:
        return text
    sdk_stderr = (getattr(exc, "stderr", "") or "").strip()
    return "" if sdk_stderr == PLACEHOLDER_STDERR else sdk_stderr


def is_rate_limited(stderr_text: str) -> bool:
    lowered = (stderr_text or "").lower()
    return any(hint in lowered for hint in RATE_LIMIT_HINTS)


def describe_startup_failure(
    stderr_text: str,
    exit_code: int | None,
    *,
    agent_label: str = "agent engine",
) -> str:
    """Phrase a clear, user-facing reason for a CLI startup crash.

    ``agent_label`` is the human noun phrase (e.g. "content engine"). Falls back
    to a generic message when no stderr was captured so the error is never just
    "exit code 1".
    """
    text = (stderr_text or "").strip()
    if is_rate_limited(text):
        return (
            f"The {agent_label} hit a temporary Claude usage/rate limit while "
            "starting up. Wait a few minutes and retry."
            + (f"\nSubprocess stderr:\n{text}" if text else "")
        )
    if text:
        return (
            f"The {agent_label} subprocess failed to start "
            f"(exit code {exit_code}).\nSubprocess stderr:\n{text}"
        )
    return (
        f"The {agent_label} subprocess failed to start "
        f"(exit code {exit_code}) without emitting stderr. Common causes: the "
        "Claude CLI is not authenticated (set CLAUDE_CODE_OAUTH_TOKEN from "
        "`claude setup-token`, or ANTHROPIC_API_KEY), a temporary subscription "
        "usage limit, or the backend was launched from an IDE debugger that "
        "injected NODE_OPTIONS into the spawned Node CLI."
    )


def isolated_config_dir(
    explicit_auth: str,
    *,
    env_var: str,
    suffix: str,
    log_prefix: str = "agent",
    session_id: str | None = None,
) -> str | None:
    """A CLAUDE_CONFIG_DIR isolated from the developer's interactive ~/.claude.

    A backend worker spawning `claude` on the OAuth path shares ~/.claude with
    any interactive Claude Code on the box — session files, locks, plugin venv
    bootstraps. That contention is the one difference between a worker that
    intermittently sees the CLI exit 1 during initialize and a clean-room run.
    A dedicated config dir removes it.

    ``explicit_auth`` is any auth the SDK env carries itself (ANTHROPIC_API_KEY
    or a CLAUDE_CODE_OAUTH_TOKEN). When empty we fall back to the interactive
    `/login` subscription, whose credentials live in ~/.claude/.credentials.json,
    so we symlink that file (live, so refreshes propagate). ``env_var`` opts out
    when set to a falsey string; ``suffix`` names the dir (``~/.claude-<suffix>``).

    ``session_id`` (when given) gives THIS run its own dir under
    ``~/.claude-<suffix>/sessions/<session_id>``, so concurrent `claude`
    subprocesses never share CLI state (locks, session files) and can't contend
    — the durable fix for two same-agent runs overlapping. Pair it with
    ``cleanup_session_config_dir`` once the subprocess is gone.

    Returns the dir to use, or None to fall back to the default ~/.claude.
    """
    override = os.environ.get(env_var)
    if override in ("0", "off", "false", "no"):
        return None

    home = os.path.expanduser("~/.claude")
    base = override or f"{home}-{suffix}"
    # Per-session subdir keeps concurrent runs from sharing CLI state; without a
    # session_id we keep the historical single shared dir.
    target = os.path.join(base, _SESSION_DIR_SEGMENT, session_id) if session_id else base
    try:
        os.makedirs(target, exist_ok=True)
        if not explicit_auth:
            src = os.path.join(home, ".credentials.json")
            dst = os.path.join(target, ".credentials.json")
            if os.path.exists(src) and not os.path.lexists(dst):
                os.symlink(src, dst)
        return target
    except OSError:
        logger.warning(
            "%s: could not prepare isolated CLAUDE_CONFIG_DIR at %s; "
            "falling back to default ~/.claude", log_prefix, target, exc_info=True,
        )
        return None


def cleanup_session_config_dir(path: str | None, *, log_prefix: str = "agent") -> None:
    """Remove a per-session config dir created by ``isolated_config_dir(session_id=…)``.

    Best-effort and defensive: only ever removes a dir that sits under the
    ``/sessions/`` segment, so a shared base dir (or an operator override) can
    never be deleted. No-op on a falsy path. Safe to call after the subprocess
    has been disconnected.
    """
    if not path:
        return
    if f"{os.sep}{_SESSION_DIR_SEGMENT}{os.sep}" not in path:
        return  # not a session-scoped dir — never touch the shared base
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:  # noqa: BLE001 — cleanup must never break teardown
        logger.debug("%s: could not remove session config dir %s", log_prefix, path, exc_info=True)


def report_startup_failure_to_sentry(
    exc: Exception | None,
    *,
    agent: str,
    session_id: str,
    mode: object = "",
    attempts: int,
    exit_code: int | None,
    stderr: str,
    rate_limited: bool,
) -> None:
    """Send an exhausted CLI-startup failure to Sentry (no-op if uninitialised).

    Only the final failure (after all retries) is reported. Rate-limit vs hard
    crashes get distinct fingerprints so they group separately. Never raises.
    """
    try:
        import sentry_sdk

        kind = "rate_limit" if rate_limited else "startup_crash"
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("agent", agent)
            scope.set_tag(f"{agent}.failure", "cli_startup")
            scope.set_tag(f"{agent}.failure_kind", kind)
            scope.set_tag(f"{agent}.mode", str(getattr(mode, "value", mode)))
            scope.set_context(
                f"{agent}_startup",
                {
                    "session_id": session_id,
                    "attempts": attempts,
                    "exit_code": exit_code,
                    "stderr": stderr or "(none captured)",
                },
            )
            scope.fingerprint = [f"{agent}-cli-startup", kind]
            scope.level = "warning" if rate_limited else "error"
            if exc is not None:
                sentry_sdk.capture_exception(exc)
            else:
                sentry_sdk.capture_message(
                    f"{agent} CLI startup failed ({kind})", level=scope.level
                )
    except Exception:  # noqa: BLE001 — reporting must never break the run
        logger.debug("%s: Sentry startup-failure report failed", agent, exc_info=True)
