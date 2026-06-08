# Ariadne — Implementation scratchpad

What's being worked on **right now** — nothing else. Long-term plans and the
one-line ledger of completed work live in [ROADMAP.md](./ROADMAP.md); the full
record of *how* each thing shipped is in `docs/superpowers/plans/`, the ADRs
(`docs/architecture/decisions/`), and git history. Keep this file short: when a
task ships, move its one-liner to ROADMAP and clear it from here.

## In flight

**Adaptive Ariadne — Axis A + Axis B first slices complete end to end.** Axis A — A1
(introspect → propose [deterministic *and* LLM] → validate → freeze → apply), **A2** (the
declarative user ontology), **A3** (the dynamic MCP surface). Axis B (self-improvement) —
**B1** seed (learned mappings), **B2** (learned analytic skills: `ariadne distil`), **B3**
(reflexion over the eval harness: `ariadne reflect`) — all complete; see *Recently shipped*.
The propose → ratify → freeze epic of [ADR-0020](./docs/architecture/decisions/0020-adaptive-self-improving-ariadne.md)
is realized in first-slice form: the harness adapts to a user's store *and* learns from
experience (success → a distilled skill; failure → a grounded reflection), with every change
human-ratified and the eval gate it can never edit as the external verifiable reward.

The **net-effect ratification comparator** (`ariadne compare`, [ADR-0031](./docs/architecture/decisions/0031-net-effect-ratification-comparator.md))
gives that ratify step a *measured* verdict — see *Recently shipped*.

Skills also **deepen from experience** now — `distil --into <skill>` (ADR-0032) revises an
existing skill from a new certified run, ratified by `compare`; see *Recently shipped*.

**Next candidates (all YAGNI until a consumer needs them):** the live wrapper that *produces*
the paired runs for `compare` (orchestrate a workup with vs without the artifact) + an auto-ratify
gate on its verdict; B2's multi-trajectory hierarchical consolidation (Trace2Skill across many
runs), skill *composition* (`composes_with`); B1's agent-driven refinement of a persisted mapping
(now unblocked by B3); test-time skill synthesis (the SkillTTA ephemeral track); A3 richer
per-dataset tool families; A2's SHACL transpile of `validate_against_ontology`, an
`ARIADNE_ONTOLOGIES` registry, multi-`domain`/`range` edges. Re-survey ROADMAP and overrule if
something higher-value surfaces.

(Bring the stores up with the `infra/*/docker-compose.yml` files; Neo4j needs the
manual `infra/neo4j/seed.cypher` on a fresh container.)

---

**Unified governance/assurance verdict — Phase 4 fold, shipped 2026-06-08.** The four
governance signals — read-only audit (security), citation gate (sourcing), ICD-203 tradecraft
(calibration), egress posture (isolation) — folded into one analyst-facing `GovernanceVerdict`
(`provenance/assurance.py`). **Weakest-link, never averaged**: a hard-gate breach (read-only /
citations) is FAIL, an advisory finding (tradecraft) is ADVISORY, the egress posture is descriptive
and never moves the status — a single composite number would let a strong analytic-quality score
mask a safety-gate breach. Persisted into `governance.json` (a `verdict` block: status + ok + the
per-axis model-card sections); `ariadne governance` now prints the unified multi-axis label and gates
weakest-link (read-only breach exit 3 > citation fail exit 1 > advisory/clean 0), recomputing the
read-only axis fresh from the ledger (verify-don't-trust) while reading the run's own persisted
citation/tradecraft/egress results; the report renders one assurance banner above the dashboard
(model-card pattern — summary verdict + the existing four cards as the drill-down, color-coded
green/amber/red, headless-verified). TDD; 514 unit green. `# research(2026-06): composite
single-number assurance scores mislead; weakest-link gating over distinct safety-vs-quality
dimensions is the 2026 standard (Kili "AI Benchmarks 2026"; "Evaluating Frontier Safety Frameworks"
arXiv:2512.01166 — assurance is the weakest-treated dimension, so it must not be averaged away);
multi-axis model-card presentation over an average (AI model cards 2026).`

> Smoke finding (free, no API): the on-disk `workups/halberd` run scores **reconciliation 2/2 +
> grounded=true** and its note surfaces *both* planted needles (the Halberd↔Wren shared-cover tie
> and the Talon Compound-Beta conflict) as its lead finding — so the prior handoff's "cross-store
> miss" was **stochastic run-to-run variance, not a reproducible bug** (N=1 either way proves
> nothing; reliability characterization needs paired live workups + `compare` = real API spend,
> deferred). But that same run's **citation gate is FAIL**: the "Decisive finding:" summary line
> under *Alternatives considered* is uncited. The unified verdict makes that visible at a glance
> where the four scattered dashboard cards buried it — exactly the verification-ease win the fold
> was for.

