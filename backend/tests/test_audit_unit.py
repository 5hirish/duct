"""Unit tests for the SEO audit unified-session tag parser and event logic.

All tests are pure-Python — no network, no Anthropic API key needed. The
ClaudeSDKClient is patched so we can feed controlled StreamEvent sequences
and verify exactly which SSE events run_synthesis() emits.

Covers:
  - _parse_report()              direct unit test
  - <duct_artifact> tag parser     single chunk, split across chunks, text before/after
  - THINKING_CHUNK forwarding    adaptive thinking delta → event
  - MESSAGE_STOP emission        after each completed turn
  - session close terminates     close_session() drains chat_queue cleanly
  - <audit_report_update>        second turn → REPORT_UPDATED version 2
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load backend/.env.local so secrets are available without the server's loader.
for _env_file in (ROOT / ".env", ROOT / ".env.local"):
    if _env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=False)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_FIXTURE_URL = "https://test.io/"

# The <duct_artifact> tag now wraps HTML directly (not JSON).
# This is the HTML artifact the model generates.
_REPORT_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    "<meta charset=\"UTF-8\"><title>SEO Report</title>"
    "<style>body{font-family:sans-serif;}</style></head>"
    "<body><h1>SEO Audit</h1><p>Score: 72/100</p></body></html>"
)

# For update-tag tests we also need a v2 HTML
_REPORT_V2_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    "<meta charset=\"UTF-8\"><title>SEO Report v2</title>"
    "<style>body{font-family:sans-serif;}</style></head>"
    "<body><h1>SEO Audit — Updated</h1><p>Score: 85/100</p></body></html>"
)

# Use the real SDK StreamEvent dataclass so isinstance checks in runner.py pass.
from claude_agent_sdk.types import StreamEvent as _SDKStreamEvent  # noqa: E402

_UUID = "00000000-0000-0000-0000-000000000001"
_SID = "test-session"


def _text_delta(text: str) -> _SDKStreamEvent:
    return _SDKStreamEvent(
        uuid=_UUID, session_id=_SID,
        event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}},
    )


def _thinking_delta(text: str) -> _SDKStreamEvent:
    return _SDKStreamEvent(
        uuid=_UUID, session_id=_SID,
        event={"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": text}},
    )


def _message_stop() -> _SDKStreamEvent:
    return _SDKStreamEvent(uuid=_UUID, session_id=_SID, event={"type": "message_stop"})


async def _async_gen(items):
    """Wrap a list as an async iterable for receive_response()."""
    for item in items:
        yield item


def _make_mock_sdk(stream_messages: list):
    """
    Return a mock ClaudeSDKClient for the connect_with_retry flow.

    The runner instantiates the client and calls connect()/disconnect()
    directly (no `async with`), so those are async no-ops here. query() is a
    no-op; receive_response() yields the given stream_messages in order.
    """
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.query = AsyncMock()
    mock_client.receive_response = MagicMock(return_value=_async_gen(stream_messages))
    return mock_client


def _make_crawl_result(url: str = _FIXTURE_URL):
    from agents.audit.schema import CrawlPlan, CrawlResult
    plan = CrawlPlan(
        root_url=url,
        sitemap_url="",
        robots_txt_url=f"{url}robots.txt",
        llms_txt_url=f"{url}llms.txt",
        landing_pages=[url],
        blog_posts=[],
        total_sitemap_urls=1,
    )
    return CrawlResult(plan=plan, pages=[], robots_txt="", llms_txt="", crawl_errors=[])


async def _run(stream_messages: list, close_on_report: bool = True):
    """
    Run run_synthesis() with a mocked SDK and return (report, had_thinking, events).

    If close_on_report is True (default), the collect callback calls
    close_session() when REPORT_UPDATED fires, which terminates the
    message_gen loop so the function returns promptly.
    """
    from agents.audit.schema import AuditBusinessContext
    from agents.audit.v3.runner import (
        close_session,
        create_audit_session,
        run_synthesis,
    )
    from agents.models import Provider

    session_id = "unit-test-session"
    create_audit_session(session_id)
    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)
        if close_on_report and event.get("event") == "report_updated":
            close_session(session_id)

    crawl = _make_crawl_result()
    biz = AuditBusinessContext()

    with patch("claude_agent_sdk.ClaudeSDKClient", return_value=_make_mock_sdk(stream_messages)):
        report, had_thinking = await run_synthesis(
            session_id=session_id,
            crawl_result=crawl,
            business_context=biz,
            model_str="claude-haiku-4-5-20251001",
            api_key="test-key",
            provider=Provider.ANTHROPIC,
            emit=collect,
        )

    # Clean up in case close_session wasn't called
    close_session(session_id)

    return report, had_thinking, events


# ---------------------------------------------------------------------------
# HTML artifact extraction (no SDK involved)
# ---------------------------------------------------------------------------

def test_report_built_from_html():
    """AuditReport is now built from raw HTML, not JSON parsing."""
    from agents.audit.schema import AuditReport
    report = AuditReport(
        url=_FIXTURE_URL,
        generated_at="2026-05-16T00:00:00",
        html_report=_REPORT_HTML,
        executive_summary="Strong fundamentals, critical title issue.",
    )
    assert report.url == _FIXTURE_URL
    assert "<html" in report.html_report
    assert report.executive_summary != ""


# ---------------------------------------------------------------------------
# Tag parser: happy path (single chunk contains full tag)
# ---------------------------------------------------------------------------

async def test_duct_artifact_tag_single_chunk():
    stream = [
        _text_delta("I analysed the site. "),
        _text_delta(f"<duct_artifact>{_REPORT_HTML}</duct_artifact>"),
        _text_delta(" Report is ready."),
        _message_stop(),
    ]
    report, _, events = await _run(stream)

    assert report is not None, "report not extracted from <duct_artifact> tag"
    assert report.url == _FIXTURE_URL

    # Text outside the tag should be streamed
    chunks = [e["text"] for e in events if e.get("event") == "agent_message_chunk"]
    combined = "".join(chunks)
    assert "I analysed the site." in combined
    assert " Report is ready." in combined

    # HTML inside the tag must NOT appear in chat chunks
    assert "<!DOCTYPE html>" not in combined, "raw HTML leaked into AGENT_MESSAGE_CHUNK"

    # REPORT_UPDATED must fire exactly once with version_id=1
    updates = [e for e in events if e.get("event") == "report_updated"]
    assert len(updates) == 1
    assert updates[0]["version_id"] == 1
    assert updates[0]["payload"]["url"] == _FIXTURE_URL

    # html_report must survive the tag parser intact and be valid HTML
    assert report.html_report, "html_report was lost during tag parsing"
    assert "<html" in report.html_report.lower()
    assert "</html>" in report.html_report.lower()
    assert updates[0]["payload"]["html_report"] == report.html_report, \
        "html_report in REPORT_UPDATED payload doesn't match parsed report"


# ---------------------------------------------------------------------------
# Tag parser: tag split across chunk boundaries
# ---------------------------------------------------------------------------

async def test_duct_artifact_tag_split_across_chunks():
    # Split "<duct_artifact>" across three chunks to stress the holdback buffer
    tag_parts = ["<duct_", "arti", f"fact>{_REPORT_HTML}</duct_artifact>"]
    stream = [
        _text_delta("Pre-tag text. "),
        *[_text_delta(p) for p in tag_parts],
        _message_stop(),
    ]
    report, _, events = await _run(stream)

    assert report is not None, "report not parsed when open tag was split across chunks"

    chunks = [e["text"] for e in events if e.get("event") == "agent_message_chunk"]
    combined = "".join(chunks)
    assert "Pre-tag text." in combined
    assert "<duct_" not in combined, "partial open tag leaked into chat stream"
    assert _REPORT_HTML not in combined, "JSON leaked into chat stream"


async def test_duct_artifact_close_tag_split():
    # Split "</duct_artifact>" across two chunks
    json_part = _REPORT_HTML
    stream = [
        _text_delta(f"<duct_artifact>{json_part}</duct_arti"),
        _text_delta("fact> Post-tag text."),
        _message_stop(),
    ]
    report, _, events = await _run(stream)
    assert report is not None, "report not parsed when close tag was split"

    chunks = [e["text"] for e in events if e.get("event") == "agent_message_chunk"]
    assert "Post-tag text." in "".join(chunks)


# ---------------------------------------------------------------------------
# Thinking chunks
# ---------------------------------------------------------------------------

async def test_thinking_chunks_forwarded():
    stream = [
        _thinking_delta("Let me think about the SEO issues..."),
        _thinking_delta(" Checking title length."),
        _text_delta(f"<duct_artifact>{_REPORT_HTML}</duct_artifact>"),
        _message_stop(),
    ]
    report, had_thinking, events = await _run(stream)

    assert had_thinking is True, "had_thinking should be True when thinking deltas fired"

    think_events = [e for e in events if e.get("event") == "thinking_chunk"]
    assert len(think_events) == 2
    combined_thinking = "".join(e["text"] for e in think_events)
    assert "Let me think about the SEO issues..." in combined_thinking
    assert "Checking title length." in combined_thinking


async def test_no_thinking_had_thinking_false():
    stream = [
        _text_delta(f"<duct_artifact>{_REPORT_HTML}</duct_artifact>"),
        _message_stop(),
    ]
    _, had_thinking, events = await _run(stream)

    assert had_thinking is False
    assert not any(e.get("event") == "thinking_chunk" for e in events)


# ---------------------------------------------------------------------------
# MESSAGE_STOP emitted
# ---------------------------------------------------------------------------

async def test_message_stop_emitted_after_turn():
    stream = [
        _text_delta(f"<duct_artifact>{_REPORT_HTML}</duct_artifact>"),
        _message_stop(),
    ]
    _, _, events = await _run(stream)

    stop_events = [e for e in events if e.get("event") == "message_stop"]
    assert len(stop_events) >= 1, "MESSAGE_STOP must be emitted"


# ---------------------------------------------------------------------------
# No raw JSON in AGENT_MESSAGE_CHUNK
# ---------------------------------------------------------------------------

async def test_text_outside_tag_streamed_not_json():
    prefix = "Here is my analysis:"
    suffix = "Review the findings above."
    stream = [
        _text_delta(prefix),
        _text_delta(f"<duct_artifact>{_REPORT_HTML}</duct_artifact>"),
        _text_delta(suffix),
        _message_stop(),
    ]
    _, _, events = await _run(stream)

    chunks = [e["text"] for e in events if e.get("event") == "agent_message_chunk"]
    combined = "".join(chunks)
    assert prefix in combined
    assert suffix in combined
    assert _REPORT_HTML not in combined


# ---------------------------------------------------------------------------
# Session close terminates cleanly
# ---------------------------------------------------------------------------

async def test_session_close_terminates_cleanly():
    """close_session() in the emit callback must allow run_synthesis() to return."""
    stream = [
        _text_delta(f"<duct_artifact>{_REPORT_HTML}</duct_artifact>"),
        _message_stop(),
    ]
    # close_on_report=True is the default — _run() already tests this
    report, _, _ = await _run(stream, close_on_report=True)
    assert report is not None


# ---------------------------------------------------------------------------
# <audit_report_update> in a second chat turn
# ---------------------------------------------------------------------------


async def test_audit_report_update_in_chat_turn():
    """
    The SDK yields a single continuous stream across all turns.
    Turn 1 produces <duct_artifact> → REPORT_UPDATED v1.
    Turn 2 produces <audit_report_update> → REPORT_UPDATED v2.
    """
    # Combined stream: initial report then, after message_stop, an update block.
    # close_session() is called when v2 fires, which puts None in chat_queue
    # and allows message_gen to exit so run_synthesis() returns.
    stream = [
        _text_delta(f"<duct_artifact>{_REPORT_HTML}</duct_artifact>"),
        _message_stop(),
        _text_delta(f"Here is the refreshed report. <audit_report_update>{_REPORT_V2_HTML}</audit_report_update>"),
        _message_stop(),
    ]

    from agents.audit.schema import AuditBusinessContext
    from agents.audit.v3.runner import close_session, create_audit_session, run_synthesis
    from agents.models import Provider

    session_id = "unit-update-test"
    create_audit_session(session_id)
    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)
        if event.get("event") == "report_updated" and event.get("version_id") == 2:
            close_session(session_id)

    with patch("claude_agent_sdk.ClaudeSDKClient", return_value=_make_mock_sdk(stream)):
        report, _ = await asyncio.wait_for(
            run_synthesis(
                session_id=session_id,
                crawl_result=_make_crawl_result(),
                business_context=AuditBusinessContext(),
                model_str="claude-haiku-4-5-20251001",
                api_key="test-key",
                provider=Provider.ANTHROPIC,
                emit=collect,
            ),
            timeout=10,
        )

    close_session(session_id)

    updates = [e for e in events if e.get("event") == "report_updated"]
    assert len(updates) >= 2, f"expected at least 2 REPORT_UPDATED, got {len(updates)}"

    v2 = next((e for e in updates if e.get("version_id") == 2), None)
    assert v2 is not None, "REPORT_UPDATED version_id=2 never fired"
    assert "<html" in v2["payload"]["html_report"], "v2 html_report should be HTML"
    assert "Updated" in v2["payload"]["html_report"]


# ---------------------------------------------------------------------------
# SDK plumbing tests — real ClaudeAgentOptions, no mocking, no API key
#
# These catch a class of bug the mocked tests can't see: invalid option values
# that only fail when the SDK actually builds the CLI command or spawns the
# subprocess.  Both the ThinkingConfigAdaptive() empty-dict bug and the
# sandbox-causes-exit-1 bug were invisible to mocked tests but would have been
# caught here.
# ---------------------------------------------------------------------------

def test_sdk_options_build_valid_cli_command():
    """ClaudeAgentOptions.thinking and other options must produce a valid CLI command.

    Calls _build_command() on the real SubprocessCLITransport (no subprocess
    spawned) and asserts the expected flags are present.  Any KeyError or
    AttributeError from bad option values (e.g. ThinkingConfigAdaptive() with
    no args producing {}) will surface here.
    """
    import asyncio
    import anyio
    from claude_agent_sdk import ClaudeAgentOptions
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

    opts = ClaudeAgentOptions(
        model="claude-sonnet-4-6",
        permission_mode="dontAsk",
        allowed_tools=["AskUserQuestion", "TodoWrite"],
        max_turns=60,
        system_prompt="test",
        include_partial_messages=True,
        thinking={"type": "adaptive"},   # must NOT be ThinkingConfigAdaptive()
        env={"ANTHROPIC_API_KEY": "test-key"},
        setting_sources=[],
        # sandbox intentionally omitted
    )

    transport = SubprocessCLITransport("test", opts)

    async def _get_cmd():
        cli = await anyio.to_thread.run_sync(transport._find_cli)
        transport._cli_path = cli
        return transport._build_command()

    cmd = asyncio.run(_get_cmd())

    # --thinking adaptive must be present
    assert "--thinking" in cmd, f"--thinking flag missing from command: {cmd}"
    idx = cmd.index("--thinking")
    assert cmd[idx + 1] == "adaptive", \
        f"--thinking value should be 'adaptive', got {cmd[idx + 1]!r}"

    # --setting-sources= (empty) must disable user settings
    assert any("setting-sources" in a for a in cmd), \
        "--setting-sources flag missing"

    # sandbox must NOT be in the --settings JSON (we removed it)
    settings_flags = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--settings"]
    for s in settings_flags:
        parsed = json.loads(s)
        assert "sandbox" not in parsed, \
            f"sandbox should not be in --settings but found: {s}"

    # permission-mode dontAsk
    assert "--permission-mode" in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"


async def test_sdk_subprocess_starts_and_responds():
    """The claude CLI subprocess must start cleanly and respond to the initialize handshake.

    This test actually spawns the subprocess (no API call — just the control
    protocol handshake) and asserts it replies with subtype=success.  It will
    catch any startup failure that causes exit code 1 before the handshake
    completes (e.g. sandbox misconfiguration, bad CLI flags).
    """
    import json as _json
    import subprocess
    import shutil
    import os
    from agents.audit.schema import AuditReport
    from agents.audit.prompts import build_unified_system_prompt

    cli = shutil.which("claude")
    if not cli:
        pytest.skip("claude CLI not found in PATH")

    env = dict(os.environ)
    env["CLAUDE_CODE_ENTRYPOINT"] = "sdk-py"
    env["CLAUDE_AGENT_SDK_VERSION"] = "0.1.81"
    env.pop("CLAUDECODE", None)

    cmd = [
        cli,
        "--output-format", "stream-json", "--verbose",
        "--system-prompt", build_unified_system_prompt(),
        "--allowedTools", "AskUserQuestion,TodoWrite",
        "--max-turns", "60",
        "--model", "claude-sonnet-4-6",
        "--permission-prompt-tool", "stdio",
        "--permission-mode", "dontAsk",
        "--include-partial-messages",
        "--thinking", "adaptive",
        "--json-schema", _json.dumps(AuditReport.model_json_schema()),
        "--input-format", "stream-json",
        "--setting-sources=",
        # no --settings (no sandbox)
    ]

    init_req = _json.dumps({
        "type": "control_request",
        "request_id": "req_smoke_1",
        "request": {"subtype": "initialize", "hooks": None},
    }) + "\n"

    result = subprocess.run(
        cmd,
        input=init_req.encode(),
        capture_output=True,
        timeout=15,
        env=env,
    )

    assert result.returncode == 0, (
        f"claude subprocess exited with code {result.returncode}.\n"
        f"stderr: {result.stderr.decode()[:500] or '(empty)'}\n"
        f"stdout: {result.stdout.decode()[:200] or '(empty)'}"
    )

    first_line = result.stdout.decode().split("\n")[0]
    assert first_line, "subprocess produced no stdout"
    msg = _json.loads(first_line)
    assert msg.get("type") == "control_response", \
        f"expected control_response, got: {msg}"
    assert msg.get("response", {}).get("subtype") == "success", \
        f"initialize handshake failed: {msg}"
