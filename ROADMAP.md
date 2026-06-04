# Ariadne — Roadmap

A living plan for the sensemaking harness. Items are **planned** (full detail)
or **shipped** (one-liner with date). Whatever's *in flight right now* lives in
[IMPL.md](./IMPL.md).

Last reviewed: 2026-06-01 (Phase 1 vertical slice landed — Neo4j MCP connector,
entity-workup skill, provenance hook + citation validator, and `ariadne workup`
CLI; Phase 0 fully complete).

Stance: **ground every architectural choice in current best practice.**
Web-search the specific target's primary docs at the planning step; prefer an
architectural fix over an expedient patch. Each committed design decision in
this file should carry a `# research(YYYY-MM):` provenance note.

---

## Mission & charter

> Distilled from the SCADS onboarding brief and archived here 2026-06-01. The
> brief is not retained; this section is now its system of record.

**Problem.** Modern SIGINT-style collection produces intelligence about entities
embedded in large, complex *organizational hierarchies*, scattered across highly
heterogeneous systems — graph databases, relational stores, unstructured
repositories — with content spanning metadata, free text, imagery, and video. No
single interface spans that range, so analysts pivot manually between systems and
lose context and momentum at every transition. The hard part is not data
*access*; it is **coherent multi-hop reasoning across heterogeneous
representations**, where decisive evidence is often linked only through implicit
organizational relationships buried across modalities.

**Why now.** Today's analytic workflows are shaped by out-of-date technical and
organizational expectations. The bet: reimagine the workflow as a **conversation
between an analyst and an AI agent**, delivering **composable, shareable, and
manageable** agentic workflows.

**Approach.** Use an agentic coding harness as a unifying *orchestration layer*
over existing infrastructure rather than a replacement — it dispatches
specialized tools and skills to retrieve, interpret, and synthesize across graph,
structured, and unstructured sources. Analytic services and databases are exposed
via API; the agent builds visualizations and interactive interfaces on demand to
glue services together and present results to humans. (The brief names Claude
Code / Cowork or OpenClaw as example harnesses; Ariadne builds on the Claude
Agent SDK.)

**Central research question.** *Given such a harness and its UI, what specific
tools, skills, and hooks are necessary to support a rigorous end-to-end analytic
workflow targeting entities within an organizational hierarchy?* The work is to
identify and prototype the **minimum viable toolset** — database connectors,
modality-specific processors (image/video analyzers, NLP extractors), and
hierarchical reasoning hooks.

**Deliverables.**
- *Primary* — a working prototype demonstrating an end-to-end analytic workflow:
  input a target **entity or organizational node**; through a coordinated tool
  sequence, surface evidence across all data structures and modalities; synthesize
  it into a coherent, cited analytic product.
- *Secondary* — **documented, reusable workflow patterns** that transfer to future
  SCADS analytic use cases.

**Success criteria.** The harness's ability to (1) **traverse** organizational
relationships, (2) **reconcile** information across modalities, (3) **reduce the
analyst's manual pivot burden**, and (4) surface **non-obvious connections** that
are impractical to find with conventional tooling.

**Design constraints** (brief, "Workflow Implementation"). Core challenges are
**specification and validation** — *"how do you know what works?"* Composable
primitives are the SDK set: **models, agents, tools, skills, hooks**. Governance
must be uniform across **quality, security, and data integrity**.

**Stretch goals.** Multi-player shared sessions; raising analysts' domain
knowledge and analytic capacity through the tool.

**Program context.** SCADS (Government + Academia + Industry) spans five areas —
*AI Evaluation*, *AI Implementation*, *AI Agent Development*, *Sensemaking for
Large Entities*, and *Data Set Creation & Augmentation* — with Data Set Creation
as the shared foundation and AI Evaluation as the overarching validation
framework. Ariadne is the **Sensemaking** effort under **AI Agent Development**,
and an explicit **umbrella project**: it defines integration interfaces so sibling
contributions (graph-extraction pipelines, entity-resolution models, multimodal
indexing) surface as callable tools — both a standalone contribution and the
portfolio's unifying demonstration layer.

---

## Why this file exists

If you want to know what Ariadne is building next and why, this is the answer.
The roadmap is deliberately legible: the tools, skills, and hooks we add are
research questions made concrete, and each should trace back to a cited source.

---

## Open architecture questions

The June-2026 [best-practice research](./docs/research/best-practice-architecture.md)
settled several of these. Resolved **directions** carry a provenance note; still-open
items must not be hardened against one answer.

