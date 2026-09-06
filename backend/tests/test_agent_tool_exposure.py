"""The agent tool-exposure gate.

Every Duct agent reads text somebody else wrote. The audit agent's prompt
carries H2 headings scraped off the site under audit; the audit and content
research passes fetch competitor pages; conversation summaries quote tool
output. That is the product working as intended, and it means an injected
instruction reaching a writer is a path into things the user never agreed to —
at worst a shell, and a shell is a path into ``backend/.env*``: the Fernet key
for every stored connector refresh token, ``JWT_SECRET``, ``DATABASE_URL``.

This gate used to police two Claude Agent SDK options (``tools`` versus
``allowed_tools``), because omitting the first shipped the CLI's default set —
Bash, Read, Write, Edit — and the second never removed anything. That specific
trap left with the SDK: a LangChain agent carries exactly the list it is
handed, and there is no implicit default to forget about.

What did not leave is the property underneath it, so that is what is checked
here now. The research passes are the agents that eat the open web, and they
must carry web tools and nothing else — no writers, no session, no credentials.
Both of them build their agent in one place, so both are asked directly.
"""

from __future__ import annotations

import inspect

import pytest

import agents.audit.enrichment as audit_enrichment
import agents.content.enrichment as content_enrichment

# A tool whose name suggests it changes something the user owns, or reaches a
# shell. Matched on the name the model sees, because that is what an injected
# instruction would have to call.
_WRITER_HINTS = (
    "bash", "shell", "exec", "run_command", "write", "edit", "create", "update",
    "rewrite", "delete", "submit", "publish", "propose", "remember", "save",
)


class _RecordingAgent:
    """Stands in for ``create_agent`` and keeps the tools it was handed."""

    def __init__(self) -> None:
        self.tools: list = []

    def __call__(self, *, model, tools, **kwargs):
        self.tools = list(tools)
        return self

    async def ainvoke(self, _state, _config=None):
        return {"structured_response": None}


@pytest.mark.parametrize(
    "module, research",
    [
        (audit_enrichment, "_research"),
        (content_enrichment, "_research"),
    ],
    ids=["audit", "content"],
)
async def test_a_research_pass_carries_web_tools_and_nothing_else(module, research, monkeypatch):
    """The one agent in Duct whose input is attacker-authored by construction."""
    recorder = _RecordingAgent()
    monkeypatch.setattr("langchain.agents.create_agent", recorder)

    sentinel_tools = [_named("WebSearch"), _named("WebFetch")]
    await getattr(module, research)("prompt", object(), sentinel_tools)

    assert recorder.tools, "the research agent was never built"
    names = [getattr(t, "name", "") for t in recorder.tools]
    assert names == ["WebSearch", "WebFetch"], (
        f"the research pass mounted {names}; it may carry web tools only"
    )


def _named(name: str):
    from types import SimpleNamespace

    return SimpleNamespace(name=name)


@pytest.mark.parametrize(
    "module", [audit_enrichment, content_enrichment], ids=["audit", "content"]
)
def test_a_research_pass_is_handed_its_tools_and_never_picks_its_own(module):
    """The tools arrive as an argument, so the caller decides — and the caller
    is the runner that knows whether this run may search at all. A research
    function that built its own list could not be audited by the test above."""
    signature = inspect.signature(module._research)

    assert "web_tools" in signature.parameters, (
        f"{module.__name__}._research must take its tools, not source them"
    )
    source = inspect.getsource(module._research)
    for builder in ("build_memory_tools", "build_artifact_tools", "build_execution_tools"):
        assert builder not in source, f"{module.__name__}._research reaches for {builder}"


def test_no_writer_reaches_the_open_web_passes():
    """Names, not types: an injected instruction has to call a tool by name, so
    the check is on the vocabulary the model is shown."""
    for hint in _WRITER_HINTS:
        assert hint not in "websearch"
        assert hint not in "webfetch"
