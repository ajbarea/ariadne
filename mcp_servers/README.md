# mcp_servers/

MCP server connectors surface heterogeneous stores as callable tool families. The shipped
connectors live in [`src/ariadne/`](../src/ariadne/), each building the stdio config for an
official, guardrailed MCP server (ADR-0002) rather than hand-rolling one:

- **graph** — `graph/neo4j_server.py`: read-only Neo4j via `mcp-neo4j-cypher` → `mcp__neo4j__*`
- **relational** — `relational/postgres_server.py`: restricted Postgres via `postgres-mcp` → `mcp__postgres__*`
- **vector / unstructured** — `unstructured/`: the in-process Ariadne hybrid-search server → `mcp__ariadne__hybrid_search`

Decide per store whether a connector is a separate MCP server (reusable,
language-agnostic, isolatable) or an in-process [tool](../tools/). Credentials
and endpoints come from the environment — never from tracked files. Grant access
with scoped `allowedTools` patterns (e.g. `mcp__graph__*`). See the
[SDK reference](../docs/research/claude-agent-sdk-reference.md), §5.

This directory is also where **sibling-project integration interfaces**
land: a sibling's graph-extraction or entity-resolution capability is surfaced
here as a callable MCP tool rather than reimplemented.
