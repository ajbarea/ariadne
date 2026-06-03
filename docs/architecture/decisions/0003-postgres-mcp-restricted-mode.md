# 0003 — Expose Postgres via `postgres-mcp` Restricted Mode

- **Status:** Accepted (2026-06-02)
- **Deciders:** Ariadne maintainers

## Context

Phase 2 adds the relational connector. The agent must run read-only SQL against a
Postgres store, and "read-only" has to be *enforced*, not merely requested — the
agent composes its own queries.

## Decision drivers

- Read-only must survive a hostile or malformed query (no writes, no
  statement-stacking escape).
- Least privilege: expose retrieval/introspection only, not DBA or performance
  tooling.
- Same hardened-server principle as the graph connector
  ([ADR-0002](0002-official-mcp-connectors-over-hand-rolled.md)).

## Considered options

- **[`crystaldba/postgres-mcp`](https://github.com/crystaldba/postgres-mcp)
  ("Postgres MCP Pro") in `--access-mode=restricted`** — read-only transactions
  with execution-time caps; SQL parsed with `pglast` before execution to reject
  `COMMIT`/`ROLLBACK` statement-stacking.
- **Official `@modelcontextprotocol/server-postgres`** — its
  `BEGIN TRANSACTION READ ONLY` guardrail is **bypassable via semicolon
  statement-stacking**, a confirmed SQL-injection through v0.6.2
  ([Datadog Security Labs](https://securitylabs.datadoghq.com/articles/mcp-vulnerability-case-study-SQL-injection-in-the-postgresql-mcp-server/)).
- **`XiYanSQL` MCP (Text2SQL)** — a local-deployable alternative, kept as an
  option if natural-language→SQL is wanted later.

## Decision

Use **`postgres-mcp@0.3.0` in Restricted Mode**, exposing only the read-only
retrieval/introspection tools (`list_schemas`, `list_objects`,
`get_object_details`, `execute_sql`). The official reference server is rejected on
the SQL-injection finding.

## Consequences

- Read-only is enforced by a parser-backed guard, not trust.
- The MCP server runs under `uvx --python 3.13` because its `pglast==7.2`
  dependency has no Python 3.14 wheel; the server is an isolated subprocess, so
  this does not constrain the interpreter running Ariadne itself.
- DBA/perf tools are intentionally out of scope (least privilege).
