"""The agent tool-exposure gate.

Every Duct agent reads text somebody else wrote. The audit agent's prompt
carries H2 headings scraped off the site under audit; the content and audit
enrichment sub-agents WebFetch competitor pages; conversation summaries quote
tool output. That is the product working as intended, and it means an injected
instruction reaching a shell is a remote code execution path into
``backend/.env*`` — the Fernet key for every stored connector refresh token,
``JWT_SECRET``, ``DATABASE_URL``.

Two Claude Agent SDK options decide whether that path exists, and they are easy
to confuse:

* ``tools``         — what the CLI *offers*. The SDK emits ``--tools`` only when
                      this is not None (``_internal/transport/subprocess_cli.py``),
                      so **omitting it ships the CLI's default set**: Bash, Read,
                      Write, Edit, Glob, Grep.
* ``allowed_tools`` — what is *pre-approved*. It never removes a tool. Listing
                      two entries here while leaving ``tools`` unset does not
                      narrow anything.

So an options block is only safe when at least one of these holds:

  1. ``tools`` is set — the CLI cannot offer anything else, or
  2. ``permission_mode`` hard-denies whatever is not matched: ``dontAsk`` or
     ``plan``.

``bypassPermissions`` with an unset ``tools`` is the specific combination that
put an unsandboxed Bash in front of scraped web text (audit + content
enrichment, fixed Sept 2026). The SDK itself warns about it in
``_get_can_use_tool_shadowed_warning``: bypass auto-approves every call
*before* ``can_use_tool`` is consulted, so a callback is not a mitigation.

This test reads the source rather than the runtime because these options are
built inside async functions that need a live API key to reach. Adding a new
agent is the moment this matters, which is exactly when nobody re-reads the
enrichment files.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent

# Where first-party code that could construct agent options lives.
SOURCE_ROOTS = ("agents", "routes", "service")

# The constructor this gate is about.
OPTIONS_CLASS = "ClaudeAgentOptions"

# `permission_mode` values that hard-deny anything not explicitly matched, and
# therefore make an unbounded `tools` survivable. Mirrors AgentPermissionMode in
# agents/models.py — both the enum member name and the wire string, since either
# spelling is valid at a call site.
DENYING_MODES = {"DONT_ASK", "dontAsk", "PLAN", "plan"}


def _source_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in SOURCE_ROOTS:
        files.extend(sorted((BACKEND / root).rglob("*.py")))
    return files


def _callee_name(node: ast.Call) -> str:
    """Last path segment of the callee: `ClaudeAgentOptions` or `sdk.ClaudeAgentOptions`."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _permission_mode(node: ast.Call) -> str | None:
    """The `permission_mode` argument as a comparable string, or None if unset.

    Handles the two spellings that appear at call sites: the enum member
    (`AgentPermissionMode.DONT_ASK`) and a bare string (`"dontAsk"`).
    """
    for kw in node.keywords:
        if kw.arg != "permission_mode":
            continue
        value = kw.value
        if isinstance(value, ast.Attribute):
            return value.attr
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
        # Anything computed — a variable, a call — cannot be read statically.
        # Treat it as unknown, which fails closed below.
        return "<dynamic>"
    return None


def _options_calls() -> list[tuple[pathlib.Path, ast.Call]]:
    found: list[tuple[pathlib.Path, ast.Call]] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _callee_name(node) == OPTIONS_CLASS:
                found.append((path, node))
    return found


def test_gate_has_something_to_check() -> None:
    """A gate that matches nothing passes for the wrong reason.

    If the SDK is swapped or the constructor renamed, this fails first and says
    so, rather than letting the real assertion below go quietly green.
    """
    calls = _options_calls()
    assert calls, (
        f"No {OPTIONS_CLASS}(...) call sites found under {SOURCE_ROOTS}. Either the "
        "SDK was replaced or the constructor was renamed — update OPTIONS_CLASS, "
        "do not delete this test."
    )


def test_unbounded_tools_only_with_a_denying_permission_mode() -> None:
    """Every options block bounds `tools` or hard-denies unmatched tools."""
    offenders: list[str] = []

    for path, node in _options_calls():
        kwargs = {kw.arg for kw in node.keywords if kw.arg}
        if "tools" in kwargs:
            continue  # the CLI offers only what is listed — safe whatever the mode

        mode = _permission_mode(node)
        if mode in DENYING_MODES:
            continue  # unmatched tools are hard-denied — safe

        rel = path.relative_to(BACKEND)
        shown = "unset" if mode is None else repr(mode)
        offenders.append(
            f"  {rel}:{node.lineno} — permission_mode={shown} with no `tools=`. "
            "The CLI ships its default set (Bash, Read, Write, Edit) and this mode "
            "does not deny them."
        )

    assert not offenders, (
        "Agent options that expose the default tool set without hard-denying it:\n"
        + "\n".join(offenders)
        + "\n\nFix by adding an explicit `tools=[...]` (what the CLI may offer) or "
        "`permission_mode=AgentPermissionMode.DONT_ASK`. `allowed_tools` alone does "
        "NOT narrow the tool set — it only pre-approves. See this module's docstring."
    )


@pytest.mark.parametrize("path,node", _options_calls(), ids=lambda v: getattr(v, "name", ""))
def test_bypass_permissions_always_bounds_tools(path: pathlib.Path, node: ast.Call) -> None:
    """`bypassPermissions` is never paired with an unbounded tool set.

    Narrower than the test above and kept separate on purpose: this is the exact
    combination that shipped, so it deserves a failure message that names it.
    """
    mode = _permission_mode(node)
    if mode not in {"BYPASS", "bypassPermissions"}:
        return
    kwargs = {kw.arg for kw in node.keywords if kw.arg}
    assert "tools" in kwargs, (
        f"{path.relative_to(BACKEND)}:{node.lineno} uses permission_mode=bypassPermissions "
        "without an explicit `tools=`. That auto-approves the CLI's default Bash/Write/Edit "
        "tools before can_use_tool is ever consulted. If the agent genuinely needs bypass, "
        "bound the tool set; otherwise use DONT_ASK."
    )
