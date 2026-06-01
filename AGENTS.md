# AGENTS.md — Ariadne

Repository conventions for agentic coding tools (Claude Code, Cursor, Codex,
Aider). Humans: start with [`README.md`](README.md), then [`ROADMAP.md`](ROADMAP.md).

## What this project is

A sensemaking harness for nonatomic entities, built on the **Claude Agent SDK**
as an orchestration layer over heterogeneous, multimodal data. Architecture is
research-driven; see [`docs/research/`](docs/research/). Do **not** introduce
runtime dependencies or pin connectors/libraries until the decision is recorded
in [`ROADMAP.md`](ROADMAP.md) with a `# research(YYYY-MM):` provenance note.

## Build & run

`uv` is the canonical toolchain; `make` targets wrap it. `make help` lists all.

| Goal                        | Command              |
| --------------------------- | -------------------- |
| Install deps                | `make setup`         |
| Auto-fix (format + lint)    | `make fix`           |
| Lint (CI-equivalent)        | `make lint`          |
| Unit tests (fast)           | `make test-unit`     |
| Full test suite             | `make test`          |
| Pre-push gate               | `make validate`      |
| Run the CLI                 | `uv run ariadne`     |
| Archived/auditable run      | `./scripts/dev-runner.sh <target>` |

## Conventions

- **Python ≥ 3.12**, src-layout package under `src/ariadne/`.
- **Formatting/linting:** ruff (format + check). **Types:** ty. Config in `pyproject.toml`.
- **Fix-first gates:** `make fix` before `make lint` so lint measures intent.
- **Tests:** pytest, `asyncio_mode = auto`. Mark integration tests `@pytest.mark.integration`
  and heavy ones `@pytest.mark.slow` so the fast lane stays hermetic.
- **No secrets or source intelligence data in the repo.** `data/`, `models/`,
  `.env`, and `logs/` are gitignored.
- **Provenance matters.** This is an analytic tool: every fact the harness
  surfaces should be traceable to its source tool. Favor designs that preserve
  citations end-to-end.

## Where things go

- Agent **tools** (custom/in-process connectors & processors) → `tools/`.
- Agent **Skills** (packaged analytic procedures) → `skills/<name>/SKILL.md`.
- **MCP servers** (graph / SQL / vector connectors) → `mcp_servers/`.
- Research backing decisions → `docs/research/`.

## Skill context

Repo-specific facts for canonical `~/.claude/skills/` (techne) live in
[`.claude/skill-context.md`](.claude/skill-context.md). Update it on toolchain
or path changes.
