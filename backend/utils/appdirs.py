"""Per-user writable data directory for the desktop (local) build.

Under a PyInstaller bundle the code lives in a read-only app bundle, so anything
the backend writes — the SQLite database, uploaded images, agent artifacts — has
to go to an OS-appropriate per-user location instead of next to the source.

Leaf module: imports only the standard library so ``config`` can use it without
an import cycle.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Reverse-DNS identifier, matching the Tauri shell's `identifier` in
# src-tauri/tauri.conf.json so both halves of the app agree on one folder.
APP_IDENTIFIER = "ai.getduct.desktop"
APP_NAME = "Duct"


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def default_data_dir() -> Path:
    """OS-conventional per-user data directory for Duct.

    macOS   ~/Library/Application Support/ai.getduct.desktop
    Windows %APPDATA%\\Duct
    Linux   $XDG_DATA_HOME/duct  (default ~/.local/share/duct)
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_IDENTIFIER
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
        return root / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    root = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return root / "duct"


def resolve_data_dir(override: str = "") -> Path:
    """Data directory to use, honouring an explicit override, then DUCT_DATA_DIR."""
    raw = (override or os.environ.get("DUCT_DATA_DIR", "")).strip()
    return Path(raw).expanduser() if raw else default_data_dir()


def ensure_data_dir(override: str = "") -> Path:
    """Resolve the data directory and make sure it exists (private to this user)."""
    path = resolve_data_dir(override)
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        # The SQLite DB and the local API key live here — keep it owner-only.
        os.chmod(path, 0o700)
    return path
