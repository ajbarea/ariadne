# mcp_servers/

MCP server connectors that surface heterogeneous stores as callable tool
families. **Empty until Phase 1.**

Anticipated connectors (provisional — confirm against research):

- **graph** — graph DB (e.g. Neo4j / Cypher) → `mcp__graph__query`, `mcp__graph__get_schema`
- **relational** — SQL store (e.g. Postgres) → `mcp__relational__query`, `mcp__relational__list_tables`
- **vector** — vector / unstructured retrieval → `mcp__vector__search`

Decide per store whether a connector is a separate MCP server (reusable,
language-agnostic, isolatable) or an in-process [tool](../tools/). Credentials
and endpoints come from the environment — never from tracked files. Grant access
with scoped `allowedTools` patterns (e.g. `mcp__graph__*`). See the
[SDK reference](../docs/research/claude-agent-sdk-reference.md), §5.

This directory is also where **SCADS sibling-project integration interfaces**
land: a sibling's graph-extraction or entity-resolution capability is surfaced
here as a callable MCP tool rather than reimplemented.
