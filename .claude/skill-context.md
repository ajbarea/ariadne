# skill-context — ariadne

Repo-specific facts for canonical skills under `~/.claude/skills/`. Injected
into each skill at invocation. Update on toolchain / path / tooling changes.

## repo

- name: ariadne
- description: sensemaking harness for nonatomic entities (SCADS), built on the Claude Agent SDK
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
