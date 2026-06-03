# Ariadne — Implementation scratchpad

The active TODO list for what's in flight **right now**. Queued specs and
phase ordering live in [ROADMAP.md](./ROADMAP.md); git history is the archive.
If this file grows past ~50 lines, extract the referential bits back to ROADMAP.

## Done — Phase 1 shipped

Read-only Neo4j MCP connector, `entity-workup` skill, `PostToolUse` provenance
hook + citation-coverage validator, and `ariadne workup <entity>` CLI are all
committed and gated. Full record in
[docs/superpowers/plans/2026-06-01-phase-1-vertical-slice.md](./docs/superpowers/plans/2026-06-01-phase-1-vertical-slice.md).
Re-verified end-to-end 2026-06-02 (lint + 35 unit + seeded-Neo4j + live agent e2e).

## Shipped since Phase 1

- **Citation gate v2 — Stage 1 (coverage / recall).** `find_uncited_claims` +
  `CitationReport.uncited`; a note now fails validation if any asserted claim is
  uncited — closes the hole where a zero-citation note passed and makes the
  `SKILL.md` promise real. Hermetic, section-aware (Gaps/Provenance exempt),
  segment-granular (trailing citation covers its bullet).
- **Citation gate v2 — Stage 2 (entailment / precision).** `EntailmentVerifier`
  protocol + `find_unsupported_claims` + `CitationReport.unsupported`, injected
  into `validate_citations(note, ledger, verifier=...)` (optional → default path
  stays hermetic). Real `HHEMVerifier` (Vectara HHEM-2.1-Open) behind the
  optional `eval` extra with lazy import; gated integration test. Unit-tested via
  a fake verifier (DI). Grounded in ALCE citation precision — see
  [docs/research/analytic-rigor-eval.md](./docs/research/analytic-rigor-eval.md).

- **Tradecraft lint (ICD-203).** `provenance/tradecraft.py`
  `lint_estimative_language` — flags non-standard estimative hedges, maps WEP
  terms to their probability band, detects the analytic-confidence axis. Advisory
  `tradecraft.json` artifact + CLI warning. Grounded in ICD-203 + WEP-calibration
  research.
- **Phase 4 eval harness.** `evaluation/needle.py` `score_workup` +
  `HALBERD_FIXTURE` + `ariadne eval <dir>` — scores recall / trajectory /
  `grounded` (surfaced AND traversed, not guessed) / pivot-burden against the
  planted Compound-Alpha needle. Real Halberd workup scores `grounded=True`.
- **Eval harness — cross-store needle + per-edge F1.** Statement extraction is
  now connector-agnostic (scans all string-valued tool args, so the Postgres
  `sql` arg counts toward trajectory, not just Cypher `query`). New
  `WREN_TIE_FIXTURE` scores the cross-modality Halberd↔Wren shared-`cover_employer`
  tie — `grounded` requires the relational store was actually queried
  (`personnel` in a statement), so asserting the tie from graph-only evidence is
  caught as a guess. Added per-edge **supporting-fact F1** (HotpotQA/MuSiQue-style:
  precision = grounded/surfaced edges, recall = grounded/gold edges) on both
  fixtures. `ariadne eval --fixture {halberd,wren-tie}` selects the needle and
  prints `sf_f1`. The headline heterogeneous-retrieval capability is now
  measurable end-to-end.
