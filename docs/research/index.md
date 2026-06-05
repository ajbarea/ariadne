# Research

The research grounding behind Ariadne's architecture. Every committed design
decision traces to a source here, recorded as a `# research(YYYY-MM):` note in
the [Roadmap](../roadmap.md) and, where it became a commitment, an
[Architecture Decision Record](../architecture/index.md).

This directory holds **findings** (what the research learned); the **decisions**
those findings justify live separately as numbered ADRs. The two are kept apart
on purpose — findings are point-in-time and may be superseded; an ADR is the
choice we committed to.

## Findings (deep-research passes)

Each is a dated, adversarially-verified pass. Later passes exist to close the
**open questions** an earlier pass left unresolved — read them as a trail, not a
pile:

- **[Best-Practice Architecture](best-practice-architecture.md)** (2026-06-01) —
  the foundation pass: orchestrator-worker harness, GraphRAG and multi-hop
  reasoning, heterogeneous MCP connectors, multimodal fusion, and the
  minimum-viable architecture. Produced by a deep-research pass (29 sources, 139
  claims, 25 adversarially verified). It closed with **four open questions**; the
  two passes below answer two of them.
- **[Analytic Rigor & Evaluation](analytic-rigor-eval.md)** (2026-06-02) —
  resolves the foundation pass's open question on **analytic rigor** ("how do you
  know it works?"): citation groundedness via NLI entailment, ICD-203/206
  tradecraft-compliance linting, and a planted-needle + LLM-rubric eval harness.
- **[Open-Weight Validation](open-weight-validation.md)** (2026-06-04) —
  resolves the open question on the **air-gapped fork** by turning
  [ADR-0012](../architecture/decisions/0012-cloud-vs-air-gapped-deployment-fork.md)'s
  single-seam claim into measured evidence: a live run on this repo's code with
  only `ANTHROPIC_BASE_URL` swapped, isolating which open-weight model clears the
  eval bar.

Still open from the foundation pass: **entity resolution across stores** and a
fully **empirically-validated phased order** (Phases 1–2 are shipped and the
open-weight run exercised the end-to-end slice, but the full order is not yet
proven). These are the next research targets.

## Reference

- **[Claude Agent SDK Reference](claude-agent-sdk-reference.md)** — doc-cited
  mechanics of the SDK primitives (tools, skills, hooks, subagents, MCP, context
  management, deployment). Not a findings pass; a stable reference the other docs
  and the code link into.

## How this research was produced

Parallel web searches across multiple angles, source de-duplication,
falsifiable-claim extraction, and **adversarial verification** (multi-vote,
majority-refute kills the claim). Confidence levels and open questions are carried
through so unsettled areas stay visible — and so a later pass knows what to go
close.
