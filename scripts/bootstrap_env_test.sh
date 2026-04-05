#!/usr/bin/env bash
# Copy local dev env files to gitignored .env.test targets (never commit).
# Usage: ./scripts/bootstrap_env_test.sh [--force]
# See: docs/engineering/deployment-cloudflare-railway.md

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FORCE=0
for arg in "$@"; do
	if [[ "$arg" == "--force" ]]; then
		FORCE=1
	fi
done

copy_one() {
	local src="$1"
	local dest="$2"
	local label="$3"
	if [[ ! -f "$src" ]]; then
		echo "skip: missing $label ($src)" >&2
		return 0
	fi
	if [[ -f "$dest" && "$FORCE" -ne 1 ]]; then
		echo "error: $dest already exists (use --force to overwrite)" >&2
		exit 1
	fi
	cp "$src" "$dest"
	echo "wrote $dest (from $label)"
}

copy_one "$ROOT/backend/.env" "$ROOT/backend/.env.test" "backend/.env"
copy_one "$ROOT/app/.env.local" "$ROOT/app/.env.test" "app/.env.local"
