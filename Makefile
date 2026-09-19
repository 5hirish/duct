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
        i18n fmt test dump-prompts serve-backend serve-app serve-app-api serve-site serve-desktop serve-desktop-local serve-desktop-api clean

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

clean: ## Remove build output and caches
	rm -rf app/.next app/.open-next
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	find . -name .pytest_cache -type d -prune -exec rm -rf {} + 2>/dev/null || true
