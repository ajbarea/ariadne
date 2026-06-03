# 0004 — Keep Postgres (not Redis) for the relational store

- **Status:** Accepted (2026-06-03)
- **Deciders:** Ariadne maintainers
- **Supersedes / superseded by:** none

## Context

Ariadne's relational connector ([ADR-0003](0003-postgres-mcp-restricted-mode.md))
holds the structured-attribute store: a `personnel` table keyed by `alias` to the
graph's `Person.alias`, queried with read-only SQL. Its jobs are (1) supply
structured facts the graph does not hold, (2) support **cross-store entity
resolution** by shared key, and (3) surface relational ties — e.g. *"who else
shares this `cover_employer`?"*, the planted cross-modality needle. Every fact it
returns must be **auditable**, because the analytic product cites its sources.

The question raised: would **Redis** be a better backing store than Postgres
(or any SQL store) for this role?

## Decision drivers

- The role is *relational queries over structured records*, including set/join
  questions ("who shares attribute X").
- The brief's central challenge is **specification, validation, and governance**
  (quality / security / data integrity). Auditable, durable evidence is not
  optional — it is the spine of the rigor layer.
- Keep the stack as small as the work allows; add infrastructure only when a
  measured need justifies it.

## Considered options

### A. Postgres (current) — relational store via `postgres-mcp` Restricted Mode

- **Pros:** native relational joins and set queries; ACID and durable, so cited
  evidence is reproducible and auditable; read-only is enforceable (restricted
  mode + `pglast` guard, see ADR-0003); `pgvector` keeps a future vector
  connector on the same engine; the 2026 trend consolidates agent stacks *into*
  Postgres (pgvector, `SKIP LOCKED`, `LISTEN/NOTIFY` displacing classic Redis
  patterns).
- **Cons:** disk-backed, so not sub-millisecond; one more service to run than an
  in-memory cache (but we already run it).

### B. Redis as the relational store

- **Pros:** sub-millisecond reads; trivial for hot key lookups and ephemeral
  state; Redis 8 folds in RediSearch (secondary indexing + vector search).
- **Cons:** **no relational join engine** — the "who shares this attribute"
  query that defines the needle is awkward and non-native; it is a key-value /
  data-structure store, not a system of record, and "provides no
  memory-management logic" of its own; using it as the evidence store weakens the
  durability/auditability the governance story depends on. This is a **category
  mismatch** for the role, not a close performance call.

### C. Another SQL store (SQLite, MySQL, DuckDB)

- **Pros:** also relational/auditable.
- **Cons:** no advantage over Postgres for this workload, and we lose the
  ecosystem we already depend on (`pgvector`, the hardened `postgres-mcp`
  server). No reason to switch.

## Decision

**Keep Postgres for the relational store. Do not swap to Redis.** A sensemaking
workup is not a sub-millisecond hot path, so Redis's one real advantage does not
apply, while its lack of relational/auditable semantics directly undercuts the
connector's purpose. Consensus best practice (2026): *start on Postgres for
reliability and auditability; add Redis only when latency profiling proves a
bottleneck.* We have no such bottleneck.

**Redis still has a place in Ariadne — as an addition, not a replacement:**

1. **Agent memory / session layer** for long investigations (the lead agent
   persisting its plan and working context). The official
   [`redis/agent-memory-server`](https://github.com/redis/agent-memory-server)
   exposes an MCP interface with sub-millisecond reads and is a strong fit. This
   is the working-memory plane, *not* the evidence store.
2. **One candidate** for the still-open vector/unstructured connector (Redis 8 +
   RediSearch vector search) — but `pgvector` is the consolidation-friendly rival
   there. That fork is settled when we build the connector, not now.

## Consequences

- No code change: the relational connector stays as built.
- The evidence store remains durable and auditable, consistent with the
  provenance/citation model.
- Redis is now scoped to two additive, optional roles; revisit them when store
  count or investigation length creates real pressure.

## Sources

- [SitePoint — Agent state: Redis vs Postgres](https://www.sitepoint.com/state-management-for-long-running-agents-redis-vs-postgres/)
- [Alongside — Why Postgres beats Redis for agent memory/session state](https://www.alongside.team/blog/redis-vs-postgresql-agent-memory-session-state)
- [PingCAP — Best database for AI agents (2026)](https://www.pingcap.com/compare/best-database-for-ai-agents/)
- [`redis/mcp-redis`](https://github.com/redis/mcp-redis) · [`redis/agent-memory-server`](https://github.com/redis/agent-memory-server)
