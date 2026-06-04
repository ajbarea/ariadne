# Reusable workflow patterns

> A brief deliverable for the SCADS program. Ariadne is one sensemaking
> prototype, but the workflow patterns it demonstrates generalize to other
> entity-centric analytic use cases. Each pattern below names the problem it
> solves, its shape, where Ariadne implements it, and how to reuse it. Every
> claim points at real code or a decision record, if one drifts from the
> implementation, fix the doc.

## 1. The sensemaking loop: gather → act → verify → synthesize

**Problem.** An analyst reasoning about one entity must pull scattered evidence,
check it, and write a defensible product, not free-associate over a search box.

**Shape.** A skill encodes a fixed loop: **gather** each store's shape and locate
the target; **act** by routing focused read-only queries to the right store;
**verify & reconcile** decisive links and hunt non-obvious cross-source ties;
**synthesize** a structured, cited note. The loop is the same regardless of
domain.

**In Ariadne.** `.claude/skills/entity-workup/SKILL.md` + `note-template.md`.

**Reuse.** Author one skill per analytic task; keep the four-step spine, swap the
routing rules and the note template for the domain.

## 2. Each store as a read-only MCP tool family, with a routing lead agent

**Problem.** Evidence lives in heterogeneous stores (graph, relational, text)
with different query languages; the analyst should not pivot between them by hand.

**Shape.** Expose every store as its own MCP tool family (`mcp__graph__*`,
`mcp__postgres__*`, `mcp__ariadne__*`), all **read-only**. A lead agent routes by
question type, graph for relationships/hierarchy/co-location, relational for
per-entity attributes, hybrid full-text+vector for free-text, and resolves the
*same* entity across stores by a shared key.

**In Ariadne.** `graph/neo4j_server.py`, `relational/postgres_server.py`,
`unstructured/search_tool.py`; routing in the skill. Decisions:
[ADR-0002](architecture/decisions/0002-official-mcp-connectors-over-hand-rolled.md),
[ADR-0003](architecture/decisions/0003-postgres-mcp-restricted-mode.md),
[ADR-0007](architecture/decisions/0007-hybrid-retrieval-fulltext-first.md).

**Reuse.** Add a store by wrapping it as a read-only MCP tool family and giving
the lead a routing rule; no change to the loop or the gates.

## 3. Provenance-by-hook + a citation gate

**Problem.** An analytic product is only trustworthy if every claim traces to
evidence the system actually retrieved, and the agent must not fabricate sources.

**Shape.** A `PostToolUse` hook stamps every evidence call with a provenance id
(`gN`) into a ledger; the synthesis must cite `[cite:gN]`; a gate validates
**recall** (no uncited claims) and **precision** (the cited evidence entails the
claim), distinguishing facts from analytic judgments (ICD-206).

**In Ariadne.** `provenance/hook.py`, `provenance/ledger.py`,
`provenance/citations.py`; entailment via `provenance/entailment.py`
([ADR-0011](architecture/decisions/0011-llm-rubric-analytic-standards-eval.md)
covers the rigor stack).

**Reuse.** The hook + ledger + gate are domain-agnostic; reuse as-is for any
tool-using agent that must produce traceable output.

## 4. Cross-modal reconciliation: corroborate agreements, flag conflicts

**Problem.** When two stores describe the same entity, agreement should
*strengthen* a finding and disagreement must be *surfaced*, never silently
resolved.

**Shape.** On a decisive cross-store fact, the note states whether the stores
corroborate (independent agreement → higher confidence) or conflict (flag it,
weigh the sources). A scorer grades whether the note actually did so, fact
surfaced **and** reconciliation language **and** both stores queried.

**In Ariadne.** Skill verify-step; scored by `evaluation/reconcile.py`
(`ariadne eval --reconcile`).

**Reuse.** Plant known agreements/conflicts in a fixture; score any multi-source
workflow's reconciliation behavior with the same scorer.

## 5. Tradecraft calibration (ICD-203 / ICD-206)

