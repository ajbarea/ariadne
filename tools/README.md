# tools/

Custom, in-process agent tools (connectors and modality-specific processors) would live here.
In practice the research ([ADR-0002](../docs/architecture/decisions/0002-official-mcp-connectors-over-hand-rolled.md))
chose **MCP-server connectors over in-process tools**, so the store connectors live in
[`src/ariadne/`](../src/ariadne/) (`graph/`, `relational/`, `unstructured/`); this directory is
reserved for any future app-specific in-process tool.

Per the [SDK reference](../docs/research/claude-agent-sdk-reference.md), prefer
in-process SDK tools for app-specific logic and fast iteration; promote a tool to
an [MCP server](../mcp_servers/) when it should be reusable across projects or
run as a separate process. Anticipated early tools (provisional — confirm against
research): a graph-store query tool, a provenance recorder, an entity-resolution
lookup. Each new tool gets a `# research(YYYY-MM):` note in
[`../ROADMAP.md`](../ROADMAP.md).
