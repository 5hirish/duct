# Duct — one entry point for the checks CI runs.
#
# The point of this file is that `make check` and the pull-request workflows run
# the same commands. If they drift, CI is right and this is wrong — fix it here.
#
#   make check        everything CI runs on a PR (backend, app, site, desktop, security)
#   make check-<area> just that area, while you are working in it
#   make setup        install dependencies for every area
#
# Each target runs in its own subshell with its own working directory, so there
# is no `cd` leaking between recipe lines.

.DEFAULT_GOAL := help
.PHONY: help setup setup-backend setup-app setup-site setup-desktop \
        check check-backend check-app check-site check-desktop check-security check-docs \
        i18n fmt test dump-prompts serve-backend serve-app serve-app-api serve-site serve-desktop serve-desktop-local serve-desktop-api clean clean-deep clean-prune

# ---------------------------------------------------------------------------

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

setup: setup-backend setup-app setup-site setup-desktop ## Install dependencies everywhere

setup-backend: ## Install backend dependencies (Poetry)
	cd backend && poetry install --with dev

setup-app: ## Install app dependencies (npm)
	cd app && npm ci

setup-site: ## Install site test dependencies (Playwright)
	npm --prefix site ci
	npx --prefix site playwright install --with-deps chromium

setup-desktop: ## Install desktop dependencies (npm + Cargo)
	cd desktop && npm ci
	cd desktop/src-tauri && cargo fetch --locked

# ---------------------------------------------------------------------------
# Checks — these mirror .github/workflows/*.yml
# ---------------------------------------------------------------------------

check: check-backend check-app check-site check-desktop check-security check-docs ## Run every check CI runs
	@echo "\n✅ all checks passed"

check-backend: ## Ruff + pytest + rendered prompts (mirrors backend.yml and prompts.yml)
	cd backend && poetry run ruff check server.py agents routes service tests utils
	cd backend && poetry run pytest -q -m "not live" tests
	# Mirrors prompts.yml. Unlike check-migrations this needs nothing a laptop
	# lacks, so it belongs in the local gate rather than beside it.
	cd backend && poetry run python scripts/dump_prompts.py --check

# Not part of `check`: it needs a throwaway Postgres in DATABASE_URL, which a
# laptop does not have by default and CI provides as a service container.
# The offline suite runs on SQLite, so this is the only local way to see the
# drift `alembic check` reports on the pull request.
check-migrations: ## Apply every migration to an empty Postgres and check the models match (mirrors backend.yml)
	cd backend && poetry run python scripts/migrations.py upgrade head
	cd backend && poetry run alembic check
	cd backend && poetry run alembic downgrade -1 && poetry run alembic upgrade head

# `lint` stays --if-present: app/ has no ESLint config, so that line is a
# placeholder rather than a gate. `typecheck` was a placeholder too until the
# script existed — `--if-present` on a missing script exits 0, so the step
# reported green without ever running tsc. A real gate is invoked by name.
check-app: ## Typecheck, unit tests, parity, build (mirrors app.yml)
	cd app && npm run lint --if-present
	cd app && npm run typecheck
	cd app && npm run check:i18n
	cd app && npm test
	cd app && npm run check:parity
	cd app && npm run build

check-site: ## Page requirements, sitemap, smoke tests (mirrors site.yml)
	python3 scripts/build_blog.py --check
	python3 scripts/build_site_i18n.py --check
	python3 .github/scripts/check-pages.py
	python3 scripts/check_changelog_sync.py
	# Local only: a variant older than its shot means a reshoot was copied in
	# without regenerating them. CI cannot tell (checkout resets mtimes), so
	# there check-pages.py's "every srcset file exists" is the whole guard.
	node scripts/build_media_variants.mjs --check
	python3 -c "import xml.dom.minidom as m; m.parse('site/sitemap.xml'); print('sitemap.xml is well-formed')"
	npm --prefix site run test:e2e

check-desktop: ## Check the Tauri contract, compile the shell, run its unit tests
	python3 .github/scripts/check-shell-contract.py
	cd desktop/src-tauri && cargo check --locked --all-targets
	cd desktop/src-tauri && cargo test --lib --locked

check-security: ## Secret scan + deep audit (mirrors security-audit.yml)
	python3 scripts/security/leak_scan.py --all
	python3 scripts/security/audit.py --mode deep

check-docs: ## Every doc is a dated record or a reference with a current Updated: line (mirrors docs.yml)
	python3 scripts/check_docs.py

# ---------------------------------------------------------------------------
# Shortcuts
# ---------------------------------------------------------------------------

test: ## Backend tests only — the fastest useful signal
	cd backend && poetry run pytest -q -m "not live" tests

