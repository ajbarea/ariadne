# Ariadne — Implementation scratchpad

What's being worked on **right now** — nothing else. Long-term plans and the
one-line ledger of completed work live in [ROADMAP.md](./ROADMAP.md); the full
record of *how* each thing shipped is in `docs/superpowers/plans/`, the ADRs
(`docs/architecture/decisions/`), and git history. Keep this file short: when a
task ships, move its one-liner to ROADMAP and clear it from here.

## In flight

**Adaptive Ariadne — A3: the dynamic MCP surface.** A1 (introspect → propose
[deterministic *and* LLM] → validate → freeze → apply) and **A2 (the declarative user
ontology)** are both complete — see *Recently shipped*. A3 is the next thread:
per-source tool families register at runtime as datasets connect
(`notifications/tools/list_changed`). `# research(2026-06): dynamic-fastmcp / Spring AI
/ Docker Dynamic MCP — web-search current practice before building.`

A2 follow-ons, deferred (smaller, ride the same seams): formalize
`validate_against_ontology` as a SHACL transpile (entity types → `sh:NodeShape`,
relationship types → `sh:PropertyShape` with `sh:class` domain/range); an
`ARIADNE_ONTOLOGIES` registry so an ontology self-discovers like profiles/mappings;
multi-`domain`/`range` edges (`sh:or`). Then B2 (learned skills), B3 (reflexion over
the eval harness).

(Bring the stores up with the `infra/*/docker-compose.yml` files; Neo4j needs the
manual `infra/neo4j/seed.cypher` on a fresh container.)

---

