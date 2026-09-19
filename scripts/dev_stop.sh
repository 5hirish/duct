#!/usr/bin/env bash
# Stop the local dev processes this repo starts.
#
#   scripts/dev_stop.sh all
#   scripts/dev_stop.sh backend site
#
# Lives here rather than inside an editor task because it has two callers that
# cannot share one: VS Code expresses "stop everything" as `dependsOn` over
# five tasks, and Zed has no task dependencies at all, so the same list written
# in both files is a list that drifts — and the failure is silent, an editor
# that quietly stops stopping something. Touches only Duct's own ports; other
# projects on this machine are not its business.
set -uo pipefail

kill_port() {
  command -v lsof >/dev/null 2>&1 || return 0
  local pids
  pids=$(lsof -t -i ":$1" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    # shellcheck disable=SC2086 — lsof returns one pid per line, all wanted.
    kill -9 $pids >/dev/null 2>&1 || true
  fi
}

stop_backend() {
  kill_port 8002
  pkill -f "uvicorn server:app" >/dev/null 2>&1 || true
}

stop_app() {
  kill_port 3003
}

stop_site() {
  kill_port 8090
  pkill -f "dev_server.py" >/dev/null 2>&1 || true
}

stop_phoenix() {
  kill_port 6006
  pkill -f "phoenix.server.main" >/dev/null 2>&1 || true
}

# Quit first, kill second: a graceful quit reaches RunEvent::Exit, which stops
# the sidecar, while SIGTERM to the shell skips it and leaves an orphan holding
# its loopback port. The pkill pair is the fallback for an app already gone or
# wedged. The dev bundle is handed to launchd by `open`, so no editor session
# owns it and no stop button can reach it — this is the one thing that can.
stop_desktop() {
  osascript -e 'quit app "Duct Dev"' >/dev/null 2>&1 || true
  sleep 1
  pkill -f "Duct Dev.app" >/dev/null 2>&1 || true
  pkill -f "duct-sidecar" >/dev/null 2>&1 || true
}

usage() {
  echo "usage: scripts/dev_stop.sh [all|backend|app|site|phoenix|desktop]..." >&2
  exit 2
}

[ $# -gt 0 ] || usage

for target in "$@"; do
  case "$target" in
    all)      stop_desktop; stop_app; stop_backend; stop_site; stop_phoenix ;;
    backend)  stop_backend ;;
    app)      stop_app ;;
    site)     stop_site ;;
    phoenix)  stop_phoenix ;;
    desktop)  stop_desktop ;;
    *)        echo "unknown target: $target" >&2; usage ;;
  esac
done
