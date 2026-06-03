# Ariadne — design: dataset-agnostic sensemaking pipeline

> **Status:** design, awaiting review. Authored 2026-06-03.
> **Driver:** SCADS demo feedback — prove the harness handles sensemaking on
> real corpora beyond the synthetic Neo4j graph, and make adding a dataset easy
> for future devs. Target corpora: **Enron** (public) and **Avocado / LDC2015T03**
> (license + PII gated).
> **Source research (June 2026):** canonical-data-model integration pattern;
> pgvector ≤10M-vector guidance; hybrid (BM25 + vector) retrieval; deterministic
> email-header graphing. Recorded inline below.

## Goal

One pipeline, many datasets. A future dev adds a corpus by writing one **adapter**
that maps raw data to a small **canonical schema**; a dataset-agnostic indexer
fans those records into the standard stores; the agent, `entity-workup` skill,
connectors, and eval harness do not change. Litmus test: *write an adapter,
register it, run `ariadne workup <entity> --dataset <name>`.*

## Decisions (research-grounded)

### D1 — Canonical schema + adapter contract + registry

`# research(2026-06):` The canonical-data-model pattern replaces N×M point-to-point
translation with two adapters per source (to/from a shared model). Justified here
(3+ datasets, explicit extensibility goal); the documented anti-case is one-off
prototypes, which this is not. Guard against the two named pitfalls: the **"god
model"** (keep the core minimal; dataset-specific fields live in `attributes`
dicts, never widen the core records) and **ownership/versioning** (the schema is
owned here; bump a `schema_version` on change).
Sources: [Canonical Data Model guide (2026)](https://datadriven.io/data-modeling/canonical-data-model),
[Enterprise Integration Patterns](https://www.enterpriseintegrationpatterns.com/patterns/messaging/CanonicalDataModel.html).

### D2 — Hybrid retrieval, full-text first; pgvector for the semantic leg

`# research(2026-06):` Hybrid (BM25-style full-text + dense vectors, fused with
RRF) beats either alone, and full-text is essential for the **exact identifiers**
that dominate email entity lookup (addresses, names, codenames). Full-text is the
must-have first leg — it needs **no embedding step**, so PII content never leaves
the box to be embedded (Avocado/air-gap win). pgvector adds the semantic leg:
2026 consensus is "pgvector if you already run Postgres and are under 10M
vectors"; Enron ≈500K emails sits an order of magnitude inside that. Both legs
live in the **one access-controlled Postgres store** already built. Escape hatch
when scale grows: pgvectorscale (StreamingDiskANN) or a dedicated store (Qdrant).
Reconciles with Anthropic's "default to agentic search, add semantic only when
needed." → **ADR-0006**.
Sources: [hybrid BM25+vector (2026)](https://techbytes.app/posts/hybrid-rag-search-bm25-embeddings-deep-dive-2026/),
[full-text for RAG](https://redis.io/blog/full-text-search-for-rag-the-precision-layer/),
[vector DB benchmarks 2026](https://callsphere.ai/blog/vector-database-benchmarks-2026-pgvector-qdrant-weaviate-milvus-lancedb).

### D3 — Email → graph from headers deterministically; LLM body-extraction deferred

`# research(2026-06):` The communication graph (who→whom, when) comes from email
**headers** — deterministic, cheap, reliable. LLM entity extraction is "biased
toward frequent entities" and adds cost/error for what headers give free; it is a
later semantic-enrichment enhancement over bodies, not the backbone.
Sources: [LLM-powered enterprise KGs](https://arxiv.org/abs/2503.07993).

### D4 — Governance lives at the canonical layer

An adapter declares `access ∈ {public, restricted}`. A `restricted` adapter
(Avocado) reads only from a gitignored local path, never commits or pushes, and is
gated behind an explicit authorized-access flag. Whether PII content may reach a
cloud model is flagged for the cloud-vs-air-gap fork, not solved here. Putting
governance at the canonical choke point means every new dataset inherits it.
→ **ADR-0007**.

## Canonical schema (the contract — keep minimal)

| Record | Fields | Lands in |
| ------ | ------ | -------- |
| `Entity` | `id`, `type`, `name`, `aliases`, `attributes: dict` | graph node |
| `Relationship` | `src`, `dst`, `type`, `attributes: dict` | graph edge |
| `Document` | `id`, `text`, `source_entity_ids`, `metadata: dict`, `modality` | full-text + vector (text); relational (metadata) |
| `Attribute` | `entity_id`, `key`, `value` | relational row |

`Entity.type` is open (`person`, `org`, `unit`, `topic`, …): **person-centric is
the v1 primary entity, but topics/events are addable later with no schema change.**

## Adapter contract

```python
class DatasetAdapter(Protocol):
    name: str                                  # registry key / --dataset value
    entity_type: str                           # primary entity, e.g. "person"
    access: Literal["public", "restricted"]
    def load(self) -> Iterable[Canonical]: ...        # Entity|Relationship|Document|Attribute
    def eval_fixtures(self) -> list[NeedleFixture]: ... # known-answer needles
```

Registered in `DATASETS = {...}`, selected by `--dataset` (same idiom as the
existing `FIXTURES` registry).

## Architecture

```
ariadne workup <entity> --dataset <name>
   │
   ├─ adapter.load()  ──►  canonical records (Entity/Relationship/Document/Attribute)
   │                         │  (restricted adapters: local-only, access-gated — D4)
   ├─ indexer  ──►  Neo4j (Entity+Relationship)
   │                Postgres: full-text + pgvector (Document.text), metadata+Attribute
   │
   └─ agent loop (UNCHANGED): gather → act → verify → synthesize → cited note + ledger + eval
```

## Components

| Unit | Path | Responsibility | Depends on |
| ---- | ---- | -------------- | ---------- |
| **canonical schema** | `src/ariadne/datasets/canonical.py` | the four record dataclasses + `schema_version` | — (pure) |
| **adapter contract + registry** | `src/ariadne/datasets/base.py` | `DatasetAdapter` Protocol + `DATASETS` registry + lookup | canonical |
| **indexer** | `src/ariadne/datasets/indexer.py` | fan canonical records into the stores; idempotent; per-dataset namespace | store clients |
| **synthetic adapter** | `src/ariadne/datasets/synthetic.py` | wrap the existing seed graph as the first adapter (proves the seam) | canonical |
| **enron adapter** | `src/ariadne/datasets/enron.py` | HF `corbt/enron-emails` → canonical (headers→graph, body→Document) | canonical, HF datasets |
| **avocado adapter** | `src/ariadne/datasets/avocado.py` | local PST/export → canonical; `access="restricted"` | canonical, local data |
| **hybrid retrieval** | `src/ariadne/unstructured/` | full-text + pgvector search exposed to the agent (via Postgres MCP) | Postgres |
| **eval fixtures** | per-adapter `eval_fixtures()` | dataset-specific known-answer needles | needle harness |

## Email → canonical mapping (Enron adapter)

- Each message → `Entity(person)` for sender + each recipient; `Relationship(EMAILED,
  src=sender, dst=recipient, attributes={count, first_seen, last_seen})`.
- Body → `Document(text=body, metadata={subject, ts, folder}, source_entity_ids=[…])`.
- Account facts (display name, folder owner) → `Attribute` rows.
- No LLM in the v1 path (D3).

## Governance (Avocado, D4)

- Raw Avocado data lives under a gitignored path (reuses the existing `data/`
  ignore); never committed, never pushed.
- The `restricted` adapter refuses to run unless an explicit authorized flag/env
  is set (e.g. `ARIADNE_ALLOW_RESTRICTED=1`).
- Malware caveat (loveletter in ~27 msgs): the adapter ingests text/headers only;
  attachments are not executed.
- PII-to-cloud-model handling is recorded as an open fork question, not resolved.

## Testing strategy

- **Unit (hermetic):** canonical record validation; registry lookup; indexer fan
  with a fake store; Enron mapping over a few recorded raw messages → expected
  canonical records; restricted-adapter access gate (refuses without the flag);
  hybrid-retrieval ranking over a fixture corpus (full-text + vector legs, fusion).
- **Integration (`-m integration`):** Enron sample loaded into testcontainers
  Neo4j + Postgres(+pgvector); a live `workup --dataset enron` behind a key check
  surfaces a known Enron tie with citations; eval `--fixture` scores it grounded.

## Build order (each independently shippable)

- **A — Abstraction:** canonical schema + contract + registry + indexer; refactor
  the existing synthetic graph into the first adapter (no new data, proves the seam).
- **B — Enron:** HF adapter + hybrid retrieval connector (full-text first, then
  pgvector) → generalization + tri-modal sensemaking on real data.
- **C — Avocado:** restricted adapter with access-control governance; built now,
  populated when licensed data is provided.

## Out of scope (later)

LLM body entity-extraction; cross-dataset entity resolution; the cloud-vs-air-gap
PII fork; subagent fan-out (deferred, ADR-0005).

## Success criteria (done = all true)

1. `ariadne workup <entity> --dataset synthetic` reproduces today's behaviour
   through the new adapter path (no regression).
2. `--dataset enron` loads a real email slice and produces a cited note surfacing
   a known communication tie; eval scores it grounded.
3. The Avocado adapter exists, is `restricted`, and refuses to run without the
   authorized flag (no data required to test the gate).
4. Adding a dataset touches only a new adapter file + its eval fixtures.
5. `make lint` + `make test-unit` green; integration green with a key.
6. ADR-0006 (hybrid retrieval) and ADR-0007 (dataset governance) written.
