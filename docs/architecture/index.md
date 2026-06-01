# Architecture

Design notes for Ariadne's harness. **Deliberately thin until the June-2026
research resolves the open questions** in the [Roadmap](../roadmap.md) — hardening
a design before then risks building against the wrong fork.

## Building blocks

The orchestration layer is the **Claude Agent SDK**. Its primitives are the
vocabulary every design choice is expressed in:

- **Tools** — callable retrieval/processing functions (in-process or via MCP).
- **Skills** — packaged multi-step analytic procedures (e.g. `entity-workup`).
- **Hooks** — lifecycle interceptors for provenance, authorization, and audit.
- **Subagents** — context-isolated workers for parallel per-source retrieval.
- **MCP** — the connector standard surfacing graph / SQL / vector stores as tools.

See the [Claude Agent SDK Reference](../research/claude-agent-sdk-reference.md)
for the full doc-cited mechanics.

## Emerging shape (from the research)

The [June-2026 best-practice research](../research/best-practice-architecture.md)
points to an **orchestrator–worker** design: a lead agent runs the canonical
*gather context → take action → verify → repeat* loop and dispatches parallel,
context-isolated subagents — each restricted to one source — that retrieve via
MCP connectors and hand back only their findings. **GraphRAG** is the core
capability for traversing organizational hierarchies; multimodal evidence is
fused **agentically** by converting imagery/video to structured text before
reasoning over it.

## To be written

Once the MVP boundary is set: the end-to-end analytic workflow (entity in →
coordinated tool sequence → cited analytic product), the source-routing /
reconciliation strategy, the entity-resolution approach, the provenance model,
and the cloud-vs-air-gapped component map.
