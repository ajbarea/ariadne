# Ariadne — Implementation scratchpad

What's being worked on **right now** — nothing else. Long-term plans and the
one-line ledger of completed work live in [ROADMAP.md](./ROADMAP.md); the full
record of *how* each thing shipped is in `docs/superpowers/plans/`, the ADRs
(`docs/architecture/decisions/`), and git history. Keep this file short: when a
task ships, move its one-liner to ROADMAP and clear it from here.

## In flight

_Nothing in flight._ Pick the next item from
[ROADMAP](./ROADMAP.md) — open candidates worth grabbing first:

- **Entity resolution across stores** — the foundation research pass left this
  open; reconciliation is scored but cross-store record-linkage strategy is
  unspecified. Likely the next meaty research/design item.
- **Subagent fan-out implementation** — design now specified
  ([ADR-0015](./docs/architecture/decisions/0015-subagent-fan-out-design.md));
  gated on store count ≥4 or a measured latency bottleneck, so not yet. When it
  fires, owe a smoke test that a worker `mcp__*` call lands in the shared ledger
  with `agent_id` set.

Recently settled: vector-store engine → [ADR-0014](./docs/architecture/decisions/0014-pgvector-for-the-semantic-leg.md)
(pgvector ratified); subagent fan-out design → [ADR-0015](./docs/architecture/decisions/0015-subagent-fan-out-design.md)
(provenance blocker dissolved by the SDK; implementation gated on a trigger).

- **Vector/unstructured connector re-research** — the deep-research run only
  adversarially confirmed the SQL choice; pgvector vs Redis-8 vs a dedicated
  store still needs its own clean pass before hardening.
- **Subagent fan-out design pass** — deferred (ADR-0005), not blocked on
  research; needs the provenance-redesign sketch before any code.

Blocked on AJ: Phase C / Avocado (licensed data), PyPI publish (token + name).
