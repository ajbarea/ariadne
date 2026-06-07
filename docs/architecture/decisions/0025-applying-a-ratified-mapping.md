# 0025, Applying a ratified mapping — env-discovered dataset, ingest-time, DSN from env

- **Status:** Accepted (2026-06-07)
- **Deciders:** Ariadne maintainers
- **Refines:** [ADR-0020](0020-adaptive-self-improving-ariadne.md) (the "Apply" step of the first Postgres slice)

## Context

[ADR-0020](0020-adaptive-self-improving-ariadne.md)'s first slice is a
propose → ratify → freeze → **apply** loop over a user's Postgres. Everything up to
*freeze* shipped: read-only `information_schema` introspection
(`introspect/postgres.py`), a `SchemaMapper` that proposes a draft
(`mapping/propose.py`), a deterministic structural validator + a `mapping.toml`
model (`mapping/schema.py`), a `MappingDrivenAdapter` that projects a user's rows
onto the canonical schema (`mapping/adapter.py`), a `postgres_row_reader`, an
`ariadne map` command that writes the draft, and a testcontainers test proving the
adapter loads canonical records off live Postgres.

The **apply** step was the gap: nothing wired a ratified `mapping.toml` so the
*existing* `ariadne index` loads it into the stores and `ariadne workup` / `eval`
resolve it. The `map` command literally ended with the dangling instruction "load
it with a `MappingDrivenAdapter`" — with no command that does so. This ADR records
how apply closes, since the wiring (where the DSN lives, how a dataset name resolves
across fresh processes) is a contestable design call, not a mechanical detail.

## Decision drivers

- **Run the existing pipeline unchanged.** ADR-0020's stated done-state is "the
  existing indexer + workup + eval run unchanged on the user's data." Apply must add
  a *source*, not a parallel pipeline.
- **Governance posture is preserved.** Workups query Ariadne's own stores through the
  read-only MCP surface; they must not open ad-hoc live connections to a user's
  database mid-workup.
- **Secrets stay off the command line.** A connection string carries a password;
  command-line arguments are world-readable via `ps` / `/proc`, so a `--dsn` flag is
  the wrong home for it (June-2026 secrets-handling practice).
- **Match the existing idiom.** Datasets self-register into `DATASETS` by import;
  `ARIADNE_PROFILES` already establishes "an env var points to ratified TOML." Apply
  should reuse these, not invent a new resolution path.

## Considered options

1. **Query-time federation** — workups query the user's Postgres live, per-question.
   *Rejected.* Unbounded (every store/dialect becomes a live tool surface), and it
   breaks the read-only-MCP-over-our-own-stores governance posture. The 2026 pattern
   keeps sources behind a declarative layer; ingest-then-query is the bounded form.
2. **A `--mapping` flag threaded through every command** (`index --mapping`,
   `workup --mapping`, `eval --mapping`) with argparse `choices` relaxed.
   *Rejected.* More code, and it diverges from the `DATASETS` registry idiom that
   keeps the agent/connectors/eval ignorant of *which* dataset is loaded. `workup`
   does not even need the mapping (it queries the already-indexed stores).
3. **Ingest-time apply via env-discovered registration.** *Chosen.* A ratified
   `mapping.toml` self-registers as a normal dataset; `index` loads it through the
   *existing* indexer; `workup` / `eval` resolve the name with zero changes.

## Decision

Adopt **option 3**.

- **Ingest-time, not query-time.** A ratified mapping is applied at `index`: the
  `MappingDrivenAdapter` projects the user's rows onto canonical records, and the
  *existing* `load_graph` / `load_documents` write them into Ariadne's own Neo4j +
  Postgres. `workup` / `eval` / `governance` then run unchanged against those stores.
- **Discovery-registration mirroring `ARIADNE_PROFILES`.** Ratified mappings live as
  `*.toml` under an **opt-in**, env-pointed directory `ARIADNE_MAPPINGS` (unset ⇒ no
  user datasets, zero import-time surprise). `discover_and_register` reads the dir and
  `register()`s one `MappingDrivenAdapter` per file, so `--dataset <name>` resolves
  identically for `index`, `workup`, and `eval` across fresh processes. The
  `mapping.toml` gains an optional `[dataset]` header (`name`, `dsn_env`, `schema`);
  the structural `[[entities]]` / `[[relationships]]` body is unchanged.
- **Source DSN from env, never argv.** The `[dataset]` header names the env var
  (`dsn_env`, default `ARIADNE_SOURCE_DSN`) holding the connection string. The row
  reader connects **lazily, inside `load()`**, opening a short-lived read-only
  connection per table — so only `index` ever touches the source database;
  `workup` / `eval` register the adapter but never open it. One `_source_dsn`
  resolver is shared with `ariadne map`, whose `--dsn` flag becomes an optional
  override of the same env var (DRY; the env path is documented as primary).

**Loop-closure done-state.** The permanent gate is a testcontainers integration
test: a frozen `mapping.toml` → adapter → the *real* indexer → records queryable in
Neo4j (the foreign key resolves to a `MATCH`-able typed edge). The end-to-end
*grounded note* (a live LLM workup) is the existing synthetic e2e once the user's
data is in the stores; it is driven and recorded rather than added as a
cost-incurring, variance-prone assertion, consistent with how live-judge tests are
gated.

## Consequences

- ADR-0020's first slice closes: a maintainer points Ariadne at a Postgres nobody
  hand-wrote an adapter for, ratifies a `mapping.toml`, and `index` / `workup` /
  `eval` run on it unchanged.
- No new query-time attack surface or live cross-store federation; the read-only
  governance spine is untouched. The source DB is read once, at ingest, over
  short-lived read-only connections, with the credential off the command line.
- A second store dialect (CSV, Neo4j-as-source, …) is a new reader + header, not a
  new resolution path — discovery, naming, and the indexer are dialect-agnostic.
- The `[dataset]` header is additive: a header-less `mapping.toml` still parses for
  the existing validator/adapter tests; only registration needs the header.

Sources: avoid secrets on the command line (argv visible in process listings) —
[smallstep, *How to Handle Secrets on the Command Line*](https://smallstep.com/blog/command-line-secrets/);
connection strings out of source/argv, env or a vault —
[*Securing Connection Strings*](https://dev.to/chami/securing-connection-strings-best-practices-for-development-and-production-3cj0);
psycopg / libpq environment-variable connection parameters
([PostgreSQL libpq env vars](https://www.postgresql.org/docs/current/libpq-envars.html));
sources behind a declarative layer queried via tools, not federated live
([Truto, *Mapping AI Agent Patterns to Integration Platforms 2026*](https://truto.one/blog/mapping-ai-agent-patterns-to-integration-platforms-2026-tutorial/)).
