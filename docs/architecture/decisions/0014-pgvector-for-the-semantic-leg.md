# 0014, pgvector for the semantic-leg vector store

- **Status:** Accepted (2026-06-05)
- **Deciders:** Ariadne maintainers
- **Supersedes / superseded by:** none (extends [ADR-0004](0004-postgres-over-redis-for-relational-store.md) and [ADR-0007](0007-hybrid-retrieval-fulltext-first.md))

## Context

The unstructured `Document` leg ([ADR-0006](0006-dataset-agnostic-pipeline.md))
does **hybrid** retrieval: a lexical (full-text) pass and a semantic
(vector-similarity) pass fused by Reciprocal Rank Fusion ([ADR-0007](0007-hybrid-retrieval-fulltext-first.md)).
The semantic leg is implemented as a `pgvector` column with an HNSW cosine index
(`src/ariadne/unstructured/document_store.py`), queried through the same
`postgres-mcp` `execute_sql` tool as everything else.

That choice was made *implicitly* — pgvector rode in on the Postgres relational
decision (ADR-0004) and ADR-0007's "stay in one store" driver — but it was never
weighed on its own against the **June 2026** field, which has moved: Redis 8.4
shipped `FT.HYBRID` (native full-text + vector + RRF in one command), dedicated
stores (Qdrant) got faster filtered search, and in-Postgres ANN extensions
(pgvectorscale's StreamingDiskANN, VectorChord) now beat stock pgvector by
multiples. This ADR ratifies the vector **engine** with that field in view, and
records the scale threshold and upgrade path so the choice is auditable rather
than inherited.

## Decision drivers

- **One auditable store.** Every cited fact must be traceable through the single
  access-controlled `execute_sql` boundary (ADR-0003/0004/0007). A second store
  splits the audit trail and the access-control surface — the spine of the rigor
  story.
- **Scale is small-to-medium.** The corpora are email bodies (synthetic, Enron,
  Avocado) — tens of thousands to low millions of chunks, single-node, read-only
  at query time. Not a billion-vector, high-concurrency workload.
- **Air-gappable (ADR-0012).** The semantic leg must run in-enclave with a local
  embedder (ADR-0007/0008) and no new egress or managed service.
- **Lean dependencies.** Add infrastructure only when a *measured* need justifies
  it; a pre-release project should not pre-pay for scale it does not have.
- **Don't trap ourselves.** Whatever we pick must have a credible upgrade path if
  recall-at-throughput later becomes a bottleneck.

## Considered options

### A. pgvector (chosen)

`vector` column + HNSW cosine index in the existing Postgres, fused with the
lexical leg by RRF, queried via `postgres-mcp`.

- **Pros:** zero new service or audit boundary — the semantic leg is just another
  column in the access-controlled store; transactional consistency with the
  relational + full-text data; runs in-enclave with a local embedder; the 2026
  consensus is "pgvector if you already run Postgres" up to ~tens of millions of
  vectors, which is well above this workload; pgvector 0.8 added iterative index
  scans that fixed the old filtered-query recall cliff. **In-engine upgrade path
  without changing the architecture:** drop in pgvectorscale (StreamingDiskANN)
  or VectorChord (≈3× faster queries at equal recall, ≈20× faster index build)
  if scale grows — same SQL, same `execute_sql` audit boundary.
- **Cons:** stock HNSW must fit in RAM and slows above ~5–10M vectors; needs
  Postgres tuning for large indexes; not sub-millisecond. None bind at this
  scale, and the upgrade path covers the growth case.

### B. Qdrant (dedicated vector database)

- **Pros:** best-in-class filtered-search performance; built for 10M+ vectors and
  high query concurrency; self-hostable in Rust.
- **Cons:** a second service and a **second audit/access-control surface**,
  splitting the provenance model (rejected on this ground in ADR-0004/0007); its
  advantages only materialize above ~tens of millions of vectors and heavy
  concurrent filtering — scale this project does not have. "pgvector if you have
  Postgres, Qdrant if you don't," and we have Postgres.

### C. Redis 8.4 (vector sets + `FT.HYBRID`)

- **Pros:** genuinely changed since ADR-0004 — `FT.HYBRID` now does full-text +
  vector + RRF natively in one command; sub-millisecond in-memory reads.
- **Cons:** same category mismatch ADR-0004 already settled — Redis is not the
  system-of-record, weakening the durability/auditability the governance story
  needs; adding it *only* for vectors re-splits the single store ADR-0007 keeps
  unified; in-memory means RAM-bound and a separate persistence/operational
  story. The new hybrid feature is real but does not outweigh the audit-trail
  cost when Postgres already does hybrid in-store.

### D. Embedded vector store (sqlite-vec, LanceDB)

- **Pros:** no service at all; attractive for the air-gapped fork.
- **Cons:** still a *second* store and a separate audit trail alongside the
  Postgres evidence of record; the air-gapped fork (ADR-0012) already keeps
  Postgres in-enclave, so an embedded store adds a split without removing a
  dependency. No net win here.

## Decision

**Adopt option A.** pgvector is the semantic-leg vector store, fused with the
in-Postgres lexical leg by RRF, queried through the one `postgres-mcp`
`execute_sql` boundary. Named **in-engine** upgrade path, taken only when
recall-at-throughput is a *measured* bottleneck (not before): pgvectorscale
(StreamingDiskANN) or VectorChord, both Postgres extensions that preserve the
single-store audit trail. A dedicated vector DB is reconsidered only if the
corpus crosses ~tens of millions of vectors with high concurrent filtering — a
threshold this workload is not near.

## Consequences

- The semantic leg stays a column in the one access-controlled store; provenance
  and access control remain single-surface.
- Growth is handled in-engine (pgvectorscale / VectorChord) without re-architecting
  or splitting the audit trail; migrating off Postgres is explicitly *not* on the
  near path.
- Redis 8.4's native hybrid search is acknowledged and deliberately not adopted;
  if a future need inverts the trade (e.g. a hot low-latency cache tier becomes
  first-class), this ADR is superseded rather than edited.
- The decision is now documented with a scale threshold, so "why not Qdrant /
  Redis?" has a dated, auditable answer.

## Sources

- [pgvector vs Qdrant: when each wins (2026)](https://open-techstack.com/blog/pgvector-vs-qdrant-2026/) — "pgvector if you have Postgres, Qdrant if you don't"; dedicated DB rarely justified below tens of millions of vectors.
- [Vector database benchmarks 2026 (pgvector 0.9, Qdrant, Weaviate, Milvus, LanceDB)](https://callsphere.ai/blog/vector-database-benchmarks-2026-pgvector-qdrant-weaviate-milvus-lancedb)
- [pgvector 0.8.0 on Aurora — iterative scans fix the filtered-recall cliff](https://aws.amazon.com/blogs/database/supercharging-vector-search-performance-and-relevance-with-pgvector-0-8-0-on-amazon-aurora-postgresql/)
- [VectorChord vs pgvector vs pgvectorscale — memory/disk comparison](https://blog.vectorchord.ai/vector-search-over-postgresql-a-comparative-analysis-of-memory-and-disk-solutions) — ≈3× faster queries, ≈20× faster index build vs stock HNSW.
- [Redis 8.4 hybrid search (`FT.HYBRID`, RRF + linear combination)](https://redis.io/blog/revamping-context-oriented-retrieval-with-hybrid-search-in-redis-84/)
