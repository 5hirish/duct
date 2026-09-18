"""OpenTelemetry GenAI spans — the observability port (agents/core/ports).

Why this exists
---------------
**The harness gives us nothing.** LangChain's own tracing goes to LangSmith,
which is a second vendor and a second place to look. The one harness that did
carry OTel built in was the Claude Agent SDK — its subprocess inherited Sentry's
OTLP endpoint from an env var — and it was removed, taking that plumbing with
it. "Observability comes free with the harness" was never true of the harness we
kept, which is exactly when it mattered most.

So the port is a vendor-neutral one: emit the OpenTelemetry GenAI semantic
conventions ourselves, from our side of the boundary. Whatever harness runs
underneath, the spans look the same, and they land wherever OTLP is pointed
rather than wherever the framework vendor prefers.

Where the spans go
------------------
Nowhere, until ``configure_tracing`` installs a provider. For a year the spans
below were opened faithfully and dropped on the floor: the API package's
``get_tracer`` hands back a no-op unless something has called
``set_tracer_provider``, and nothing had. The launch config even set an
``OTEL_ENDPOINT`` that no code read. ``server.py`` now calls
``configure_tracing`` with ``OTEL_EXPORTER_OTLP_ENDPOINT`` — the standard
variable, so a Phoenix on ``:6006`` locally and any OTLP collector in
production are the same one-line change — and leaves tracing off when it is
unset, which is what every test and every self-host build gets.

Stability, stated honestly
--------------------------
The GenAI conventions are **not stable**. ``gen_ai.client`` spans have settled
but ``gen_ai.agent`` spans remain experimental, and in June 2026 the whole
``gen_ai.*`` namespace moved out of the main semantic-conventions repo into its
own. The Python package still ships them under
``opentelemetry.semconv._incubating`` — a private module.

The response is to pin rather than avoid: the attribute names below are
*our* copy of the convention, pinned to ``SEMCONV_VERSION``, not an import from
a private module that may move. ``tests/test_telemetry.py`` diffs our copy
against the installed package, so drift surfaces as a failing test instead of
as silently wrong telemetry.

Dependency note
---------------
``opentelemetry-api`` is a declared dependency. It used to arrive transitively
via ``google-adk``; declaring it is what let the v2/ADK engine be removed without
silently stopping the spans. The import is still guarded and every entry point
degrades to a no-op, because telemetry must never be the reason a run fails.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

# The semantic-conventions package version these names were verified against.
# Bump only together with a run of tests/test_telemetry.py.
SEMCONV_VERSION = "0.62b1"

# --- Attribute names (our pinned copy of the convention) -------------------
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_SYSTEM = "gen_ai.system"  # predecessor of provider.name; still emitted by many backends
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"
GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS = "gen_ai.usage.cache_creation.input_tokens"
GEN_AI_CONVERSATION_ID = "gen_ai.conversation.id"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_TOOL_CALL_ID = "gen_ai.tool.call.id"
GEN_AI_TOOL_TYPE = "gen_ai.tool.type"

# Not GenAI semconv: the OpenInference attribute Phoenix groups its trace view
# by (LLM / TOOL / AGENT columns, latency per kind). A plain string attribute,
# no dependency, ignored by any backend that does not know it — cheap enough
# to carry so the local trace UI is legible rather than a flat list of spans.
OPENINFERENCE_SPAN_KIND = "openinference.span.kind"
SPAN_KIND_LLM = "LLM"
SPAN_KIND_TOOL = "TOOL"
SPAN_KIND_AGENT = "AGENT"

# --- Operation names -------------------------------------------------------
OP_CHAT = "chat"
OP_EXECUTE_TOOL = "execute_tool"
OP_INVOKE_AGENT = "invoke_agent"

# What the exporter appends to a bare collector URL. Phoenix, the collector
# and Sentry all take traces at this path; a value that already ends in it is
# left alone so a full URL works too.
OTLP_TRACES_PATH = "/v1/traces"
SERVICE_NAME = "duct-backend"

# Duct's Provider values → the convention's provider vocabulary. OpenRouter is
# not in the enum (it is a gateway, not a model vendor); the convention's own
# guidance for that case is to record the gateway, which is what a reader needs
# to interpret latency and cost anyway.
_PROVIDER_NAMES = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google_genai": "gcp.gemini",
    "openrouter": "openrouter",
}


def _tracer() -> Any | None:
    """The OTel tracer, or None when OpenTelemetry is not installed.

    Import is deferred and guarded on purpose — see the dependency note above.
    """
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    return trace.get_tracer("duct.agents", SEMCONV_VERSION)


def configure_tracing(endpoint: str, *, environment: str = "") -> Any | None:
    """Install a tracer provider that ships spans to ``endpoint`` over OTLP/HTTP.

    Returns the provider, or None when ``endpoint`` is empty or the SDK is not
    installed — both mean "tracing off", and neither is an error: the spans
    above degrade to no-ops exactly as they always have. Batched export, so a
    burst of tool spans never blocks the event loop on the collector.

    Process-global and set-once by OpenTelemetry's design; a second call
    (a test module that installed its own in-memory provider first) logs and
    keeps the existing one rather than fighting it.
    """
    endpoint = (endpoint or "").strip()
    if not endpoint:
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning("telemetry: OTEL_EXPORTER_OTLP_ENDPOINT is set but the OTel SDK is not installed")
        return None

    url = endpoint.rstrip("/")
    if not url.endswith(OTLP_TRACES_PATH):
        url += OTLP_TRACES_PATH
    attributes = {"service.name": SERVICE_NAME}
    if environment:
        attributes["deployment.environment"] = environment
    provider = TracerProvider(resource=Resource.create(attributes))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=url)))
    trace.set_tracer_provider(provider)
    logger.info("telemetry: exporting agent spans to %s", url)
    return provider


class _NoopSpan:
    """Stands in for a span so callers never branch on whether OTel is present."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: D102
        return None

    def record_exception(self, exc: BaseException) -> None:  # noqa: D102
        return None


