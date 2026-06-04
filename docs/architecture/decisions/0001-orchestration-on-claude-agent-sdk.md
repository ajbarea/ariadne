# 0001, Orchestrate on the Claude Agent SDK

- **Status:** Accepted (2026-06-01)
- **Deciders:** Ariadne maintainers

## Context

Ariadne is an orchestration layer over heterogeneous data stores, not a new data
platform. It needs an agent runtime that provides tool use, packaged skills,
lifecycle hooks (for provenance/governance), context-isolated subagents, and a
connector standard (MCP), the exact primitives the
[best-practice research](../../research/best-practice-architecture.md) names for
agentic entity sensemaking.

## Decision drivers

- First-class MCP support, so each store is a callable tool family.
- Hooks that can enforce provenance and authorization without baking them into
  prompts (the governance requirement from the brief).
- Subagents for parallel, context-isolated per-source retrieval.
- The same primitives power Claude Code and Cowork, so patterns transfer.

## Considered options

- **Claude Agent SDK**: native tools / skills / hooks / subagents / MCP;
  doc-cited mechanics captured in the
  [SDK reference](../../research/claude-agent-sdk-reference.md).
- **Open-source agent frameworks (e.g. OpenClaw-style harnesses)**: viable and
  attractive for the air-gapped fork, but weaker/less-uniform hook and MCP
  stories today, and more glue to maintain.
- **Hand-rolled orchestration loop**: maximum control, but we would rebuild
  provenance hooks, subagent isolation, and MCP plumbing from scratch.

## Decision

Build on the **Claude Agent SDK**. It supplies the governance and connector
primitives out of the box and matches the researched best-practice shape.

## Consequences

- Cloud-first/frontier-model path is the default; the air-gapped fork
  (open-weight proxy, self-hosted MCP) is the open deployment question tracked in
  the [roadmap](../../roadmap.md) and is where an open-source harness may
  re-enter.
- Design vocabulary is fixed to SDK primitives, which keeps the architecture docs
  and the code aligned.
