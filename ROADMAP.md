# Ariadne — Roadmap

A living plan for the sensemaking harness. Items are **planned** (full detail)
or **shipped** (one-liner with date). Whatever's *in flight right now* lives in
[IMPL.md](./IMPL.md).

Last reviewed: 2026-06-01 (repo scaffolded; June-2026 architecture research
**landed** — a deep-research synthesis plus a captured Claude Agent SDK reference
under [docs/research/](./docs/research/); Zensical docs site stood up; project
charter distilled from the SCADS onboarding brief into **Mission & charter**
below).

Stance: **ground every architectural choice in current best practice.**
Web-search the specific target's primary docs at the planning step; prefer an
architectural fix over an expedient patch. Each committed design decision in
this file should carry a `# research(YYYY-MM):` provenance note.

---

## Mission & charter

> Distilled from the SCADS onboarding brief — **Project 1: "Sensemaking for
> Nonatomic Entities using AI Coding Agents"** — and archived here 2026-06-01.
> The brief is not retained; this section is now its system of record.

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
- [ ] Turn resolved decisions into frozen Phase-1 scope in [IMPL.md](./IMPL.md).

### Phase 1 — Single-store vertical slice
- [ ] One connector (likely graph DB) as a callable tool/MCP server.
- [ ] An `entity-workup` skill that runs a minimal retrieve → reason → synthesize loop.
- [ ] A `PostToolUse` provenance hook recording which tool sourced each fact.
- [ ] CLI takes a target **entity or organizational node**, returns a cited analytic note. End-to-end on one store.

### Phase 2 — Heterogeneous retrieval
- [ ] Add relational/SQL and vector/unstructured connectors.
- [ ] Source-routing: agent decides which store to query; reconcile overlapping results.
- [ ] Subagent fan-out for parallel per-store retrieval.

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
- [ ] Provenance/citation surface in the analytic product; confidence handling.
- [ ] Evaluation harness for the four success criteria (traversal, reconciliation,
      pivot-burden reduction, non-obvious connections); add a spec/validation pass
      ("how do you know it works?") and governance checks (quality, security,
      data integrity).
- [ ] SCADS integration interfaces: document how sibling tools plug in as callable tools.
- [ ] Capture **reusable workflow patterns** (a brief deliverable) for future SCADS use cases.

### Phase 5 — Deployment hardening
- [ ] Resolve the cloud-vs-air-gapped fork per component; document the swap points.

  > **Research watch — on-prem serving efficiency.** `# research(2026-06):`
  > [TurboQuant](https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/)
  > also compresses the **LLM KV cache** (~6× smaller, 3-bit, ~8× faster attention
  > on H100) with no fine-tuning — relevant only to the **self-hosted / open-weight**
  > branch where we serve models ourselves (not the cloud frontier-model path).
  > Consider when sizing on-prem inference. Same caveat: unreleased research.

### Stretch (post-MVP — from the brief)
- [ ] Multi-player shared sessions (collaborative analyst workflows).
- [ ] Tooling that raises analysts' domain knowledge / analytic capacity.

---

## Shipped

- **2026-06-01** — Repo scaffolded; Claude Agent SDK reference captured;
  June-2026 best-practice research synthesized; Zensical docs site stood up.
- **2026-06-01** — Project charter distilled from the SCADS onboarding brief into
  **Mission & charter** (problem, central research question, deliverables, success
  criteria, design constraints, program context); source PDF removed.
