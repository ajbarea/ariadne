# Ariadne — Roadmap

A living plan for the sensemaking harness. Items are **planned** (full detail)
or **shipped** (one-liner with date). Whatever's *in flight right now* lives in
[IMPL.md](./IMPL.md).

Last reviewed: 2026-06-01 (repo scaffolded; June-2026 architecture research
**landed** — a deep-research synthesis plus a captured Claude Agent SDK reference
under [docs/research/](./docs/research/); Zensical docs site stood up).

Stance: **ground every architectural choice in current best practice.**
Web-search the specific target's primary docs at the planning step; prefer an
architectural fix over an expedient patch. Each committed design decision in
this file should carry a `# research(YYYY-MM):` provenance note.

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
   **Open** — no verified claims this pass; top target for the next research pass.
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
- [ ] CLI takes a target entity, returns a cited analytic note. End-to-end on one store.

### Phase 2 — Heterogeneous retrieval
- [ ] Add relational/SQL and vector/unstructured connectors.
- [ ] Source-routing: agent decides which store to query; reconcile overlapping results.
- [ ] Subagent fan-out for parallel per-store retrieval.

### Phase 3 — Multimodal fusion
- [ ] Image / video / OCR / NLP extraction tools.
- [ ] Cross-modal evidence fusion into the analytic product.

### Phase 4 — Rigor, eval & integration
- [ ] Provenance/citation surface in the analytic product; confidence handling.
- [ ] Evaluation harness for the four success criteria (traversal, reconciliation,
      pivot-burden reduction, non-obvious connections).
- [ ] SCADS integration interfaces: document how sibling tools plug in as callable tools.

### Phase 5 — Deployment hardening
- [ ] Resolve the cloud-vs-air-gapped fork per component; document the swap points.

---

## Shipped

- **2026-06-01** — Repo scaffolded; Claude Agent SDK reference captured;
  June-2026 best-practice research synthesized; Zensical docs site stood up.
