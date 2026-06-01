# Ariadne

**Sensemaking for nonatomic entities using AI coding agents.** SCADS Project #1.

📖 **Docs:** <https://ajbarea.github.io/ariadne/>

> Ariadne gave Theseus the thread that let him traverse the Labyrinth and find
> his way back out. This project is that thread: a single line of reasoning that
> traces one entity's evidence through a maze of heterogeneous data systems and
> back into a coherent analytic picture.

> [!NOTE]
> `ariadne` is a working codename, easy to rename. The architecture is being
> defined from June-2026 best-practice research, now captured in
> [`docs/research/`](./docs/research/) — runtime dependencies and the concrete
> toolset stay intentionally unset until each is grounded in that research with a
> `# research(YYYY-MM):` note. See [`ROADMAP.md`](./ROADMAP.md).

## The problem

Intelligence about a single entity (a person, a unit, an organizational node)
is scattered across **heterogeneous systems** — graph databases, structured
relational stores, and unstructured repositories — and across **modalities** —
metadata, free text, imagery, and video. No single query interface spans that
range. Analysts pivot manually between systems, losing context and momentum at
every transition. The hard part isn't access; it's **coherent, multi-hop
reasoning** across representations, where the decisive link between two facts
may exist only through an implicit organizational relationship buried in a
different store and a different modality.

## The approach

Use an agentic AI harness — the **Claude Agent SDK** — as a *unifying analytic
interface*, not a replacement for existing infrastructure. The harness is an
**orchestration layer** that dispatches specialized tools and skills to
retrieve, interpret, and synthesize across graph, structured, and unstructured
sources in one coordinated workflow.

**Central research question:** given the harness and its UI, what specific
**tools, skills, and hooks** are necessary to support a rigorous end-to-end
analytic workflow targeting entities within an organizational hierarchy — and
what is the *minimum viable toolset* that demonstrates real analytic value?

## Deliverable

A working prototype that takes a **target entity or organizational node** as
input and, through a coordinated sequence of tool invocations, surfaces relevant
evidence from across all available data structures and modalities, synthesizing
findings into a coherent analytic product. Success is measured by the harness's
ability to:

- traverse organizational relationships,
- reconcile information across modalities,
- reduce the analyst's manual-pivot burden, and
- surface non-obvious connections impractical to find with conventional tooling.

## SCADS umbrella role

Ariadne is conceived as an **umbrella effort** within SCADS. It does not
duplicate sibling-project work; it defines **integration interfaces** so that
contributions from other SCADS projects — graph-extraction pipelines, entity-
resolution models, multimodal indexing schemes — can be surfaced as callable
tools within the harness. It is both a standalone research contribution and a
unifying demonstration layer for the SCADS portfolio.

## Quickstart

Phase 1 works up a target entity against a graph store and returns a cited analytic note.

```bash
# 1a. start a local Neo4j
docker compose -f infra/neo4j/docker-compose.yml up -d
# 1b. seed the synthetic org graph
docker exec -i ariadne-neo4j cypher-shell -u neo4j -p password < infra/neo4j/seed.cypher

# 2. the live agent loop needs an API key
export ANTHROPIC_API_KEY=sk-...

# 3. run a workup (writes ./workups/<entity>/note.md, provenance.jsonl, citations.json)
uv run ariadne workup Halberd
```

Every fact in the note carries a `[cite:gN]` id that resolves to a recorded graph
query in `provenance.jsonl`; the run fails if any citation is unverified.

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

| Path            | Purpose                                                              |
| --------------- | ------------------------------------------------------------------- |
| `src/ariadne/`  | The Python package — harness wiring, CLI entrypoint.                |
| `tools/`        | Custom/in-process agent tools (connectors, processors). *Pending.* |
| `skills/`       | Agent Skills — packaged analytic procedures (e.g. entity-workup). *Pending.* |
| `mcp_servers/`  | MCP server connectors for graph / SQL / vector stores. *Pending.*  |
| `docs/`         | Zensical documentation site (conventions, architecture, research). |
| `docs/research/`| June-2026 best-practice research backing every design decision.    |
| `tests/`        | Test suite (unit + integration).                                   |
| `scripts/`      | `dev-runner.sh` and other repo scripts.                            |

## Documentation site

Built with [Zensical](https://zensical.org/) and deployed to GitHub Pages on
every push to `main` touching `docs/`. Serve locally:

```bash
make docs        # uv run --with zensical zensical serve
```

## Status

Phase 1 shipped. The Neo4j MCP connector, `entity-workup` skill, provenance hook,
and `ariadne workup` CLI are all committed and gated. See [`IMPL.md`](./IMPL.md)
for what's in flight (Phase 2) and [`ROADMAP.md`](./ROADMAP.md) for the phased
build order.

## License

MIT © 2026 AJ Barea. See [`LICENSE`](./LICENSE).