- **Phase 2 SQL connector.** `relational/postgres_server.py`
  `postgres_stdio_config` + `RELATIONAL_TOOLS` — `postgres-mcp@0.3.0` via uvx in
  `--access-mode=restricted` (read-only, pglast-guarded), read-only retrieval
  tools only. `infra/postgres/` compose + seed (synthetic `personnel`, keyed by
  `alias` to the graph's `Person.alias`) with a planted **cross-modality** link
  (Halberd & Wren share a cover employer — invisible in the graph). Seeded-
  Postgres integration test green. (Pinned to `uvx --python 3.13` — postgres-mcp's
  `pglast==7.2` has no py3.14 wheel.)
- **Phase 2 heterogeneous retrieval — WIRED & demonstrated.** Provenance hook
  records both `mcp__neo4j__` and `mcp__postgres__` under one source-agnostic
  `gN` space; `ariadne workup <e> --sql` adds the relational store (opt-in);
  `entity-workup` skill routes by question (graph=relationships, SQL=attributes),
  resolves the same entity by shared key, and reconciles (corroborate / flag
  conflicts). **Live two-store run:** the agent queried both stores and produced a
  cited note surfacing the Halberd↔Wren cross-modality tie (shared employer +
  co-location), flagging a graph/relational conflict on Talon's site, and
  attributing facts by source. Scores `grounded=True` on the eval harness.

- **Phase A — Dataset abstraction shipped (2026-06-03).** Canonical schema
  (`Entity` / `Relationship` / `Document` / `Attribute`) + `DatasetAdapter`
  protocol + `DATASETS` registry + dataset-agnostic indexer + synthetic adapter
  (wraps the existing seed graph, proves the seam) + `--dataset` flag wired into
  the CLI. Full plan:
  [docs/superpowers/plans/2026-06-03-phase-a-dataset-abstraction.md](./docs/superpowers/plans/2026-06-03-phase-a-dataset-abstraction.md).
  Decision: [ADR-0006](./docs/architecture/decisions/0006-dataset-agnostic-pipeline.md).

- **Phase B1 — Live indexing + Postgres full-text retrieval shipped (2026-06-03).**
  `src/ariadne/unstructured/document_store.py` — `tsvector` generated column +
  GIN index, `websearch_to_tsquery`-based search. `src/ariadne/datasets/load.py`
  — `load_graph` idempotent via per-label id-uniqueness constraints; `load_documents`
  bulk-inserts `Document` records. `ariadne index --dataset <name>` CLI wires the
  full pipeline. Decision: [ADR-0007](./docs/architecture/decisions/0007-hybrid-retrieval-fulltext-first.md).
  Full plan:
  [docs/superpowers/plans/2026-06-03-phase-b1-live-indexing-fulltext.md](./docs/superpowers/plans/2026-06-03-phase-b1-live-indexing-fulltext.md).

- **Phase B3.1 — Semantic retrieval leg shipped (2026-06-03).** Injectable
  `Embedder` protocol — `FakeEmbedder` (hermetic) + `SentenceTransformerEmbedder`
  default `bge-small-en-v1.5` (384-dim, Apache-2.0, ungated), behind the optional
  `embed` extra (lazy `importlib`). `documents` gains a nullable
  `embedding vector(N)` column + HNSW cosine index; `hybrid_search` RRF-fuses
  the full-text and vector legs (`1/(k+rank)`, k=60). Data layer only — wiring
  into the live agent loop is B3.2. Full plan:
  [docs/superpowers/plans/2026-06-03-phase-b3-1-semantic-leg.md](./docs/superpowers/plans/2026-06-03-phase-b3-1-semantic-leg.md).

- **Phase B2 — Enron adapter shipped (2026-06-03).** `EnronAdapter` streams
  `corbt/enron-emails` bounded to Vince Kaminski's `kaminski-v` mailbox (HF
  `datasets` behind the optional `data` extra; lazy + streaming); maps headers
  deterministically to graph (`Entity` / `Relationship`) and body to `Document`
  — no LLM in the path. Registered so `ariadne index --dataset enron` /
  `ariadne workup … --dataset enron` resolve it. Eval needle:
  `kaminski-aol` scores the non-obvious cross-account tie
  (Kaminski → personal `vkaminski@aol.com`). Proves the canonical seam
  generalizes to a second, real corpus. Full plan:
  [docs/superpowers/plans/2026-06-03-phase-b2-enron-adapter.md](./docs/superpowers/plans/2026-06-03-phase-b2-enron-adapter.md).

## In flight — rigor (Phase 4) + Phase 2 retrieval

Rigor next (grounded; see the research doc):
- ~~Stage 2 follow-through: validate HHEM on a hedged/estimative-claim set.~~
  **Done — resolved by design, not by tuning the model.** Estimative claims
  (ICD-203 hedges / WEP terms / confidence statements, detected by
  `tradecraft.is_estimative`) are now **routed out of the entailment gate**:
  `find_unsupported_claims` skips them, because an NLI model would reject a
  calibrated *inference* the evidence does not literally state. They stay subject
  to the recall (must-cite) gate and the tradecraft calibration lint — clean
  separation of *factual* precision (HHEM) from *analytic* calibration (ICD-203).
- Optionally wire an `--entail` flag into the CLI (still open).
- Prompt the `entity-workup` skill to use WEP terms + state analytic confidence
  (the real note currently uses neither — the lint surfaces this).
- Eval harness: more needle fixtures (per-edge F1 + cross-store needle now done).

Phase 2 retrieval (graph + SQL wired; remaining):
- Vector/unstructured connector — still needs a clean research pass (the
  deep-research run only confirmed SQL).
- **Subagent fan-out — deferred pending its own design pass, not blocked on
  research.** The headline orchestrator–worker finding conflicts with two things
  the current slice depends on: (1) cross-store **reconciliation** (corroborate /
  flag-conflicts) is a *shared-context* task, and the research doc flags multi-agent
  fan-out as explicitly **not** generalising to shared-context work; (2) the
  provenance backbone is a parent-side `PostToolUse` `gN` hook, but subagents run
  in isolated contexts and only return a *summary* — their raw tool calls never
  reach the parent hook, so citations would attach to a worker's prose, not `gN`
  evidence. A correct design (workers retrieve in parallel → return structured,
  pre-cited evidence → lead reconciles) is a real redesign of the provenance layer.
  YAGNI for a 2-store slice that already demonstrates `grounded=True`; revisit when
  store count or context pressure justifies the ~15× token cost.

## Still open (not blocking)

- Entity resolution / record linkage across stores (lead: blocking + LLM matcher).
- Concrete air-gapped substitutions per component.
