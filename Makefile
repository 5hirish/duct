# Duct — one entry point for the checks CI runs.
#
# The point of this file is that `make check` and the pull-request workflows run
# the same commands. If they drift, CI is right and this is wrong — fix it here.
#
#   make check        everything CI runs on a PR (backend, app, site, security)
#   make check-<area> just that area, while you are working in it
#   make setup        install dependencies for every area
#
# Each target runs in its own subshell with its own working directory, so there
# is no `cd` leaking between recipe lines.

.DEFAULT_GOAL := help
.PHONY: help setup setup-backend setup-app setup-site \
        check check-backend check-app check-site check-security \
        fmt test serve-backend serve-app serve-site clean

# ---------------------------------------------------------------------------

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

setup: setup-backend setup-app setup-site ## Install dependencies everywhere

setup-backend: ## Install backend dependencies (Poetry)
	cd backend && poetry install --with dev

setup-app: ## Install app dependencies (npm)
	cd app && npm ci

setup-site: ## Install site test dependencies (Playwright)
	npm --prefix site ci
	npx --prefix site playwright install --with-deps chromium

# ---------------------------------------------------------------------------
# Checks — these mirror .github/workflows/*.yml
# ---------------------------------------------------------------------------

check: check-backend check-app check-site check-security ## Run every check CI runs
	@echo "\n✅ all checks passed"

check-backend: ## Ruff + pytest (mirrors backend.yml)
	cd backend && poetry run ruff check server.py agents routes service tests utils
	cd backend && poetry run pytest -q -m "not live" tests

# `lint` stays --if-present: app/ has no ESLint config, so that line is a
# placeholder rather than a gate. `typecheck` was a placeholder too until the
# script existed — `--if-present` on a missing script exits 0, so the step
# reported green without ever running tsc. A real gate is invoked by name.
check-app: ## Typecheck, unit tests, parity, build (mirrors app.yml)
	cd app && npm run lint --if-present
	cd app && npm run typecheck
	cd app && npm test
	cd app && npm run check:parity
	cd app && npm run build

check-site: ## Page requirements, sitemap, smoke tests (mirrors site.yml)
	python3 .github/scripts/check-pages.py
	python3 -c "import xml.dom.minidom as m; m.parse('site/sitemap.xml'); print('sitemap.xml is well-formed')"
	npm --prefix site run test:e2e

check-security: ## Secret scan + deep audit (mirrors security-audit.yml)
	python3 scripts/security/leak_scan.py --all
	python3 scripts/security/audit.py --mode deep

# ---------------------------------------------------------------------------
# Shortcuts
# ---------------------------------------------------------------------------

test: ## Backend tests only — the fastest useful signal
	cd backend && poetry run pytest -q -m "not live" tests

fmt: ## Auto-fix what ruff can fix
	cd backend && poetry run ruff check --fix server.py agents routes service tests utils

serve-backend: ## FastAPI on :8002
	cd backend && poetry run uvicorn server:app --reload --port 8002

serve-app: ## Next.js on :3003
	cd app && npm run dev

serve-site: ## Static site on :8090
	python3 -m http.server 8090 --directory site

clean: ## Remove build output and caches
	rm -rf app/.next app/.open-next
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	find . -name .pytest_cache -type d -prune -exec rm -rf {} + 2>/dev/null || true