# Regenerate after ANY prompt change. `prompts.yml` runs the --check form on a
# pull request that touches a prompt, so skipping this shows up in review
# rather than shipping a document describing last week's prompt.
dump-prompts: ## Re-render docs/engineering/agent-prompts.md from the code
	cd backend && poetry run python scripts/dump_prompts.py

session-bundle: ## Pull one agent session for review: make session-bundle ID=<conversation id> [OUT=dir]; ID=list to browse
	cd backend && poetry run python scripts/session_bundle.py $(ID) $(if $(OUT),--out "$(OUT)") --prompt-check

session-replay: ## Re-run a bundled session on its own data with today's prompt/model: make session-replay BUNDLE=<dir> [ARGS="--model ... --tier heavy"]
	cd backend && poetry run python scripts/session_replay.py "$(BUNDLE)" $(ARGS)

# Run after ANY change to user-facing copy in app/ or site/, before `make check`.
# Extracts the new and changed strings, translates only what is missing (needs
# GEMINI_API_KEY or ANTHROPIC_API_KEY in the shell; see scripts/i18n/fill.py
# for the keyless `--provider manual` path), then compiles and re-renders.
# check-app and check-site fail on whatever this would have produced.
i18n: ## Extract, translate what is missing, compile and render (app + site)
	cd app && npm run i18n:extract
	python3 scripts/build_site_i18n.py
	python3 scripts/i18n/fill.py
	cd app && npm run i18n:compile
	python3 scripts/build_site_i18n.py

fmt: ## Auto-fix what ruff can fix
	cd backend && poetry run ruff check --fix server.py agents routes service tests utils

serve-backend: ## FastAPI on :8002
	cd backend && poetry run uvicorn server:app --reload --port 8002

serve-app: ## Next.js on :3003
	cd app && npm run dev

serve-app-api: ## Run the local Next.js app and FastAPI API together
	$(MAKE) -j2 serve-backend serve-app

serve-site: ## Static site on :8090
	python3 -m http.server 8090 --directory site

serve-desktop: ## Run the Tauri desktop app against the hosted web app
	cd desktop && npm run dev

serve-desktop-local: ## Run Tauri against the local Next.js app
	cd desktop && npm run dev:local

serve-desktop-api: ## Run local Tauri, Next.js, and FastAPI together
	$(MAKE) -j2 serve-backend serve-desktop-local

clean: ## Remove build output and caches that cost nothing to regenerate
	rm -rf app/.next app/.open-next app/tsconfig.tsbuildinfo
	rm -rf backend/build
	rm -rf desktop/src-tauri/target/debug/incremental
	@# find, not a fixed list: ruff and pytest drop these wherever they are run
	@# from, and a hardcoded backend/ path quietly missed the one at the root.
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	find . -name .pytest_cache -type d -prune -exec rm -rf {} + 2>/dev/null || true
	find . -name .ruff_cache -type d -prune -exec rm -rf {} + 2>/dev/null || true

# `clean` deliberately leaves target/debug alone: that directory is not build
# garbage, it is the cache that keeps a Tauri rebuild under a minute instead of
# fifteen. What it never does is forget — 286 crates were occupying 841 .rlib
# files here, ~3 stale generations deep, because nothing prunes superseded
# artifacts. Prefer `clean-prune` for that; this target is the blunt fallback
# for when the tool is missing or the tree is genuinely wedged.
# NOT `cargo clean`. That walks target/*/duct-sidecar — the PyInstaller bundle
# Tauri copies in as an external binary — and dies on grpc's vendored
# roots.pem wherever .pem files are write-protected (agent sandboxes here, and
# anything with a hardened profile). It exits 101 *after* deleting the
# fingerprints, leaving deps/ on disk with nothing left to validate it: several
# GB of dead weight that still looks like a warm cache. Removing the Rust
# output by name is both sandbox-safe and keeps the sidecar where the build
# already expects to find it.
clean-deep: clean ## Also drop Rust build output (next desktop build recompiles everything)
	@for d in desktop/src-tauri/target/*/; do \
		[ -d "$$d" ] || continue; \
		find "$$d" -mindepth 1 -maxdepth 1 ! -name duct-sidecar -exec rm -rf {} + ; \
	done

# 14, not 30: cargo-sweep keys off cargo's own fingerprint data rather than file
# mtime, and the whole target dir gets re-fingerprinted on any full build. At
# --time 30 this tree reported 663 KiB to reclaim; at --time 14, 5.5 GiB. The
# stale generations here are 14-30 days old, so a 30-day window sweeps nothing.
# Anything the current build actually uses was fingerprinted far more recently.
clean-prune: ## Drop Rust artifacts untouched for 14 days, keeping the hot cache warm
	@command -v cargo-sweep >/dev/null 2>&1 || { \
		echo "cargo-sweep not installed. Run: cargo install cargo-sweep"; exit 1; }
	cargo sweep --time 14 --recursive desktop/src-tauri
