##
## ariadne — Makefile
## Thin wrapper around the uv-driven toolchain. `make <target>` and the raw
## `uv run ...` invocation are equivalent.
##
## Quality gates are fix-first: `make fix` runs every auto-fixer (ruff format,
## ruff check --fix) without the check pass, so a subsequent `make lint`
## measures intent, not formatting noise.
##
## For archived runs that techne:audit reconciles, wrap from OUTSIDE the
## Makefile:  ./scripts/dev-runner.sh lint   (writes logs/dev-<UTC>-lint.log)
## Do NOT call dev-runner.sh from inside a recipe — it invokes make and recurses.
##

.PHONY: help check-env setup upgrade fix lint validate test test-unit test-integration audit clean docs dev logs logs-tail
.DEFAULT_GOAL := help

UV := uv run --no-active

# ---------------------------------------------------------------------------
# Environment & setup
# ---------------------------------------------------------------------------

check-env:              ## Verify uv and Python are available
	@command -v uv >/dev/null 2>&1 && echo "uv: $$(uv --version)" || { echo "uv not found on PATH"; exit 1; }
	@uv run python --version

setup:                  ## Install all dependencies (uv sync with dev group)
	@uv sync --group dev

upgrade:                ## Upgrade all dependencies to latest allowed
	@uv sync --group dev --upgrade

# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------

fix:                    ## Run every auto-fixer (ruff format, ruff check --fix); skip the check pass
	@$(UV) ruff format .
	@$(UV) ruff check --fix .

lint:                   ## Format + lint + type check (no auto-fix); CI-equivalent
	@$(UV) ruff format --check .
	@$(UV) ruff check .
	@$(UV) ty check

validate:               ## Fast pre-push gate: lint + unit tests
	@$(MAKE) lint
	@$(MAKE) test-unit

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

test:                   ## Run the full test suite
	@$(UV) pytest

test-unit:              ## Unit tests only (fast, hermetic; -m "not integration and not slow")
	@$(UV) pytest -m "not integration and not slow" -n auto

test-integration:       ## Integration tests only (-m integration; may need live MCP servers / containers)
	@$(UV) pytest -m integration

# ---------------------------------------------------------------------------
# Security & housekeeping
# ---------------------------------------------------------------------------

audit:                  ## Audit dependencies for known CVEs (informational, not a gate)
	@$(UV) --with pip-audit pip-audit || uv audit || echo "audit tooling unavailable"

clean:                  ## Remove caches, build artifacts, and old dev-runner archives
	@rm -rf .ruff_cache .pytest_cache .hypothesis htmlcov .coverage build dist *.egg-info
	@find . -type d -name __pycache__ -not -path './.git/*' -exec rm -rf {} + 2>/dev/null || true
	@find logs -maxdepth 1 -name 'dev-*-*.log' -delete 2>/dev/null || true
	@echo "clean: done"

# ---------------------------------------------------------------------------
# Long-running / interactive (do-not-run for techne:audit)
# ---------------------------------------------------------------------------

docs:                   ## Serve project documentation locally (do-not-run)
	@$(UV) --with zensical zensical serve

dev:                    ## Run the ariadne CLI entrypoint (do-not-run)
	@$(UV) ariadne

# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

logs:                   ## Show the last 200 lines of logs/dev-latest.log
	@tail -n 200 logs/dev-latest.log 2>/dev/null || echo "no logs yet — run ./scripts/dev-runner.sh <target> first"

logs-tail:              ## Follow logs/dev-latest.log (Ctrl-C to exit)
	@tail -f logs/dev-latest.log 2>/dev/null || echo "no logs yet — run ./scripts/dev-runner.sh <target> first"

help:                   ## Show this help
	@grep -hE '^[a-zA-Z][a-zA-Z0-9_-]*:.*?##' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'
