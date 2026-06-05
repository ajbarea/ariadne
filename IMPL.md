# Ariadne — Implementation scratchpad

What's being worked on **right now** — nothing else. Long-term plans and the
one-line ledger of completed work live in [ROADMAP.md](./ROADMAP.md); the full
record of *how* each thing shipped is in `docs/superpowers/plans/`, the ADRs
(`docs/architecture/decisions/`), and git history. Keep this file short: when a
task ships, move its one-liner to ROADMAP and clear it from here.

## In flight

_Nothing in flight._ Pick the next item from
[ROADMAP](./ROADMAP.md) — open candidates worth grabbing first:

- **Subagent fan-out design pass** — deferred (ADR-0005), not blocked on
  research; needs the provenance-redesign sketch before any code (workers return
  *pre-cited* evidence so the parent `gN` provenance hook stays whole).
- **Entity resolution across stores** — the foundation research pass left this
  open; reconciliation is scored but cross-store record-linkage strategy is
  unspecified.

Recently settled: vector-store engine → [ADR-0014](./docs/architecture/decisions/0014-pgvector-for-the-semantic-leg.md)
(pgvector ratified vs Qdrant / Redis 8.4 / embedded; in-engine upgrade path
pgvectorscale·VectorChord).

- **Vector/unstructured connector re-research** — the deep-research run only
  adversarially confirmed the SQL choice; pgvector vs Redis-8 vs a dedicated
  store still needs its own clean pass before hardening.
- **Subagent fan-out design pass** — deferred (ADR-0005), not blocked on
  research; needs the provenance-redesign sketch before any code.

Blocked on AJ: Phase C / Avocado (licensed data), PyPI publish (token + name).
