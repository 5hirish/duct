#!/usr/bin/env bash
# Local trace viewer for agent runs: Jaeger (Apache-2.0), which replaced
# Phoenix (Elastic License 2.0, source-available, not open source).
#
#   scripts/jaeger.sh     # UI and MCP on :16686, OTLP on :4318 (HTTP) and :4317
#
# The API exports to it when OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
# (agents/core/telemetry.py). One Go binary with no Docker and no login, so it
# fits beside the dev stack on an 8 GB laptop. Its MCP server
# (/api/ai/mcp/ on the UI port) is how an agent reads a slow or failed run.
#
# Pinned, downloaded once from the GitHub release into ~/.cache/duct/jaeger and
# checked against the release's own checksum before it ever runs. Spans live on
# disk for a week (scripts/jaeger.yaml), so a run survives a restart.
set -euo pipefail

VERSION=2.22.0
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/duct/jaeger"

os=$(uname -s | tr '[:upper:]' '[:lower:]')
case "$(uname -m)" in
  x86_64) arch=amd64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) echo "no Jaeger release for $(uname -m)" >&2; exit 1 ;;
esac
name="jaeger-$VERSION-$os-$arch"
bin="$CACHE/$name/jaeger"

if [ ! -x "$bin" ]; then
  release="https://github.com/jaegertracing/jaeger/releases/download/v$VERSION"
  mkdir -p "$CACHE"
  echo "downloading Jaeger $VERSION ($os-$arch)…" >&2
  curl -fsSL "$release/$name.tar.gz" | tar -xzf - -C "$CACHE" "$name/jaeger"
  # The release lists the extracted binary, not the tarball: "<sha256> *<path>".
  expected=$(curl -fsSL "$release/$name.sha256sum.txt" | awk -v f="*$name/jaeger" '$2 == f { print $1 }')
  actual=$(shasum -a 256 "$bin" | awk '{ print $1 }')
  if [ -z "$expected" ] || [ "$expected" != "$actual" ]; then
    rm -rf "${CACHE:?}/$name"
    echo "checksum mismatch for $name/jaeger; removed it" >&2
    exit 1
  fi
fi

export JAEGER_DATA_DIR="$CACHE/data"
mkdir -p "$JAEGER_DATA_DIR"
"$bin" --config "$(cd "$(dirname "$0")" && pwd)/jaeger.yaml" &
pid=$!
trap 'kill "$pid" 2>/dev/null' EXIT INT TERM

# The config logs warnings only, so this line is the ready signal, for a person
# and for the editors' launch configs that open the UI on it.
until curl -sf -o /dev/null http://localhost:16686/; do
  kill -0 "$pid" 2>/dev/null || exit 1
  sleep 0.5
done
echo "Jaeger ready: http://localhost:16686 · MCP /api/ai/mcp/ · OTLP http://localhost:4318"
wait "$pid"
