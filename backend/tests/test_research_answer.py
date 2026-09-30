"""The enrichment passes' research loop picks the answer shape the model accepts.

Opus 5.5 is the Heavy rung on Claude and the audit's competitor research runs
on it. A ``ToolStrategy`` answer forces ``tool_choice``, which Opus 5.5, Sonnet
5.5 and Fable 5.1 refuse with a 400 — so on those models every audit would lose
its research to local signals, all tests green, unless the loop asks another way.
"""

from __future__ import annotations

from types import SimpleNamespace

from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage
from pydantic import BaseModel

import agents.core.research as research


class _Answer(BaseModel):
    competitors: list[str] = []


class _RecordingAgent:
    def __init__(self, result: dict) -> None:
        self.kwargs: dict = {}
        self._result = result

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return self

    async def ainvoke(self, _state, _config=None):
        return self._result


def _patch(monkeypatch, result: dict) -> tuple[_RecordingAgent, list]:
    agent = _RecordingAgent(result)
    monkeypatch.setattr("langchain.agents.create_agent", agent)
    extracted: list = []

    class _Extractor:
        async def ainvoke(self, messages):
            extracted.append(messages)
            return _Answer(competitors=["acme.com"])

    monkeypatch.setattr(research, "structured_output", lambda _llm, _schema: _Extractor())
    return agent, extracted


async def test_a_model_that_takes_a_forced_tool_call_answers_through_the_tool(monkeypatch):
    agent, extracted = _patch(monkeypatch, {"structured_response": _Answer(competitors=["x.com"])})

    found = await research.research_answer(
        "prompt", SimpleNamespace(model_name="gpt-6.1-sol"), [], _Answer, recursion_limit=10,
    )

    assert isinstance(agent.kwargs["response_format"], ToolStrategy)
    assert found == _Answer(competitors=["x.com"])
    assert not extracted, "one call when one call works"


async def test_a_model_that_refuses_one_runs_free_and_is_asked_after(monkeypatch):
    agent, extracted = _patch(
        monkeypatch, {"messages": [AIMessage(content="Acme leads on pricing pages.")]},
    )

    found = await research.research_answer(
        "Research acme's market.", SimpleNamespace(model="claude-opus-5-5"), [], _Answer,
        recursion_limit=10,
    )

    assert agent.kwargs["response_format"] is None, "nothing may force tool_choice"
    assert found == _Answer(competitors=["acme.com"])
    sent = extracted[0][0].content
    assert "Research acme's market." in sent and "Acme leads on pricing pages." in sent


async def test_a_free_loop_that_wrote_nothing_has_no_answer(monkeypatch):
    _agent, extracted = _patch(monkeypatch, {"messages": [AIMessage(content="")]})

    found = await research.research_answer(
        "prompt", SimpleNamespace(model="claude-sonnet-5-5"), [], _Answer, recursion_limit=10,
    )

    assert found is None
    assert not extracted, "no call to extract an answer from nothing"
