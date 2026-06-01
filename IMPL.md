# Ariadne — Implementation scratchpad

The active TODO list for what's in flight **right now**. Queued specs and
phase ordering live in [ROADMAP.md](./ROADMAP.md); git history is the archive.
If this file grows past ~50 lines, extract the referential bits back to ROADMAP.

## Done — Phase 1 shipped

Read-only Neo4j MCP connector, `entity-workup` skill, `PostToolUse` provenance
hook + citation-coverage validator, and `ariadne workup <entity>` CLI are all
committed and gated. Full record in
[docs/superpowers/plans/2026-06-01-phase-1-vertical-slice.md](./docs/superpowers/plans/2026-06-01-phase-1-vertical-slice.md).

## In flight — Phase 2

- Add relational/SQL and vector/unstructured connectors.
- Source-routing: agent decides which store to query; reconcile overlapping results.
- Subagent fan-out for parallel per-store retrieval.

## Still open (next research pass, not blocking Phase 2)

- Analytic rigor / eval — the brief frames it as **specification & validation**
  ("how do you know what works?") + **governance** (quality, security, data
  integrity); plus structured-analytic-technique framing.
- Entity resolution / record linkage across stores.
- Concrete air-gapped substitutions per component.
