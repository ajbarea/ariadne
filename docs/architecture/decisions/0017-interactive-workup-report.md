# 0017, Results presentation — a self-contained interactive workup report

- **Status:** Accepted (2026-06-05) — v1 shipped: `ariadne report <dir>` -> self-contained `report.html` (cited note + clickable-provenance evidence drawer + radial provenance-thread graph + trajectory + run dashboard). The accurate entity-subgraph view (reconstructed from a structured workup emission) remains a follow-on.
- **Deciders:** Ariadne maintainers

## Context

A workup currently outputs `note.md` (the analytic note with `[cite:gN]` tags) plus
`provenance.jsonl`, `citations.json`, `tradecraft.json`, `governance.json`. The
human-facing artifact is the flat Markdown note. The question: is a written
summary good enough for the quality bar, and how else should an analyst explore a
result?

A flat note **buries exactly what makes Ariadne trustworthy.** The `[cite:gN]`
tags are dead text — you cannot click a claim to see the Cypher/SQL that grounds
it. The entity subgraph the agent traversed (the Halberd→Signals-Cell→
Compound-Alpha bridge) is invisible. Reconciliation (corroboration/conflict) is
prose, not a comparison. The agent's evidence trajectory (`g1…gN`) is in a JSONL
file no analyst opens. For a tool whose whole value proposition is **auditable,
provenance-grounded, cross-store-reconciled** analysis, the presentation layer
should make provenance and structure **explorable**, not just assert them.

## Decision drivers

- **Provenance must be navigable**, not asserted — the audit trail is the product.
- **Air-gappable + lean** (ADR-0012): no new runtime service, no cloud, works
  offline; mirrors the existing zero-dependency themed architecture diagram.
- **Reuse what exists**: the report should render the artifacts already produced
  (`note.md` + the four JSON/JSONL files), not require new agent work.
- **Analyst-first**: link-analysis / entity-graph exploration is the dominant
  sensemaking paradigm (Maltego, Palantir Object Explorer, i2); GraphRAG result
  tools (XGraphRAG) add an inference-trace + entity-explore view.

## Considered options

### A. Self-contained interactive HTML report (chosen direction)

`ariadne workup` also emits `report.html` — one file, no server, opens in any
browser, embeds its data inline. Four linked views over the existing artifacts:

1. **Cited note** — render `note.md`; every `[cite:gN]` is a chip that, on click,
   reveals the ledger entry (the exact graph/SQL/text query + result excerpt).
   The audit trail becomes navigable.
2. **Entity graph** — the traversed subgraph (reconstructed from the ledger's
   graph queries) as an interactive node-link diagram with pan/zoom and
   "search-around" expansion. Cytoscape.js, **vendored as a single offline file**
   (built-in layouts + graph algorithms; air-gap-friendly).
3. **Provenance trajectory** — `g1…gN` in order: what was queried, in sequence,
   which facts each grounded. Mirrors XGraphRAG's inference-trace view and ties to
   the eval `trajectory` / `pivot_burden` metrics.
4. **Reconciliation panel** — corroborations (stores agree) and conflicts (stores
   disagree) as side-by-side store evidence with agree/conflict badges; surfaces
   the reconciliation criterion visually.

- **Pros:** zero runtime deps / offline / air-gappable; portable single artifact
  an analyst can keep, diff, and share; reuses existing outputs; extends the
  existing `report/` module and the zero-dep-diagram precedent.
- **Cons:** not a live, server-backed exploration (cannot re-query the stores from
  the page); one vendored JS asset to keep current.

### B. Full web application (server + SPA)

- **Pro:** live re-query, richest interactivity.
- **Con:** a new always-on service + build toolchain, conflicting with the lean,
  air-gappable ethos; large surface for a pre-release single-analyst tool. YAGNI.

### C. Jupyter / notebook widgets

- **Pro:** fast to prototype; familiar to data scientists.
- **Con:** needs a kernel + environment; not analyst-portable; not a shippable
  artifact. Good for ad-hoc exploration, wrong as the default deliverable.

### D. TUI (terminal UI)

- **Pro:** matches the CLI-first posture.
- **Con:** no real graph visualization; the entity-exploration view is the point.

## Decision

**Adopt option A as the direction.** Make the self-contained interactive HTML
report the primary human-facing deliverable, generated alongside `note.md` from
the artifacts already produced — no new agent work, no service, offline. Build
incrementally: (1) cited-note + clickable provenance first (highest value, pure
text+JSON), (2) the entity graph, (3) trajectory + reconciliation panels.
Notebook/web-app remain available later for use cases A does not cover; this ADR
is superseded if a live re-query surface becomes a first-class need.

## Consequences

- New `report/html.py` rendering one self-contained file; one vendored offline JS
  asset (Cytoscape.js) tracked in-repo with a pinned version.
- The CLI gains a `report.html` output (and optionally `ariadne report <dir>` to
  (re)render a persisted workup without re-running the agent).
- Presentation reads only persisted artifacts → testable hermetically (golden-file
  assertions on generated HTML), no live stores needed.
- The note stays the source of truth; the report is a *view*, so nothing about the
  provenance/citation contract changes.

## Sources

- [XGraphRAG — interactive visual analysis for graph-based RAG (inference-trace, entity-explore views)](https://arxiv.org/pdf/2506.13782)
- [LLM agents for interactive workflow provenance — provenance-aware exploration architecture](https://arxiv.org/html/2509.13978v2)
- [Maltego / Palantir Object Explorer / i2 — link-analysis entity sensemaking paradigm](https://blackdotsolutions.com/blog/best-osint-tools)
- [Cytoscape.js — offline-capable graph viz with built-in layouts + algorithms](https://js.cytoscape.org/)
