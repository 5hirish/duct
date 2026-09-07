#!/usr/bin/env python3
"""Guard the two facts the desktop shell's version number is supposed to carry.

The web app never sniffs the shell version — it asks `get_shell_info` what the
shell can do. That is the right design, and it has one failure mode: when a
capability changes without the version changing, two different builds share a
version and disagree about what they support. The version then tells nobody
anything, and identifying an affected install means reading strings out of the
binary. That is not hypothetical — `browserAuth` shipped inside 0.2.0 exactly
that way, and an install predating it looked like a routing bug for a day.

So this checks:

0. Every `#[tauri::command]` is registered in all three places it has to be:
   `generate_handler!`, `AppManifest::commands` in `build.rs`, and at least one
   capability file. Miss one and the command is simply absent from the shipped
   binary; `invoke` rejects it, `getShellInfo()` swallows the rejection and
   returns null, and the web app silently takes its "old shell" path. An
   installed build has been found in exactly that state — carrying the string
   literals from inside `get_shell_info` while the command name appeared
   nowhere in the bundle.

1. `tauri.conf.json` and `Cargo.toml` agree on the version. `get_shell_info`
   reports the Cargo value while the bundle is named after the Tauri one, and
   nothing else fails when they drift apart.

2. If the capability set in `get_shell_info` changed against the base branch,
   the version changed too. Per `desktop/AGENTS.md`, a new capability flag is a
   MINOR bump; removing one is MAJOR (MINOR while pre-1.0).

Usage: check-shell-contract.py [base-ref]   # base-ref defaults to origin/main
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TAURI_CONF = "desktop/src-tauri/tauri.conf.json"
CARGO_TOML = "desktop/src-tauri/Cargo.toml"
LIB_RS = "desktop/src-tauri/src/lib.rs"
SRC_TAURI = REPO_ROOT / "desktop/src-tauri"
BUILD_RS = SRC_TAURI / "build.rs"
CAPABILITIES = SRC_TAURI / "capabilities"


def read_base(ref: str, path: str) -> str | None:
    """File contents at `ref`, or None when it did not exist there."""
    out = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return out.stdout if out.returncode == 0 else None


def tauri_version(text: str) -> str:
    return str(json.loads(text).get("version", ""))


def cargo_version(text: str) -> str:
    # Scoped to [package] — a dependency's `version =` would otherwise match first.
    body = text.split("[package]", 1)[-1] if "[package]" in text else text
    body = re.split(r"^\[", body, maxsplit=1, flags=re.M)[0]
    m = re.search(r'^version\s*=\s*"([^"]+)"', body, re.M)
    return m.group(1) if m else ""


def capabilities(text: str) -> set[str]:
    """Capability flag names declared inside `get_shell_info`."""
    fn = re.search(r"fn get_shell_info\b.*?\n}\n", text, re.S)
    if not fn:
        return set()
    block = re.search(r'"capabilities"\s*:\s*\{(.*?)\n\s*\}', fn.group(0), re.S)
    if not block:
        return set()
    body = re.sub(r"//[^\n]*", "", block.group(1))  # comments quote flag names
    return set(re.findall(r'"([A-Za-z0-9_]+)"\s*:', body))


def command_registrations() -> list[str]:
    """Commands missing any of the three edits a `#[tauri::command]` needs."""
    problems: list[str] = []
    commands: set[str] = set()
    for rs in sorted(SRC_TAURI.rglob("*.rs")):
        if "target" in rs.parts:
            continue
        text = rs.read_text(encoding="utf-8", errors="replace")
        commands.update(
            re.findall(
                r"#\[tauri::command\][^\n]*\n(?:\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+))",
                text,
            )
        )
    if not commands:
        return ["found no #[tauri::command] functions — has the layout changed?"]

    lib = (REPO_ROOT / LIB_RS).read_text(encoding="utf-8")
    handler = re.search(r"generate_handler!\s*\[(.*?)\]", lib, re.S)
    handler_body = handler.group(1) if handler else ""
    build = BUILD_RS.read_text(encoding="utf-8") if BUILD_RS.exists() else ""
    caps = {p.name: p.read_text(encoding="utf-8") for p in CAPABILITIES.glob("*.json")}

    for name in sorted(commands):
        missing = []
        if not re.search(rf"\b{re.escape(name)}\b", handler_body):
            missing.append("generate_handler! in src/lib.rs")
        if f'"{name}"' not in build:
            missing.append("AppManifest::commands in build.rs")
        allow = "allow-" + name.replace("_", "-")
        if not any(allow in text for text in caps.values()):
            missing.append(f"`{allow}` in any capabilities/*.json")
        if missing:
            problems.append(
                f"command `{name}` is not registered in: " + "; ".join(missing) + ".\n"
                "    All three are required. Without them the command is unreachable from\n"
                "    the webview at runtime and the JS side degrades silently."
            )
    return problems


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    errors: list[str] = command_registrations()

    head_conf = (REPO_ROOT / TAURI_CONF).read_text(encoding="utf-8")
    head_cargo = (REPO_ROOT / CARGO_TOML).read_text(encoding="utf-8")
    head_lib = (REPO_ROOT / LIB_RS).read_text(encoding="utf-8")

    v_tauri, v_cargo = tauri_version(head_conf), cargo_version(head_cargo)
    if not v_tauri or not v_cargo:
        errors.append(f"could not read a version from {TAURI_CONF} and {CARGO_TOML}")
    elif v_tauri != v_cargo:
        errors.append(
            f"version mismatch: {TAURI_CONF} says {v_tauri}, {CARGO_TOML} says {v_cargo}.\n"
            f"    They must always match — get_shell_info reports the Cargo value and the\n"
            f"    bundle is named after the Tauri one. Refresh Cargo.lock after editing."
        )

    base_conf = read_base(base, TAURI_CONF)
    base_lib = read_base(base, LIB_RS)
    if base_conf is None or base_lib is None:
        print(f"shell contract: no baseline at {base}; version-bump check skipped")
    else:
        head_caps, base_caps = capabilities(head_lib), capabilities(base_lib)
        if not head_caps:
            errors.append(f"could not parse any capability flags out of {LIB_RS}")
        elif head_caps != base_caps:
            added = sorted(head_caps - base_caps)
            removed = sorted(base_caps - head_caps)
            if v_tauri == tauri_version(base_conf):
                change = ", ".join(
                    [f"+{c}" for c in added] + [f"-{c}" for c in removed]
                )
                errors.append(
                    f"capabilities changed ({change}) but the shell version is still"
                    f" {v_tauri}.\n"
                    f"    The web app gates behaviour on these flags, so two builds sharing\n"
                    f"    a version while disagreeing about them cannot be told apart from\n"
                    f"    the outside. Bump MINOR in {TAURI_CONF} and {CARGO_TOML}\n"
                    f"    (see desktop/AGENTS.md, Versioning)."
                )

    if errors:
        print("shell contract check failed:\n")
        for e in errors:
            print(f"  ✗ {e}\n")
        return 1

    print(f"shell contract: version {v_tauri} consistent; capabilities in step with {base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
