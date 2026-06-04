# Get Started

!!! note "Scaffold and research phase"

    Ariadne's harness architecture is being defined from
    [current best practice](research/best-practice-architecture.md) before any
    connector or library is pinned. The steps below set up the toolchain and run
    the placeholder CLI, not yet the full analytic workflow.

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

| Goal                       | Command            |
| -------------------------- | ------------------ |
| Install dependencies       | `make setup`       |
| Auto-fix (format + lint)   | `make fix`         |
| Lint (CI-equivalent)       | `make lint`        |
| Unit tests (fast)          | `make test-unit`   |
| Full test suite            | `make test`        |
| Pre-push gate              | `make validate`    |
| Run the (scaffold) CLI     | `uv run ariadne`   |
| Serve these docs locally   | `make docs`        |

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
`docs/`, `overrides/`, or `zensical.toml`.

## Project layout

| Path            | Purpose                                                       |
| --------------- | ------------------------------------------------------------- |
| `src/ariadne/`  | The Python package, harness wiring, CLI entrypoint.          |
| `tools/`        | Custom/in-process agent tools (connectors, processors).       |
| `skills/`       | Agent Skills, packaged analytic procedures.                  |
| `mcp_servers/`  | MCP connectors for graph / SQL / vector stores.               |
| `docs/`         | This documentation site (conventions, architecture, research).|
| `tests/`        | Test suite (unit + integration).                              |

See the [Roadmap](roadmap.md) for what lands in each of these as the build
progresses.
