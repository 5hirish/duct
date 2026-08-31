"""The harness boundary gate.

Duct rents an agent harness; it does not marry one (see
``agents/core/ports/__init__.py``). That only stays true if framework imports
are confined to adapters, so this test makes the boundary a property of the
codebase rather than an intention in a document.

It fails in two directions:

  * a framework import appears in a file that is not a declared adapter, or
  * a declared adapter no longer imports a framework (the allowlist has gone
    stale and is now blessing files for nothing).

Adding a path to ``ADAPTERS`` is a deliberate architectural act. It is not the
fix for a failing test — the usual fix is to move the framework-touching lines
into an existing binder and leave the domain function plain.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from agents.core.events import AG_UI_EVENT, AG_UI_EVENT_KIND, AgentEvent, EventKind

BACKEND = pathlib.Path(__file__).resolve().parent.parent

# Package prefixes that constitute "an agent framework" for boundary purposes.
# Matched on the top-level module, so `langchain_core` and `langchain_openai`
# count as `langchain` — the distribution split is not a boundary.
FRAMEWORK_PREFIXES = ("langchain", "langgraph", "deepagents", "claude_agent_sdk")
FRAMEWORK_DOTTED = ("google.adk",)

# Directories that hold first-party application code.
SOURCE_ROOTS = ("agents", "routes", "service", "models", "utils")

# ---------------------------------------------------------------------------
# The allowlist: every file permitted to import an agent framework, and why.
# ---------------------------------------------------------------------------

ADAPTERS: dict[str, str] = {
    # -- Harness runners. The middle of a runner is allowed to be harness-shaped;
    #    that is the whole point of the ports design.
    "agents/audit/v1/runner.py":            "LangChain runner (create_agent)",
    "agents/audit/v3/runner.py":            "Claude Agent SDK runner",
    "agents/content/v3/runner.py":          "Claude Agent SDK runner",
    "agents/insights/v1/agent.py":          "LangChain synthesis (init_chat_model)",
    "agents/insights/v1/runner.py":         "deepagents runner — autonomous insights session",
    "agents/insights/v3/runner.py":         "Claude Agent SDK runner",
    "agents/insights/v2/agents.py":         "Google ADK runner — frozen engine",
    "agents/insights/v2/runner.py":         "Google ADK runner — frozen engine",

    # -- Shared LangChain adapter: the model-transport + events-out ports for
    #    every V1 runner. Extracted from agents/audit/v1/runner.py on the second
    #    consumer (insights), per the ports rule.
    "agents/core/lc.py":                    "LangChain adapter: resolve_chat_model + stream_agent",

    # -- Tool binders. Domain logic stays plain; these wrap it per harness.
    "agents/core/connector_tools.py":       "LangChain binder: connector discovery tools",
    "agents/core/memory_tools.py":          "binder pair: build_memory_tools_lc / _sdk",
    "agents/audit/v1/tools.py":             "LangChain tool binder",
    "agents/audit/tools.py":                "Claude Agent SDK tool binder (duct_crawl)",
    "agents/content/tools.py":              "Claude Agent SDK tool binder (duct_content)",
    "agents/insights/tools.py":             "LangChain StructuredTool binder",
    "agents/insights/data_tools.py":        "LangChain binder: FetchData + connector notes",
    "agents/tools/execution_tools.py":      "Claude Agent SDK tool binder (staged execution)",

    # -- Named harness shims.
    "agents/core/claude_sdk.py":            "Claude Agent SDK subprocess survival",
    "agents/core/stream.py":                "pump_stream_event — SDK message decode",
    "agents/sandbox.py":                    "Claude Agent SDK sandbox options",
    "agents/content/subagents/draft_post.py":     "Claude Agent SDK AgentDefinition",
    "agents/content/subagents/research_pillar.py": "Claude Agent SDK AgentDefinition",

    # -- Content/audit enrichment + persistence run their own one-shot model
    #    calls through the SDK.
    "agents/audit/enrichment.py":           "one-shot SDK call",
    "agents/content/enrichment.py":         "one-shot SDK call",
    "agents/content/persistence.py":        "SDK message shapes on resume",

    # -- Boundary debt. Allowed today, but these are the wrong layer: a route is
    #    transport and a service is domain, so neither should know a harness.
    #    Moving them behind a binder is the next boundary cleanup; until then
    #    they are listed here honestly rather than silently.
    "routes/chat.py":                       "DEBT — route imports LangChain directly",
    "service/artifact_store.py":            "DEBT — service imports claude_agent_sdk",
    "service/memory_consolidation.py":      "DEBT — service imports LangChain",
}

# Domain modules that must NEVER import a framework. These hold the durable
# assets — vocabulary, schemas, registries, prompt text — and they are what
# survives a harness swap. Listed explicitly so the guarantee is legible.
FRAMEWORK_FREE: tuple[str, ...] = (
    "agents/core/events.py",
    "agents/core/prompts.py",
    "agents/core/ports/__init__.py",
    "agents/core/telemetry.py",
    "agents/core/session.py",
    "agents/models.py",
    "agents/engines.py",
    "agents/audit/schema.py",
    "agents/audit/prompts.py",
    "agents/content/schema.py",
    "agents/content/prompts.py",
    "agents/insights/schema.py",
)


def _framework_of(module: str) -> str | None:
    top = module.split(".")[0]
    for prefix in FRAMEWORK_PREFIXES:
        if top == prefix or top.startswith(prefix + "_"):
            return prefix
    for dotted in FRAMEWORK_DOTTED:
        if module == dotted or module.startswith(dotted + "."):
            return dotted
    return None


def _frameworks_imported(path: pathlib.Path) -> set[str]:
    """Every framework imported by a file, including inside functions.

    Deferred imports are the common shape here (binders import their harness
    inside the build function), so an AST walk is required — a top-of-file scan
    would miss most of the real boundary.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (fw := _framework_of(alias.name)):
                    found.add(fw)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if (fw := _framework_of(node.module)):
                found.add(fw)
    return found


