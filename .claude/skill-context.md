# skill-context — ariadne

Repo-specific facts for canonical skills under `~/.claude/skills/`. Injected
into each skill at invocation. Update on toolchain / path / tooling changes.

## repo

- name: ariadne
- description: sensemaking harness for nonatomic entities, built on the Claude Agent SDK
- package_root: `src/ariadne/` (src-layout, single package)
- language: Python (>=3.12,<3.15)
- toolchain: uv (canonical); ruff (format + lint), ty (types), pytest
- cli_entrypoint: `uv run ariadne workup <entity>` (Phase 1 — graph-backed cited-note pipeline)
- runner: `./scripts/dev-runner.sh <make-target>` → writes `logs/dev-<UTC>-<target>.log` + `logs/dev-latest.log`
- has: Docker (Neo4j via `infra/neo4j/docker-compose.yml`), no frontend, no Rust.
  Runtime deps: claude-agent-sdk, neo4j, mcp-neo4j-cypher.
  Architecture: Phase 1 — read-only Neo4j MCP connector (`src/ariadne/graph/neo4j_server.py`),
  entity-workup skill (`.claude/skills/entity-workup/`), PostToolUse provenance hook
  (`src/ariadne/provenance/hook.py`), cited-note CLI (`src/ariadne/cli.py`).

## audit

`techne:audit` reconciles terminal exit codes against `logs/dev-<ts>-<cmd>.log`
archives. Wrap each target from OUTSIDE the Makefile via `./scripts/dev-runner.sh <target>`.

Audit order (skip interactive/long-running):

### Phase 1 — Setup
1. `make clean` — wipes caches, build artifacts, old `logs/dev-*-*.log` archives.
2. `make check-env` — uv + Python on PATH.

`make setup` is safe (non-interactive `uv sync`) but mutates `.venv`; run it
only if deps aren't installed.

### Phase 2 — Fix (one-way door)
3. `make fix` — `ruff format`, `ruff check --fix`. (`ty` has no auto-fix.)

### Phase 3 — Lint
4. `make lint` — `ruff format --check`, `ruff check`, `ty check`.

### Phase 4 — Test
5. `make test-unit` — `pytest -m "not integration and not slow"`, parallel. Fast, hermetic.
6. `make test` — full suite. May include integration tests needing live MCP servers / containers.

### Phase 5 — Gates
7. `make validate` — `lint + test-unit`. "Am I ready to push" probe.
8. `make audit` — `pip-audit` / `uv audit` for CVEs. **Informational**, not a gate.

### do_not_run (interactive / long-running)
- `make docs` — serves Zensical docs site (blocks).
- `make dev` / `uv run ariadne` — runs the harness CLI.
- `make logs-tail` — follows the log (blocks).

## ci_audit

Configs a CI failure traces to:
- `pyproject.toml`, `Makefile`, `scripts/dev-runner.sh`
- `infra/neo4j/docker-compose.yml` (integration: live Neo4j MCP)
- `.github/workflows/{ci,docs,pin-check,zizmor,release}.yml`, `zensical.toml` (docs build), `codecov.yml`

Required PR checks (7): `Lint (ruff + ty)`, `Tests (py3.12)`, `Tests (py3.13)`, `Tests (py3.14)`, `Read-only governance gate`, `pin-check`, `zizmor`. `docs.yml` build/deploy is push-only — deliberately NOT required (would block PRs forever).

Tool error markers (extend the default grep set):
- `pytest`, `ruff`, `ty` (lint/test)
- `pip-audit` / `uv audit` (advisory; informational)
- `neo4j` / `docker` / `compose` (integration container / MCP errors)
- `zizmor` (workflow-security findings)

## slop_ground_truth

ariadne ships **no perf/benchmark harness** (no `pytest.mark.performance`, no `make baselines`). Its claims are qualitative — cited-note quality, provenance coverage, graph-backed reasoning — not throughput/latency numbers. Any quantitative perf / scale / accuracy claim is slop unless it traces to a committed test or an evaluation artifact under `tests/` or `runs/`.

## scan_scope

Skip paths:
- `.venv/`, `dist/`, `site/`, `runs/` (eval outputs), `__pycache__/`, `.ruff_cache/`, `.pytest_cache/`, `.hypothesis/`
- `uv.lock`, `logs/`, `infra/**/data/` (Neo4j volumes), `overrides/` (docs theme), `docs/assets/`

Subagent scan-area split:
- Package: `src/ariadne/**/*.py` (Neo4j connector, provenance hook, cited-note CLI, entity workup)
- MCP servers: `mcp_servers/**/*.py`
- Skills: `skills/**`, `.claude/skills/entity-workup/**`
- Scripts and tests: `scripts/**`, `tests/**/*.py`
- Config/build: `pyproject.toml`, `Makefile`, `.github/workflows/**`, `zensical.toml`, `infra/**/docker-compose.yml`, `codecov.yml`
- Docs (opt-in): `docs/**/*.md`

## docs_site

- config: `zensical.toml`
- workflow: `.github/workflows/docs.yml` (build + deploy; push-only, NOT a PR-required check)
- build_command: `uv tool run zensical build --clean` (CI); local preview `make docs` → `zensical serve` (blocks — do-not-run)
- site_url: `https://ajbarea.github.io/ariadne/`