---

**Deepen a skill from new experience — `distil --into`, shipped 2026-06-07** ([ADR-0032](./docs/architecture/decisions/0032-deepening-a-skill-from-new-experience.md)).
Skills now improve across uses, not just get created once: `ariadne distil <run> --into <skill-dir>`
does a **trace-conditioned, bounded, conflict-aware revision** of an existing skill from a new
certified run (Trace2Skill's deepen mode / SkillRevise), integrating the *generalizable* lesson
without hard-coding the run's specifics (the documented overfitting failure mode). **LLM-only** (a
deterministic deepen could only append-and-bloat — the honest line); requires `--llm` + the
certified-source gate (B2). Keeps the existing skill's identity; the revision is a *proposal* written
to `skills-proposed/` (never overwrites the original) — **ratify by measuring it: `ariadne compare`
the revised skill vs the original and adopt only on a net gain** (ADR-0031's held-out edit gate, the
SkillOpt loop, human-in-loop). Live-smoked: deepened the real `entity-workup` from the `halberd` run
— structure + 4-phase loop + citation discipline preserved, **0 hard-coded entity leaks**, 693→978
words (integrated, not rewritten/bloated). Refactored shared `_trajectory_moves` + the
incomplete-proposal guard out of create-mode (DRY). TDD; 462 unit green. `# research(2026-06):
Trace2Skill deepen + overfitting failure mode (arXiv 2603.25158); SkillOpt bounded edits + held-out
gate (arXiv 2605.23904); SkillRevise trace-conditioned revision (arXiv 2606.01139).`

**Net-effect ratification comparator — shipped 2026-06-07** ([ADR-0031](./docs/architecture/decisions/0031-net-effect-ratification-comparator.md)).
`ariadne compare --baseline RUN… --candidate RUN…` gives the ratify step a *measured* verdict:
you cannot tell a good skill from its prose (negative transfer hits ~25% of skills), so it nets a
candidate's **repairs** against its **regressions** vs a baseline — not a single delta (an artifact
can fix more *and* break more). **Same-instance gate** (all runs share the eval fixture — paired
comparison is what makes the delta a signal, not instance noise; mixed fixtures raise
`IncomparableRuns`); a hard-gated regression (`grounded` / `citation_coverage`) forces *reject*
regardless of the net; caveats for a differing harness (model/profile/params — disclosure) and
small N (`<3`/side — agentic eval is stochastic). It only *reads* `eval.json` — never recomputes a
score (the eval stays the single scorer, ADR-0020). Exit code carries the verdict (ratify/neutral 0,
reject 1, incomparable 2). Hermetic core (no API, no live stores); the live wrapper that produces the
paired runs is deferred. Smoked on the real `halberd` run vs a degraded copy — REJECT (4 regressions,
net -4) and, reversed, RATIFY (4 repairs, +4). TDD; 453 unit green. `# research(2026-06): SkillGen
net-gain gate arXiv 2605.10999; "can't tell a good skill by reading it" / negative-transfer-25%
SkillLens-SkillOpt arXiv 2605.23904; net-effect = repairs−regressions arXiv 2511.11012; paired
same-instance variance reduction arXiv 2512.06710; disclose the harness arXiv 2605.23950.`

