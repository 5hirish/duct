"""scripts/session_bundle.py — the pull the session-audit skill runs.

The database half is plain SQLModel reads; what is worth holding is the
rendering (a reviewer reads transcript.md before anything else), the tool
pairing (a result must land beside its call, whatever the seq gap), the
redaction on the way to disk, and the prompt fingerprint check (a finding
against a prompt that has since changed is a finding against history).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "session_bundle.py"
spec = importlib.util.spec_from_file_location("session_bundle", SCRIPT)
session_bundle = importlib.util.module_from_spec(spec)
sys.modules["session_bundle"] = session_bundle
spec.loader.exec_module(session_bundle)


def _bundle(prompt_sha: str = "") -> dict:
    events = [
        {"seq": 1, "kind": "context", "created_at": "t", "data": {
            "agent_type": "insights", "provider": "anthropic", "model": "claude-sonnet-5", "thinking": "",
            "system_prompt_sha256": prompt_sha, "system_prompt_chars": 4200, "resume": False,
            "turn": "…", "blocks": {"business_context": "<business_context>Acme</business_context>",
                                     "user_context": "", "memory": "", "data_sources": "",
                                     "artifact_format": "markdown", "autonomy": "ask", "compress": True},
        }},
        {"seq": 2, "kind": "user", "created_at": "t", "data": {"content": "why did CPA jump?"}},
        {"seq": 3, "kind": "tool_use", "created_at": "t", "data": {
            "name": "FetchData", "tool_use_id": "t1", "input": {"entity_id": "ga4_traffic"}}},
        {"seq": 4, "kind": "thinking", "created_at": "t", "data": {"text": "check ads"}},
        {"seq": 5, "kind": "tool_result", "created_at": "t", "data": {
            "name": "FetchData", "tool_use_id": "t1", "is_error": False,
            "output": json.dumps({"status": "ok", "data": "sessions,users\n10,8", "note": "token sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyz"})}},
        {"seq": 6, "kind": "assistant", "created_at": "t", "data": {"text": "One campaign."}},
    ]
    return {
        "bundled_at": "2026-09-19T00:00:00+02:00",
        "repo_sha": "abc123def456",
        "conversation": {"id": "c1", "agent_type": "insights", "mode": "", "title": "CPA", "status": "active",
                         "run_status": "idle", "run_error": None, "summary": "", "input_tokens": 0,
                         "output_tokens": 0, "meta": {}, "created_at": "t", "last_active_at": "t"},
        "project": {"id": "p1", "name": "Acme"},
        "profile": None,
        "events": events,
        "artifacts": [{"id": "a1", "group_id": "g1", "version": 2, "slug": "growth-brief", "agent_type": "insights",
                       "kind": "brief", "content_type": "text/markdown", "title": "Growth brief", "filename": "",
                       "size_bytes": 12, "summary": "", "created_at": "t", "content": "# Brief\n"}],
        "memories_written": [{"kind": "fact", "title": "CPA target", "body": "$40"}],
        "memories_active": [],
        "change_sets": [],
        "usage": [{"provider": "anthropic", "model": "claude-sonnet-5", "tier": "", "scope": "thread",
                   "input_tokens": 1000, "output_tokens": 200, "cache_read_tokens": 800,
                   "cache_creation_tokens": 0, "cost_micros": 12500, "created_at": "t"}],
    }


def test_tool_calls_are_paired_with_their_results_across_the_gap():
    [call] = session_bundle.pair_tools(_bundle()["events"])
    assert call["seq"] == 3 and call["result_seq"] == 5
    assert call["input"] == {"entity_id": "ga4_traffic"}
    assert json.loads(call["output"])["status"] == "ok"


def test_transcript_reads_context_first_then_the_turns_with_tools_collapsed():
    text = session_bundle.render_transcript(_bundle())
    assert text.index("Context the model read") < text.index("## [2] User") < text.index("## [6] Assistant")
    assert "FetchData" in text and 'tools/0003-FetchData.json' in text
    assert "sessions,users" not in text, "the transcript names a tool call; the payload lives in tools/"
    assert "artifacts/growth-brief-v2.md" in text
    assert "$0.0125" in text and "1,000 in / 200 out" in text
    assert "CPA target" in text


def test_the_bundle_on_disk_is_redacted(tmp_path):
    files = session_bundle.write_bundle(_bundle(), tmp_path)
    names = sorted(str(p.relative_to(tmp_path)) for p in files)
    assert names == ["artifacts/growth-brief-v2.md", "bundle.json", "tools/0003-FetchData.json", "transcript.md"]
    tool = (tmp_path / "tools" / "0003-FetchData.json").read_text()
    assert "sk-ant-api03" not in tool and "redacted" in tool
    assert "sk-ant-api03" not in (tmp_path / "bundle.json").read_text()


def test_prompt_check_knows_whether_the_prompt_has_moved():
    from agents.insights.prompts.autonomous import CAPABILITIES_PHASE_3, build_insights_system_prompt

    current = hashlib.sha256(
        build_insights_system_prompt(capabilities=CAPABILITIES_PHASE_3, can_execute=False).encode()
    ).hexdigest()
    assert "ran on this checkout's prompt" in session_bundle.prompt_check(_bundle(current))
    assert "CHANGED" in session_bundle.prompt_check(_bundle("0" * 64))
    old = _bundle()
    old["events"] = old["events"][1:]
    assert "predates" in session_bundle.prompt_check(old)
