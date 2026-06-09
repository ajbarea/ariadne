# Get Started

!!! note "What runs today"

    The harness runs end-to-end: `ariadne workup <entity>` drives the live agent
    loop over the seeded stores and writes a cited analytic note; `ariadne report
    <run-dir>` renders a self-contained interactive report. It also adapts to your
    own Postgres (introspect, propose a mapping, ratify) and learns from experience
    (`distil`, `reflect`, `compare`).

    The live loop needs `ANTHROPIC_API_KEY` (plus Neo4j and Postgres for the
    relational/semantic legs); the offline commands (`report`, `eval`, `governance`,
    `compare`) need neither. Every design choice is grounded in
    [current best practice](research/best-practice-architecture.md) before it
    hardens into code.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/), Python packaging and runner
- Python ≥ 3.12 (uv can install it for you)

## Setup

```bash
git clone https://github.com/ajbarea/ariadne.git
cd ariadne
make setup        # uv sync: installs dependencies + dev group
```

## Everyday commands

`make help` lists every target. The common ones:

| Goal                       | Command                          |
| -------------------------- | -------------------------------- |
| Install dependencies       | `make setup`                     |
| Auto-fix (format + lint)   | `make fix`                       |
| Lint (CI-equivalent)       | `make lint`                      |
| Unit tests (fast)          | `make test-unit`                 |
| Full test suite            | `make test`                      |
| Pre-push gate              | `make validate`                  |
| Run a workup (live loop)   | `uv run ariadne workup <entity>` |
| Open a run's report        | `uv run ariadne report <run-dir>` |
| List the CLI subcommands   | `uv run ariadne --help`          |
| Serve these docs locally   | `make docs`                      |

## Auditable runs

For archived runs that `/techne:audit` reconciles against terminal output, wrap
a target from outside the Makefile:

```bash
./scripts/dev-runner.sh lint     # writes logs/dev-<UTC>-lint.log + logs/dev-latest.log
```

## Documentation

This site is built with [Zensical](https://zensical.org/). Serve it locally:

```bash
make docs                        # uv run --with zensical zensical serve
```

It deploys automatically to GitHub Pages on every push to `main` that touches
`docs/`, `overrides/`, `zensical.toml`, or the docs workflow itself.

## Project layout

| Path            | Purpose                                                       |
| --------------- | ------------------------------------------------------------- |
| `src/ariadne/`  | The package: CLI + MCP server, store connectors, the adapt layer, and the `learning` self-improvement modules. |
| `plugins/ariadne/` | The Claude Code plugin (bundled MCP server + analyst-workup skill). |
| `infra/`        | docker-compose for a local Neo4j + Postgres.                  |
| `docs/architecture/decisions/` | The MADR ADRs (every contestable choice + its alternatives). |
| `docs/`         | This documentation site (conventions, architecture, research).|
| `tests/`        | Test suite (unit + integration).                              |

See the [Roadmap](roadmap.md) for what lands in each of these as the build
progresses.
