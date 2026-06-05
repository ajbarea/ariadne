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
trajectory. Verified headlessly (incl. a live seeded-Neo4j subgraph).

**Entity-network node-click drawer — shipped 2026-06-05.** Clicking a network
node now opens a detail drawer mirroring the evidence drawer: the entity's **type
badge** (colored by label), its **attributes** (the node's domain properties), and
its **relationships** (typed, directional, click-to-pivot to the neighbour). The
subgraph seam carries node `props` end to end — `fetch_subgraph` maps each Neo4j
node's properties (minus `name`, already the title), `build_subgraph` passes them
through, and the report renders them client-side from the data island. Esc/scrim
close; the two drawers never stack. Verified headlessly (Playwright: open,
attrs+rels render, pivot, Esc-close, zero JS errors).

**Analytic-evaluation panel — shipped 2026-06-05.** The fixture-scored eval
metrics no longer live only on stdout: `ariadne eval` persists `eval.json` and
`ariadne rubric` persists `rubric.json`, and the report renders an **Analytic
evaluation** panel (present only when scored) — the planted-needle scores
(grounded / recall / trajectory / supporting-fact F1 / context-utilization /
queries / pivot-burden / reconciliation) as a stat grid, and the ICD-203 rubric
as scored dimensions with bars + the judge's rationales. Degrades cleanly on a
live workup with no fixture/judge run. TDD; headless-verified.
`# research(2026-06): Shneiderman details-on-demand + PatternFly primary-detail
drawer convention — mirror the existing evidence drawer for interaction consistency.`

**Multimodal connector slate — shipped 2026-06-05** ([ADR-0018](./docs/architecture/decisions/0018-multimodal-connector-slate.md)):
`enron` (text) · `worldspeech` (audio) · `lahman` (relational), all on the
canonical seam. **Video deferred**, criteria-gated (entity-rich + HF-loadable +
ships text + acceptable license) — HF video download charts are robotics/training
dominated; per ADR-0008 WorldSpeech already proves the sensory→text thesis.
HF caching: defaults are best-practice; `HF_HOME`/`HF_TOKEN` optional in `.env`.

**Context-utilization eval stat — shipped 2026-06-05**
([ADR-0019](./docs/architecture/decisions/0019-retrieval-side-evaluation-for-sensemaking.md)):
a deterministic, descriptive retrieval-side signal — `|distinct cited gN| /
|distinct retrieved gN|` (`evaluation/utilization.py`, pure over note × ledger) —
surfaced in `ariadne eval` (`utilization=…`) and as a report dashboard card,
**never gated** (a dangling cite is excluded as a citation error; exploratory /
negative-confirmation retrieval legitimately lowers it). TDD; verified headlessly
(card renders 67% on a 2/3 fixture; `grounded` unaffected). The June-2026 research
pass reframed this for the agentic domain: precision@k doesn't apply, retrieval-
recall is already covered by needle `recall` + supporting-fact F1.

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
