# Conventions

Ariadne follows the techne conventions so the canonical skills (`/techne:audit`,
`/techne:ci-audit`, `/techne:theoros`) work against this repo.

## The Makefile pattern

The toolchain is invoked through one-word `make` targets, not raw tool commands.
Required vocabulary: `setup`, `lint`, `test`, plus the richer set this repo
adopts: `fix`, `test-unit`, `test-integration`, `validate`, `audit`, `clean`,
`docs`, `dev`, `logs`, `help`. `make help` renders the list from the
`## description` comment after each target. `.DEFAULT_GOAL := help`.

**Fix-first gates:** `make fix` runs every auto-fixer with no check pass, so a
subsequent `make lint` measures intent, not formatting noise.

## The dev-runner archive

`/techne:audit` does not run `make` directly; it diffs the terminal exit code
against a per-invocation log archive. Wrap each target from **outside** the
Makefile:

```bash
./scripts/dev-runner.sh lint     # writes logs/dev-<UTC-timestamp>-lint.log
```

Each run produces `logs/dev-<UTC>-<target>.log` (and truncates the stable
pointer `logs/dev-latest.log`) ending with a `SUMMARY` block carrying the
overall `rc`. Do **not** call `dev-runner.sh` from inside a Makefile recipe — it
invokes `make` and would recurse.

## Toolchain

- **uv** for dependency management and running (`uv run ...`).
- **ruff** for formatting and linting; **ty** for type checking.
- **pytest** for tests (`asyncio_mode = auto`); `integration` and `slow` markers
  keep the fast lane hermetic.
- **Python ≥ 3.12**, src-layout under `src/ariadne/`.

## Data & secrets

Never commit source intelligence data, credentials, or model weights. `data/`,
`models/`, `.env*`, and `logs/` are gitignored. Connectors read endpoints and
credentials from the environment, never from tracked files.

## Provenance

Ariadne produces analytic products, so traceability is a first-class convention:
every fact the harness surfaces should carry its source. Prefer designs (e.g.
`PostToolUse` provenance hooks) that preserve citations end-to-end. See
[`research/`](research/) for the grounding behind each architectural decision.
