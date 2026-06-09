# Architecture

Design notes for Ariadne's harness. The shape below is implemented end to end, from
heterogeneous retrieval and analytic rigor through distribution and an adaptive,
self-improving harness; the [Decision log](decisions/index.md) records each contestable
choice, and the [Roadmap](../roadmap.md) tracks what is built versus planned.

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
an **orchestrator-worker** design: a lead agent runs the *gather → act → verify →
repeat* loop and dispatches context-isolated subagents (one per source) that
retrieve via MCP and hand back only their findings. **GraphRAG** traverses
organizational hierarchies; multimodal evidence is fused **agentically** by
converting imagery/video to structured text before reasoning over it.

Today the loop runs as a **single lead agent** querying the stores directly.
Subagent fan-out is deferred as YAGNI (trigger: store count ≥4 or a measured
latency bottleneck; the provenance blocker is dissolved now that the SDK hook
fires inside subagents) per [ADR-0005](decisions/0005-defer-subagent-fan-out.md)
and [ADR-0015](decisions/0015-subagent-fan-out-design.md). The diagram below shows
the target shape.

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

A developer adds a corpus by writing one **adapter** that maps raw data to the
canonical schema below; a dataset-agnostic indexer fans the records into the
stores. The agent, `entity-workup` skill, connectors, and eval harness never
change. Governance (access-control, PII gating) attaches at the canonical layer
once, not per dataset.

<div class="schema-model" markdown="0">
  <svg class="links" viewBox="0 0 100 72" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
    <line x1="50" y1="28.8" x2="16" y2="15.8"></line>
    <line x1="50" y1="28.8" x2="84" y2="15.8"></line>
    <line x1="50" y1="28.8" x2="50" y2="63.4"></line>
  </svg>
  <div class="tbl tbl-attribute"><div class="tbl-h">Attribute</div><div class="tbl-r">key</div><div class="tbl-r">value</div></div>
  <div class="tbl tbl-document"><div class="tbl-h">Document</div><div class="tbl-r">text</div><div class="tbl-r">source</div></div>
  <div class="tbl tbl--hub tbl-entity"><div class="tbl-h">Entity</div><div class="tbl-r">name</div><div class="tbl-r">type</div><div class="tbl-r">aliases[]</div></div>
  <div class="tbl tbl-relationship"><div class="tbl-h">Relationship</div><div class="tbl-r">type</div><div class="tbl-r">source &rarr; Entity</div><div class="tbl-r">target &rarr; Entity</div></div>
  <div class="rel-label" style="left: 33%; top: 31%;">1 : N</div>
  <div class="rel-label" style="left: 67%; top: 31%;">mentions</div>
  <div class="rel-label" style="left: 50%; top: 64%;">source · target</div>
</div>

**Free-text retrieval** is hybrid: Postgres full-text (`tsvector` GIN,
`websearch_to_tsquery`) fused with pgvector semantic search via Reciprocal Rank
Fusion. The agent reaches it through the in-process `mcp__ariadne__hybrid_search`
tool (opt-in `--semantic`), per
[ADR-0007](decisions/0007-hybrid-retrieval-fulltext-first.md).

A **second adapter** (the Enron email corpus, via HF streaming) plugs in through
the same canonical schema with no change to the agent, connectors, or eval
harness, proving the seam generalizes beyond the synthetic graph. See
[ADR-0006](decisions/0006-dataset-agnostic-pipeline.md) for the decision record
and the [pipeline design spec](../superpowers/specs/2026-06-03-multi-dataset-pipeline-design.md)
for the full design.

## Distribution

Ariadne is consumable as an MCP server (the `workup` tool runs the full harness
and returns a cited analytic note) from any MCP client, with a Claude Code
plugin wrapper for one-click install and slash-command UX, per
[ADR-0009](decisions/0009-distribute-as-mcp-server-and-plugin.md). It is published to PyPI as
`ariadne-sensemaking` (`uvx ariadne-sensemaking`).

## Adaptive & self-improvement

