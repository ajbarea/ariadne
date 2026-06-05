# Ariadne — Implementation scratchpad

What's being worked on **right now** — nothing else. Long-term plans and the
one-line ledger of completed work live in [ROADMAP.md](./ROADMAP.md); the full
record of *how* each thing shipped is in `docs/superpowers/plans/`, the ADRs
(`docs/architecture/decisions/`), and git history. Keep this file short: when a
task ships, move its one-liner to ROADMAP and clear it from here.

## In flight

_Nothing in flight._ Recently shipped: the **interactive workup report**
([ADR-0017](./docs/architecture/decisions/0017-interactive-workup-report.md)) —
`ariadne report <dir>` + auto-render at end of `ariadne workup` → self-contained
`report.html`: light/dark toggle, **self-explaining dashboard** (click a stat for
a plain-language definition), clickable-provenance note + evidence drawer, an
**Entity-network view** (real traversed subgraph via deterministic
neighbourhood query → `subgraph.json`, force-directed, typed+labelled) toggling
with the Provenance flow, a **Reconciliation panel** (note sentences classified
corroboration vs conflict using the reconcile-eval cue vocabulary), and the
trajectory. Verified headlessly (incl. a live seeded-Neo4j subgraph). Follow-ons:
richer entity attrs in a node-click drawer for the network.

**Multimodal connector slate — shipped 2026-06-05** ([ADR-0018](./docs/architecture/decisions/0018-multimodal-connector-slate.md)):
`enron` (text) · `worldspeech` (audio) · `lahman` (relational), all on the
canonical seam. **Video deferred**, criteria-gated (entity-rich + HF-loadable +
ships text + acceptable license) — HF video download charts are robotics/training
dominated; per ADR-0008 WorldSpeech already proves the sensory→text thesis.
HF caching: defaults are best-practice; `HF_HOME`/`HF_TOKEN` optional in `.env`.

Open candidates after this:

- **Entity-resolution implementation** — strategy now specified
  ([ADR-0016](./docs/architecture/decisions/0016-entity-resolution-across-stores.md));
  Tier 1 (exact key) shipped, Tiers 2–3 (blocking+normalized, LLM-adjudicated)
  gated on real unstructured ingestion (Enron/Avocado). When it fires, owe an
  ER-accuracy eval fixture + a Tier-3-link-is-a-cited-`gN` smoke.
- **Subagent fan-out implementation** — design now specified
  ([ADR-0015](./docs/architecture/decisions/0015-subagent-fan-out-design.md));
  gated on store count ≥4 or a measured latency bottleneck, so not yet. When it
  fires, owe a smoke test that a worker `mcp__*` call lands in the shared ledger
  with `agent_id` set.

Recently settled (decided, implementation gated where noted):
[ADR-0014](./docs/architecture/decisions/0014-pgvector-for-the-semantic-leg.md)
vector-store engine (pgvector) ·
[ADR-0015](./docs/architecture/decisions/0015-subagent-fan-out-design.md)
subagent fan-out (provenance blocker dissolved by the SDK) ·
[ADR-0016](./docs/architecture/decisions/0016-entity-resolution-across-stores.md)
entity resolution (tiered, ingestion-first).

Blocked on AJ: Phase C / Avocado (licensed data), PyPI publish (token + name).
