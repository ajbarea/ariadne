# Architecture

Design notes for Ariadne's harness. **Deliberately thin until the research
resolves the open questions** in the [Roadmap](../roadmap.md). Hardening a design
before then risks building against the wrong fork.

## Building blocks

The orchestration layer is the **Claude Agent SDK**. Its primitives are the
vocabulary every design choice is expressed in:

- **Tools**: callable retrieval/processing functions (in-process or via MCP).
- **Skills**: packaged multi-step analytic procedures (e.g. `entity-workup`).
- **Hooks**: lifecycle interceptors for provenance, authorization, and audit.
- **Subagents**: context-isolated workers for parallel per-source retrieval.
- **MCP**: the connector standard surfacing graph / SQL / vector stores as tools.

See the [Claude Agent SDK Reference](../research/claude-agent-sdk-reference.md)
for the full doc-cited mechanics.

## Decisions

Significant, contestable choices, *which store, which connector, what was
deferred and why*, live in the [Decision log](decisions/index.md) as ADRs: the
single place to point when asked "why this instead of that?" Notable examples:
the Postgres-over-Redis comparison ([ADR-0004](decisions/0004-postgres-over-redis-for-relational-store.md))
and the dataset-abstraction approach ([ADR-0006](decisions/0006-dataset-agnostic-pipeline.md)).

## Emerging shape (from the research)

The [best-practice research](../research/best-practice-architecture.md) points to
an **orchestrator-worker** design: a lead agent runs the canonical *gather
context → take action → verify → repeat* loop and dispatches parallel,
context-isolated subagents (each restricted to one source) that retrieve via MCP
connectors and hand back only their findings. **GraphRAG** is the core
capability for traversing organizational hierarchies; multimodal evidence is
fused **agentically** by converting imagery/video to structured text before
reasoning over it.

<div class="arch-diagram" markdown="0">
  <div class="arch-row">
    <div class="arch-node arch-node--input"><span class="arch-node-title">Target entity</span><span class="arch-node-sub">a person, unit, or org node</span></div>
  </div>
  <div class="arch-flow"></div>
  <div class="arch-row">
    <div class="arch-node arch-node--lead"><span class="arch-node-title">Lead agent</span><span class="arch-node-sub">gather → act → verify → repeat</span></div>
  </div>
  <div class="arch-flow"><span class="arch-flow-label">dispatches parallel, context-isolated subagents</span></div>
  <div class="arch-row arch-row--three">
    <div class="arch-node arch-node--worker"><span class="arch-badge">Graph</span><span class="arch-node-title">Neo4j</span><span class="arch-node-sub">relationships via MCP</span></div>
    <div class="arch-node arch-node--worker"><span class="arch-badge">Relational</span><span class="arch-node-title">Postgres</span><span class="arch-node-sub">records via MCP</span></div>
    <div class="arch-node arch-node--worker"><span class="arch-badge">Unstructured</span><span class="arch-node-title">Hybrid search</span><span class="arch-node-sub">text + vector via MCP</span></div>
  </div>
  <div class="arch-flow"><span class="arch-flow-label">findings return to the lead</span></div>
  <div class="arch-row">
    <div class="arch-node arch-node--synth"><span class="arch-node-title">Synthesis</span><span class="arch-node-sub">provenance + citation gate</span></div>
  </div>
  <div class="arch-flow"></div>
  <div class="arch-row">
    <div class="arch-node arch-node--output"><span class="arch-node-title">Cited analytic note</span></div>
  </div>
</div>

## Datasets

A future developer adds a corpus by writing one **adapter** that maps raw data to
the canonical schema (`Entity` / `Relationship` / `Document` / `Attribute`); a
dataset-agnostic indexer fans the records into the stores. The agent,
`entity-workup` skill, connectors, and eval harness never change. Governance
(access-control, PII gating) attaches at the canonical layer once, not per
dataset. Unstructured/free-text evidence is now retrieved via **hybrid retrieval**,
Postgres full-text (`tsvector` GIN, `websearch_to_tsquery`) fused with pgvector
semantic search via Reciprocal Rank Fusion, per
[ADR-0007](decisions/0007-hybrid-retrieval-fulltext-first.md). The agent reaches
this hybrid retrieval via the in-process `mcp__ariadne__hybrid_search` tool
(opt-in `--semantic`), per ADR-0007. A second adapter (the Enron email corpus, via HF streaming)
plugs in through the same canonical schema with no change to the agent,
connectors, or eval harness, demonstrating generalization beyond the synthetic
graph. See [ADR-0006](decisions/0006-dataset-agnostic-pipeline.md)
for the dataset-abstraction decision record and
[`docs/superpowers/specs/2026-06-03-multi-dataset-pipeline-design.md`](../superpowers/specs/2026-06-03-multi-dataset-pipeline-design.md)
for the full design.

## Distribution

Ariadne is consumable as an MCP server (the `workup` tool runs the full harness
and returns a cited analytic note) from any MCP client, with a Claude Code
plugin wrapper for one-click install and slash-command UX, per
[ADR-0009](decisions/0009-distribute-as-mcp-server-and-plugin.md).

## To be written

Once the MVP boundary is set: the end-to-end analytic workflow (entity in →
coordinated tool sequence → cited analytic product), source-routing /
reconciliation strategy, entity-resolution approach, provenance model, and
cloud-vs-air-gapped component map.
