# 0002, Use official MCP connectors over hand-rolled wrappers

- **Status:** Accepted (2026-06-01)
- **Deciders:** Ariadne maintainers

## Context

Each store is surfaced to the agent as an MCP tool family. For the graph
connector (Phase 1) we had to choose between the official
[`mcp-neo4j-cypher`](https://github.com/neo4j-contrib/mcp-neo4j) server and an
in-process wrapper we write ourselves. A related sub-question: should the agent
write Cypher directly, or should we add a separate Text2Cypher translation tool?

## Decision drivers

- Read-only enforcement, query timeouts, and result truncation are
  security-critical and easy to get subtly wrong.
- Less bespoke code to maintain; connector behaviour stays language-agnostic and
  reusable.
- The agent loop already excels at writing queries from schema.

## Considered options

- **Official `mcp-neo4j-cypher` server** with `NEO4J_READ_ONLY`, battle-tested
  read-only / timeout / truncation guardrails maintained upstream.
- **Hand-rolled in-process connector**: full control and no subprocess, but we
  reimplement the guardrails and own every edge case.
- **Separate Text2Cypher tool** vs **agent writes read-only Cypher**: an extra
  translation hop vs letting the agent read schema and emit Cypher directly.

## Decision

Use the **official MCP server** with read-only enforcement, and let the **agent
write read-only Cypher directly** (no separate Text2Cypher tool). The same
"official-guardrailed-server-over-hand-rolled" principle is applied to the
relational connector in [ADR-0003](0003-postgres-mcp-restricted-mode.md).

## Consequences

- Security-critical read-only behaviour is delegated to a maintained component.
- Connectors run as stdio subprocesses (one more process per store), accepted for
  the isolation and guardrails it buys.
- Establishes the pattern every future connector follows: prefer a hardened
  official server; only hand-roll when none exists.
