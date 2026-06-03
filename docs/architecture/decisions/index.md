# Decision log

Architectural decisions for Ariadne, recorded as **ADRs** (Architecture Decision
Records) in the [MADR](https://adr.github.io/madr/) format. One file per decision.
This is the single place to point to when someone asks *"why did you choose X
instead of Y?"* — each record names the alternatives that were considered, why
they lost, and what the choice costs us.

## Why we keep these

Decisions get made constantly and then disappear into chat logs and commit
messages. An ADR is a small, dated, immutable record of one decision and its
*rejected* alternatives, kept in source control next to the code so it stays in
sync. When the context changes, we don't edit the old record — we supersede it
with a new one.

## When to write one

Write an ADR when a choice is **architecturally significant and contestable**: a
store, a framework, a connector, a security posture, a deferral. Skip it for
reversible implementation details. A good trigger is *"a reviewer could
reasonably ask why we didn't do it the other way."* Each design choice should
still carry its `# research(YYYY-MM):` provenance at the code/roadmap level; the
ADR is where the *comparison* lives.

## The records

| # | Decision | Status |
| - | -------- | ------ |
| [0001](0001-orchestration-on-claude-agent-sdk.md) | Orchestrate on the Claude Agent SDK | Accepted |
| [0002](0002-official-mcp-connectors-over-hand-rolled.md) | Use official MCP connectors over hand-rolled wrappers | Accepted |
| [0003](0003-postgres-mcp-restricted-mode.md) | Expose Postgres via `postgres-mcp` Restricted Mode | Accepted |
| [0004](0004-postgres-over-redis-for-relational-store.md) | Keep Postgres (not Redis) for the relational store | Accepted |
| [0005](0005-defer-subagent-fan-out.md) | Defer subagent fan-out pending a design pass | Deferred |

## Template

New records follow the MADR shape: **Context → Decision drivers → Considered
options (with pros/cons) → Decision → Consequences**, plus a one-line status and
the sources behind the call. Copy an existing record and keep it to a single
decision.
