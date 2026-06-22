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

import asyncio
import logging
import os
import shutil
from collections import deque
from contextlib import suppress
from typing import Any

logger = logging.getLogger(__name__)

# Per-session config dirs live under this subfolder of the agent's base dir, so
# cleanup can tell a throwaway session dir apart from the shared base.
_SESSION_DIR_SEGMENT = "sessions"

# A Claude subscription/OAuth token (minted by `claude setup-token`) carries this
# prefix; API keys use `sk-ant-api…`. A bring-your-own Anthropic credential must
# be routed by which kind it is: an OAuth token in ANTHROPIC_API_KEY makes the
# CLI exit 1 during initialize, and an API key in CLAUDE_CODE_OAUTH_TOKEN fails
# the same way. The frontend's API/OAuth selector is only a hint — this prefix is
# the source of truth, so a mis-selected credential still authenticates.
_ANTHROPIC_OAUTH_PREFIX = "sk-ant-oat"


def is_anthropic_oauth_token(value: str | None) -> bool:
    """True when ``value`` looks like a Claude subscription/OAuth token.

    Used to decide whether a bring-your-own Anthropic credential belongs in
    ``CLAUDE_CODE_OAUTH_TOKEN`` (this returns True) or ``ANTHROPIC_API_KEY``.
    """
    return bool(value) and value.strip().startswith(_ANTHROPIC_OAUTH_PREFIX)

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


def build_sdk_env(
    *,
    service_name: str,
    api_key: str,
    oauth_token: str = "",
    config_env_var: str,
    config_suffix: str,
    log_prefix: str = "agent",
    session_id: str | None = None,
    sentry_env: dict[str, str] | None = None,
    api_key_env_var: str = "ANTHROPIC_API_KEY",
    enable_tool_search: bool = True,
    extra: dict[str, str] | None = None,
) -> tuple[dict[str, str], str | None]:
    """Build the env for a Claude-SDK subprocess, isolated from any interactive
    ~/.claude and from an IDE-launched parent. Returns ``(env, config_dir)`` —
    set ``options.env=env`` and pass ``config_dir`` to
    ``cleanup_session_config_dir()`` after teardown.

    Consolidates the env hygiene that audit and content had drifted copies of:
      - clears Claude Code IDE session vars that confuse a child ``claude``
        (parent session id, IDE binary path, inherited effort/checkpointing,
        IDE-sandbox temp dirs);
      - clears a blank ``ANTHROPIC_API_KEY``/``ANTHROPIC_AUTH_TOKEN`` that would
        otherwise shadow ``CLAUDE_CODE_OAUTH_TOKEN`` (exit 1, no stderr);
      - clears an IDE debugger's ``NODE_OPTIONS`` / ``CLAUDE_CODE_SSE_PORT``;
      - per-session ``CLAUDE_CONFIG_DIR`` isolation (see ``isolated_config_dir``);
      - optional Sentry-OTLP (``sentry_env``) + local OTLP (``OTEL_ENDPOINT``).

    ``enable_tool_search=False`` sets ``ENABLE_TOOL_SEARCH=false`` (eager schema
    load — faster for a small fixed tool set). ``extra`` is merged in last for
    any agent-specific keys.
    """
    env: dict[str, str] = {
        "OTEL_SERVICE_NAME": service_name,
        "ENABLE_PROMPT_CACHING_1H": "1",
        # Clear inherited Claude Code IDE session vars that confuse child
        # instances: a parent session id makes the child think it belongs to that
        # session, EXECPATH points at the IDE's binary not the installed CLI,
        # CLAUDE_EFFORT overrides the effort we set, and the temp/checkpoint vars
        # are scoped to the IDE sandbox.
        "CLAUDE_CODE_SESSION_ID": "",
        "CLAUDE_CODE_EXECPATH": "",
        "CLAUDE_EFFORT": "",
        "CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING": "false",
        "CLAUDE_CODE_ENABLE_TASKS": "",
        "TMPDIR": "/tmp",
        "CLAUDE_TMPDIR": "/tmp",
        "CLAUDE_CODE_TMPDIR": "/tmp",
    }
    if not enable_tool_search:
        env["ENABLE_TOOL_SEARCH"] = "false"
    if sentry_env:
        env.update(sentry_env)

    # A bring-your-own Anthropic credential may be a subscription OAuth token
    # rather than an API key. Route it to the OAuth slot so the CLI authenticates
    # correctly, and let a supplied OAuth token win over a server-configured one.
    if is_anthropic_oauth_token(api_key):
        oauth_token = api_key.strip()
        api_key = ""

    # Auth precedence mirrors the CLI's: an explicit key wins; otherwise forward a
    # CLAUDE_CODE_OAUTH_TOKEN. The SDK merges options.env OVER os.environ but can't
    # DELETE a key, so a present-but-blank ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN
    # inherited from a Claude Desktop/Code launch would outrank the OAuth token and
    # make the CLI exit 1 during initialize with no stderr — drop the blanks here.
    if api_key:
        env[api_key_env_var] = api_key
    else:
        for _stale in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            if _stale in os.environ and not os.environ[_stale].strip():
                del os.environ[_stale]
        if oauth_token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token

    # An IDE debugger injects NODE_OPTIONS=--require .../bootloader.js, which the
    # `claude` Node CLI inherits and which corrupts the stream-json protocol (exit
    # 1 during initialize). CLAUDE_CODE_SSE_PORT is the IDE bridge port. Blank both
    # (can't delete; an empty NODE_OPTIONS is ignored by Node).
    for _ide_var in ("NODE_OPTIONS", "CLAUDE_CODE_SSE_PORT"):
        if os.environ.get(_ide_var):
            env[_ide_var] = ""

    config_dir = isolated_config_dir(
        api_key or oauth_token,
        env_var=config_env_var,
        suffix=config_suffix,
        log_prefix=log_prefix,
        session_id=session_id,
    )
    if config_dir:
        env["CLAUDE_CONFIG_DIR"] = config_dir

    # Local OTLP collector (e.g. Phoenix) when OTEL_ENDPOINT is set.
    otel_endpoint = os.environ.get("OTEL_ENDPOINT", "")
    if otel_endpoint:
        env.update({
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_METRICS_EXPORTER": "otlp",
            "OTEL_LOGS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
            "OTEL_EXPORTER_OTLP_ENDPOINT": otel_endpoint,
            "OTEL_METRIC_EXPORT_INTERVAL": "5000",
            "OTEL_LOGS_EXPORT_INTERVAL": "2000",
            "OTEL_TRACES_EXPORT_INTERVAL": "2000",
        })
        logger.info("%s: OTEL traces → %s", log_prefix, otel_endpoint)

    if extra:
        env.update(extra)

    return env, config_dir


