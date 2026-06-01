# Roadmap

A living plan for the sensemaking harness. The canonical source is
[`ROADMAP.md`](https://github.com/ajbarea/ariadne/blob/main/ROADMAP.md) in the
repo; this page mirrors it for the docs site.

**Stance:** ground every architectural choice in current best practice.
Web-search the specific target's primary docs at the planning step; prefer an
architectural fix over an expedient patch. Each committed design decision carries
a `# research(YYYY-MM):` provenance note.

## Open architecture questions

Resolved (or partly resolved) by the
[June-2026 research](research/best-practice-architecture.md); treat the
still-open items as unsettled — don't harden code against one answer.

1. **MVP toolset boundary** — smallest set of tools/skills/hooks that
   demonstrates end-to-end value; build vs. expose a stub for a sibling SCADS
   project.
2. **Graph / multi-hop reasoning** — GraphRAG vs. agent-driven Cypher traversal
   vs. hybrid; entity resolution across stores. *(Research: hybrid graph+text +
   agentic correction; GraphRAG for multi-hop only.)*
3. **Connector strategy** — MCP servers vs. in-process tools per store.
   *(Research: MCP tool families per store.)*
4. **Multimodal processing** — extraction tools and cross-modal fusion.
   *(Research: convert imagery/video to structured text, then reason.)*
5. **Analytic rigor & eval** — provenance, grounding, confidence, success
   metrics, structured analytic techniques. *(Open — next research pass.)*
6. **Cloud vs. air-gapped fork** — per-component swap points. *(Partly open.)*

## Phased build order

| Phase | Focus | Lands |
| ----- | ----- | ----- |
| **0** *(in progress)* | Scaffold & research | toolchain, docs site, captured research |
| **1** | Single-store vertical slice | graph connector + `entity-workup` skill + provenance hook + CLI (entity → cited note) |
| **2** | Heterogeneous retrieval | SQL + vector connectors; source-routing + reconciliation; subagent fan-out |
| **3** | Multimodal fusion | multimodal-to-text extraction; cross-modal evidence fusion |
| **4** | Rigor, eval & integration | provenance surface, confidence, eval harness, SCADS sibling-tool interfaces |
| **5** | Deployment hardening | resolve cloud-vs-air-gapped fork per component |

## Shipped

- **2026-06-01** — Repo scaffolded; Claude Agent SDK reference captured;
  June-2026 best-practice research synthesized; Zensical docs site stood up.