def _source_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in SOURCE_ROOTS:
        for path in sorted((BACKEND / root).rglob("*.py")):
            if "__pycache__" not in path.as_posix():
                files.append(path)
    return files


def _actual_importers() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for path in _source_files():
        if (fws := _frameworks_imported(path)):
            out[path.relative_to(BACKEND).as_posix()] = fws
    return out


def test_framework_imports_stay_in_adapters():
    """No agent-framework import outside the declared adapter set."""
    unexpected = {
        rel: sorted(fws)
        for rel, fws in _actual_importers().items()
        if rel not in ADAPTERS
    }
    assert not unexpected, (
        "Agent-framework imports found outside agents/core/ports' adapter set:\n"
        + "\n".join(f"  {rel}: {', '.join(fws)}" for rel, fws in sorted(unexpected.items()))
        + "\n\nKeep domain logic framework-free and put the framework call in a "
          "binder (see agents/core/memory_tools.py). Only add to ADAPTERS if this "
          "file is genuinely a new adapter."
    )


def test_allowlist_has_no_dead_entries():
    """Every allowlisted adapter still imports a framework.

    A stale entry silently widens the boundary, which is exactly the failure
    mode this gate exists to prevent.
    """
    actual = _actual_importers()
    dead = sorted(rel for rel in ADAPTERS if rel not in actual)
    assert not dead, (
        "ADAPTERS lists files that no longer import a framework — remove them:\n"
        + "\n".join(f"  {rel}" for rel in dead)
    )