async def connect_with_retry(
    options: Any,
    *,
    stderr_buf: deque[str],
    session_id: str,
    agent: str,
    agent_label: str,
    mode: object = "",
) -> Any:
    """Open a connected ``ClaudeSDKClient``, retrying transient startup crashes.

    A fresh client is built per attempt so a half-initialised one is never
    reused. On the final failure raises ``RuntimeError`` carrying the real
    subprocess stderr (the SDK's ``ProcessError`` only says "exit code 1") and
    reports the exhausted failure to Sentry. ``agent`` is the Sentry/log
    namespace; ``agent_label`` is the human noun phrase for the error message.
    """
    from claude_agent_sdk import CLIConnectionError, ClaudeSDKClient, ProcessError

    last_exc: Exception | None = None
    for attempt in range(1, MAX_CONNECT_ATTEMPTS + 1):
        stderr_buf.clear()
        candidate = ClaudeSDKClient(options)
        try:
            await candidate.connect()
            if attempt > 1:
                logger.info(
                    "%s: SDK connect recovered on attempt %d/%d for session %s",
                    agent, attempt, MAX_CONNECT_ATTEMPTS, session_id,
                )
            return candidate
        except (ProcessError, CLIConnectionError) as exc:
            last_exc = exc
            with suppress(Exception):
                await candidate.disconnect()
            captured = captured_stderr(stderr_buf, exc)
            logger.warning(
                "%s: SDK connect attempt %d/%d failed for session %s: %s%s",
                agent, attempt, MAX_CONNECT_ATTEMPTS, session_id, exc,
                f"\n  subprocess stderr:\n{captured}" if captured else "",
            )
            if attempt < MAX_CONNECT_ATTEMPTS:
                await asyncio.sleep(CONNECT_BACKOFF_SECS * attempt)

    captured = captured_stderr(stderr_buf, last_exc)
    exit_code = getattr(last_exc, "exit_code", None)
    rate_limited = is_rate_limited(captured)
    report_startup_failure_to_sentry(
        last_exc, agent=agent, session_id=session_id, mode=mode,
        attempts=MAX_CONNECT_ATTEMPTS, exit_code=exit_code, stderr=captured,
        rate_limited=rate_limited,
    )
    raise RuntimeError(
        describe_startup_failure(captured, exit_code, agent_label=agent_label)
    ) from last_exc


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
