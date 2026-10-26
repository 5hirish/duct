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

Secrets contract (stdin, exactly one line, read before anything else):

    {"duct_secrets": 1, "DUCT_LOCAL_API_KEY": "...", "DUCT_LOCAL_JWT_SECRET": "...",
     "CREDENTIALS_ENCRYPTION_KEY": "...", "GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET": "..."}

With `--secrets-on-stdin` the shell writes that line on the same pipe it then
holds open for `--exit-on-stdin-eof`, and omits any value it does not have.
The sidecar prefers a supplied value over its environment, and whichever
channel a secret arrived on, the names are removed from `os.environ` once the
settings object has read them (`SECRET_ENV_NAMES`). Without the flag nothing
is read from stdin and the environment alone is consulted, which is how a
headless `--data-dir` run and a developer's shell keep working.

Usage:
    python local_server.py [--port N] [--data-dir PATH] [--log-level LEVEL]
                           [--exit-on-stdin-eof] [--secrets-on-stdin]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import secrets
import signal
import socket
import stat
import sys
import threading
import time
from collections.abc import Mapping
from pathlib import Path

from utils.appdirs import ensure_data_dir

# Filename of the persisted local API key inside the data dir.
_API_KEY_FILE = "local-api-key"
_JWT_SECRET_FILE = "local-jwt-secret"
# Loopback only — the sidecar must never be reachable from the network.
_HOST = "127.0.0.1"
# How long a graceful stop may take once the shell is gone before the process
# ends itself outright. The shell waits the same two seconds before it kills.
_SHUTDOWN_GRACE_SECS = 2.0


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


# What the desktop shell passes down when it holds these in the OS keychain.
# Deliberately not `DUCT_API_KEY`/`JWT_SECRET`: those are Configs settings a
# developer may pin for other reasons, and seeing one set must not be read as
# "the shell has this in the keychain now, delete the file".
_API_KEY_ENV = "DUCT_LOCAL_API_KEY"
_JWT_SECRET_ENV = "DUCT_LOCAL_JWT_SECRET"
# Marker field on the stdin secrets line, the counterpart of `duct_sidecar` on
# the handshake: a line without it is not ours, whatever else it parses as.
_SECRETS_LINE_MARKER = "duct_secrets"
# Settings `Configs` reads straight from the environment. A value the shell
# supplies on stdin is placed there for it with `setdefault`, so a value a
# developer exported still wins, exactly as it did when the shell set the
# variable itself.
_CONFIGS_SECRET_NAMES = ("CREDENTIALS_ENCRYPTION_KEY", "GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET")
# Every secret this process ever holds in its environment: the four the shell
# may hand down and the two `bootstrap()` derives from them. Removed by
# `scrub_secrets_from_environment()` once `Configs` is built, because a
# process environment is readable by every other process this user runs and
# is inherited by every subprocess, and `Configs` is cached after one read
# (`get_configs` is `lru_cache`d; nothing in the backend reads these names
# from `os.environ` afterwards).
SECRET_ENV_NAMES = (
    _API_KEY_ENV,
    _JWT_SECRET_ENV,
    *_CONFIGS_SECRET_NAMES,
    "DUCT_API_KEY",
    "JWT_SECRET",
)


def _retire_file(path: Path) -> None:
    """Remove a secret now held somewhere stronger.

    Best effort and deliberately quiet: the value is already in the keychain, so
    a file that cannot be deleted is stale rather than dangerous, and failing a
    boot over it would be the worse outcome.
    """
    try:
        path.unlink()
    except OSError:
        pass


def _from_shell_or_file(env_name: str, path: Path, supplied: Mapping[str, str]) -> str:
    """The shell's keychain copy if there is one, else the file, else a new one.

    The shell's copy arrives on stdin (`supplied`); the environment is consulted
    second so a developer exporting the name by hand keeps working. Deleting the
    file once the keychain answers *is* the migration: an existing install moves
    on its next launch and nothing has to detect a version. The file fallback is
    what keeps a headless `duct-sidecar --data-dir …` working with no shell, and
    what keeps a machine whose keychain is unavailable bootable.
    """
    value = (supplied.get(env_name) or os.environ.get(env_name, "")).strip()
    if value:
        _retire_file(path)
        return value
    return _load_or_create_secret(path)


