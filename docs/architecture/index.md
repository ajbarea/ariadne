# Architecture

Design notes for Ariadne's harness. **Deliberately thin until the June-2026
research resolves the open questions** in the [Roadmap](../roadmap.md) — hardening
a design before then risks building against the wrong fork.

## Building blocks

The orchestration layer is the **Claude Agent SDK**. Its primitives are the
vocabulary every design choice is expressed in:

- **Tools** — callable retrieval/processing functions (in-process or via MCP).
- **Skills** — packaged multi-step analytic procedures (e.g. `entity-workup`).
- **Hooks** — lifecycle interceptors for provenance, authorization, and audit.
- **Subagents** — context-isolated workers for parallel per-source retrieval.
- **MCP** — the connector standard surfacing graph / SQL / vector stores as tools.

See the [Claude Agent SDK Reference](../research/claude-agent-sdk-reference.md)
for the full doc-cited mechanics.

## Decisions

Significant, contestable choices — *which store, which connector, what was
deferred and why* — live in the [Decision log](decisions/index.md) as ADRs: the
single place to point when asked "why this instead of that?" Notable examples:
the Postgres-over-Redis comparison ([ADR-0004](decisions/0004-postgres-over-redis-for-relational-store.md))
and the dataset-abstraction approach ([ADR-0006](decisions/0006-dataset-agnostic-pipeline.md)).

## Emerging shape (from the research)

The [June-2026 best-practice research](../research/best-practice-architecture.md)
points to an **orchestrator–worker** design: a lead agent runs the canonical
*gather context → take action → verify → repeat* loop and dispatches parallel,
context-isolated subagents — each restricted to one source — that retrieve via
MCP connectors and hand back only their findings. **GraphRAG** is the core
capability for traversing organizational hierarchies; multimodal evidence is
fused **agentically** by converting imagery/video to structured text before
reasoning over it.

## Datasets

A future developer adds a corpus by writing one **adapter** that maps raw data to
the canonical schema (`Entity` / `Relationship` / `Document` / `Attribute`); a
dataset-agnostic indexer fans the records into the stores. The agent,
`entity-workup` skill, connectors, and eval harness never change. Governance
(access-control, PII gating) attaches at the canonical layer once, not per
dataset. Unstructured/free-text evidence is retrieved full-text-first via a
Postgres `tsvector` GIN index (`websearch_to_tsquery`), per
[ADR-0007](decisions/0007-hybrid-retrieval-fulltext-first.md), with the semantic pgvector
leg as a follow-on. See [ADR-0006](decisions/0006-dataset-agnostic-pipeline.md)
for the dataset-abstraction decision record and
[`docs/superpowers/specs/2026-06-03-multi-dataset-pipeline-design.md`](../superpowers/specs/2026-06-03-multi-dataset-pipeline-design.md)
for the full design.

## To be written

Once the MVP boundary is set: the end-to-end analytic workflow (entity in →
coordinated tool sequence → cited analytic product), source-routing /
reconciliation strategy, entity-resolution approach, provenance model, and
cloud-vs-air-gapped component map.