@pytest.mark.parametrize("rel", FRAMEWORK_FREE)
def test_domain_modules_import_no_framework(rel: str):
    """The durable layer stays portable.

    These modules are what survives a harness swap. If one of them grows a
    framework import, the swap stops being cheap — which is the moment to
    notice, not later.
    """
    path = BACKEND / rel
    if not path.exists():
        pytest.skip(f"{rel} not in this checkout")
    found = _frameworks_imported(path)
    assert not found, f"{rel} must stay framework-free but imports: {sorted(found)}"


def test_ag_ui_map_is_exhaustive():
    """Every event has a declared AG-UI meaning.

    The map is the entire AG-UI adapter (agents/core/events.py). A missing
    entry means a new event would silently have no external meaning.
    """
    missing = sorted(e.name for e in AgentEvent if e not in AG_UI_EVENT)
    assert not missing, f"AgentEvent members missing from AG_UI_EVENT: {missing}"

    missing_kinds = sorted(k.name for k in EventKind if k not in AG_UI_EVENT_KIND)
    assert not missing_kinds, f"EventKind members missing from AG_UI_EVENT_KIND: {missing_kinds}"


# ---------------------------------------------------------------------------
# Frontend mirror parity — the events-out port has two sides
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "js_rel",
    [
        "app/src/lib/auditEvents.js",
        "app/src/lib/contentEvents.js",
        "app/src/lib/insightsEvents.js",
    ],
)
def test_frontend_event_mirrors_reference_real_backend_values(js_rel: str):
    """Every event string the frontend names must be one the backend can emit.

    ``LEGACY_*`` keys are exempt by design: they name wire values the backend
    has stopped emitting, kept so an app deployed ahead of the backend still
    renders. Everything else is a typo or a drift.
    """
    import re

    js_path = BACKEND.parent / js_rel
    if not js_path.exists():
        pytest.skip(f"{js_rel} not in this checkout")

    from agents.core.events import AgentStep

    valid = {e.value for e in AgentEvent} | {s.value for s in AgentStep}
    pairs = re.findall(r'([A-Z_0-9]+):\s*"([a-z_0-9]+)"', js_path.read_text())
    unknown = {v for k, v in pairs if not k.startswith("LEGACY_")} - valid
    assert not unknown, f"{js_rel} references unknown events/steps: {sorted(unknown)}"


@pytest.mark.parametrize(
    "js_rel",
    [
        "app/src/lib/auditEvents.js",
        "app/src/lib/contentEvents.js",
        "app/src/lib/insightsEvents.js",
    ],
)
def test_legacy_frontend_values_are_genuinely_retired(js_rel: str):
    """A LEGACY_* key must name a value the backend no longer emits.

    Otherwise the exemption above becomes a hole big enough to hide a real
    drift in.
    """
    import re

    js_path = BACKEND.parent / js_rel
    if not js_path.exists():
        pytest.skip(f"{js_rel} not in this checkout")

    live = {e.value for e in AgentEvent}
    legacy = {
        v for k, v in re.findall(r'([A-Z_0-9]+):\s*"([a-z_0-9]+)"', js_path.read_text())
        if k.startswith("LEGACY_")
    }
    still_live = legacy & live
    assert not still_live, (
        f"{js_rel} marks these LEGACY_ but the backend still emits them: {sorted(still_live)}"
    )


def test_no_live_event_uses_report_vocabulary():
    """The artifact mechanism is named for artifacts, not reports.

    "Report" was audit vocabulary sitting on a primitive every agent uses —
    content streams plans and post drafts through the same tag, and the artifact
    store versions all of them alike. The deprecated Python aliases were removed
    once nothing referenced them; this keeps them from creeping back.

    Note this governs the *mechanism* only. ``artifacts.kind == "report"`` is a
    different thing and stays: it discriminates report / document / ticket /
    image, so it says what an artifact *is*.
    """
    offenders = sorted(e.name for e in AgentEvent if "report" in e.value or "report" in e.name.lower())
    assert not offenders, (
        f"AgentEvent still carries report vocabulary: {offenders}. "
        "Use artifact_chunk / artifact_version."
    )
