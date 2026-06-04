# 0005, Defer subagent fan-out pending a design pass

- **Status:** Deferred (2026-06-02)
- **Deciders:** Ariadne maintainers

## Context

The [best-practice research](../../research/best-practice-architecture.md) names
an **orchestrator-worker** design, a lead agent dispatching parallel,
context-isolated subagents, one per source, as the headline architecture. The
obvious next step would be to fan out the graph and SQL retrieval into separate
subagents.

## Decision drivers

- Cross-store **reconciliation** (corroborate facts, flag conflicts about the
  same entity) is a *shared-context* task.
- Provenance is the spine: a parent-side `PostToolUse` hook assigns each evidence
  call a `gN` id that citations resolve to.
- Add cost and complexity only when they buy something the current slice needs.

## Considered options

- **Fan out now**: one subagent per store, run in parallel.
- **Defer**: keep the single lead agent with both connectors until a design
  resolves the conflicts below.

## Decision

**Defer.** Naive fan-out collides with two load-bearing properties of the current
slice:

1. **Shared context.** Reconciliation needs both stores' evidence in one context;
   the research explicitly flags multi-agent fan-out as *not* generalising to
   shared-context tasks.
2. **Provenance.** Subagents run in isolated contexts and return only a summary,
   their raw tool calls never reach the parent's `gN` hook, so citations would
   attach to a worker's prose instead of to evidence entries.

A correct design (workers retrieve in parallel and return **pre-cited** evidence;
the lead reconciles) is a real redesign of the provenance layer. It is not
blocked on research, it needs a focused design pass.

## Consequences

- The 2-store slice keeps the single-agent design and already scores
  `grounded=True` on the eval harness.
- Revisit when store count or context pressure justifies the cost (multi-agent
  fan-out runs ~15× the tokens of a single agent).
- When revisited, the provenance redesign is the gating work, not the
  parallelism itself.