def load_or_create_api_key(data_dir: Path, supplied: Mapping[str, str] | None = None) -> str:
    """Return the local API key: the shell's keychain copy, or this install's file.

    This is not a shared secret with a server — it only stops other local
    processes on the machine from driving the sidecar.
    """
    return _from_shell_or_file(_API_KEY_ENV, data_dir / _API_KEY_FILE, supplied or {})


def load_or_create_jwt_secret(data_dir: Path, supplied: Mapping[str, str] | None = None) -> str:
    """Return the persisted key that signs this install's session tokens.

    The deployment gets JWT_SECRET from its environment; a frozen bundle ships
    no `.env` and the shell injects only the Google client, so without this the
    sign-in callback reaches `_create_jwt` with an empty key and raises — the
    request fails as a bare 500 *after* the user has already approved at Google,
    which is a confusing place to land. Persisted rather than per-boot so a
    restart does not silently sign everyone out.
    """
    return _from_shell_or_file(_JWT_SECRET_ENV, data_dir / _JWT_SECRET_FILE, supplied or {})


def read_secrets_line(stream) -> dict[str, str]:
    """Read the shell's one-line JSON object of secrets from `stream`.

    Exactly one line, so the watchdog can go on reading the same stream for
    EOF afterwards; the two readers are sequential, never concurrent. Anything
    but the documented object is a failed start rather than a fallback: the
    shell asked for this channel with `--secrets-on-stdin`, so silently running
    on freshly minted files would hand the webview a key the shell does not
    hold and every request would 401 with nothing in the log saying why.

    The failure is reported as a `SystemExit` carrying one line for stderr that
    names the cause and never a value — this process's stderr is relayed into
    the shell's log.
    """
    line = stream.readline()
    if not line:
        raise SystemExit("[duct-sidecar] --secrets-on-stdin was set but stdin closed before a line arrived")
    try:
        payload = json.loads(line)
    except ValueError:
        raise SystemExit("[duct-sidecar] the first line on stdin was not valid JSON") from None
    if not isinstance(payload, dict) or payload.get(_SECRETS_LINE_MARKER) != 1:
        raise SystemExit(f"[duct-sidecar] the first line on stdin was not a {_SECRETS_LINE_MARKER} object")
    return {
        name: value
        for name, value in payload.items()
        if name != _SECRETS_LINE_MARKER and isinstance(value, str)
    }


def scrub_secrets_from_environment() -> None:
    """Drop every secret name from `os.environ` once nothing needs it there.

    Safe only after `get_configs()` has run: `Configs` reads the environment at
    construction and is cached for the life of the process, and every consumer
    (`service/credentials.py`, `routes/signin.py`, `validate_api_key`) goes
    through it rather than back to `os.environ`.
    """
    for name in SECRET_ENV_NAMES:
        os.environ.pop(name, None)


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
    parser.add_argument(
        "--exit-on-stdin-eof",
        action="store_true",
        help=(
            "Exit when stdin reaches end-of-file. The desktop shell passes this "
            "with a pipe only it holds, so the sidecar ends when the shell does."
        ),
    )
    parser.add_argument(
        "--secrets-on-stdin",
        action="store_true",
        help=(
            "Read one JSON line of secrets from stdin before anything else. The "
            "desktop shell passes this instead of putting them in the environment."
        ),
    )
    return parser.parse_args(argv)


def _stdin_bytes():
    """The binary stdin both the secrets line and the watchdog read, or None.

    One object for both readers on purpose: a second buffered reader over the
    same descriptor could swallow bytes the first had already consumed, or
    hold the line in a buffer the other never sees.
    """
    return getattr(sys.stdin, "buffer", None)


