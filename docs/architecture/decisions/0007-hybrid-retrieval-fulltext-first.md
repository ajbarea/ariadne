# 0007 — Hybrid retrieval, full-text first (in-Postgres)

- **Status:** Accepted (2026-06-03)
- **Deciders:** Ariadne maintainers
- **Supersedes / superseded by:** none

## Context

The canonical pipeline (ADR-0006) includes a `Document` leg for unstructured
evidence — email bodies, attachments, free-text records. That leg needs retrieval.
The full design spec
([`docs/superpowers/specs/2026-06-03-multi-dataset-pipeline-design.md`](../../superpowers/specs/2026-06-03-multi-dataset-pipeline-design.md))
calls for **hybrid lexical + semantic retrieval**: a full-text (lexical) pass
and a vector-similarity (semantic) pass whose results are fused. The question
is sequencing — what to build first, and at what dependency cost.

## Decision drivers

- **Exact-identifier lookup dominates.** Entity searches in the email corpora
  (Enron, Avocado) centre on names, addresses, codenames, and short phrases.
  Lexical recall on these terms is high; semantic search adds cost without
  proportional gain at Phase B1.
- **PII must not require an embedding round-trip.** Sending document text to a
  cloud embedding model exposes PII content to a third party before access
  control has been applied. The lexical leg requires no embedding step.
- **Keep dependencies lean.** Every new extension or service is a new failure
  mode for a pre-release project.
- **Stay in the one access-controlled store (per ADR-0004).** All evidence must
  be auditable and traceable through the existing `postgres-mcp` `execute_sql`
  interface. A separate retrieval service would split the audit trail.

## Considered options

### A. Postgres built-in full-text search (chosen)

Generated `tsvector` column + GIN index + `websearch_to_tsquery`, queried via
the existing `postgres-mcp` `execute_sql` tool. Semantic leg (`pgvector` +
local embedding model) added later and fused via Reciprocal Rank Fusion (RRF).

- **Pro:** zero new dependency; no embedding step (PII content never leaves the
  box at Phase B1); exact-term precision on names and addresses; the full-text
  index is queryable through the same `execute_sql` tool already in use.
- **Con:** Postgres's built-in `ts_rank` lacks BM25's IDF weighting, so ranking
  quality is lower than a BM25 extension for longer documents. Acceptable at
  Phase B1; addressable later via a named upgrade path.

### B. Adopt a BM25 extension now (`pg_textsearch` or ParadeDB `pg_search`)

- **Pro:** better term-frequency / inverse-document-frequency ranking out of
  the box.
- **Con:** introduces a new Postgres extension before ranking quality is a
  measured bottleneck; adds complexity earlier than the work justifies.
  `pg_textsearch` (2026 C-native BM25) is the preferred future path when
  ranking quality matters — faster than ParadeDB and not Neon-deprecated — but
  it belongs in a named upgrade, not Phase B1.

### C. Dedicated vector database

Rejected per ADR-0004: consolidate evidence into the one auditable Postgres
store. A separate vector DB splits access control and breaks the provenance
model the analytic product depends on.

## Decision

**Adopt option A.** Ship a generated `tsvector` column, a GIN index, and
`websearch_to_tsquery` queries via the existing `postgres-mcp` `execute_sql`
tool. Named upgrade paths:

1. **`pg_textsearch`** — C-native BM25, faster than ParadeDB, not
   Neon-deprecated — when ranking quality on longer documents becomes a measured
   need.
2. **pgvector + local embedding model** — EmbeddingGemma-300M (primary; small
   footprint, no cloud call); BGE-M3 fallback — for the semantic leg, fused
   with the lexical leg by Reciprocal Rank Fusion. The semantic leg is an
   isolated follow-on that does not change the lexical schema.

## Consequences

- Phase B1 ships the lexical leg with no embedding dependency and no new
  Postgres extension. PII document content does not leave the box.
- The semantic leg is an isolated, additive follow-on: add a `vector` column,
  populate it with a local model, and join the two ranked lists via RRF.
- All retrieval — both legs — stays inside Postgres and is queryable through
  the same `execute_sql` interface, preserving the single-store audit trail.

## Sources

- [PostgreSQL full-text search — `tsvector` and `GIN` indexes](https://www.postgresql.org/docs/current/textsearch-tables.html)
- [TigerData — `pg_textsearch`: BM25 full-text search for Postgres (2026)](https://www.tigerdata.com/blog/pg-textsearch-bm25-full-text-search-postgres)
- [ParadeDB — Hybrid search in PostgreSQL: the missing manual](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual)
