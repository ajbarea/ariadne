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
[best-practice research](research/best-practice-architecture.md). Treat the
still-open items as unsettled; don't harden code against one answer.

1. **MVP toolset boundary**: smallest set of tools/skills/hooks that
   demonstrates end-to-end value; build vs. expose a stub for a sibling SCADS
   project.
2. **Graph / multi-hop reasoning**: GraphRAG vs. agent-driven Cypher traversal
   vs. hybrid; entity resolution across stores. *(Research: hybrid graph+text +
   agentic correction; GraphRAG for multi-hop only.)*
3. **Connector strategy**: MCP servers vs. in-process tools per store.
   *(Research: MCP tool families per store.)*
4. **Multimodal processing**: extraction tools and cross-modal fusion.
   *(Research: convert imagery/video to structured text, then reason.)*
5. **Analytic rigor & eval**: provenance, grounding, confidence, success
   metrics, structured analytic techniques. *(Researched and shipped: citation
   gate, ICD-203 tradecraft lint, planted-needle + rubric eval, governance audit;
   see the [analytic-rigor research](research/analytic-rigor-eval.md).)*
6. **Cloud vs. air-gapped fork**: per-component swap points. *(Resolved as a
   single seam at the orchestrator model; see
   [ADR-0012](architecture/decisions/0012-cloud-vs-air-gapped-deployment-fork.md).
   Remaining work is open-weight validation, not architecture.)*

## Phased build order

| Phase | Focus | Status |
| ----- | ----- | ------ |
| **0** | Scaffold & research | ✅ complete: toolchain, docs site, captured research |
| **1** | Single-store vertical slice | ✅ complete: Neo4j connector + `entity-workup` skill + provenance hook + `ariadne workup` (entity → cited note) |
| **2** | Heterogeneous retrieval | mostly complete: Postgres SQL connector + hybrid (full-text + vector, RRF) wired into the loop; dataset-agnostic seam; subagent fan-out deferred ([ADR-0005](architecture/decisions/0005-defer-subagent-fan-out.md)) |
| **3** | Multimodal fusion | planned: multimodal-to-text extraction; cross-modal evidence fusion |
| **4** | Rigor, eval & integration | mostly complete: citation gate, ICD-203 tradecraft lint, planted-needle + rubric eval, reconciliation scoring, read-only governance gate, SCADS integration interfaces |
| **5** | Deployment hardening | mostly complete: cloud-vs-air-gapped fork resolved ([ADR-0012](architecture/decisions/0012-cloud-vs-air-gapped-deployment-fork.md)); OpenTelemetry observability; model profiles ([ADR-0013](architecture/decisions/0013-user-selectable-model-profiles.md)); published to PyPI as `ariadne-sensemaking` via trusted publishing; open-weight validation remains |
| **6** | Adaptive & self-improving harness | first slices complete ([ADR-0020](architecture/decisions/0020-adaptive-self-improving-ariadne.md)): adapt to a user's own Postgres (introspect, propose a mapping, ratify, run the existing pipeline unchanged); a declarative user ontology; a dynamic MCP surface; and bounded, audited self-improvement, `distil` / `reflect` / `compare` / `distil --into` (learn from a good run, reflect on a poor one, measure net effect, deepen a skill) on a propose-ratify-freeze spine |

## Recently shipped

- **2026-06-08**: Published to PyPI as `ariadne-sensemaking` (GitHub trusted publishing);
  first-run UX polish (corrected quickstart paths, surfaced the interactive report,
  actionable run-dir errors, pre-flight store-reachability before the live loop).
- **2026-06-07**: Adaptive & self-improving harness (Phase 6, first slices): schema
  introspection into a ratified mapping that the existing pipeline runs unchanged; a
  declarative user ontology; a dynamic MCP surface; and bounded, audited self-improvement
  (`distil`, `reflect`, `compare`, `distil --into`) on a propose-ratify-freeze spine.
- **2026-06-04/05**: LLM-rubric analytic-standards eval, reconciliation scoring,
  read-only governance hard-fail gate, user-selectable model profiles, SCADS
  integration interfaces + reusable workflow patterns, OpenTelemetry observability.
- **2026-06-03**: Dataset-agnostic pipeline (canonical schema + adapters),
  live indexing + hybrid full-text/semantic retrieval, Enron adapter.
- **2026-06-02**: Heterogeneous (graph + SQL) retrieval in the live loop;
  planted-needle eval harness; citation gate v2 (recall + entailment).
- **2026-06-01**: Repo scaffolded; Claude Agent SDK reference captured;
  best-practice research synthesized; Zensical docs site stood up.

The canonical [`ROADMAP.md`](https://github.com/ajbarea/ariadne/blob/main/ROADMAP.md)
carries the full per-item ledger with research provenance.
