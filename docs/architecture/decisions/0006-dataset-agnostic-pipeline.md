# 0006, Dataset-agnostic pipeline (canonical schema + adapters)

- **Status:** Accepted (2026-06-03)
- **Deciders:** Ariadne maintainers
- **Supersedes / superseded by:** none

## Context

SCADS demo feedback asked the harness to handle sensemaking on real corpora
(Enron, Avocado/LDC2015T03) beyond the synthetic Neo4j graph, and to make adding
a dataset straightforward for future developers. The question is how to structure
that expansion without re-wiring stores, re-implementing governance, or coupling
dataset-specific concerns into the agent/connectors/eval harness.

See the full design spec at
[`docs/superpowers/specs/2026-06-03-multi-dataset-pipeline-design.md`](../../superpowers/specs/2026-06-03-multi-dataset-pipeline-design.md).

## Decision drivers

- **Future-dev extensibility:** one file to touch when adding a new dataset.
- **Governance choke point:** access-control and PII handling must attach once,
  not per-dataset wiring.
- **Avoid N×M coupling** between datasets and stores.

## Considered options

### A. Canonical schema + adapter contract + registry (chosen)

Four canonical records (`Entity`, `Relationship`, `Document`, `Attribute`), a
`DatasetAdapter` protocol, and a `DATASETS` registry. A dataset-agnostic indexer
fans canonical records into the stores. The agent, skill, connectors, and eval
harness never change.

- **Pro:** two adapters per source instead of N×M point-to-point translation;
  small blast radius (one adapter file per dataset); governance attaches at the
  canonical layer once; recognized 2026 enterprise-integration pattern.
- **Con:** someone owns the canonical schema and its versioning, the schema is
  a shared contract that must be evolved carefully.

Guard the two named pitfalls: the **"god model"** (keep core records minimal;
dataset-specific fields live in `attributes`/`metadata` dicts, never widen the
core records) and **schema ownership/versioning** (the schema is owned here;
bump `SCHEMA_VERSION` on any breaking change).

### B. Per-dataset bespoke setups

Each dataset gets its own store wiring and tooling.

- **Pro:** fast for one or two datasets.
- **Con:** re-wires stores and re-implements governance for every new corpus;
  the opposite of "easy to add a dataset."

### C. Heavy ingestion framework as the architecture (LlamaIndex / Unstructured / Docling)

Adopt an ingestion framework as the integration contract.

- **Pro:** broad out-of-the-box parsing support.
- **Con:** the framework's abstractions become the contract, not ours; conflicts
  with the lean MCP-connector design; weaker control over provenance and
  access-control. An adapter *may* use such a library internally for parsing,
  just not as the architecture.

## Decision

**Adopt option A.** Four canonical records (`Entity` / `Relationship` /
`Document` / `Attribute`) + a `DatasetAdapter` protocol + a `DATASETS` registry.
A dataset-agnostic indexer fans records into Neo4j (entities + relationships),
Postgres full-text + pgvector (documents), and the relational store (attributes).
Guard the two named pitfalls: keep core records minimal (dataset-specific fields
in `attributes`/`metadata`), and version the schema (`SCHEMA_VERSION`).

## Consequences

- Adding a dataset touches one adapter file and its eval fixtures. The
  agent, `entity-workup` skill, connectors, and eval harness do not change.
- Governance is uniform across datasets: every adapter declares
  `access ∈ {public, restricted}`; a restricted adapter is gated behind an
  explicit authorized-access flag.
- The canonical schema is a versioned shared contract, breaking changes require
  a `SCHEMA_VERSION` bump and coordinated adapter updates.

## Sources

- [Canonical Data Model guide (datadriven.io, 2026)](https://datadriven.io/data-modeling/canonical-data-model)
- [Enterprise Integration Patterns, Canonical Data Model](https://www.enterpriseintegrationpatterns.com/patterns/messaging/CanonicalDataModel.html)