def bootstrap(argv: list[str] | None = None) -> dict[str, object]:
    """Prepare the environment for a local run and return the handshake payload.

    Must run *before* `config`/`server` are imported, because Configs is cached
    (`@lru_cache`) and reads these env vars once at first construction.
    """
    args = _parse_args(argv)

    # First, before the data dir or anything that could log: the shell wrote
    # the line right after spawning and is now waiting on the handshake.
    supplied: dict[str, str] = {}
    if args.secrets_on_stdin:
        stdin = _stdin_bytes()
        if stdin is None:
            raise SystemExit("[duct-sidecar] --secrets-on-stdin was set but there is no stdin to read")
        supplied = read_secrets_line(stdin)

    data_dir = ensure_data_dir(args.data_dir)
    api_key = load_or_create_api_key(data_dir, supplied)
    port = args.port or _pick_free_port()
    url = f"http://{_HOST}:{port}"

    os.environ["DUCT_LOCAL"] = "1"
    os.environ["DUCT_DATA_DIR"] = str(data_dir)
    os.environ["DUCT_API_KEY"] = api_key
    os.environ["API_PUBLIC_URL"] = url
    # setdefault, not assignment: a developer running the sidecar against a
    # shared backend may want to pin the signing key to that deployment's.
    os.environ.setdefault("JWT_SECRET", load_or_create_jwt_secret(data_dir, supplied))
    for name in _CONFIGS_SECRET_NAMES:
        if supplied.get(name):
            os.environ.setdefault(name, supplied[name])
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


def watch_stdin(stream, on_eof) -> threading.Thread:
    """Call `on_eof` from a daemon thread once `stream` reaches end-of-file.

    The shell holds the other end of the pipe and nothing else does, so EOF
    means the shell is gone — quit, crashed, killed, or relaunched for an
    update. Before this the sidecar learned of none of those but the clean
    quit: it kept the SQLite file and its port until someone found the stray
    Python process. Opt-in by flag rather than always on, because a sidecar
    started by hand reads a terminal, where Ctrl-D would stop the server, or
    `/dev/null` from a service manager, where it would stop at once.

    A read error counts as EOF: either way nobody is on the other end.
    """

    def wait_for_eof() -> None:
        try:
            while stream.read(4096):
                pass
        except OSError:
            pass
        on_eof()

    thread = threading.Thread(target=wait_for_eof, name="stdin-watchdog", daemon=True)
    thread.start()
    return thread


def _stop_for_lost_shell() -> None:
    """The stop a lost shell gets: uvicorn's own, then a guaranteed one.

    SIGTERM is what uvicorn already handles — in-flight requests finish, the
    lifespan shutdown runs, the process exits on its own. The hard exit behind
    it exists because this is the one case where nobody is left to send a
    kill, so the sidecar has to be the one that makes sure it ends.
    """
    signal.raise_signal(signal.SIGTERM)
    time.sleep(_SHUTDOWN_GRACE_SECS)
    os._exit(0)


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

    args = _parse_args(argv)
    handshake = bootstrap(argv)

    # Emit the handshake before importing the app so the shell gets it promptly
    # even if startup (DB create_all, connector registration) takes a moment.
    sys.stdout.write(json.dumps(handshake) + "\n")
    sys.stdout.flush()

    if args.exit_on_stdin_eof:
        stdin = _stdin_bytes()
        if stdin is None:
            print(
                "[duct-sidecar] no stdin to watch; the shell cannot end this process",
                file=sys.stderr,
            )
        else:
            watch_stdin(stdin, _stop_for_lost_shell)

    _report_environment()
    # `_report_environment` built and cached Configs, so from here on nothing
    # needs the secrets in the environment; uvicorn and the app are imported
    # below, after they are gone.
    scrub_secrets_from_environment()

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
        log_level=args.log_level,
        # One process: the sidecar's lifetime is the app window's lifetime.
        workers=1,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