1. **MVP toolset boundary** — the smallest set of tools/skills/hooks that
   credibly demonstrates end-to-end value; build vs. expose a stub for a sibling
   SCADS project. *(Direction set — see Phase 1 / the MVP in the research report.)*
2. **Graph / multi-hop reasoning** — `# research(2026-06):` GraphRAG is the core
   multi-hop capability, but **hybrid graph+text + agentic correction**
   (HRAG/AGRAG) beats graph-only, and "graph-first" is justified *only* for
   multi-hop/relational queries (it loses on simple fact lookup). Entity
   resolution across stores remains **open**.
3. **Connector strategy** — `# research(2026-06):` expose each store as an **MCP
   tool family** (`mcp__graph__*`, `mcp__relational__*`, `mcp__vector__*`); a
   lead agent routes by source and reconciles. Default to **agentic search**, add
   semantic/vector retrieval when faster lookup is needed.
4. **Multimodal processing** — `# research(2026-06):` fuse **agentically** —
   convert imagery/video to **structured text** (VQA + summarization, à la
   DeepMEL) and reason over it, rather than a shared embedding space.
5. **Analytic rigor & eval** — provenance/citation tracking, grounding,
   confidence handling, success metrics, structured-analytic-technique framing.
   The brief frames this as the core challenge: **specification & validation**
   (*"how do you know what works?"*) plus **governance** — uniform quality,
   security, and data integrity. **Open** — no verified claims this pass; top
   target for the next research pass.
6. **Cloud vs. air-gapped fork** — forks at the **MCP connector** and **model**
   layers (managed cloud MCP + frontier Claude vs. self-hosted/open-weight).
   Concrete air-gapped substitutions remain **open**. (Constraint: **hybrid**.)

> **Harness shape (research-backed):** orchestrator–worker — a lead agent runs
> the *gather context → act → verify → repeat* loop and dispatches parallel,
> context-isolated **subagents** (one per source) that retrieve via MCP and hand
> back only findings; the lead persists its plan to **Memory** for long
> multi-hop investigations. `# research(2026-06):`
> [details](./docs/research/best-practice-architecture.md).

---

## Phased build order (provisional — confirm against research)

> This ordering is a sensible default to be validated/replaced by the research
> findings. It exists so Phase 1 can start the moment the MVP boundary is set.

### Phase 0 — Scaffold & research  *(nearly complete)*
- [x] Repo scaffold: uv + ruff + ty + pytest, Makefile, dev-runner, docs, CI-ready layout.
- [x] Capture Claude Agent SDK primitives reference → `docs/research/claude-agent-sdk-reference.md`.
- [x] Land deep-research report → `docs/research/best-practice-architecture.md`; resolve the questions above.
- [x] Stand up the Zensical docs site (`zensical.toml`, `docs/`, GitHub Pages workflow).
- [x] Turn resolved decisions into frozen Phase-1 scope in [IMPL.md](./IMPL.md).

### Phase 1 — Single-store vertical slice
- [x] One connector (likely graph DB) as a callable tool/MCP server.
- [x] An `entity-workup` skill that runs a minimal retrieve → reason → synthesize loop.
- [x] A `PostToolUse` provenance hook recording which tool sourced each fact.
- [x] CLI takes a target **entity or organizational node**, returns a cited analytic note. End-to-end on one store.

### Phase 2 — Heterogeneous retrieval
- [x] **Relational/SQL connector built** — `relational/postgres_server.py` +
      `infra/postgres/` (synthetic personnel seed with a planted cross-modality
      link), `postgres-mcp@0.3.0` restricted mode; seeded-Postgres integration
      test green (2026-06-02). Not yet wired into the workup (next).
- [x] **SQL wired into the workup** (`--sql`): provenance hook cites both stores
      under one `gN` space; the `entity-workup` skill routes by question and
      reconciles. A live two-store run surfaced the Halberd↔Wren cross-modality
      tie, flagged a graph/relational conflict, and scored `grounded=True`
      (2026-06-02). `# research(2026-06): ER-RAG shared-key routing + MADAM-RAG conflict-flagging.`
- [x] **Phase A — Dataset abstraction** (2026-06-03): canonical schema +
      `DatasetAdapter` protocol + `DATASETS` registry + dataset-agnostic indexer +
      synthetic adapter + `--dataset` flag. Decision: [ADR-0006](./docs/architecture/decisions/0006-dataset-agnostic-pipeline.md).
      Full design: [`docs/superpowers/specs/2026-06-03-multi-dataset-pipeline-design.md`](./docs/superpowers/specs/2026-06-03-multi-dataset-pipeline-design.md).
      `# research(2026-06): canonical-data-model pattern (datadriven.io + enterpriseintegrationpatterns.com).`
