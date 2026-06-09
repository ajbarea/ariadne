# Ariadne

**Sensemaking for nonatomic entities using AI coding agents.** Part of the SCADS program.

[![CI](https://github.com/ajbarea/ariadne/actions/workflows/ci.yml/badge.svg)](https://github.com/ajbarea/ariadne/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/ajbarea/ariadne/graph/badge.svg)](https://codecov.io/gh/ajbarea/ariadne)
[![Python](https://img.shields.io/badge/Python-3.12--3.14-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![uv](https://img.shields.io/badge/uv-package_manager-DE5FE9?style=flat-square)](https://docs.astral.sh/uv/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](./LICENSE)

**Docs:** <https://ajbarea.github.io/ariadne/>

> Ariadne gave Theseus the thread that let him traverse the Labyrinth and find
> his way back out. This project is that thread: a single line of reasoning that
> traces one entity's evidence through a maze of heterogeneous data systems and
> back into a coherent analytic picture.

> [!NOTE]
> Every architectural decision is grounded in current best-practice research,
> captured in [`docs/research/`](./docs/research/): new runtime dependencies and
> tools aren't adopted until grounded there with a `# research(YYYY-MM):` note.
> See [`ROADMAP.md`](./ROADMAP.md).

## The problem

Intelligence about a single entity (a person, a unit, an organizational node)
is scattered across heterogeneous systems (graph, relational, and unstructured
stores) and modalities (metadata, text, imagery, video). No single interface
spans that range, so analysts pivot between systems by hand and lose the thread
at every step. The hard part isn't access; it's multi-hop reasoning across
representations, where the decisive link between two facts often exists only
through an implicit organizational relationship buried in another store and
another modality.

## The approach

Use an agentic AI harness — the Claude Agent SDK — as a *unifying analytic
interface*, not a replacement for existing infrastructure. The harness is an
orchestration layer that dispatches specialized tools and skills to
retrieve, interpret, and synthesize across graph, structured, and unstructured
sources in one coordinated workflow.

**Central research question:** given the harness and its UI, what specific
tools, skills, and hooks are necessary to support a rigorous end-to-end
analytic workflow targeting entities within an organizational hierarchy, and
what is the *minimum viable toolset* that demonstrates real analytic value?

## Deliverable

A working prototype that takes a target entity or organizational node as
input and, through a coordinated sequence of tool invocations, surfaces relevant
evidence from across all available data structures and modalities, synthesizing
findings into a coherent analytic product. Success is measured by the harness's
ability to:

- traverse organizational relationships,
- reconcile information across modalities,
- reduce the analyst's manual-pivot burden, and
- surface non-obvious connections impractical to find with conventional tooling.

## SCADS umbrella role

Ariadne is conceived as an umbrella effort within SCADS. It does not
duplicate sibling-project work; it defines integration interfaces so that
contributions from other SCADS projects — graph-extraction pipelines, entity-
resolution models, multimodal indexing schemes — can be surfaced as callable
tools within the harness. It is both a standalone research contribution and a
unifying demonstration layer for the SCADS portfolio.

## Install

```bash
pip install ariadne-sensemaking      # or: uv add ariadne-sensemaking
```

This installs the `ariadne` CLI and the `ariadne-sensemaking` MCP server entry point.

## Use from any AI CLI

The `ariadne` MCP server exposes the `workup` tool to any MCP client: Claude
Code, Copilot, Gemini CLI, Cursor, Windsurf, and others. Two install paths:

**Claude Code (one-click):** add this repo's marketplace, then install the
plugin:

```bash
/plugin marketplace add ajbarea/ariadne
# then: /plugin install ariadne
```

This bundles the Ariadne MCP server + the `analyst-workup` skill into Claude Code
in a single step. A workup is then available via the `ariadne` server tool.

**Any other MCP client:** point the client's MCP config at the published
package, and `uvx` will fetch and run it with no clone or manual install:

```json
{
  "mcpServers": {
    "ariadne": { "command": "uvx", "args": ["ariadne-sensemaking"] }
  }
}
```

To track an unreleased commit instead, point `uvx` at the repo with
`"args": ["--from", "git+https://github.com/ajbarea/ariadne", "ariadne-sensemaking"]`;
to run from a local checkout, use `"command": "python", "args": ["-m", "ariadne.mcp_server"]`.

Config caveat: the tool is portable; the data is not. Point the server at your
stores (`NEO4J_*` / `DATABASE_URI`) and set `ANTHROPIC_API_KEY` per install.
See [ADR-0009](./docs/architecture/decisions/0009-distribute-as-mcp-server-and-plugin.md).

## Observability

Ariadne emits OpenTelemetry traces and metrics via the optional `otel` extra.
The base install (api-only) is a no-op — nothing is emitted unless you configure
an OTLP endpoint.

```bash
# 1. install the otel extra
uv sync --extra otel

# 2. point at your OTLP collector (Jaeger, Grafana, Datadog, etc.)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

# 3. optionally add the Claude Agent SDK's per-LLM-call spans
export CLAUDE_CODE_ENABLE_TELEMETRY=1
```

What is emitted per workup:

- **`invoke_agent` span** — covers the full workup; duration = task time.
- **`ariadne.workups` counter** and **`ariadne.workup.duration` histogram** —
  latency and throughput.
- **`ariadne.evidence.calls` counter** — evidence-tool calls (from the
  provenance ledger); surfaces existing `provenance.jsonl` data.
- **`ariadne.citation.failures` counter** — uncited + unsupported claims;
  surfaces existing `citations.json` gate output.
- **Span attributes** for citation compliance (`citation.ok`, `citation.uncited`,
  `citation.unsupported`) and tradecraft compliance (`tradecraft.estimative_terms`,
  `tradecraft.has_confidence`) — surfaces existing `tradecraft.json` output.

When `CLAUDE_CODE_ENABLE_TELEMETRY=1` is set, the Agent SDK's per-LLM-call spans
nest under Ariadne's `invoke_agent` span — one trace covers the full workup
without any extra config.

See [ADR-0010](./docs/architecture/decisions/0010-observability-opentelemetry.md)
for the design rationale and considered alternatives.

## Quickstart

Work up a target entity against a graph store, open an interactive report, and score
the run. This first run is graph-only (one store, ~90s); add `--sql --semantic` once you
have Postgres up for the full cross-store workup.

```bash
# 1a. start a local Neo4j
docker compose -f infra/neo4j/docker-compose.yml up -d
# 1b. seed the synthetic org graph
docker exec -i ariadne-neo4j cypher-shell -u neo4j -p password < infra/neo4j/seed.cypher

# 2. the live agent loop needs an API key
export ANTHROPIC_API_KEY=sk-...

# 3. work up a target entity. The output is an immutable run dir
#    runs/synthetic/halberd/<run-id>/ (note.md, provenance.jsonl, citations.json,
#    manifest.json, ...), with runs/synthetic/halberd/latest pointing at the newest run.
uv run ariadne workup Halberd

# 4. open the self-contained interactive report: entity-network view, clickable
#    provenance + evidence drawer, reconciliation panel, eval dashboard. The fastest
#    way to see what the workup found.
uv run ariadne report runs/synthetic/halberd/latest
#    -> writes runs/synthetic/halberd/latest/report.html; open it in a browser

# 5. score the run: planted-needle grounding (+ optional cross-store reconciliation)
uv run ariadne eval runs/synthetic/halberd/latest --reconcile synthetic
#    and the ICD-203 analytic-quality rubric (LLM judge; needs the 'rubric' extra)
uv run ariadne rubric runs/synthetic/halberd/latest

# 6. enforce the read-only contract offline (CI gate, no API key; exit 3 on a write attempt)
uv run ariadne governance runs/synthetic/halberd/latest
```

Every fact in the note carries a `[cite:gN]` id that resolves to a recorded graph
query in `provenance.jsonl`; the run fails if any citation is uncited, dangling,
or (with the optional `eval` extra) unsupported by its cited evidence. `ariadne
eval` then scores whether the run **surfaced and actually traversed** the seed's
planted non-obvious bridge; `grounded=True` means it reasoned, not guessed.

The analytic loop is **read-only by construction** (the graph and relational MCP
connectors run in read-only / restricted mode); `ariadne governance` *verifies* that
on a persisted run by auditing the provenance ledger for any mutating verb, and
**gates by default** (exit 3 on a write attempt). Pass `--strict` to `ariadne workup`
to apply the same gate to the live run.

**Dev gates** (requires [`uv`](https://docs.astral.sh/uv/)):

```bash
make setup        # install dependencies (uv sync)
make lint         # ruff format --check + ruff check + ty
make test-unit    # fast hermetic tests
make validate     # lint + unit tests (pre-push gate)
```

Archived, auditable runs (reconciled by `/techne:audit`):

```bash
./scripts/dev-runner.sh lint   # writes logs/dev-<UTC>-lint.log + logs/dev-latest.log
```

## Repository layout

| Path | Purpose |
| ---- | ------- |
| `src/ariadne/` | The package: CLI + MCP server, read-only store connectors (`graph`, `relational`, `unstructured`), the adapt layer (`introspect`, `mapping`), bounded self-improvement (`learning`), and the eval / provenance / report modules. |
| `plugins/ariadne/` | The Claude Code plugin: the bundled MCP server config + the `analyst-workup` skill. |
| `.claude/skills/entity-workup/` | The analytic procedure (gather, act, verify, synthesize) the agent loop follows. |
| `infra/` | docker-compose for a local Neo4j + Postgres. |
| `docs/architecture/decisions/` | MADR ADRs: every contestable choice and its rejected alternatives. |
| `docs/research/` | The June-2026 best-practice research backing each design decision. |
| `tests/` | Unit + integration suite. |
| `scripts/` | `dev-runner.sh` and other repo scripts. |

## Documentation site

Built with [Zensical](https://zensical.org/) and deployed to GitHub Pages on
every push to `main` touching `docs/`. Serve locally:

```bash
make docs        # uv run --with zensical zensical serve
```

## Status

Ariadne works up an entity end to end: graph, relational, full-text, and semantic
retrieval; a citation-gated analytic note; a self-contained interactive report;
planted-needle and ICD-203 evaluation; and a read-only governance gate.

Beyond the built-in datasets it **adapts** to your own Postgres (introspect, propose
a mapping, ratify, then run the existing pipeline unchanged) and **learns from
experience** (distil a skill from a strong run, reflect on a weak one, deepen a
skill, and use `ariadne compare` to measure whether a learned change actually helps
before adopting it).

See [`IMPL.md`](./IMPL.md) for what's in flight and [`ROADMAP.md`](./ROADMAP.md) for
the build order.

## License

MIT © 2026 AJ Barea. See [`LICENSE`](./LICENSE).
