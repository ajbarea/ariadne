# 0015, Subagent fan-out — design specified, implementation gated

- **Status:** Accepted (2026-06-05) — the design pass [ADR-0005](0005-defer-subagent-fan-out.md) called for; extends, does not supersede, its *defer* decision
- **Deciders:** Ariadne maintainers

## Context

[ADR-0005](0005-defer-subagent-fan-out.md) deferred orchestrator-worker fan-out
(one parallel subagent per evidence store) "pending a design pass," naming the
**provenance redesign** as the gating work and shared-context reconciliation +
token cost as the other objections. This is that pass. It revisits the blocker
against the **June 2026** Claude Agent SDK and current multi-agent practice, and
fixes the design so the implementation is a known quantity when the trigger fires.

## What changed since ADR-0005

ADR-0005's load-bearing provenance claim — *"subagents run in isolated contexts
and return only a summary; their raw tool calls never reach the parent's `gN`
hook"* — **no longer holds in the Python SDK.** Per the SDK hooks reference, a
`PostToolUse` hook fires **inside** subagents, and `agent_id` / `agent_type` are
populated on `PreToolUse` / `PostToolUse` / `PostToolUseFailure` when it does.
`make_provenance_hook(ledger)` is a closure registered once on the parent options;
because subagents run in the same SDK process, the *same* hook fires for a
worker's `mcp__*` evidence call and records it into the *same* `ProvenanceLedger`.
The provenance redesign is therefore largely dissolved:

- One shared ledger, one monotonic counter → `gN` ids stay globally unique across
  workers automatically; no per-worker renumbering/merge step.
- The hook's `additionalContext` reaches the worker that made the call, so the
  worker is still told its `[cite:gN]` and can return **pre-cited** prose.
- `agent_id` is available to attribute each ledger entry to its worker (optional
  enrichment, not required for citation correctness).

The remaining objections from ADR-0005 stand:

- **Reconciliation is shared-context.** Cross-store corroboration/conflict needs
  both stores' evidence reasoned over together; that step does not parallelize and
  must converge in the lead.
- **Cost.** Fan-out runs multiples of a single agent's tokens (≈3× for a small
  pipeline, up to ≈15× cited in the foundation research); justified when latency
  matters more than cost and there are **4+ genuinely independent** subtasks.
  Ariadne has 2–3 stores (graph, relational, text) and a fast single-agent workup
  already scoring `grounded=True`.

## Decision drivers

- The provenance spine must stay intact: every cited fact resolves to a ledger
  entry through one auditable surface.
- Parallelism should buy a *measured* latency win, not be added speculatively
  (YAGNI; matches the "4+ independent tasks" fan-out heuristic).
- When we do fan out, the design should be already-decided, not re-litigated.

## Decision

**Specify the design; keep implementation deferred** until a trigger fires.

Specified shape ("fan-out retrieval, converge to reconcile"):

1. The lead decomposes the workup into per-store **retrieval** subtasks and
   dispatches one worker per store in parallel (independent, no shared state).
2. Each worker runs evidence tools; the shared `PostToolUse` provenance hook
   records every call into the one ledger and hands the worker its `[cite:gN]`.
   Workers return **pre-cited** evidence (prose tagged with `[cite:gN]`), not raw
   context.
3. The lead **reconciles in shared context** over the workers' pre-cited returns
   (corroboration / conflict), then synthesizes the note. Citations resolve
   against the unified ledger exactly as today.

**Triggers to implement** (any one):

- Store count reaches **≥4** (e.g. when image/video/OCR stores land per
  [ADR-0008](0008-multimodal-agentic-to-text-not-native-embeddings.md)), crossing
  the fan-out break-even.
- A measured **latency or context-pressure** bottleneck in the single-agent loop
  on a real corpus (Enron/Avocado), not a hypothetical one.

## Consequences

- The 2–3-store slice keeps the single-agent design; no token-cost regression now.
- The hard part is no longer hard: when the trigger fires, fan-out is mostly
  wiring (dispatch + a reconcile-over-pre-cited-returns step), because the SDK
  already carries subagent tool calls through the existing provenance hook.
- **Validation owed at implementation time** (not assumed here): a smoke test that
  a worker's `mcp__*` call actually lands in the shared ledger with `agent_id`
  set, and that the worker receives its `[cite:gN]` — the design rests on the SDK
  doc, which should be confirmed against the installed SDK version before shipping.
- `ProvenanceLedger` may gain an optional `agent_id` column for per-worker
  attribution; the citation contract (`gN` → ledger entry) is unchanged.

## Sources

- [Claude Agent SDK — hooks: `agent_id`/`agent_type` populated when a hook fires inside a subagent (Python: PreToolUse/PostToolUse/PostToolUseFailure)](https://code.claude.com/docs/en/agent-sdk/hooks)
- [Claude Agent SDK — subagents: isolated context, only the final message returns to the parent](https://code.claude.com/docs/en/agent-sdk/subagents)
- [Multi-agent orchestration patterns 2026 — orchestrator-worker is ~70% of production; fan-out for 4+ independent tasks when latency > cost](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)
- Anthropic multi-agent research-system writeup — fan-out token cost (~15× a single agent) and the shared-context caveat (carried from the foundation research pass).
