# SCADS integration interfaces

> Ariadne is the SCADS **umbrella** sensemaking layer: it should *integrate*
> sibling-project outputs, graph extraction, entity resolution, multimodal
> indexing, as callable tools through defined interfaces, **not duplicate**
> them. This page is the contract a sibling tool implements to plug in. Every
> claim points at real code; fix the doc if it drifts.

## The build-vs-expose decision

For each capability Ariadne needs, the boundary question is **build it here** or
**expose a sibling as a tool**. Default to *expose* when a sibling already owns
the capability (its extraction, resolution, or indexing is the system of record);
*build* only the thin orchestration that routes to it and reconciles its output.
Ariadne owns the analytic loop, provenance, gates, and eval, not the data
infrastructure.

There are two integration ports: a **runtime** port (a sibling as a live tool)
and an **ingest** port (a sibling's output as indexed evidence). A sibling may
use either or both. Both must honor the evidence, provenance, and governance
contracts below.

## Port A (runtime): a sibling as an MCP tool family

A sibling that answers queries at analysis time (an entity-resolution service, a
live graph API, a multimodal retriever) integrates as its own **read-only MCP
tool family**, exactly like Ariadne's graph / relational / hybrid-search families.

The contract:

- **Tools are namespaced** `mcp__<sibling>__*` and **read-only**: they retrieve
  and return evidence, never mutate a store.
- **Register three things** in `build_options` (`cli.py`): the server in
  `mcp_servers`, its tools in `allowed_tools`, and a `PostToolUse` `HookMatcher`
  (`mcp__<sibling>__.*`) so its calls land in the provenance ledger.
- **Add the prefix** to `EVIDENCE_TOOL_PREFIXES` (`provenance/hook.py`) so each
  call gets a `gN` id and its results are citable.
- **Give the lead a routing rule** in the `entity-workup` skill (when to call
  this family, and the shared key that resolves the same entity across stores).

Reference families: `graph/neo4j_server.py`, `relational/postgres_server.py`,
`unstructured/search_tool.py`. Decisions:
[ADR-0002](architecture/decisions/0002-official-mcp-connectors-over-hand-rolled.md)
(prefer the sibling's own battle-tested server over a hand-rolled wrapper),
[ADR-0009](architecture/decisions/0009-distribute-as-mcp-server-and-plugin.md)
(Ariadne itself is also an MCP server, so siblings compose symmetrically).

## Port B (ingest): a sibling's output via the canonical schema

A sibling that *produces* a corpus (an extractor emitting entities/relationships,
a multimodal indexer emitting document text) integrates at the **canonical
schema** seam: it writes a `DatasetAdapter` that maps its output to
`Entity` / `Relationship` / `Document` / `Attribute`. Ariadne's indexer loads the
canonical records into the stores; nothing downstream changes.

The contract (`datasets/canonical.py`, `datasets/base.py`):

- Map every record to one of the four canonical types; key entities by a stable
  `alias`/id so they resolve across stores (this is what makes cross-store
  reconciliation possible).
- Register the adapter in `DATASETS`; it becomes `ariadne index --dataset <name>`
  and `ariadne workup … --dataset <name>`.
- Ingestion is the *only* place that touches the sibling's format, the same seam
  that lets an air-gapped deployment swap a streaming source for a local one
  ([ADR-0006](architecture/decisions/0006-dataset-agnostic-pipeline.md),
  [ADR-0012](architecture/decisions/0012-cloud-vs-air-gapped-deployment-fork.md)).

Reference adapters: the synthetic and Enron adapters in `datasets/`.

## The contracts both ports honor

Whichever port a sibling uses, three properties are non-negotiable because the
analytic product's trustworthiness depends on them:

1. **Evidence + provenance.** Every retrieval is a tool call the provenance hook
   can stamp with a `gN` id; results must be quotable so the synthesis can cite
   `[cite:gN]`. A claim with no resolvable citation fails the gate
   (`provenance/citations.py`).
2. **Read-only governance.** Integration tools retrieve, never mutate. The
   read-only audit scans the ledger for any write verb and flags a violation,
   even one a connector blocked (`provenance/governance.py`).
3. **Entity resolution across the seam.** Expose a stable shared key per entity so
   the lead can reconcile the same entity across the sibling's output and the
   other stores (corroborate agreements, flag conflicts).

## What a sibling does *not* need to provide

Ariadne owns, and a sibling should not re-implement, the analytic loop, the
provenance ledger and citation gate, the ICD-203 tradecraft lint and rubric, the
planted-needle / reconciliation eval, and the observability layer. A sibling
brings a capability; Ariadne brings the rigor and orchestration around it. See
the [workflow patterns](patterns.md) for the reusable shapes.