Beyond the built-in datasets, Ariadne **adapts** to a user's own store and **improves from
experience** ([ADR-0020](decisions/0020-adaptive-self-improving-ariadne.md)). Every change rides
one cycle, turning around a core the loop can never touch:

<div class="figure-cycle" markdown="0">
  <svg class="cycle-ring" viewBox="0 0 100 86" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
    <circle class="ring" cx="50" cy="47.3" r="37"></circle>
    <path class="tip" d="M-2.4,-2.4 L3.4,0 L-2.4,2.4 Z" transform="translate(81,27) rotate(57)"></path>
    <path class="tip" d="M-2.4,-2.4 L3.4,0 L-2.4,2.4 Z" transform="translate(50,84.3) rotate(180)"></path>
    <path class="tip" d="M-2.4,-2.4 L3.4,0 L-2.4,2.4 Z" transform="translate(19,27.2) rotate(303)"></path>
  </svg>
  <div class="cyc-node cyc-propose"><b>Propose</b><span>the agent drafts a declarative artifact</span></div>
  <div class="cyc-node cyc-ratify"><b>Ratify</b><span>a human approves or rejects</span></div>
  <div class="cyc-node cyc-freeze"><b>Freeze</b><span>it becomes config the gates check</span></div>
  <div class="cyc-core">eval gate · governance<small>the loop can never edit this</small></div>
</div>

The loop edits only ratified artifacts; the eval harness it is scored against stays off-limits,
so an agent can never quietly grade its own work.

- **Adapt (Axis A):** introspect a real Postgres, propose a mapping into the canonical schema
  (deterministic or LLM), ratify it, and the existing indexer / workup / eval run unchanged on
  the user's data (`ariadne map`); plus a declarative user ontology and a dynamic MCP surface
  that activates a ratified store at runtime.
- **Learn (Axis B):** distil a high-scoring workup into a reusable analytic skill
  (`ariadne distil`), reflect on a low-scoring one and propose grounded, gold-free refinements
  (`ariadne reflect`), deepen an existing skill from a new run (`distil --into`), and measure
  whether a learned change actually helps before adopting it (`ariadne compare`: repairs net of
  regressions on the same eval instance). The eval harness is the external verifiable reward the
  loop can never edit.

## Knowing it works

The brief's central challenge is *"how do you know what works?"* Ariadne answers it
with a tiered eval pyramid: cheap, exhaustive checks on every output at the base;
expensive, sampled judgment at the apex.

<div class="eval-pyramid" markdown="0">
  <div class="tier" style="--w: 48%; --tint: var(--ari-scarlet);">
    <div class="tk">LLM-as-judge</div>
    <div class="td">ICD-203 analytic-standards rubric, on a sample of survivors</div>
    <div class="tmeta">slow · costly · sampled</div>
  </div>
  <div class="tier" style="--w: 74%;">
    <div class="tk">Entailment (NLI)</div>
    <div class="td">HHEM-2.1 checks each cited claim against its evidence</div>
    <div class="tmeta">fast · local · per claim</div>
  </div>
  <div class="tier" style="--w: 100%; --tint: var(--ari-thread);">
    <div class="tk">Deterministic floor</div>
    <div class="td">citation gate + ICD-203 tradecraft lint on every output</div>
    <div class="tmeta">microseconds · $0 · every claim</div>
  </div>
  <p class="pyramid-axis">volume falls and cost rises toward the apex</p>
</div>

## Still open

The pieces not yet built or still settling:

- **Multimodal fusion** (Phase 3): image/video/OCR extraction and cross-modal
  evidence fusion.
- **Subagent fan-out**: parallel per-source workers, deferred as YAGNI until store
  count ≥4 or a measured latency bottleneck (design specified in
  [ADR-0015](decisions/0015-subagent-fan-out-design.md)).
- **Entity resolution across stores**: currently a stable shared key per entity;
  a richer resolver remains an open research question.
- **Open-weight validation**: which self-hostable model clears the eval bar
  through the air-gap seam ([open-weight validation](../research/open-weight-validation.md)).