**Reflexion over the eval harness — B3 first slice, shipped 2026-06-07** ([ADR-0030](./docs/architecture/decisions/0030-reflexion-over-the-eval-harness.md)).
`ariadne reflect <run>` reflects on an under-performing workup and **proposes refinements for a
human to ratify** — the failure-side counterpart to B2's success-side distillation. Eval-triggered
(no eval ⇒ refuse) and **gold-free by construction**: it reads the run's own scores + artifacts and
never the held-out gold (`reflect.py` does not import the fixture gold — a structural test enforces
it). Findings: *own-evidence* (citation_coverage / grounded cite the agent's own uncited/dangling
claims) · *score-triggered* (recall / trajectory / sf-f1 below ideal, grounded in the trajectory
*shape*, never the missed gold) · *behavioral* (exact-duplicate queries). Descriptive dims
(pivot_burden, context_utilization) are reported as context, not defects (no arbitrary thresholds).
The two reward-hacking vectors are structurally closed — **no evaluator tampering** (proposes only
ratified artifacts, never the scorer) and **no train/test leakage** (never the gold); **propose-only**
breaks the in-context self-refine loop. Deterministic diagnosis + `--llm` reflexion (`propose_reflection`
forced tool-use, `adaptive` extra, key-guarded), writing `reflection.{md,json}` beside the run.
Live-smoked: the clean `halberd` run → *no findings* (restraint); a degraded copy → 3 findings, and
the `--llm` reflexion caught that an uncited claim was *contradicted by the run's own traversal*
(co-location ≠ command) and proposed a closing-citation-audit skill + an enumeration query strategy +
a supporting-fact mapping — all gold-free. Also refactored the shared run model + structural
extraction into `learning/runs.py` (DRY, B2+B3). TDD; 437 unit green. `# research(2026-06): Reflexion
arXiv 2303.11366; reward-hacking vectors = evaluator-tampering + train/test-leakage arXiv 2603.11337;
in-context reward hacking arXiv 2407.04549 / 2402.06627 → propose-only.`

**Distil analytic skills from eval-certified trajectories — B2 first slice, shipped 2026-06-07** ([ADR-0029](./docs/architecture/decisions/0029-distilling-analytic-skills-from-trajectories.md)).
`ariadne distil <run>` distils a high-scoring workup into a named, structured, declarative
skill (`SKILL.md` + a `skill-card.toml` sidecar) — the skill analog of A1's `map`, on the same
propose → ratify → freeze spine. **Keystone gate:** distil **only** from a run the eval harness
certified `grounded` (the external verifiable reward; no eval ⇒ no distillation — the honest
capability line). The deterministic distiller *records* the trajectory into a phase-grouped
skeleton (graph-schema / relational-schema / traversal / relational-query / free-text); `--llm`
runs the Trace2Skill move, generalizing the trajectory + note into transferable procedural prose
via forced tool-use (`propose_skill`, behind the `adaptive` extra, key-guarded). The draft lands
in `skills-proposed/` for a human to ratify into `.claude/skills/`. Live-smoked both paths against
the `halberd` run — the `--llm` smoke caught a `max_tokens` truncation (the forced tool-call
dropped the required `body`), now fixed (8192 + a clear incomplete-proposal error). TDD; 419 unit
green. `# research(2026-06): Trace2Skill arXiv 2603.25158; SkillGen verifier-gate arXiv 2605.10999;
SoK Agentic Skills arXiv 2602.20867; SkillTTA arXiv 2605.16986 (the rejected ephemeral alternative).`

**MCP `connect_dataset` — A3 runtime activation, shipped 2026-06-07** ([ADR-0028](./docs/architecture/decisions/0028-runtime-dataset-activation-over-mcp.md)).
A host agent can onboard a ratified user store **mid-session**: `connect_dataset(name)`
resolves a mapping.toml ratified under `$ARIADNE_MAPPINGS`, registers its adapter, exposes
an intent-named `workup_<name>` tool via `add_tool`, and fires `send_tool_list_changed` so
connected clients re-list — no server restart. Governance held: only an already-ratified
mapping can be activated, never a raw DSN (the ADR-0020 boundary). The research pass caught
that the **official MCP SDK's FastMCP does *not* auto-notify on `add_tool`** (that's the
separate `jlowin/fastmcp` v2) and only delivers from within a request context — so the
notification is sent by hand. Verified end to end over the real protocol via the SDK's
**in-memory client** (connect → `tools/list` shows `workup_<name>`). TDD; 390 unit green.

**MCP `list_datasets` — A3 enumeration seam, shipped 2026-06-07.** The MCP server
exposed `list_profiles` but no way to discover which *datasets* a host agent could
`workup` — built-ins *or* user stores ratified under `$ARIADNE_MAPPINGS`. `list_datasets`
(testable core `list_datasets_info(env)`) imports the built-in adapters for their
registration side-effect, runs `discover_and_register`, and returns
`{name: {entity_type, access}}`. Closes the discovery gap and is the enumeration
foundation A3's dynamic per-dataset tool families build on. Live-smoked: the built-in
slate + the ratified `intel` user mapping all enumerate over the seam. TDD; 387 unit green.

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

Blocked on AJ: Phase C / Avocado (licensed data). (PyPI publish shipped 2026-06-08 as
`ariadne-sensemaking`, via trusted publishing — see ROADMAP.)