**Problem.** Analytic writing has standards, calibrated uncertainty, fact-vs-
judgment separation, analysis of alternatives, that generic generation ignores.

**Shape.** A lint maps estimative language to ICD-203 probability bands and
detects the confidence axis; the skill directs an **analysis of competing
hypotheses** on the decisive finding and proportionate, hedged judgments; the
citation gate enforces that judgments cite their basis (ICD-206).

**In Ariadne.** `provenance/tradecraft.py`; skill ACH guidance + the note
template's *Alternatives considered* section.

**Reuse.** The lint and the ACH/confidence prompt pattern transfer to any
analytic-writing task with a published standard.

## 6. "How do you know it works?": planted-needle + rubric evaluation

**Problem.** The brief's central challenge is **specification & validation**: an
analytic product has no single right answer, so quality must be measured another
way.

**Shape.** Two complementary evals. **Mechanical**: plant ground-truth needles
(a non-obvious multi-hop bridge, a cross-store tie) and score recall, trajectory
(traversed vs guessed), grounding, and supporting-fact F1. **Judgment**: an
LLM-rubric scores the ICD-203 standards a regex can't see (alternatives,
argumentation, relevance, accuracy), pointwise and criterion-separated.

**In Ariadne.** `evaluation/needle.py`, `evaluation/reconcile.py`,
`evaluation/rubric.py` (`ariadne eval`, `ariadne rubric`).
[ADR-0011](architecture/decisions/0011-llm-rubric-analytic-standards-eval.md) +
[analytic-rigor research](research/analytic-rigor-eval.md).

**Reuse.** Plant a needle per use case for mechanical scoring; reuse the rubric
engine (swap the dimensions) for the judgment axis.

## 7. Governance: verify the posture, don't trust the config

**Problem.** Governance must be uniform across quality, security, and data
integrity, and verified, not assumed.

**Shape.** Quality is the citation gate + tradecraft lint + rubric. **Security /
data integrity**: audit the actual tool trace for any mutating statement, so a
write the agent attempted, even one the read-only connector blocked, is caught.
Every governance signal is also emitted as telemetry.

**In Ariadne.** `provenance/governance.py` (`audit_read_only` → `governance.json`),
surfaced via OpenTelemetry
([ADR-0010](architecture/decisions/0010-observability-opentelemetry.md)).

**Reuse.** The ledger audit is store-agnostic; reuse it as a defense-in-depth
check for any read-only analytic loop.

## 8. Dataset-agnostic canonical seam

**Problem.** A new corpus should not mean rewriting the pipeline.

**Shape.** A canonical schema (Entity / Relationship / Document / Attribute) plus
a `DatasetAdapter` protocol; per-corpus adapters are the only thing a new dataset
needs. The same seam isolates ingestion for air-gap (a local-file adapter instead
of a streaming one).

**In Ariadne.** `datasets/canonical.py`, `datasets/base.py`, the synthetic +
Enron adapters.
[ADR-0006](architecture/decisions/0006-dataset-agnostic-pipeline.md).

**Reuse.** Onboard a corpus by writing one adapter to the canonical schema;
everything downstream is unchanged.

## 9. Injectable Protocols for optional heavy dependencies

**Problem.** Embedding models, entailment models, and LLM judges are heavy and
sometimes cloud-bound, but the core must stay hermetically testable and
air-gap-friendly.

**Shape.** Define a narrow `Protocol` (Embedder, EntailmentVerifier,
AnalyticJudge); ship a deterministic fake for tests and a real implementation
behind an optional extra, imported lazily so static analysis and the base install
stay clean.

**In Ariadne.** `unstructured/embed.py`, `provenance/entailment.py`,
`evaluation/judge.py`. This is also what makes the
[cloud/air-gap fork](architecture/decisions/0012-cloud-vs-air-gapped-deployment-fork.md)
a single seam.

**Reuse.** Wrap any optional model behind a Protocol + fake + extra; the analytic
logic never depends on whether the heavy dependency is installed.
