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
import contextlib
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
_JWT_SECRET_FILE = "local-jwt-secret"
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


def _load_or_create_secret(path: Path) -> str:
    """Return the secret stored at `path`, generating it on first run. 0600."""
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    # 43 url-safe chars, comfortably over the 32 Configs requires of JWT_SECRET.
    value = secrets.token_urlsafe(32)
    path.write_text(value, encoding="utf-8")
    if sys.platform != "win32":
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return value


def load_or_create_api_key(data_dir: Path) -> str:
    """Return the persisted local API key, creating it on first run.

    This is not a shared secret with a server — it only stops other local
    processes on the machine from driving the sidecar. Stored 0600.
    """
    return _load_or_create_secret(data_dir / _API_KEY_FILE)


def load_or_create_jwt_secret(data_dir: Path) -> str:
    """Return the persisted key that signs this install's session tokens.

    The deployment gets JWT_SECRET from its environment; a frozen bundle ships
    no `.env` and the shell injects only the Google client, so without this the
    sign-in callback reaches `_create_jwt` with an empty key and raises — the
    request fails as a bare 500 *after* the user has already approved at Google,
    which is a confusing place to land. Persisted rather than per-boot so a
    restart does not silently sign everyone out.
    """
    return _load_or_create_secret(data_dir / _JWT_SECRET_FILE)


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
    # setdefault, not assignment: a developer running the sidecar against a
    # shared backend may want to pin the signing key to that deployment's.
    os.environ.setdefault("JWT_SECRET", load_or_create_jwt_secret(data_dir))
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


def _report_environment() -> None:
    """Say which env files and which database this run ended up on.

    Which environment a sidecar embodies is configuration, not a default: the
    same binary is expected to run against a laptop's SQLite or a team's
    Postgres depending on what it was started with. That makes "which one is
    this?" the first question of every desktop bug report, and the answer was
    previously nowhere in the log.

    Written straight to stderr rather than through `logging`: this has to be
    legible before the app (and its logging config) is even imported, and the
    line is worthless if a logging change can silence it. Credentials are
    stripped by `describe_database` — never print the URL itself.
    """
    from config import describe_database, get_configs, _settings_env_files

    sources = [
        f"{path}{'' if path.is_file() else ' (missing)'}" for path in _settings_env_files()
    ]
    print(f"[duct-sidecar] env files: {', '.join(sources) or '(none)'}", file=sys.stderr)
    print(
        f"[duct-sidecar] database:  {describe_database(get_configs().database_url)}",
        file=sys.stderr,
    )
    sys.stderr.flush()


def main(argv: list[str] | None = None) -> int:
    # Line-buffer our own output before anything writes. Python block-buffers
    # stdout when it is a pipe rather than a terminal — which is exactly how the
    # shell runs us — so without this the log arrives in 8 KB gulps, i.e. never
    # for the handful of lines that precede a crash. The shell also passes
    # PYTHONUNBUFFERED, but a sidecar launched any other way (a developer
    # debugging one by hand, CI) deserves the same.
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(line_buffering=True)

    handshake = bootstrap(argv)

    # Emit the handshake before importing the app so the shell gets it promptly
    # even if startup (DB create_all, connector registration) takes a moment.
    sys.stdout.write(json.dumps(handshake) + "\n")
    sys.stdout.flush()

    _report_environment()

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
