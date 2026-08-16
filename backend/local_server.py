"""Desktop entrypoint — run the Duct backend as a local sidecar.

The Tauri shell spawns this binary, reads one JSON handshake line from stdout,
and points the webview at the reported URL. Everything stays on the user's
machine: SQLite in the per-user data dir, provider keys from the OS keychain
passed per request, no Railway.

Handshake contract (stdout, exactly one line, before any log output):

    {"duct_sidecar": 1, "url": "http://127.0.0.1:53124", "port": 53124,
     "api_key": "...", "data_dir": "/Users/x/Library/Application Support/..."}

The shell MUST read the port from this line rather than assuming one — we bind
port 0 and let the OS choose, so two Duct windows (or a dev server) never
collide. `api_key` is the local `X-API-Key` value; it is generated once and
persisted in the data dir so it survives restarts.

Usage:
    python local_server.py [--port N] [--data-dir PATH] [--log-level LEVEL]
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import stat
import sys
from pathlib import Path

from utils.appdirs import ensure_data_dir

# Filename of the persisted local API key inside the data dir.
_API_KEY_FILE = "local-api-key"
# Loopback only — the sidecar must never be reachable from the network.
_HOST = "127.0.0.1"


def _pick_free_port() -> int:
    """Ask the OS for an unused loopback port.

    Bound and released immediately; uvicorn re-binds it a moment later. The race
    is acceptable for a single-user desktop app and avoids hardcoding a port that
    might already be taken.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_HOST, 0))
        return int(sock.getsockname()[1])


def load_or_create_api_key(data_dir: Path) -> str:
    """Return the persisted local API key, creating it on first run.

    This is not a shared secret with a server — it only stops other local
    processes on the machine from driving the sidecar. Stored 0600.
    """
    key_path = data_dir / _API_KEY_FILE
    if key_path.exists():
        existing = key_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    key = secrets.token_urlsafe(32)
    key_path.write_text(key, encoding="utf-8")
    if sys.platform != "win32":
        key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return key


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="duct-sidecar", description=__doc__)
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port to bind. 0 (default) asks the OS for a free one.",
    )
    parser.add_argument(
        "--data-dir",
        default="",
        help="Override the per-user data directory (default: OS-conventional path).",
    )
    parser.add_argument("--log-level", default="info")
    return parser.parse_args(argv)


def bootstrap(argv: list[str] | None = None) -> dict[str, object]:
    """Prepare the environment for a local run and return the handshake payload.

    Must run *before* `config`/`server` are imported, because Configs is cached
    (`@lru_cache`) and reads these env vars once at first construction.
    """
    args = _parse_args(argv)

    data_dir = ensure_data_dir(args.data_dir)
    api_key = load_or_create_api_key(data_dir)
    port = args.port or _pick_free_port()
    url = f"http://{_HOST}:{port}"

    os.environ["DUCT_LOCAL"] = "1"
    os.environ["DUCT_DATA_DIR"] = str(data_dir)
    os.environ["DUCT_API_KEY"] = api_key
    os.environ["API_PUBLIC_URL"] = url
    # The Tauri webview loads the bundled frontend from a tauri:// origin; the
    # shell also opens the hosted app during the transition, so allow both.
    os.environ.setdefault("FRONTEND_ORIGIN", "tauri://localhost")
    # A user's laptop is not a deployment — never phone home by default.
    os.environ.setdefault("APP_ENV", "desktop")
    os.environ.setdefault("SENTRY_DSN", "")

    return {
        "duct_sidecar": 1,
        "url": url,
        "port": port,
        "api_key": api_key,
        "data_dir": str(data_dir),
    }


def main(argv: list[str] | None = None) -> int:
    handshake = bootstrap(argv)

    # Emit the handshake before importing the app so the shell gets it promptly
    # even if startup (DB create_all, connector registration) takes a moment.
    sys.stdout.write(json.dumps(handshake) + "\n")
    sys.stdout.flush()

    import uvicorn  # imported after bootstrap so logging config sees our env

    # Import the app object rather than passing "server:app". PyInstaller freezes
    # modules into an archive, so uvicorn's string-based import fails with
    # "Could not import module 'server'" in a packaged build. Passing the object
    # also skips uvicorn's reloader, which a desktop sidecar never wants.
    from server import app

    uvicorn.run(
        app,
        host=_HOST,
        port=int(handshake["port"]),
        log_level=_parse_args(argv).log_level,
        # One process: the sidecar's lifetime is the app window's lifetime.
        workers=1,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
