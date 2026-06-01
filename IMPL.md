# Ariadne — Implementation scratchpad

The active TODO list for what's in flight **right now**. Queued specs and
phase ordering live in [ROADMAP.md](./ROADMAP.md); git history is the archive.
If this file grows past ~50 lines, extract the referential bits back to ROADMAP.

## In flight — Phase 0: scaffold & research

**Done:**
- Repo scaffolded (uv / ruff / ty / pytest, Makefile, dev-runner, docs tree, smoke tests).
- Claude Agent SDK primitives reference captured → `docs/research/claude-agent-sdk-reference.md`.
- June-2026 deep-research synthesized → `docs/research/best-practice-architecture.md`
  (29 sources, 25 claims adversarially verified). Resolved directions recorded in
  ROADMAP with `# research(2026-06):` notes.
- Zensical docs site up (`zensical.toml`, `docs/`, `.github/workflows/docs.yml`);
  builds clean locally (`zensical build` → "No issues found").
- Codename `ariadne` confirmed by AJ.
- Project charter distilled from the SCADS onboarding brief → ROADMAP
  **Mission & charter** (problem, research question, deliverables, success
  criteria, design constraints); source PDF removed.

**Immediate next pickup — freeze Phase-1 scope:**
1. Set the MVP toolset boundary (build vs. sibling-stub) from the research report's
   minimum-viable architecture.
2. Spec Phase 1 here: the **graph connector** (MCP `mcp__graph__*`), the
   **`entity-workup`** skill (gather → act → verify loop), the **provenance**
   `PostToolUse` hook, and the CLI flow (entity **or org node** → cited analytic note).
3. Decide first graph store (Neo4j/Cypher vs. multi-model) — pin with a
   `# research(2026-06):` note when chosen.

**Still open (next research pass, not blocking Phase 1):**
- Analytic rigor / eval — the brief frames it as **specification & validation**
  ("how do you know what works?") + **governance** (quality, security, data
  integrity); plus structured-analytic-technique framing.
- Entity resolution / record linkage across stores.
- Concrete air-gapped substitutions per component.