**Declarative user ontology — A2 first slice, shipped 2026-06-07** ([ADR-0027](./docs/architecture/decisions/0027-declarative-user-ontology.md)).
The mapper now maps into a user's *own* closed vocabulary, not just the open-string
canonical types. A lightweight `ontology.toml` declares `[[entity_types]]` +
`[[relationship_types]]` (`domain → range`); `mapping/ontology.py` loads it and
`validate_against_ontology` enforces it — every entity a declared type, every edge a
declared type routed between the declared endpoints (the relational half of OntoKG's
intrinsic-vs-relational routing, made checkable; composes with the structural
validator, doesn't duplicate it). The LLM mapper is *guided*: `build_map_tool(ontology)`
injects the vocabulary as JSON-Schema `enum`s on the forced-tool `type` fields, the
prompt describes the legal edges, and `propose_with_repair` re-prompts on conformance
errors as well as structural ones (the same gate-terminates-the-loop spine as ADR-0026).
`ariadne map --ontology PATH`: LLM-guided with `--llm`, validation-only for the baseline
(which can't invent a user's vocabulary from table names — the honest capability line).
Chose lightweight TOML over LinkML (kept the all-TOML idiom + zero new deps; LinkML's
codegen / prompt-gen value is redundant with the existing loop or deferred to the SHACL
transpile). TDD; 384 unit green. `# research(2026-06): OntoKG routing (arXiv 2604.02618);
Anchor SHACL-enforced typing + prompt-inclusion-for-small-ontologies (arXiv 2606.01208);
LinkML the heavier alternative (arXiv 2511.16935).`

**Agentic LLM schema mapper — A1 complete, shipped 2026-06-07** ([ADR-0026](./docs/architecture/decisions/0026-llm-schema-mapper.md)).
The agentic half of A1: `ariadne map --llm` proposes the `mapping.toml` with a real
Claude model (`mapping/llm_mapper.ClaudeSchemaMapper`) instead of the deterministic
`BaselineMapper`. Structured output via **forced tool-use** (`propose_mapping`, mirrors
`judge.py`) inside a **bounded validator-terminated retry loop** (`propose_with_repair`,
mirrors `repair.py` — re-prompts with `validate_mapping`'s complaints; the gate, not the
model, stops it). Injected `call_llm` seam → hermetic loop tests; real `anthropic` behind
the new `adaptive` extra; key-guarded CLI; live test gated like the rubric judge. Live
drive on the `intel` DB beat the baseline: dropped the `entity_attributes` key-value
side-table, dropped `content_tsv`/`embedding` junk columns, picked `text` over `id` for
the document name, typed `personnel`→`person`. Full AutoLink schema-*exploration*
deferred (large schemas only). TDD; 364 unit + 1 live green. `# research(2026-06):
structured output = schema + validator + repair loop; AutoLink arXiv:2511.17190 deferred.`

**Apply a ratified mapping — first adaptive Postgres slice closed, shipped 2026-06-07** ([ADR-0025](./docs/architecture/decisions/0025-applying-a-ratified-mapping.md)).
ADR-0020's "apply" step was the gap: the adapter existed but nothing wired a frozen
`mapping.toml` so the *existing* pipeline used it. Now a ratified mapping under
`ARIADNE_MAPPINGS` self-registers as a dataset (mirroring `ARIADNE_PROFILES`), so
`--dataset <name>` resolves for `index`/`workup`/`eval` with zero changes to them;
the source DSN is read **lazily from env** (off argv, per June-2026 secrets practice)
so only `index` opens the source DB. `ariadne map` now stamps the `[dataset]` header
and reads the DSN from env (one shared resolver; de-anti-patterns its old `--dsn`).
Deterministic proof: a testcontainers test runs source PG → mapping → the real
indexer → a traversable `(:Staff)-[:WORKS_IN]->(:Dept)` Neo4j edge; live-smoked the
`map` + discovery CLI against the running `intel` DB (read-only, no LLM). TDD; 353
unit + 3 integration green. `# research(2026-06): secrets off argv (ps/proc visible);
sources behind a declarative layer queried via tools, not federated live.`

**Trajectory eval grades observations, not just actions — shipped 2026-06-07** ([ADR-0024](./docs/architecture/decisions/0024-trajectory-grades-observations.md)).
Found verifying ADR-0023: the planted-needle `trajectory` + supporting-fact scorer
scanned only the query text, so an agent that walked the bridge via untyped
`MATCH (n)-[r]- RETURN type(r)` Cypher scored `trajectory=0`/`grounded=False` (rel
types land in the *response*). `evaluation/_text.traversal_text` now grades the
(action + data-retrieval observation) pair, excluding schema-introspection
observations (`CALL db.relationshipTypes`, postgres catalog tools) so enumeration
can't false-positive a guess. The live Halberd run that surfaced it re-scores
`trajectory 0→1`, `grounded False→True`, `sf_f1 0→1.0`. TDD; 343 tests green.
`# research(2026-06): agentic-RAG trajectory eval grades observations (AgenticRAGTracer
arXiv:2602.19127; SoK Agentic RAG arXiv:2603.07379).`

**Citation-coverage measurement — shipped 2026-06-07** ([ADR-0023](./docs/architecture/decisions/0023-measuring-citation-coverage-gain.md)).
The P-Cite repair loop's gain is now a *measured number*, not an exit code:
`citation_coverage` scores structural coverage (cited / total citable claims,
sharing one claim classifier with the recall gate, so coverage is `1.0` iff the
gate passes); `repair_citations_loop` returns raw-vs-repaired coverage; the Δ
(after − before) persists to `citations.json`, prints to stdout, and surfaces in
`ariadne eval` + the report (dashboard card + eval panel). Live Halberd:
**87% → 100% (+13 pts) in one repair pass**, 31/31 claims grounded; the report
card was headless-confirmed (and a defined-but-unwired card bug it surfaced is now
guarded by a wiring test). TDD; 334 tests green.
`# research(2026-06): Coverage axis + Δcoverage = P-Cite − G-Cite (arXiv:2509.21557);
Δ vs unrepaired baseline (Doctor-RAG arXiv:2604.00865); claim-level ALiiCE deferred.`

Recently shipped: the **interactive workup report**
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

Open candidates after this (the Adaptive Postgres slice is promoted to *In flight*
above as the next thread):

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
