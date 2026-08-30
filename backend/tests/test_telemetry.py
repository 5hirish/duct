"""OpenTelemetry GenAI conventions — pin, drift check, and behaviour.

``agents/core/telemetry.py`` keeps its *own* copy of the GenAI attribute names
rather than importing them from ``opentelemetry.semconv._incubating``, because
that module is private and the conventions are still experimental — in June
2026 the whole ``gen_ai.*`` namespace moved into its own repository.

A pinned copy is only safe if drift is loud, which is what this file is for.
"""

from __future__ import annotations

import pytest

from agents.core import telemetry as t

pytest.importorskip("opentelemetry.sdk", reason="opentelemetry-sdk not installed")

from opentelemetry import trace  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

_exporter = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def _tracing():
    """Install an in-memory exporter so spans are inspectable.

    The tracer provider is process-global and set-once in OpenTelemetry, so
    this is deliberately module-scoped and tolerant of an existing provider.
    """
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(_exporter))
    try:
        trace.set_tracer_provider(provider)
    except Exception:  # pragma: no cover - already set by another module
        pass
    yield
    _exporter.clear()


@pytest.fixture(autouse=True)
def _clear_spans():
    _exporter.clear()
    yield


def _spans():
    return list(_exporter.get_finished_spans())


# ---------------------------------------------------------------------------
# Drift against the installed convention
# ---------------------------------------------------------------------------

def test_pinned_attribute_names_match_the_installed_semconv():
    """Our copy of the convention must equal the package's.

    If this fails, the conventions moved. Read the diff, decide whether to
    follow, then bump SEMCONV_VERSION — do not silently re-pin.
    """
    incubating = pytest.importorskip(
        "opentelemetry.semconv._incubating.attributes.gen_ai_attributes",
        reason="semconv incubating attributes not available",
    )

    ours = {
        name: value
        for name, value in vars(t).items()
        if name.startswith("GEN_AI_") and isinstance(value, str)
    }
    assert ours, "telemetry.py defines no GEN_AI_* constants"

    mismatched = {
        name: (value, getattr(incubating, name))
        for name, value in ours.items()
        if hasattr(incubating, name) and getattr(incubating, name) != value
    }
    assert not mismatched, (
        "Pinned GenAI attribute names drifted from the installed semantic "
        f"conventions ({t.SEMCONV_VERSION}):\n"
        + "\n".join(f"  {k}: ours={v[0]!r} theirs={v[1]!r}" for k, v in sorted(mismatched.items()))
    )

    unknown = sorted(name for name in ours if not hasattr(incubating, name))
    assert not unknown, f"GEN_AI_* constants not present in the convention at all: {unknown}"


def test_pinned_operation_names_are_real_convention_values():
    incubating = pytest.importorskip(
        "opentelemetry.semconv._incubating.attributes.gen_ai_attributes",
        reason="semconv incubating attributes not available",
    )
    valid = {m.value for m in incubating.GenAiOperationNameValues}
    for op in (t.OP_CHAT, t.OP_EXECUTE_TOOL, t.OP_INVOKE_AGENT):
        assert op in valid, f"{op!r} is not a GenAI operation name"


# ---------------------------------------------------------------------------
# Span shape
# ---------------------------------------------------------------------------

def test_model_span_carries_the_convention_attributes():
    with t.model_span(
        provider="anthropic", model="claude-sonnet-5", temperature=0.7,
        conversation_id="conv-1", agent_name="audit-v1",
    ) as span:
        t.record_usage(span, input_tokens=120, output_tokens=45, response_model="claude-sonnet-5")

    (s,) = _spans()
    assert s.name == "chat claude-sonnet-5", "span name must be '{operation} {model}'"
    a = s.attributes
    assert a[t.GEN_AI_OPERATION_NAME] == "chat"
    assert a[t.GEN_AI_PROVIDER_NAME] == "anthropic"
    assert a[t.GEN_AI_SYSTEM] == "anthropic"  # emitted too; the rename is mid-flight
    assert a[t.GEN_AI_REQUEST_MODEL] == "claude-sonnet-5"
    assert a[t.GEN_AI_REQUEST_TEMPERATURE] == 0.7
    assert a[t.GEN_AI_CONVERSATION_ID] == "conv-1"
    assert a[t.GEN_AI_USAGE_INPUT_TOKENS] == 120
    assert a[t.GEN_AI_USAGE_OUTPUT_TOKENS] == 45


def test_google_provider_maps_to_the_convention_vocabulary():
    """Duct's provider values are ours; the span must speak the convention's."""
    with t.model_span(provider="google_genai", model="gemini-2.5-flash"):
        pass
    (s,) = _spans()
    assert s.attributes[t.GEN_AI_PROVIDER_NAME] == "gcp.gemini"


def test_openrouter_is_recorded_as_the_gateway_it_is():
    """OpenRouter is not in the convention's vendor enum — it is a gateway.
    Recording it is still what a reader needs to interpret latency and cost."""
    with t.model_span(provider="openrouter", model="z-ai/glm-4.6"):
        pass
    (s,) = _spans()
    assert s.attributes[t.GEN_AI_PROVIDER_NAME] == "openrouter"
    assert s.name == "chat z-ai/glm-4.6"


def test_tool_span_shape():
    with t.tool_span(tool_name="RememberFact", tool_call_id="call-9", agent_name="audit_seo"):
        pass
    (s,) = _spans()
    assert s.name == "execute_tool RememberFact"
    assert s.attributes[t.GEN_AI_OPERATION_NAME] == "execute_tool"
    assert s.attributes[t.GEN_AI_TOOL_NAME] == "RememberFact"
    assert s.attributes[t.GEN_AI_TOOL_CALL_ID] == "call-9"


def test_empty_attributes_are_omitted_not_blank():
    """A blank attribute is worse than a missing one — it looks like data."""
    with t.model_span(provider="anthropic", model="claude-sonnet-5"):
        pass
    (s,) = _spans()
    assert t.GEN_AI_CONVERSATION_ID not in s.attributes
    assert t.GEN_AI_REQUEST_TEMPERATURE not in s.attributes


# ---------------------------------------------------------------------------
# Telemetry must never break a run
# ---------------------------------------------------------------------------

def test_exception_is_recorded_and_re_raised():
    with pytest.raises(ValueError):
        with t.model_span(provider="anthropic", model="m"):
            raise ValueError("boom")
    (s,) = _spans()
    assert s.events, "the exception should be recorded on the span"


def test_degrades_to_noop_without_opentelemetry(monkeypatch):
    """opentelemetry-api is a transitive dependency today (via google-adk).
    If that edge disappears, spans must vanish — not the agent run."""
    monkeypatch.setattr(t, "_tracer", lambda: None)
    with t.model_span(provider="anthropic", model="m") as span:
        t.record_usage(span, input_tokens=1, output_tokens=2)
    with t.tool_span(tool_name="X"):
        pass
    assert _spans() == []