- [x] **Phase B1 — Live indexing + full-text retrieval** (2026-06-03):
      `document_store.py` `tsvector` GIN index + `websearch_to_tsquery`;
      `load_graph` / `load_documents` idempotent loaders; `ariadne index --dataset <name>` CLI.
      Decision: [ADR-0007](./docs/architecture/decisions/0007-hybrid-retrieval-fulltext-first.md).
- [x] **Phase B2 — Enron HF adapter** (2026-06-03): `EnronAdapter` streams
      `corbt/enron-emails` (Kaminski `kaminski-v` mailbox), maps headers→graph
      and body→Document deterministically; registered in `DATASETS`; `kaminski-aol`
      eval needle scores the non-obvious cross-account tie. Proves the canonical
      seam generalizes to a second, real corpus.
- [x] **Phase B3.1 — Semantic leg, data layer** (2026-06-03): injectable
      `Embedder` protocol (`FakeEmbedder` hermetic + `SentenceTransformerEmbedder`
      default `bge-small-en-v1.5`), pgvector `embedding vector(N)` column + HNSW
      cosine index on `documents`, `hybrid_search` RRF-fuses full-text + vector
      legs (`1/(k+rank)`, k=60). Decision: [ADR-0007](./docs/architecture/decisions/0007-hybrid-retrieval-fulltext-first.md).
- [x] **Phase B3.2 — Hybrid search wired into the live agent loop (2026-06-03):**
      in-process `mcp__ariadne__hybrid_search` SDK tool + `--semantic` flag +
      provenance hook records `mcp__ariadne__` calls for `[cite:gN]`; skill routes
      email-body queries to it. ADR-0007 hybrid retrieval is now complete
      end-to-end: full-text + semantic + RRF in the live loop. The live Kaminski
      demo exercises graph + full-text + semantic together.
- [ ] **Phase C — Avocado adapter:** local PST/export → canonical; `access="restricted"`,
      access-gated behind `ARIADNE_ALLOW_RESTRICTED=1`; malware caveat (loveletter,
      ~27 msgs) — ingest text/headers only. Built now, populated when licensed data
      is provided.