def _set(span: Any, key: str, value: Any) -> None:
    if value is None or value == "":
        return
    try:
        span.set_attribute(key, value)
    except Exception:  # pragma: no cover - telemetry must never break a run
        logger.debug("telemetry: could not set %s", key, exc_info=True)


@contextmanager
def model_span(
    *,
    provider: str,
    model: str,
    operation: str = OP_CHAT,
    temperature: float | None = None,
    conversation_id: str = "",
    agent_name: str = "",
) -> Iterator[Any]:
    """Span around one model call.

    Named ``"{operation} {model}"`` per the convention, so traces group by
    operation and model without a custom query.
    """
    tracer = _tracer()
    if tracer is None:
        yield _NoopSpan()
        return

    provider_name = _PROVIDER_NAMES.get(provider, provider)
    with tracer.start_as_current_span(f"{operation} {model}") as span:
        _set(
            span,
            OPENINFERENCE_SPAN_KIND,
            SPAN_KIND_AGENT if operation == OP_INVOKE_AGENT else SPAN_KIND_LLM,
        )
        _set(span, GEN_AI_OPERATION_NAME, operation)
        _set(span, GEN_AI_PROVIDER_NAME, provider_name)
        # Emitted alongside provider.name because the rename is mid-flight and
        # backends disagree on which one they read.
        _set(span, GEN_AI_SYSTEM, provider_name)
        _set(span, GEN_AI_REQUEST_MODEL, model)
        _set(span, GEN_AI_REQUEST_TEMPERATURE, temperature)
        _set(span, GEN_AI_CONVERSATION_ID, conversation_id)
        _set(span, GEN_AI_AGENT_NAME, agent_name)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            raise


@contextmanager
def tool_span(
    *,
    tool_name: str,
    tool_call_id: str = "",
    agent_name: str = "",
    tool_type: str = "function",
) -> Iterator[Any]:
    """Span around one tool execution.

    Placed on *our* side of the tool binder, so the same span appears whether
    the tool was invoked through LangChain or the Claude Agent SDK. That is the
    ports design paying off in observability: one shape, any harness.
    """
    tracer = _tracer()
    if tracer is None:
        yield _NoopSpan()
        return

    with tracer.start_as_current_span(f"{OP_EXECUTE_TOOL} {tool_name}") as span:
        _set(span, OPENINFERENCE_SPAN_KIND, SPAN_KIND_TOOL)
        _set(span, GEN_AI_OPERATION_NAME, OP_EXECUTE_TOOL)
        _set(span, GEN_AI_TOOL_NAME, tool_name)
        _set(span, GEN_AI_TOOL_CALL_ID, tool_call_id)
        _set(span, GEN_AI_TOOL_TYPE, tool_type)
        _set(span, GEN_AI_AGENT_NAME, agent_name)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            raise


def record_usage(
    span: Any,
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    cache_creation_tokens: int | None = None,
    response_model: str = "",
    finish_reason: str = "",
) -> None:
    """Attach token usage to a model span. Safe on a no-op span."""
    _set(span, GEN_AI_USAGE_INPUT_TOKENS, input_tokens)
    _set(span, GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens)
    _set(span, GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS, cache_read_tokens)
    _set(span, GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS, cache_creation_tokens)
    _set(span, GEN_AI_RESPONSE_MODEL, response_model)
    if finish_reason:
        _set(span, GEN_AI_RESPONSE_FINISH_REASONS, [finish_reason])