- [ ] Add the vector/unstructured connector.
- [ ] Subagent fan-out for parallel per-store retrieval — **deferred pending a
      design pass** (not blocked on research). Naive fan-out conflicts with the
      slice's two load-bearing properties: cross-store **reconciliation** is a
      shared-context task (the research doc flags fan-out as *not* generalising to
      shared-context work), and the parent-side `PostToolUse` `gN` provenance hook
      never sees a subagent's isolated tool calls (only its summary returns). The
      correct shape — workers retrieve in parallel and return *pre-cited* evidence,
      lead reconciles — is a real provenance redesign. YAGNI for a 2-store slice
      already scoring `grounded=True`; revisit at higher store count / context
      pressure (fan-out costs ~15× tokens). See IMPL.md.

  > **SQL connector — decided.** `# research(2026-06):` use
  > [`crystaldba/postgres-mcp`](https://github.com/crystaldba/postgres-mcp)
  > ("Postgres MCP Pro") in **Restricted Mode** — read-only transactions,
  > execution-time caps, SQL parsed with `pglast` to reject COMMIT/ROLLBACK
  > statement-stacking. **Avoid** the official `@modelcontextprotocol/server-postgres`:
  > its `BEGIN TRANSACTION READ ONLY` guardrail is bypassable via semicolon
  > statement-stacking — a confirmed SQLi through v0.6.2
  > ([Datadog Security Labs](https://securitylabs.datadoghq.com/articles/mcp-vulnerability-case-study-SQL-injection-in-the-postgresql-mcp-server/)).
  > Mirrors the Phase-1 official-guardrailed-server-over-hand-rolled call.
  > `XiYanSQL` MCP is an optional Text2SQL alternative (local-deployable).
  > Vector connector, source-routing, and subagent fan-out still need a clean
  > research pass — the verified run only confirmed the SQL choice.

  > **Redis vs. Postgres for the relational store — decided: stay on Postgres.**
  > Full comparison in
  > [ADR-0004](./docs/architecture/decisions/0004-postgres-over-redis-for-relational-store.md)
  > (the canonical record). `# research(2026-06):` Redis is a category mismatch for this connector's job
  > (structured attribute retrieval, cross-store entity resolution via joins,
  > auditable evidence): it is an in-memory key-value store with no relational
  > join engine, and "provides no memory-management logic" of its own. The brief's
  > governance/validation spine wants durable, ACID, auditable evidence — exactly
  > Postgres's strength with our restricted read-only + `pglast` guard. The 2026
  > trend runs *toward* Postgres-as-substrate (pgvector, `SKIP LOCKED`,
  > `LISTEN/NOTIFY` displacing classic Redis patterns); consensus is "start on
  > Postgres for reliability/auditability, add Redis only when latency profiling
  > proves a bottleneck" — and a sensemaking workup has no sub-ms hot path. Redis
  > *does* fit two **additive** roles, not a swap: (a) the agent **memory/session**
  > layer for long investigations (official
  > [`redis/agent-memory-server`](https://github.com/redis/agent-memory-server)
  > exposes an MCP interface, sub-ms reads); (b) **one** candidate for the open
  > vector connector below (Redis 8 folds in RediSearch vector search) — but
  > `pgvector` is the consolidation-friendly rival there, so that fork settles when
  > we build the connector, not now. Sources:
  > [SitePoint](https://www.sitepoint.com/state-management-for-long-running-agents-redis-vs-postgres/) ·
  > [Alongside](https://www.alongside.team/blog/redis-vs-postgresql-agent-memory-session-state) ·
  > [PingCAP](https://www.pingcap.com/compare/best-database-for-ai-agents/) ·
  > [redis/mcp-redis](https://github.com/redis/mcp-redis).

  > **Research watch — vector-store compression.** `# research(2026-06):` Google's
  > [TurboQuant](https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/)
  > (PolarQuant + QJL; ICLR/AISTATS 2026) does near-lossless vector quantization
  > with *zero-overhead* quantization constants — claims strong recall at low bit
  > rates for similarity search. Evaluate when choosing the embedding/vector index
  > for this connector. **Caveat:** research papers only, no released library as of
  > 2026-06 — treat as directional, not a dependency.

### Phase 3 — Multimodal fusion
- [ ] Image / video / OCR / NLP extraction tools.
- [ ] Cross-modal evidence fusion into the analytic product.

### Phase 4 — Rigor, eval & integration
- [x] **Citation gate v2 — Stage 1 (coverage/recall):** uncited-claim detection
      (2026-06-02). Brought forward because it closed a confirmed governance hole.
      `# research(2026-06): ALCE citation recall.`
- [x] **Citation gate v2 — Stage 2 (entailment/precision):** `EntailmentVerifier`
      protocol + HHEM-2.1-Open adapter behind the optional `eval` extra (2026-06-02;
      real-model integration test green). `# research(2026-06): ALCE precision + HHEM.`
- [x] **Tradecraft lint (ICD-203):** `lint_estimative_language` flags non-standard
      estimative hedges, maps WEP terms to bands, detects the confidence axis
      (2026-06-02; advisory `tradecraft.json`). `# research(2026-06): ICD-203 WEP.`
- [x] **Estimative claims routed out of the entailment gate** (2026-06-03):
      `tradecraft.is_estimative` (ICD-203 hedges / WEP terms / confidence) gates
      `find_unsupported_claims`, so a calibrated analytic judgment is checked by
      the calibration lint, not falsely rejected by HHEM. Separates factual
      precision from analytic calibration. `# research(2026-06): ICD-203 likelihood vs ALCE entailment.`
- [x] **LLM-rubric scoring of the analytic standards + `--entail` flag (2026-06-04):**
      `evaluation/rubric.py` scores a note against four ICD-203 standards the
      mechanical gates cannot see (alternatives / argumentation / relevance /
      accuracy) — pointwise, criterion-separated, anchored 1-5, via an injected
      `AnalyticJudge` (hermetic fake; real `ClaudeAnalyticJudge` behind the
      `rubric` extra, forced tool-use). `ariadne rubric <dir>` (API-gated,
      optional `--min` CI gate). `workup --entail` wires the HHEM entailment
      verifier into the citation gate. Decision:
      [ADR-0011](./docs/architecture/decisions/0011-llm-rubric-analytic-standards-eval.md).
      `# research(2026-06): LLM-Rubric (pointwise, criterion-separated, anchored) + judge-bias mitigations.`
- [x] **Evaluation harness (planted-needle):** `ariadne eval <dir>` scores recall
      / trajectory / `grounded` (surfaced AND traversed, not guessed) / pivot-burden
      against the Compound-Alpha fixture (2026-06-02; the real Halberd workup scores
      `grounded=True`). `# research(2026-06): MuSiQue + AgenticRAGTracer.`
- [x] **Per-edge supporting-fact F1 + cross-store needle** (2026-06-02): statement
      extraction is connector-agnostic (Postgres `sql` counts toward trajectory);
      `WREN_TIE_FIXTURE` scores the cross-modality Halberd↔Wren shared-employer tie
      (`grounded` requires the relational store was actually queried, so a graph-only
      assertion is caught as a guess); per-edge precision/recall/F1 on both fixtures;
      `ariadne eval --fixture {halberd,wren-tie}`. The heterogeneous-retrieval
      capability is now measurable. `# research(2026-06): HotpotQA/MuSiQue supporting-fact F1.`
- [ ] Extend the harness further: more needle fixtures, the reconciliation
      criterion as a first-class score, and governance checks (quality, security,
      data integrity).
- [x] **`entity-workup` skill-prompt improvement (2026-06-04):** the note template
      gained **Alternatives considered** (analysis of competing hypotheses) +
      **Implications** sections and an explicit analytic-confidence sentence; the
      skill directs an ACH on the decisive finding and proportionate, hedged
      judgments. Measured before→after on a live Halberd workup (ICD-203 rubric):
      `alternatives` 4→5, overall **4.50→4.75**, `grounded=True` preserved.
      `# research(2026-06): SATs for LLM analytic writing — ACH / key-assumptions.`
- [ ] Provenance/citation surface in the analytic product; confidence handling.
- [ ] SCADS integration interfaces: document how sibling tools plug in as callable tools.
- [ ] Capture **reusable workflow patterns** (a brief deliverable) for future SCADS use cases.

### Phase 5 — Deployment hardening
- [ ] Resolve the cloud-vs-air-gapped fork per component; document the swap points.
- [ ] **Publish to PyPI** so `uvx ariadne-mcp` installs without a local checkout
      (the one remaining distribution step from ADR-0009). Blocked on AJ: needs a
      PyPI token + a non-`ariadne` package name (taken by the GraphQL lib).
- [x] **Observability — traces + metrics for the MCP server / harness (2026-06-03).** [ADR-0010](./docs/architecture/decisions/0010-observability-opentelemetry.md).
      `# research(2026-06):` instrument with **OpenTelemetry GenAI semantic
      conventions** (CNCF-backed, adopted by Datadog/Google/AWS/Azure) — the
      standard span tree is `invoke_agent` → `chat` (per LLM call) → `execute_tool`
      (per evidence tool call), with `gen_ai.*` attributes (model, input/output
      tokens, finish reason). The Claude Agent SDK already emits OTEL via
      `CLAUDE_CODE_ENABLE_TELEMETRY=1` + an OTLP exporter — wire that through plus a
      handful of Ariadne-specific spans/metrics. **Most of the metrics already
      exist as artifacts; this surfaces them as telemetry:**
      - *task duration / time-to-report* — **new** (wrap `run_workup`; per-phase
        gather→act→verify→synthesize timing).
      - *# queries* — already the provenance-ledger `gN` count (`provenance.jsonl`);
        emit per `execute_tool` span + a counter.
      - *accuracy report* — already the eval harness (`recall` / `trajectory` /
        `grounded` / supporting-fact F1); emit as metrics when a fixture is scored.
      - *compliance* — already the citation gate (`uncited` / `unsupported` /
        `dangling`) + ICD-203 tradecraft lint; emit pass/fail + counts as
        span events / metrics.
      Net: one OTEL layer turns the existing `citations.json` / `tradecraft.json` /
      eval scores + new timing into dashboards (latency, query volume, accuracy,
      governance compliance per run). Sources:
      [OTel GenAI observability](https://opentelemetry.io/blog/2026/genai-observability/),
      [agentic-system conventions](https://github.com/open-telemetry/semantic-conventions/issues/2664).

  > **Research watch — on-prem serving efficiency.** `# research(2026-06):`
  > [TurboQuant](https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/)
  > also compresses the **LLM KV cache** (~6× smaller, 3-bit, ~8× faster attention
  > on H100) with no fine-tuning — relevant only to the **self-hosted / open-weight**
  > branch where we serve models ourselves (not the cloud frontier-model path).
  > Consider when sizing on-prem inference. Same caveat: unreleased research.

### Stretch (post-MVP — from the brief)
- [ ] Multi-player shared sessions (collaborative analyst workflows).
- [ ] Tooling that raises analysts' domain knowledge / analytic capacity.

> **Completed work** is the `[x]` items in the phases above — that is the
> one-line ledger of what's done. The full record of *how* each shipped lives in
> `docs/superpowers/plans/`, the ADRs, and git history.
